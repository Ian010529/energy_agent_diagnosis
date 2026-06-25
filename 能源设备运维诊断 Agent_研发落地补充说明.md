# 能源设备运维诊断 Agent — 研发落地补充说明

## 一、补充目标

现有《实施计划》《详细设计方案》《数据接入方案》已经明确了系统目标、阶段计划、工作流、RAG、工具和数据接入方式。本补充说明主要补齐研发落地所需的工程契约，避免开发阶段出现“设计有了，但代码不知道按什么边界实现”的问题。

本补充说明重点回答：

1. 服务之间怎么分工；
2. 统一数据结构怎么定义；
3. 外部接口接入前需要确认什么；
4. 前后端如何联调诊断进度和结果；
5. 开发任务如何拆分优先级；
6. 什么情况算开发完成。

### 1.1 对齐坐标

本文中的“阶段二”专指数据接入子流程的 D2 Schema 冻结，不替代《实施计划》的全局阶段 0 到阶段 7；P0/P1 仅表示任务优先级。三套坐标同时保留：

1. 全局阶段管理项目交付顺序；
2. D1 Mock、D2 Schema、D3 Real Adapter 管理每个 Provider 的接入成熟度；
3. P0/P1 管理一期内部的必需与增强优先级。

每个 Provider 独立经过 D1 -> D2 -> D3，因此允许设备 Provider 已进入 Real，而工单 Provider 仍使用 Mock，上层工作流不受影响。

------

## 二、建议新增的研发落地边界

一期建议采用“逻辑拆分、物理适度合并”的方式。不要一开始把服务拆得过细，否则会增加联调成本。

| 服务                 | 一期建议                    | 核心职责                                     |
| -------------------- | --------------------------- | -------------------------------------------- |
| `gateway-service`    | 独立                        | 鉴权、限流、创建会话、SSE/WebSocket 输出     |
| `agent-service`      | 独立                        | LangGraph 状态机、诊断流程编排、会话状态控制 |
| `retrieval-service`  | 可与 tool-service 合并      | 查询重写、混合检索、重排、证据包生成         |
| `tool-service`       | 可与 retrieval-service 合并 | 设备、告警、时序、工单、图谱等工具封装       |
| `memory-service`     | 可与 agent-service 合并     | Redis 会话记忆、案例草稿、审核状态、案例入库 |
| `admin-service`      | P1 可做                     | 字典、模板、案例审核、配置管理               |
| `evaluation-service` | 可后置                      | 离线评估、回归测试、Prompt/检索策略对比      |

约束：

1. `agent-service` 不直接访问底层数据库；
2. `retrieval-service` 不生成最终诊断结论；
3. `tool-service` 不做自由推理；
4. `memory-service` 不允许未审核案例进入强证据集；
5. 写入类操作必须经过用户或审核人显式确认。

上述名称是逻辑服务边界，不强制一一对应物理进程。保留以下部署并集：本地开发可整体合并，Mock 联调可按前后端边界拆分，试点环境优先独立 gateway 和 agent，规模扩大后再拆分 retrieval、tool、memory、admin 和 evaluation。

------

## 三、阶段二补充：Schema 冻结与联调契约

建议在 Mock 阶段和 Real Adapter 阶段之间增加一个阶段：

### 阶段二：Schema 冻结与联调契约阶段

目标：

1. 固化 Agent、Tool、Provider、前端之间的数据结构；
2. 明确错误码、状态码、trace_id、幂等要求；
3. 确保 Mock 和 Real 后续可以平滑替换。

核心产出：

1. `RequestContext` 统一请求上下文；
2. `ToolResult` 统一工具返回结构；
3. `EvidencePackage` 统一证据包结构；
4. `DiagnosisResult` 统一诊断输出结构；
5. 外部接口确认单；
6. 错误码与降级策略表；
7. 前端 SSE 事件格式。

验收标准：

1. 所有工具 Mock 返回值符合统一 schema；
2. Agent 工作流只依赖统一 ToolResult，不依赖具体 Provider；
3. 前端能按统一状态展示诊断进度；
4. 任一 Real Adapter 替换 Mock 后，上层工作流无需修改。

------

## 四、标准数据契约

### 4.1 标准诊断请求上下文

所有入口进入 Agent 前，需要转换成统一结构：

```json
{
  "request_id": "req_001",
  "trace_id": "trace_abc",
  "session_id": "diag_s_001",
  "source": "alarm",
  "user": {
    "user_id": "u001",
    "role": "operator"
  },
  "site": {
    "site_id": "SITE-01"
  },
  "device": {
    "device_id": "PCS-10086",
    "device_type": "PCS",
    "device_model": "SC5000",
    "manufacturer": "unknown"
  },
  "alarm": {
    "alarm_id": "ALARM-001",
    "alarm_name": "PCS机柜温度过高",
    "alarm_level": "major",
    "alarm_time": "2026-06-23T10:30:00+08:00"
  },
  "message": "这台 PCS 温度持续升高，先查什么？",
  "options": {
    "stream": true,
    "debug": false
  }
}
```

### 4.2 标准工具返回结构

所有工具统一返回：

```json
{
  "success": true,
  "status": "OK",
  "data": {},
  "error_code": "",
  "error_message": "",
  "trace_id": "trace_abc",
  "source": "mock"
}
```

`status` 建议枚举：

| 状态              | 说明         |
| ----------------- | ------------ |
| `OK`              | 成功         |
| `NOT_FOUND`       | 未找到数据   |
| `PARTIAL_SUCCESS` | 部分成功     |
| `FAILED`          | 调用失败     |
| `TIMEOUT`         | 调用超时     |
| `DEGRADED`        | 使用降级结果 |

约束：

1. `success=false` 时必须带 `error_code`；
2. `trace_id` 必须透传；
3. 工具不直接返回超大原始数据；
4. 时序类工具优先返回摘要，不直接把大量点位塞给 Agent；
5. 写入类工具默认只生成草稿或待确认请求。

### 4.3 ToolResult 超集契约

4.2 的紧凑结构继续有效；为兼容详细设计中的企业级返回信息，Provider 边界同时接受以下超集：

```json
{
  "success": true,
  "status": "OK",
  "data": {},
  "meta": {
    "trace_id": "trace_abc",
    "source_system": "ems",
    "provider_type": "real",
    "partial_result": false,
    "latency_ms": 128
  },
  "error_code": "",
  "error_message": "",
  "warnings": []
}
```

归一化规则：

1. `OK` 是内部成功状态，`SUCCESS` 作为兼容别名；
2. 状态全集为 `OK/SUCCESS`、`PARTIAL_SUCCESS`、`NOT_FOUND`、`TIMEOUT`、`DEGRADED`、`FAILED`；
3. 紧凑结构顶层的 `trace_id` 和 `source` 分别映射到 `meta.trace_id` 和 `meta.provider_type`；
4. 请求入口的 `source` 映射为 `request_source`，Mock/Real 映射为 `provider_type`，EMS/CMDB 等实际系统映射为 `source_system`；
5. `alarm_time/trigger_time`、`start/end`、`start_time/end_time` 均在边界兼容，内部使用 `trigger_time`、`start_time`、`end_time`；
6. 所有时间值必须使用带时区的 ISO8601；
7. Mock 和 Real 必须通过同一套规范化后契约测试。

### 4.4 EvidencePackage 与 DiagnosisResult

`EvidencePackage` 至少包含 `package_id`、`session_id`、`trace_id`、`ranked_evidence`、`degraded_sources` 和 `need_manual_confirmation`。每条证据保留：

1. `evidence_id`、`source_type`、`source_id`；
2. 可选的 `chunk_id`、页码、章节和时间窗；
3. 引用摘要、统一分数、审核状态和来源元数据；
4. 图谱、未审核工单或降级结果的弱证据标记。

`DiagnosisResult` 至少包含 `session_id`、状态、摘要、候选根因、支持与反向证据、排查步骤、安全提示、补充问题、工单建议和 `evidence_package_id`。关键结论引用的 `evidence_id` 必须存在于对应证据包；工单建议可以是草稿，也可以在权限和确认门禁通过后提交真实系统。

------

## 五、外部接口确认单

每个 Real Adapter 开发前，必须确认以下内容：

| 项目         | 说明                                |
| ------------ | ----------------------------------- |
| 接口负责人   | 业务或平台联系人                    |
| 接口地址     | 测试与生产环境地址                  |
| 鉴权方式     | token、AK/SK、内网白名单等          |
| 请求参数     | 必填、选填、枚举                    |
| 响应字段     | 字段含义、单位、类型                |
| 错误码       | 上游错误码与本系统错误码映射        |
| 超时时间     | 默认建议 3 到 10 秒                 |
| QPS 限制     | 是否需要限流                        |
| 数据延迟     | 实时、分钟级、小时级                |
| 是否支持批量 | 设备、告警、时序是否可批量查        |
| 样例数据     | 至少 3 条成功、1 条失败、1 条空结果 |
| 联调窗口     | 对接时间与责任人                    |
| 生产发布流程 | 是否需要审批、白名单、灰度          |

以上字段是阶段 0 和 D3 的真实接入门禁。当前文档中的 `SITE-01`、`ems`、`mock` 等均为结构示例；实际场站、接口负责人、地址、鉴权和联调窗口必须由业务方补充，不以示例值代替。

------

## 六、前端联调补充

前端不应只等待最终结果，建议按状态展示诊断过程。

### 6.1 诊断状态展示

| 状态              | 前端展示                         |
| ----------------- | -------------------------------- |
| `INIT`            | 正在初始化诊断                   |
| `PLAN_READY`      | 已生成诊断计划                   |
| `DATA_FETCHING`   | 正在查询设备、告警、时序和知识库 |
| `EVIDENCE_READY`  | 已整理证据                       |
| `NEED_USER_INPUT` | 需要用户补充现场信息             |
| `DRAFT_READY`     | 已生成候选结论                   |
| `REVIEWING`       | 正在进行规则校验                 |
| `COMPLETED`       | 诊断完成                         |
| `FAILED`          | 诊断失败，可重试或转人工         |

### 6.2 SSE 事件格式

```json
{
  "event": "retrieval_completed",
  "session_id": "diag_s_001",
  "trace_id": "trace_abc",
  "timestamp": "2026-06-23T10:31:00+08:00",
  "payload": {
    "message": "已完成手册与历史工单检索",
    "progress": 60,
    "data": {
      "manual_count": 5,
      "ticket_count": 3
    }
  }
}
```

前端诊断结果页至少展示：

1. 结论摘要；
2. 候选根因排序；
3. 支持证据；
4. 不确定性或反证；
5. 排查步骤；
6. 安全提示；
7. 人工补充问题；
8. 工具调用摘要；
9. 继续追问入口；
10. 创建或升级工单入口。

### 6.3 API 与传输兼容

会话消息同时保留两种入口：

1. `POST /api/v1/diagnosis/chat`：从请求体读取 `session_id` 的便捷入口；
2. `POST /api/v1/diagnosis/sessions/{session_id}/messages`：REST 风格标准入口。

创建会话、查询结果和人工确认继续使用详细设计中的既有接口。诊断进度默认通过 SSE 输出；需要双向实时控制时可使用 WebSocket。SSE 与 WebSocket 复用 6.2 的事件 payload，不允许形成两套状态语义。

------

## 七、建议补充的数据表

详细设计中已有会话表、步骤日志表和案例表。为了研发落地，建议再补充以下表。

### 7.1 `diagnosis_evidence_ref`

用于保存一次诊断中引用过的证据。

| 字段          | 说明                                    |
| ------------- | --------------------------------------- |
| `id`          | 主键                                    |
| `session_id`  | 会话 ID                                 |
| `evidence_id` | 证据 ID                                 |
| `source_type` | manual/ticket/timeseries/graph/metadata |
| `source_id`   | 原始来源 ID                             |
| `quote_text`  | 引用摘要                                |
| `score`       | 证据分数                                |
| `created_at`  | 创建时间                                |

### 7.2 `tool_call_log`

用于追踪工具调用。

| 字段                | 说明              |
| ------------------- | ----------------- |
| `id`                | 主键              |
| `session_id`        | 会话 ID           |
| `tool_name`         | 工具名            |
| `provider_type`     | mock/real         |
| `request_snapshot`  | 请求快照          |
| `response_snapshot` | 响应快照          |
| `status`            | OK/FAILED/TIMEOUT |
| `latency_ms`        | 调用耗时          |
| `trace_id`          | 链路 ID           |
| `created_at`        | 创建时间          |

### 7.3 `config_dictionary`

用于维护设备、告警、部件、指标等字典。

| 字段            | 说明                          |
| --------------- | ----------------------------- |
| `dict_type`     | device/alarm/component/metric |
| `raw_name`      | 原始名称                      |
| `standard_name` | 标准名称                      |
| `aliases`       | 别名                          |
| `enabled`       | 是否启用                      |
| `updated_at`    | 更新时间                      |

------

## 八、错误码与幂等要求

### 8.1 核心错误码

| 错误码                     | 说明         | 前端处理         |
| -------------------------- | ------------ | ---------------- |
| `DEVICE_NOT_FOUND`         | 设备不存在   | 提示检查设备 ID  |
| `ALARM_NOT_FOUND`          | 告警不存在   | 提示检查告警 ID  |
| `TIMESERIES_UNAVAILABLE`   | 时序不可用   | 展示降级提示     |
| `RETRIEVAL_FAILED`         | 检索失败     | 提示可重试       |
| `LLM_UNAVAILABLE`          | 模型不可用   | 使用规则模板降级 |
| `NEED_MANUAL_CONFIRMATION` | 需要人工确认 | 展示补充问题     |
| `UNSUPPORTED_OPERATION`    | 一期不支持   | 明确边界提示     |

### 8.2 幂等要求

以下操作必须支持幂等：

1. 创建诊断会话；
2. 告警触发诊断；
3. 提交人工确认；
4. 创建案例草稿；
5. 审核通过入库；
6. 工单创建或更新。

建议通过 `X-Idempotency-Key` 控制重复提交，避免重复告警或用户重复点击造成多次创建。

------

## 九、P0 / P1 研发任务建议

P0/P1 是一期内部优先级，不是实施阶段：P0 构成首次可验收闭环，P1 在不改变 P0 契约的前提下增强管理、图谱、工单、看板和灰度能力；阶段 7 可按试点需要交付部分 P1。

### P0：一期必须完成

| 编号  | 任务                 | 输出                                   |
| ----- | -------------------- | -------------------------------------- |
| P0-01 | 项目工程骨架         | 服务目录、配置、日志、健康检查         |
| P0-02 | 统一 Schema          | 请求上下文、工具结果、证据包、诊断结果 |
| P0-03 | 诊断会话 API         | 创建会话、发送消息、查询状态           |
| P0-04 | LangGraph 主状态机   | INIT 到 COMPLETED/FAILED               |
| P0-05 | 设备画像工具         | `get_device_profile`                   |
| P0-06 | 告警详情工具         | `get_alarm_detail`                     |
| P0-07 | 时序查询工具         | `query_timeseries_window`              |
| P0-08 | 手册检索工具         | `search_manual_chunks`                 |
| P0-09 | 相似工单检索工具     | `search_similar_tickets`               |
| P0-10 | 证据包与引用         | evidence package                       |
| P0-11 | 候选根因生成         | reason_generator                       |
| P0-12 | 结果生成与 Guardrail | response_generator + rule_checker      |
| P0-13 | Redis 会话记忆       | 会话恢复、追问上下文                   |
| P0-14 | Web 诊断页           | 对话、进度、结果、证据                 |
| P0-15 | 人工补充提问         | NEED_USER_INPUT 分支                   |
| P0-16 | 案例草稿与审核       | DRAFT -> APPROVED                      |
| P0-17 | 工具调用日志         | tool_call_log                          |
| P0-18 | 基础回归测试         | 典型告警用例、引用覆盖率、工具成功率   |

### P1：一期增强或试点后优化

| 编号  | 任务             | 输出                         |
| ----- | ---------------- | ---------------------------- |
| P1-01 | 知识库上传后台   | 文档上传、解析、索引状态     |
| P1-02 | 字典管理后台     | 设备、告警、部件、指标维护   |
| P1-03 | 模板管理后台     | 故障模板、Prompt 模板        |
| P1-04 | 诊断历史页       | 查询历史会话                 |
| P1-05 | 用户反馈闭环     | helpful / not helpful        |
| P1-06 | 图谱关系检索增强 | Neo4j 补充召回               |
| P1-07 | 工单创建建议     | 创建工单草稿                 |
| P1-08 | 监控看板         | 节点耗时、工具成功率、失败率 |
| P1-09 | 灰度发布能力     | 按用户、场站、设备类型启用   |

能力按成熟度合并解释如下：

| 能力 | P0 基础形态 | P1 增强形态 |
|------|-------------|-------------|
| 图谱 | Provider 接口、Mock 关系和降级路径 | Neo4j 真实关系、抽取与质量治理 |
| 工单 | 创建建议、待确认草稿 | 受控写入真实工单系统 |
| 知识库 | 解析、切分、索引、查询流水线 | 上传、版本、字典和模板管理后台 |
| 可观测 | trace、日志、指标和错误追踪 | 监控看板与运营分析 |
| 评估 | 基础回归集与上线门禁 | 独立服务、版本对比和持续评估 |

------

## 十、开发完成定义

一个开发任务只有同时满足以下条件，才视为完成：

1. 代码已合并到主干或指定发布分支；
2. 单元测试通过；
3. 接口联调通过；
4. 关键逻辑有日志和 trace；
5. 异常路径有错误码；
6. 配置项不写死；
7. 接口文档已更新；
8. 涉及数据表的任务已提交 migration；
9. 涉及 Prompt 的任务已标明版本；
10. 经过代码评审。

联调完成需额外满足：

1. Mock 数据能跑通主链路；
2. 至少 3 类典型告警可完成诊断；
3. 前端能看到中间状态和最终结果；
4. 证据引用可点击或可追溯；
5. 工具失败时能展示降级提示；
6. 日志中能通过 trace_id 串起完整链路。

------

## 十一、上线前最小验收清单

| 验收项               | 是否必须 |
| -------------------- | -------- |
| Web 可发起诊断       | 是       |
| 告警可触发诊断       | 是       |
| 能查询设备画像       | 是       |
| 能查询时序数据       | 是       |
| 能检索手册           | 是       |
| 能检索历史工单       | 是       |
| 能输出候选根因       | 是       |
| 能输出证据引用       | 是       |
| 能输出排查步骤       | 是       |
| 能识别证据不足       | 是       |
| 能进行人工补充提问   | 是       |
| 能生成案例草稿       | 是       |
| 能审核案例入库       | 是       |
| 审核案例能被召回     | 是       |
| 高风险建议需人工确认 | 是       |
| 降级链路演练通过     | 是       |
| 线上日志 trace 完整  | 是       |

非功能试点门槛建议：

1. 完整诊断建议生成时间：1 到 3 分钟；
2. 工具调用成功率：不低于 95%；
3. 会话失败率：不高于 5%；
4. 关键结论引用覆盖率：不低于 80%；
5. 无引用强结论：0；
6. 高风险建议人工确认覆盖率：100%。

同时保留实施计划和详细设计中的 Top-1/Top-3 根因命中率、Human Escalation Precision、人工介入率和相似案例命中率。未给出数字的指标不在本文擅自设值，由阶段 0 明确试点阈值；阶段 6 统一出具全量指标报告。

------

## 十二、建议研发推进顺序

建议按以下顺序推进：

1. 统一 Schema、项目骨架和诊断会话 API；
2. 设备、告警、时序三个结构化工具；
3. 手册和工单基础检索；
4. 查询重写、混合召回和重排；
5. LangGraph 主状态机；
6. 前端诊断会话页和 SSE 进度展示；
7. 证据引用、候选根因和 Guardrail；
8. 案例草稿、审核、入库和回归评估；
9. 逐步将 Mock Provider 替换为 Real Adapter。

与全局阶段的关系为：阶段 1 建立公共骨架并启动 D1，阶段 2/3 按 Provider 滚动完成 D1-D3，阶段 4 保留完整 Mock 回归并联调已就绪 Real Adapter，阶段 5 完成记忆、审核和写入类 Provider，阶段 6 做稳定性门禁，阶段 7 灰度启用并继续交付增强项。

一期最小可演示闭环：

```text
告警/用户输入
  -> 创建诊断会话
  -> 查询设备与告警信息
  -> 查询近 30 分钟时序摘要
  -> 检索手册与相似工单
  -> 生成证据包
  -> 输出候选根因与排查步骤
  -> 用户补充现场信息
  -> 重新生成结论
  -> reviewer 审核案例
  -> 审核通过后入库
  -> 后续诊断可召回该案例
```

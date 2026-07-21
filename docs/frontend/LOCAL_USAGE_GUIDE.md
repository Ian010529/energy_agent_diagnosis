# 能源诊断 Agent 本地启动与使用教程

本文面向 Phase 7 本地试用环境。所有命令默认在仓库根目录执行：

```bash
cd /Users/chl/Desktop/my_project/energy_agent_diagnosis_reset
```

## 1. 当前访问地址

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| 前端 | http://localhost:3000 | 日常使用入口 |
| 后端 | http://localhost:8000 | FastAPI 服务 |
| 后端存活检查 | http://localhost:8000/health/live | 进程是否存活 |
| 前端就绪检查 | http://localhost:3000/api/health/ready | 依赖及能力状态 |
| RabbitMQ 管理页 | http://localhost:15672 | 本地队列观察 |
| Neo4j Browser | http://localhost:7474 | 本地图谱观察 |
| MinIO Console | http://localhost:9001 | 本地对象存储观察 |

管理服务的本地开发账号以 `.env` 和 `compose.yaml` 为准，不要把账号、API Key 或 `.env` 发到聊天、截图或 Git 仓库。

## 2. 第一次启动

确认 Docker Desktop 已启动。本机是 8 GB 内存的 M1 MacBook Air，Docker Desktop 保持 `4 GB Memory + 1 GB Swap`；不要把 Docker 内存设为 8 GB，否则会挤压 macOS、浏览器和本地热更新进程。日常开发只启动当前功能需要的容器，不同时做镜像构建、大批量索引和长时间评估。

```bash
docker compose config --quiet
docker compose --profile phase7 up -d --build --wait
make migrate
```

如果 Docker Hub 临时返回 EOF，而镜像已经在本地，可改用：

```bash
docker compose --profile phase7 up -d --build --wait --pull never
make migrate
```

启动成功后检查：

```bash
docker compose ps
curl -fsS http://localhost:8000/health/live | jq
curl -fsS http://localhost:3000/api/health/ready | jq
curl -fsS http://localhost:3000/api/backend/capabilities | jq
```

正常情况下，所有容器都应为 `Up` 或 `healthy`，capabilities 应显示 `pilot_medium_v1`、版本 `1.3.0` 和 5 个诊断模板。

## 3. 日常启动、停止与日志

镜像已经构建后，日常启动不需要再次 `--build`：

```bash
docker compose --profile phase7 up -d --wait --pull never
```

查看状态：

```bash
docker compose ps
docker stats --no-stream
```

查看应用日志：

```bash
docker compose logs -f --tail=200 backend frontend index-worker
```

停止但保留数据：

```bash
docker compose --profile phase7 stop
```

删除容器但保留命名卷数据：

```bash
docker compose --profile phase7 down
```

不要随意执行 `docker compose down -v`；`-v` 会删除 MySQL、InfluxDB、Milvus、MinIO、Neo4j 等本地数据卷。

## 4. 角色说明

本地环境支持四种角色。角色切换器可在“系统”“人工审核”和“案例详情”等页面看到。

- `viewer`：只读查看。
- `operator`：创建诊断线程、发送消息、回答澄清问题。
- `reviewer`：执行人工诊断审核。
- `admin`：审批、停用、修订、重新索引案例。

日常诊断先使用 `operator`。只有进入审核和案例管理步骤时，再切换到相应角色。本地切换功能在生产环境不会开放。

## 5. 用告警创建诊断

1. 浏览器打开 http://localhost:3000。
2. 点击左侧“诊断”。
3. 点击“新建诊断”。
4. 选择“告警诊断”。
5. 可先选择场站，再选择设备和告警。
6. 优先选择页面显示“已匹配模板”的告警。
7. 点击“创建诊断线程”。
8. 在线程底部的“诊断消息”输入框发送：

```text
请诊断当前告警。先判断是否存在立即停机或人身安全风险，再按证据强弱列出最可能的 3 个原因和排查顺序。所有结论必须引用当前线程中的证据；不要执行任何设备动作。
```

发送后，线程会按真实 SSE 事件显示意图识别、数据读取、检索、人工补充、草稿和完成状态。

混合检索需要访问 embedding、reranker 和模型服务，本机一次通常约 10–60 秒。发送后底部会显示已等待秒数；不要重复点击发送。若超过 60 秒没有新进度，可先点击线程右上角刷新，页面会从后端 session 和 timeline 恢复，而不会伪造完成状态。

## 6. 如何回答人工澄清

Agent 进入“需要现场补充”时，只填写真实观察或真实测量结果。不要为了让流程继续而编造数据。

推荐回答结构：

```text
检查时间：2026-07-21 10:30
检查人：现场运维 A
设备状态：运行/停机/检修
观察结果：……
实测值及单位：……
对照测点或独立仪表：……
已采取措施：仅检查，未执行控制动作
异常安全迹象：无冒烟、无焦味、无异常放电；如有请如实说明
```

温度告警示例（数值必须替换为真实值）：

```text
现场红外测温 42.1°C，冗余测点 41.8°C，告警测点显示 65.4°C；环境温度 31°C。端子和线束外观正常，无焦味、无冒烟。目前只做了测量，没有复位、启停或参数修改。
```

风扇告警示例：

```text
现场检查发现 2 号风扇有异响，转速约 820 rpm；同组正常风扇约 1450 rpm。进风口存在明显积尘，供电和控制线束未见松动。未执行清理、复位或启停操作。
```

通信告警示例：

```text
设备本地屏正常，辅助电源正常；交换机端口灯间歇闪烁。最近 10 分钟出现丢包，现场尚未插拔网线、重启设备或修改网络配置。
```

## 7. 推荐的追问方式

诊断完成后可以继续发送：

```text
请把每个候选根因分别对应到 Evidence 引用，并说明支持证据、冲突证据和排除条件。
```

```text
请只给出安全的人工检查步骤，按“先无侵入、后停机检查”的顺序排列，并标出哪些步骤需要审批或停电确认。
```

```text
当前还缺哪些信息？请最多提出 3 个最能区分候选根因的问题，不要重复已经获取的数据。
```

```text
请解释为什么第一候选原因排在第二候选原因之前，并列出对应的时序指标、工单、手册或历史案例证据。
```

```text
请生成一份交接班摘要：告警现象、当前风险、已核验事实、未确认事项、下一步人工检查和禁止操作。
```

## 8. 自由问诊

在“新建诊断”中选择“自由问诊”，输入设备现象。例如：

```text
设备 pilot_medium_v1-SITE-PILOT-01-PCS-0001，告警 ALARM-pilot_medium_v1-29127340057e08cdc97e。请先判断是否存在立即停机或人身安全风险，再按证据强弱列出最可能的 3 个原因和排查顺序；不要执行任何设备动作。
```

提交后会立即进入诊断线程，并通过 SSE 持续显示节点进度，不需要停留在“正在创建”页面等待整次诊断完成。消息中包含格式有效的设备编号和告警编号时，系统会先解析编号，再由真实数据工具核验并加载对应时序、告警和案例证据；编号不会被当作已核验事实直接采信。

如果没有提供可核验编号，系统只会要求补充设备编号和告警编号，不会猜测真实实体。也可以直接使用“告警诊断”入口，从现有告警列表选择目标。

## 9. 查看 Evidence、时序、工具和 Trace

在线程右侧“检查器”中：

- `Evidence`：查看来源、引用、摘要、验证状态和各维度分数。
- `Time Series`：选择时间范围和指标，查看告警时间参考线。
- `Tools`：查看工具名称、状态、是否获得可用数据及结果引用。
- `Trace`：查看 session/run/trace、模板版本、降级组件，并跳转 LangFuse。

手机或平板上，检查器会作为 Drawer 打开。刷新页面后，线程、时间线和最终结果会从后端恢复。

## 10. 人工审核和案例闭环

诊断完成后：

1. 将本地角色切换为 `reviewer`。
2. 打开“审核”。
3. 选择待审核诊断。
4. 选择 `confirmed`、`rejected` 或 `needs_more_info`。
5. `confirmed` 时必须选择候选根因、逐行填写处理步骤，并保留 Evidence refs。
6. 点击“提交审核”。

确认后会创建案例。随后：

1. 打开“案例”并进入案例详情。
2. 将角色切换为 `admin`。
3. 对草稿执行“提交审核”。
4. 对待审核案例填写操作意见并“审批通过”或“拒绝”。
5. 已批准案例可停用、创建修订；仅当索引状态为失败或降级时才显示“重新索引”。

前端不会提供设备启停、复位、参数修改或其他实际执行按钮。

## 11. 常见问题

### 页面打不开

```bash
docker compose ps
curl -i http://localhost:3000
docker compose logs --tail=200 frontend backend
```

### 后端存活但诊断不可用

```bash
curl -fsS http://localhost:3000/api/health/ready | jq
docker compose logs --tail=300 backend index-worker
```

重点检查 MySQL、Redis、InfluxDB、MinIO、Milvus、RabbitMQ 是否 healthy。

### 已有会话的 Time Series 显示为空

检查器现在会优先使用当前 session 的时间窗口，其次使用告警触发时间，并显示窗口来源、每个指标点数和明确空数据原因。空图不代表接口卡住，也不能把别的日期数据冒充为当前告警证据。

当前不可变 `pilot_medium_v1 1.3.0` 数据中，部分告警时间与已加载时序窗口并不重叠；这些历史会话在告警窗口返回 0 点是数据事实。可以在 Time Series 顶部手动选择有数据的时间范围验证图表，但该范围的数据只有在与告警上下文一致时才能作为诊断证据。不得为了让图表有线而修改数据集、模板或时间戳。

### Docker 容器出现 137 或自动退出

这是容器被系统终止的表现之一，但不能仅凭退出码认定是内存不足。先查看容器状态和日志：

```bash
docker compose ps -a
docker compose logs --tail=200 <服务名>
docker stats --no-stream
```

在这台 8 GB Mac 上保持 Docker `4 GB Memory + 1 GB Swap`，并停止当前诊断不需要的增强服务：

```bash
docker compose stop index-worker neo4j rabbitmq
```

### indexing 显示 degraded

先确认 `index-worker` healthy 且队列有消费者：

```bash
docker compose ps index-worker rabbitmq milvus neo4j
docker compose exec -T rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
```

历史上失败或降级过的索引任务会保留用于审计，即使后续 reindex 已成功，系统状态仍可能展示历史降级。以具体案例的最新 `index_status` 和最新 reindex 任务为准。

### 修改代码后如何热更新

前后端日常开发不需要重建镜像。保留数据依赖容器，应用在宿主机以热更新模式运行：

```bash
# 终端 1：按当前功能启动必要依赖
make up-phase7-dev-deps

# 终端 2：后端热更新
uv sync
make backend-dev

# 终端 3：前端热更新
make frontend-install
make frontend-dev
```

`make frontend-dev` 会只在 Next.js 服务端读取根目录 `.env`，把现有内部 API Key 映射给 BFF；密钥不会进入浏览器 bundle。宿主机 `.env` 的依赖地址应使用 `127.0.0.1` 或 `localhost`，端口沿用 `compose.yaml` 暴露的端口。不要把改过的密钥提交到 Git。

只有修改 `Dockerfile`、系统包或依赖锁文件后才需要重建对应镜像，并禁止带起无关依赖：

```bash
docker compose build backend
docker compose up -d --no-deps backend

docker compose build frontend
docker compose up -d --no-deps frontend
make migrate
```

## 12. 安全提醒

- 不要把 `.env`、API Key、内部请求头复制到浏览器控制台或聊天中。
- Agent 的推荐动作默认均为“未执行”，必须经过人工审核和现场安全流程。
- 遇到冒烟、异味、放电、过热或人身风险时，优先执行现场既有应急制度，不等待 Agent 输出。
- Agent 的诊断是证据辅助决策，不替代持证人员、设备厂家规程和审批流程。

# 模块边界说明

## 1. 权威来源

本文是开发期边界说明，服从用户最新指令、`docs/immutable/能源设备运维诊断Agent_详细设计.md`、根目录 `AGENTS.md` 和 `docs/IMPLEMENTATION_STATUS.yaml`，不替代或修改不可变详细设计。

## 2. 当前物理部署

系统保持模块化单体：一个 FastAPI 后端进程、一个独立 index-worker 和 Next.js BFF。此次加固不拆微服务，不改变 Docker 拓扑。

## 3. 逻辑模块

详细设计的交互层、接入层、Agent 编排层、能力层、数据层继续成立。代码中的主要逻辑模块为 `api`、`agent`、`retrieval`、`tools`、`memory`、`cases`、`catalog`、`timeline`、`evidence`、`indexing`、`graph`、`templates`、`contracts`、`providers`、`persistence` 和 `bootstrap`。

## 4. 模块职责

- `api`：HTTP、鉴权、限流接入、SSE 和 DTO 绑定。
- `agent`：会话应用服务、LangGraph 编排、节点运行和诊断状态转换。
- `retrieval`：混合召回、查询改写、合并、重排和证据评分。
- `tools`：稳定 Tool Schema、注册、执行策略和工具适配。
- `memory`：会话短期记忆。
- `cases`：人工确认、案例状态机和案例索引协调。
- `catalog`：设备、告警、场站查询及模板支持映射。
- `timeline`：业务时间线的统一写入和查询。
- `evidence`：证据归属、来源路由和时序明细。
- `indexing`：索引事件消费、投影、重试和幂等处理。
- `graph`：Neo4j 可选增强能力的非阻塞门面。
- `templates`：五个诊断模板、路由和规则的唯一权威实现。
- `contracts`：跨模块且与框架无关的稳定数据契约。
- `providers` / `persistence`：外部 SDK、数据库模型和 Port 实现。
- `bootstrap`：唯一 Web 运行时 Composition Root。

## 5. 允许依赖

`frontend -> HTTP/OpenAPI -> api -> application services/contracts`；应用服务依赖领域 Contract 和使用方定义的窄 Port；`providers`、`persistence` 实现 Port；`bootstrap` 可以导入全部运行时模块并完成具体装配。CLI、evaluation、tests 可以拥有受控的独立装配。

## 6. 禁止依赖

禁止 `core` 导入 API、Provider、Persistence 或业务服务；禁止 `contracts` 导入 `agent`；禁止应用 Service 导入 FastAPI/Starlette、SQLAlchemy 或 ORM Model；禁止 API Router 导入 ORM Model、具体 Provider 或 Repository SQL；禁止 Retrieval、Tool、Case 面向具体 Provider；禁止外部访问 `GraphService` 的底层 Provider；禁止非 Agent 模块导入 `agent.templates`；禁止运行时模块导入 `evaluation`；禁止 Client Component 读取内部 API Key。

## 7. Composition Root

`energy_agent.bootstrap` 创建带类型的 `ApplicationContainer`，装配 Provider、Repository、Service、Tool Registry、Session Store、熔断器和生命周期资源。FastAPI 只保存 `app.state.container`；业务模块不得把它当作 Service Locator 使用，Router 通过 `api.dependencies` 获取类型化 Service。

## 8. Port 与 Adapter

Port 使用 `typing.Protocol` 并放在使用方模块，只覆盖真实可替换接缝：外部业务数据源、时序、检索候选、Embedding、向量、Reranker、Graph、索引发布、存储 Repository、模型和测试替换依赖。具体实现不必继承 Protocol。模块内部纯函数和无替换需求的协作不创建接口。

## 9. 允许的例外

- `bootstrap/**`：Web 运行时具体装配。
- `indexing/worker.py`、`indexing/cli.py`、`retrieval/ingestion/cli.py`、`retrieval/smoke.py`：独立进程或 CLI Composition Root。
- `evaluation/**`：离线评估独立装配，不得被运行时模块导入。
- `tests/**`：测试装配和兼容路径验证。

例外必须在 `scripts/check_module_boundaries.py` 中逐文件记录原因，不允许目录通配豁免。

## 10. 后续拆服务时的边界

若后续按详细设计拆分，`agent` 只通过 Tool/Retrieval/Memory Contract 调用能力层；`retrieval`、`tools`、`memory` 保留独立接口；Case 主记录、索引发布和 Graph 投影分别通过窄 Port 连接。此次不引入内部事件总线或分布式事务。

## 11. 当前仍后置的生产能力

多副本、durable accept、lease/fencing、worker crash recovery、大规模并发、chaos、性能压测、Helm、灾备、独立 trace exporter、trace outbox、精确成本结算和完整生产监控平台继续后置但未删除。

## 12. 模块定向检查

普通修改使用 `make module-check MODULE=<模块名>`。可用模块通过 `make module-list` 查看。
每个模块检查只执行全局静态边界扫描、该模块的 Ruff/Mypy，以及该模块的单元或契约测试；
不会递归调用任何 `phase*-check`、`auth-check`、评估集或完整 Gate。

若修改具体基础设施 Adapter，再单独运行该 Adapter 对应的 integration 或 smoke 目标，并只启动它所需依赖。
完整纵向 Gate 只用于纵向切片验收、试点验收、跨模块 Contract 变更，或 Composition Root/公共基础设施发生影响面不确定的变更。

## 问题冻结与当前违规基线

问题：当前系统已经具备模块化目录，但应用层仍依赖 FastAPI Request、`app.state` Service Locator、具体 Provider、SQLAlchemy Model 和底层 Provider 属性。

违反的详细设计要求：逻辑组件职责必须独立保留；部署形态可以合并，但逻辑服务不能互相穿透。

根因：纵向切片快速开发过程中，依赖装配、持久化协调、工作流运行和 API 接入逐步集中在 lifecycle、DiagnosisService、CaseService 和 EvidenceService。

本次只修改：依赖装配、应用服务拆分、Port、Repository、模板归属、Graph 封装、Tool 元数据和模块边界测试。

本次不修改：业务规则、模板内容、RAG 算法、评分、Prompt、API Contract、SSE Contract、数据集、数据库业务结构、诊断结果和前端视觉。

加固前已确认的违规包括：`core/lifecycle.py` 承担装配、平行 `app.state.*`、应用 Service 的 `Request/from_request()`、Evidence 直连 ORM、Retrieval/Tool/Case 具体 Provider 类型、Graph `.provider` 穿透、模板由 Agent 所有，以及缺少自动架构 Gate。

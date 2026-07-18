# AGENTS.md

## 项目目标

- 当前按单人开发推进，目标是快速实现符合不可变详细设计的一期后端。
- 开发顺序采用纵向主链路优先，初始物理形态采用模块化单体。
- gateway、agent、retrieval、tool、memory 的逻辑边界必须保留，便于后续拆分。

## 权威顺序

冲突依次按以下来源裁决：

1. 用户最新明确指令；
2. `docs/immutable/能源设备运维诊断Agent_详细设计.md`；
3. 根目录 `AGENTS.md`；
4. `docs/IMPLEMENTATION_STATUS.yaml`；
5. 当前阶段 Prompt；
6. 测试、代码注释和其他文档。

不可修改、重命名、重排或重新格式化不可变详细设计。

## 不可削减的核心能力

一期必须保留：LangGraph 显式工作流、Tool Schema、混合 RAG、证据引用、Guardrail、
人工补充、人工审核、会话记忆、案例状态机、SSE、LangFuse、结构化日志、审计，以及超时、有限重试和降级。

## 当前允许简化的工程形态

- gateway、agent、retrieval、tool、memory 可在一个 FastAPI 应用中运行。
- LangGraph 第一版可在应用进程内同步或异步执行。
- retrieval、tool、memory 必须保持独立代码和接口边界。
- Neo4j 是增强能力，失败不得阻塞诊断主链路。
- RabbitMQ 可在异步索引和案例回写阶段接入。
- 关键词检索可先使用兼容的轻量实现。
- Docker 只启动当前目标所需依赖。

## deferred_not_deleted

以下能力后置但未删除：多副本、durable accept、lease、fencing、worker crash recovery、大规模并发控制、
chaos、性能压测、Helm、灾备、独立 trace exporter、trace outbox、精确成本结算系统、完整生产监控平台。

## 上下文恢复

新任务、上下文压缩、会话恢复或中断继续时，优先只读取：

1. `AGENTS.md`
2. `docs/IMPLEMENTATION_STATUS.yaml`
3. 当前阶段 Prompt
4. 当前阶段引用的详细设计章节
5. 目标代码和对应测试

不要默认重读完整生产硬化规范、全部 Gate 报告或整个仓库。对话记忆、旧 TODO、历史 Gate 和测试名称不是当前开发状态的权威来源。

## Bug 修复边界

修复前先写明：

```text
问题：
违反的详细设计要求：
根因：
本次只修改：
```

根因未明确前不得大范围修改；不改无关模块，不顺便重构，不删除或弱化测试。
只运行目标模块所需测试；仅阶段验收运行完整纵向集成测试。

## Docker、测试与验收

- 纯逻辑、状态机、Prompt、Guardrail、评分修改默认不启动 Docker。
- 修改 MySQL、Redis、InfluxDB、Milvus 等适配器时只启动对应依赖。
- 普通 Bug 修复不默认启动全量容器。
- 完整依赖仅在纵向切片验收或试点验收时启动。
- 容器启动或健康检查成功不等于业务验收通过。

## GitHub 发布边界

- 用户要求推送到 GitHub 时，默认只提交并推送当前任务分支，不创建 Pull Request。
- 只有用户明确要求创建 PR 时，才允许创建 Pull Request。

## LangFuse 边界

LangFuse 是第一条诊断主链路的核心可观测能力。第一版必须追踪 LangGraph 节点、Tool、RAG、LLM、
Guardrail 和最终状态。LangFuse 不可用时不得阻断本地诊断，应降级到结构化日志。独立 exporter、
outbox 和生产级可靠投递后置。不得向 Trace 发送密钥、大段原始工单、完整原始时序或敏感内容。

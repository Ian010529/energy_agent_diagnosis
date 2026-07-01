# 能源设备运维诊断 Agent

本目录当前实现全局阶段 1 到阶段 4：工程底座、数据接入 Mock 基线、RAG 检索链路，以及基于
LangGraph 的 Agent 诊断主链路。可通过 Web API 发起诊断会话、查看进度事件（SSE）、多轮追问
并获取带证据引用的候选根因输出。

## 本地环境

```bash
make venv
make sync
cp .env.example .env
make run
```

所有 Python 命令均通过项目根目录的 `.venv` 执行，版本固定为 Python 3.13.13。`uv run`
会自动选择该环境，不需要向系统 Python 安装依赖。

## 常用命令

```bash
make check          # Ruff、Mypy 和测试
make compose-config # 同时校验 dev 与 full Compose 拓扑
make dev-up          # 启动应用及四个核心依赖
make dev-down        # 停止最小开发拓扑并保留命名卷
make infra-up       # 启动完整阶段 1 基础设施
make smoke          # 验证应用和依赖就绪状态
make infra-down     # 停止基础设施
```

## 阶段边界

当前可执行能力包含阶段 1 工程底座、阶段 2 数据接入 Mock 基线、阶段 3 RAG 检索链路（查询
重写、混合召回、重排、证据归并），以及阶段 4 Agent 诊断主链路（LangGraph 工作流、工具编
排、多轮会话、补充提问、Web API 联调）。

当前实现不包含 Redis 会话记忆、案例审核闭环、Web 前端或真实外部系统 Adapter。

## 本地基础设施边界

`dev` profile 包含应用、MySQL、Redis、MinIO 和 RabbitMQ；`full` profile 额外包含 Milvus、
Neo4j、InfluxDB 和 OpenSearch。所有宿主端口默认仅绑定 `127.0.0.1`，且示例凭据只适用于
单机开发。完整验收使用：

```bash
make infra-up
make smoke
make infra-down
```

如使用自定义环境文件，可通过 `ENV_FILE=.env make infra-up smoke` 传入；脚本只读取 smoke
专用密钥，不会执行环境文件内容。生产密钥不得写入 README、日志或版本库。

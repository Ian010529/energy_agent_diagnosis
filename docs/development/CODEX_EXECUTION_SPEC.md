# 当前开发执行入口

当前单人开发采用模块化单体和纵向主链路优先的方式。

- 开发治理、权威顺序和任务边界：[`../../AGENTS.md`](../../AGENTS.md)
- 当前阶段、已完成事项和下一任务：[`../IMPLEMENTATION_STATUS.yaml`](../IMPLEMENTATION_STATUS.yaml)
- 后期生产硬化要求：[`PRODUCTION_HARDENING_SPEC.md`](PRODUCTION_HARDENING_SPEC.md)

生产硬化规范保留可靠性、安全、并发、部署和生产验收要求，但不作为当前
普通修改的逐模块阻塞流程。当前阶段不要求严格执行 M0 → M11 串行门禁，也
不默认执行 full、live、chaos 或 performance Gate。

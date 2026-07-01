# 阶段 3 RAG 首版评估报告

## 评估范围

本报告覆盖全局阶段 3 RAG 检索链路，不覆盖 LangGraph 主流程、候选根因生成、Web 联调、案例审核
闭环或真实外部系统 Adapter。

## 评估集

评估集见 [`rag_stage3_eval_set.json`](rag_stage3_eval_set.json)，当前包含 3 类典型告警：

1. PCS 机柜温度持续升高；
2. 逆变器通讯中断；
3. 风机齿轮箱温度偏高。

## 验收口径

1. 每个样例应召回至少一条手册证据和一条相似工单证据；
2. 每条证据必须包含可追溯的 `evidence_id`、`source_type`、`source_id`、引用摘要和分数；
3. 单个非核心来源失败时，检索链路应记录 `degraded_sources`，但不阻断证据包生成；
4. 没有足够强证据时，`need_manual_confirmation` 必须为 `true`。

## 当前实现说明

当前阶段 3 使用 Mock/D2 Provider 完成可回归的 RAG 检索闭环：关键词召回和向量召回路径共用统一
Provider 契约，向量与 reranker 在无真实模型服务时采用确定性 fallback。真实 Milvus、
OpenSearch/Elasticsearch、Neo4j 或工单索引接入仍需外部接口确认单后进入 D3。

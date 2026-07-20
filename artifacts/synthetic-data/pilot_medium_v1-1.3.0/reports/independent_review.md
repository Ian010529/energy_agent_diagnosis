# pilot_medium_v1 1.3.0 独立离线复核

## 结论

`OFFLINE_DATA_READY_REQUIRES_EXTERNAL_RELOAD`

## 时序对齐

- Calibration：77/77，误匹配 0。
- Regression：75/75，误匹配 0。
- Holdout：38/38，误匹配 0。
- 总时序点：1,161,650。

## 手册

- 文档：24；可解析：24；OCR 完成：2。
- Chunk：4,328。
- 规范化精确重复率：0.42%。
- 字符 n-gram 最近邻 >0.95：0.69%。
- BGE-M3 需要在仓库真实 Provider 中重跑。

## 泄漏与图谱

- Static forbidden overlap：0。
- 无效 forbidden decoy：0。
- Holdout 设备工单泄漏：0。
- Gold source mapping errors：0。
- 预计 Neo4j：415 节点 / 1000 关系。

## 外部复核

此压缩包没有伪造新版本的 MySQL、RabbitMQ、Milvus 或 Neo4j 装载结果。必须重新装载 1.3.0 后运行完整 Calibration、Regression 和真实 BGE-M3 检查。

# pilot_medium_v1 1.3.0

修复版中等规模能源诊断数据资产。

## 已修复

- 时序窗口：所有声明时序证据的样本均可查，未声明的样本在对应窗口无数据。
- Influx 数据：1,161,650 个点。
- 手册版本身份：24 个文档使用 24 个独立 doc_id。
- OCR：两份扫描 PDF 已加入可提取文本层。
- 手册 Chunk：4,328。
- 规范化精确重复率：0.42%。
- 字符 n-gram 最近邻 >0.95：0.69%。
- Calibration forbidden ticket：全部替换为独立背景巡检工单。
- Holdout 设备关联工单：0。
- 预计 Neo4j 节点：415；关系：1000。

## 必须重新执行

1. 将 1.3.0 重新装载到 MySQL、MinIO 和 InfluxDB。
2. 通过 RabbitMQ 重建 Milvus 与 Neo4j。
3. 使用真实 BGE-M3 重跑手册相似度。
4. 重新运行完整 Calibration 和 Regression。
5. 再确认 Tool Success、Gold 泄漏和 Holdout Gate。

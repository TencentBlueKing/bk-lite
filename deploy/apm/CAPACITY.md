# APM 数据面容量约束

本文给出生产必须满足的容量**下界与告警门槛**，供运维填入自身容量模型与流水线。
本地 Compose 的 256 MiB Stream 只用于契约测试，禁止直接照搬为生产配置。

| 输入 | 符号 | 单位/来源 |
| --- | --- | --- |
| 峰值 Span 速率 | `peak_spans_per_second` | spans/s，按最高区域峰值及总峰值 |
| 平均传输大小 | `average_bytes_per_span` | OTLP Protobuf bytes/span，含批次摊销 |
| 平均日写入量 | `average_ingest_bytes_per_day` | VT 实际 ingest 指标 |
| 区域断连容忍 | `regional_outage_seconds` | 秒，业务 RTO 输入 |
| 中心消费倍数 | `consumer_headroom` | 峰值生产速率的倍数，建议至少 2 |
| VT 存储放大 | `storage_amplification` | 压测所得，不使用猜测值 |
| 保留期 | `retention_days` | 至少 35 天 |
| 副本数 | `replicas` | NATS/VT 实际部署值 |
| 安全余量 | `headroom` | 默认 1.3 |

计算下界：

```text
peak_ingest_bytes_per_second = peak_spans_per_second × average_bytes_per_span
regional_queue_bytes >= peak_ingest_bytes_per_second × regional_outage_seconds × headroom
jetstream_bytes >= peak_ingest_bytes_per_second × regional_outage_seconds × replicas × headroom
consumer_capacity >= peak_spans_per_second × consumer_headroom
victoria_traces_bytes >= average_ingest_bytes_per_day × retention_days × storage_amplification × replicas × headroom
```

批次必须同时满足 `APM_TRACE_BATCH_MAX_SIZE` 和 8 MiB 单消息上限。区域 file queue、Stream 和 VT
磁盘均需预留文件系统空间；VT 必须配置 `storage.minFreeDiskSpaceBytes`。

## 告警门槛

- 区域队列与 Stream 70% 告警、85% 严重；达到硬上限时记录拒绝/丢弃，禁止自动扩成无界。
- pending 最老消息达到 max age 的 70%/85% 告警；`max-deliver` advisory 必须进入值班渠道。
- 持续 publish 失败、ACK 失败、重投、poison message、VT 写入失败分别告警，不能只看端口存活。
- 中心消费须能在演练中清空一次完整 `regional_outage_seconds` 积压；未达到时增加并发或分片，
  不能通过缩短 ack wait 掩盖。
- VT 磁盘 70%/85%、剩余空间、查询错误率/延迟和实际保留期告警。实际保留期低于 35 天时
  APM 健康必须 degraded，30 天/月历月 SLO 不得标为 available。

调整采样（默认全量）、属性上限、批次、保留期或副本后须重新测量并更新工作表。如何接入运维
监控系统由运维决定，门槛不得低于本文。

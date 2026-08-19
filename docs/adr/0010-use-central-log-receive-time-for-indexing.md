# ADR 0010：日志索引统一使用中心接收时间

Status: accepted

日志来源可能自带带时区、无时区、错误或漂移的时间。让 VictoriaLogs 直接使用来源
`timestamp` 会使同一检索窗口和告警窗口受设备时钟影响，因此日志索引统一采用中心系统
Vector 从 Server NATS 消费到事件的时间。该时间包含 NATS 排队延迟，但它是当前架构在
不扩展 Broker 协议和区域代理的前提下唯一能够集中、稳定生成的服务端时间。

中心归一化把上游顶层 `timestamp` 以移动语义保存为可选的 `collect_timestamp`，随后以
`now()` 重建 `timestamp`；已有 `collect_timestamp` 时保留最早值，以便事件重复经过中心
归一化时不丢失原始采集时间。VictoriaLogs 的 `_time_field` 继续指向 `timestamp`，来源
时间不参与索引。不同名称和嵌套的业务时间字段不自动改名。

Vector NATS source 在 legacy namespace 中会向缺少时间的事件自动注入顶层
`timestamp`，无法再与负载原字段区分。因此中心 NATS source 单独开启
`log_namespace: true`，让 ingest timestamp、source type 和 subject 先进入 Vector
元数据 namespace；归一化仅把 source type 和 subject 恢复为存量兼容字段。

时间契约、日志正文契约、用户提取规则和 VictoriaLogs 适配器由同一个完整配置编译模块
按固定顺序组合并通过一份快照热加载。平台契约使用独立 contract version，完整快照每次发布递增
generation；发布始终重新编译完整快照，不允许功能各自修改已发布 YAML。存量升级和代码
回滚都通过显式完整重新发布命令生效，失败时保留上一份成功快照。

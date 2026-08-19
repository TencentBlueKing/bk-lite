# 日志时间字段统一契约

Status: implemented

## Problem Statement

主动上报日志通常自带顶层 `timestamp`，Vector 的 Syslog source 也会根据报文头生成
`timestamp`。中心 VictoriaLogs sink 直接把该字段指定为 `_time_field`，因此来源设备的
时区、时钟漂移、格式错误以及区域采集时间都会改变日志的检索窗口、告警窗口和默认排序。

## Solution

日志服务端时间与日志采集时间分离：

- `timestamp` 是中心系统 Vector 从 Server NATS 消费到事件的时间，由中心
  `normalize_event` 统一以 `now()` 生成；VictoriaLogs 继续使用
  `_time_field=timestamp`，因此查询结果 `_time` 只表达日志服务端时间。
- 输入事件存在顶层 `timestamp` 且尚无 `collect_timestamp` 时，以移动语义把原值保存为
  `collect_timestamp`；不解析、不校正时区、不要求合法日期格式。
- 已有 `collect_timestamp` 的事件视为已经归一化过，保留最早采集时间并丢弃输入
  `timestamp`，随后重新生成本次中心接收时间。
- 输入没有顶层 `timestamp` 时不制造 `collect_timestamp`。`@timestamp`、
  `kafka.log.timestamp` 等嵌套或不同名称的业务字段保持原样。
- 中心 NATS source 显式使用 `log_namespace: true`，使 Vector 自动生成的
  ingest timestamp 留在元数据 namespace，不与上报负载的顶层 `timestamp`
  混淆。归一化显式恢复兼容字段 `source_type` 和 `subject`，但不持久化
  namespace 中的 ingest timestamp。

中心系统 Vector 的固定拓扑保持为：

`Server NATS → normalize_event → log_extractors → prepare_victoria_logs → VictoriaLogs`

`normalize_event` 是平台固定契约模块，对外仍只有一个 transform；其内部按固定顺序组合
互不覆盖字段的时间契约和正文契约。`log_extractors` 只能修改普通业务字段，
`timestamp`、`collect_timestamp`、正文历史别名和其他系统字段均受保护。
`prepare_victoria_logs` 仍只处理 `message → _msg`，不得修改时间字段。

## Complete Snapshot and Contract Version

系统 Vector 每次只热加载一份完整 YAML，不存在时间戳、正文或提取器各自独立的配置。
每次 generation 发布都从当前代码中的平台固定契约、数据库中全部有效提取规则和
VictoriaLogs 适配器重新编译完整快照；禁止在已发布 YAML 上做局部补丁。

完整 YAML 首行包含 `bk-lite-system-vector-contract-version` 注释，配置 OpenAPI 同时返回
`X-Config-Contract-Version`。generation 表示完整快照的发布次序，contract version 表示平台固定
契约的语义版本，两者不能互相替代。存量部署通过显式命令
`python manage.py republish_system_vector_config` 同步生成当前完整快照；该命令不进入
`batch_init` 或服务启动钩子。

## Compatibility and Rollback

- 区域 fusion-collector、Syslog 接收 Vector、Kubernetes Vector、Beat 与 SNMP 模板无需
  为本契约改变运行逻辑；新中心同时兼容带或不带 `timestamp` 的生产者。
- 历史 VictoriaLogs 数据不回填，上线前日志的 `_time` 仍保留旧语义。
- 配置重新发布失败时保留最后成功快照，不阻断 Server 启动。
- 回滚 Server 代码后必须用目标版本的编译器再次发布完整配置，使系统 Vector 热加载旧
  平台契约。目标版本有管理命令时使用管理命令；更旧版本则由受控运维任务调用其已有的
  `mark_dirty()` 异步发布入口。只回滚镜像不会替换数据库中的新快照。

## Testing Decisions

- 使用 Vector 0.48 真实运行 Syslog 带时区时间、主动上报时间、缺失时间、非法时间、
  已有 `collect_timestamp` 和 `@timestamp` 场景。
- 完整配置测试固定 NATS source 的 `log_namespace: true`；本地真实
  NATS → Vector 0.48 → VictoriaLogs 验证缺失上游时间时不会误生成
  `collect_timestamp`。
- Python 预览与 Vector 运行共享动态根合并用例，证明提取器不能覆盖两个系统时间字段。
- 静态枚举全部 18 种内置采集类型，声明 `timestamp` 与 `collect_timestamp`。
- 配置编译测试验证完整快照包含平台契约版本；OpenAPI 测试验证版本响应头。
- 重新发布命令通过真实数据库状态验证 generation 递增、完整拓扑保留和当前契约版本生效。

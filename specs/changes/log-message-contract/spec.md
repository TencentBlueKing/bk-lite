# 日志正文统一契约

Status: implemented

## Problem Statement

18 种内置日志采集类型对主要文本的命名不一致。Kubernetes、Winlogbeat 与 SNMP 会在
保留 `message` 的同时再生成完整副本，Packetbeat 还可能把整个结构化事件序列化到
`_msg`。中心系统 Vector 的 VictoriaLogs sink 固定读取 `_msg`，但大部分采集器只输出
`message`，导致正常正文被 VictoriaLogs 的缺失字段提示替代。前端随后直接依赖 `_msg`，
使存储引擎字段扩散为产品契约。

## Solution

日志正文的唯一逻辑字段是顶层 `message`。所有 Collector、NATS 事件、中心归一化、
日志提取器、查询接口和 Web 都使用该名称；`nginx.error.message` 等语义不同的解析属性
可以保留，但任何与完整正文相同的顶层副本都必须删除。

中心系统 Vector 固定拓扑为：

`Server NATS → normalize_event → log_extractors → prepare_victoria_logs → VictoriaLogs`

- `normalize_event` 兼容旧 `_msg`、`log_message`、`trap_message`、`raw_message`，以移动
  语义产生一个 `message`，然后删除全部已知别名。
- HTTP、Flow 与文件完整性等没有天然正文的结构化事件生成短摘要，禁止把整个事件
  JSON 序列化为正文。
- `log_extractors` 始终读取逻辑字段 `message`；旧正文别名是保护字段，用户规则不能
  重新写入。
- `prepare_victoria_logs` 是唯一存储适配器，通过 `._msg = del(.message)` 保证发送给
  VictoriaLogs 的事件只有一个物理正文。
- 查询适配器把字段参数、`message:` 过滤、`from message` 和 `fields message` 转换为
  `_msg`，并在响应和 SSE 中把 `_msg` 移回 `message`；嵌套 `*.message` 属性、全文
  关键词和引号内文本不改写。

## Collector Decisions

- Filebeat 9 类：声明并使用原生 `message`，保留语义不同的模块解析属性。
- Vector 4 类：file、docker、syslog 保留 `message`；Kubernetes 删除 `log_message`。
- Packetbeat 2 类：删除子模板空 `_msg` 与 Windows 全事件序列化，生成短 `message`。
- Auditbeat file_integrity：删除空 `_msg`，生成“动作 + 路径”的短 `message`。
- Snmptrapd：去掉 syslog 头后的 Trap 内容直接写回 `message`。
- Winlogbeat：保留原生 `message`，删除 `_msg` 副本和子模板空字段。

每个内置 `collect_type.json` 必须且只能声明一次顶层 `message`，不得声明正文别名。

## Compatibility and Rollback

- 发布顺序是中心归一化与查询适配器先上线，再滚动更新采集器配置；新中心兼容旧
  采集器。旧中心不理解仅含 `message` 的新事件，因此禁止先升级采集器，也不能在
  未回退采集器前回滚中心。
- 不批量回填 VictoriaLogs 历史数据。读取旧数据时优先已有 `message`；SNMP 优先解析后
  的 `trap_message`，并隐藏其他别名。
- `message:` 查询只映射完整顶层字段 token，不改写全文关键词、引号内文本或
  `nginx.error.message` 等结构化属性。
- 代码回滚使用现有镜像回滚流程；回退采集器不会丢日志，但可能在旧中心配置中恢复
  重复写入，因此中心版本应最后回滚。

## Testing Decisions

- 静态契约枚举全部 18 种采集类型，断言恰好一个 `message` 且没有旧正文别名。
- 扫描 K8s、Beat、SNMP 与全部子模板，禁止自动复制、空 `_msg` 和 `JSON.stringify(evt)`。
- 使用 Vector 0.48 真实执行旧 K8s、Winlogbeat、SNMP 与 Packetbeat 事件，断言归一化后
  只有 `message`，最终适配后只有 `_msg`。
- 查询模块测试逻辑/物理字段映射、历史冲突优先级、字段列表去重和 SSE NDJSON 转换。

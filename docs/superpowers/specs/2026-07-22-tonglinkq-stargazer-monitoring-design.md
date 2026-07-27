# TongLinkQ V8.x Stargazer 远程监控设计

> 状态：已评审设计稿
>
> 日期：2026-07-22
>
> 范围：企业版监控中心；不包含 CMDB 配置采集
>
> 验收基线：用户提供的 TongLinkQ V8.1 `tlqstat` 原始输出

## 1. 背景与目标

BK-Lite 监控中心通过插件元数据、接入表单和采集模板驱动监控接入。节点侧 Telegraf 负责周期触发与标准指标上报，VictoriaMetrics 保存时序数据。对于需要远程登录目标机的监控，现有 Remote Host 链路已经形成“Telegraf 触发 Stargazer、Stargazer 异步执行并经 NATS 上报指标”的模式。

本设计在企业版新增 TongLinkQ 监控对象。采集节点通过 SSH 登录 TongLinkQ 主机，执行只读 `tlqstat` 命令，按 QCU 形成监控实例，并采集队列、收发进程和连接容量等运行指标。

目标如下：

- 一个 QCU 对应一个 TongLinkQ 监控实例。
- 用户手工填写 QCU 名称，一条接入配置对应一个 QCU。
- 复用 Stargazer、ARQ、nats-executor 和 NATS 指标上报能力。
- 首版支持 SSH 用户名和密码认证。
- 解析器面向 TongLinkQ V8.x 做有限容错，最低保证 V8.1 验收样本。
- 单条命令失败时保留其他命令的有效指标，并明确暴露采集健康状态。
- 企业能力与社区版监控、其他监控插件及 CMDB 采集链路隔离。

## 2. 已确认决策

| 主题 | 决策 |
|---|---|
| 产品范围 | 仅监控中心，不改 CMDB |
| 采集方式 | 独立采集节点经 Stargazer 远程 SSH 执行 |
| 认证方式 | 首版仅用户名和密码 |
| 对象粒度 | 单一 TongLinkQ 对象，QCU 为实例 |
| 队列与进程 | 作为指标维度，不创建子监控对象 |
| QCU 接入 | 用户手工填写 QCU 名称 |
| 命令环境 | 可配置 `tlqstat` 路径和可选环境文件路径 |
| 首版命令 | `-qcu`、`-qcu <qcu> -c`、`-snd <qcu>`、`-rcv <qcu>`、`-limit` |
| 采集周期 | 用户可配置，默认 60 秒 |
| 兼容范围 | V8.x 容错；V8.1 样本为强制验收基线 |
| 部分失败 | 成功部分继续上报，失败命令产生有界健康指标 |

## 3. 非目标

首版不包含：

- `tlqstat -sys`、`tlqstat -ver`、License 和其他静态系统参数。
- CMDB 模型、配置发现、CMDB 采集任务或监控到 CMDB 的同步。
- QCU 自动发现和批量勾选。
- SSH 私钥认证、`sudo` 或 `su` 切换用户。
- TongLinkQ V9.x 兼容承诺。
- 队列、发送进程、接收进程等子监控对象。
- 通用远程命令监控框架。

## 4. 总体架构

### 4.1 数据流

1. 用户在监控中心企业插件中配置采集节点、SSH 目标、QCU 和周期。
2. 监控中心通过现有 Controller 渲染 Telegraf 子配置，并由节点管理下发。
3. Telegraf `inputs.prometheus` 按配置周期请求 Stargazer 企业接口。
4. Stargazer 校验请求并将 `monitor_type=tonglinkq` 任务放入 Redis/ARQ 队列，HTTP 立即返回 accepted 指标。
5. 企业任务处理器通过目标采集节点对应的 nats-executor `ssh.execute` 执行固定脚本。
6. 专用解析器把五组命令输出转换为 Prometheus 文本。
7. Stargazer 复用现有转换与发布能力，将 Prometheus 转成 Influx Line Protocol，发送至 `metrics.tonglinkq`。
8. 既有指标消费链路写入 VictoriaMetrics，监控中心按 `instance_id` 查询并展示 QCU 实例。

### 4.2 企业版组件

监控中心企业插件放在既有企业插件根目录下，包含：

- `metrics.json`：TongLinkQ 对象、指标、维度与列表展示字段。
- `UI.json`：接入表单和资产配置字段。
- Telegraf `.child.toml.j2`：周期请求 Stargazer 企业接口。
- `language/{zh-Hans,en}.yaml`：对象、指标和说明文本。
- `policy.json`：保守的默认告警模板。
- `guide/zh-Hans.md`：权限、路径、排障和运行前提说明。

Stargazer 企业包包含：

- 企业 Blueprint 路由 `/api/enterprise/monitor/tonglinkq/metrics`。
- TongLinkQ 企业任务处理器。
- 固定 SSH 采集脚本生成器。
- V8.x 输出解析器及 fixture。

### 4.3 共享链路影响控制

优先通过现有扩展点实现，不改变社区版业务分支：

- 监控插件迁移器已经扫描 `PluginConstants.ENTERPRISE_DIRECTORY`，不修改社区插件目录。
- Stargazer 已注册 `enterprise.api.ENTERPRISE_BLUEPRINTS`，专用路由放在企业 Blueprint。
- Stargazer worker 已支持按 `monitor_type` 动态寻找企业 handler。TongLinkQ 实现放在企业包的 middleware handler 中，并按现有企业分派契约导出 `collect_tonglinkq_metrics_task`，不在社区 worker 中新增品牌判断。
- 不注册 CMDB plugin、不修改 Stargazer CMDB `plugin.yml`、不修改 CMDB formatter、任务类型或模型配置。
- 不修改 Telegraf 默认模板；TongLinkQ 只增加独立 child config。

已知约束：当前社区 worker 的企业动态分派入口通过历史命名 `enterprise.tasks.handlers.storage_handler` 加载。企业包需要在该兼容入口重导出 TongLinkQ handler，实际实现仍放在 middleware 语义目录。若实施时发现必须修改社区 worker 才能注册企业 handler，须停止实施，提交影响分析并取得用户确认。

## 5. 接入配置

| 字段 | 必填 | 默认值 | 约束 |
|---|---:|---|---|
| 采集节点 | 是 | 无 | 使用当前节点授权与选择逻辑 |
| 目标主机 | 是 | 无 | 合法 IP 或域名 |
| SSH 端口 | 是 | `22` | 1–65535 |
| SSH 用户名 | 是 | 无 | 不允许控制字符 |
| SSH 密码 | 是 | 无 | `ENV_PASSWORD` 加密存储 |
| QCU 名称 | 是 | 无 | `[A-Za-z0-9._-]`，最大 128 字符 |
| `tlqstat` 路径 | 是 | `tlqstat` | 仅允许字面量 `tlqstat` 或规范化绝对路径 |
| 环境文件路径 | 否 | 空 | 仅允许规范化绝对文件路径 |
| 采集周期 | 是 | `60` 秒 | 用户可改，建议 UI 范围 10–3600 秒 |
| 执行超时 | 是 | `60` 秒 | 必须小于任务运行标记 TTL |
| 实例名称 | 是 | 由目标主机与 QCU 派生 | 用户可编辑展示名 |
| 所属组 | 否 | 当前授权组 | 沿用监控资产权限逻辑 |

环境文件只允许以安全方式执行 `source <quoted-absolute-path>`，不提供任意初始化命令。路径存在性和 `tlqstat` 可执行性在目标机执行阶段检查。

稳定实例标识由云区域、目标主机和 QCU 组成，必须使用现有安全实例 ID 工具生成，不能直接把未规范化字符串作为数据库主键。所有指标至少携带：

- `instance_id`
- `instance_type="tonglinkq"`
- `collect_type="http"`
- `config_type="tonglinkq"`
- `qcu_name`
- `target_host`

## 6. 远程执行协议

### 6.1 单会话执行

每轮只建立一次 SSH 会话。固定脚本按顺序执行：

1. `tlqstat -qcu`
2. `tlqstat -qcu <qcu> -c`
3. `tlqstat -snd <qcu>`
4. `tlqstat -rcv <qcu>`
5. `tlqstat -limit`

脚本不能使用全局 `set -e` 中断整轮。每条命令独立捕获：

- 命令标识。
- 退出码。
- stdout。
- stderr。
- 单命令耗时。

输出使用固定、不可由用户输入构造的分隔标记封装。解析器先恢复命令级结果，再解析业务表格。

### 6.2 安全约束

- 命令集合固定，用户不能填写命令文本或额外参数。
- QCU、可执行路径和环境文件分别校验并 Shell 安全转义。
- 密码只通过现有加密 env config 和内部调用传递，不进入命令文本。
- SSH Host Key 校验沿用 nats-executor 平台配置，插件不得自行关闭。
- 日志不得记录密码、完整 Header、包含密码的任务参数或未脱敏 NATS payload。
- 目标输出设置合理大小上限；超限时保留截断标记并将对应命令判为解析失败。

## 7. V8.x 解析规则

解析器以标题和列名为主，不依赖单一固定字符宽度：

- 允许空行、连续空格、Tab 和 CRLF。
- 表头大小写按 V8.x 已知形态归一化，但指标字段映射使用明确白名单。
- 允许已知可选列缺失；缺失字段不生成指标，不用零值补齐。
- 空表是合法结果，不能判为采集失败。
- 未知表头或列结构产生有界 `parser_error`，不能猜测列含义。
- `unknown` 是有效业务状态，映射为状态枚举 2，不能映射成故障 0。

V8.1 fixture 至少覆盖用户提供的以下输出：QCU 列表、队列综合信息、发送进程、接收进程和连接容量限制。

## 8. 指标模型

### 8.1 QCU

| 指标 | 类型/单位 | 维度 | 说明 |
|---|---|---|---|
| `tonglinkq_qcu_status` | Enum | `qcu_name` | active=1，inactive=0，unknown=2 |
| `tonglinkq_qcu_runtime_seconds` | seconds | `qcu_name` | QCU 运行时长；V8.1 的 `RunTime` 按秒解释 |

`tonglinkq_qcu_status` 是对象默认状态指标。

### 8.2 队列

以下指标统一带 `queue_type` 和 `queue_name`；`queue_type` 取 `send/local/remote/virtual`：

- `tonglinkq_queue_ready`
- `tonglinkq_queue_sending`
- `tonglinkq_queue_receiving`
- `tonglinkq_queue_wait_ack`
- `tonglinkq_queue_delay`
- `tonglinkq_queue_getor`

源表不存在某列时不生成对应序列。`Delay` 在未获得厂商单位证据前按数量型原值展示，不标注为毫秒。

远程队列另提供：

- `tonglinkq_remote_queue_connection_status`
- `tonglinkq_remote_queue_info`

允许的补充维度为发送队列、目标队列、发送连接、目标主机、连接端口和连接类型。信息指标值固定为 1，仅承载稳定元数据。

### 8.3 收发进程

| 指标 | 类型/单位 | 维度 |
|---|---|---|
| `tonglinkq_send_process_status` | Enum | `proc_id`、`qcu_id` |
| `tonglinkq_send_process_connection_count` | count | `proc_id`、`qcu_id` |
| `tonglinkq_receive_process_status` | Enum | `proc_id`、`qcu_id` |
| `tonglinkq_receive_process_info` | Info | `proc_id`、`qcu_id`、`listen_ip`、`port` |

### 8.4 容量限制

统一使用 `resource_type=send/receive/client/jms`：

- `tonglinkq_connection_current`
- `tonglinkq_connection_limit`
- `tonglinkq_connection_usage_ratio`

使用率按百分比上报，取值范围为 0–100，单位为 `percent`。比例仅在上限大于零时生成；上限为零或不可解析时不生成比例。

### 8.5 采集健康

- `tonglinkq_collect_up`
- `tonglinkq_collect_command_success{command}`
- `tonglinkq_collect_duration_seconds`
- `tonglinkq_collect_error{stage,reason}`
- `tonglinkq_parser_error{command,reason}`

两个错误指标均为 Gauge：本轮出现对应错误时值为 1，正常轮次不生成错误序列，由 `collect_up` 和命令成功指标表达恢复状态。`command`、`stage` 和 `reason` 必须来自有限枚举；`reason` 首版仅允许 `ssh_auth`、`ssh_network`、`timeout`、`qcu_not_found`、`command_exit`、`parser_error`、`output_truncated`。stderr 和任意错误文本不得作为标签，防止时序高基数。

## 9. 异常语义

| 场景 | 行为 |
|---|---|
| SSH/认证/网络失败 | 上报 `collect_up=0` 和对应的有界 `collect_error`；不生成业务零值 |
| 指定 QCU 不存在 | 上报 `collect_up=0` 和 `collect_error{reason="qcu_not_found"}`；停止 QCU 依赖命令 |
| QCU 明确 inactive | 正常上报 `qcu_status=0`，不判为采集故障 |
| 单命令退出非零 | 其他命令继续；失败命令本轮无业务指标 |
| 命令成功但解析失败 | 该命令 `success=0`，记录有界 parser reason |
| 空队列表 | 合法成功，不生成队列序列 |
| 上一轮仍运行 | 新任务按目标主机和 QCU 去重，不并发执行 |
| 输出超限 | 截断日志摘要，对应命令判为解析失败 |

失败轮次不得以零值覆盖上一轮业务值。用户通过 `collect_up`、命令健康指标和无数据策略区分业务零值与采集中断。

## 10. 默认展示与告警

对象列表默认展示：

- QCU 状态。
- 运行时长。
- Ready 消息总数。
- WaitAck 总数。
- 最大连接容量使用率。
- 采集状态。

默认策略仅覆盖含义明确的场景：

- QCU 非 active 连续 2 个周期告警。
- `tonglinkq_collect_up=0` 连续 2 个周期告警。
- 任一连接容量使用率达到 80% 为 warning，达到 90% 为 critical。

Ready、WaitAck、Delay 和收发进程不预置固定阈值，由用户根据业务基线配置。

## 11. 测试设计

### 11.1 解析器单元测试

- V8.1 原始样本完整转换为预期指标。
- QCU active/inactive/unknown。
- 发送、本地、远程和虚拟队列表及空表。
- 发送和接收进程字段。
- 四类连接当前值、上限和比例。
- 多空格、Tab、CRLF、空行和已知可选列缺失。
- 未知表头、错误列数、非数字值和输出截断。

### 11.2 安全与异常测试

- QCU、可执行路径和环境文件注入字符被拒绝。
- 密码不出现在日志、响应、指标标签和命令文本中。
- SSH 认证失败、连接超时、命令超时和 QCU 不存在。
- 单命令失败时成功部分仍上报。
- 同一目标和 QCU 不产生重叠任务。

### 11.3 插件契约测试

- 企业 `metrics.json`、`UI.json`、模板、语言和策略文件可被现有迁移器加载。
- `instance_id`、指标名、维度名和 status query 一致。
- Telegraf 模板渲染后可通过配置校验。
- 企业插件缺失时社区版启动和现有插件同步不受影响。

### 11.4 链路测试

以伪造 nats-executor 响应跑通：

`Telegraf 请求 → Stargazer 入队 → 企业 handler → SSH 输出解析 → Prometheus → Influx Line → NATS`

同时回归：

- 现有 Stargazer Host、Windows WMI、VMware 和 QCloud 监控任务分派。
- 现有 Stargazer CMDB plugin task 分派。
- monitor 插件迁移与孤立对象清理行为。
- 企业包不存在时的社区版降级行为。

最终使用当前 TongLinkQ V8.1 环境进行真实冒烟测试。

## 12. 验收标准

1. 用户能够通过企业监控插件配置目标主机、密码、QCU、路径和周期。
2. 默认周期为 60 秒，用户修改后下发配置正确生效。
3. 正常环境在两个采集周期内出现对应 QCU 实例及状态、运行时长指标。
4. 队列、收发进程和容量限制指标与 V8.1 原始输出一致。
5. 任一子命令失败时，成功子命令的指标仍进入 VictoriaMetrics。
6. SSH 或认证失败时出现 `collect_up=0`，且不产生业务伪零值。
7. V8.1 fixture 全部通过，V8.x 容错用例通过。
8. 日志、指标和 API 响应中不存在明文密码。
9. 现有监控回归和 CMDB 采集回归无新增失败。
10. 社区版在没有企业包时的行为与基线一致。

## 13. 实施门禁与冲突上报

实施必须遵守以下门禁：

- 优先只新增企业插件和企业 Stargazer 文件。
- 任何社区版共享文件修改都必须先说明必要性、调用方、兼容策略和回归范围。
- 不得为了 TongLinkQ 修改 CMDB 模型、采集插件注册、任务请求格式或现有 fixture。
- 不得改变现有 Host/VMware/QCloud/Windows WMI 的路由、任务类型或指标主题。
- 如果企业 handler 无法通过现有动态分派入口注册，或 `metrics.tonglinkq` 与现有消费路由不兼容，应停止实施并向用户报告冲突，不得静默改造共享链路。
- 如果真实 V8.1 输出与当前截图存在结构差异，应保存脱敏原始证据并先更新解析契约，不得以猜测方式兼容。

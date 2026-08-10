# Stargazer IP 预检与凭据冷冻设计评审

日期：2026-08-06  
状态：评审记录，尚未形成实施决定  
范围：Stargazer 统一异步采集运行时、IP 发现、凭据亲和/冷冻及 CMDB 结果回写链路

## 结论

当前设计的正确方向是：一个目标内部串行尝试凭据、认证失败才冷冻凭据、网络失败不冷冻，
并跨采集运行复用成功亲和与失败状态。现有实现已经具备基础状态结构和 Redis 持久化，但实际
链路尚不能可靠满足这些语义。

需要优先处理两类风险：

1. IP 发现把扫描基础设施失败折叠成“全部目标离线”，可能导致错误离线对账；
2. 凭据冷冻缺少稳定目标端点、调用方作用域和凭据集合版本，且 Stargazer 与 CMDB 之间的
   结果事件契约不一致。

在这些问题修复前，不宜把当前预检结果或凭据冷冻状态视为完整、权威的业务事实。

## 统一领域语义

本评审采用根 `CONTEXT.md` 中的以下术语：

- **目标采集**：面向一个稳定目标身份的逻辑采集；
- **凭据尝试**：一个候选凭据对同一稳定目标端点的一次认证或采集尝试；
- **凭据冷冻**：确认认证失败后，对“目标端点 + 凭据”的临时排除；
- **凭据亲和**：最近成功凭据的优先尝试提示。

目标端点至少包含影响连接和认证语义的坐标，例如协议、主机、端口、API Endpoint、云区域
或远程执行节点。端口放在不同候选凭据中时，这些候选项并不是同一目标端点上的替代凭据，
不能共享同一个冷冻状态。

## 一、IP 预检与 IP 发现

### P1：扫描失败会被误认为目标离线

`IPDiscoveryScanner._tcp_probe()` 和 `_icmp_probe()` 捕获所有异常并返回 `False`，
`list_all_resources()` 最终仍固定返回 `success=True`。因此以下场景均与真实离线不可区分：

- 容器没有 ICMP raw socket 权限；
- 采集 Pod 到整个子网的路由或防火墙临时异常；
- 本机文件描述符、线程或子进程资源不足；
- 用户传入非法扫描方法、端口或超时；
- 扫描运行被外层超时取消。

CMDB 的 `apply_ip_discovery_vm_rows()` 会为每个选中子网调用 `apply_discovery_result()`；当某子网
没有在线行时，会按空在线集合执行离线对账。扫描基础设施失败因此可能把历史自动发现地址
批量置为离线。

建议引入每子网扫描完成事实：`completed | partial | failed`。只有 `completed` 的子网才允许
执行缺失地址离线对账；`partial` 和 `failed` 只记录运行错误并保留上一轮状态。

证据：

- `agents/stargazer/plugins/inputs/ip/ip_discovery_scanner.py:77-102,135-139`
- `server/apps/cmdb/services/ipam_discovery.py:299-324`

### P1：子网扫描绕过统一目标窗口

IP 发现请求没有 `hosts` 时，运行时只建立一个逻辑目标 `ip`。插件随后在内部把整个 CIDR
展开为列表，并通过一次 `asyncio.gather()` 创建全部主机协程。外层看到的目标数始终为 1，
因此 `MAX_TARGETS_PER_RUN`、`MAX_ACTIVE_TARGETS`、`TARGET_TASK_WINDOW` 和单目标断点均不覆盖
实际 IP 数量。

真实影响包括：

- `/16` 一次创建约 6.5 万个协程；
- IPv6 大前缀无法物化；
- 中途接管只能重跑整个子网；
- 固定内部并发 50 无法与 Pod 全局容量协调。

建议在接纳阶段计算并限制地址总量，由 TargetPlanner 流式产生 IP；若首轮仍保留插件内扫描，
至少使用有界队列且禁止不受支持的大前缀。

证据：

- `agents/stargazer/core/collection_request_builder.py:116-140`
- `agents/stargazer/plugins/inputs/ip/ip_discovery_scanner.py:43-75,135-139`

### P1：插件清单超时没有进入运行时执行计划

IP 插件清单声明 `timeout: 600`，统一运行时却固定使用全局 `PLUGIN_TIMEOUT=60`。默认 TCP 扫描
依次探测 4 个端口，每端口最多 5 秒、内部并发 50；多数端口被过滤的 `/24` 最坏时间约为：

```text
254 / 50 * 4 * 5 ≈ 102 秒
```

普通 `/24` 已可能被外层提前取消。插件超时应在插件解析后进入类型化执行计划，并允许部署层
设置全局上限，而不是完全忽略清单值。

证据：

- `agents/stargazer/plugins/inputs/ip/plugin.yml:14-21`
- `agents/stargazer/core/collection_application.py:50-57,113-118`

### P1：预检推断与最终插件执行器脱节

`collection_request_builder._apply_preflight_defaults()` 根据少量插件名和请求参数推断预检类型，
而真正的 executor、默认端口和采集器稍后才从 `plugin.yml` 解析。当前已确认的偏差包括：

| 插件/执行器 | 真实连接 | 当前默认预检 |
| --- | --- | --- |
| `network_config_file` | Netmiko TCP/22 | `none` |
| `physcial_server:protocol` | IPMI UDP/623 | `none` |
| `fusioninsight` | HTTPS/443 | `none` |
| `oceanstor` | HTTPS/8088 | `none` |
| Job 插件 | 选定节点经 NATS 执行 SSH/本地脚本 | 未必检查实际 responder |
| 云插件 | 多个云 API Endpoint | `UNKNOWN`，未执行端点检查 |
| SNMP | 凭据相关 UDP 请求 | `UNKNOWN`，未执行最小协议请求 |

建议在解析最终插件来源和 executor 后产生 `ResolvedTargetPlan`，至少包含 transport、稳定目标
端点、TLS 策略、remote responder、超时和出站策略。预检不再读取散落的字符串参数。

证据：

- `agents/stargazer/core/collection_request_builder.py:163-193`
- `agents/stargazer/core/preflight.py:30-86`
- `agents/stargazer/core/yaml_reader.py:195-236`

### P1：出站策略只校验预检连接

预检把域名解析为允许地址后进行 TCP/TLS 连接，正式插件仍使用原始 host 独立解析和连接。
多 A 记录、DNS rebinding 和插件重定向可能让正式连接走向未经校验的地址；Cloud、SNMP 等
`UNKNOWN` 路径也没有统一实际连接阶段校验。

建议把统一出站策略下沉为受控 dialer/HTTP transport，并由真实插件连接复用；预检本身不能
充当正式连接的安全授权凭证。

证据：

- `agents/stargazer/core/outbound_policy.py:45-70`
- `agents/stargazer/core/preflight.py:88-101`
- `agents/stargazer/core/collection_plugins.py:224-238`

### P2：TLS 预检与插件 TLS 策略不一致

HTTPS 预检固定使用系统默认 CA 校验，而 FusionInsight、OceanStor 等插件允许按配置关闭证书
校验。企业设备常使用自签名证书；如果只给这些插件补 HTTPS 预检，会出现预检失败但真实插件
本可成功的假阴性。

TLS 校验、SNI、CA 和客户端证书必须来自同一个已解析执行计划。

## 二、凭据亲和与冷冻

### 正确的基础设计

以下实现方向应保留：

- 不把 `IP × 凭据` 展开为全局任务；
- 同一目标内串行尝试凭据，首个成功后停止；
- 预检明确不可达时不尝试凭据；
- 认证失败使用 `1h → 4h → 24h` 渐进冷冻；
- 网络失败和插件失败不冷冻凭据；
- Redis 只保存凭据引用与状态，不保存秘密正文；
- 全部凭据冷冻时返回最近 `next_retry_at`。

对应实现集中在：

- `agents/stargazer/core/credential_policy.py`
- `agents/stargazer/core/target_collection_executor.py:395-503`
- `agents/stargazer/core/redis_collection_state.py:245-355`

### P1：目标身份只有 host，错误地跨端口和 Endpoint 共享状态

`CredentialScope.target_id` 当前直接使用运行时 `target`；请求构建器的目标通常只有 host，端口
保存在公共参数或单个凭据中。因此同一主机的 MySQL 3306/3307、SSH 22/2200、不同 SNMP
端口或 API Endpoint 会共享凭据亲和和冷冻。

更严重的是，现有上游测试允许不同凭据携带不同 `port`。这实际上表示不同目标端点，不应被
建模为同一目标上的替代凭据。

建议：

- 目标身份使用稳定、规范化的 Endpoint ID；
- host、port、transport、region/responder 等连接坐标归目标；
- 凭据只携带认证材料和凭据版本；
- 入站阶段拒绝一个凭据池内互相冲突的目标坐标。

证据：

- `agents/stargazer/core/credential_policy.py:144-153`
- `agents/stargazer/core/collection_request_builder.py:116-140`
- `server/apps/cmdb/node_configs/*` 中多凭据端口参数

### P1：生产请求没有提供真实 scope/version，默认值导致污染

策略设计要求作用域为：

```text
scope_id + plugin_ref + target_id + credential_set_version
```

但当前 server 下发链路没有提供 `scope_id` 或 `credential_set_version`，请求构建器统一回退到
`default`。结果是：

- 不同组织或采集任务可能共享同一插件/目标的状态；
- 同一 credential ID 修改密码后，旧冷冻仍可能持续最多约 25 小时；
- 凭据集合调整或顺序变化后，旧亲和可能指向语义不同的凭据；
- 自动生成的 `credential-1` 等位置 ID 会把缓存状态绑定到输入顺序，而非稳定凭据身份。

建议由 CMDB 明确下发稳定的租户/任务配置作用域，以及随凭据集合任何认证材料变化而变化的
集合版本；多凭据模式应要求稳定 `credential_id`，禁止用位置生成跨运行复用的身份。

证据：

- `agents/stargazer/core/collection_request_builder.py:98-105,143-160`
- `agents/stargazer/core/credential_policy.py:144-153`
- `server/` 中当前没有 Stargazer `scope_id`/`credential_set_version` 下发实现

### P1：一个凭据成功会清除同作用域全部凭据的失败事实

`CredentialPolicy.record_success()` 设置成功亲和后调用 `clear_scope_failures()`，会删除该目标下
所有凭据的失败状态。凭据 B 成功并不能证明此前认证失败的凭据 A 已被修复。当前行为会让 A
在下一轮立即重新成为候选；当亲和凭据 B 后续临时失败时，A 可能再次触发无效登录或账号锁定。

成功时只应清除当前成功凭据自身的失败状态，并更新亲和；其他凭据的已确认认证失败应保留到
冷冻到期或其版本发生变化。

证据：

- `agents/stargazer/core/credential_policy.py:103-115`
- `agents/stargazer/tests/test_credential_policy.py:7-44` 当前测试显式接受了全部清除行为

### P1：错误分类依赖字符串关键词，冷冻事实不可信

配置插件通过错误文本中的 `auth/password/credential/denied/community` 等词判断认证失败。
这会同时产生：

- 假阳性：例如“authentication plugin missing”是插件/环境错误，却可能冷冻凭据；
- 假阴性：本地化错误、厂商错误码或结构化异常没有命中英文关键词；
- SNMP 无响应只能轮换凭据，但无法区分网络、ACL、community 和 SNMPv3 安全级别问题；
- CMDB 侧还有另一套不同关键词分类，两个系统可能得出不同结论。

应由插件 Adapter 把厂商异常转换为结构化结果：`auth_rejected`、`transport_failed`、
`protocol_no_response`、`rate_limited`、`plugin_failed`。只有 `auth_rejected` 可直接冷冻；
`protocol_no_response` 最多允许本轮尝试下一凭据，不持久化认证失败。

证据：

- `agents/stargazer/core/collection_plugins.py:18-42,273-292`
- `server/apps/cmdb/services/collect_dispatch_service.py:40-51,261-266`

### P1：Stargazer 与 CMDB 凭据结果事件契约不一致

新运行时发布的事件字段为：

```text
collect_task_id, plugin_ref, host, credential_id, status,
error_code, attempts, fence, result_id, finished_at
```

CMDB 消费端却读取：

```text
success, failure_kind, error_message, snapshot
```

因此新运行时的成功事件在 CMDB 中会被 `bool(data.get("success"))` 解释为失败，且默认按
`failure_kind=task` 写为 `untested`。同时新运行时只发布最终目标结果，不发布每个凭据尝试：
“凭据 A 认证失败、凭据 B 成功”只会上报 B 的最终结果；全部认证失败时最终结果没有
credential ID，CMDB 会忽略该事件。

这意味着 CMDB 的 `CollectTaskCredentialHit` 不能作为新运行时冷冻状态的可靠镜像。

建议明确单一权威：

- **执行决策权威**放在 Stargazer Redis；
- CMDB 只消费不可变的逐凭据尝试事件，用于展示和审计，不自行重新推导冷冻；
- 或者由 CMDB 持有权威状态并在每次请求中下发有版本的候选集合，但不能两边独立演算。

无论选择哪种方案，都应定义版本化事件契约，并至少包含 `event_id`、Endpoint ID、scope、
credential ID/version、typed outcome、occurred_at 和 attempt/run ID。

证据：

- `agents/stargazer/core/result_publisher.py:76-97`
- `agents/stargazer/core/credential_state_cache.py:74-94`
- `server/apps/cmdb/services/collect_credential_result_service.py:9-62`

### P1：并发运行会丢失失败计数或让迟到失败覆盖成功

`eligible_credentials()`、`get_failure()`、`set_failure()` 和 `record_success()` 是多个独立 Redis
操作，没有 scope/credential 级原子更新，也没有事件时间或 fencing。两个不同 task ID 的运行
可以同时采集同一 Endpoint：

- 两次认证失败都读到旧计数 0，最终仍只保存 1 次；
- 一次成功先清除失败，另一次迟到失败随后重新冷冻同一凭据；
- 成功亲和与失败状态可能来自不同运行，无法判断新旧。

建议用 Redis Lua/CAS 原子更新失败计数，并携带 `observed_at` 或单调版本拒绝迟到状态；必要时
增加短期 Endpoint + credential 尝试租约，避免多个采集运行同时冲击同一账号。

证据：

- `agents/stargazer/core/credential_policy.py:69-142`
- `agents/stargazer/core/redis_collection_state.py:261-327`

### P2：冷冻后的重试只提供时间，不提供重新调度

全部凭据冷冻时目标结果为 `no_valid_credential`，并作为目标结果进入 checkpoint。相同 task ID
重入会复用完成状态，不会在 `next_retry_at` 自动重试。当前设计依赖上游后续创建新的采集运行。

这可以是有效取舍，但接口和 UI 必须明确：`next_retry_at` 是下一次新运行允许尝试的时间，不是
当前运行内部已安排的重试时间。

## 三、建议的目标状态模型

建议采用一个权威的凭据状态模块，接口隐藏 Redis 和 CMDB 镜像细节：

```text
CredentialScope
  owner_scope_id
  plugin_ref
  endpoint_id
  credential_set_version

CredentialState
  credential_id
  credential_version
  affinity: preferred | normal
  cooldown_until
  consecutive_auth_rejections
  last_typed_outcome
  observed_at
```

状态转换：

| 结果 | 亲和 | 冷冻 | 是否继续下一凭据 |
| --- | --- | --- | --- |
| 成功 | 当前凭据设为 preferred | 只清当前凭据失败 | 否 |
| 明确认定认证拒绝 | 不变；若当前亲和可撤销 | 1h/4h/24h | 是 |
| SNMP/UDP 无响应 | 不变 | 不持久化冷冻 | 是，但受本轮尝试上限约束 |
| 网络/目标不可达 | 不变 | 不变 | 否 |
| 限流/账号锁定 | 不变 | 使用服务端 retry-after 或独立保护状态 | 通常否 |
| 插件/数据错误 | 不变 | 不变 | 否 |

## 四、推荐提案：自适应凭据保护

本节是推荐设计提案，尚未成为已批准的实现决定。产品界面继续使用“凭据冷冻”或“凭据保护”，
内部可以使用惩罚分；不建议向用户暴露“惩罚账号”这样的表达。

固定 `1h → 4h → 24h` 只能描述一个凭据的连续失败，无法区分错误凭据扩散、目标离线、账号
锁定、云 API 限流和插件批量故障。建议使用“分类状态 + 独立惩罚维度”，避免把所有异常压缩
成一个黑盒分数。

### 4.1 四个保护维度

| 维度 | 解决的问题 | 保护动作 |
| --- | --- | --- |
| 凭据 × Endpoint | 某凭据只在某个稳定目标端点认证失败 | 冷冻该组合 |
| 凭据 × 认证域 | 同一凭据在大量目标连续认证失败 | 隔离凭据，停止继续扩散 |
| Endpoint 健康 | 网络、端口或协议不可达 | 熔断目标，不轮询全部凭据 |
| 插件健康 | SDK、依赖或插件实现批量异常 | 暂停插件或降载，不污染凭据状态 |

认证域建议定义为：

```text
owner_scope + plugin_ref + credential_id + credential_version + auth_realm
```

`auth_realm` 用于表达 AD 域、设备管理域或云账号等共享锁定策略；无法确定时退化到 owner scope
与插件范围，避免无依据地跨租户或跨协议关联失败。

### 4.2 Endpoint 级认证惩罚

只有插件 Adapter 明确认定 `auth_rejected` 时，才增加 `credential + endpoint` 的认证惩罚。
建议初始默认值：

| 24 小时内明确认证失败次数 | 冷冻时间 |
| --- | ---: |
| 第 1 次 | 5 分钟 |
| 第 2 次 | 30 分钟 |
| 第 3 次 | 4 小时 |
| 第 4 次及以上 | 24 小时 |

相比首次直接冷冻 1 小时，5 分钟可以让用户修正刚录入的错误密码后较快恢复；连续失败仍快速
升级，避免账号锁定。冷冻时间应增加少量随机抖动，防止大量目标同一时刻恢复并形成认证洪峰。

当前凭据在当前 Endpoint 成功后：

- 清除当前 `credential + endpoint + version` 的认证惩罚；
- 将当前凭据设为该 Endpoint 的亲和凭据；
- 不清除其他凭据的失败事实；
- 不清除同一凭据在其他 Endpoint 的失败事实；
- 对认证域级失败证据进行衰减，但不无条件清空。

### 4.3 SNMP/UDP 无响应

`protocol_no_response` 不增加持久认证惩罚，因为它可能来自丢包、ACL、community 错误、
SNMPv3 安全参数错误或设备限流。运行时可以在本轮尝试下一凭据，但每个目标应设置 2～3 个
凭据的探测上限，避免一个离线设备消耗完整凭据池。

如果设备返回明确的 SNMP authorization error，可由对应 Adapter 转为 `auth_rejected`；不能仅凭
超时推导认证失败。

### 4.4 Endpoint 熔断

网络和协议错误只更新 Endpoint 健康，不更新凭据惩罚。建议默认状态转换：

```text
closed --连续传输失败--> open --到达 retry_at--> half_open
   ^                                           |
   |--------------- 单次探测成功 -------------|
```

- 5 分钟内连续 3 次传输失败：熔断 5 分钟；
- 到期进入 `half_open`，全局只允许一个单次探测；
- 半开失败升级到 30 分钟，成功则关闭熔断；
- 熔断期间直接返回 Endpoint 保护状态，不遍历候选凭据。

Endpoint 熔断必须和 IP 预检复用同一目标身份与传输错误分类，否则预检和凭据策略会维护两套
互相冲突的“目标是否可用”事实。

### 4.5 限流与账号锁定

`rate_limited` 和 `account_locked` 不是普通认证失败：

- 立即停止当前目标或认证域的后续凭据尝试；
- 优先使用服务端返回的 `Retry-After`/解锁时间；
- 没有明确时间时，默认至少保护 1 小时；
- 生成聚合产品告警，提示用户检查账号状态；
- 人工解除前应执行一次受控验证，不能只删除状态。

### 4.6 凭据扇出保护

一个错误凭据被同时下发到数百个目标，比单目标连续失败更容易触发域账号锁定。建议对新凭据、
新版本或长期未验证凭据采用渐进扇出：

1. 未取得成功证据前，只允许在 1～3 个 Endpoint 上验证；
2. 同一凭据未验证阶段的最大并发限制为 2～3；
3. 2 分钟内在 3 个不同 Endpoint 明确认证失败且成功数为 0，触发认证域级隔离；
4. 隔离后不再向剩余目标扩散，任务结果明确标记 `credential_quarantined`；
5. 取得成功后逐级放大并发，而不是瞬间放开全部目标。

阈值应作为产品默认策略集中管理，不为每个插件暴露大量配置项。只有存在明确厂商锁定规则时，
插件 Adapter 才覆盖默认阈值。

### 4.7 半开恢复与凭据版本

凭据冷冻到期后进入半开状态，而不是立即恢复全部并发：

```text
cooldown → half_open 单次验证 → success → healthy
                         └────→ auth_rejected → 更高级冷冻
```

同一个 `Endpoint + credential version` 同时只能持有一个半开尝试 token。凭据认证材料发生修改时
必须产生新的 `credential_version`；新版本从干净状态开始，旧版本状态保留用于审计但不阻塞
新版本。

### 4.8 产品呈现与人工操作

采集任务详情至少区分：

- 目标不可达；
- 凭据保护中；
- 凭据已隔离；
- 账号可能锁定；
- 插件异常；
- 全部凭据不可用。

凭据详情展示非敏感摘要：最近成功时间、最后失败类型、保护级别、下次允许尝试时间、影响目标
数量和凭据版本。提供“安全验证并解除”操作：只对一个用户确认的 Endpoint 进行低并发真实
验证，成功后解除对应状态，失败则保留或升级；不得提供无验证的一键清空全部保护。

告警只针对聚合高价值事件，例如认证域级隔离、账号锁定、任务全部凭据不可用和同插件大面积
异常；不为每个目标的一次认证失败单独告警。

### 4.9 深模块接口

建议把状态读取、排序、并发 token、惩罚升级、半开和事件生成收进一个深模块。调用方和插件只
学习两个接口：

```python
plan = await credential_protection.plan(
    scope,
    endpoint,
    candidates,
)

events = await credential_protection.complete(
    plan.attempt_token,
    typed_outcome,
)
```

`plan()` 返回有序候选凭据、跳过原因、最早重试时间和受控 attempt token；`complete()` 原子处理
亲和、惩罚升级/衰减、半开、迟到结果和审计事件。插件 Adapter 只返回结构化结果：

```text
success
auth_rejected
account_locked
rate_limited
transport_failed
protocol_no_response
plugin_failed
```

生产 Adapter 使用 Redis 原子实现；测试 Adapter 使用内存实现。CMDB 消费不可变事件作为产品
投影和审计，不独立重复计算执行冷冻状态。

### 4.10 分阶段落地

第一阶段，先保证基础正确性：

- Endpoint ID 包含协议、host、port、区域/responder；
- 引入稳定 credential ID 和 credential version；
- 成功只清当前凭据失败；
- 插件返回结构化结果；
- 统一 Stargazer 与 CMDB 事件契约。

第二阶段，增加账号保护：

- 半开单次验证；
- Redis 原子状态更新和迟到结果保护；
- 新凭据渐进扇出；
- 跨 Endpoint 连续失败隔离；
- 限流和账号锁定专用状态。

第三阶段，完善产品体验：

- 冷冻原因、影响范围和下次重试展示；
- 安全验证并解除；
- 聚合告警；
- Endpoint、凭据和插件三个维度的失败趋势。

## 五、修复顺序

1. 为 IP 发现增加扫描完成状态，失败时禁止离线对账；
2. 统一 Stargazer → CMDB 凭据尝试事件契约，停止错误镜像；
3. 将 target identity 改为 Endpoint ID，并禁止凭据携带冲突连接坐标；
4. 由 server 下发真实 scope 和 credential set/version；
5. 成功只清理当前凭据失败，不清除整个 scope；
6. 用结构化插件结果替代错误字符串猜测；
7. 原子化并发状态更新并处理迟到事件；
8. 将预检、插件超时和出站策略收敛到解析后的执行计划；
9. 把 IP 扫描改为受统一容量约束的流式目标。

## 六、必需验证场景

- ICMP 权限不足、整段路由失败、扫描超时时，不修改历史在线/离线状态；
- `/24` TCP 默认配置能在声明超时内完成，超大 CIDR 在接纳阶段被拒绝；
- 同主机不同端口不共享亲和或冷冻；
- 凭据密码更新、凭据池重排后不继承旧身份状态；
- A 认证失败、B 成功后，A 仍保持冷冻，B 成为亲和；
- 网络失败、插件异常、TLS 错误不会冷冻凭据；
- 结构化认证失败在数据库、SSH、WinRM、SNMPv3、云 API 上行为一致；
- 两个不同 task ID 并发命中同一 Endpoint/credential 时，失败计数不丢失且迟到失败不覆盖新成功；
- Stargazer 成功、认证失败和全部耗尽事件在 CMDB 中得到同语义结果；
- 事件重发幂等，同一毫秒超过批次上限时不丢事件；
- 自签名 TLS、多 A 记录和 DNS 地址变化仍遵守解析后的 TLS 与出站策略。

## 验证记录

2026-08-06 使用项目 Python 3.12/uv 环境运行：

```text
uv run pytest -q tests/test_preflight.py tests/test_collection_request_builder.py \
  tests/test_ip_discovery_scanner.py tests/test_ip_discovery_targets.py
```

结果：`22 passed`，伴随 2 个未注册 `unit` marker 警告。现有测试证明当前 mock 契约可运行，
但未覆盖本评审列出的真实故障、跨模块事件契约和并发状态场景。

凭据链路补充验证：

```text
uv run pytest -q tests/test_credential_policy.py tests/test_collection_plugins.py \
  tests/test_target_collection_executor.py tests/test_redis_collection_state.py \
  tests/test_result_publisher.py tests/test_collect_credential_push.py
```

结果：`30 passed`，伴随 1 个第三方 `websockets` 弃用警告。这些测试分别验证了两端当前各自
接受的契约，但没有把 Stargazer 实际事件交给 CMDB 消费端，因此未发现字段语义不一致。

CMDB 侧尝试运行 `test_collect_hit_state_service.py`、`test_collect_dispatch_service.py` 和
`test_collect_credential_event_nats.py`。共收集 20 项，7 项通过，13 项在复用现有 Django 测试
数据库的准备/模型访问阶段报错，未进入目标断言；本评审未重建或清理用户的现有测试数据库，
因此保留为基线环境限制，不把该结果作为功能失败证据。

# 告警责任人：事件上报、CMDB 丰富与兜底分派

Status: implemented

## Completion Evidence

- 事件接入把映射后的 `assignee` 归一化为最多 20 个用户名；未映射的源保持空列表。
- 丰富规则 `provider_config.owner_fields` 把 CMDB 用户 ID 转成用户名。丰富到则替换上报责任人，查不到、字段为空或查询失败时保留上报值。来源记在 `enrichment_meta.owner_source`。
- `Alert.owners` 是创建事件责任人的并集，最多 50 个。列表可用 `owner` 做精确成员过滤。
- 分派策略 `notification_target.prefer_alert_owner` 开启后，有有效责任人只通知责任人；没有责任人或责任人全部失效时，使用页面选择的兜底用户或组织。升级层不能开启该开关。
- 前端：丰富规则可配置 CMDB 用户字段；分派策略有「优先通知告警责任人」开关；告警列表、详情和通知模板变量 `alert.owners` 包含责任人，变量目录和预览样例也带这个字段。
- 验证（2026-10-13，sqlite + `--nomigrations`）：`apps/alerts/tests/test_source_adapter.py`、`test_alert_builder.py`、`test_enrichment_engine.py`、`test_enrichment_chain_service.py`、`test_notification_target.py`、`test_alert_owner_dispatch.py` 共 **137 passed**。完整路径测试 `test_ingress_enrichment_aggregation_and_dispatch_cover_three_owner_paths` 覆盖丰富替换、保留上报、走兜底。前端 `alert-assignment-notification-target-test` 通过，告警配置表单链 **203 passed**。本机 Postgres 未启动，历史迁移在 sqlite 上无法整库重放，迁移文件 `0036_alert_owners` 未在数据库上执行。

## Problem Statement

告警产生后，运维希望通知到告警对象的责任人，责任人数据缺失时仍要有人收到。现状有四个缺口：

1. `Event.assignee`（事件责任人）字段已存在，但不在告警源 `event_fields_mapping` 中，上游无法上报，字段从未被写入。
2. 告警丰富只能通过「出参投影」把 CMDB 字段写到 `enrichment.<namespace>.<别名>`。别名可以随意填写（例如 `a`），分派无法识别哪个字段代表责任人。
3. CMDB `user` 类型字段（如 `host.operator`）存的是用户 ID 列表，告警处理人和分派使用的是用户名，投影结果不能直接用于分派。
4. 分派策略只能通知固定用户或组织，无法「优先通知这条告警的责任人，没有责任人再通知兜底人员」。

部分 CMDB 模型（如 `aliyun_clb`）没有用户字段，这类告警永远拿不到丰富责任人，必须依赖上报或兜底。

## Solution

把 `Event.assignee` 作为唯一的「事件责任人」，并与处理人（`Alert.operator`）分离：

- 来源一：事件上报 `assignee`。
- 来源二：丰富规则新增「责任人映射」，把 CMDB 实例上选中的用户字段转换为用户名后写入 `Event.assignee`。
- 优先级：丰富最高。丰富到责任人时以丰富结果为准（替换上报值）；没有丰富到时保留上报值。
- 聚合：`Alert.owners` 为成员事件 `assignee` 的并集。
- 分派：策略新增开关「优先通知告警责任人」。开启后优先通知 `Alert.owners` 中的有效用户；告警没有责任人（事件既没上报也没丰富到）或全部失效时，以页面上选择的兜底用户或组织为准。

## User Stories

1. As a 上游监控系统接入方, I want 在事件里上报责任人用户名, so that 告警能直接通知到我指定的人
2. As a 告警中心管理员, I want 在丰富规则里选择 CMDB 实例的用户字段（默认主要维护人）作为告警责任人，并以 CMDB 数据为准, so that 责任人统一由 CMDB 维护，上游不上报时也能知道该通知谁
3. As a 告警中心管理员, I want 选择多个用户字段（如主要维护人 + 备份维护人）合并通知, so that 主备维护人都能收到
4. As a 告警中心管理员, I want 分派策略优先通知告警责任人，并配置必填的兜底用户或组织, so that 数据不规范时告警也不会无人处理
5. As a 告警处理人, I want 在告警详情、列表和通知内容里看到告警责任人, so that 我知道该找谁协作
6. As a 告警中心管理员, I want 知道某个责任人是上报的还是哪条丰富规则带出来的, so that 通知错人时能定位数据源

## Implementation Decisions

### 1. 事件上报责任人

- `DEFAULT_SOURCE_CONFIG.event_fields_mapping` 与 `event_fields_desc_mapping` 增加 `assignee`，契约为用户名字符串数组，可选。
- 接入时只做形状归一化：非数组或非字符串元素丢弃，去空白、去重，最多保留 20 个。不校验用户是否存在（留到分派时），不合法值不拒绝整条事件。
- 已有告警源配置不自动改写；存量源需要手动在字段映射中加入 `assignee` 才生效。
- 上报责任人允许是归属组织之外的租户内用户，与 `alert-ownership-oncall-split` 中「处理人可为租户内任意有效用户」一致。

### 2. 丰富规则「责任人映射」

- `EnrichmentRule.provider_config` 增加 `owner_fields`：CMDB 属性 ID 列表，可选，最多 5 个，不重复。不配置表示该规则不写责任人，行为与现在一致。
- 与「出参投影」相互独立：投影仍只写 `enrichment.<namespace>`；`owner_fields` 只写 `Event.assignee`，目标固定，不可配置别名。
- 取值：查到实例后，取所选字段的值合并去重。只接受整数用户 ID，非整数值丢弃；再转换为用户名，过滤不存在或已禁用的用户，最多 20 个。CMDB `search_instances_batch` 返回的是原始字段值，因此 ID → 用户名在告警侧通过 `system_mgmt.User` 完成，同一批事件只查询一次。
- 写入规则（丰富优先）：
  - 所有命中规则（按规则执行顺序）得到的用户合并去重。结果非空时，替换 `Event.assignee`，不与上报值合并。
  - 丰富结果为空时（规则未命中、未查到实例、实例没有所选字段、字段为空、转换后为空、查询失败或超时），保留上报的 `assignee`，也不报错。
  - 查询失败或超时与「查到但为空」同样保留上报值，不能把故障变成清空责任人。
  - `on_multiple` 查到多个实例时，按该规则的多结果策略选出的实例取值。
  - 被替换的上报值不另存字段，仍可从 `Event.raw_data` 追溯。
- 来源记录：`Event.enrichment_meta.owner_source` 记录 `enrichment`（附贡献规则 ID 列表，有界）、`reported` 或 `none`。不记录用户名单。
- 内置预设 `builtin_cmdb_resource` 不默认开启责任人映射；规则表单「责任人映射」新增时默认填 `operator`。

### 3. 聚合

- `Alert` 新增 `owners` JSONField（默认空列表，需迁移），值为成员事件（`action=created`）`assignee` 的有序并集，最多 50 个。在 `AlertBuilder` 的创建和更新路径与 `push_source_ids`、`monitor_objects` 同口径计算。

### 4. 分派「优先通知告警责任人」

- `notification_target` 增加布尔字段 `prefer_alert_owner`，默认 `false`；用户目标和组织目标都可以开启。字段缺失时与现有行为完全一致。
- 开启时，`usernames` / `organization_ids` 的含义变为兜底，且必须非空（沿用现有必填校验）。
- 解析（按告警逐条，不能像现在这样对一批告警只解析一次）：
  1. 读取 `Alert.owners`，过滤为存在且未禁用的用户；非空则只分派给他们，不叠加兜底人员，组织边界为 `None`（沿用用户目标的处理人校验）。
  2. `Alert.owners` 为空（成员事件既没上报也没丰富到责任人）或全部失效时，以页面选择的兜底用户或组织为准，按现有逻辑解析。
  3. 兜底也解析为空时，该告警保持未分派，进入现有全局未分派通知。
- 只作用于首次自动分派。升级链中各层的 `notification_target` 不支持 `prefer_alert_owner`，序列化器拒绝该字段。
- 告警后续事件带来新的责任人，不改写已有处理人；提醒和升级沿用已写入的处理人。
- 操作日志记录本次命中「责任人」还是「兜底」以及人数，不记录用户名单；INFO 日志按策略汇总两类命中次数。

### 5. 前端

- 丰富规则表单（数据源为 CMDB 时）新增「责任人映射」区块：
  - 「CMDB 用户字段」：可输入的多选标签，新增时默认 `operator`，提示「只取用户类型字段；丰富到责任人时以丰富结果为准，未丰富到时保留事件上报的责任人」。
  - 写入目标显示为只读文案「告警责任人」。
- 分派策略表单在「分派对象」下方新增开关「优先通知告警责任人」：
  - 开启后，「选择用户」/「选择组织」的标签改为「兜底用户」/「兜底组织」。
  - 提示文案：「优先通知告警上的责任人（来自事件上报或告警丰富）；责任人为空或均已失效时，通知兜底人员。」
- 告警详情与列表展示「责任人」；列表支持按责任人精确成员过滤（与「我的告警」一样，不能用 JSON 子串匹配）。
- 通知模板增加变量 `owners`。

## Testing Decisions

只测对外行为，优先复用现有接入、丰富、聚合、自动分派测试入口。

- 接入：映射了 `assignee` 的源写入归一化后的列表；非法元素丢弃、超限截断；未映射的源保持空列表。
- 丰富：
  - 选择 `operator` + `bak_operator` 时，用户 ID 合并去重并转换为用户名。
  - 禁用、不存在的用户 ID 被丢弃；非整数值被丢弃。
  - 上报了 `assignee` 且丰富到责任人：以丰富结果替换，`owner_source=enrichment`。
  - 上报了 `assignee` 但未丰富到（无字段、字段为空、未查到实例）：保留上报值，`owner_source=reported`。
  - 上报了 `assignee` 且 CMDB 查询失败或超时：保留上报值。
  - 既没上报也没丰富到：`assignee` 为空，`owner_source=none`。
  - 模型没有所选字段时不写入，`enrichment_meta` 状态不记为失败。
  - 多条规则命中时合并；`owner_source` 记录贡献规则。
  - 组织外实例查不到，不带出责任人（双租户）。
  - 不配置 `owner_fields` 的规则行为不变。
- 聚合：`owners` 为成员事件并集且有上限。
- 分派：
  - 开关关闭时行为与现在一致（回归）。
  - 开启且有有效责任人：只通知责任人，不通知兜底人员。
  - 开启但事件没有用户、告警 `owners` 为空，或责任人全部禁用：通知页面选择的兜底用户；兜底为组织时通知组织成员。
  - 兜底也为空：告警保持未分派，进入全局未分派通知。
  - 同一批告警中，不同告警分派给各自的责任人。
  - 开启时兜底为空，保存被拒绝；升级层携带 `prefer_alert_owner` 被拒绝。
- 日志：命中类型与人数作为独立参数，不包含用户名单。

## Out of Scope

- 沿 CMDB 关联（主机 → 应用 → 应用系统）查找应用系统负责人，作为第二期，在「责任人映射」中增加关联路径选项。
- 责任人变化后重新分派或改写处理人。
- 升级链使用告警责任人。
- 存量告警 `owners` 回填、存量告警源字段映射自动补齐。
- 对外 OpenAPI 新增端点（现有告警查询返回 `owners` 字段即可）。

## Further Notes

- 拆分建议：上报与 `Alert.owners`；丰富「责任人映射」；分派开关；前端两个表单与展示。前两个可以并行。
- 风险：外部告警源可以借 `assignee` 把通知发给租户内任意有效用户。配置了责任人映射且丰富到时，上报值会被 CMDB 数据替换，风险只存在于丰富不到的告警。首期按现有处理人口径接受；如需收紧，后续在告警源上增加「允许上报责任人」开关。

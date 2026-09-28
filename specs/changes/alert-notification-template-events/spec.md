# 告警通知模板与处理传参支持 Event 数据

状态：已实现，待提交。交互与资源边界以 2026-09-22 确认结果为准。

日期：2026-09-22。

关联：[自定义通知模板第一版](../alert-notification-templates/spec.md)、[渠道能力分析](../alert-notification-templates/channel-analysis.md)。

## 1. 目标与边界

在已有的告警通知模板和告警处理动作传参两条链路上，补齐 `Alert` 关联 `Event` 的数据访问能力：

- 通知正文里可以渲染该告警下的事件清单，条数和列都由使用者决定；
- 事件的嵌套 JSON 字段（`tags`、`labels`、`enrichment`）可以按点号路径取到叶子值；
- 告警处理动作的参数绑定可以引用代表事件的字段，把事件信息传给外部系统。

本次不做的事：

- 不引入 Jinja 或任何具备表达式、调用、条件和自定义循环体能力的模板引擎，理由见第 3 节；
- 不改 `unassigned_summary` 汇总模板，该范围没有单一告警上下文，明确禁止使用事件变量；
- 不改 `build_rule_payload`，即动作规则的匹配条件字段集合保持不变，避免存量规则的匹配行为漂移；
- 不改 `system_mgmt` 的自定义 Webhook 请求体机制，其 `{{content}}` 仍是字符串替换（限制见第 8 节）。

## 2. 现状事实

| 事实 | 位置 |
|---|---|
| 模板只支持 `{{ path.to.value }}`，显式拒绝 `{% %}`、`{# #}` | `notification_templates/renderer.py::validate_source` |
| 允许的根变量为 `alert`、`labels`、`dimensions`、`enrichment`、`notification`、`summary` | `renderer.py::ALLOWED_ROOTS` |
| 邮件渠道对模板源做 HTML 结构校验：变量必须完整落在文本节点，属性内不得出现变量，`script`/`style`/`iframe` 等标签被拒 | `renderer.py::_EmailHTMLValidator` |
| 渲染期按渠道分别转义：邮件 `html.escape`，三类机器人走 Markdown 反斜杠转义并把 `@` 变为 `@\u200b` | `renderer.py::render_source` |
| 体积上界：源 64KB、输出 256KB、单值 64KB、集合 100 项、嵌套 6 层、占位符 200 个 | `renderer.py` 常量 |
| 动作参数绑定走点号 payload，不走模板 | `action/payload.py`、`action/resolver.py` |
| `Alert.events` 是无界 M2M；`Event.Meta.ordering = ["-received_at"]`，故 `events.first()` 取到的是最近接收的事件 | `models/models.py` |
| `Event.raw_data` 是原始上报报文，无长度上界且可能含凭据 | `models/models.py::Event` |
| 同一次通知会对每个渠道各调一次 `render_bound_template` | `common/notify/dispatcher.py::build_channel_params` |

## 3. 为什么不上 Jinja

第一版的 `renderer.py` 在文件头就写明「模板内容来自页面，它不应拥有表达式、调用、循环或过滤器能力」。这不是保守，是四条具体代价：

1. **转义模型不匹配。** Jinja 的 autoescape 只有 HTML 一种。现有 Markdown 渠道用的是 `_escape_markdown`（转义 `` \`*_{}[]()#+-.!|>~ `` 并阻断 `@all`），纯文本渠道不转义。上了 Jinja 就要为每种渠道写 finalize/policies 并保证循环体内的输出也走同一条转义，等于把现有已回归的转义逻辑重写一遍。
2. **邮件 HTML 静态校验失效。** 现在的做法是把每个 `{{ }}` 替换成标记后用 `HTMLParser` 校验「变量只在文本节点」。一旦有 `{% for %}`，标签可以由循环拼出来（例如 `{% for %}<td{% endfor %}`），静态校验拿不到真实输出结构，这条防线只能作废，改成对每次发送的渲染结果做 HTML 解析，成本和失败语义都要重新定义。
3. **输出爆炸只能事后发现。** 现在是边替换边累加 `replacement_bytes`，超限立即中断。有了嵌套循环，256KB 上界要等渲染完才知道，而渲染过程本身可能先把 worker 内存打满。
4. **沙箱面。** 模板由多租户用户在页面编辑，属于不可信输入。`SandboxedEnvironment` 仍需自行禁用 `attr`、`getattr` 链和属性遍历，历史上也有逃逸 CVE。

结论：保留「无表达式」契约，把「循环」下沉为后端实现的声明式区块——使用者声明取哪些数据、哪些列、多少条，后端负责生成各渠道的正确格式并完成转义。

## 4. 事件区块语法

### 4.1 形式

新增一种自闭合区块，定界符 `{{@ ... @}}`。选它是因为 `{%`、`{#` 已被现有校验当作 Jinja 标记拒绝，而 `{{@` 不与之冲突。

```
{{@ events limit=10 order=-start_time columns=level as 告警级别, resource_name as 资源, tags.alert as 触发规则, value as 当前值, start_time as 发生时间 @}}
```

区块内只有 `key=value` 参数，没有循环体、条件、函数调用和表达式。解析器是一个参数切分器，不是求值器。

### 4.2 参数

| 参数 | 取值 | 默认 | 说明 |
|---|---|---|---|
| `columns` | 1~10 个 `路径[ as 表头]`，逗号分隔 | 必填 | 路径见 4.3；省略 `as` 时用内置中文名 |
| `limit` | `1`~`100` 的整数，或 `all` | `10` | `all` 表示上限内的全部，见 4.5 |
| `order` | `-start_time` / `start_time` / `-received_at` / `received_at` | `-start_time` | 白名单枚举 |
| `format` | `table` / `list` | 按渠道自动选 | 显式覆盖，见 4.4 |
| `empty` | ≤32 字符文本 | `无关联事件` | 该告警无关联事件时的替代输出 |

表头文本不得包含 `,`、`{`、`}`、`@` 和换行，长度 ≤32。

### 4.3 列路径白名单

允许的标量字段：`event_id`、`external_id`、`title`、`description`、`level`、`status`、`action`、`event_type`、`item`、`value`、`service`、`location`、`start_time`、`end_time`、`received_at`、`resource_id`、`resource_name`、`resource_type`、`push_source_id`、`rule_id`、`source_name`。

其中：

- `level` 在通知模板里输出 `Level(level_type="event")` 映射后的展示名；动作参数绑定里的 `event.level` 保持库存原值，避免外部系统拿展示名去对级别 ID；
- `source_name` 取 `Event.source.name`，查询需 `select_related("source")`；
- 不暴露数据库主键 `id`，对外事件标识统一为 `event_id`。

允许的嵌套 JSON 根：`tags.*`、`labels.*`、`enrichment.*`，路径总段数 ≤4。这与 `alert` 上下文已开放 `labels` / `enrichment` 的口径一致。

明确拒绝：

- `raw_data` 及其子路径——原始上报报文无长度上界，且可能包含来源侧凭据与完整 payload；
- `enrichment_meta`——丰富执行诊断数据，不是业务字段；
- `ingest_key`——接入幂等指纹；
- `assignee`、`team`——JSON 数组，渲染成 JSON 串对收件人没有意义；
- `monitor_id`、`cmdb_id`、`node_id`——内部快照 ID。

JSON 路径省略 `as` 时，表头把路径里的 `.` 换成 `_`（`tags.team` → `tags_team`，`enrichment.cmdb.owner` → `enrichment_cmdb_owner`）。

### 4.4 各渠道输出形态

同一个区块声明在不同渠道产出不同格式，由后端决定，使用者不需要为每个渠道各写一套排版：

| 渠道 | 默认 `format` | 输出 |
|---|---|---|
| 邮件 | `table` | 内联样式 `<table>`，风格与现有内置模板一致；单元格值 `html.escape` |
| 钉钉 / 飞书机器人 | `list` | 每条事件一行，`字段: 值` 以 ` \| ` 连接 |
| 企业微信机器人 | `list` | 同上；企微 Markdown 不支持表格，不赌渲染兼容性 |
| 自定义 Webhook / OpsPilot NATS | `table`（纯文本对齐） | 首行列名，`\|` 分隔 |

区块只产出给人阅读的文本形态，不提供 JSON 输出。结构化传参由第 8 节的动作参数绑定承担，两者不混在同一条链路上。

区块产出的是已完成格式化和转义的可信片段，渲染时不再经过外层的 `html.escape` 或 `_escape_markdown`。实现上用一个 `SafeFragment` 包装类型承载，由 `render_source` 识别后原样写入，避免用路径白名单来判断「哪些值不转义」而与上下文脱节。

### 4.5 资源边界

| 约束 | 值 | 理由 |
|---|---|---|
| 单次读取事件上限 | 100 条 | `Alert.events` 无界，`limit=all` 实际取该上限 |
| 每份渠道内容的区块数 | ≤5 | 与列数上限共同约束输出规模 |
| 单元格值长度 | ≤200 字符，超出截断并加省略号 | 覆盖 `description` 等无界 TextField，以及 dict/list 值序列化后的长度 |
| 总输出 | 沿用 `MAX_OUTPUT_BYTES` = 256KB | 区块按剩余预算逐行装入，放不下一行就少放，页脚写实际展示行数；一行都放不下才走原有超限错误 |

实际事件数超过展示条数时，在区块末尾追加「共 N 条，已展示前 M 条」，不静默截断。

每个实际用到的 `order` 各查一次 `select_related("source").defer("raw_data", "enrichment_meta").order_by(...)[:100]`，同一告警同一次派发里按 order 缓存。`events.latest` / `events.first` 另取一条。`defer` 是必须的，`raw_data` 是该表最大的列。排序只支持发生时间和接收时间，不按级别排。

## 5. 单条事件与计数变量

除区块外，`ALLOWED_ROOTS` 新增 `events` 根，支持普通 `{{ path }}` 取值：

- `{{ events.count }}`：关联事件总数；
- `{{ events.latest.* }}`：最近接收事件，字段路径同 4.3；
- `{{ events.first.* }}`：最早接收事件。

需求原文写的 `event.id`、`event.tags.alert`，在通知模板侧对应 `{{ events.latest.event_id }}`、`{{ events.latest.tags.alert }}`。统一到 `events.*` 一个命名空间，不设 `event.*` 别名，避免同一份模板里出现两套等价路径。

`_resolve_path` 已支持任意深度 Mapping 取值，此处只需扩展 `ALLOWED_ROOTS` 与 `_validate_placeholder` 的字段校验，不改路径解析逻辑。

## 6. 取数时机与复用

1. **惰性。** 渲染前扫描模板源，只有出现事件区块或 `events.*` 路径时才查询事件，未使用事件变量的存量模板不产生任何额外 SQL。
2. **按排序各查一次。** 一次通知对同一条告警：需要计数时一次 `count()`，每个实际用到的 `order` 各取前 100 条。同一 order 在这次派发里缓存，多渠道不重复查。
3. **跨渠道复用。** `build_channel_params` 目前对每个渠道各调一次 `render_bound_template`，事件数据需要在这一层按告警缓存，否则一条告警配了 4 个渠道就查 4 遍。

## 7. 作用域约束

| 模板范围 | 事件变量 |
|---|---|
| `single_alert` | 允许 |
| `alert_operation` | 允许 |
| `unassigned_summary` | 拒绝，报「汇总模板不能使用事件变量」 |

校验落在 `_validate_placeholder` 和区块解析入口，与现有 `summary` 变量的 scope 约束同一处实现。

## 8. 告警处理动作传参

这是与模板无关的第二条链路。动作参数绑定的形式是 `{"name": ..., "from": "field", "value": "labels.env"}`，由 `resolve_params` 从点号 payload 取值，不存在模板渲染。

改动：在 `build_match_payload` 中注入代表事件的扁平路径，代表事件取 `alert.events.first()`，即最近接收的事件——与该函数现有的 `source_id` 取值来源保持同一条事件。

新增路径：

- `event.<标量字段>`，字段集合同 4.3；
- `event.tags.*`、`event.labels.*`、`event.enrichment.*` 的扁平叶子路径，复用现有 `_flatten`；
- 不注入 `event.raw_data.*`。

这里用 `event.*` 而非 `events.latest.*`，因为该命名空间只有一条代表事件，且需求原文与作业参数绑定的既有风格都是扁平单值。

注入位置必须是 `build_match_payload` 而不是 `_base_payload`：后者同时被 `build_rule_payload` 使用，在那里加字段会改变存量动作规则的匹配语义。

作业参数要求标量，因此只有叶子路径可绑定；`event.tags` 这类中间节点不进入 payload。

## 9. 页面与 API

- `GET /notification_templates/catalog/` 扩展：新增 `event_fields`（可选列清单，含路径、中文名、类型）和事件区块的参数说明，供编辑器构建配置面板；
- 模板编辑页在现有「可用变量」标签行旁增加「插入事件表格」入口。标量列是可点开关；`tags` / `labels` / `enrichment` 点开后手填键名。确认后把区块插到正文光标处。语法由 UI 生成，之后只在正文里改，不提供二次打开弹窗；
- `_preview_context` 补充 2~3 条示例事件，让未选真实告警时的预览也能渲染出区块；
- 真实试发走 `_get_test_alert` 拿到的告警及其真实关联事件。

## 10. 验证要求

除常规单元测试外，以下行为必须有回归锁定：

1. `raw_data` 无论作为区块列还是 `events.latest.*` 路径都被拒绝，且动作 payload 中不出现该前缀;
2. 邮件渠道下区块产出的 HTML 不被二次转义，而单元格内的 `<script>` 等值被转义;
3. Markdown 渠道下单元格值走 Markdown 转义，`@all` 被阻断;
4. `limit=all` 在事件数超过 100 时只读 100 条，并输出总数提示；字节预算不够时少放行，页脚行数与实际输出一致；
5. 未使用事件变量的模板渲染不产生事件查询（查询计数断言）;
6. 多渠道通知对同一告警只查一次事件;
7. `unassigned_summary` 范围使用事件变量时校验失败;
8. `build_rule_payload` 的字段集合不含 `event.*`，存量动作规则匹配结果不变。

## 11. 已确认

1. 定界符 `{{@ ... @}}`。
2. 行数硬上限 100。单元格 200 字符。
3. 插入位置是正文光标。插入后只作为文本编辑，不提供二次打开弹窗。
4. Markdown 渠道自动出列表，不让用户选表格。
5. 弹窗不提供改表头；JSON 列默认表头为路径各段用下划线连接，如 `tags_team`。
6. `tags` / `labels` / `enrichment` 是开关，点开后手填键名，不提供固定可点键清单。
7. 动作传参只铺最近一条事件的扁平 `event.*`，不传事件列表。
8. 非法区块在保存模板时拒绝。渲染期仍走现有 `validate_source`，不另加降级文案。

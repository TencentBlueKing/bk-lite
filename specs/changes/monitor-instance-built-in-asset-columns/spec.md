# 监控实例摘要事实与内置展示列

> 状态：已确认并实现第一期；动态事实筛选、自动发现事实和历史节点事实对账不在第一期范围。

## 1. 问题定义

监控实例列表需要展示能够快速识别目标的信息。当前需求包括：

- 主机、数据库、中间件等对象展示资产 IP；
- Web、Ping、TCP 等拨测对象展示拨测节点和目标。

这些信息不是 `MonitorInstance` 的固定领域字段。未来对象可能需要展示集群、命名空间、
区域、设备型号、服务地址、云账号等新的摘要信息。如果每出现一种信息就在
`MonitorInstance` 增加一列，数据库模型、列表接口和前端表格会持续膨胀，并要求核心代码
理解每一种插件配置。

本变更需要解决的根问题是：**插件如何把自身配置转换成标准化的实例事实，以及监控对象
如何声明要展示哪些事实。**

## 2. 领域语言

- **监控实例（Monitor Instance）**：平台纳管的一个逻辑监控目标；拥有稳定身份、名称、
  所属对象和组织等核心信息。
- **采集端（Collector Node）**：执行采集或拨测的受管节点，不等同于监控目标。
- **监控目标（Target）**：被采集或拨测的实际资源或端点。
- **实例事实（Instance Fact）**：由插件接入配置或受信任平台数据推导出的、用于识别实例的
  标准化非敏感信息，例如 `asset.ip`、`probe.target`、`collector.nodes`。
- **事实绑定（Fact Binding）**：插件声明“某个实例事实由哪类数据源、按什么规则产生”。
- **实例摘要列（Instance Summary Column）**：监控对象声明在实例列表中展示哪个实例事实。

实例事实不是任意插件配置的副本，也不是指标。密码、令牌、完整采集配置禁止进入实例事实。

## 3. 设计原则

1. `MonitorInstance` 只保留稳定核心字段，不为每一种展示属性新增数据库列。
2. 数据来源与页面展示分离：插件负责产生事实，对象负责选择展示事实，页面只负责通用渲染。
3. 后端是事实解析的唯一权威；前端提交的节点名称、节点 IP 等只能作为输入提示，不能作为可信事实。
4. 插件显式声明事实绑定，不根据 `host`、`url` 等字段名进行全局猜测。
5. 常见来源使用声明式解析器；只有出现新的数据来源行为时才增加解析适配器，而不是每新增对象就改核心代码。
6. 事实值必须经过类型规整、大小限制和敏感字段白名单校验。

## 4. 推荐数据模型

### 4.1 MonitorInstance

新增一个通用 JSON 字段：

```python
summary_facts = models.JSONField(default=dict, verbose_name="实例摘要事实")
```

示例：

```json
{
  "asset.ip": "10.0.41.149",
  "collector.nodes": [
    {"id": "node-1", "name": "fusion-collector", "ip": "10.0.41.149"}
  ],
  "probe.target": "https://example.com/health"
}
```

该字段是由事实解析模块生成的只读投影，不接受通用接口任意写入。节点值保存稳定 ID 和接入时的
非敏感快照，使实例列表不依赖 NodeMgmt RPC 实时可用；节点变更可由运行期对账刷新。

### 4.2 MonitorPlugin

新增一个通用 JSON 配置字段：

```python
instance_fact_bindings = models.JSONField(default=list, verbose_name="实例事实绑定")
```

内容由插件 `metrics.json` 导入。示例：

```json
{
  "instance_fact_bindings": [
    {
      "fact": "asset.ip",
      "value_type": "ip",
      "resolver": "selected_node",
      "options": {"selection_field": "node_ids", "node_field": "ip", "cardinality": "one"}
    }
  ]
}
```

### 4.3 MonitorObject

新增一个通用 JSON 配置字段：

```python
instance_summary_columns = models.JSONField(default=list, verbose_name="实例摘要列")
```

内容由 `metrics.json` 中对应对象块导入。示例：

```json
{
  "instance_summary_columns": [
    {"fact": "collector.nodes", "title": "Probe Nodes", "order": 10},
    {"fact": "probe.target", "title": "Target", "order": 20}
  ]
}
```

列标题沿用插件语言文件翻译。列的渲染方式由事实定义的 `value_type` 决定，常见类型包括
`text`、`ip`、`endpoint`、`node_ref`、`node_ref_list`；未知类型安全回退为文本。

## 5. 插件契约

### 5.1 内置解析器

第一期提供以下后端解析器：

| resolver | 用途 | 示例 |
|---|---|---|
| `input` | 从接入实例的显式字段读取并规整 | 远程主机 `host -> asset.ip` |
| `selected_node` | 根据节点 ID 从 NodeMgmt 权威查询单个节点属性 | 本地主机 `node.ip -> asset.ip` |
| `selected_nodes` | 根据节点 ID 批量生成节点引用 | 拨测节点 |
| `compose_endpoint` | 从协议、主机、端口、路径组合规范化端点 | TCP 或 HTTP 目标 |
| `constant` | 插件声明固定的非敏感事实 | 极少数静态场景 |

解析器只允许读取绑定中声明的字段，不遍历或猜测插件输入。`value_type` 负责 IPv4/IPv6、URL、
端口、列表去重及最大长度校验。

若未来出现云 API 自动发现、父实例继承或指标标签回填等全新来源，则增加一个可复用的解析适配器，
例如 `discovery_payload` 或 `parent_fact`。新增使用现有来源的对象和插件不需要修改核心代码。

### 5.2 现有对象绑定示例

本地主机采集：

```json
{
  "fact": "asset.ip",
  "value_type": "ip",
  "resolver": "selected_node",
  "options": {"selection_field": "node_ids", "node_field": "ip", "cardinality": "one"}
}
```

远程主机采集：

```json
{
  "fact": "asset.ip",
  "value_type": "ip",
  "resolver": "input",
  "options": {"field": "host"}
}
```

Web 拨测：

```json
{
  "instance_fact_bindings": [
    {
      "fact": "collector.nodes",
      "value_type": "node_ref_list",
      "resolver": "selected_nodes",
      "options": {"selection_field": "node_ids"}
    },
    {
      "fact": "probe.target",
      "value_type": "endpoint",
      "resolver": "input",
      "options": {"field": "request_url"}
    }
  ]
}
```

## 6. 事实解析模块

在监控后端建立一个深模块，外部接口保持为：

```python
resolve(plugin, instance_input, trusted_context) -> dict[str, JsonValue]
```

调用方只需传入插件、单个实例输入和可信上下文。模块内部负责：

- 校验插件事实绑定；
- 批量预取和授权校验节点；
- 调用对应解析适配器；
- 类型规整及敏感信息过滤；
- 合并同一实例已有事实；
- 返回可直接持久化的 `summary_facts`。

插件接入、Excel 导入、重新配置和自动发现都必须通过同一接口产生事实，避免不同入口行为不一致。

### 6.1 多插件与冲突

同一个监控实例可以关联多个插件。事实合并遵循：

1. 相同事实的新值与旧值一致时幂等更新；
2. 新值为空时不覆盖已有非空事实；
3. 两个插件对同一单值事实产生不同非空值时拒绝静默覆盖，记录冲突并使本次配置失败；
4. 列表类型事实按稳定标识去重；
5. 删除采集配置后，通过运行期对账重新计算该实例事实，不在删除链路中猜测剩余来源。

第一期在 `summary_facts._sources` 中保留事实来源贡献。同一插件可幂等更新自己的贡献；不同插件产生
冲突的单值事实时拒绝写入，不能使用“最后写入者胜出”。删除采集配置后的事实重算留给运行期
对账能力实现。

## 7. 展示链路

后端实例列表返回：

```json
{
  "instance_id": "...",
  "instance_name": "...",
  "summary_facts": {...}
}
```

监控对象接口返回 `instance_summary_columns`。前端通用表格按列声明读取事实并按类型渲染：

```text
监控对象列声明 -> fact key -> 实例 summary_facts -> 通用 renderer
```

前端不再使用 `type === "Web"` 判断列，也不再认识 `probe_target`、`probe_nodes`、`ip` 等专用响应字段。
对象分类可以在插件初始化时提供默认列种子，但运行时展示必须以对象的显式列声明为准。

## 8. 插件初始化校验

`plugin_init` 必须快速失败并报告插件文件路径：

- `instance_fact_bindings` 的 fact key、类型、解析器和 options 不合法；
- 对象摘要列引用了没有任何关联插件能够产生的事实；
- 绑定读取未声明字段、使用不支持的解析器或声明敏感字段；
- 单值事实被同一插件重复绑定；
- 复合对象的摘要列放在错误的对象块中。

插件文档需要增加实例事实和摘要列章节，并提供本地主机、远程主机、Web、Ping、TCP 示例。

## 9. 兼容与迁移

当前 `MonitorInstance.ip` 早于本需求存在，并承担 Flow 网络资产身份兼容用途，不能直接删除。
它不再作为通用实例列表展示契约：

1. 新增三个通用 JSON 字段并完成插件元数据导入；
2. 为现有插件补充事实绑定和对象摘要列声明；
3. 将已有 `ip`、`probe_target`、`probe_node_ids`、`probe_nodes` 数据迁移到 `summary_facts`；
4. Flow 相关代码在过渡期同时维护既有 `ip` 字段与 `asset.ip` 事实；
5. 前端切换到摘要列通用渲染；
6. 验证无旧接口消费者后，删除本次新增的三个拨测专用字段；
7. `ip` 是否最终移除由 Flow 身份模型的独立变更决定，不在本变更中处理。

历史实例的回填优先使用数据库已有安全数据；需要读取 NodeMgmt 或外部系统的回填放入运行期幂等任务，
不得阻断服务启动。

## 10. 验收场景

1. 本地 `Host + Telegraf host`：`asset.ip` 来自所选节点的权威 IP。
2. 远程 `Host + Telegraf http`：`asset.ip` 来自远程目标，不被采集节点 IP 覆盖。
3. Web、Ping、TCP：展示全部拨测节点及规范化目标。
4. 数据库、中间件：按各插件显式绑定展示目标 IP；域名不会伪装成物理 IP。
5. 新插件只使用已有解析器和类型时，仅修改插件文件即可完成接入，无需数据库迁移、后端分支或前端列代码。
6. 新事实类型未提供专用 renderer 时安全显示文本，不导致页面失败。
7. 节点信息查询失败时，新建接入明确失败；实例列表仍可使用已持久化快照展示。
8. 插件绑定冲突、非法字段或敏感字段在 `plugin_init` 阶段失败。
9. Excel 导入、单条创建、编辑和重新接入对相同输入产生相同事实。
10. 旧实例迁移后与旧页面展示结果一致；无事实时统一显示 `--`。

## 11. 明确不采用的方案

### 每种属性增加一个 MonitorInstance 字段

拒绝。它把插件变化传播到数据库、序列化器和所有列表调用方，无法承载未来未知属性。

### 前端按对象类型或插件名称提取字段

拒绝。前端无法验证节点权威数据，且每个插件都会增加条件分支。

### 自动扫描 host、url、server 等常见字段名

拒绝。字段同名不代表语义相同，本地主机问题已经证明猜测式提取会产生错误或空值。

### 完全开放的 EAV 属性表

第一期拒绝。当前需求是小规模摘要展示，不需要任意属性查询、排序和关系建模。受约束 JSON 事实可以提供更小接口和更低读放大；若未来出现跨实例按任意事实过滤、索引和聚合的明确需求，再独立评估事实索引表。

## 12. 实施门禁

在开始改代码前需要确认：

- 接受“实例事实”作为统一扩展模型；
- 接受插件显式声明数据来源，而不是系统猜字段；
- 接受节点事实以 NodeMgmt 为权威并持久化非敏感快照；
- 接受 `MonitorInstance.ip` 暂时仅为 Flow 兼容保留；
- 确认第一期是否要求历史实例自动回填，以及是否需要事实列筛选/排序。

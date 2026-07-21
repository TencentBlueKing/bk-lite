# 网络拓扑大屏 - 验收规格

> 本 capability 的验收场景。所有场景均已在 `server/apps/operation_analysis/tests/test_network_topology_*.py` 中以测试用例形式实现并通过。

## ADDED Requirements

### Requirement: 网络拓扑画布模型（扁平 schema）

系统 MUST 在运营分析模块下提供 `NetworkTopology` 模型，承载网络拓扑大屏配置。模型 MUST 满足：

#### Scenario: 单表承载画布与 WeOps 凭据

- **WHEN** 用户创建一个网络拓扑大屏
- **THEN** 系统在 `operation_analysis_network_topology` 表中创建一行
- **AND** 该行的 `base_url` / `token` / `view_sets` 全部直接存储在该行上
- **AND** 不存在 `weops_connection_id` 等外键指向单独的凭据表

#### Scenario: Token Fernet 加密持久化

- **WHEN** 用户提交创建画布请求，明文 `token="plain-token"`
- **THEN** DB 列 `token` 存储的不是明文（以 `gAAAAA` 开头）
- **AND** 模型方法 `topology.decrypt_token()` 还原明文
- **AND** `topology.token_set()` 返回 `True`

#### Scenario: base_url 规范化

- **WHEN** 用户提交 `base_url="https://weops.example.com/api///"`
- **THEN** DB 存储为 `https://weops.example.com/api`（去尾斜杠）
- **WHEN** 用户提交 `base_url="weops.example.com"`（无 scheme）
- **THEN** 校验失败，返回 400
- **WHEN** 用户提交 `base_url="ftp://weops"`
- **THEN** 校验失败，返回 400

#### Scenario: 占位符 token 拒绝

- **WHEN** 用户提交 `token="******"`
- **THEN** 校验失败，返回 400（"Token 不允许使用占位符"）

### Requirement: view_sets JSON 应用层校验

系统 MUST 对 `view_sets` JSON 实施应用层结构校验，校验失败时返回 400，错误 detail 形如 `{"nodes": [...], "links": [...]}`。

#### Scenario: 节点 id 唯一性

- **WHEN** `view_sets` 包含两个 `id` 相同的节点
- **THEN** 校验失败，detail 中 `nodes` 包含 "节点 id 'node-1' 重复"

#### Scenario: 节点资产对 (bk_obj_id, bk_inst_id) 唯一性

- **WHEN** 画布包含两个节点 `(bk_switch, 10001)` 和 `(bk_switch, 10001)`（不同 id 但同资产）
- **THEN** 校验失败，detail 包含 "与画布中已有节点 (bk_switch, 10001) 重复"

#### Scenario: 连线引用完整性

- **WHEN** 画布中有连线引用 `target_node_id="ghost-node"`，但 `ghost-node` 不在画布
- **THEN** 校验失败，detail 包含 "连线 link-1 的 target_node_id 'ghost-node' 不在画布中"

#### Scenario: 非草稿连线必须有端口对

- **WHEN** `is_draft=false` 的连线 `port_pairs=[]`
- **THEN** 校验失败，detail 包含 "连线 link-1 至少需要 1 对端口"
- **WHEN** `is_draft=true` 的连线 `port_pairs=[]`
- **THEN** 校验通过

#### Scenario: 端口对 bk_inst_id 必填

- **WHEN** port_pair 缺 `source_interface.bk_inst_id`
- **THEN** 校验失败，detail 包含 "缺少源接口 bk_inst_id"

#### Scenario: 指标必填字段

- **WHEN** metric 缺 `metric_field` 或 `result_table_id`
- **THEN** 校验失败，detail 包含 "缺少 metric_field" / "缺少 result_table_id"

#### Scenario: 阈值必填字段

- **WHEN** threshold 缺 `value` 或 `color`
- **THEN** 校验失败，detail 包含 "缺少 value" / "缺少 color"

### Requirement: 应用层级联删除

系统 MUST 在应用层（非 DB FK）实施级联删除：删除一个节点时引用它的所有连线同步删除。

#### Scenario: 删除节点时级联删除引用它的连线

- **WHEN** 画布有 `node-1`、`node-2`，连线 `link-1` 引用两者
- **AND** 用户调用 `DELETE /api/network_topology/<id>/config/nodes/node-1/`
- **THEN** 节点 `node-1` 被删除
- **AND** 连线 `link-1` 也被删除（因为它引用了 `node-1`）
- **AND** 画布中剩下 `node-2`，无连线

#### Scenario: 删除不存在的节点是幂等 no-op

- **WHEN** 用户调用删除节点 API，节点 id 不存在
- **THEN** 不抛错，返回 200，view_sets 不变

### Requirement: Token API 可见性

系统 MUST 在 GET 接口中**永不**返回明文 token，只返回 `token_set: bool`。

#### Scenario: 创建后 token_set 标志

- **WHEN** 用户 POST 创建画布 body 包含明文 token
- **THEN** 响应 201
- **AND** 响应 `data.token_set == true`
- **AND** 响应 `data` 中不包含 `token` 字段
- **AND** 响应原文（`json.dumps(payload)`）不包含明文 token

#### Scenario: 详情接口不暴露 token

- **WHEN** 用户 GET `/api/network_topology/<id>/`
- **THEN** 响应 `data.token_set == true`
- **AND** 响应 `data` 中不包含 `token` 字段
- **AND** 响应原文不包含 DB 中密文 token

### Requirement: test_connection 端点

系统 MUST 提供 `POST /api/network_topology/test_connection/` 端点用于验证 WeOps 凭据，**不**持久化凭据。

#### Scenario: 凭据有效返回 200

- **WHEN** 用户 POST 端点，body 包含合法 base_url + token
- **THEN** 响应 200
- **AND** 响应 `data == {"status": "ok"}`
- **AND** DB 中无任何新行

#### Scenario: 凭据无效返回 403 + weops_token_invalid

- **WHEN** 用户 POST 端点，token 已失效
- **THEN** 响应 403
- **AND** 响应顶层 `code == "40300"`
- **AND** 响应 `data.code == "weops_token_invalid"`

#### Scenario: base_url 格式错误返回 400

- **WHEN** 用户 POST 端点，base_url 缺 scheme
- **THEN** 响应 400

### Requirement: runtime 端点 + 缓存 stale fallback

系统 MUST 提供 `GET /api/network_topology/<id>/runtime/` 端点拉取运行态聚合结果。

#### Scenario: 拉取 fresh 成功

- **WHEN** WeOps 可用
- **THEN** 响应 200
- **AND** 响应 `data.nodes` 是按最深阈值命中颜色聚合的节点列表
- **AND** 响应 `data.links` 是按 `oper_status_down_only` 聚合的连线状态
- **AND** 响应 `data.stale == false`（或缺失）

#### Scenario: WeOps 不可用时 stale fallback

- **WHEN** WeOps 抛 `weops_unavailable`
- **AND** 画布有 fresh 缓存（60s TTL 内）
- **THEN** 响应 200
- **AND** 响应 `data.stale == true`
- **AND** 响应 `data` 是上次缓存内容
- **AND** 响应 `data.errors[0].code == "weops_unavailable"`

#### Scenario: WeOps 不可用且无缓存返回 502

- **WHEN** WeOps 抛 `weops_unavailable`
- **AND** 画布无 fresh 缓存（TTL 过期或从未缓存）
- **THEN** 响应 502
- **AND** 响应 `result == false`
- **AND** 响应 `data.stale == false`
- **AND** 响应 `data` 不包含 `nodes` 字段

#### Scenario: Token 失效时也走 stale fallback

- **WHEN** WeOps 抛 `weops_token_invalid` (401/403)
- **AND** 画布有 fresh 缓存
- **THEN** 响应 200
- **AND** 响应 `data.stale == true`
- **AND** 响应 `data.errors[0].code == "weops_token_invalid"`

### Requirement: 节点颜色聚合

系统 MUST 按"最深阈值命中"为节点外层颜色排序，平局按画布中 metric 位置优先。

#### Scenario: 单 metric 基线（value 低于所有阈值）

- **WHEN** metric 只有一个 threshold `[{value: 0, color: "#22c55e"}]`
- **AND** runtime value = -1
- **THEN** 节点外层颜色为 `#22c55e`（baseline）

#### Scenario: 多 metric 平局

- **WHEN** 节点有两个 metric，都命中各自的第一个 threshold（level=0）
- **THEN** 取画布中位置靠前的 metric 的 color

#### Scenario: 全部无数据

- **WHEN** 节点 metrics 全部无 runtime value
- **THEN** `resolve_node_outer_color` 返回 `None`
- **AND** 前端用 `NODE_OUTER_COLOR_UNKNOWN = "#64748b"` 兜底

#### Scenario: NaN / 字符串值

- **WHEN** runtime value 是 `NaN` 或字符串
- **THEN** 该 metric 不参与聚合

### Requirement: 连线状态聚合 (oper_status_down_only)

#### Scenario: 任一 down → critical

- **WHEN** link 的任一接口 `oper_status == "down"`
- **THEN** 状态 = `"critical"`，原因 = `"interface_down"`

#### Scenario: 全部 up 且 status=ok → normal

- **WHEN** 所有接口 `oper_status == "up"` 且 `status == "ok"`
- **THEN** 状态 = `"normal"`，原因 = `"all_interface_up"`

#### Scenario: 含 testing / unknown / 缺数据

- **WHEN** 接口有 `unknown` / `testing` 状态或缺数据
- **THEN** 状态 = `"unknown"`，原因 = `"interface_unknown"`（不降到 critical）

#### Scenario: 无接口项

- **WHEN** link 没有任何接口 runtime 项
- **THEN** 状态 = `"unknown"`，原因 = `"no_interface"`

### Requirement: WeOps 适配器

#### Scenario: 16 种 error_code 全部映射

- **WHEN** WeOps 在 `data.items[].error_code` 中返回已知 code（如 `metric_not_found`、`status_query_failed` 等）
- **THEN** 适配器把它映射到对应的 `NetworkTopologyErrorType` 枚举值
- **WHEN** 返回未知 code
- **THEN** 映射到 `NetworkTopologyErrorType.UNKNOWN`

#### Scenario: 401/403 → weops_token_invalid

- **WHEN** WeOps 响应 HTTP 401 或 403
- **THEN** 适配器抛 `WeOpsTopologyAdapterError(code="weops_token_invalid", status_code=401/403)`

#### Scenario: node_ref URL 编码

- **WHEN** 调用 `adapter.get_node({"bk_obj_id": "bk_switch", "bk_inst_id": 10001})`
- **THEN** URL 路径中 `node_ref` 是 base64-url-safe 编码的字符串

#### Scenario: 全量拉 nodes 用 page_size=1000

- **WHEN** 调用 `adapter.list_nodes()`
- **THEN** HTTP 请求 query 包含 `page_size=1000`

### Requirement: 视图层错误转换

#### Scenario: view_sets 校验失败返回 400

- **WHEN** `PUT /config/` body 包含非法 view_sets
- **THEN** 响应 400
- **AND** 响应 message 或 data 中包含具体错误描述（如 "ghost"、"端口" 等关键词）

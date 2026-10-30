# CMDB 关联模型属性筛选

Status: implemented

完成证据：`apps/cmdb/tests/test_advanced_filter.py`、`apps/cmdb/tests/test_advanced_filter_api.py`（含 FalkorDB 写入后查询）、`web` 的 `advancedFilter.test.ts`、`advancedFilterDrawer.test.tsx`、`ExportSubmission.test.tsx`。未提交。

## Problem Statement

CMDB 实例列表只能按当前模型自身属性筛选（`MATCH (n:instance) WHERE n.xxx`）。运维常见问题的条件落在关联对象上：「运行在 Linux 主机上的 MySQL」（条件属于主机）、「运行在生产集群主机上的 MySQL」（条件属于两跳外的集群）。当前只能逐个打开实例看关联或拓扑。应用资源概览虽能展开周边资源，但它是从单个中心实例逐节点 BFS（N+1 次查询），不支持按属性筛选、分页和计数，不能当查询能力用。

## Solution

在所有模型的实例列表上增加「高级筛选」右侧抽屉。每个条件 = 关联路径（当前模型 / 一跳 / 两跳）+ 路径终点模型的属性 + 运算符 + 值；一个条件组内多个条件统一用 AND 或 OR。后端把条件组编译成一条参数化 Cypher，结果始终是当前模型实例、不重复，沿用现有分页、排序、权限；未勾选实例时导出当前筛选结果。筛选方案可保存复用，扩展现有 `cmdb_saved_filters`。

## User Stories

1. As an 运维人员, I want 在 MySQL 列表筛选「运行于主机.操作系统 = Linux」, so that 直接得到运行在 Linux 主机上的 MySQL
2. As an 运维人员, I want 筛选「运行于主机 > 所属集群.环境 = 生产」, so that 得到生产集群下的 MySQL
3. As an 运维人员, I want 当前模型与另一模型之间有多种关系时（如运行于主机、关联主机）能分别选择, so that 不同关系语义不混淆
4. As an 运维人员, I want 把数据库版本、操作系统、集群环境多个条件按 AND 或 OR 组合, so that 一次表达完整的筛选意图
5. As an 运维人员, I want 一个 MySQL 关联多台主机、多台命中时只出现一次且总数准确, so that 列表、分页可信
6. As an 运维人员, I want 应用后在列表上方看到生效条件并能单独移除或一键清空, so that 随时知道列表被什么过滤
7. As an 运维人员, I want 保存常用筛选方案并一键恢复, so that 不必每次重建条件
8. As an 运维人员, I want 高级筛选与原有快速搜索同时生效, so that 不影响现有使用习惯
9. As an 运维人员, I want 不勾选实例时导出当前筛选结果, so that 导出内容与列表所见一致

## Implementation Decisions

### 筛选语义

- 结果始终是当前模型实例；同一实例经多条路径、多个关联对象命中只返回一次，计数按去重后的实例。
- 关联条件是「存在」语义：存在一个沿该路径可达、且满足条件的关联对象即命中。
- AND 模式下，路径前缀相同的条件绑定同一个关联对象：
  - 完整路径相同：由同一个关联对象满足。例：「运行于主机.OS = Linux」AND「运行于主机.IP 包含 10.11」要求是同一台主机。
  - 第一跳相同：共用同一个中间对象。例：「运行于主机.OS = Linux」AND「运行于主机 > 所属集群.环境 = 生产」要求同一台主机既是 Linux、又属于生产集群。
  - 第一跳不同（如「运行于主机」与「关联主机」）的条件相互独立。
- OR 模式下不存在绑定问题：「存在对象满足 A」或「存在对象满足 B」与「存在对象满足 A 或 B」等价。
- 没有该路径关联对象的实例不命中该路径上的任何条件，包括否定类运算符和「为空」。否定类同样是存在语义：MySQL 关联 Linux 与 Windows 两台主机，「操作系统 不等于 Linux」命中（存在 Windows 主机）。
- 条件组内统一 AND 或 OR，不支持嵌套分组。高级筛选与快速搜索栏的条件之间恒为 AND。

### 请求结构

`instance/search` 增加可选参数 `advanced_filter`，现有 `query_list` 不变：

```json
{
  "model_id": "mysql",
  "query_list": [],
  "advanced_filter": {
    "logic": "AND",
    "conditions": [
      {"path": [], "field": "db_version", "type": "str*", "value": "8.0"},
      {"path": ["mysql_run_host"], "field": "os_type", "type": "str=", "value": "linux"},
      {"path": ["mysql_run_host", "host_belong_cluster"], "field": "env", "type": "list_any[]", "value": ["prod"]}
    ]
  }
}
```

- `path` 为 `model_asst_id` 链，长度 0–2；空数组表示当前模型。字段名以实际模型属性为准，上例仅示意。
- 校验（失败返回 400 并指明第几个条件）：
  - 每个 `model_asst_id` 存在于模型关联定义。
  - 第一跳一端是当前模型，第二跳一端是第一跳的对端模型；终点模型由路径推导。
  - 第二跳不得与第一跳是同一 `model_asst_id`（原路返回）。
  - 路径上的模型对当前用户可见（`BusinessModelVisibility`）。
  - `field` 是终点模型的可筛选属性，`type` 与属性类型匹配。
  - 条件数不超过 10，防止查询失控。
- 同一端模型的多种关系靠 `model_asst_id` 区分，不按模型去重。

### 编译策略

不依赖 `EXISTS {}` 子查询（仓库内未使用，需同时兼容 FalkorDB `falkordb==1.2.0` 客户端对应服务端与 Neo4j 5），按逻辑分两种模板。

AND：条件按路径组织成前缀树：第一跳相同的条件共用一个中间节点，完整路径相同的条件合并到同一个终点节点的 `WHERE`。每棵子树一组 `MATCH`，组间 `WITH DISTINCT n` 逐步收敛：

```cypher
MATCH (n:instance) WHERE n.model_id = $m AND <n 权限> AND <快速搜索> AND <当前模型条件>
// 「运行于主机」子树：h 上有一跳条件，同时作为两跳条件的中间节点
MATCH (n)-[r1]-(h:instance) WHERE r1.model_asst_id = $a1 AND h.model_id = $hm AND <h 条件> AND <h 权限>
MATCH (h)-[r2]-(c:instance) WHERE r2.model_asst_id = $a2 AND c.model_id = $cm AND <c 条件> AND <c 权限>
WITH DISTINCT n
// 第一跳不同的另一棵子树
MATCH (n)-[r3]-(x:instance) WHERE r3.model_asst_id = $a3 AND ... 
WITH DISTINCT n
RETURN n ORDER BY ... SKIP $skip LIMIT $limit
```

同一中间节点下有多个不同的第二跳时，各自从同一个 `h` 再 `MATCH`。`h` 上没有一跳条件时只做中转，不加 `<h 条件>` 和 `<h 权限>`。

OR：条件按完整路径分组（OR 下绑定没有意义），每组一个 `OPTIONAL MATCH`，聚合为布尔标记，最后统一判断：

```cypher
MATCH (n:instance) WHERE n.model_id = $m AND <n 权限> AND <快速搜索>
OPTIONAL MATCH (n)-[r1]-(h:instance) WHERE r1.model_asst_id = $a1 AND h.model_id = $hm AND <h 条件> AND <h 权限>
WITH n, count(h) > 0 AS c1
OPTIONAL MATCH (n)-[r2]-(:instance)-[r3]-(c:instance) WHERE ... AND <c 条件> AND <c 权限>
WITH n, c1, count(c) > 0 AS c2
WHERE (<当前模型条件>) OR c1 OR c2
RETURN n ORDER BY ... SKIP $skip LIMIT $limit
```

- 计数用同一模板截至最后的 `WHERE`，`RETURN count(n)`。
- 编译结果作为图层统一入口（如 `query_entity` 增加 `advanced_filter` 参数或新增同签名方法），支持 `params`（含导出游标）、权限、排序、分页、`fields` 投影和 `include_count`，供列表和导出共用。
- 边一律无向匹配并约束 `model_asst_id`：它已编码两端模型与方向，两端为同一模型的自关联也成立。
- OR 模式下同一路径组内的条件在该节点 `WHERE` 内用 OR 连接，与拆成多组结果等价。
- 全程参数化；`model_asst_id`、`model_id`、`field` 经 `CQLValidator` 校验，不拼接用户值。查询设超时（参照云成本查询的 `timeout` 用法），超时返回明确错误，不静默返回空。
- 不传 `advanced_filter` 时走原 `query_entity` 路径，行为不变。

### 运算符

| 属性类型 | 运算符 | 查询类型 |
|---|---|---|
| 文本 | 等于 / 不等于 / 包含 / 不包含 | `str=` / `str<>` / `str*` / 新增 `str!*` |
| 数字 | 等于 / 不等于 / 大于 / 小于 | `int=` / `int<>` / `int>` / `int<` |
| 枚举 | 等于 / 不等于 / 属于 | `list_any[]`（单值）/ `list_none[]` / `list_any[]`（多值） |
| 日期 | 早于 / 晚于 / 时间范围 | 新增 `time<` / `time>` / `time` |
| 通用 | 为空 / 不为空 | 新增 `empty` / `not_empty` |

- 「为空」= 属性不存在、`null`、空字符串或空列表；「不为空」取反。
- 用户、组织、标签、云区域沿用现有快速搜索的类型映射（`list[]`、`list_any[]` 等）。
- 新增类型同时补参数化与非参数化实现，FalkorDB / Neo4j 两端一致。

### 前置改造：条件格式化支持别名

- `graph/format_type.py` 当前硬编码 `n.`（29 处）。改为可传别名、默认 `n`，现有调用输出逐字不变。
- 组织/实例权限条件拼接同样支持别名，关联节点需要。
- 不复用 `convert_to_cypher_match` 中 `params_str.replace('n', rep_alias)` 的写法。

### 权限

- 当前模型实例 `n`：沿用 `instance/search` 现有权限条件。
- 带条件的关联节点：按其模型的权限规则（`format_user_groups_permissions(request, end_model_id)`）加组织 + 实例权限条件；用户看不到的对象不能作为命中依据，避免借筛选探测不可见对象的属性值。前缀绑定后，中间节点上如果也有一跳条件，同样适用此规则。
- 只起中转作用、自身没有条件的中间节点不校验实例权限。已接受的取舍：可能借此推断不可见中间对象的存在。

### 前端

- 实例列表顶部（快速搜索右侧）增加「高级筛选」按钮，打开右侧 AntD `Drawer`，按原型布局；不改现有列表布局。
- 条件卡片：
  - 关联路径用 `Cascader`：第一项「当前模型」，其后为一跳关系，展开为二跳关系。
  - 选项文案为「关系名 + 对端模型名」（如「运行于主机」「运行于主机 > 所属集群」）。
  - 数据来自现有 `model/{model_id}/association` 接口，二跳按需加载，支持搜索；不新增后端接口。
- 字段：终点模型属性列表，复用 `visibleSearchableFilterAttrs` 过滤规则。运算符按属性类型给出，值输入控件复用快速搜索的同类控件（枚举、用户、组织、时间等）。
- 条件组顶部 AND / OR 切换；底部「添加条件」；抽屉底部「重置」「保存筛选」「应用筛选」。
- 应用后，列表上方显示生效条件标签（如「运行于主机.操作系统 = Linux」），可单独移除或「清空全部」，移除后立即重新查询。
- 布局与颜色遵守 Web UI 硬约束：Tailwind + 语义 token，不新建 SCSS Module。

### 保存筛选方案

- 扩展现有用户配置 `cmdb_saved_filters`（按模型存放），`SavedFilterItem` 增加可选字段 `advanced_filter`（结构同请求）；旧方案没有该字段，行为不变。
- 恢复方案时同时恢复快速搜索条件与高级筛选。
- 方案中的路径或字段失效（模型关联或属性被删除）时，应用接口返回 400 指明失效条件；前端在抽屉中标记失效条件，由用户删除后再应用，不静默丢弃。

### 列表操作

- 分页、排序与现有列表一致，排序作用于当前模型字段。
- 导出：
  - 勾选了实例（`inst_uuids` 非空）：按勾选导出，忽略筛选条件，与现有行为一致。
  - 未勾选：导出当前列表的筛选结果，即快速搜索 `query_list` 加 `advanced_filter`。两者都为空时等同现有的全量导出。注意，这会让「导出全部」开始带上快速搜索条件，是有意的行为变更，使导出与列表所见一致。
  - 同步导出（`instance/{model_id}/inst_export`）与异步导出任务（`transfer_execution.export`）都接收这两个参数，传入 `InstanceManage.inst_export`，复用编译入口。现有按 `inst_uuid` 游标分批（`str>` 游标、`ORDER BY inst_uuid`）和 10 万行上限不变。
  - 异步任务把筛选条件存入 `task.params`，执行时重新校验路径、字段并按执行时权限计算。条件失效时任务以明确错误失败，不导出全量。

## Testing Decisions

- 单元：
  - `format_type` 别名：默认 `n` 输出与改造前逐字一致；传入别名后各操作符正确。新增 `str!*`、`time<`、`time>`、`empty`、`not_empty` 的参数化输出正确。
  - 路径校验：合法 0/1/2 跳通过；不存在的 `model_asst_id`、断链、超过 2 跳、原路返回、不可见模型、非法字段、超过 10 个条件均返回 400 并指明条件序号。
  - 编译：AND/OR 两种模板生成预期 Cypher 与参数。AND 下完整路径相同的条件合并到同一节点，第一跳相同的条件共用中间节点，第一跳不同的条件各成一组。带条件的节点有权限条件，纯中转节点没有。
  - 不传 `advanced_filter` 时 `instance_list` 调用与改造前一致。
- 集成（FalkorDB 真实图，对应验收场景）：
  - 当前模型条件：数据库版本包含 8.0，只返回对应 MySQL。
  - 一跳：MySQL-A 运行于 Linux 主机，MySQL-B 运行于 Windows 主机，筛 OS = Linux 只返回 A。
  - 两跳：主机属于生产集群 / 测试集群，筛集群环境 = 生产，只返回生产链路上的 MySQL。
  - 多关联去重：一个 MySQL 关联两台 Linux 主机，结果出现一次，计数为 1。
  - 同对象约束：MySQL 关联主机 X（Linux, 10.0.0.1）与主机 Y（Windows, 10.11.0.1），AND「OS = Linux」「IP 包含 10.11」不命中。
  - 前缀绑定：MySQL 运行于主机 X（Linux，属于测试集群）与主机 Y（Windows，属于生产集群）。AND「运行于主机.OS = Linux」「运行于主机 > 所属集群.环境 = 生产」不命中，改为 OR 则命中。
  - 第一跳不同时独立：「运行于主机.OS = Linux」AND「关联主机.OS = Windows」可由两台不同主机分别满足。
  - 无关联对象：没有主机的 MySQL 不命中「OS 不等于 Linux」与「OS 为空」。
  - AND / OR 组合三类条件结果正确；OR 模式下仅满足当前模型条件的实例也命中。
  - 权限：关联主机不可见时不作为命中依据；两跳中间主机不可见、集群可见时仍命中。
  - 分页与计数在去重后一致。
  - 导出：未勾选时同步导出与异步任务的行数、内容与列表筛选结果一致，跨多个游标批次也不重复、不遗漏；勾选时忽略筛选条件；两种条件都为空时与现有全量导出一致；异步任务执行时条件失效则失败，不导出全量。
- 前端：路径 Cascader 区分同一端模型的不同关系；生效条件标签移除后重新查询；保存方案后恢复出相同的请求体；失效条件被标记。
- Prior art：`test_falkordb_client.py`、`test_falkordb_graph_real_extra.py`、`test_application_resource_overview_service.py`、`assetData/list/searchFilter.tsx` 的保存筛选逻辑。

## Out of Scope

- 三层及以上关联筛选
- 条件组嵌套、组间 AND/OR 混合
- 「关联对象字段」「引用属性」：把关联关系定义为模型字段、把关联模型属性配置为当前模型常驻属性或列表列
- 结果中展示关联路径或关联对象信息
- 编辑关联模型属性
- 纯中转中间节点的实例权限校验
- LLM / NATS `search_instances` 接入

## Further Notes

- 原型中的关系名仅为示意。实际以模型关联定义为准，例如 MySQL 与主机是 `mysql_run_host`（运行于），应用与主机是 `application_run_host`，不要假设「属于」。
- `OPTIONAL MATCH ... WHERE` + `count()` 聚合在 FalkorDB 部署版本上的语义需由集成测试锁定；如部署版本已支持模式谓词或 `EXISTS {}`，可在不改接口的前提下替换编译模板。
- 需在 FalkorDB 上确认 `model_id` 及常用过滤字段有索引。OR 模式需扫描当前模型全部可见实例再做可选匹配，大模型（数万实例）需在验收环境压测。

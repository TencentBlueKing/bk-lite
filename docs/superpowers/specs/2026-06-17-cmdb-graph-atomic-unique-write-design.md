# CMDB 图库实例写入：约束兜底 + 原子写 设计

- 日期：2026-06-17
- 状态：设计已确认，待写实现计划
- 关联代码：`server/apps/cmdb/graph/falkordb.py`、`server/apps/cmdb/services/instance.py`、`server/apps/cmdb/services/unique_rule.py`、`server/apps/cmdb/collection/common.py`、`server/apps/cmdb/utils/Import.py`、`server/apps/cmdb/services/model.py`

## 背景与问题

CMDB 所有实例写入路径（手动建实例 `instance_create`、改实例 `instance_update` / `batch_instance_update`、自动采集 `add_inst` / `update_inst`、批量导入 `Import`）共用同一模式：

```python
exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])  # 读该模型全部实例进内存
result = ag.create_entity(INSTANCE, instance_info, check_attr_map, exist_items, ...)                      # 内存里 for 循环比对
```

唯一性 / 去重判断（`falkordb.py::check_unique_attr`、`unique_rule.py::collect_unique_rule_conflicts`）全部是 Python 内存遍历 `exist_items`。当前 FalkorDB（客户端 1.2.0）**没有任何 DB 层唯一约束 / 索引 / MERGE**。

### 确认的问题（按严重度）

1. **竞态 / TOCTOU（正确性，最严重）**：「读全量 → 内存比对 → 写入」三步非原子且横跨两条独立查询。两个并发请求建同一唯一值实例，都读到「无冲突」，都写入 → 图库产生重复数据，且无 DB 约束兜底，破坏后无法自愈。生产已确认存在自动采集 + 手动并发。
2. **全量读取进内存（性能/内存）**：每次单条 create/update 都把整个模型的所有实例拉进内存。模型 10 万实例时建 1 条要先传 10 万节点，O(N) 内存 + O(N) 网络。
3. **批量写入 O(N²)（性能）**：`batch_create_entity` / `add_inst` 循环里 `exist_items.append(entity)` 后每条重扫整个列表。
4. **快照漂移（一致性）**：`exist_items` 是写入开始时的快照，批处理期间库可能被别的进程改动。

## 决定性技术事实（已核实）

- **FalkorDB 串行化所有写查询**（[官方并发文档](https://docs.falkordb.com/design/concurrency.html)）：同一 graph 的写查询 FIFO 一次执行一条；单条写原子，约束冲突整条回滚。
  - 推论：单条写串行原子，但本问题竞态横跨「读 + 写」两条查询，中间有 Python gap，别的写能插入。**无论加多细的应用层锁都关不死跨查询竞态；DB 唯一约束是唯一硬保证**——并发第二个写会因约束冲突被原子回滚。
- **FalkorDB 唯一约束语义**（[GRAPH.CONSTRAINT CREATE 文档](https://docs.falkordb.com/commands/graph.constraint-create.html)、[Issue #664](https://github.com/FalkorDB/FalkorDB/issues/664)）：
  - 支持复合唯一约束（多属性组合唯一）。
  - **仅当所有受约束属性非 NULL 时才强制**；缺失/NULL 属性的节点豁免。
  - 创建唯一约束**前必须先有同属性的 exact-match（range）索引**，否则失败。
  - 若存量数据已违反约束，约束状态置 **FAILED 且不生效**，需先清理冲突数据再重建。
- **客户端 1.2.0 API 齐全**：`create_node_range_index(label, *properties)`、`create_node_unique_constraint(label, *properties)`、`list_constraints()`、`drop_node_unique_constraint(label, *properties)`。

## 实测验证结论（2026-06-17，10.10.41.149:6479，临时图 `cmdb_constraint_probe*`，已删除）

在真实 FalkorDB 服务器上用 host 的真实约束形态实测，全部假设已验证：

| 验证项 | 结果 |
|---|---|
| 复合 unique 约束可建、状态 `OPERATIONAL` | ✅ |
| 重复被原子阻断 | ✅ 异常类 = **`redis.exceptions.ResponseError`**，消息 = `unique constraint violation on node of type instance` |
| `model_id` 入约束 → 按模型分区（不同 model_id 同值放行） | ✅ 成立 |
| NULL/缺失字段豁免（与 `_build_rule_signature` 跳过缺失语义一致） | ✅ 生效（两条都缺 `cloud` 不报冲突）|
| 完整字段复合 `(ip_addr, cloud)` 唯一阻断 | ✅ |
| 存量重复 → 约束置 `FAILED` 不生效 | ✅ 确认（佐证组件 ② 必要性）|

**关键修正（实测发现）**：FalkorDB 的 range index 是**按单属性**的，`create_node_range_index('instance', a, b)` 等于分别建 a、b 两个单属性索引。`model_id` 被所有复合约束共享，**重复建会报 `Attribute 'model_id' is already indexed`**。因此组件 ① 必须**按单属性幂等建索引**（捕获 `already indexed` 跳过），再建复合 unique 约束引用这些属性。

**host 真实唯一性定义**（实测读取）→ 生成两个约束：
- `is_only: inst_name` → `unique(instance, [model_id, inst_name])`
- `unique_rule: [ip_addr, cloud]`（`ip_addr`/`cloud`/`inst_name` 均 required）→ `unique(instance, [model_id, ip_addr, cloud])`

**数据局面**：可达的 `cmdb_graph` 仅 7 个实例（host 为 0），第二台 `10.10.40.189:6379` 不可达 —— 无大规模真实数据，验证对象为约束机制本身而非数据量。

## 已确认的决策

- **修复范围**：彻底修——引入 DB 唯一约束 + 原子写，从根上消除全量读取与竞态。
- **并发现状**：生产真实存在自动采集 + 手动并发写同一模型，竞态是首要矛盾。
- **存量重复处理**：报告 + 提供半自动清理脚本（默认 dry-run，须显式确认才动数据）。
- **上线方式**：测试分支直接切换，不加 feature flag，靠测试 + 评审保质量。

## 架构总览

把 4 处写路径的 `exist_items = query_entity(全量)` + 内存比对，统一替换为「**定向索引查询（友好报错）+ DB 唯一约束（竞态硬保证）**」。

```
模型唯一性定义 (is_only / unique_rules)
        │  ① 约束同步服务（建 range index → 建 unique constraint）
        ▼
FalkorDB 唯一约束 (model_id, 字段...)  ←─ 竞态硬保证（串行写 + 原子回滚）
        ▲
        │  ③ 原子写路径：定向查询出友好提示，约束冲突翻译成 BaseAppException
写入 (create / update / 采集 / 导入)
        ▲
        │  ② 上线前：存量重复盘点报告 + 半自动清理脚本
```

## 组件 ①：约束同步服务（新增 `services/graph_constraints.py`）

职责：把模型的唯一性定义翻译成 FalkorDB 约束并维护其生命周期。

- 映射规则：
  - 单字段 `is_only` 属性 X → 约束 `unique(instance, [model_id, X])`
  - 复合 `unique_rule` 字段列表 [A, B, …] → 约束 `unique(instance, [model_id, A, B, …])`
  - model_id 入约束 + NULL 豁免 → 实现「按模型分区唯一」，且与现有 `_build_rule_signature`「字段缺失即跳过」语义一致。
- 建唯一约束前，先确保其每个受约束属性都有 range index（FalkorDB 硬性要求）。**实测修正**：range index 按单属性建且不可重复——对约束涉及的每个属性（`model_id` + 规则字段）调用 `create_node_range_index('instance', 单属性)` 并捕获 `Attribute '...' is already indexed` 跳过；不要用复合索引语法重复建共享的 `model_id`。
- 幂等：用 `list_constraints()` 判断约束已存在则跳过；约束冲突异常按 `redis.exceptions.ResponseError` + 消息 `unique constraint violation` 识别。
- 同步触发点（已扫码确认为单一汇聚点）：
  - 额外唯一规则增删改：`unique_rule.py::_apply_unique_rule_mutation`（create/update/delete 三入口全经此）在 `_save_unique_rules` 之后同步 DB 约束到 `next_rules`。
  - `is_only` 切换：`model.py::create_model_attr` / `update_model_attr`。
  - `model.py::delete_model`（drop 该模型相关约束）。
- 引导命令 `cmdb_provision_unique_constraints`：为全部存量模型幂等建约束。**建前先查重复，有冲突则跳过该约束并报告，绝不留 FAILED 约束。**

### 唯一规则语义支持核验（扫码确认）

模型的唯一性由三部分组成，约束设计逐条覆盖：

| 语义（前后端） | 约束映射 | 状态 |
| --- | --- | --- |
| `inst_name` 内置 is_only、始终生效、不可入额外规则 | `unique(instance,[model_id,inst_name])` | ✅ 实测 |
| 历史 `is_only` 字段（`legacy_unique_fields`，inst_name 之外） | `unique(instance,[model_id,X])` | ✅ |
| 额外复合规则 `[A,B,…]`（如 `内网IP+云区域`=`[ip_addr,cloud]`） | `unique(instance,[model_id,A,B,…])` | ✅ 实测 |
| 每模型最多 3 条 + inst_name + legacy（`UNIQUE_RULE_MAX_COUNT=3`） | ≤ ~5 约束/模型，单属性索引共享 model_id | ✅ 无索引膨胀 |
| 字段必须必填 | 约束非空时强制；缺失走 NULL 豁免 | ✅ 与 `_build_rule_signature` 一致 |
| 排除 enum/tag/bool/organization/display 字段（`UNIQUE_RULE_UNSUPPORTED_*`） | 多值/列表类型不进约束 | ✅ 规避列表属性约束 |
| 同字段不可跨规则、规则内不可重复 | 字段集互斥，约束属性集不冲突 | ✅ |

**利好**：`_apply_unique_rule_mutation` 在保存前已调 `_raise_conflict_if_rules_invalid` 做存量冲突校验，冲突即不保存 → 保存后建的约束数据必无冲突 → 必为 `OPERATIONAL`。**`FAILED` 风险只存在于组件 ② 的存量旧规则迁移，新规则编辑路径无此风险。**

**必须处理的语义差（空串 vs NULL）**：应用层 `_is_empty_unique_rule_value` 把 `""`/纯空格当空→跳过比对；DB 约束把 `""` 当真实值→会强制唯一。规则字段虽必填（`check_required_attr` 用 `not item.get(attr)` 拒空串）一般挡得住，但自动采集等路径可能绕过。为与应用层语义完全一致，**写入归一化时把唯一字段空值落成 NULL（不存 `""`）**，并加测试覆盖。

## 组件 ②：存量重复盘点 + 半自动清理（管理命令）

- `cmdb_report_unique_duplicates`：逐模型按 `is_only` + `unique_rules` 扫描冲突实例，输出报告（模型 / 命中规则 / 冲突实例 id + 名）。可复用 `unique_rule.py::validate_unique_rules_against_existing_instances`。
- `cmdb_cleanup_unique_duplicates`：半自动清理脚本，默认 `--dry-run`。策略如「保留最早或最新一条，其余打标/删除」。**必须 `--confirm` 才真正动数据**，且打印将要操作的实例清单。

## 组件 ③：原子写路径改造

- `check_unique_attr` / `check_unique_rules` 不再吃全量 `exist_items`：改为用候选实例的唯一值拼**定向查询**（`MATCH (n:instance) WHERE n.model_id=$m AND n.X=$v`，走 range index，O(log N)），只取匹配行（通常 0~1 条）跑现有比对逻辑 → 保留友好的「XX 已存在」报错。
- 移除 4 处写路径的 `query_entity(全量)` 调用。
- 写入捕获约束冲突 `ResponseError` → 翻译成 `BaseAppException`（兜底覆盖定向查询与写入之间的并发缝隙；这是竞态的最终硬保证）。
- 批量：N 次定向索引查询 + 批内内存去重（batch_map），消除 O(N²)。
- `check_required_attr`（必填校验）保持应用层不变（与竞态无关）。

## 测试策略（systematic-debugging RED → TDD GREEN）

测试对接**本地 FalkorDB**（按历史偏好用本地 docker 临时实例，不连 10.10.41.149 生产）。

### Phase 0 — 复现（先证明问题存在，预期失败/暴露缺陷）

- **竞态**：两线程并发建同一唯一值实例 → 现状两条都成功（产生重复）。
- **性能**：写入会全量加载该模型实例（断言加载规模随实例数增长）。
- **批量 O(N²)**：断言比对/扫描次数随批量平方增长。

### Phase 1+ — GREEN（实现后转绿）

- 建约束后并发建同一唯一值，只成功一条，另一条得到友好 `BaseAppException`。
- 写路径不再全量扫描（断言只发定向索引查询）。
- 批量写入比对次数随规模线性。
- 约束同步：模型加 is_only / unique_rule 后 `list_constraints()` 出现对应约束；删除后消失。
- 存量盘点命令在构造的重复数据上正确报告；清理脚本 dry-run 不动数据、`--confirm` 才动。

## 工程流程

- **worktree**：从当前分支拉隔离分支 `feature/cmdb-graph-atomic-unique`（using-git-worktrees）。
- **执行计划**：本设计经评审后用 writing-plans 拆分步骤，逐步实现（executing-plans）。
- **完成前**：verification-before-completion —— 跑全量 pytest + lint + 并发手测 + `list_constraints()` 核验，证据齐全才声明完成。

## 风险与缓解

- **存量重复导致约束 FAILED**：引导命令建前查重、有冲突即跳过并报告（组件 ②），不留 FAILED 约束。
- **直接切换无开关**：限定在测试分支；RED 复现 + GREEN 回归 + 代码评审三道关；保留旧 `format_*`/非参数化分支不删，降低回滚成本。
- **约束属性顺序 / 索引依赖**：index 与 constraint 属性顺序统一封装在组件 ①，单元测试覆盖。
- **NULL 豁免语义差异**：已确认与现有 `_build_rule_signature` 跳过缺失字段语义一致，测试显式覆盖「部分字段缺失不报冲突」。

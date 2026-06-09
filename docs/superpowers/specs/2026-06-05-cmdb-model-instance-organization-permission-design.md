# CMDB model / instance 对象权限组织归属修复设计

日期: 2026-06-05
范围: `server/apps/cmdb` 权限 helper 与权限回填链路，重点覆盖 issue #3038
目标: 修复 model / instance 对象级权限在按名称聚合后丢失组织归属校验的问题，阻断跨组织越权查看、操作和错误 permission 回填。

## 1. 背景与问题

当前 CMDB 的 model / instance 对象级权限依赖 `CmdbRulesFormatUtil` 做组织规则格式化和最终判定。现有实现为了支持“同一对象在多个组织下存在不同对象权限”的场景，会先把各组织的对象权限汇总成按 `model_id` / `inst_name` 索引的聚合表。

问题出在这一步聚合后的结果虽然保留了 `organization` 集合，但最终消费方没有再使用这个集合做约束：

1. `format_organizations_instances_map()` 会把多组织对象权限压平为聚合索引，并记录 `permission` 与 `organization`。
2. `has_object_permission()` 在命中 `model_id` 或 `inst_name` 后，只判断操作是否在 `permission` 内，不校验命中权限是否来自当前对象所属组织。
3. `InstanceViewSet.add_instance_permission()` 与 `ModelViewSet.model_add_permission()` 也会消费同一聚合索引，在前端 permission 回填时同样忽略组织来源。

这会导致用户在同时属于多个组织时，只要其中一个组织拥有某个模型或实例名的对象权限，就可能把该授权错误作用到其他组织下的同名实例或多组织挂载模型上，形成跨组织越权查看、越权操作，以及前端 permission 放大。

## 2. 目标与非目标

### 2.1 目标

1. 保持现有 `permission_instances_map` 的输入契约和主要调用链不变。
2. 修复 model / instance 对象权限的最终判定逻辑，要求命中名称级权限时必须校验授权组织与当前对象所属组织相交。
3. 修复实例与模型 permission 回填逻辑，禁止跨组织复用同名对象的权限结果。
4. 让详情、更新、删除、批量更新、关联写入等依赖该 helper 的链路自动受益。
5. 用最小改动完成安全闭环，不引入新的权限协议或大规模 helper 重构。

### 2.2 非目标

1. 本轮不改造 `format_user_groups_permissions()` 的返回结构。
2. 本轮不引入新的通用权限引擎或统一授权 DSL。
3. 本轮不调整组织级“全选”授权的现有业务语义。
4. 本轮不扩展到 model / instance 之外的其他 CMDB 权限模块。
5. 本轮不新增测试文件，只在现有测试文件中补回归覆盖。

## 3. 方案对比与选择

### 方案 A: 保留聚合索引，消费阶段补组织校验（推荐）

保留 `format_organizations_instances_map()` 的聚合思路，但把聚合结果中的 `organization` 集合变成最终判定和 permission 回填的硬约束。

优点:

1. 改动最小，兼容现有上游规则格式与下游调用方式。
2. 能同时修住“越权放行”和“permission 回填放大”两个问题。
3. 风险集中在 helper 与回填函数，回归面可控。

缺点:

1. 仍然保留“先聚合再消费”的间接层，语义不如按组织逐层判断直观。

### 方案 B: 最终判定完全按组织原始 map 遍历

不再依赖聚合索引做最终判断，而是在 `has_object_permission()` 等函数内部直接遍历 `permission_instances_map[organization]` 做组织级决策。

优点:

1. 判定过程最直观，天然避免聚合后丢失上下文。

缺点:

1. 需要同时重写 helper 判定和回填逻辑，触点更多。
2. 与当前大量调用方式耦合更深，不适合作为本次安全修复的最小闭环。

### 方案 C: 抽象新的统一组织权限解析器

新增统一 helper，把 model / instance 的对象权限判定与回填都迁移到新解析器。

优点:

1. 长期形态更整洁，职责边界更清晰。

缺点:

1. 明显超出本次 issue 的必要范围。
2. 重构面较大，安全修复上线成本更高。

最终选择: 方案 A。

## 4. 架构与职责边界

### 4.1 权限规则输入边界

`format_user_groups_permissions()` 继续负责从权限系统获取并组织当前用户可见组织下的对象权限规则。本次不修改其输出结构，仍保持：

```python
{
    team_id: {
        "permission_instances_map": {...},
        "inst_names": [...],
    }
}
```

这样可以避免向上游权限规则生成链路扩散改动。

### 4.2 聚合索引边界

`format_organizations_instances_map()` 继续负责把组织维度规则整理成便于消费的聚合索引，但其返回值不再被当作“已经可以直接放行的最终权限”，而是被视为：

1. 组织级全量授权索引；
2. 名称级对象授权索引；
3. 每条名称级授权对应的授权组织集合。

也就是说，**命中名称只代表“可能有权限”，最终是否放行仍取决于对象组织与授权组织是否相交。**

### 4.3 最终消费边界

以下三个函数是本次修复的核心收口点：

1. `CmdbRulesFormatUtil.has_object_permission()`：负责最终放行与拒绝。
2. `InstanceViewSet.add_instance_permission()`：负责实例详情/列表中的 permission 回填。
3. `ModelViewSet.model_add_permission()`：负责模型详情/列表中的 permission 回填。

三者都必须遵守相同原则：**只能消费来自当前对象所属组织的授权结果。**

## 5. 判定与回填设计

### 5.1 实例最终判定

`has_object_permission(obj_type="instances")` 调整为两段式判定：

1. 遍历 `instance["organization"]`，若某个组织直接命中组织级全量授权，则允许该组织对应的权限。
2. 若未命中组织级全量授权，再检查 `inst_name` 是否命中名称级授权。
3. 名称级命中后，必须确认 `set(instance["organization"])` 与该记录的 `organization` 集合有交集。
4. 只有在组织交集成立且目标操作在 `permission` 中时，才返回允许。

这意味着“同名实例”不再天然共享授权；只有**同名且同组织授权来源匹配**时，权限才成立。

### 5.2 模型最终判定

`has_object_permission(obj_type="model")` 调整为组织感知判定：

1. 对 `instance["group"]` 中的每个组织，优先检查是否命中组织级全量授权。
2. 若未命中，再检查 `model_id` 是否命中名称级授权。
3. 名称级命中后，必须确认 `set(instance["group"])` 与该记录的 `organization` 集合有交集。
4. 只有交集成立且目标操作在 `permission` 中，才允许对应模型操作。

### 5.3 默认组织可见性特例

当前 `default_group_id` 下对模型 `VIEW` 有特殊可见性语义。本次保留该特例，但边界收紧为：

1. 它只影响默认组织模型的 `VIEW` 判断。
2. 它不能让其他组织的名称级授权穿透到当前模型。
3. 它不能影响 `OPERATE` 判定。

这样既保留现有默认组织模型可见性，又不扩大越权面。

### 5.4 实例 permission 回填

`InstanceViewSet.add_instance_permission()` 继续允许“同一实例挂多个组织时合并这些组织的有效权限”，但合并范围仅限：

1. 当前实例所属组织直接命中的组织级全量授权；
2. 当前实例名命中的名称级授权，且该授权记录的 `organization` 集合与实例组织相交。

如果实例在组织 B 下没有对象级授权，即使组织 A 存在同名实例授权，也不能把 A 的权限回填给 B 的实例。

### 5.5 模型 permission 回填

`ModelViewSet.model_add_permission()` 同样只允许合并当前模型 `group` 内的有效权限来源：

1. 默认组织按现有规则补 `VIEW`；
2. 组织级全量授权只对命中的模型组织生效；
3. 名称级 `model_id` 授权只有在授权组织与模型 `group` 相交时才可回填。

这可以避免前端把其他组织对象权限错误展示为当前模型可操作。

## 6. 数据流与影响面

### 6.1 实例链路

本次修复后，以下链路会自动收敛到正确语义：

1. 实例详情 `retrieve`
2. 实例删除 `destroy`
3. 实例批量删除 / 批量更新
4. 实例关联创建等依赖 `check_instance_permission()` 或 `has_object_permission()` 的写接口

这些链路最终都依赖同一个 helper，因此只要 helper 和回填逻辑正确，详情与写操作都会一起收紧。

### 6.2 模型链路

以下模型链路会直接受益：

1. 模型详情 `get_model_info`
2. 模型更新 / 删除
3. 关联规则相关写接口
4. 前端模型列表与详情中的 permission 回填

### 6.3 兼容性

本次修复不会改变：

1. 用户所属组织的获取方式；
2. 权限规则来源；
3. 组织级全量授权的原有效果；
4. 详情和写接口的输入输出契约。

变化只体现在：**名称级对象权限不再跨组织串用。**

## 7. 测试设计

本次仅补现有测试文件中的回归覆盖，不新建测试文件。

### 7.1 `test_permission_util.py`

至少补充：

1. 同名实例存在于组织 A/B，仅 A 有名称级授权时，B 下实例 `has_object_permission()` 返回 `False`。
2. 模型挂载于组织 A/B，仅 A 有 `model_id` 名称级授权时，B 下模型 `OPERATE` 返回 `False`。
3. 当对象组织与授权组织相交时，现有正向权限仍返回 `True`。

### 7.2 `test_instance_views.py`

至少补充：

1. `add_instance_permission()` 在“跨组织同名实例”场景下不再错误回填权限。
2. 多组织实例在其所属组织都有授权时，仍可合并得到正确 permission 集合。

### 7.3 `test_misc_views.py`

至少补充：

1. 通过 mixin 调用 helper 时，跨组织名称级授权不会被误判为可访问。
2. 原有无组织交集拒绝路径不回归。

## 8. 验收标准

1. 用户属于多个组织时，其他组织下同名实例的对象权限不能借用到当前组织对象。
2. 多组织挂载模型只能消费其自身组织范围内的对象级授权。
3. 实例详情、模型详情、相关写接口在跨组织名称重合场景下正确返回拒绝。
4. 返回给前端的 `permission` 字段不再被其他组织权限放大。
5. 与当前对象组织相交的合法授权场景不回归。

## 9. 风险与缓解

1. 误伤当前“多组织同一对象合法合并权限”场景
- 缓解: 保留“对象所属组织内可合并权限”的语义，只阻断跨组织来源。

2. 默认组织可见性逻辑被误收紧
- 缓解: 保留 `default_group_id + VIEW` 特例，并在模型相关测试中单独回归。

3. 只修 helper 但遗漏回填路径
- 缓解: 将 `InstanceViewSet.add_instance_permission()` 和 `ModelViewSet.model_add_permission()` 明确纳入实施范围与测试范围。

## 10. 实施范围

建议仅修改以下位置：

1. `server/apps/cmdb/utils/permission_util.py`
2. `server/apps/cmdb/views/instance.py`
3. `server/apps/cmdb/views/model.py`
4. `server/apps/cmdb/tests/test_permission_util.py`
5. `server/apps/cmdb/tests/test_instance_views.py`
6. `server/apps/cmdb/tests/test_misc_views.py`

不扩展到其他权限体系、权限规则来源或新抽象层。

## 11. 自检结果

1. Placeholder 检查: 无 TBD/TODO 占位。
2. 一致性检查: 目标、职责边界、验收标准一致，均围绕“名称级对象权限必须受组织归属约束”展开。
3. 范围检查: 聚焦 `server/apps/cmdb` 的 helper 与回填路径，不扩展到权限系统整体重构。
4. 歧义检查: 已明确“组织级全量授权保留、名称级授权需校验组织相交、默认组织仅保留 VIEW 特例”的边界。

# CMDB 数据订阅：空过滤条件与实例生命周期

Status: done

## Completion

- 空过滤条件按规则所属组织查询全部实例；已填写条件不追加组织。
- 新增、修改、删除可单独勾选。当前实例集非空时，只勾新增或删除也会进入生命周期扫描。字段修改只在勾选修改时通知。空字符串和空值不写入新增、删除摘要。
- 旧规则若包含修改且缺少新增或删除，迁移 `0060_subscription_attribute_lifecycle` 会补齐。回滚不删除已经保存的类型。
- 验证：`server` 下 `pytest apps/cmdb/tests/test_subscription_serializer.py apps/cmdb/tests/test_subscription_trigger_service.py apps/cmdb/tests/test_subscription_task_service.py --nomigrations --create-db`，122 passed。SQLite 全量迁移仍被既有 `NewSessionEventRelation` 错误挡住，这次没有用迁移执行器跑 `0060`。
- 前端：`web` 下 `pnpm exec tsx scripts/cmdb-subscription-lifecycle-test.ts` 通过。没有可用的页面服务，表单点击路径没有在浏览器里走一遍。

## Problem Statement

数据订阅规则在「过滤条件」下不允许留空，用户无法直接订阅当前组织、当前模型的全部实例。属性变化把实例创建、字段修改和实例删除混成同一种通知，无法只订阅其中一种生命周期。

## Solution

过滤条件留空表示订阅规则所属组织下、目标模型的全部实例，表单把这个含义写在空状态里。属性变化拆成可独立勾选的新增、修改、删除，三者共用监听字段。修改仍按字段值变化触发；新增和删除按创建、删除记录触发，监听字段只出现在通知摘要里。已经只保存了「属性变化」的规则迁移后三种都保留，行为与现在一致。

## User Stories

1. As a CMDB 运维人员, I want an empty filter condition to subscribe every instance of the model in the rule organization, so that I do not have to add a dummy condition for the whole set.
2. As a CMDB 运维人员, I want the empty filter state to say that leaving conditions blank means all instances in the current organization, so that I know what will be subscribed.
3. As a CMDB 运维人员, I want to subscribe to instance create, field update, and instance delete separately, so that I only receive the lifecycle I care about.
4. As a CMDB 运维人员, I want create and delete notifications to include the watched field values, so that the message still identifies what changed without using those fields as a trigger gate.
5. As a CMDB 运维人员, I want an existing attribute-change rule to keep notifying on create, update, and delete until I edit it, so that the split does not silently drop notifications.
6. As a CMDB 运维人员, I want an instance that merely enters or leaves the filter because a field changed to be a modification, so that create and delete mean the instance was actually created or deleted.

## Implementation Decisions

- 过滤条件模式接受空 `query_list`。实例选择模式仍至少要有一个实例。条件最多仍是 8 个。
- 扫描时，过滤条件为空则查询 `{ field: organization, type: list[], value: [规则所属组织] }`，再由实例查询补上模型。已填写的条件保持原样，不额外补组织。
- 触发类型增加可保存的 `instance_added`（新增）和 `instance_deleted`（删除）。`attribute_change` 的界面文案改为「修改」。关联变化、临近到期、配置文件不变。
- 勾选新增、修改、删除中的任意一种时，共用一份 `attribute_change.fields`。三种都未勾选时不要求这份字段。字段仍不能为空。
- 新增：窗口内存在创建记录，且该实例当前落在订阅范围内。
- 修改：窗口内存在修改记录，监听字段前后值不同，且实例当前在范围内或上一次快照在范围内。同一实例的多次修改仍合并为一条修改事件。
- 删除：窗口内存在删除记录，且该实例在上一次快照的订阅范围内。当前结果集为空时仍要检测删除，不能因为查不到实例就跳过。
- 过滤条件造成的进出范围不单独发「进入/离开订阅范围」。没有创建记录的进入按修改处理；没有删除记录的离开按修改处理。
- 新增、删除通知摘要带上监听字段里实际有值的字段。修改摘要保持「字段: 旧值 → 新值」。
- 数据迁移：已保存且包含 `attribute_change`、尚未包含新增或删除类型的规则，补上缺失的那两种。迁移之后，只保存修改就只触发修改。
- 资产列表与实例详情使用的订阅表单，以及订阅抽屉表单，一起改空状态文案、空条件校验和三个生命周期选项。
- 通知标题里，修改从「属性变化」改为「修改」。新增、删除沿用现有「出现新增实例」「已删除」标题。

## Testing Decisions

- 后端行为从订阅规则序列化、触发检测和通知文案这三处对外结果验证，不断言私有查询拼装过程以外的内部结构。触发检测沿用现有订阅触发测试：真实规则与变更记录，只替掉模型和实例查询。
- 空过滤条件要看到发往实例查询的条件包含规则所属组织；已填写条件不追加组织。
- 生命周期要覆盖：创建只在勾选新增时通知；字段修改只在勾选修改时通知；删除只在勾选删除且实例曾在快照中时通知；过滤命中变化不是新增或删除；当前实例集为空时删除仍通知。
- 旧规则补齐三种类型用迁移里的纯转换函数验证，不把断言绑在迁移执行器上。
- 前端用同一份过滤与生命周期判断给两套表单共用，并用脚本锁定空条件合法、三种类型需要监听字段，以及中英文文案。
- 既有修改合并、到期、关联、配置文件用例保持通过。

## Out of Scope

- 已填写的过滤条件不自动补组织。
- 不追补规则保存前的历史变更。
- 不改关联变化、临近到期、配置文件的判定。
- 不调整通知聚合窗口和渠道投递。

## Further Notes

- 创建记录的全部字段看起来都「从空变成有值」，因此创建不能再走修改的字段差分，否则只勾选修改也会收到新建通知。

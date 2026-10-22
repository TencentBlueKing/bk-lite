# 02 — 规则级字段：触发/恢复周期、恢复阈值、告警名称（后端）

Status: ready

Blocked by: None

**What to build:** 修改规则接口在阈值之外接受可选的 `trigger_count`、`recovery_condition`、`recovery_threshold`、`alert_name`。检测语义字段变化时结束未恢复告警；只改告警名称不结束。规则序列化返回这些字段。

- [x] `update_rule` 接受可选字段，未传不动
- [x] 校验：`trigger_count`、`recovery_threshold` 复用单策略序列化器已有校验（`validate_trigger_count`、`validate_recovery_threshold`）；`recovery_condition` 按同样的正整数 ≥ 1 规则校验；`alert_name` 非空、不超过模型长度、变量占位符原样保存
- [x] 多条件规则传 `recovery_threshold` 被拒绝
- [x] 阈值、多条件阈值、`trigger_count`、`recovery_condition`、`recovery_threshold` 任一变化结束未恢复告警（原因 `policy_group_rule_changed`）；只改 `alert_name` 不结束
- [x] 规则序列化增加 `alert_name`、`trigger_count`、`recovery_condition`、`recovery_threshold`
- [x] 服务层测试覆盖：改触发周期结束告警、只改名称不结束、多条件拒绝恢复阈值、非法值拒绝、复制组带走这些字段

## Notes

- 不改 `MonitorPolicySerializer` 本身的行为；只复用它的校验方法，或把校验抽成可被两处调用的函数时保持原序列化器测试通过。
- 测试命令同 01。

## Completion evidence

- 与 01 同一条 pytest：116 passed，0 failed（4.38s），含 `test_policy_multi_group.py`。
- 覆盖：改 `trigger_count` 结束未恢复告警且其它字段不动；只改 `alert_name`（含占位符）不结束；改恢复周期和恢复阈值结束告警；多条件规则传 `recovery_threshold` 被拒绝；非法触发周期、恢复周期、名称被拒绝；复制组带走这些字段。

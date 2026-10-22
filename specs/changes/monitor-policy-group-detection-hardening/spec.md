# 策略组检测配置收口

Status: implemented — 2026-10-22 已实施。本机走查见 `local-verification.md` 结果。走查中补了一处：规则保存关闭告警必须包在事务里，否则 `select_for_update` 在自动提交下会失败，规则已改、告警仍是 new。

## Problem Statement

检测配置分层已经能保存，但有两处还不能按生产标准放出去。

检测配置抽屉只有一个保存动作，请求里同时带上检测频率和无数据。组内不一致时接口按约定返回空频率、以及 `enabled: false` 的无数据。页面把空频率填成 5 分钟，把无数据画成关闭。用户只想把频率写成同一套时，保存会把无数据一起关掉，并结束未恢复的无数据告警。

关闭无数据时只从 `enable_alerts` 里拿掉 `no_data`，承载规则上原来的窗口、级别和名称留着。两条承载规则原来的窗口不同，关掉之后一致性比较仍会判成不一致，列表徽标消不掉。

另外，`PolicyGroupRule.push_alert_center` 只在创建和复制时写入，扫描和通知都不读。接入时的「推送告警中心」已经收成通知方式。字段还在，会让以后的人以为组上还有一个独立开关。

全仓 `pnpm lint` 的 141 个问题不在本次文件里，分布在告警、CMDB、作业、运维分析、OpsPilot 等既有代码，其中还有另一项未提交改动。这次不改那些文件。

## Solution

保存检测配置时，频率和无数据分开提交。没被用户改过、且组内不一致的那一块不写入。关闭无数据时把承载规则收成同一份关闭状态，列表不再显示不一致。删掉策略组规则上的 `push_alert_center` 字段。

## User Stories

1. 作为运维，组内无数据不一致时，我只改检测频率并保存，无数据开关、窗口和正在响的无数据告警保持原样。
2. 作为运维，我在不一致的那一块亲自改过再保存，这一块才写成同一套；确认文案写明这次会写入哪一块，关闭无数据时写明会结束未恢复的无数据告警。
3. 作为运维，我关闭策略组的无数据告警后，刷新列表不再出现「无数据不一致」。
4. 作为运维，策略组上不再出现一个不生效的「推送告警中心」字段。通知方式里选了告警中心，告警仍会推送。

## Implementation Decisions

### 分开写入

- `update_detection` 继续允许只带 `schedule` 或只带 `no_data`。这次不改接口形状。
- 抽屉记录频率和无数据各自是否被用户改过。打开时按接口原值填表：一致就填真实值；不一致就不要把空频率填成 5 分钟，也不要把空无数据画成一次明确的关闭。不一致的控件旁保留「保存后会写成同一套」。
- 保存请求只包含「已经一致」或「这次被用户改过」的块。两块都不该写时，确认按钮不可用，不发请求。
- 确认文案按这次实际会改变的块生成。已经一致的块可以随请求重写，但不因此多说一句。只有这次把无数据从打开或不一致收成关闭时，才写明会结束未恢复的无数据告警。无数据本来就是关闭、只是随频率请求把 `{enabled: false}` 再写一遍时，确认文案不提无数据。
- 纯函数放在现有 `policyGroupDetection` 模块：根据草稿、初始值和两块是否一致，产出请求体和确认文案。补测试，锁住「不一致且未改的块不出现在请求里」。

### 关闭后必须一致

- 关闭无数据时，每条承载规则写成同一份：`enable_alerts` 不含 `no_data`，`no_data_period` 与 `no_data_recovery_period` 为空对象，`no_data_level` 与 `no_data_alert_name` 为空字符串。
- 非承载规则仍然去掉 `no_data`，结束其上未恢复的无数据告警并清空基准。不要求把非承载规则的窗口字段改成和承载规则一样；一致性只比较承载规则。
- 从关到开、或只改窗口的行为不变：只在开关从关到开时刷新基准；只改窗口不结束告警、不重建基准。
- 补一条服务测试：两条承载规则原先窗口不同，执行关闭后 `no_data_uniform` 为真，未恢复无数据告警结束，阈值告警仍是 new。

### 删除 push_alert_center

- 删除 `PolicyGroupRule.push_alert_center`。新迁移接在 monitor 应用当前最新迁移之后，只删这一列。
- 创建规则和复制规则不再写这个字段。服务测试里对它的断言删掉。
- 不改模板批量套用、用户习惯里的 `push_alert_center`。那是另一条链路，表示所选通知方式是否包含告警中心。
- 不改通知投递。告警中心是否推送仍由策略上的通知方式决定。

## Testing Decisions

- 服务测试看关闭后的字段、`no_data_uniform`、告警状态和基准行。前端纯函数测试看请求体里出现哪些块，以及确认文案。迁移后创建和复制策略组的现有测试仍通过。
- 改规则并关闭告警的测试用 `pytest.mark.django_db(transaction=True)`，跑在请求事务之外，锁住 `select_for_update` 必须由 `update_rule` 自己开事务。

命令：

- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/monitor/tests/test_policy_group_service.py apps/monitor/tests/test_global_write_action_permissions_views.py --nomigrations --no-cov -o addopts=`
- 迁移本身用本机 Postgres 跑一次 `migrate monitor`，确认只新增这一列删除。sqlite 单测继续 `--nomigrations`，不把迁移逻辑放进单测。
- `cd web && pnpm exec vitest run src/app/monitor/(pages)/event/policy-group/__tests__/policyGroupDetection.test.ts`
- 对本次改动的前端文件跑 eslint，并跑 `pnpm type-check`。

## Out of Scope

- 把全仓 `pnpm lint` 从 141 个既有问题修到零。这些问题不在策略组文件里。
- 改通知、处理人、生效开关的保存方式。
- 改单策略页、模板页，或模板批量套用里的告警中心开关。
- 允许在组里增删单条规则。

## Further Notes

本机走查放在 `specs/changes/monitor-policy-group-detection-config/local-verification.md`。收口完成后再走那份清单。走查之前不要对现网「Host默认告警」保存检测配置。

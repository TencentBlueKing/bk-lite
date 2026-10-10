# 01 — 创建策略组并完成成员加入与退出

Status: done

Blocked by: None

**What to build:** 能在当前组织、当前监控对象下从模板创建一套策略组。每条规则单独执行，只覆盖正在使用该规则所属采集插件的成员，默认不填写通知人，也不猜测通知方式。可以把实例加入或退出这一组；退出后采集还在，该实例在原规则上尚未恢复的告警结束。改模板不影响已建成的组，组内规则不出现在策略列表。

- [x] 从所选模板创建策略组，新组没有成员；模板按插件可区分，规则记住自己的插件
- [x] 一条规则一次执行只覆盖该插件下的当前成员，不为每台成员再拆一次执行
- [x] 新建规则不预填通知人，也不预填通知方式。通知方式和通知人在策略组上设置
- [x] 加入后实例只属于这一组；已在别的组时先离开原组
- [x] 退出后记为不自动入组，原规则上尚未恢复的告警结束，之后不再按原规则产生新告警
- [x] 实例刚加入且该指标从未上报时，不因无数据告警
- [x] 改模板不改变已建成的组；组内规则不出现在策略列表
- [x] 实例不属于当前组织时不能加入该组织的策略组
- [x] 测试覆盖插件覆盖范围、一实例一组、退出结束告警、模板断开、策略列表不出现组内规则

## Notes

- 成员状态只有这一处写入。后续自动加入、接入页和实例页都调用它，不再各写一套。
- 复用现有策略的调度、检测、告警和通知。组内一条规则对应一条策略，策略的实例范围等于该规则当前覆盖的成员。

## Completion evidence

- 6 passed：`DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true python -m pytest apps/monitor/tests/test_policy_group_service.py --nomigrations --no-cov -o addopts=`
- 本机 Postgres 5432 未启动；sqlite 全量 migrate 会撞上既有的 `NewSessionEventRelation.event`，因此用 `--nomigrations`。

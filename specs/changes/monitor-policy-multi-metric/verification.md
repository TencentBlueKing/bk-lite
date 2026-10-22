# 多指标条件验证记录

后端 Django 测试走本机 Postgres（`pytest.ini` 的 `env_files=.env`），并保留 `--reuse-db`。

## 切片 1 后端契约与判定

完成。

命令（`server/`）：

```bash
uv run pytest \
  apps/monitor/tests/test_formula_validator.py \
  apps/monitor/tests/test_formula_compiler.py \
  apps/monitor/tests/test_policy_query_compile.py \
  apps/monitor/tests/test_policy_calculate_service.py \
  apps/monitor/tests/test_policy_scan_alert_detector.py \
  apps/monitor/tests/test_formula_policy_scan.py \
  apps/monitor/tests/test_policy_dry_run.py \
  apps/monitor/tests/test_monitor_policy_serializer_validation.py \
  apps/monitor/tests/test_monitor_policy_serializer_calc_enrichment.py \
  apps/monitor/tests/test_policy_template_portability.py \
  apps/monitor/tests/test_policy_group_service.py \
  apps/monitor/tests/test_policy_scan_metric_query_service.py \
  apps/monitor/tests/test_policy_preview_service.py \
  apps/monitor/tests/test_formula_policy_preview.py \
  apps/monitor/tests/test_snapshot_recorder_service.py \
  apps/monitor/tests/test_alert_center_metric_key_service.py \
  apps/monitor/tests/test_multi_validator.py \
  apps/monitor/tests/test_policy_calculate_multi.py \
  apps/monitor/tests/test_monitor_policy_serializer_multi.py \
  apps/monitor/tests/test_policy_multi_compile.py \
  apps/monitor/tests/test_policy_multi_scan.py \
  --no-cov -q --override-ini='addopts=-q --reuse-db'
```

结果：397 passed。旧 `metric` / `pmq` / `formula` 套件与新的多指标契约、编译、判定、扫描测试一起通过。

基线失败（与本次无关，未改迁移）：

```bash
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest apps/monitor/tests/test_monitor_policy_serializer_validation.py::test_serializer_accepts_valid_formula_query_condition \
  --no-cov -q --override-ini='addopts=-q' -p no:cacheprovider
```

结果：ERROR。`DB_NAME=:memory:` 会被拼成文件路径，随后 migrate 在删除 `NewSessionEventRelation.event` 时失败：`django.core.exceptions.FieldDoesNotExist: NewSessionEventRelation has no field named 'event'`。后续 Django 测试改用本机 Postgres。

未覆盖：浏览器；全量 `apps/monitor/tests/` 以外的 app。

## 切片 2 试跑与预览

完成。

命令（`server/`）：`test_policy_multi_dry_run.py`、`test_policy_multi_preview.py`，以及既有 `test_policy_dry_run.py`、`test_policy_preview_service.py`、`test_formula_policy_preview.py`，同样带 `--no-cov --reuse-db`。

结果：多指标试跑与预览用例通过。预览 VM 失败时，异常文案仍会进入既有 `BaseAppException` ERROR；断言只要求响应正文哨兵不出现在日志里，且没有新的 INFO。修正断言后单测 `test_preview_vm_error_raises_without_logging_response_body` 通过。

未覆盖：真实 VictoriaMetrics。

## 切片 3 策略表单

完成代码与脚本验证。页面没有在浏览器里点过。

命令（`web/`）：

- `pnpm test:monitor-policy-formula-payload`：passed。两行且未传显式模式时保持 `metric`；`formula` / `multi` 必须显式传入。
- `pnpm type-check`：第一次失败于 `metricPreview.tsx` 的 `unknown[]` 不能赋给 `ChartDataItem[]`。补上类型断言后再次 `pnpm type-check` 通过（本机 Node v22.16.0，引擎声明要 24.x，只有警告）。
- `pnpm exec eslint` 覆盖本次改过的策略页、试跑弹窗、预览和文案相关文件：0 error。`alertConditionsForm.tsx` 里未使用的 `onCountPredicateChange` 解构已去掉。

未覆盖：登录后的策略新建、编辑回显、模式切换提示、试跑表和预览页签。`pnpm lint`（全仓 `eslint .`）未跑。

## 切片 4 策略组、模板、告警详情

完成代码与对应测试。页面没有在浏览器里点过。

命令：

```bash
# server/
uv run pytest apps/monitor/tests/test_policy_multi_group.py \
  apps/monitor/tests/test_policy_template_portability.py \
  apps/monitor/tests/test_policy_group_service.py \
  --no-cov -q --override-ini='addopts=-q --reuse-db'
# 51 passed；随后补了非 multi 拒绝用例
uv run pytest apps/monitor/tests/test_policy_multi_group.py \
  --no-cov -q --override-ini='addopts=-q --reuse-db'
# 6 passed
```

```bash
# web/
pnpm type-check
pnpm test:monitor-policy-formula-payload
pnpm test:monitor-alert-detail-snapshot
pnpm exec vitest run 'src/app/monitor/(pages)/integration/list/detail/configure/__tests__/policyGroupAccessNotes.test.ts'
```

结果：type-check 通过；快照脚本通过（旧 `raw_data.values` 仍优先，`seriesRef` 读对应条件，只有 series 时回退第一条）；接入页说明 5 passed。

未覆盖：策略组抽屉里改阈值、告警详情条件页签的真实点击。全仓 `pnpm lint` 未跑。

## 浏览器走查（本机 localhost:3000，Host / 10.10.41.149）

2026-10-21。已登录 admin。走查策略创建后已删除（id 173），列表不再显示。

| 步骤 | 结果 |
|---|---|
| 新建策略切到「多指标条件」 | 通过。两条常规条件、锚点、结果名称、添加条件；比较基准和恢复阈值不出现；组合方式只有「全部满足」 |
| 默认阈值 | 已改为与单指标一致的严重 / 错误 / 警告。复述级别与阶梯文案一致（警告起） |
| 筛选按钮和添加条件 | 行内筛选改为「添加筛选」，底部仍是「添加条件」 |
| 配置 CPU、内存、运行时长前置条件 | 通过。必须选「主机远程采集（SSH/WinRM）」。同名的「主机（Telegraf）」查询的是 `cpu_usage_idle` / `mem_used_percent` / `system_uptime`，这台机器实际序列是 `*_gauge`，试跑会是无数据 |
| 单位 | 指标单位如果是展示符号 `%`，保存会被拒「结果单位无效」。选择指标时只保留单位目录里的单位 id，需要时在条件下拉选 `percent (0-100)` |
| 试跑 10.10.41.149 | 通过。会触发、警告、原因「各条件级别一致」。CPU 19.7%、内存 67.6%、运行时长前置条件通过 |
| 预览 | 通过。a/b/c 页签各自画阈值线（CPU 90/70/10，内存 95/80/50）。页签标题改为当前条件 |
| 保存后再打开 | 通过。插件、三条条件、角色、单位、阈值和复述都回显。分组维度只剩 `instance_id` |
| 编辑时切回单指标 | 通过。提示「保存后该策略下未恢复的告警会结束」。没有保存这次切换 |
| 分组维度「+ 0 ...」 | 已去掉自适应折叠。之前这个占位会被写进 `group_by` |
| 策略组改条件阈值 | 见下方「补测」。默认组是单指标模板，没有改真实规则 |
| 告警详情条件页签 | 见下方「补测」。用页面内告警行打开详情抽屉 |

`pnpm test:monitor-policy-formula-payload` 通过。

## 补测（mock 页面 + Postgres）

2026-10-21。主机默认策略组「Host默认告警」有 23 条单指标模板规则，没有改它们。多指标规则只写在当前页面状态里，保存请求被拦在浏览器内，没有打到后端。

| 步骤 | 结果 |
|---|---|
| 策略组规则抽屉 | 通过。打开「走查多指标组 / CPU与内存双高」。a、b 是严重 / 错误 / 警告，初值 90/70/10 和 95/80/50；c 标成「前置条件」，初值 1 |
| 改阈值并确认 | 通过。警告改为 11、前置条件改为 2。确认框文案是「保存后按新阈值检测，并结束这条规则上 1 条未恢复告警。」提交体是 `condition_thresholds`，没有带策略级 `threshold`。成功提示「已修改当前规则，未恢复告警会结束」 |
| 告警详情条件页签 | 通过。详情抽屉有 `a CPU使用率`、`b 内存使用率`、`c 系统运行时长`。a 显示 CPU使用率（%）和严重90 / 错误70 / 警告10；b 显示内存使用率（%）和严重95 / 错误80 / 警告50；c 显示系统运行时长（s）和前置条件 1 |
| 第 6 条条件 | 通过。新建页切到多指标后连点「添加条件」，到 5 条后按钮禁用 |
| 全部改成前置条件再确认 | 通过。表单错误为「多指标条件至少需要一个常规条件」。没有保存 |
| 非锚点额外维度 | 这台新建页的分组下拉只有 `instance_id`，页面上加不出锚点外维度。校验由 `monitor-policy-formula-payload-test.ts` 锁定：`groupBy` 带 `mount` 时抛出「锚点外额外维度」 |

Postgres `--reuse-db`，4 passed：

```bash
uv run pytest \
  apps/monitor/tests/test_policy_multi_scan.py::test_missing_non_anchor_data_does_not_change_recovery_count \
  apps/monitor/tests/test_policy_multi_group.py::test_condition_thresholds_replace_queries_and_close_open_alerts \
  apps/monitor/tests/test_policy_multi_dry_run.py::test_dry_run_missing_condition_does_not_touch_active_alert \
  apps/monitor/tests/test_monitor_policy_view_helpers.py::TestConfigChangeReason::test_query_condition_changed \
  --no-cov -q --override-ini='addopts=-q --reuse-db'
```

- 非锚点无数据：扫描不产生新事件，原告警保持 `new`，`info_event_count` 不变。
- 试跑缺条件：结论 `missing_condition_data`，不改活动告警。
- 策略组只改 `condition_thresholds`：未恢复告警结束。
- `query_condition` 变化的关闭原因仍是现有的 `policy_query_condition_changed`。编辑页切回单指标时的提示上次已经点到，这次没有再保存出一条真实告警。

## 实现判断

- `ref` 限制为 Prometheus 标识符，保证 `${ref_value}` 是合法模板键。
- 非锚点 `group_by` 集合与锚点不同就发 `MULTI_DIMENSION_REUSE`，文案与公式维度复用警告相同。
- 策略级 `threshold`、`count_predicate`、`compare_value_kind` 在多指标保存时清空；比较模式非绝对、恢复阈值非空、trap、timeleft 则拒绝。
- 锚点 `group_by` 经现有身份键纠正后写回 `queries[0]`。字段校验和镜像各走一次，同一保存会打两次既有 WARNING。
- `query_comparison_metrics` 遇到 multi 直接拒绝，避免旧的单载荷查询被误用。试跑和预览按条件分别查。
- 缺条件数据的原因文案是「条件 {ref} 无数据」。前置条件失败优先于级别未命中。
- 预览响应保留第一条条件的顶层 `query` / `data` / 单位 / 阈值，并附加 `conditions[]`。
- `query_condition.type` 变化结束未恢复告警走现有策略保存路径，没有另做一条关闭链路。
- 快照 `raw_data.series` 只保留参与判定的时间点。多指标判定不产生 `hold_events`。
- 百分比展示单位是 `percent`，告警文案断言不含 `%`。

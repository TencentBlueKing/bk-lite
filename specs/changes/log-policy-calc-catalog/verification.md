# 验证记录：日志策略计算方式目录（第二批）

日期：2026-10-27。环境：macOS，Python 3.12.11，Node v22.16.0（`package.json` 要求 Node 24.x，仅引擎警告）。本机 Docker 底座（Postgres、VictoriaLogs 等）在跑，后端 uvicorn `https://127.0.0.1:8443 --reload`，前端 Next dev `http://localhost:3000`。

实施分三批，每批后端 / 前端各一笔提交，均只含 `server/apps/log/**` 与 `web/src/app/log/**`：

| 批次 | 后端 | 前端 |
|---|---|---|
| B1 条件模型 × 比较方式 × 对照、去重计数、分位数、字节速率、`count_delta` 归一 | `1215d99119` | `ba074cfa8f` |
| B2 占比、无数据告警 | `03c696af7a` | `7fa8e1cc4f` |
| B3 连续满足次数、告警详情按条件渲染 | `03536ea953` | `efdaae8a46` |

## 后端

工作目录 `server`。sqlite 环境变量：`DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true`，均加 `--no-cov --create-db --nomigrations`。

| 命令 | 结果 |
|---|---|
| `uv run pytest apps/log/tests/test_policy_condition_pure.py apps/log/tests/test_policy_scan_pure.py apps/log/tests/test_policy_alert_condition_validation.py apps/log/tests/test_alert_notice_format.py apps/log/tests/test_issue_4336_i18n.py apps/log/tests/test_policy_dry_run.py apps/log/tests/test_policy_scan_db.py --deselect "apps/log/tests/test_policy_scan_db.py::TestCreateEvents"`（B3 后） | **209 passed，24 deselected** |
| 同一组不 deselect（B1 / B2 后各跑一次） | 3 条 `TestCreateEvents` 并发用例 `database table is locked`，其余全过 |
| `uv run pytest apps/log/tests/test_policy_scan_db.py::TestCreateEvents --no-cov --create-db --nomigrations`（本机 Postgres，不带 `DB_ENGINE`） | **24 passed**（B1 后整类一次通过；B3 后整类建库冲突 `test_bklite already exists` 报 3 errors，这 3 条单独重跑 3 passed） |

sqlite 的失败是线程并发写内存库的锁等待，与 `specs/changes/log-policy-calc-methods/verification.md` 记录的同一现象；Postgres 下全部通过，没有改并发写路径。

## 前端

工作目录 `web`。

| 命令 | 结果 |
|---|---|
| `pnpm exec vitest run` 相关文件（`policyFormUtils`、`conditionSelector`、`alertConditionsForm`、`dryRunResultModal`、`aggregateConditionHit`、`AlertRawLogWidget`、`logPolicyCalcMethods.i18n` 等） | B1 17 passed；B2 21 passed；B3 31 passed |
| `pnpm exec eslint <改动文件>` | 通过 |
| `pnpm type-check`（每笔前端提交钩子内也跑一次） | 通过 |
| `pnpm test:log-policy-form` | 通过 |
| `pnpm test:log-alert-raw-columns` | **失败，基线问题**。在今日改动之前的提交 `4bcbc6b18d` 上用临时 worktree 重跑同样失败（期望 `_msg`、实际 `message`），本批未改 `rawLogColumns.ts` 与该脚本。 |

## LogsQL 与现网试算（VictoriaLogs `http://127.0.0.1:9428`，策略查询 `*` 按 `host_name` 分组，窗口 15 分钟）

| 场景 | 结果 |
|---|---|
| `stats by (host) count_uniq(host) limit 1000000, quantile(0.95, duration), sum_len(_msg)` 直接查 VL | 接受；`duration` 非数值时分位列省略 |
| `count() if ((_msg:ERR)) as hit, count() as total` 直接查 VL | `{"hit":"611","total":"8886"}` |
| 不存在的主机 `stats count() as count__msg` | 返回一行 `{"count__msg":"0"}`，不是空列表（无分组无数据据此实现） |
| 试算：`count` 变化率对照上一窗 + `count_uniq(host_name) > 0` + 旧 `count_delta` | `(8925−9160)/9160×100 = −2.57%`；`count_uniq = 1`；`count_delta` 归一为 `count + delta`，`value = −235`；只查一次对照 |
| 试算：`count` 变化率对照 `offset_24h` + `quantile(0.95, _msg)` + `bytes_rate` | 对照窗 `[start−86400, end−86400)`，`baseline_status = ok`；分位非数值 `reason = not_numeric` 不成立；`bytes_rate ≈ 1559.6 字节/秒` |
| 试算：`ratio(message:ERR) > 1` | `612 / 8925 ≈ 6.86%`，`would_trigger` |
| 试算：不存在的主机 + 无数据开关 | 条件行 `no_trigger`，另有一行 `would_trigger_no_data`，`previous_count = 0` |
| 试算：`count > 1` 且 `ratio > 1`，`trigger_count = 3` | `streak = 3`，`would_trigger`；`count > 10000000` 时 `streak = 0`，`no_trigger` |

## 浏览器走查（`http://localhost:3000/log/event/strategy/detail?type=add&alert_type=aggregate`）

- 函数下拉双语显示 10 个函数（计数（COUNT）… 占比（RATIO）、字节速率（BYTES_RATE））。
- 选「变化率」后出现「对照」下拉（上一窗 / 1 小时前 / 24 小时前 / 7 天前），阈值后缀 `%`，行下提示「对照为 0 时不判定」。
- 选「占比」后出现分子筛选输入与提示「分母是上方查询条件，分母为 0 不判定」。
- 「无数据告警」开关打开后出现级别单选（严重 / 错误 / 警告）。
- 「连续满足次数」`InputNumber` 1..5，缺省 1，提示「连续 N 个检测窗都满足才告警」。
- 第一批修正过的条件行布局（行内固定宽度 + flex）在新增控件后仍为单行，超宽自动换行。

## 与规格的偏差（已接受）

- 扫描文件沿用既有 logger（第一批测试锁定），新 WARNING 模板 `event=log_policy_baseline_failed … compare_to=%s`、`event=log_policy_streak_failed … window_index=%s`，不含查询正文。
- 分位行同时显示字段下拉与分位下拉（`field` 必填）。
- 多个对照时段时 `aggregate_result.baseline` 只带 `status / values`，单一时段才带 `to / window`。
- 无数据级别单选复用现有三档（严重 / 错误 / 警告），后端仍接受 `info`。
- 无分组无数据按 VL 现网返回「一行 count=0」实现；该行条件已成立时不再另产无数据事件。
- 平移窗查询失败时本轮该策略所有分组都不判（`reason = window_failed`），而不是只跳过单个分组。
- 占比数值全精度落库，通知一位小数、告警名模板两位小数。

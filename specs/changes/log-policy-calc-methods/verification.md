# 验证记录：日志策略计算方式丰富

日期：2026-10-27。环境：macOS，Python 3.12.11，Node v22.16.0（`package.json` 要求 Node 24.x，仅引擎警告）。

通过的 pytest 都加了 `--create-db --nomigrations`。`pytest.ini` 默认 `--reuse-db`，复用本机已有 sqlite 测试库时，迁移在重做 `NewSessionEventRelation` 表时抛出 `KeyError: 'event'` / `FieldDoesNotExist: NewSessionEventRelation has no field named 'event'`。该模型不在本次改动范围，未改。

## 后端

工作目录 `server`。环境变量：`DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true`。

| 命令 | 结果 |
|---|---|
| `uv run pytest apps/log/tests/test_policy_scan_pure.py apps/log/tests/test_policy_dry_run.py apps/log/tests/test_format_notice_content_href_3651.py apps/log/tests/test_alert_query_clue.py apps/log/tests/test_alert_lifecycle_notify.py apps/log/tests/test_policy_alert_condition_validation.py apps/log/tests/test_issue_4336_i18n.py --no-cov --create-db --nomigrations -q` | **137 passed** |
| `uv run pytest apps/log/tests/test_policy_scan_db.py --no-cov --create-db --nomigrations -q`（新增两条快照测试之前） | **59 passed，1 failed，1 skipped**。失败用例在两次全文件运行中不是同一条：第一次 `TestCreateEvents::test_concurrent_existing_event_cannot_be_overwritten_by_late_worker`，第二次 `TestCreateEvents::test_concurrent_same_execution_recovers_event_conflict`。都是 `django.db.utils.OperationalError: database table is locked`（sqlite 并发写）。 |
| `uv run pytest apps/log/tests/test_policy_scan_db.py::TestCreateEvents --no-cov --create-db --nomigrations -q` | **22 passed，1 failed**（同上 `test_concurrent_existing_event_cannot_be_overwritten_by_late_worker`，`database table is locked: log_alert`） |
| `uv run pytest apps/log/tests/test_policy_scan_db.py::TestCreateEvents::test_concurrent_existing_event_cannot_be_overwritten_by_late_worker --no-cov --create-db --nomigrations -q` | **1 passed** |
| `uv run pytest apps/log/tests/test_policy_scan_db.py::TestKeywordAlertDetection::test_keyword_snapshot_freezes_jump_query apps/log/tests/test_policy_scan_db.py::TestAggregateAlertDetection::test_aggregate_samples_capped_and_snapshot_has_jump_query --no-cov --create-db --nomigrations -q` | **2 passed**（加在全文件运行之后） |
| `uv run pytest apps/log/tests/test_policy_alert_condition_validation.py --no-cov -q`（不加 `--create-db --nomigrations`） | **14 errors**。setup：`KeyError: 'event'`，随后 `FieldDoesNotExist: NewSessionEventRelation has no field named 'event'`。与本次改动无关。 |

sqlite 并发失败是既有线程用例在 sqlite 上的锁等待，单测隔离运行通过。没有改并发写路径。聚合取样线程里对 `close_old_connections` 做了函数内导入，避免通知正文回归夹具在替换 `django.db` 时模块无法加载。

## 前端

工作目录 `web`。

| 命令 | 结果 |
|---|---|
| `pnpm exec vitest run` 六个相关文件（`policyFormUtils.test.ts`、`conditionSelector.test.tsx`、`dryRunResultModal.test.tsx`、`buildSearchJumpUrl.test.ts`、`AlertRawLogWidget.test.tsx`、`logPolicyCalcMethods.i18n.test.ts`） | **6 files，19 tests passed**。jsdom 的 `getComputedStyle` 未实现、antd v5 / React 19 兼容警告，测试仍通过。 |
| `pnpm test:log-policy-form` | 通过（`log-policy-form-state validation passed`） |
| `pnpm test:log-alert-raw-columns` | **失败**，与本次改动无关。`web/scripts/log-alert-raw-columns-test.ts` 期望 `showFields: message` 的 `dataIndex` 为 `_msg`，实际为 `message`。`rawLogColumns.ts` 的 `FIELD_ALIAS` 把 `message` / `_msg` 都映到 `message`，来自已提交的 `be8a07a381 feat(log): 统一日志正文为 message`。本次未改该文件或该脚本。 |
| `pnpm exec eslint` 本次改过的 log 前端文件 | 退出码 0 |
| `pnpm lint` | 退出码 1。**101 problems（3 errors，98 warnings）**。3 个 error 都不在 `src/app/log`：`automaticPolicyApply.ts`、`rum-bootstrap.tsx`、`rumBootstrap.ts` 的 `consistent-type-definitions`。`src/app/log` 无报告。 |
| `pnpm type-check` | 退出码 0。过程中有 Node 24 引擎警告，以及 isoflow webpack 体积警告。 |

## 与规格的偏差

- 未改 `docs/changelog/`。规格 T5 写了 changelog 条目，本次任务明确要求不改该目录。
- 策略详情页主按钮文案是既有的 `common.confirm`（确认），不是「保存」。试算按钮放在它左侧。
- 检索链接的 `startTime` / `endTime` 用毫秒。后端窗口是 unix 秒；小于 `1e10` 时乘 1000，与检索页 `dayjs(+startTime)` 一致。规格 URL 示例未写单位。
- 通知正文里的检测窗口按 UTC 格式化。规格示例 `2026-10-27 15:50:00` 未声明时区；测试锁定 `1700000000–1700000300` → `2023-11-14 22:13:20 ~ 22:18:20`。
- 试算失败日志用 `exc_info=safe_exception_info(exc)`，不把异常消息原文写入日志。规格写 `exc_info=True`。异常消息可能带查询正文，与「日志不记查询正文」冲突，因此保留 traceback、把异常身份换成类型名。对外文案仍是「试算失败」。
- 未保存的 `Policy`（试算）没有主键。`snapshot_policy_organization_ids` 在 `pk is None` 时返回空列表，否则关联查询会抛 `ValueError`。编辑试算带主键时仍读库内组织。
- 聚合条件的 `group_by` 必须是字符串列表。扫描期 `_normalize_group_by` 仍接受单个字符串，序列化层拒绝，与前端只提交数组一致。
- 额外 i18n 键：`countRateUnit`（速率后缀）、`dryRunGroup`、`dryRunVerdict`。规格清单里的键 zh/en 都有。
- 既有纯函数测试里样本 `limit="12"` 的期望从 12 改为 10，对应规格上限 `min(max(limit, 1), 10)`。
- 聚合查询的既有 DEBUG 日志仍会格式化查询字符串。本次新增的 INFO / WARNING 不记查询正文。
## 本机走查（2026-10-27）

底座已在跑（Postgres、Redis、VictoriaLogs）。后端是 `https://127.0.0.1:8443` 的 uvicorn `--reload`，前端是 `:3000`。

| 步骤 | 结果 |
|---|---|
| `POST /api/v1/log/policy/dry_run/`，采集类型 `kafka_subscribe`，15 分钟窗，`count_rate > 0.01` 且 `count_delta > -1000000`，分组 `host_name` | 200。`baseline_status=ok`。`fusion-collector`：本窗 9370、上一窗 8916、速率 10.41 条/秒、变化量 454、`would_trigger`，样本 5 条。策略数仍为 1，没有落库 |
| 新建策略 id 5（`notice=false`、`enable=false`），用 `LogPolicyScan` 扫同一窗口 | 产生 1 条告警。内容「走查 fusion-collector 速率 9.98 变化 -520」。聚合结果 count 8981、previous 9501、delta -520、rate 9.98。样本 10 条。`jump_query` 为 `collect_type:"kafka_subscribe" AND host_name:="fusion-collector"`，窗口与扫描窗一致 |
| 用该 `jump_query` 和窗口直接查 VictoriaLogs | 命中原始日志 |
| 用扫描器的 `_format_notice_content` 渲染正文 | 含命中条数、速率、较上一窗 -520、UTC 检测窗口、10 条截断样本、检索链接（时间为毫秒）和告警详情链接。未发送通知 |
| 删除策略 5 | 策略、定时任务、告警都清掉，策略数回到 1 |

嵌入式浏览器打开 `http://127.0.0.1:3000` 时，Next 对带 `Origin: http://127.0.0.1:3000` 的脚本请求返回 403（`web/next.config.mjs` 的 `allowedDevOrigins` 只有 `bklite.weops.com`），页面停在加载圈，表单点击没走成。这是既有开发源站限制，不是这次改动。

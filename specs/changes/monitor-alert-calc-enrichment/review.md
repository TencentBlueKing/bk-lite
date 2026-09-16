# Monitor 告警计算方式丰富 — 审查结论与整改清单

审查对象：`c2575b616..7381d1a8e`（9 提交）+ 未跟踪 `verification.md`。
审查日：2026-09-15。对照 `spec.md` D1～D10 与仓库标准（CLAUDE.md、`specs/capabilities/backend-engineering.md`）。

标 ✅ 的条目已由审查者对代码逐行核实；未标的来自子代理报告，整改前先核一次。
每条整改都要补对应测试，测试要求见 `spec.md`「Testing Decisions」。

## 0. 独立验证基线

- 本 change 相关 18 个后端测试文件（sqlite `--nomigrations`）：325 passed。
- 全 monitor 目录 241 失败全部为 sqlite 基线问题（基线提交同环境复跑失败数一致），与本 change 无关；`test_push_to_cmdb.py` 收集失败也是基线问题。
- 前端 4 个逻辑脚本、`pnpm type-check` 通过。
- eslint：切片 4 引入 2 处 indent 错误 —— `information.tsx:298`、`strategyDetailUtils.ts:629`。`alertDetailUtils.ts:169-171` 三处是基线已有，不用动。

## 1. P0：必须修，否则产生错误告警或静默改语义

### 1.1 ✅ `count_if_over_time` 零匹配窗口 → 序列消失

- 位置：`policy_methods.compile_existence_query` 对 count_if 走 `compile_window_query`；`_compile_count_if_query` 编出 `count_over_time(((avg(m) by g) > 80)[5m:10s])`。
- 事实：VM 对零匹配窗口不返回序列（`verification.md` 已观测「CPU<50 → 0 条」）。
- 后果：① 存在性查询同形态 → 无数据检测误报、试跑判成 `no_data`；② 比较查询无行 → 告警触发后失败归零时行不进 `info_events` → `info_event_count` 不增 → **告警永不自动恢复**。
- 修法：存在性对 count_if 走 `_compile_last_over_time_existence`（与 rate/changes/deriv 同路）；比较查询改为 `sum_over_time(((group(base) by g) > bool 80)[period:step])`，零匹配返回 0 而不是消失。同步更新 spec D2 编译表。
- 测试：锁两条字符串；用 mock 返回「零匹配 → 0 值行」验证 info 事件产生、恢复计数递增、无数据不误报。

### 1.2 ✅ 模板批量建策略丢全部新字段，新算法静默降级

- 位置：`policy_bulk.build_bulk_policy_payloads` 生成 payload 不带 `compare_mode / compare_value_kind / count_predicate / forecast_target / forecast_lookback / recovery_threshold`；`normalize_template_algorithms` 对无 `group_algorithm` 的 rate/changes/deriv/count_if 回落成 `("avg", "avg_over_time")`。
- 后果：「P95 比 1h 前高 50%」模板批量下发后变成 absolute 策略；模板选速率被无声改成均值。
- 修法：payload 透传全部新字段（缺省与 D1 一致）；`normalize_template_algorithms` 对新算法不走 legacy 映射，缺 `group_algorithm` 时补默认 `avg` 而不是改 `algorithm`。
- 测试：`test_policy_templates_aggregation` / `test_policy_template_portability` 加「模板带新字段 → payload 逐字段一致」「模板选 rate 无 group_algorithm → algorithm 仍是 rate」。

### 1.3 ✅ 运行期基线同步仍吃比较查询结果

- 位置：`scanner._sync_baselines(alert_events, info_events)`，事件来自比较查询；`hold_events` 也未传入。
- 后果：对照缺失的新实例行不进任何事件 → 不建基线 → 无数据检测对它不生效，直到有对照数据。D2 的拆分只在保存时 `PolicyBaselineService.sync` 生效，扫描期没生效。
- 修法：`_sync_baselines` 改用本轮存在性查询结果（无数据分支已经查过，可传下来复用），不再从事件推导。
- 测试：mock 比较查询返回空、存在性返回有行 → 基线被创建。

### 1.4 `timeleft` 边界

- `clamp_min(deriv, 1e-9)` 让斜率≈0/负时得到 ~1e7 小时的有限值，spec「非有限值过滤」不成立（结论仍不触发，但依赖 `<` 语义，需在 spec D2 改写说明）。
- `forecast_target < 当前水位`（如「可用空间距 0」）时 `clamp_min(target - w, 0) = 0` → 永远 0 小时 → 立即触发。表单和 serializer 都没拦。
- 修法：spec 明确 timeleft 只对「上升水位逼近上限」；serializer 校验 `forecast_target` 必须配 `<` / `<=` 阈值（时间只会「小于」告警）；表单 tooltip 写明。
- 测试：负斜率不触发；`target` 低于水位的用例写明期望。

## 2. P1：标准硬违规

### 2.1 试跑失败路径零 traceback 持有者

- 位置：`policy_dry_run.py` `run()` 的 `except Exception → logger.warning(无 exc_info) → raise BaseAppException`；中间件对 `BaseAppException` 也不带 traceback。
- 后果：`_classify` 里的 `KeyError/TypeError` 全部变成不可排障的「试跑失败」。
- 决策：spec D7「只记一条 WARNING」与 `backend-engineering.md §8.2`「一个失败恰有一个 traceback 持有者」冲突。**采用**：保留 WARNING 等级和稳定模板，加 `exc_info=True`，由这条日志持有 traceback；`BaseAppException` 继续不带。同步改 spec D7 措辞。
- 测试：现有 `test_failure_logs_single_warning_without_query_or_payload` 加断言 `record.exc_info` 非空，且 traceback 文本不含查询正文/响应哨兵。

### 2.2 ✅ 已保存策略 id 未做归属校验

- 位置：`policy_dry_run._build_unsaved_policy` 只 `filter(pk=saved_id).exists()`，随后 `_classify` 用该 id 读活动告警决定 `would_recover/hold`。
- 后果：任意 id 可探测他人策略是否有活动告警。
- 修法：用视图层同样的可见范围 queryset（`scope_permission_queryset` 或策略列表用的过滤）校验 `saved_id` 可见，不可见按草稿处理（`saved_id = ""`）。
- 测试：跨团队策略 id → 不评恢复且不抛错。

### 2.3 ✅ `query_aggregation_metrics` 兼容层

- 位置：`metric_query.py:177-179`。生产零调用方，只有 `test_docker_container_policy_scan_repro`、`test_formula_policy_scan`、`test_k8s_cluster_policy_scan_repro`、`test_policy_scan_alert_detector` 的 fake 在 mock 它。
- 修法：删方法，四处 fake 改成 `query_comparison_metrics`。

### 2.4 对 mock 友好的生产防线

- 位置：`alert_detector.py` `_overlay_last_values` / `source_display_unit` 处、`snapshot_recorder.py:257-259,283-285` 用 `getattr(..., None) + callable` 探测 `MetricQueryService` 必有方法。
- 修法：直接调用；测试桩补齐方法。

## 3. P2：偏离 spec，需记录或收口

- D3 rate/deriv「量纲/秒」只覆盖 bytes/bits/counts（`QUANTITY_TO_RATE_UNIT`），percent/ms/celsius 等原样返回。选一：补映射（`percent → percent/s` 之类需要单位目录支持）或在 spec D3 明确「无速率单位的量纲显示为原单位并标注 /s」。前端 `mapQuantityToRateUnit` 同步。
- D10 预览叠对照时阈值线直接不画（`shouldDrawPreviewThreshold = !overlay`），spec 要求「按结果单位画」。选一：实现（后端 overlay 分支返回 `result_unit`，前端按此画阈值线）或记录偏离。
- ✅ D2 存在性查询窗口类沿用原汇聚而非一律 `last_over_time`：合理（保住旧策略字符串不变），但要写进 spec D2，不只在验收记录。
- serializer 多了两条禁则表没有的规则：多级触发方向不一致禁配恢复阈值；强制 `threshold_unit == result_unit`。保留，但补进 spec D4 表。

## 4. 范围蔓延，回退或记录

- `7381d1a8e` 在 `page.tsx:309-313` 用 `useEffect` 把已含 rate 指标上的 `algorithm` 自动改写成 `avg_over_time`。spec 只要求保存拒绝；隐藏选项可以，**静默改写用户选择不行**。回退成：隐藏选项 + 若当前值非法则表单校验报错，不改值。
- `formatDryRunHitCountCopy` 前端硬编码中文并复刻后端 `HIT_COUNT_REASON`。后端 `reason` 已经返回文案，前端直接展示。
- ✅ `SLICE1_COMPARE_MODES` / `SLICE1_COMPARE_VALUE_KINDS`（后端）与 `SLICE1_COMPARE_MODES` / `getSlice1CompareModes`（前端）把切片编号泄入领域代码。内联进 `COMPARE_MODES` / `COMPARE_VALUE_KINDS`，删前端仅测试引用的导出。

## 5. 测试缺口（对照 spec Testing Decisions）

- 编译矩阵：现在只锁 avg/p95 × {previous_window, offset_1h, offset_24h}。补 stddev / rate / changes / deriv × 至少一个 compare_mode；`offset_30d`（全库无用例）、`offset_7d ratio`、`baseline_4w delta`、`count_if` 新形态。
- `trigger_count > 1` × offset 共存。
- 「对照缺失时基线同步仍能建基线」：`test_policy_baseline_service.py:118` 只改了 mock 名，补行为断言（配合 1.3）。
- scanner 级旧策略逐点回归：无新字段策略跑一轮 `MonitorPolicyScan`，Alert/Event/快照与基线提交一致。
- 试跑结果表：各 verdict 与「本轮命中 k/N」文案的渲染测试。

## 6. 代码气味（判断性，顺手处理，不强制）

- 前后端重复：`strategyDetailUtils.ts` 复刻后端字节/比特单位表与 `resolve_result_unit`（preview/dry_run 已返回 `result_unit`，前端应直接用）；`COMPARE_VALUE_KINDS_BY_MODE`、算法分类集合、`RATE_FUNCTION_RE` 双份维护；结果单位规则在 `page.tsx:1180-1197`、`formulaExpressionUtils.ts:733-740`、`alertConditionsForm.tsx:265-271` 又各硬编码 `'rate'|'deriv'|'changes'`。至少收口成前端一处 `resolvePolicyResultUnit`。
- `mode in ("", COMPARE_MODE_ABSOLUTE)` 六处重复；`policy_preview` 用裸字符串 `"timeleft"`。抽 `is_absolute_compare(policy_like)`。
- `_raise_for_vm_error` 在 `policy_dry_run` 与 `policy_preview` 各一份。
- `_compile_count_if_query` / `_compile_last_over_time_existence` / `compile_timeleft_query` 三处重复「formula → 子查询 / 否则 group_by 必填 → 分组」骨架。
- `TRUNCATED_WARNING` 写死 200，与 `DRY_RUN_INSTANCE_LIMIT` 脱钩。
- ✅ `_authorized_instances` 用 `MonitorPolicyScan.__new__` 绕构造函数调私有 `_get_instance_list_by_source`。把实例展开提成 `MonitorPolicyScan` 的 classmethod 或独立函数。
- 死代码：`format_period` 内 `del points`；`shouldDrawPreviewThreshold` 的 `conversionEnabled` 未用；`_overlay_value_maps(policy, ...)` 的 `policy` 未用。
- `_classify` 9 个参数；`AlertConditionsForm` 新增 15 props，compare / forecast / recovery 三组可各打包成对象。
- `LEVEL_ALGORITHMS` 含白名单里没有的 `"last"`；`dryRunResultModal` verdict 列复用「级别」文案；serializer 重复 import `BaseAppException`；`_is_enum_metric` 与 `_compiled_base_query` 各查一次 `Metric`；`views/monitor_alert.py` 新 import 顺序；`SnapshotRecorder` / `PolicyDryRunService` 跨模块导入私有 `_parse_finite_float`。

## 7. 验收记录残留

- `verification.md` P3：现网快照点未见 `current_value / baseline_value / compared_value / result_unit`。重启 `make -C deploy/local dev-celery` 后扫一轮策略 1 复验。
- `verification.md` P4：浏览器策略页未走通（`web/.env.local` 的 `NEXTAUTH_URL` 指向 `10.10.40.53`，本机是 `10.10.42.173`）。修正后补 UI 手测：比较基准下拉互斥、试跑表格、预览叠对照、Trap 无新字段、恢复阈值控件。
- 修完后更新 `verification.md` 的 §5 对照表与 §6 问题列表。

## 8. 建议顺序

1. §1 四条 + §2.1～2.3（含测试）
2. §4 回退 + §2.4 + §5 测试缺口
3. §3 决策并同步 spec；§7 复验
4. §6 顺手项

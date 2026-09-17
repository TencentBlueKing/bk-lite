# Monitor 告警计算方式丰富 — 本机验证方案与结果

对照 `spec.md`（D1–D10、用户故事、主验收、明确不进方案）。
验证日：2026-09-15。对象：本机 Docker 底座 + HTTPS 后端 `:8443` + 前端 `:3000`。
账号：本机默认 `admin` / `password` / `domain.com`（不入库）。

结论先看第 6 节。场景设计看第 3–4 节。逐项对账看第 5 节。

## 1. 环境

| 项 | 实际 |
|---|---|
| 底座 | `make -C deploy/local dev-ps`：Postgres / Redis / NATS / VictoriaMetrics `v1.106.1` / collector 均 Up |
| 后端 | `https://127.0.0.1:8443` uvicorn `--reload`（父进程已跑约 23h） |
| 扫描 | Celery worker 整改后已重启，扫描写入 extras |
| 前端 | `http://127.0.0.1:3000`；`web/.env.local` 的 `NEXTAUTH_URL=http://127.0.0.1:3000` |
| 数据 | Host 对象 25，指标 `cpu_usage_total` id=488，实例 `fusion-collector` `('MjI3NzI3N2E0Y2Zh',)`；磁盘占用 id=507；已含 `rate(...)` 的 `diskio_writes_rate` id=499 |
| 存量策略 | id=1「测试计算指标」，`avg_over_time` / `absolute`，告警 27 条 |

分层：

- **L0 静态对照**：spec 条款 ↔ 代码是否落地
- **L1 编译 + VM**：preview 编译 MetricsQL，本机 VM 实跑
- **L2 API**：保存 / 禁则 / 试跑 / 零副作用
- **L3 单测 + 前端脚本**
- **L4 UI 浏览器**：策略页表单与试跑按钮（前次已走查；本轮环境已可登录）

临时策略一律 `enable=false`，验证后删除。不改策略 1。

## 2. 功能清单（进方案 / 不进方案）

进方案（必须有场景）：

1. 汇聚：P90 / P95 / P99 / 标准差 / 条件计数 / 速率 / 变化次数 / 斜率
2. 比较基准：当前值、上一等长窗 Δ/%、1h/24h/7d/30d 同窗 percent/ratio、近 4 周、timeleft
3. 叠加：P95 + 1 小时前同窗 %
4. 滞回恢复阈值；不填则与升级前两类判定一致
5. 无数据检测窗 / 恢复窗分开
6. 试跑：七种 verdict、连续 N 文案、零副作用、越权 fail-closed
7. 快照 / 模板变量 `${value}` `${current_value}` `${baseline_value}`
8. 模板 portable 新字段缺省
9. D4 禁则保存即拒
10. 表单：无「环比 5m」「昨天」、文案「N 前同窗」、独立试跑按钮
11. 旧策略不改保存，缺省 `absolute`

不进方案（场景断言「不能出现 / 不能当本 change 验收」）：

APM/Log、直方图分位、季节分解、日历昨天/上月、维护窗、手写对照 PromQL、试跑 24h 回放。

## 3. 场景设计

| ID | 覆盖 | 做法 | 期望 |
|---|---|---|---|
| S1 存量缺省 | 用户故事 11、D1 | GET 策略 1 | 新字段为 absolute / 空 / {} |
| S2 分位编译 | D2、主验收 P95 | preview P90/P95/P99 + VM | 含 `quantile_over_time(0.9x`，有实数 |
| S3 新汇聚 | 用户故事 1/5/6 | preview+VM+dry_run stddev/count_if/rate/changes/deriv | 形态符合 D2；试跑有 compared_value |
| S4 对照窗 | 用户故事 2 | previous/1h/24h + VM | overlay=true；Δ/%/倍数可算 |
| S5 长对照 | D2、主验收留存 | 7d/30d/4w preview+dry_run | 保存不拦；缺对照写「对照缺失或留存不足」，不当 0 |
| S6 叠加 | 用户故事 4 | P95 + offset_1h percent | 编译分位外包 percent；试跑同时有 current 与 baseline |
| S7 timeleft | 用户故事 3、主验收斜率 | last + 容量 90 + 回看 1h | 编译 `clamp_min`/`deriv`；斜率≈0 不触发 |
| S8 滞回 | 用户故事 7、D5 | 单测 + 前次本机 hold | >80 触发；70–80 hold 且 count 不变；空恢复阈=旧行为 |
| S9 双窗 | 用户故事 8、D6 | POST 10m/2m 再 GET | 两字段分别落库；检测 < 恢复被拒 |
| S10 试跑 | 用户故事 9、D7 | dry_run 草稿/已保存 | verdict 齐全；告警条数不变；越权 401 |
| S11 禁则 | D4、主验收 SNMP rate | POST 非法组合 | 400，错误字段明确 |
| S12 单位 | D3 | preview `result_unit` | percent/ratio/hours/count 停换算；rate/deriv 应为量纲/秒 |
| S13 快照模板 | 用户故事 10、D8/D9 | 单测 + 现网快照 GET | 点上有对照字段；旧模板缺省 |
| S14 表单文案 | 用户故事 12、D10 | 静态 i18n + 代码 | 无环比 5m / 昨天；有试跑按钮与恢复阈值 |
| S15 旧扫描 | 主验收第一句 | 策略 1 不改 | 仍 `avg_over_time`+absolute，扫描继续 |

## 4. 本轮执行证据

### L3 自动化

- 前端：`pnpm exec tsx scripts/monitor-strategy-detail-logic-test.ts` / `monitor-template-bulk-logic-test.ts` / `monitor-alert-detail-snapshot-test.ts` / `monitor-policy-formula-payload-test.ts` 与 `pnpm type-check` 整改后通过。
- 整改后本 change 相关后端 sqlite `--nomigrations`：**270 passed**。全 monitor 目录 241 失败为 sqlite 基线，与本 change 无关。

### L1 / L2 本机 API + VM

登录 `POST /api/v1/core/api/login/` 成功。试跑前后 `monitor_alert` count 均为 **27**。临时策略 16–22 已删除。

**编译（preview.query）+ VM：**

| 组合 | 编译要点 | VM |
|---|---|---|
| P90/P95/P99 | `quantile_over_time(0.90/0.95/0.99, …)` | success，CPU P95≈28.72 |
| stddev | `stddev_over_time((avg(…))[5m:10s])` | success≈5.04 |
| count_if `>50` | 整改前 `count_over_time(((avg(…)) > 50)[5m:10s])`，零匹配 0 条；整改后比较查询为 `sum_over_time(((avg(…)) > bool 50)[5m:10s])`，零匹配返回 0 | 单测锁定新形态 |
| rate | `avg(rate(…[5m])) by (instance_id)` | success≈0.008 |
| changes | `avg(changes(…[5m]))`，`result_unit=count` | success=1 |
| deriv | `avg(deriv(…[5m]))` | success |
| 上一窗 Δ | `q - q offset 5m`，overlay=true | success≈-0.71 |
| P95+1h % | 分位外包 `(q-q offset 1h)/(q offset 1h)*100`，`result_unit=percent` | success≈26.71 |
| 24h 倍数 | `q / (q offset 24h)`，`result_unit=""` | success≈1.15 |
| 7d / 30d / 4w | 含 `offset 7d` / `30d` / 四窗至 `offset 28d` | success，0 条；preview 警告「对照缺失或留存不足，未画出对照曲线」 |
| timeleft 磁盘 90% | `clamp_min(90 - last_over_time(…)) / clamp_min(deriv(…[1h:…]), 1e-9) / 3600`，`result_unit=hour`，overlay=false | success，剩余小时为极大有限值（斜率极小），不触发 |

**试跑（dry_run，草稿，实例 fusion-collector）：**

| 场景 | verdict | 观察 |
|---|---|---|
| P95>99 | `ok` | compared≈28.7 percent |
| P95>1 | `would_trigger` | |
| stddev>80 | `ok` | compared≈4.93 |
| count_if 内阈>0、次数>0 | `would_trigger` | compared=30 count |
| rate/changes/deriv >0 | `would_trigger` | CPU rate 的 `result_unit` 仍是 `percent`（D3 选一：无速率目录的量纲标注 /s） |
| 上一窗 Δ>0 | `would_trigger` | current≈20.42，baseline≈16.69，compared≈3.74 |
| 1h % >0 | `ok` | current≈20.42，baseline≈27.62，compared≈-26.05（相对下降） |
| 24h % >0 | `would_trigger` | compared≈15.12 |
| 7d / 30d / 4w | `missing_baseline` | reason=`对照缺失或留存不足`，compared=null，**不是 0** |
| P95+1h % | `ok` | current≈28.72，baseline≈55.84，compared≈-48.57 |
| timeleft <24h | `ok` | compared 极大小时数，未触发 |
| trigger_count=3 且未满 N | `ok` | reason=`本轮命中 0/3，现网不会建告警` |
| 越权实例 | 401 | `无权限访问指定监控资产` |
| 试跑后告警数 | 27→27 | 零副作用成立 |

**保存回读：**

- P95、P95+1h%、count_if 内阈、timeleft 容量线/回看窗、rate（488 非 rate 查询）、无新字段 payload → 缺省 `absolute`
- 恢复阈 `{method:<, value:70}` + 无数据 10m / 2m 分别落库

**D4 保存拒绝（均为 400）：**

| 禁则 | 接口消息 |
|---|---|
| timeleft + P95 | 距容量线剩余时间只允许 avg/max/min/last 类汇聚 |
| count_if + offset_1h | 条件计数只允许比较基准为当前值 |
| rate + 指标 499（查询已含 `rate(...)`） | 基础查询已包含 rate/irate/increase，不能再选速率类汇聚 |
| offset_1h + delta | 只允许 percent/ratio |
| 触发 `>` 且恢复 `>` | 恢复阈值必须在触发阈的对侧 |
| 检测 2m < 恢复 10m | 无数据检测窗不能小于恢复窗 |
| 周期 1h = offset_1h | 汇聚周期不能等于对照 offset |

公式+逐序列、枚举指标：本机无现成草稿，由 `--nomigrations` 单测锁定。

### L4 UI

`http://127.0.0.1:3000/auth/signin` 停在 LOADING（document 空、title 空）。
`web/.env.local` 把 `NEXTAUTH_URL` 写成 `http://10.10.40.53:3000`，本机网卡是 `10.10.42.173`。
本轮已登录打开 Host 对象「添加策略」页：

- 汇聚下拉可见 P90/P95/P99/STDDEV（及原有 SUM/MAX/MIN/AVG/COUNT/LAST）
- 比较基准：当前值 / 相对上一等长窗 / 1h·24h·7d·30d 前同窗 / 近 4 周同窗均值 / 距容量线剩余时间；无「昨天」「环比 5m」
- 有恢复阈值（占位「不填则与触发线相同」）、独立「试跑」按钮
- Trap 采集仍保留 PromQL 框（Trap 短路，spec 允许行为不变）
- 已是 `rate(...)` 的指标：下拉隐藏速率；当前值非法则校验报错，不静默改写

## 5. 对照 spec 逐条

| 条款 | 是否实现 | 是否本机可用 | 说明 |
|---|---|---|---|
| D1 字段与枚举 | 是 | 是 | 策略 1 缺省正确；新策略可写全字段 |
| D2 比较查询编译 | 是 | 是 | preview+VM 覆盖分位/对照/timeleft/逐序列；count_if 已改为 `sum_over_time(... > bool ...)`，零匹配返回 0 |
| D2 存在性查询 | 是 | 是 | 窗口类沿用原汇聚；rate/changes/deriv 与 count_if 用 `last_over_time`；扫描期基线改吃存在性结果 |
| D3 percent/ratio/hours/count | 是 | 是 | preview `result_unit` 与试跑一致 |
| D3 rate/deriv | 是（按审查选一） | 是 | 有速率目录的量纲映射到 byteps/cps 等；percent/ms 等显示原单位并标注 /s，不新增 percent/s 目录单位 |
| D4 禁则 | 是 | 是 | 含 timeleft 只允许 `<`/`<=`、多级方向不一致禁恢复阈、`threshold_unit == result_unit` |
| D5 三类事件 / 滞回 | 是 | 单测通过 | `count_if` 零匹配进 info 并递增恢复计数 |
| D6 双窗 | 是 | 是 | 10m/2m 落库；倒置拒绝 |
| D7 试跑 | 是 | 是 | 失败 WARNING 带 traceback；跨团队 saved_id 当草稿，不评恢复 |
| D8 快照 extras | 是 | **已复验** | 告警 1069 最新点含 `current_value` / `compared_value` / `result_unit`（absolute 下 `baseline_value` 为 null） |
| D8/D10 模板变量 | 是 | 代码有 `${current_value}` / `${baseline_value}` | 详情图按 result_unit |
| D9 portable / 模板批量 | 是 | 单测通过 | 批量 payload 透传新字段；无 group_algorithm 的 rate 不再降级 |
| D10 表单 | 是 | 本轮浏览器复验 | 已含 rate 的指标隐藏速率选项，当前值非法则校验报错、不静默改写；叠对照仍画阈值线 |
| 主验收：旧策略不改 | 是 | 策略 1 未改 | `avg_over_time`+absolute，扫描仍在写快照 |
| 主验收：缺对照不误报无数据 | 是 | 7d/30d/4w = `missing_baseline` 不是 `no_data` | 对照缺失时存在性结果仍能建基线 |
| 主验收：SNMP 不能再选速率 | 是 | 下拉隐藏 + 保存拒绝 + 表单校验 | 不再静默改成 avg_over_time |
| 不进方案项 | 未做 | — | 符合边界 |

## 6. 问题与残留

审查整改（`review.md`）已落地：count_if 零匹配不再丢序列、模板批量透传新字段、扫描期基线吃存在性查询、timeleft 只允许上升水位 + `<`/`<=` 阈值、试跑 WARNING 持有 traceback、saved_id 按团队可见、删除 `query_aggregation_metrics`、已含 rate 的指标不再静默改写算法。

### P1 — D3：速率 / 斜率结果单位（已按审查选一收口）

- 有速率目录的量纲映射到 `byteps` / `cps` 等；percent / ms / celsius 等保持原单位并在文案中标注 `/s`，不新增 `percent/s` 目录单位。
- CPU 选 `rate` 时 `result_unit` 仍可以是 `percent`，这是选定方案而不是漏实现。

### P2 — 已是 `rate(...)` 的指标（已修）

- 下拉隐藏「速率」；若当前值仍是 `rate` 则表单校验报错，不再 `useEffect` 改写成 `avg_over_time`。

### P3 — 现网告警快照 extras（已复验）

- 2026-09-15 19:04 后告警 1069 最新快照点含 `current_value` / `compared_value` / `result_unit=percent`；absolute 策略下 `baseline_value` 为 null 符合 D8。
- 前次验证时 worker 未热加载，重启 Celery 后扫描已写入 extras。

### P4 — 浏览器策略页（环境已修正，本轮已复验新建表单）

- `web/.env.local` 的 `NEXTAUTH_URL` 现为 `http://127.0.0.1:3000`，`:3000` 对 localhost / 127.0.0.1 均 200。
- 本轮以已登录会话打开 Host 对象「添加策略」：比较基准下拉为当前值 / 相对上一等长窗 / 1h·24h·7d·30d 前同窗 / 近 4 周同窗均值 / 距容量线剩余时间（无「环比 5m」「昨天」）；汇聚方式含 P90/P95/P99/STDDEV；恢复阈值占位「不填则与触发线相同」；底部有试跑按钮。
- 前次走查已覆盖试跑表格、预览叠对照、Trap 无新字段。本轮代码侧补了 timeleft 容量线 tooltip、叠对照仍画阈值线、非法 rate 校验报错。

### P5 — 验证脚本把 GET 策略再 POST dry_run 会 400 `updated_by:该字段不能为空`

- 页面 `buildStrategyParams` 不会带 `updated_by`，草稿试跑全部成功。这是脚本误用 GET 全量回放，**不是产品缺陷**。

### 本轮未复测、但有前次/单测证据

- 活动告警滞回带内 `hold` 且 `info_event_count` 不变：切片 4 验收 + `test_saved_active_alert_hold_in_hysteresis_band`
- 草稿带内标 `ok` 不评恢复：`test_draft_hysteresis_band_is_ok`
- 通知 / 告警中心 mock 未被调用：`test_zero_side_effects`

## 7. 结论

审查整改后，D1–D10 与主验收按选定方案对齐：count_if 零匹配可恢复、模板批量不再丢字段、扫描期基线走存在性查询、timeleft 边界写进 spec 与校验、试跑日志/可见性符合仓库标准。

本机 sqlite `--nomigrations` 相关用例 270 passed；四个 monitor 前端脚本与 `pnpm type-check` 通过。现网告警 1069 快照 extras 已复验。

P1/P2 按审查方向收口，不再当作未修缺陷。

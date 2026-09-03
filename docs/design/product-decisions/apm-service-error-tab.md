# APM 服务详情错误 Tab 产品决策记忆

- 最近更新：2026-09-02
- 当前规格：`specs/changes/apm-service-error-breakdown/spec.md`、`specs/capabilities/apm-function-list.md`

## 产品定位

服务详情错误 Tab 回答四个排障问题：多严重、哪些入口在失败、失败原因是什么、给我一条能点进去的链。它不是失败事件流水，也不是 Issue 管理页。

## 已确认范围

- 错误率仍是该服务、环境、时间窗内入口 Span（SERVER / CONSUMER）的 OTel ERROR 比例。
- **计数看入口，归因看全部 Error Span**：失败次数、失败端点用入口口径；错误原因用该服务本窗全部 Error Span（含 CLIENT / INTERNAL 子 Span），因为异常信息不在入口 Span 上。
- 调用链 Tab 保持近窗混合样本，不与错误率对账。
- 探索「错误分析」仍是全量 Error Span 的 Issue fingerprint 翻页，不收成入口口径。

## 已确认设计决策

- Tab 只写「错误」，不用 Issue 种类冒充错误条数。
- 四个区块各用单一口径：错误率与趋势、失败端点（合计 = 失败次数）、错误原因（按错误类型统计，标注发生位置，与失败次数不一一对应）、最近失败样本（明确写「最近 N 条」）。
- 全部数字来自存储侧 `stats by` 聚合，服务详情不再逐条 `get_trace`，不按 Span 翻页；更早样本走「在错误分析中打开」。
- 归因键优先级：`exception.type` > `error.type` > `status_message` > HTTP 5xx > 「未携带错误信息」。
- 样本区不出现百分比；「N 条 Trace」标签与卡片内展开堆栈从服务详情移除。

## 明确后置

- Issue 持久化与全窗精确 fingerprint 去重。
- Issue 生命周期、认领、激增 / 回归标记。
- 按错误类型过滤样本（第一期用每类型自带样例链替代）。

## 仍待确认

无。

## 已替代决策

- 「错误 Tab 按 Error Span 游标翻页并 concat Issue 卡」：2026-09-02 改为 Top Issue 摘要，去掉加载更多。
- 「Tab 展示错误 ({count})」：2026-09-02 改为只写「错误」。
- 「错误 Tab 与错误率同源：只取入口 ERROR Span 聚成 Top Issue，卡片标『占失败样本 %』」：2026-09-02 同日替代。本机 VT 实测入口 Error Span 全是笼统 `server_error`，原因在 CLIENT Span，入口口径导致页面只剩 `SpanError`；改为计数入口 / 归因全量分区标注。
- 「`get_trace` 失败的未归因兜底并入同服务最大的已归因 Issue」：随上一条一并移除，根因消除后不再需要。

## 决策来源

- 2026-09-02 用户确认：错误 Tab 只回答「错误率是哪些错」，不对账调用链样本，不把全窗失败翻完。
- 2026-09-02 用户确认：采纳「归因准确、口径分区标注」方案，参考 Elastic APM / Datadog 的 transaction 错误率与 error group 分离做法。

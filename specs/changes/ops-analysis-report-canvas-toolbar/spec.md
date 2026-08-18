# 运营分析报表画布工具栏对齐仪表盘

Status: implemented

## Problem Statement

报表构建器已经能查看和编辑纵向表格列表，但不能把同一份报表分发给未登录同事、导出 PDF，
或按计划邮件投递。仪表盘和大屏已经通过统一画布分享与 `CanvasReportAdapter` 订阅完成
这条分发闭环；报表此前被明确推迟。值班场景也缺少和仪表盘同一套刷新、全屏入口。

## Solution

报表查看态工具栏对齐仪表盘：周期刷新、全屏、客户端 PDF、分享、邮件订阅。分享复用现有
画布分享会话，订阅注册 `ReportCanvasReportAdapter`，不另做报表专用产品。客户端导出与
订阅 Chromium 都走仪表盘同款 A4 横向分页，不套用大屏单页等比缩小。

## User Stories

1. 作为报表查看者，我希望工具栏有刷新按钮和 关/1m/5m/10m 频率，从而表格能按画布间隔自动更新。
2. 作为有编辑权限的搭建者，我希望在非内置报表上改频率后立即写入画布，从而下次打开和 YAML 导入导出仍是该间隔。
3. 作为分享链接查看者，我希望看到刷新控件并能手动刷新；分享页按已保存频率自动静默刷新，但我改的频率只对这次打开有效，不写回源报表。
4. 作为报表查看者，我希望进入全屏只看筛选条和表格列表，按 Escape 退出，从而汇报时不被标题栏挡住。
5. 作为报表查看者，我希望导出 A4 横向分页 PDF，从而把纵向表格完整打出来，而不是只截当前 420px 卡片视口。
6. 作为有查看权限的用户，我希望复制报表分享链接给未登录同事，从而对方能在分享会话里看表并按允许清单查询。
7. 作为报表查看者，我希望为报表创建邮件订阅，从而按计划或立即测试收到与查看态一致的分页 PDF。
8. 作为报表维护者，我希望删除报表时终止其订阅，从而不会继续对已经不存在的报表出报。

## Implementation Decisions

- 报表是一等 `report` 画布，不是 Dashboard PDF 报告。订阅走已有编排壳层，只新增 Adapter。
- `refresh_interval` 加到 Report 模型、详情序列化、YAML `ReportItem` 与分享 payload。合法值与其它运行态画布相同：0 / 60000 / 300000 / 600000。字段 PATCH 不得夹带 `view_sets`，因此不走报表内容的 `expected_updated_at` 乐观锁。
- 前端复用 `useCanvasPeriodicRefresh`。`canPersist` 仅在非分享、非内置、具备 `view-EditChart` 时为真。分享态与订阅 `renderMode` 不持久化；分享页按 **effective**（初值=saved）自动刷，与仪表盘分享一致。订阅 `renderMode` 不启定时器；手动刷新与筛选搜索仍重拉表格，不重拉整份 `view_sets`。
- 全屏复用 `useAppViewFullscreen` overlay（`fixed inset-0`，z-index 1100），不用浏览器 Fullscreen API。进入时退出编辑并记住恢复；全屏不渲染带工具栏的工作区标题栏，只留筛选条、正文和退出按钮；Escape 退出。分享态仍可全屏。
- 客户端 PDF 导出前须 eager 激活全部 section 并等待各组件 settled，再调用 `exportDashboardToPdf`（html-to-image + jsPDF A4 横向分页）。订阅 Chromium 用默认 1440×900 视口 + A4 横向分页，**不加** Screen 策略 2 的 fit scale；就绪前调用 `prepareReportPrintLayout`（仅 overflow 展开），不走 GridStack `prepareDashboardPrintLayout` 的 `.grid-stack` 路径。卡片固定高度与内部滚动区打 `data-export-expand`；工具栏 `data-export-hidden`。仅非分享、非编辑态显示导出。
- 打开 `ReportModelViewSet.share_resource_type = "report"`。分享数据源查询把 report 纳入数据源类型，并从 `resource.filters` 或 `view_sets.filters` 收集允许的筛选键。分享页删除「report 未完成」拦截，渲染 `<Report shareMode />`，并把 `report` 加入 `ShareDataSourceProvider` 包装集合。
- 订阅新增 `ReportCanvasReportAdapter`：manifest 来自 `view_sets.sections`，filters 来自 `view_sets.filters`，`render_route_key = "report"`，展示标签「报表」，删除终止原因 `report_deleted`。写入类型包含 report。权限走 `ReportModelViewSet`。
- 前端订阅 Modal `resourceType` 包含 `report`；非 dashboard 创建走 `resource_type` + `resource_id`。Execution render 按 `resource_type` 分支到报表页，不得落入仪表盘 GridStack。
- 报表 `renderMode`：无工具栏、关闭 IntersectionObserver 懒加载（全部 section 立即查询）、筛选来自 Input Snapshot、聚合 `report-ready` / `report-failed`。空报表在 paint 后再发 ready。
- 工具栏顺序：刷新 → 全屏 → PDF → 分享 → 订阅 → 编辑。文案复用 `dashboard.*` / `common.*`。
- 权限：分享/订阅查看沿用 `view-View`；持久化刷新间隔要 `view-EditChart`。内置报表只读，间隔不落库。
- 本 spec 覆盖 `ops-analysis-report-table-builder` 中分享/PDF/订阅/周期刷新排除项、`ops-analysis-canvas-periodic-refresh` 中「报表 YAML 不加 refresh_interval」、以及 `canvas-report-subscription` 把 Report 列为非目标等历史边界。

## Testing Decisions

好的测试断言对外合同：分享 HTTP 200、订阅创建与 render-input 冻结布局、删除终止、refresh 字段 PATCH 不要求 `view_sets`、前端分享入口不再 Exclude report、render 页以 `renderMode` 挂载报表。

- 后端：`refresh_interval` 读写与分享 payload；`POST /api/report/:id/share/` 为 200；Adapter 注册、manifest、快照、创建订阅、执行 snapshot、render-input HTTP、删除终止；视口与仪表盘相同且不加 Screen fit。
- 前端：分享契约脚本承认 report；订阅 Modal 用 `resource_type=report` 创建；render 页消费冻结 Input Snapshot；既有 `reportBuilder` 行为不被工具栏改坏。

## Out of Scope

- 普通表格和事件表格之外的报表组件。
- 大屏策略 2（A4 单页等比缩小）套用到报表。
- Topology、Architecture、NetworkTopology 的报告订阅。
- 把报表分享会话当作订阅执行身份。
- 多收件人或非 email 渠道。
- 将 `DashboardReport*` 物理模型 rename 为 `CanvasReport*`。

## Further Notes

- 这里的「报表」始终指运营分析一等 `report` 画布。
- 报表纵向列表分页可读，优先于把整份画布塞进一页。
- 分享态周期刷新与仪表盘分享一致：按已保存 `refresh_interval` 自动静默刷新；访客改频率仅本次会话有效，不写回源画布。
## Completion Evidence

- 报表工具栏顺序：刷新 → 全屏 → PDF → 分享 → 订阅 → 编辑；分享态隐藏分享、订阅、PDF 与编辑；订阅 `renderMode` 无工具栏且关闭懒加载。
- 后端：`Report.refresh_interval`（migration `0029`）、YAML `ReportItem`、分享 payload；`POST /api/report/:id/share/` 返回 200；`ReportCanvasReportAdapter` 注册；删除终止 `report_deleted`；订阅 Chromium 视口与仪表盘相同且不加 Screen fit。
- 聚焦测试（2026-08-17）：
  - `cd server && uv run pytest apps/operation_analysis/tests/test_canvas_report_report_adapter.py apps/operation_analysis/tests/test_share_canvas_types.py apps/operation_analysis/tests/test_canvas_refresh_interval.py -q`：**40 passed**；补跑 `test_export_report_yaml_includes_refresh_interval`：**1 passed**
  - `cd web && pnpm exec tsx scripts/ops-analysis-dashboard-share-test.ts`：通过
  - `cd web && pnpm exec vitest run src/app/ops-analysis/components/__tests__/dashboardSubscriptionModal.test.tsx src/app/ops-analysis/render/__tests__/reportExecutionRenderPage.test.tsx src/app/ops-analysis/render/__tests__/screenExecutionRenderPage.test.tsx`：**24 passed**
- 已将稳定交付事实同步到
  `specs/capabilities/legacy-ard-modules-operation-analysis.md`。

# CMDB 扫描命中详情交互

Status: ready

## Problem Statement

扫描已经能发现设备并留下命中清单，但详情仍是窄抽屉里的卡片分组。未知 SOID 的网络命中和已识别设备混在一起，管理员既难看清「哪些还没进特征库」，也不能就地教会指纹或先把这几台推进监控 / 采集。未匹配的口径以后还会增加，不能把交互写死成「只有缺指纹」一种。

## Solution

把命中详情拉成大抽屉，用表格呈现。顶层拆成「已匹配」和「未匹配」两个 tab；未匹配按 SOID 分组。两条路径互不前置：可以给这条 SOID 写指纹并立刻认领本次执行，也可以不写指纹、只选手选类型后推监控或生成采集。跳转特征库只是检索口子，不代替扫描侧认领。

## User Stories

1. As a CMDB 管理员, I want 在加宽的命中抽屉里用表格查看本次执行结果, so that 我能按家族对照 IP、类型、品牌、型号和凭据，而不是翻卡片。
2. As a CMDB 管理员, I want 收口完成后在「未匹配」tab 里按 SOID 看到未进特征库的网络命中, so that 未知设备和已识别设备分开处理。
3. As a CMDB 管理员, I want 对某一 SOID 组打开添加指纹弹窗（OID 预填锁定），保存后本次相同 SOID 立刻建成 CI 并进入已匹配, so that 我不必等下次扫描才看到指纹生效。
4. As a CMDB 管理员, I want 在未匹配实例上勾选后直接推监控或生成采集，并只选择设备类型, so that 这一台可以先用起来，而不必先教特征库。
5. As a CMDB 管理员, I want 从扫描详情新开标签页跳到特征库并带上该 SOID 检索, so that 我可以对照整库，同时扫描抽屉和勾选还在。
6. As a CMDB 管理员, I want 已匹配 / 未匹配表格前端分页且跨页勾选保留, so that 批量推送不会因为翻页丢掉选择。

## Implementation Decisions

- 详情容器仍是抽屉，不新开路由。宽度约 80vw、上限约 1440px。任务列表留在背后。
- 顶层只有「已匹配」「未匹配」两个 tab。未匹配永远是一张（分组）表，行上带 `unmatch_reason`。网络未匹配产出 `unknown_soid` 和 `empty_soid`；数据库鉴权失败占位为 `credential_failed`（见 `cmdb-scan-port-fingerprint`）。以后新原因加枚举，不加第三、第四个顶层 tab。
- `unmatch_reason` 由命中序列化计算，不新加库字段：网络族且 `cmdb_model_id` 为空时，有 SOID 为 `unknown_soid`，无 SOID 为 `empty_soid`。三库族鉴权失败占位且 `cmdb_model_id` 为空时为 `credential_failed`。其它情况为空字符串。前端不得靠自己猜空模型。
- 执行仍为 pending / running / finalizing 时不拆未匹配：命中全部按族放在已匹配查看；添加指纹和选类型禁用。状态变为 completed / timed_out / failed 后再按 `unmatch_reason` 拆出未匹配。后端认领 / 手选分类在非终态时拒绝。
- 已匹配按家族分子 tab，只渲染本次有命中的族，每族一张表。网络列含 IP、sysname、类型、品牌、型号、SOID、凭据；主机含 IP、hostname、OS；库含 IP、端口、版本、凭据。
- 未匹配按 SOID 分组：父行是 SOID、台数、添加指纹；子行表格含 IP、sysname、SOID、凭据和原因。空 SOID 单独一组，仍可添加指纹（OID 可填），保存后把该 OID 回写到本组命中再认领。Path 2 勾选在子行，允许跨 SOID。
- 命中列表接口保持分页上界（现有 `page_size` 上限 200）。前端循环拉全量后再本地分页；禁止做无界 `page_size`。勾选按命中 id 保存，翻页不清空；组头勾选覆盖该 SOID 下全部实例。
- Path 1 与 Path 2 互不前置。写指纹不自动推监控、不自动生成采集。选类型推送不写特征库。
- Path 1：扫描抽屉上再盖 Modal（不套抽屉）。字段与特征库新增一致（设备类型、sysObjectID、品牌、型号，均必填）。已知 SOID 时 sysObjectID 预填且锁定；空 SOID 组可编辑 sysObjectID。创建走现有 OID 接口（`soid_library-Add`）。成功后对本次执行中该组未匹配网络命中回写 SOID、重新识别并建 CI。若 OID 已存在，跳过创建，只做本次认领。
- Path 2：未匹配勾选后点「推送监控」或「生成采集」，先弹四个网络类型（switch / router / firewall / loadbalance）。确认后只给这些命中建本实例 CI（品牌/型号沿用快照，未知保持未知），不写 `OidMapping`，再执行用户点的那一个出口。没有单独的「只识别、不推」按钮。空 SOID 只能走 Path 2。
- 认领与手选分类以命中 snapshot + 特征库 / 用户类型为准，不重打扫描枪、不强制重查 VictoriaMetrics。写 CI 仍走现有 mapping 控制器（允许新增），扫描只组行并回填 `cmdb_model_id` / `inst_uuid`。
- 本执行里已分类的行进入已匹配。下一次扫描同一未知 SOID 仍进未匹配，直到特征库有指纹。
- 跳转：新标签打开特征库路径并带 `oid` 查询参数，特征库用该值做 OID 检索，不自动弹出新增。跳转不触发认领。链接在 SOID 组行和添加指纹 Modal 各一处。
- 添加指纹按钮权限为 `soid_library-Add`（permissionPath 指向特征库）。推监控 / 生成采集 / 手选分类 / 认领扫描 CI 仍用 `auto_collection-Execute`。
- 新扫描动作：对某次执行认领指定 SOID；对选中命中按类型分类。二者都要校验命中属于该执行、执行已终态、只处理仍未匹配的网络行。
- 不改采集「未知当 switch」、不改 Stargazer、不改扫描触发与收口主路径。未知 SOID 自动收口仍不建网络 CI。

## Testing Decisions

只测外部行为：序列化给出的 `unmatch_reason`、认领 / 手选分类后的命中身份与是否写入特征库、非终态拒绝、已匹配行不被二次分类、未知 SOID 仍不经自动收口建成交换机。不测抽屉像素和 Ant Design 内部状态。

测试缝（沿用扫描现有缝，不新开运行时）：

- 命中序列化 / 身份纯函数：`unmatch_reason` 与网络四类约束。
- 扫描服务层：认领指定 SOID、手选类型建 CI；mock 图写入，断言命中回填、不写 `OidMapping`（Path 2）、写 `OidMapping` 后认领（Path 1）。
- 扫描 API：新动作的成功摘要、非法类型、非终态、空选择；沿用现有 ViewSet + `APIRequestFactory` 风格。
- 前端以类型检查覆盖表格 / tab 改动；特征库读取 `oid` 查询参数后发起 OID 检索。不强制为抽屉补 Playwright。

Prior art：`test_scan_identity.py`、`test_scan_finalize_service.py`、`test_scan_views.py`、`test_scan_push_monitor.py`。

## Out of Scope

- 扫描任务 CRUD、触发、进度、自动收口主路径。
- 按未匹配原因拆更多顶层 tab，或未匹配服务端按组分页。
- 手选分类时填写品牌/型号，或「只入库不推」第三条路径。
- 改采集未知 SOID 默认交换机、凭据中心、Redfish / 中间件 / 云扫描族。
- 独立执行详情页与分享深链。

## Further Notes

讨论对齐见 grilling；实现以本文为准。扫描纳管主规格仍是 `cmdb-scan-discovery`。端口指纹与统一数据库扫描见 `cmdb-scan-port-fingerprint`。入口不要占用空的 `featureLibrary/scanFeature` 页。

验证：`uv run pytest apps/cmdb/tests/test_scan_identity.py apps/cmdb/tests/test_scan_classify_service.py apps/cmdb/tests/test_scan_views.py --no-cov` 通过；`web` `pnpm type-check` 通过。sqlite 全量 migrate 在本地 alerts 历史迁移上失败，django_db 测试走现有 PostgreSQL 测试库。`test_scan_push_monitor.py::test_scan_push_does_not_import_monitor_internal_ingest` 为基线失败（注释里出现类名），本变更未改该文件。

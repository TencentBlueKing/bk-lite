# CMDB 扫描：清单驱动的显式落库 / 采集 / 推监控

Status: ready

## Problem Statement

扫描收口会自动写 CI，且依赖 VictoriaMetrics 指标；指标晚到时清单有数据、对象模型仍为空，生成采集被跳过。用户希望扫描只负责发现展示，是否进 CMDB、是否建采集、是否推监控由清单上手动决定；生成采集应挂已选实例，而不是再铺 IP 段。

## Solution

扫描收口只保留命中清单与 snapshot，不再自动写 CI、不再为写 CI 查 VM。任务上的「自动推监控 / 自动生成采集」去掉。终态清单对勾选行提供三个动作：写入 CMDB；写入 CMDB 并生成采集（按族合并为选择实例任务，凭据池可多把且扫描生成路径放开 3 把上限）；推送监控（必须已有 CI，不代写）。写 CI 只信命中 snapshot。网络未匹配须先手选类型或添加指纹后再写。

## User Stories

1. As a CMDB 管理员, I want 扫描结束后只看到发现清单而不自动进 CMDB, so that 发现与纳管解耦、不会误落库。
2. As a CMDB 管理员, I want 勾选命中后点「写入 CMDB」, so that 只把确认过的资产按 snapshot 建成 CI。
3. As a CMDB 管理员, I want 勾选后点「写入 CMDB 并生成采集」, so that 同一族多实例进一张选择实例采集任务，并合并多把命中凭据。
4. As a CMDB 管理员, I want 勾选后点「推送监控」且系统在无 CI 时拒绝, so that 监控入口始终挂在已落库资产上。
5. As a CMDB 管理员, I want 网络未匹配必须先分类再写入, so that 未知 SOID 不会被静默建成错误类型。
6. As a CMDB 管理员, I want 任务表单不再出现自动推监控 / 自动生成采集, so that 出口只发生在清单显式操作。

## Implementation Decisions

- 收口：删除自动写 CI、VM 拉指标写库与 `inst_uuid` 自动回填。凭据回传仍写命中与 snapshot。收口仍可做 OID→类型识别并写入 snapshot 建议类型，用于「已匹配 / 未匹配」拆分，但不写图。
- 「已匹配」口径：网络以特征库能识别 SOID（snapshot 有建议类型）为准；主机 / 库以凭据成功命中为准。写入前对象模型列为空；写入后回填模型与 `inst_uuid`。
- 三个按钮只处理勾选行；未勾选禁用或提示。执行非终态禁用。
- 写入 CMDB：只信 snapshot 组 mapping 行，复用现有图写入控制器（允许新增）。已有 `inst_uuid` 跳过；库 `credential_failed` 拒绝；网络未分类拒绝（`need_classify`）。
- 网络未匹配：保留添加指纹与手选四类；手选/认领可单独完成分类，写入按钮再落库。不再提供「未写 CI 直接生成采集 / 推监控」。
- 写入并生成采集：先写 CI；仅成功或已有 CI 的行进入生成。按族一张 CollectModels：`instances` 挂多 CI，`ip_range` 空，任务 `model_id` 为族（如 `network`/`host`/`postgresql`）。凭据池合并本批该族命中凭据；扫描生成路径放开采集凭据最多 3 把限制。默认周期、`input_method=AUTO`，认领图属性 `collect_task`。同扫描已生成的同族任务复用并并入 instances/凭据。主机带上扫描云区域 params。
- 推送监控：无 `inst_uuid` 则 `no_ci` 失败，不代写 CI。有 CI 则走现有 CMDB→Monitor 带凭据推送入口，成功回写 `monitor_id`/`cmdb_id`。
- 权限：三按钮沿用扫描执行权限；添加指纹沿用特征库新增权限。
- 前端：命中抽屉终态展示三按钮；任务创建/编辑去掉自动开关。网络选实例采集须保证插件按任务族 `model_id` 查找，实例上的 switch 等仅作 CI 类型。

## Testing Decisions

只测外部行为，不测 Stargazer 内部与抽屉像素。

- 收口后命中无 `inst_uuid`，且不调用写 CI / 不依赖 VM 覆盖。
- 写入 CMDB：snapshot 路径建 CI 并回填；已写入跳过；未分类网络拒绝；`credential_failed` 拒绝。
- 写入并生成采集：按族一张、instances 非空、ip_range 空、多凭据合并、超过 3 把仍成功（扫描路径）；写失败行不进生成。
- 推送监控：无 CI 失败；有 CI 走现有推送缝（mock IoC）。
- API：非终态 / 空勾选拒绝；返回逐行状态汇总。
- 前端：类型检查覆盖按钮与去掉自动开关；不强制 Playwright。

Prior art：现有 `test_scan_finalize_service`、`test_scan_classify_service`、`test_scan_collect_generate`、`test_scan_push_monitor`、`test_scan_views`、`test_scan_identity`。

## Out of Scope

- 修改 Stargazer 一枪协议与凭据事件 subject。
- 删除命中历史或扫描任务 CRUD 主路径。
- 把扫描本身做成 CollectModels。
- 手选分类时填写品牌/型号；凭据中心；Redfish / 中间件 / 云扫描族。
- 非扫描路径的采集凭据 3 把上限（仅扫描生成放开）。

## Further Notes

取代并修正 `cmdb-scan-discovery` 中「收口自动写 CI + IP 段生成采集 + 自动开关出口」相关决策；与 `cmdb-scan-hit-interaction` 的未匹配分类能力保留，但出口改为必须先（或一并）写入 CI。讨论对齐见本会话方案一。

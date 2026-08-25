# CMDB 一级「视图」工作台

Status: done

## Problem Statement

运维人员要看应用拓扑、K8S、网络拓扑、IP、机房机柜等专题视图时，必须先进入某个资产实例详情，再在关联关系或侧栏里找到对应 Tab。一级导航里的「视图」实际是模型卡片总览，并不能作为「先选视图、再切实例」的工作台。反复对比多台设备或多个机房时，路径长、上下文切换成本高。

## Solution

改造 CMDB 一级「视图」为带并列子项的导航：保留「资产总览」，并新增五个专题视图入口。用户可直接进入专题工作台，用顶部实例选择器切换合法实例；各专题独立记住上次实例。实例详情里原有专题入口与快捷方式保留，与一级视图双入口共存、共用同一套视图能力（含既有编辑能力）。

## User Stories

1. As an 运维人员, I want 在一级「视图」下看到资产总览与五个专题子导航, so that 不必先钻进实例详情就能进入专题视图
2. As an 运维人员, I want 点击父级「视图」时固定进入资产总览, so that 父项行为稳定可预期
3. As an 运维人员, I want 五个专题导航项始终可见, so that 菜单结构不因当前环境有无数据而跳动
4. As an 运维人员, I want 在专题工作台顶部用紧凑选择器搜索并切换合法实例，并看到最近访问, so that 画布空间不被侧栏占用且能快速回看常用实例
5. As an 运维人员, I want 各专题独立记住我上次查看的实例（浏览器本地）, so that 再次进入该专题时少重选
6. As an 运维人员, I want 首次进入无记忆、无 URL 参数时看到空态并可用同一套选择器选实例, so that 不会落到错误实例或空白死页
7. As an 运维人员, I want 实例选择器只列出该专题主题门控下的模型与实例, so that 不会选到不支持该视图的实例
8. As an 运维人员, I want 「机房机柜」作为一个导航项并在机房/机柜模式间切换, so that 物理空间类视图收在同一入口
9. As an 运维人员, I want 在画布上单击或「设为当前」将仍支持本视图的节点切为焦点实例, so that 我能在视图语境里连续浏览
10. As an 运维人员, I want 通过显式「查看详情」进入该实例的基础信息页, so that 查属性时有清晰出口且不打断默认浏览手势
11. As an 运维人员, I want 在机房平面图中单击机柜时可留在工作台并切到机柜模式, so that 机房到机柜的浏览不必先跳出到详情
12. As an 运维人员, I want 一级专题视图与详情内专题能力同权（含网络拓扑编辑等既有写操作）, so that 不会出现「一边能编一边不能」的认知分裂
13. As an 运维人员, I want 在实例详情侧栏仍使用网络拓扑/机房/机柜等快捷入口切到对应详情 Tab, so that 已在详情上下文时路径仍然最短
14. As an 有资产查看权限的用户, I want 能进入一级视图工作台且实例列表仍按实例读权限过滤, so that 不引入新的菜单权限点也能安全使用

## Implementation Decisions

- 一级「视图」改为带子项的导航分组。子项文案固定为：资产总览、应用拓扑、K8S 视图、网络拓扑、IP 视图、机房机柜。详情内 K8S 菜单文案可继续叫「资源详情」，一级用「K8S 视图」。
- 父级「视图」默认落地「资产总览」（沿用现有模型卡片总览页）。五个专题始终展示，不因环境无可用实例而隐藏或禁用导航项。
- 专题路由统一为 `/cmdb/views/<viewType>`，query 携带 `model_id`、`inst_id`；「机房机柜」另用 `mode=room|rack`。`viewType` 取值约定：`application`、`k8s`、`network`、`ip`、`rack-room`。
- 专题页使用独立工作台布局：无资产详情左侧子菜单；顶部为紧凑实例选择器（可搜索）+ 最近访问；主体为全宽画布/矩阵，复用详情中已有专题组件与工具条。
- 双入口共存：实例详情中的关联关系 Tab、IP 视图页、K8S 资源页及侧栏快捷入口保留原行为；一级视图不改为深链回详情壳的假入口。
- 实例资格与详情主题门控对齐，不放宽、不另造规则：
  - 网络拓扑：拓扑主题含 `network`
  - IP 视图：拓扑主题含 `ipam`（当前为 subnet）
  - 应用拓扑：拓扑主题含 `app_overview`（当前为 system / application）
  - K8S 视图：模型为 `k8s_cluster`
  - 机房机柜：`mode=room` 仅 `server_room`；`mode=rack` 仅 `rack`
- 各专题独立记忆上次实例（及机房机柜的上次 mode），键控为当前用户 × 视图类型，落在浏览器 `localStorage`；专题之间不继承实例。切换一级子导航只恢复目标专题自己的记忆。
- 「最近访问」是选择器增强，按专题维度本地记录，容量实现时可取小上限（例如每专题约 10 条），不另开产品访谈。
- 无 URL 实例且无本地记忆：渲染工作台壳 + 空态，引导使用同一套选择器；不自动挑选「第一条」实例，不做整页强制向导。
- 画布交互分层：单击或「设为当前」在目标实例仍支持当前专题时，更新焦点、URL 与记忆并重载本视图；显式「查看详情」一律进入该实例「基础信息」，不自动落到对应专题 Tab。机房平面图点机柜遵循同一分层：可留在工作台切到机柜模式；「查看详情」进基础信息。
- 权限：一级视图子项挂靠现有资产查看能力（与当前 `asset_info` 一致），不新增专题级权限点；实例选择与数据接口仍走既有实例读/写权限。能力与详情同权，含网络拓扑既有编辑。
- 菜单与路由需同步 CMDB 前端菜单源及系统管理侧菜单声明中与「视图」相关的结构，保证顶栏子项与权限挂载一致；不借此重做整棵 CMDB 权限模型。
- 本变更以前端信息架构、路由、工作台壳、选择器/记忆与组件复用为主；不新增专题数据后端 API，不改拓扑主题判定语义（除非发现与详情门控不一致的缺陷并在实现中对齐）。
- 同一期交付资产总览并列 + 五个专题全部可从一级进入；不分期留下半成品导航。

## Testing Decisions

- 好测试只验证外部行为：菜单结构与文案、路由/query 契约、实例资格过滤、记忆读写与分专题隔离、空态与「查看详情」落地、机房/机柜 mode 切换。不锁定 X6/画布内部事件名或具体 DOM 层级。
- 优先最高既有接缝：
  - 菜单配置与路由约定的静态/脚本断言（CMDB 现有 menu / K8S 资源脚本风格为 prior art）
  - 实例资格解析、记忆 key、最近访问列表、URL 构造等纯函数
  - 后端拓扑主题判定单测作为资格规则 prior art（本变更不改语义时以回归引用即可）
- 不强制本阶段完整浏览器 E2E；手动验收覆盖：五个专题进入与切换实例、无记忆空态、详情双入口仍可用、网络拓扑编辑在一级入口可用、机房→机柜留在工作台、查看详情进基础信息。

## Out of Scope

- 为专题视图新增独立权限点或改造 CMDB 整树权限模型
- 服务端持久化「上次实例」或跨设备漫游偏好
- 取消或搬迁实例详情内的专题 Tab / 侧栏快捷入口
- 修改拓扑主题判定规则本身（除与详情门控对齐所必需的缺陷修复）
- 为专题视图新建后端查询 API 或替换现有画布实现
- 移动端专用布局
- 将运营分析等其它产品中的拓扑/机房能力并入本工作台

## Further Notes

- 「资产总览」指现有模型卡片总览能力，本变更将其明确为一级「视图」下的子项，而不是用专题工作台替换它。
- 一级「K8S 视图」与详情「资源详情」指向同一能力面；双入口文案允许不同，但用户应能辨认为同一类能力。
- 若实现时发现顶栏「视图」与「资产」菜单 `name` 撞车等既有问题，仅在影响本变更挂载/高亮时做最小修正，不扩大为菜单系统重构。

## Completion Evidence

### Key files

- `web/src/app/cmdb/constants/menu.json` — 一级「视图」子项（资产总览 + 五专题）
- `web/src/app/cmdb/(pages)/views/[viewType]/page.tsx` — 专题路由入口
- `web/src/app/cmdb/(pages)/views/components/ViewsWorkspaceShell.tsx` — 工作台壳 / 选择器 / 记忆 / 查看详情
- `web/src/app/cmdb/(pages)/views/components/ViewInstancePicker.tsx` — 实例选择器
- `web/src/app/cmdb/(pages)/views/components/ViewCanvasHost.tsx` — 五专题画布复用接线
- `web/src/app/cmdb/(pages)/views/viewTypes.ts` / `viewEligibility.ts` / `viewMemory.ts` / `viewUrls.ts` — 类型、资格、记忆、URL
- 详情侧保留：`assetData/detail/relationships/*`、`ipView`、`k8sResources`、`side-menu` 快捷

### Tests (all PASS, 2026-08-12)

- `pnpm run test:cmdb-views-hub-core`
- `pnpm run test:cmdb-views-hub-menu`
- `pnpm run test:cmdb-views-hub-wiring`
- `pnpm run test:cmdb-k8s-resource-overview`
- `pnpm run test:cmdb-app-overview-wiring`
- `pnpm run test:cmdb-network-topo-editing`
- `pnpm run test:cmdb-relationships-imports`

### Tickets

- 01–08 Status: done（08 含静态 verified-via-code vs pending manual 清单）
- 未 archive；未 commit（按 Task 9 约束）

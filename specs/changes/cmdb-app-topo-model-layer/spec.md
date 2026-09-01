# CMDB 应用拓扑模型层级

Status: implemented

## Problem Statement

应用拓扑已经按五条带展示，但模型落到哪一条带是代码里的模型 ID 白名单。自定义模型几乎都会进「基础设施」，运维无法在不改代码的情况下把新模型摆到应用、主机或应用服务带。

## Solution

模型增加「应用拓扑层级」单选字段，内置模型用当前真实摆法做初始化。拓扑仍按关联跳数展开，该字段只决定画在哪一条带。模型管理和 `model_config.xlsx` 的 models 表都可维护这个字段。

## User Stories

1. As a CMDB 管理员, I want 在新建或编辑模型时选择应用拓扑层级, so that 自定义模型能出现在正确的展示带
2. As a CMDB 管理员, I want 有编辑权限时也能改内置模型的应用拓扑层级, so that 不必改代码或导入 Excel
3. As a CMDB 管理员, I want 不选时默认不分类, so that 未点名的模型不会误进某一条展示带
4. As a CMDB 管理员, I want 在模型配置 Excel 里导入导出该字段, so that 内置模型和跨环境迁移能带上分层
5. As an 运维人员, I want 打开应用拓扑时节点按模型所属层级落带, so that 图的分层和模型配置一致
6. As an 运维人员, I want 当前图的中心节点仍固定在系统带, so that 焦点应用系统不会因为模型字段跑到别的带

## Implementation Decisions

- 字段名 `app_topo_layer`，存图模型节点上。合法值：`system`、`service`、`host`、`appService`、`infrastructure`、`none`。没有 `root`；拓扑系统带同时容纳当前中心节点和 `system` 层模型。
- 新建模型默认 `none`（不分类）。内置赋值：`system` → 系统层；`application` → 服务层；主机及所有虚拟机/云主机 → 主机层；全部中间件与数据库（含云上同类）→ 应用服务层；物理设备、网络设备、机房机柜 → 基础设施层；其余 → 不分类。
- 页面用单选，选项为系统层/服务层/主机层/应用服务层/基础设施层/不分类。自定义模型编辑可改名称、组织、图标和层级。内置模型在具备「Edit Model」权限时可编辑，但只允许改应用拓扑层级。复制模型继承源模型的层级。
- Excel `models` sheet 增加中英双表头「应用拓扑层级 / `app_topo_layer`」。单元格接受英文键或中文名（系统/服务/应用/主机/应用服务/基础设施/不分类）。空单元格在新建时按模型默认映射写入；非法值拒绝导入。
- 官方初始化（`is_pre=True`）只给还没有该字段的已有内置模型补默认值，不覆盖已有值。需要把存量环境一次性对齐当前种子分层时，使用 `model_init --sync-app-topo-layer`。用户导入（`is_pre=False`）在 Excel 写了显式值时更新已有模型。
- 拓扑节点返回 `app_topo_layer`。前端：中心节点进系统带；`system` 进系统带；`none` 不进入五条展示带；其余用该字段。缺字段时回落到内置默认映射。
- 资源清单的数据库/中间件/缓存分组仍用现有类别映射，不改成四层。
- 加载和展开继续按关联跳数，不按层拉取模型实例。

## Testing Decisions

- 好测试只验证：合法/非法取值、默认映射字面量、创建默认值、更新可写、内置模型只允许改层级、复制继承、Excel 列与空/非法单元格、官方迁移不覆盖已有值、用户导入写显式值、拓扑节点带层、中心节点仍在系统带。
- 约定接缝：
  - `app_topo_layer` 纯函数（默认映射、归一化）
  - `ModelManage.create_model` / `update_model` / `copy_model`
  - `export_model_config` 与 `ModelMigrate` 导入/回填
  - `ApplicationResourceOverviewService.build_application_topology` 节点字段
  - 前端 `resolveLayer` 与模型弹窗接线脚本
- Prior art：`test_model_service_graph_mock.py`、`test_migrate_display_slice.py`、`test_application_resource_overview_service.py`、`web/scripts/cmdb-app-topology-layer-layout-test.ts`

## Out of Scope

- 按层加载或过滤拓扑
- 用户自定义层名或层数
- 资源清单分组改用该字段
- 网络拓扑、K8S 视图复用该字段
- 模型列表上展示层级列

## Further Notes

- 「系统层」是模型可选层，给应用系统模型；当前图中心节点仍固定在系统带。
- 「不分类」是模型可选层，未点名的内置模型和新建模型默认此项。
- 升级已有环境时，官方初始化默认只给还没有该字段的模型补默认值，不覆盖用户已改的层级；一次性对齐当前种子分层时使用 `model_init --sync-app-topo-layer`。

## Completion Evidence

- 后端 `--nomigrations` pytest：`test_app_topo_layer.py`、模型 CRUD/复制、Excel migrate/export、拓扑节点带层、种子列 `app_topo_layer` 均 PASS。
- 前端：`pnpm exec tsx scripts/cmdb-app-topo-resolve-layer-test.ts`、`cmdb-app-topo-model-layer-wiring-test.ts`、`cmdb-app-topology-layer-layout-test.ts` 均 PASS。

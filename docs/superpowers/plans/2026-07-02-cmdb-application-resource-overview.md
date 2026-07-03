# CMDB 应用资源全景视图 Implementation Plan

> `writing-plans` 技能当前不可用，本计划按仓库现有 `docs/superpowers/plans/` 风格直接编写，供后续实现逐项推进。

**Goal:** 在 `CMDB` 中新增“应用资源全景视图”，支持从 `应用系统(system)` 和 `应用(application)` 两类对象进入；应用详情页提供 `拓扑图` 与 `资源清单` 双视图，拓扑图支持点击节点展开与快速展开 1/2/3 层，资源清单按资源类型分组展示并支持导出。

**Architecture:** 以后端聚合服务为中心，在 `apps/cmdb/services/` 新增专用 overview 服务，统一完成入口对象解析、应用列表聚合、拓扑节点/连线组装、资源清单分组与导出数据整形；视图层通过 `InstanceViewSet` 暴露只读接口；前端在现有 CMDB 实例详情关系区追加“应用资源全景”主题页，并在系统入口下先展示应用列表，再进入应用详情里的双页签视图。

**Tech Stack:** Django 4.2 / DRF / pytest；Next.js 16 / React 19 / TypeScript / Ant Design；CMDB 图存储查询严格走 FalkorDB 语义。

**关键事实（实现前必读）：**
- 内置模型主干来自 `server/apps/cmdb/support-files/model_config.xlsx`：
  - `system` = 应用系统
  - `application` = 应用
  - `system --contains--> application`
  - `application --run--> host`
- 现有 CMDB 已有“网络拓扑”“机房机柜视图”这类只读结构视图，本功能产品形态应与其保持一致，而不是做成运营分析画布。
- 权限必须复用 CMDB 既有实例权限链路：中心实例先做 `require_instance_permission`，扩展节点继续走 `permission_map` 过滤，不能在新功能中另写一套权限规则。
- 图查询语法与实现边界遵循仓库红线：FalkorDB 语义优先，禁止把新功能设计成 Neo4j 专属语法路径。

---

## File Structure

**后端（server/）**
- 新：`apps/cmdb/services/application_resource_overview.py`
  - 负责入口对象解析、应用列表聚合、拓扑构建、资源清单聚合、导出数据整形。
- 新：`apps/cmdb/serializers/application_resource_overview.py`
  - 负责请求参数校验：入口对象、展开层级、资源类型过滤、导出参数。
- 改：`apps/cmdb/views/instance.py`
  - 新增 overview 相关只读 `@action`。
- 可能改：`apps/cmdb/constants/constants.py`
  - 放置本功能共用常量，例如最大快速展开层级、默认层级、资源类型分组枚举。
- 新测试：
  - `apps/cmdb/tests/test_application_resource_overview_service.py`
  - `apps/cmdb/tests/test_application_resource_overview_views.py`
  - 如有必要新增纯函数测试：`apps/cmdb/tests/test_application_resource_overview_pure.py`

**前端（web/）**
- 改：`src/app/cmdb/api/instance.ts`
  - 新增 overview 相关接口调用。
- 新：`src/app/cmdb/types/applicationResourceOverview.ts`
  - 定义应用列表、拓扑、清单、导出请求类型。
- 新：`src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/`
  - `index.tsx`
  - `applicationList.tsx`
  - `topologyView.tsx`
  - `resourceListView.tsx`
  - `hooks/*`
- 改：`src/app/cmdb/(pages)/assetData/detail/relationships/page.tsx`
  - 追加新主题入口，按 `modelId` 控制 system/application 的展示逻辑。
- 改：`src/app/cmdb/locales/zh.json`、`en.json`
  - 新增文案。

---

## Phase A — 后端领域建模与接口收口

### Task 1: 定义接口与常量

**目标：** 明确本功能的只读接口边界与请求参数，先把“入口对象 / 展开层级 / 清单分组 / 导出”这些产品语义固定下来。

**Files:**
- Modify: `server/apps/cmdb/constants/constants.py`
- Create: `server/apps/cmdb/serializers/application_resource_overview.py`
- Test: `server/apps/cmdb/tests/test_application_resource_overview_views.py`

- [ ] **Step 1: 写失败测试**
  - 为 system/application 两类入口分别写参数校验用例。
  - 校验快速展开层级仅允许 `1 / 2 / 3`。
  - 校验不支持的入口模型会被拒绝。

- [ ] **Step 2: 新增常量与请求 serializer**
  - 定义默认展开层级、最大展开层级、支持的入口模型、清单分组键。
  - 定义 overview 请求 serializer，显式约束请求参数。

- [ ] **Step 3: 跑视图层参数测试**
  - 确认非法参数被拒绝，合法参数可进入服务层。

---

### Task 2: system 入口的应用列表聚合

**目标：** 当用户从 `应用系统(system)` 进入时，先返回该系统下的应用列表，而不是直接返回系统级总拓扑。

**Files:**
- Create: `server/apps/cmdb/services/application_resource_overview.py`
- Test: `server/apps/cmdb/tests/test_application_resource_overview_service.py`

- [ ] **Step 1: 写失败测试**
  - system 入口能返回其 `contains` 的 application 列表。
  - 无 application 时返回空列表而不是报错。
  - 被权限裁掉的 application 不应返回。

- [ ] **Step 2: 实现应用列表聚合**
  - 基于 `system --contains--> application` 关系查询。
  - 输出应用基础信息，作为前端二次进入详情页的收敛层。

- [ ] **Step 3: 跑服务层测试**
  - 确认权限与空状态行为正确。

---

### Task 3: application 入口的拓扑聚合服务

**目标：** 从 `application` 进入时，返回收敛态拓扑，并支持点击节点展开与快速展开 1/2/3 层。

**Files:**
- Create: `server/apps/cmdb/services/application_resource_overview.py`
- Test: `server/apps/cmdb/tests/test_application_resource_overview_service.py`

- [ ] **Step 1: 写失败测试**
  - 首屏返回收敛态拓扑，不默认摊开全量资源。
  - 点击节点展开只对当前选中节点生效。
  - 快速展开 2 层/3 层只作用于当前节点。
  - 支持 `收起当前展开结果` 与 `回到初始视图` 的状态恢复。

- [ ] **Step 2: 实现拓扑主干聚合**
  - 先固化业务主干：`application -> host`。
  - 在主干基础上继续聚合软件层、承载层、硬件/空间层资源。
  - 输出统一节点/连线结构，显式标记节点类别与可展开状态。

- [ ] **Step 3: 实现快速展开**
  - 支持 `展开下一层`、`向下展开 2 层`、`向下展开 3 层`。
  - 返回展开后的增量结构或完整结构，路径由前后端统一约定。

- [ ] **Step 4: 跑服务层测试**
  - 覆盖收敛态、增量展开、快速展开、回退行为。

---

### Task 4: 资源清单分组与导出服务

**目标：** 当资源量大时，为同一应用提供按资源类型分组的清单视图，并支持导出。

**Files:**
- Create: `server/apps/cmdb/services/application_resource_overview.py`
- Test: `server/apps/cmdb/tests/test_application_resource_overview_service.py`

- [ ] **Step 1: 写失败测试**
  - application 入口能返回按资源类型分组的清单结构。
  - 导出仅导出当前应用可见资源。
  - 空分组、无资源、混合资源类型都能稳定返回。

- [ ] **Step 2: 实现资源清单聚合**
  - 首版固定分组：
    - 应用
    - 主机
    - 数据库
    - 中间件
    - 缓存
    - 消息队列
    - 硬件资源
    - 机房机柜
  - 对每组输出列表、数量与基础筛选信息。

- [ ] **Step 3: 实现导出数据整形**
  - 首版导出可以先走统一扁平表结构，保留资源类型字段。
  - 明确导出只基于当前应用上下文，不混入系统级全部数据。

- [ ] **Step 4: 跑服务层测试**
  - 确认清单分组与导出行为稳定。

---

### Task 5: 增加只读接口并复用权限链路

**目标：** 通过 `InstanceViewSet` 暴露 overview 相关接口，保持与现有 CMDB 结构视图一致的入口与权限模式。

**Files:**
- Modify: `server/apps/cmdb/views/instance.py`
- Test: `server/apps/cmdb/tests/test_application_resource_overview_views.py`

- [ ] **Step 1: 写失败测试**
  - system/application 两类入口分别走正确接口分支。
  - 无权限中心实例应被拒绝。
  - 非法展开层级与非法模型应被拒绝。

- [ ] **Step 2: 增加只读 action**
  - system 入口：应用列表接口。
  - application 入口：拓扑图接口、资源清单接口、导出接口。

- [ ] **Step 3: 复用既有权限校验**
  - 先做中心实例权限校验。
  - 扩展节点与清单资源继续走 `permission_map` 或等价现有权限工具过滤。

- [ ] **Step 4: 跑视图层测试**
  - 验证参数、权限、返回结构。

---

## Phase B — 前端详情页与双视图交互

### Task 6: 在关系页挂载“应用资源全景”主题入口

**目标：** 仅在 `system` 与 `application` 详情页展示该主题入口，避免误挂到其他模型。

**Files:**
- Modify: `web/src/app/cmdb/(pages)/assetData/detail/relationships/page.tsx`
- Modify: `web/src/app/cmdb/api/instance.ts`
- Modify: `web/src/app/cmdb/locales/zh.json`
- Modify: `web/src/app/cmdb/locales/en.json`

- [ ] **Step 1: 写失败测试或最小可验证脚本**
  - system/application 显示新主题。
  - 其他模型不显示。

- [ ] **Step 2: 新增 API hooks**
  - 拉取应用列表、拓扑图、资源清单、导出接口。

- [ ] **Step 3: 挂载主题入口**
  - 保持与现有网络拓扑、机房机柜视图相近的交互方式。

---

### Task 7: system 入口的应用列表视图

**目标：** 当中心对象是 `system` 时，先展示该系统下的应用列表，用户再进入单个应用详情。

**Files:**
- Create: `web/src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/applicationList.tsx`
- Create: `web/src/app/cmdb/types/applicationResourceOverview.ts`

- [ ] **Step 1: 实现系统下应用列表**
  - 支持空状态。
  - 支持点击进入单应用详情。

- [ ] **Step 2: 保持切换状态可控**
  - 用户从单应用详情返回时，仍能回到该系统下的应用列表。

---

### Task 8: application 详情页的拓扑图视图

**目标：** 实现收敛态拓扑、点击节点展开、快速展开 1/2/3 层、收起与回到初始视图。

**Files:**
- Create: `web/src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/topologyView.tsx`
- Create: `web/src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/hooks/useTopologyView.ts`

- [ ] **Step 1: 实现收敛态渲染**
  - 首屏只展示初始结构，不摊开全部资源。

- [ ] **Step 2: 实现节点展开交互**
  - 点击节点触发下一层展开。
  - 节点视觉上要能识别资源层级与是否可展开。

- [ ] **Step 3: 实现快速展开交互**
  - 明确提供：
    - `展开下一层`
    - `向下展开 2 层`
    - `向下展开 3 层`
  - 这些操作只作用于当前选中节点。

- [ ] **Step 4: 实现回退交互**
  - 支持 `收起当前展开结果`
  - 支持 `回到初始视图`

- [ ] **Step 5: 做最小前端验证**
  - system/application 两类入口切换稳定。
  - 快速展开不会导致整张图失控。

---

### Task 9: application 详情页的资源清单视图

**目标：** 提供按资源类型分组的清单浏览、筛选与导出。

**Files:**
- Create: `web/src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/resourceListView.tsx`

- [ ] **Step 1: 实现分组清单视图**
  - 固定分组与 spec 一致。
  - 每组展示资源数量与列表内容。

- [ ] **Step 2: 实现基础筛选与搜索**
  - 先做组内筛选与全文检索的最小可用版本。

- [ ] **Step 3: 实现导出交互**
  - 明确导出当前应用上下文的资源清单。

---

## Phase C — 联调、验收与回归

### Task 10: 后端与前端联调

- [ ] **Step 1: 联调 system 入口**
  - 系统进入后先看到应用列表。

- [ ] **Step 2: 联调 application 入口**
  - 直接进入双视图详情页。

- [ ] **Step 3: 验证拓扑交互**
  - 点击展开、快速展开 1/2/3 层、收起、回到初始视图均可用。

- [ ] **Step 4: 验证资源清单**
  - 分组、筛选、导出符合 spec。

---

### Task 11: 测试与质量门禁

- [ ] **Step 1: 跑后端测试**
  - `cd server && make test`

- [ ] **Step 2: 跑前端检查**
  - `cd web && pnpm lint && pnpm type-check`

- [ ] **Step 3: 做最小人工验证**
  - 从 `system` 与 `application` 两类入口分别走一遍核心流程。

---

## 交付标准

- 用户能从 `system` 进入，先看到系统下应用列表，再进入单应用详情。
- 用户能从 `application` 直接进入资源全景详情。
- 详情页存在两个稳定页签：
  - `拓扑图`
  - `资源清单`
- 拓扑图支持：
  - 点击节点展开
  - 快速展开 1/2/3 层
  - 收起当前展开结果
  - 回到初始视图
- 资源清单支持：
  - 按资源类型分组
  - 基础筛选与搜索
  - 导出

## 建议提交拆分

1. `feat(cmdb): 新增应用资源全景后端聚合服务`
2. `feat(cmdb): 新增应用资源全景只读接口`
3. `feat(web): 新增应用资源全景双视图`
4. `test(cmdb): 补充应用资源全景服务与视图测试`

# Historical Superpowers change: 2026-07-02-cmdb-application-resource-overview

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-02-cmdb-application-resource-overview.md

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

## specs: 2026-07-02-cmdb-application-resource-overview-design.md

- 日期：2026-07-02
- 模块：CMDB
- 状态：设计已确认，待写实现计划
- 类型：新增功能

## 1. 背景与问题

当前 CMDB 已有多种结构化视图能力，例如：

- 网络拓扑：适合看网络设备之间的连接关系。
- 机房/机柜视图：适合看物理空间与设备上架关系。

但对于客户更常见的一个问题，现有产品仍然缺少统一视角：

> 以某个应用或应用系统为中心，快速看清它使用到了哪些资源，这些资源分别落在哪些软件层和硬件层，并在资源量大时支持清单化查看与导出。

现有内置模型配置中，业务主干已具备基础语义：

- `system`：应用系统
- `application`：应用
- `system --contains--> application`
- `application --run--> host`

这说明 CMDB 已具备“业务对象到资源对象”的基础建模能力，但缺少一个面向客户心智的聚合视图，把应用、软件资源、硬件资源放到同一个入口下查看。

## 2. 目标

新增一个位于 `CMDB` 内的 `应用资源全景视图`，满足以下目标：

1. 支持从 `应用系统` 和 `应用` 两类对象进入。
2. 以 `应用` 为中心，统一展示其关联的软件资源与硬件资源。
3. 同时提供：
   - `拓扑图视图`：适合看结构、上下游、层次关系。
   - `资源清单视图`：适合资源量大时浏览、筛选、导出。
4. 拓扑图支持逐步展开与快速展开，避免首屏一次性摊开全部资源。
5. 从 `应用系统` 进入时，先收敛到“系统下的应用列表”，再进入单个应用详情，避免系统级大图失控。

## 3. 非目标

1. 不做运营分析画布或通用拓扑编辑器。
2. 不做自由绘制、拖拽连线、手工编排节点位置。
3. 不要求首版解决所有模型的自动展示问题。
4. 不做历史回放、版本对比、时间轴变化分析。
5. 不把该功能做成独立于 CMDB 的新模块。

## 4. 用户需求抽象

客户的真实需求不是“再做一张拓扑图”，而是：

- 想知道某个应用依赖了哪些资源。
- 想把软件资源和硬件资源放到一个统一视角中查看。
- 想在资源较少时快速看懂结构关系。
- 想在资源很多时用表格方式盘点、筛选、导出。

因此，该功能的本质是：

> `以应用为中心的资源全景视图`

而不是单纯的“应用部署图”或“网络拓扑图”。

## 5. 产品结构

### 5.1 入口对象

首版同时支持两类入口：

- `应用系统（system）`
- `应用（application）`

### 5.2 从应用系统进入

从 `应用系统` 进入时，默认不直接展示系统级总拓扑，而是先展示该系统下的 `应用列表`。

原因：

- 系统下可能有多个应用，直接总览容易造成信息爆炸。
- 用户更常见的操作是先确认目标应用，再进入该应用的资源全景。
- 这样也更符合 CMDB 中“先收敛、再下钻”的浏览方式。

### 5.3 从应用进入

从 `应用` 进入时，直接进入该应用的 `资源全景详情页`。

### 5.4 应用详情页

应用详情页提供两个并列页签：

- `拓扑图`
- `资源清单`

二者表达的是同一批资源，只是展示方式不同。

## 6. 拓扑图视图

## 6.1 目标

拓扑图视图用于回答：

- 这个应用关联了哪些资源？
- 这些资源处于哪些层次？
- 哪些资源属于软件层，哪些属于硬件层？
- 如果继续往下看，还能展开到什么深度？

## 6.2 默认状态

首屏必须是 `收敛态`，不能默认把所有关联资源全部展开。

原因：

- 应用资源一多，整图会立即失去可读性。
- 用户第一次进入时，更需要一个稳定、可理解的起点。

## 6.3 主交互

拓扑图的默认主交互为：

- `点击节点展开`

用户点击某个节点后，可继续查看该节点下的下一层关联资源。

这比一次性摊开更符合 CMDB 逐步探索的使用习惯。

## 6.4 快速展开

除单点逐层展开外，拓扑图需要提供 `快速展开` 能力，满足用户快速看深层结构的诉求。

首版固定提供以下快速展开操作：

- `展开下一层`
- `向下展开 2 层`
- `向下展开 3 层`

约束：

- 快速展开应对 `当前选中节点` 生效，而不是整张图全量生效。
- 快速展开后，用户仍应能继续手动展开更深层信息。
- 需要提供 `收起当前展开结果` 与 `回到初始视图` 两个明确操作，避免图面不可恢复。

## 6.5 图中资源范围

拓扑图不是纯业务对象图，也不是纯基础设施图，而是要同时覆盖：

- 业务对象层：应用系统、应用
- 软件资源层：数据库、中间件、缓存、消息队列、Web 容器等
- 承载资源层：主机、虚拟机、物理机
- 硬件/空间层：磁盘、网卡、内存、GPU、机柜、机房等

但首版仍应保证图面可读，不以“展示越多越好”为目标。

## 6.6 视觉原则

拓扑图需要让用户一眼区分不同层次资源，因此首版必须具备以下视觉区分：

- 节点类型区分：业务对象、软件资源、承载资源、硬件/空间资源
- 可展开状态提示：用户能感知该节点后续还有内容
- 资源过多提示：当某类资源很多时，优先提示，不直接把图炸开

## 7. 资源清单视图

## 7.1 目标

资源清单用于承接“量大时不适合看图”的场景。

它回答的是：

- 这个应用到底关联了哪些资源？
- 各类资源分别有多少？
- 能否快速筛选、检索、导出？

## 7.2 组织方式

资源清单默认按 `资源类型分组` 展示，而不是按统一大表混排。

首版按以下资源类型分组展示：

- 应用
- 主机
- 数据库
- 中间件
- 缓存
- 消息队列
- 硬件资源
- 机房机柜

选择按资源类型分组的原因：

- 更符合用户盘点资源时的自然心智。
- 比按依赖层级更稳定，也更适合导出。
- 比统一大表更容易浏览。

## 7.3 清单能力

资源清单首版固定支持：

- 资源分组查看
- 基础筛选
- 搜索
- 导出

导出的目标不是替代图，而是满足：

- 资产盘点
- 交付留档
- 离线分析
- 二次汇报

## 8. 应用系统入口的交互

当用户从 `应用系统` 进入时，页面先展示该系统下的 `应用列表`，而不是直接显示大拓扑。

该列表承担两个作用：

1. 作为系统级入口的收敛层，避免一进来信息过载。
2. 作为应用详情页的选择器，让用户快速切换目标应用。

在此基础上，用户点击某个应用后，再进入对应的：

- 拓扑图
- 资源清单

## 9. 方案选择

本设计采用：

> `拓扑图 + 资源清单双视图`

不采用“纯拓扑型”的原因：

- 资源量大时可读性快速下降。
- 无法很好承接筛选、盘点、导出类需求。

不采用“清单优先，拓扑辅助”的原因：

- 无法满足客户快速理解结构和依赖关系的诉求。
- 在演示与排障场景中，结构视图价值不足。

双视图方案同时满足：

- 看结构
- 查清单
- 做导出

是当前需求下最平衡的产品方案。

## 10. 成功标准

该功能上线后，用户应能完成以下典型动作：

1. 从 `应用系统` 进入，快速找到目标应用。
2. 从 `应用` 进入，查看该应用使用到的软件和硬件资源。
3. 在拓扑图中通过点击节点和快速展开，理解更深层依赖关系。
4. 在资源量较大时，切换到资源清单进行分组浏览、筛选和导出。

## 11. 范围边界

**In Scope**

- CMDB 内新增 `应用资源全景视图`
- 支持 `应用系统` 和 `应用` 两类入口
- 应用详情页提供 `拓扑图` 与 `资源清单` 双视图
- 拓扑图支持点击展开与快速展开 1/2/3 层
- 资源清单按资源类型分组并支持导出

**Out of Scope**

- 通用拓扑画布编辑
- 任意对象的自由视图编排
- 历史版本比对和时间回放
- 跨模块迁移到运营分析
- 首版即做成高度可配置的平台化规则中心

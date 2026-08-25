# APM 部署域最小闭环

Status: implemented

前置：`specs/changes/apm-deployment-event-materialize/spec.md`（已合入，`ApmDeploymentEvent` 已由目录对账增量物化，首页读表）。

## 目标与范围

补齐部署数据的产品承接面。当前前端只保留首页近 7 天 5 条摘要、服务详情「部署」Tab；独立部署列表暂不作为菜单或下钻入口。后端 `GET /api/v1/apm/deployments/`、物化写入与组织隔离保持不变，供详情 Tab 读取，并给后续 CI/CD 上报留列表闭环。全部读 `ApmDeploymentEvent`，不新增 VictoriaTraces 查询，不接 CI/CD 上报，不做版本对比/回归检测/时序标线。

信息架构决定：**不新增一级菜单**，服务二级仍为 服务 / 拓扑 / SLO。`/apm/services/deployments` 仅保留为旧链重定向到服务目录，避免被 `[serviceId]` 当成服务 ID。详情 Tab 复用 `services-View`，不新增权限声明。

## 后端

### API：`GET /api/v1/apm/deployments/`

新文件 `server/apps/apm/views/deployments.py`，`ApmDeploymentEventViewSet(viewsets.ViewSet)` 或 ReadOnlyModelViewSet，注册到 `urls.py` router：`router.register(r"deployments", ..., basename="apm-deployment")`。

- 权限：`@HasPermission("services-View")`；renderer 用 `ApmRenderer`。
- 组织隔离：`filter_current_organization(queryset, request, "service__organization_links")`；`current_organization_id` 为 None 时返回空列表（fail-closed，勿返回全量）。
- 排除已归档服务：`service__archived_at__isnull=True`。
- 查询参数（新增 `ApmDeploymentQuerySerializer`，放 `serializers/control_plane.py`）：
  - `service_id`：UUID，可选。
  - `environment`：CharField max 256，可选，按 `normalize_identity` 后精确匹配。
  - `status`：ChoiceField，`success / in_progress / rollback / failed`，可选。
  - `started_at / ended_at`：可选；默认近 7 天，跨度上限 90 天（对齐推断保留期），校验模式抄 `ApmAlertQuerySerializer`。
- 分页：`ApmCatalogPagination`（显式 page/page_size，上限 100），默认按 `-deployed_at, -id` 排序，`select_related("service")` 防 N+1。
- 响应行字段（新增 `ApmDeploymentEventSerializer`，显式列字段，禁 `__all__`）：
  `id, service_id, service_namespace, service_name, environment, version, deployed_at, deployed_by, status, source`。
  `service_namespace/service_name` 用 `source="service.namespace"` 只读映射（模式抄 `ApmSloSerializer`）。

不改写模型、迁移与写入路径。该 API 为平台内部登录态接口，不经 OpenAPI 网关（与现有 `slos`、`alerts` 等 viewset 同类）。

### 后端测试（新 `server/apps/apm/tests/test_deployment_api.py`）

1. 组织隔离双向：org 10 只见自己服务的事件，org 20 同理；跨组织事件不可见。
2. 无权限用户 403（复用 `apm_user_without_permissions` 模式）。
3. `service_id` / `environment` / `status` 过滤生效。
4. 时间窗默认近 7 天；`ended_at - started_at > 90d` 返回 400。
5. 分页上限：`page_size=1000` 被钳到 100 以内（断言分页类行为即可）。
6. 已归档服务的事件不返回。

## 前端

### 1. 部署列表页暂不展示

`web/src/app/apm/services/deployments/page.tsx` 只做 `redirect('/apm/services')`，不渲染事件表。推断阶段跨服务列表没有独立任务，CI/CD 上报后再作为工作台打开。

### 2. 菜单 `web/src/app/apm/constants/menu.json`

服务二级不挂「部署」。菜单脚本不得再要求 `/apm/services/deployments` 作为可见入口。

### 3. 服务详情「部署」Tab `web/src/app/apm/services/[serviceId]/page.tsx`

替换现有占位（`deployEmpty` 文案）：

- 进 Tab 时调 `getDeployments({ service_id })`（懒加载即可，模式抄同页其他 Tab）。
- `ApmDataTable` 列：版本 / 环境 / 发布时间 / 状态 / 来源；无部署人列（该页服务已知）。
- 表格上方一行 secondary 文案：「由遥测推断的发布记录」。
- 空态文案改为：「近 90 天未观测到版本变化」；删除 zh/en 旧 `deployEmpty` 文案或改写其内容。

### 4. 首页 `web/src/app/apm/home/page.tsx`

- 发布段保留近 7 天最多 5 条，**不设**「查看全部 →」。
- 发布行服务名链到该服务详情；部署人在推断源下为空即不显示。

### 5. API hook 与类型

- `web/src/app/apm/api/index.ts`：新增 `getDeployments`，`get<ApmPaged<ApmDeploymentEvent>>('/apm/deployments/', { params })`（分页返回结构以现有 `getInstancePage` 的封装为准）。
- `web/src/app/apm/types.ts`：新增 `ApmDeploymentEvent`（字段同 API 响应，`source: 'inferred' | 'reported'` 必填）；`ApmDashboardReleaseRow` 保持不变。

### 6. i18n

`locales/zh.json` / `en.json` 保留详情 Tab 用到的 `apm.deployments.version / deployedAt / source / sourceInferred / sourceReported`；列表页文案随入口撤回。状态四态文案复用现有 `apm.home.release*`。

### 前端测试

1. `apm-service-workflow-test.ts`：`/apm/services/deployments` 必须 `redirect`，不得再渲染事件表。
2. 服务详情测试：部署 Tab 渲染事件行而非占位文案。
3. `home/__tests__/page.test.tsx`：发布段不得再链到 `/apm/services/deployments`。
4. 菜单脚本：服务二级仅为 服务 / 拓扑 / SLO。

## 文档同步

- `spec/requirements/APM/PRD/首页.md` §3.7：最多 5 条，不提供独立部署列表下钻；行点击进入服务详情。
- `spec/requirements/APM/PRD/服务.md`：服务详情「部署」Tab 为推断部署记录表格。

## 非目标

- CI/CD 上报、部署人真实数据、失败态（第 3 步）。
- 版本对比、回归检测、端点 delta、RED 时序部署标线。
- 一级「部署追踪」菜单与单部署详情页。
- 修改 `ApmDeploymentEvent` 模型、写入逻辑或保留策略。

## 验收

- 服务菜单不出现「部署」子项；旧 URL `/apm/services/deployments` 重定向到服务目录。
- 部署列表 API 跨组织不可见；无权限 403；服务详情 Tab 可按 `service_id` 读取。
- 服务详情「部署」Tab 展示该服务版本时间线，不再是占位文案。
- 首页发布段展示近 7 天最多 5 条，无「查看全部 →」。
- 全链路无新增 VictoriaTraces 查询（仅 ORM 读表）。
- 后端 `uv run pytest apps/apm/tests/test_deployment_api.py` 及既有 APM 测试通过；前端相关 vitest 通过。

## 完成证据

- 后端：`uv run pytest apps/apm/tests/test_deployment_api.py --no-cov` → **7 passed**（含组织隔离双向、403、过滤、7 天默认/90 天上限、page_size 钳制、未传 page_size 仍分页、归档排除）。关联 `test_dashboard_api.py` / `test_dashboard_service.py` / `test_catalog_list_api.py` 共 32 passed。
- 前端：vitest 服务详情部署 Tab、首页发布段（无列表下钻）；`apm-menu-route-test`、`apm-service-workflow-test`、`apm-home-workflow-test`、`apm-i18n-coverage-test` 通过。独立列表页改为旧链重定向。

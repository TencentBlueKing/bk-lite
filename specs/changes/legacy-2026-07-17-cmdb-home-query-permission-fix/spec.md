# Historical Superpowers change: 2026-07-17-cmdb-home-query-permission-fix

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-17-cmdb-home-query-permission-fix.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让仅具备 `search-View` 或 `asset_info-View` 的 normal 用户完整加载 CMDB 首页且不出现 403，同时保持模型写操作和完整操作日志 fail-closed。

**Architecture:** 对模型、分类和实例统计的既有只读入口做当前权限名的等价回滚，继续复用对象级数据裁剪。最近资产变更使用独立的有界只读 action，前端首页只切换该数据源，通用操作日志列表与所有写接口保持原权限。

**Tech Stack:** Python 3.12、Django 4.2、Django REST Framework、pytest、Next.js 16、React 19、TypeScript、pnpm/tsx。

## Global Constraints

- 只读首页入口允许 `search-View`、`asset_info-View`；模型管理用户继续通过 `model_management-View` 读取模型元数据。
- 不给 normal 角色补发 `model_management-View` 或 `operation_log-View`。
- 不改变模型、实例和操作日志现有对象级/组织级数据权限算法。
- 模型 create/update/destroy 与通用操作日志 list/retrieve/export 的权限不得放宽。
- 最近资产变更只允许 `device_lifecycle`、`relation_change`、`ordinary_attribute_change`、`collect_automation_change`，单页最多 100 条。
- 所有生产修改先有可观察的 RED，再做最小 GREEN；新增/修改代码覆盖率不低于 75%，权限及过滤分支目标不低于 90%。
- 禁止原生 SQL；只运行触及文件格式化，避免全仓格式污染。

## 文件职责

- `server/apps/cmdb/views/model.py`：模型列表功能权限入口；保留模型级权限裁剪。
- `server/apps/cmdb/views/classification.py`：首页分类元数据功能权限入口。
- `server/apps/cmdb/views/instance.py`：首页模型实例统计功能权限入口；保留实例范围裁剪。
- `server/apps/cmdb/views/change_record.py`：首页最近资产变更的场景白名单、有界分页和功能权限。
- `server/apps/cmdb/tests/test_model_views.py`：模型列表正反向功能权限与写权限回归。
- `server/apps/cmdb/tests/test_misc_views.py`：分类列表正反向功能权限回归。
- `server/apps/cmdb/tests/test_instance_views.py`：实例统计正反向功能权限和权限映射透传回归。
- `server/apps/cmdb/tests/test_change_record_views.py`：首页最近变更白名单、分页上限及通用日志隔离回归。
- `web/src/app/cmdb/api/changeRecord.ts`：公开首页最近变更 API 方法。
- `web/src/app/cmdb/(pages)/assetSearch/page.tsx`：首页最近变更切换到专用 API。
- `web/scripts/cmdb-home-query-permission-test.ts`：首页最近变更接线回归。
- `web/package.json`：注册前端聚焦测试命令。

---

### Task 1: 放开首页基础元数据只读权限

**Files:**
- Modify: `server/apps/cmdb/tests/test_model_views.py`
- Modify: `server/apps/cmdb/tests/test_misc_views.py`
- Modify: `server/apps/cmdb/tests/test_instance_views.py`
- Modify: `server/apps/cmdb/views/model.py:108`
- Modify: `server/apps/cmdb/views/classification.py:14`
- Modify: `server/apps/cmdb/views/instance.py:1441-1445`

**Interfaces:**
- Consumes: `HasPermission` 逗号分隔权限采用“任一命中即通过”的既有语义；`request.user.permission` 形如 `{"cmdb": {"search-View"}}`。
- Produces: 模型/分类列表接受 `model_management-View | asset_info-View | search-View`；实例统计接受 `asset_info-View | search-View`。

- [ ] **Step 1: 为模型列表写 RED 权限合同**

在 `test_model_views.py` 的 list 测试旁新增：

```python
@pytest.mark.django_db
@pytest.mark.parametrize("permission", ["search-View", "asset_info-View"])
def test_list_models_allows_home_read_permissions(authenticated_user, monkeypatch, permission):
    user = authenticated_user
    user.is_superuser = False
    user.locale = "zh-Hans"
    user.group_list = [{"id": 1}]
    user.permission = {"cmdb": {permission}}
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model",
        lambda language=None, permissions_map=None, **kwargs: [{"model_id": "host", "group": [1]}],
    )

    response = ModelViewSet.as_view({"get": "list"})(_req("get", user))

    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"][0]["model_id"] == "host"


@pytest.mark.django_db
def test_list_models_denies_user_without_home_or_management_view(authenticated_user):
    user = authenticated_user
    user.is_superuser = False
    user.permission = {"cmdb": set()}

    response = ModelViewSet.as_view({"get": "list"})(_req("get", user))

    assert response.status_code == status.HTTP_403_FORBIDDEN
```

- [ ] **Step 2: 为分类列表和实例统计写 RED 权限合同**

在 `test_misc_views.py` 增加分类合同：

```python
@pytest.mark.django_db
@pytest.mark.parametrize("permission", ["search-View", "asset_info-View"])
def test_classification_list_allows_home_read_permissions(authenticated_user, monkeypatch, permission):
    user = authenticated_user
    user.is_superuser = False
    user.locale = "zh-Hans"
    user.permission = {"cmdb": {permission}}
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.search_model_classification",
        lambda locale, **kwargs: [{"classification_id": "net"}],
    )

    response = ClassificationViewSet.as_view({"get": "list"})(_req("get", user))

    assert response.status_code == status.HTTP_200_OK
```

在 `test_instance_views.py` 增加统计合同，并断言原数据权限映射仍传给 Service：

```python
@pytest.mark.django_db
@pytest.mark.parametrize("permission", ["search-View", "asset_info-View"])
def test_model_inst_count_allows_home_read_permissions(authenticated_user, monkeypatch, permission):
    user = authenticated_user
    user.is_superuser = False
    user.permission = {"cmdb": {permission}}
    seen = {}

    def fake_count(*, permissions_map, creator):
        seen.update(permissions_map=permissions_map, creator=creator)
        return {"host": 2}

    monkeypatch.setattr(f"{VIEWS}.InstanceManage.model_inst_count", fake_count)
    response = _call({"get": "model_inst_count"}, _req("get", user))

    assert response.status_code == status.HTTP_200_OK
    assert seen["permissions_map"] == {1: {"permission_instances_map": {}, "inst_names": []}}
    assert seen["creator"] == user.username
```

- [ ] **Step 3: 运行 RED，确认失败原因是功能权限拒绝**

Run（工作目录 `server/`）：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_model_views.py::test_list_models_allows_home_read_permissions \
  apps/cmdb/tests/test_misc_views.py::test_classification_list_allows_home_read_permissions \
  apps/cmdb/tests/test_instance_views.py::test_model_inst_count_allows_home_read_permissions
```

Expected: 参数化用例因当前装饰器不接受 `search-View`/`asset_info-View` 而返回 403；不是 Graph、DB 或 fixture 初始化错误。

- [ ] **Step 4: 实施当前权限名的等价回滚**

在三个 View 方法仅修改装饰器：

```diff
# apps/cmdb/views/model.py
-    @HasPermission("model_management-View")
+    @HasPermission("model_management-View,asset_info-View,search-View")
     def list(self, request):

# apps/cmdb/views/classification.py
-    @HasPermission("model_management-View")
+    @HasPermission("model_management-View,asset_info-View,search-View")
     def list(self, request):

# apps/cmdb/views/instance.py
     @action(methods=["get"], detail=False, url_path=r"model_inst_count")
-    @HasPermission("asset_info-View")
+    @HasPermission("asset_info-View,search-View")
     def model_inst_count(self, request):
```

不要修改方法体、`format_user_groups_permissions` 或模型写操作装饰器。

- [ ] **Step 5: 运行 GREEN 与写权限回归**

Run（工作目录 `server/`）：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_model_views.py \
  apps/cmdb/tests/test_misc_views.py \
  apps/cmdb/tests/test_instance_views.py
```

Expected: 全部 PASS；新增无权限用户仍为 403，既有 create/update/destroy 权限测试不回归。

- [ ] **Step 6: 提交基础查询权限修复**

```bash
git add server/apps/cmdb/views/model.py server/apps/cmdb/views/classification.py server/apps/cmdb/views/instance.py \
  server/apps/cmdb/tests/test_model_views.py server/apps/cmdb/tests/test_misc_views.py server/apps/cmdb/tests/test_instance_views.py
git commit -m "fix(cmdb): 恢复首页基础查询权限"
```

---

### Task 2: 建立有界的首页最近资产变更入口

**Files:**
- Modify: `server/apps/cmdb/tests/test_change_record_views.py`
- Modify: `server/apps/cmdb/views/change_record.py`

**Interfaces:**
- Consumes: `ChangeRecordFilter` 的 `operator`、`type`、`scenarios` 等既有查询参数。
- Produces: `GET /cmdb/api/change_record/home_recent/`，返回 `{"count": int, "items": ChangeRecord[]}`，默认 10 条、最大 100 条，仅包含四种资产场景。

- [ ] **Step 1: 写首页 action 的 RED 权限与隔离测试**

在 `test_change_record_views.py` 增加：

```python
from apps.cmdb.models.change_record import (
    DEVICE_LIFECYCLE,
    MODEL_MANAGEMENT_CHANGE,
    ORDINARY_ATTRIBUTE_CHANGE,
)


@pytest.fixture
def normal_user(authenticated_user):
    user = authenticated_user
    user.is_superuser = False
    user.locale = "zh-Hans"
    return user


@pytest.mark.django_db
@pytest.mark.parametrize("permission", ["search-View", "asset_info-View"])
def test_home_recent_allows_home_read_permissions(normal_user, record, permission):
    normal_user.permission = {"cmdb": {permission}}

    response = ChangeRecordViewSet.as_view({"get": "home_recent"})(_req("get", normal_user))

    assert response.status_code == 200
    assert _body(response)["count"] == 1


@pytest.mark.django_db
def test_home_recent_filters_non_asset_scenarios(normal_user, record):
    normal_user.permission = {"cmdb": {"search-View"}}
    ChangeRecord.objects.create(
        inst_id=2,
        model_id="host",
        label="主机",
        type="update_entity",
        operator="admin",
        model_object="主机",
        message="修改模型",
        scenario=MODEL_MANAGEMENT_CHANGE,
    )

    response = ChangeRecordViewSet.as_view({"get": "home_recent"})(_req("get", normal_user))
    scenarios = {item["scenario"] for item in _body(response)["items"]}

    assert scenarios == {ORDINARY_ATTRIBUTE_CHANGE}


@pytest.mark.django_db
def test_home_recent_caps_page_size_and_generic_list_stays_denied(normal_user):
    normal_user.permission = {"cmdb": {"asset_info-View"}}
    ChangeRecord.objects.bulk_create([
        ChangeRecord(
            inst_id=index,
            model_id="host",
            label="主机",
            type="create_entity",
            operator="admin",
            model_object="主机",
            message=f"创建实例 {index}",
            scenario=DEVICE_LIFECYCLE,
        )
        for index in range(1, 106)
    ])

    home_response = ChangeRecordViewSet.as_view({"get": "home_recent"})(
        _req("get", normal_user, query="page=1&page_size=1000")
    )
    list_response = ChangeRecordViewSet.as_view({"get": "list"})(_req("get", normal_user))

    assert len(_body(home_response)["items"]) == 100
    assert list_response.status_code == 403
```

- [ ] **Step 2: 运行 RED，确认 action 尚不存在**

Run（工作目录 `server/`）：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_change_record_views.py -k home_recent
```

Expected: FAIL，`ChangeRecordViewSet` 尚无 `home_recent` action；已有通用 list 测试保持原状。

- [ ] **Step 3: 实现白名单与有界分页**

在 `change_record.py` 增加四场景常量导入和专用分页器：

```python
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.cmdb.models.change_record import (
    COLLECT_AUTOMATION_CHANGE,
    DEVICE_LIFECYCLE,
    OPERATE_TYPE_CHOICES,
    ORDINARY_ATTRIBUTE_CHANGE,
    RELATION_CHANGE,
    SCENARIO_CHOICES,
    ChangeRecord,
)

HOME_ASSET_CHANGE_SCENARIOS = (
    DEVICE_LIFECYCLE,
    RELATION_CHANGE,
    ORDINARY_ATTRIBUTE_CHANGE,
    COLLECT_AUTOMATION_CHANGE,
)


class HomeRecentChangePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({"count": self.page.paginator.count, "items": data})
```

在 `ChangeRecordViewSet` 增加 action：

```python
@action(methods=["get"], detail=False, url_path="home_recent")
@HasPermission("asset_info-View,search-View")
def home_recent(self, request, *args, **kwargs):
    queryset = self.get_queryset().filter(scenario__in=HOME_ASSET_CHANGE_SCENARIOS)
    queryset = self.filter_queryset(queryset)
    paginator = HomeRecentChangePagination()
    page = paginator.paginate_queryset(queryset, request, view=self)
    serializer = self.get_serializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)
```

基础 queryset 先固定场景白名单，再应用客户端过滤，确保 `scenarios=model_management_change` 只能得到空结果，不能扩大范围。

- [ ] **Step 4: 运行 GREEN、完整变更记录回归与覆盖率**

Run（工作目录 `server/`）：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' \
  --cov=apps.cmdb.views.change_record --cov-report=term-missing \
  apps/cmdb/tests/test_change_record_views.py
```

Expected: 全部 PASS；`home_recent` 新分支覆盖率不低于 90%，通用 list/retrieve/export 仍仅对 `operation_log-View` 或超级用户开放。

- [ ] **Step 5: 提交最近变更安全入口**

```bash
git add server/apps/cmdb/views/change_record.py server/apps/cmdb/tests/test_change_record_views.py
git commit -m "fix(cmdb): 增加首页资产变更查询入口"
```

---

### Task 3: 前端首页切换到专用最近变更 API

**Files:**
- Create: `web/scripts/cmdb-home-query-permission-test.ts`
- Modify: `web/package.json`
- Modify: `web/src/app/cmdb/api/changeRecord.ts`
- Modify: `web/src/app/cmdb/(pages)/assetSearch/page.tsx`

**Interfaces:**
- Consumes: Task 2 的 `GET /cmdb/api/change_record/home_recent/` 与既有 `ChangeRecordListResponse`。
- Produces: `useChangeRecordApi().getHomeRecentChanges(params?)`；首页最近变更只调用该方法，操作日志和实例历史继续调用 `getChangeRecords`。

- [ ] **Step 1: 写前端接线 RED 测试**

创建 `web/scripts/cmdb-home-query-permission-test.ts`：

```typescript
import assert from 'node:assert/strict';
import fs from 'node:fs';

const apiSource = fs.readFileSync('src/app/cmdb/api/changeRecord.ts', 'utf8');
const pageSource = fs.readFileSync('src/app/cmdb/(pages)/assetSearch/page.tsx', 'utf8');

assert.match(
  apiSource,
  /const getHomeRecentChanges = \(params\?: any\) =>\s*get\('\/cmdb\/api\/change_record\/home_recent\/'/,
  'changeRecord API 必须提供首页专用最近变更方法'
);
assert.match(
  pageSource,
  /const \{ getHomeRecentChanges \} = useChangeRecordApi\(\)/,
  'CMDB 首页必须解构首页专用方法'
);
assert.match(
  pageSource,
  /getHomeRecentChanges\(\s*buildRecentChangeQuery/,
  '首页最近变更加载必须调用专用入口'
);

console.log('CMDB 首页查询权限接线测试通过');
```

在 `web/package.json` scripts 增加：

```json
"test:cmdb-home-query-permission": "pnpm exec tsx scripts/cmdb-home-query-permission-test.ts"
```

- [ ] **Step 2: 运行 RED，确认专用方法尚未接线**

Run（工作目录 `web/`）：

```bash
pnpm test:cmdb-home-query-permission
```

Expected: FAIL，提示 `changeRecord API 必须提供首页专用最近变更方法`。

- [ ] **Step 3: 增加 API 方法并替换首页调用**

在 `changeRecord.ts` 增加并导出 hook 方法：

```typescript
const getHomeRecentChanges = (params?: any) =>
  get('/cmdb/api/change_record/home_recent/', { params });

return {
  getChangeRecords,
  getHomeRecentChanges,
  getInstanceChangeRecords,
  getChangeRecordDetail,
  getChangeRecordEnumData,
  getChangeRecordScenarioEnum,
  exportChangeRecords,
};
```

在 `assetSearch/page.tsx` 将首页解构和 `loadRecentChanges` 内的调用改为：

```typescript
const { getHomeRecentChanges } = useChangeRecordApi();

const response = await getHomeRecentChanges(
  buildRecentChangeQuery(filter, operator, undefined, RECENT_CHANGE_LIMIT, page)
) as ChangeRecordListResponse;
```

高风险分支内的两个并行请求统一改为 `getHomeRecentChanges(buildRecentChangeQuery(filter, operator, type, RECENT_CHANGE_LIMIT, 1))`。不要修改操作日志页或资产详情历史页的 `getChangeRecords`。

- [ ] **Step 4: 运行前端 GREEN 与触及文件静态检查**

Run（工作目录 `web/`）：

```bash
pnpm test:cmdb-home-query-permission
pnpm exec eslint scripts/cmdb-home-query-permission-test.ts src/app/cmdb/api/changeRecord.ts 'src/app/cmdb/(pages)/assetSearch/page.tsx'
```

Expected: 接线测试通过，ESLint 0 errors。

- [ ] **Step 5: 提交前端接线**

```bash
git add web/package.json web/scripts/cmdb-home-query-permission-test.ts \
  web/src/app/cmdb/api/changeRecord.ts 'web/src/app/cmdb/(pages)/assetSearch/page.tsx'
git commit -m "fix(cmdb): 切换首页资产变更查询接口"
```

---

### Task 4: 完整回归与交付收口

**Files:**
- Verify only: Tasks 1-3 全部触及文件
- Modify only if verification reveals a scoped regression: 对应测试或生产文件

**Interfaces:**
- Consumes: Tasks 1-3 的三个提交。
- Produces: normal 查询权限无 403、管理与写权限未放宽的验证证据。

- [ ] **Step 1: 运行后端组合回归**

Run（工作目录 `server/`）：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_model_views.py \
  apps/cmdb/tests/test_misc_views.py \
  apps/cmdb/tests/test_instance_views.py \
  apps/cmdb/tests/test_change_record_views.py
```

Expected: 全部 PASS。

- [ ] **Step 2: 运行触及 Python 文件静态门禁**

Run（工作目录 `server/`）：

```bash
uv run black --check apps/cmdb/views/model.py apps/cmdb/views/classification.py apps/cmdb/views/instance.py apps/cmdb/views/change_record.py \
  apps/cmdb/tests/test_model_views.py apps/cmdb/tests/test_misc_views.py apps/cmdb/tests/test_instance_views.py apps/cmdb/tests/test_change_record_views.py
uv run isort --check-only apps/cmdb/views/model.py apps/cmdb/views/classification.py apps/cmdb/views/instance.py apps/cmdb/views/change_record.py \
  apps/cmdb/tests/test_model_views.py apps/cmdb/tests/test_misc_views.py apps/cmdb/tests/test_instance_views.py apps/cmdb/tests/test_change_record_views.py
uv run flake8 apps/cmdb/views/model.py apps/cmdb/views/classification.py apps/cmdb/views/instance.py apps/cmdb/views/change_record.py \
  apps/cmdb/tests/test_model_views.py apps/cmdb/tests/test_misc_views.py apps/cmdb/tests/test_instance_views.py apps/cmdb/tests/test_change_record_views.py
```

Expected: 触及新增行无格式或静态错误；若历史大文件基线已有错误，记录精确未触及行并对新增行做等价检查，不整文件格式化。

- [ ] **Step 3: 运行前端完整门禁并区分基线问题**

Run（工作目录 `web/`）：

```bash
pnpm test:cmdb-home-query-permission
pnpm lint
pnpm type-check
```

Expected: 聚焦测试通过；lint/type-check 全绿。若被已知全仓基线阻断，必须保留完整输出，并证明三个前端触及文件没有新增诊断。

- [ ] **Step 4: 检查权限与 diff 范围**

Run（仓库根目录）：

```bash
git diff --check HEAD~3..HEAD
git diff --stat HEAD~3..HEAD
git status --short
```

Expected: 只有计划内文件；`.superpowers/brainstorm` 临时文件保持未纳入提交；无凭据、Cookie 或 Token 进入 diff。

- [ ] **Step 5: 记录验证结论**

如果所有适用验证通过，通过 projectmem `record_attempt(outcome="worked")` 记录本轮实施证据，再以 `record_fix` 关闭 #0307。若任何验证失败，立即记录 `record_attempt(outcome="failed" | "partial")`，回到对应 Task 的 RED/GREEN 步骤，不得宣称修复完成。

# CMDB 阶段一权限修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in the current session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 IPAM 全局手动对账和 K8s 引导式接入敏感接口补齐全局权限，并证明拒绝路径不会触发任何副作用。

**Architecture:** 保持现有 ViewSet、Service 和响应契约不变，在 HTTP 入口使用项目统一的 `HasPermission` 装饰器完成 fail-closed 授权。IPAM 使用资产编辑权限；K8s token/命令使用自动采集执行权限，状态验证使用自动采集查看权限。阶段一不提前实现阶段三的 IPAM 作业化。

**Tech Stack:** Python 3.12、Django 4.2、Django REST Framework、pytest、unittest.mock。

## Global Constraints

- 严格执行 RED→GREEN→REFACTOR；生产代码之前必须观察到目标测试因缺少权限而失败。
- 权限拒绝必须发生在 Service、缓存、NodeMgmt、VictoriaMetrics 和 FalkorDB 副作用之前。
- 只修改 CMDB 阶段一相关 View 和测试，不顺带重构。
- 使用 Django ORM；不引入原生 SQL。
- 阶段完成前运行聚焦测试和相关 CMDB 回归测试。

---

## File Structure

- Modify: `server/apps/cmdb/tests/test_ipam_views.py` — 增加 IPAM 手动对账权限正反向行为测试。
- Modify: `server/apps/cmdb/views/instance.py` — 为 `ipam_reconcile` 声明资产编辑权限。
- Create: `server/apps/cmdb/tests/test_k8s_setup_views.py` — 覆盖三个内部 K8s setup action 的权限和无副作用契约。
- Modify: `server/apps/cmdb/views/k8s_setup.py` — 为 K8s setup 内部 action 声明自动采集权限。

### Task 1: IPAM 手动对账权限

**Files:**
- Modify: `server/apps/cmdb/tests/test_ipam_views.py`
- Modify: `server/apps/cmdb/views/instance.py:1416-1420`

**Interfaces:**
- Consumes: `HasPermission("asset_info-Edit")`；`run_reconciliation() -> dict`。
- Produces: `POST ipam_reconcile` 无权限返回 403；有权限保持现有成功响应。

- [ ] **Step 1: 写拒绝路径失败测试**

在 `server/apps/cmdb/tests/test_ipam_views.py` 增加：

```python
def _reconcile_request(user):
    request = APIRequestFactory().post(
        "/api/v1/cmdb/api/instance/ipam_reconcile/",
        data={},
        format="json",
    )
    force_authenticate(request, user=user)
    return request


def _call_reconcile(request):
    return InstanceViewSet.as_view({"post": "ipam_reconcile"})(request)


def test_ipam_reconcile_requires_asset_edit_permission():
    user = _user()

    with patch(
        "apps.cmdb.services.ipam_reconcile.run_reconciliation",
        return_value={"created": 1},
    ) as reconcile:
        response = _call_reconcile(_reconcile_request(user))

    assert response.status_code == 403
    reconcile.assert_not_called()
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_ipam_views.py::test_ipam_reconcile_requires_asset_edit_permission
```

Expected: FAIL；当前响应为 200，且 `run_reconciliation` 被调用一次。

- [ ] **Step 3: 实现最小权限修复**

在 `server/apps/cmdb/views/instance.py` 修改 action：

```python
    @action(detail=False, methods=["post"], url_path="ipam_reconcile")
    @HasPermission("asset_info-Edit")
    def ipam_reconcile(self, request):
        """立即对账（手动触发）。"""
        from apps.cmdb.services.ipam_reconcile import run_reconciliation

        return WebUtils.response_success(run_reconciliation())
```

- [ ] **Step 4: 运行测试并确认 GREEN**

Run: Step 2 的同一命令。

Expected: PASS；无权限响应 403，Service mock 未调用。

- [ ] **Step 5: 写有权限成功测试**

在同一测试文件增加：

```python
def test_ipam_reconcile_runs_with_asset_edit_permission():
    user = _user()
    user.permission = {"cmdb": {"asset_info-Edit"}}

    with patch(
        "apps.cmdb.services.ipam_reconcile.run_reconciliation",
        return_value={"created": 1, "updated": 2},
    ) as reconcile:
        response = _call_reconcile(_reconcile_request(user))

    assert response.status_code == 200
    reconcile.assert_called_once_with()
```

- [ ] **Step 6: 运行 IPAM View 测试**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_ipam_views.py
```

Expected: 全部 PASS。

- [ ] **Step 7: 记录并提交 Task 1**

```bash
git add server/apps/cmdb/tests/test_ipam_views.py server/apps/cmdb/views/instance.py
git commit -m "fix(cmdb): 限制IPAM手动对账权限"
```

### Task 2: K8s Setup 内部接口权限

**Files:**
- Create: `server/apps/cmdb/tests/test_k8s_setup_views.py`
- Modify: `server/apps/cmdb/views/k8s_setup.py:1-37`

**Interfaces:**
- Consumes: `K8sSetupService.generate_install_token`、`generate_install_command`、`verify_collector_reporting`。
- Produces: token/命令要求 `auto_collection-Execute`；verify 要求 `auto_collection-View`；拒绝路径不调用 Service。

- [ ] **Step 1: 写三个拒绝路径失败测试**

创建 `server/apps/cmdb/tests/test_k8s_setup_views.py`：

```python
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.services.k8s_setup import K8sSetupService
from apps.cmdb.views.k8s_setup import K8sSetupViewSet

pytestmark = pytest.mark.unit


def _user(permission=None):
    return SimpleNamespace(
        username="bob",
        is_superuser=False,
        is_authenticated=True,
        is_active=True,
        permission={"cmdb": set(permission or [])},
        group_list=[{"id": 1, "name": "Default Team"}],
        group_tree=[],
        roles=[],
        locale="en",
    )


def _call(action, user, data):
    request = APIRequestFactory().post("/api/v1/cmdb/api/k8s_setup/", data=data, format="json")
    force_authenticate(request, user=user)
    return K8sSetupViewSet.as_view({"post": action})(request)


@pytest.mark.parametrize(
    ("action", "service_method", "payload"),
    [
        ("install_token", "generate_install_token", {"collector_cluster_id": "c1", "cloud_region_id": 1}),
        ("install_command", "generate_install_command", {"collector_cluster_id": "c1", "cloud_region_id": 1}),
        ("verify", "verify_collector_reporting", {"collector_cluster_id": "c1"}),
    ],
)
def test_k8s_setup_internal_actions_reject_users_without_permission(action, service_method, payload):
    with patch.object(K8sSetupService, service_method) as service:
        response = _call(action, _user(), payload)

    assert response.status_code == 403
    service.assert_not_called()
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_k8s_setup_views.py::test_k8s_setup_internal_actions_reject_users_without_permission
```

Expected: 3 FAIL；当前接口进入 Service，而不是返回 403。

- [ ] **Step 3: 实现最小权限修复**

在 `server/apps/cmdb/views/k8s_setup.py` 导入：

```python
from apps.core.decorators.api_permission import HasPermission
```

并修改三个 action：

```python
    @action(methods=["post"], detail=False, url_path="install_token")
    @HasPermission("auto_collection-Execute")
    def install_token(self, request):
        ...

    @action(methods=["post"], detail=False, url_path="install_command")
    @HasPermission("auto_collection-Execute")
    def install_command(self, request):
        ...

    @action(methods=["post"], detail=False, url_path="verify")
    @HasPermission("auto_collection-View")
    def verify(self, request):
        ...
```

方法体保持不变。

- [ ] **Step 4: 运行拒绝测试并确认 GREEN**

Run: Step 2 的同一命令。

Expected: 3 PASS；三个 Service mock 均未调用。

- [ ] **Step 5: 写权限映射成功测试**

在同一测试文件增加：

```python
@pytest.mark.parametrize(
    ("action", "required_permission", "service_method", "payload", "result"),
    [
        (
            "install_token",
            "auto_collection-Execute",
            "generate_install_token",
            {"collector_cluster_id": "c1", "cloud_region_id": 1},
            {"token": "masked-token"},
        ),
        (
            "install_command",
            "auto_collection-Execute",
            "generate_install_command",
            {"collector_cluster_id": "c1", "cloud_region_id": 1},
            {"command": "kubectl apply"},
        ),
        (
            "verify",
            "auto_collection-View",
            "verify_collector_reporting",
            {"collector_cluster_id": "c1"},
            {"reporting": True},
        ),
    ],
)
def test_k8s_setup_internal_actions_allow_required_permission(
    action, required_permission, service_method, payload, result
):
    with patch.object(K8sSetupService, service_method, return_value=result) as service:
        response = _call(action, _user({required_permission}), payload)

    assert response.status_code == 200
    service.assert_called_once()
```

- [ ] **Step 6: 运行 K8s Setup View 测试**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_k8s_setup_views.py
```

Expected: 全部 PASS。

- [ ] **Step 7: 记录并提交 Task 2**

```bash
git add server/apps/cmdb/tests/test_k8s_setup_views.py server/apps/cmdb/views/k8s_setup.py
git commit -m "fix(cmdb): 限制K8s接入内部接口权限"
```

### Task 3: 阶段一回归与收口

**Files:**
- Verify: `server/apps/cmdb/tests/test_ipam_views.py`
- Verify: `server/apps/cmdb/tests/test_ipam_reconcile_service.py`
- Verify: `server/apps/cmdb/tests/test_ipam_reconcile_task.py`
- Verify: `server/apps/cmdb/tests/test_k8s_setup_views.py`
- Verify: `server/apps/cmdb/tests/test_infra_service.py`
- Verify: `server/apps/cmdb/tests/test_slice_collect_tool_data_cleanup_k8s.py`

**Interfaces:**
- Consumes: Task 1、Task 2 的权限装饰器。
- Produces: 阶段一可独立发布的验证证据；关闭 projectmem #0034、#0020 和重复记录 #0007。

- [ ] **Step 1: 运行阶段一相关回归测试**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_ipam_views.py \
  apps/cmdb/tests/test_ipam_reconcile_service.py \
  apps/cmdb/tests/test_ipam_reconcile_task.py \
  apps/cmdb/tests/test_k8s_setup_views.py \
  apps/cmdb/tests/test_infra_service.py \
  apps/cmdb/tests/test_slice_collect_tool_data_cleanup_k8s.py
```

Expected: 全部 PASS，退出码 0。

- [ ] **Step 2: 运行静态迁移检查**

阶段一不应产生模型变更：

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`，退出码 0。

- [ ] **Step 3: 检查最终差异**

```bash
git diff --check
git status --short
```

Expected: 无空白错误；只包含阶段一计划内文件。

- [ ] **Step 4: 更新项目记忆**

- #0034：记录 IPAM 权限失败测试由 RED 变 GREEN 后关闭。
- #0020：记录 K8s setup 三个 action 权限测试由 RED 变 GREEN 后关闭。
- #0007 与 #0020 是同一根因的重复记录；使用相同验证证据分别关闭，不创建第三条 issue。

- [ ] **Step 5: 阶段一完成检查点**

确认以下条件同时满足后才能开始阶段二计划：

- 两类无权限请求全部返回 403。
- 拒绝路径 Service 调用次数为 0。
- 有权限路径保持 200 和原响应结构。
- 相关回归测试和迁移检查退出码均为 0。

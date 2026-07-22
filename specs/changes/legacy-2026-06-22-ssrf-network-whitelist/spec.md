# Historical Superpowers change: 2026-06-22-ssrf-network-whitelist

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-22-ssrf-network-whitelist.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让管理员能在「平台设置」维护可信内网网段（CIDR）白名单，使 opspilot skilltool 等走严格 SSRF 校验的入口可以放行内网工具，同时云元数据永远硬挡。

**Architecture:** 后端在 `system_mgmt` 新增 `NetworkWhiteList` 模型 + CRUD viewset + 短 TTL 缓存；`core` 的 `SSRFValidator._is_blocked_ip` 改为 `云元数据硬挡 → 白名单放行 → 私网黑名单` 三段判定，全局生效（含 Agent 运行时 fetch/browser）。前端在平台设置新增「白名单」tab。

**Tech Stack:** Django 4.2 + DRF + pytest/pytest-mock；Next.js 16 + React 19 + Ant Design；Python `ipaddress` 做 CIDR 校验。

**Spec:** [docs/superpowers/specs/2026-06-22-ssrf-network-whitelist-design.md](../specs/2026-06-22-ssrf-network-whitelist-design.md)

---

## 执行环境须知（务必先读）

- **不自动提交/推送/同步**：按用户工作流约定，所有 commit 留在本 worktree 本地，**不 push、不同步到 master**，除非用户明确下令。计划里的 `git commit` 步骤照常执行（本地提交），但不要 `git push`。
- **后端测试运行环境**：worktree 缺 MINIO 等环境变量，后端 pytest 需用 `bkliteserver` 虚拟环境、在能加载 `server/.env` + `server/local_settings.py` 的环境跑。命令形如（在 `server/` 目录）：
  ```bash
  uv run pytest apps/core/tests/utils/test_ssrf_validator.py -v
  ```
  若 `uv run` 不可用，用解释器 `D:\app\venv\bkliteserver\Scripts\python.exe -m pytest <path> -v`。
- **代码以 worktree 为准**：所有 Edit/Write 落在本 worktree；如需在主仓库跑测试，注意别让两侧分叉。
- **前端验证走 Storybook（主仓库）**，不启 dev server / 浏览器预览。
- **完成后质量检查**：后端跑 flake8 + isort + black；前端跑 eslint + type-check。

---

## File Structure

**后端（新增）**
- `server/apps/system_mgmt/models/network_white_list.py` — `NetworkWhiteList` 模型
- `server/apps/system_mgmt/serializers/network_white_list_serializer.py` — 序列化器 + CIDR 校验
- `server/apps/system_mgmt/utils/network_whitelist_cache.py` — 白名单缓存读取 + 失效
- `server/apps/system_mgmt/viewset/network_white_list_viewset.py` — CRUD viewset
- `server/apps/system_mgmt/migrations/00XX_networkwhitelist.py` — 生成的迁移

**后端（修改）**
- `server/apps/core/utils/ssrf_validator.py` — `_is_blocked_ip` 三段判定 + `_get_allowed_networks`
- `server/apps/system_mgmt/models/__init__.py`、`viewset/__init__.py`、`urls.py`
- `server/support-files/system_mgmt/menus/system-manager.json` — 注册 `network_white_list` 权限资源

**后端（测试）**
- `server/apps/core/tests/utils/test_ssrf_validator.py`（追加白名单用例）
- `server/apps/system_mgmt/tests/test_network_white_list_serializer_pure.py`
- `server/apps/system_mgmt/tests/test_network_whitelist_cache_service.py`
- `server/apps/system_mgmt/tests/test_network_white_list_views.py`

**前端**
- `web/src/app/system-manager/(pages)/settings/network-whitelist/page.tsx`（新增）
- `web/src/app/system-manager/api/settings/index.ts`（增 CRUD + 类型）
- `web/src/app/system-manager/constants/menu.json`（平台设置组增 tab，zh/en）
- `web/src/app/system-manager/locales/zh.json`、`en.json`（i18n）

---

## Task 1: NetworkWhiteList 模型

**Files:**
- Create: `server/apps/system_mgmt/models/network_white_list.py`
- Modify: `server/apps/system_mgmt/models/__init__.py`
- Migration: `server/apps/system_mgmt/migrations/00XX_networkwhitelist.py`（生成）

- [ ] **Step 1: 写模型文件**

`server/apps/system_mgmt/models/network_white_list.py`：

```python
from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class NetworkWhiteList(MaintainerInfo, TimeInfo):
    """SSRF 内网白名单条目（CIDR）。

    命中条目的解析 IP 可绕过私网阻断（云元数据除外）。
    """

    network = models.CharField(max_length=64, unique=True)  # 规范化 CIDR: 10.11.73.0/24 / 10.11.73.15/32
    remark = models.CharField(max_length=255, default="")
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Network White List"
        db_table = "system_mgmt_network_white_list"
        ordering = ["-id"]
```

- [ ] **Step 2: 在 models 包导出**

`server/apps/system_mgmt/models/__init__.py` 追加一行（放在 `from .login_module import *` 之后即可）：

```python
from .network_white_list import NetworkWhiteList  # noqa
```

- [ ] **Step 3: 生成迁移**

Run（在 `server/`）: `uv run python manage.py makemigrations system_mgmt`
Expected: 生成 `Create model NetworkWhiteList` 的迁移文件 `00XX_networkwhitelist.py`。

- [ ] **Step 4: 应用迁移验证无误**

Run: `uv run python manage.py migrate system_mgmt`
Expected: 迁移成功，`system_mgmt_network_white_list` 表创建。

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/models/network_white_list.py server/apps/system_mgmt/models/__init__.py server/apps/system_mgmt/migrations/
git commit -m "feat(system_mgmt): add NetworkWhiteList model for SSRF allowlist"
```

---

## Task 2: 序列化器 + CIDR 校验

**Files:**
- Create: `server/apps/system_mgmt/serializers/network_white_list_serializer.py`
- Test: `server/apps/system_mgmt/tests/test_network_white_list_serializer_pure.py`

- [ ] **Step 1: 写失败测试**

`server/apps/system_mgmt/tests/test_network_white_list_serializer_pure.py`：

```python
"""NetworkWhiteListSerializer.validate_network 纯函数校验（无 DB）。"""
import pytest
from rest_framework import serializers

from apps.system_mgmt.serializers.network_white_list_serializer import NetworkWhiteListSerializer


def test_validate_network_normalizes_bare_ip():
    s = NetworkWhiteListSerializer()
    assert s.validate_network("10.11.73.15") == "10.11.73.15/32"


def test_validate_network_normalizes_cidr():
    s = NetworkWhiteListSerializer()
    assert s.validate_network(" 10.11.73.0/24 ") == "10.11.73.0/24"


def test_validate_network_rejects_invalid():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_network("not-a-cidr")


def test_validate_network_rejects_supernet_v4():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_network("0.0.0.0/0")


def test_validate_network_rejects_supernet_v6():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_network("::/0")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest apps/system_mgmt/tests/test_network_white_list_serializer_pure.py -v`
Expected: FAIL（`ModuleNotFoundError: ...network_white_list_serializer`）。

- [ ] **Step 3: 写序列化器**

`server/apps/system_mgmt/serializers/network_white_list_serializer.py`：

```python
import ipaddress

from rest_framework import serializers

from apps.system_mgmt.models import NetworkWhiteList

# 等于关闭全部 SSRF 防护的超网，禁止入库
_FORBIDDEN_SUPERNETS = {"0.0.0.0/0", "::/0"}


class NetworkWhiteListSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkWhiteList
        fields = "__all__"
        read_only_fields = (
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "created_at",
            "updated_at",
        )

    def validate_network(self, value):
        raw = (value or "").strip()
        if not raw:
            raise serializers.ValidationError("网段不能为空")
        try:
            net = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            raise serializers.ValidationError(f"非法的 CIDR/IP: {raw}")
        normalized = str(net)
        if normalized in _FORBIDDEN_SUPERNETS:
            raise serializers.ValidationError("禁止添加 0.0.0.0/0 或 ::/0（等于关闭全部防护）")
        return normalized
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest apps/system_mgmt/tests/test_network_white_list_serializer_pure.py -v`
Expected: PASS（5 passed）。

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/serializers/network_white_list_serializer.py server/apps/system_mgmt/tests/test_network_white_list_serializer_pure.py
git commit -m "feat(system_mgmt): add NetworkWhiteList serializer with CIDR validation"
```

---

## Task 3: 白名单缓存读取 + 失效

**Files:**
- Create: `server/apps/system_mgmt/utils/network_whitelist_cache.py`
- Test: `server/apps/system_mgmt/tests/test_network_whitelist_cache_service.py`

- [ ] **Step 1: 写失败测试**

`server/apps/system_mgmt/tests/test_network_whitelist_cache_service.py`：

```python
"""network_whitelist_cache 读取逻辑（测试环境用 DummyCache，故每次读 DB）。"""
import pytest


@pytest.mark.django_db
def test_get_network_whitelist_cidrs_returns_enabled_only():
    from apps.system_mgmt.models import NetworkWhiteList
    from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_cidrs

    NetworkWhiteList.objects.create(network="10.11.73.0/24", enabled=True)
    NetworkWhiteList.objects.create(network="192.168.5.0/24", enabled=False)

    result = get_network_whitelist_cidrs()

    assert "10.11.73.0/24" in result
    assert "192.168.5.0/24" not in result


@pytest.mark.django_db
def test_get_network_whitelist_cidrs_empty_when_no_rows():
    from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_cidrs

    assert get_network_whitelist_cidrs() == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest apps/system_mgmt/tests/test_network_whitelist_cache_service.py -v`
Expected: FAIL（`ModuleNotFoundError: ...network_whitelist_cache`）。

- [ ] **Step 3: 写缓存工具**

`server/apps/system_mgmt/utils/network_whitelist_cache.py`：

```python
"""SSRF 内网白名单缓存。

将 SSRFValidator.validate() 热路径上的白名单查询合并为一次查询并短 TTL 缓存；
管理员增删改白名单后调用 invalidate_network_whitelist_cache() 主动失效。
"""

from django.core.cache import cache

NETWORK_WHITELIST_CACHE_KEY = "system_settings:network_white_list"
NETWORK_WHITELIST_CACHE_TTL = 300  # 5 分钟；写操作主动清除


def get_network_whitelist_cidrs() -> list:
    """返回启用中的规范化 CIDR 字符串列表（缓存字符串，避免跨缓存后端 pickle 问题）。

    任何异常（表不存在 / app 未安装 / DB 异常）都返回空列表（fail-closed，维持严格校验）。
    """
    cached = cache.get(NETWORK_WHITELIST_CACHE_KEY)
    if cached is not None:
        return cached
    try:
        from apps.system_mgmt.models.network_white_list import NetworkWhiteList

        rows = list(NetworkWhiteList.objects.filter(enabled=True).values_list("network", flat=True))
    except Exception:
        rows = []
    cache.set(NETWORK_WHITELIST_CACHE_KEY, rows, NETWORK_WHITELIST_CACHE_TTL)
    return rows


def invalidate_network_whitelist_cache() -> None:
    cache.delete(NETWORK_WHITELIST_CACHE_KEY)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest apps/system_mgmt/tests/test_network_whitelist_cache_service.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/utils/network_whitelist_cache.py server/apps/system_mgmt/tests/test_network_whitelist_cache_service.py
git commit -m "feat(system_mgmt): add network whitelist cache with fail-closed read"
```

---

## Task 4: 校验器三段判定（核心）

**Files:**
- Modify: `server/apps/core/utils/ssrf_validator.py:98-121`（`_is_blocked_ip`，新增 `_get_allowed_networks`）
- Test: `server/apps/core/tests/utils/test_ssrf_validator.py`（追加）

- [ ] **Step 1: 写失败测试（追加到文件末尾）**

`server/apps/core/tests/utils/test_ssrf_validator.py` 顶部确认有 `import ipaddress`（无则加），并追加：

```python
class TestSSRFValidatorWhitelist:
    """白名单放行 + 元数据永封 + 空白名单零回归。"""

    @patch("socket.getaddrinfo")
    def test_whitelisted_private_ip_allowed(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.11.73.15", 8000))]
        with patch.object(SSRFValidator, "_get_allowed_networks", return_value=[ipaddress.ip_network("10.11.73.0/24")]):
            assert SSRFValidator.validate("http://10.11.73.15:8000/sse") == "http://10.11.73.15:8000/sse"

    @patch("socket.getaddrinfo")
    def test_non_whitelisted_private_ip_blocked(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]
        with patch.object(SSRFValidator, "_get_allowed_networks", return_value=[ipaddress.ip_network("10.11.73.0/24")]):
            with pytest.raises(SSRFError, match="禁止的网段"):
                SSRFValidator.validate("http://10.0.0.1/api")

    @patch("socket.getaddrinfo")
    def test_metadata_blocked_even_if_whitelisted(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("169.254.169.254", 80))]
        with patch.object(SSRFValidator, "_get_allowed_networks", return_value=[ipaddress.ip_network("169.254.0.0/16")]):
            with pytest.raises(SSRFError, match="云元数据"):
                SSRFValidator.validate("http://169.254.169.254/latest/meta-data/")

    @patch("socket.getaddrinfo")
    def test_empty_whitelist_keeps_strict(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]
        with patch.object(SSRFValidator, "_get_allowed_networks", return_value=[]):
            with pytest.raises(SSRFError, match="禁止的网段"):
                SSRFValidator.validate("http://10.0.0.1/api")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest apps/core/tests/utils/test_ssrf_validator.py::TestSSRFValidatorWhitelist -v`
Expected: FAIL（`_get_allowed_networks` 不存在 / 白名单放行未生效 → `test_whitelisted_private_ip_allowed` 抛 SSRFError）。

- [ ] **Step 3: 改 `_is_blocked_ip` 并新增 `_get_allowed_networks`**

把 `server/apps/core/utils/ssrf_validator.py` 中现有 `_is_blocked_ip`（约 98-121 行）整体替换为下面两个方法：

```python
    @classmethod
    def _get_allowed_networks(cls) -> list:
        """读取白名单 CIDR 并解析为 ip_network 列表（延迟导入 + fail-closed）。"""
        try:
            from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_cidrs

            networks = []
            for cidr in get_network_whitelist_cidrs():
                try:
                    networks.append(ipaddress.ip_network(cidr, strict=False))
                except ValueError:
                    continue
            return networks
        except Exception:
            return []

    @classmethod
    def _is_blocked_ip(cls, ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> tuple[bool, str]:
        """
        检查 IP 是否在禁止范围内。

        判定顺序：① 云元数据硬挡（白名单不可覆盖） → ② 白名单放行 → ③ 私网黑名单。

        Returns:
            (是否禁止, 原因)
        """
        ip_str = str(ip)

        # ① 云元数据永远硬挡（白名单不可覆盖）
        if ip_str in cls.CLOUD_METADATA_HOSTS:
            return True, f"云元数据地址 {ip_str}"
        for network in cls.CLOUD_METADATA_NETWORKS:
            try:
                if ip in network:
                    return True, f"云元数据地址 {ip_str}"
            except TypeError:
                continue

        # ② 白名单放行（私网黑名单之前）
        for network in cls._get_allowed_networks():
            try:
                if ip in network:
                    return False, ""
            except TypeError:
                continue

        # ③ 私网 / 特殊地址黑名单
        for network in cls.BLOCKED_NETWORKS:
            try:
                if ip in network:
                    return True, f"禁止的网段 {network}"
            except TypeError:
                continue

        return False, ""
```

- [ ] **Step 4: 跑新用例确认通过**

Run: `uv run pytest apps/core/tests/utils/test_ssrf_validator.py::TestSSRFValidatorWhitelist -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 跑整文件确认零回归**

Run: `uv run pytest apps/core/tests/utils/test_ssrf_validator.py -v`
Expected: 全部 PASS（既有严格模式/回调/LLM 端点用例不受影响）。

- [ ] **Step 6: Commit**

```bash
git add server/apps/core/utils/ssrf_validator.py server/apps/core/tests/utils/test_ssrf_validator.py
git commit -m "feat(core): SSRFValidator honors network whitelist (metadata always blocked)"
```

---

## Task 5: CRUD ViewSet + 路由 + 权限 + 缓存失效 + 审计日志

**Files:**
- Create: `server/apps/system_mgmt/viewset/network_white_list_viewset.py`
- Modify: `server/apps/system_mgmt/viewset/__init__.py`、`server/apps/system_mgmt/urls.py`
- Test: `server/apps/system_mgmt/tests/test_network_white_list_views.py`

- [ ] **Step 1: 写失败测试**

`server/apps/system_mgmt/tests/test_network_white_list_views.py`：

```python
"""NetworkWhiteListViewSet：CRUD + 权限门 + 缓存失效。

复用仓库既有 system_mgmt viewset 测试范式：APIRequestFactory + force_authenticate(SimpleNamespace)。
"""
import types

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.viewset.network_white_list_viewset import NetworkWhiteListViewSet

factory = APIRequestFactory()


def _user(perms, is_superuser=True):
    return types.SimpleNamespace(
        username="nwl-admin",
        domain="domain.com",
        locale="en",
        is_superuser=is_superuser,
        is_authenticated=True,
        permission={"system-manager": set(perms)},
    )


@pytest.mark.django_db
def test_create_normalizes_and_invalidates_cache(mocker):
    inval = mocker.patch("apps.system_mgmt.viewset.network_white_list_viewset.invalidate_network_whitelist_cache")
    view = NetworkWhiteListViewSet.as_view({"post": "create"})
    request = factory.post(
        "/system_mgmt/network_white_list/",
        {"network": "10.11.73.15", "remark": "mcp"},
        format="json",
    )
    force_authenticate(request, user=_user({"network_white_list-Add"}))

    response = view(request)

    assert response.status_code == 201
    assert response.data["network"] == "10.11.73.15/32"
    assert response.data["created_by"] == "nwl-admin"
    inval.assert_called_once()


@pytest.mark.django_db
def test_create_rejects_invalid_cidr():
    view = NetworkWhiteListViewSet.as_view({"post": "create"})
    request = factory.post("/system_mgmt/network_white_list/", {"network": "bad-cidr"}, format="json")
    force_authenticate(request, user=_user({"network_white_list-Add"}))

    response = view(request)

    assert response.status_code == 400


@pytest.mark.django_db
def test_create_denied_without_permission():
    view = NetworkWhiteListViewSet.as_view({"post": "create"})
    request = factory.post("/system_mgmt/network_white_list/", {"network": "10.11.73.0/24"}, format="json")
    force_authenticate(request, user=_user(set(), is_superuser=False))

    response = view(request)

    assert response.status_code == 403


@pytest.mark.django_db
def test_list_returns_rows():
    from apps.system_mgmt.models import NetworkWhiteList

    NetworkWhiteList.objects.create(network="10.11.73.0/24")
    view = NetworkWhiteListViewSet.as_view({"get": "list"})
    request = factory.get("/system_mgmt/network_white_list/")
    force_authenticate(request, user=_user({"network_white_list-View"}))

    response = view(request)

    assert response.status_code == 200
    networks = [item["network"] for item in response.data]
    assert "10.11.73.0/24" in networks
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest apps/system_mgmt/tests/test_network_white_list_views.py -v`
Expected: FAIL（`ModuleNotFoundError: ...network_white_list_viewset`）。

- [ ] **Step 3: 写 viewset**

`server/apps/system_mgmt/viewset/network_white_list_viewset.py`：

```python
from rest_framework import viewsets

from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.models import NetworkWhiteList
from apps.system_mgmt.serializers.network_white_list_serializer import NetworkWhiteListSerializer
from apps.system_mgmt.utils.network_whitelist_cache import invalidate_network_whitelist_cache
from apps.system_mgmt.utils.operation_log_utils import log_operation


class NetworkWhiteListViewSet(viewsets.ModelViewSet):
    queryset = NetworkWhiteList.objects.all().order_by("-id")
    serializer_class = NetworkWhiteListSerializer

    def _user_domain(self):
        return getattr(self.request.user, "domain", "domain.com")

    def perform_create(self, serializer):
        username = self.request.user.username
        serializer.save(created_by=username, updated_by=username, domain=self._user_domain())

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user.username)

    @HasPermission("network_white_list-View", "system-manager")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("network_white_list-View", "system-manager")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("network_white_list-Add", "system-manager")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if 200 <= response.status_code < 300:
            invalidate_network_whitelist_cache()
            log_operation(request, "create", "system-manager", f"新增内网白名单: {request.data.get('network', '')}")
        return response

    @HasPermission("network_white_list-Edit", "system-manager")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if 200 <= response.status_code < 300:
            invalidate_network_whitelist_cache()
            log_operation(request, "update", "system-manager", f"编辑内网白名单: {request.data.get('network', '')}")
        return response

    @HasPermission("network_white_list-Edit", "system-manager")
    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        if 200 <= response.status_code < 300:
            invalidate_network_whitelist_cache()
            log_operation(request, "update", "system-manager", f"编辑内网白名单: {request.data.get('network', '')}")
        return response

    @HasPermission("network_white_list-Delete", "system-manager")
    def destroy(self, request, *args, **kwargs):
        instance_network = self.get_object().network
        response = super().destroy(request, *args, **kwargs)
        if 200 <= response.status_code < 300:
            invalidate_network_whitelist_cache()
            log_operation(request, "delete", "system-manager", f"删除内网白名单: {instance_network}")
        return response
```

- [ ] **Step 4: 在 viewset 包导出**

`server/apps/system_mgmt/viewset/__init__.py` 追加：

```python
from .network_white_list_viewset import NetworkWhiteListViewSet  # noqa
```

- [ ] **Step 5: 注册路由**

`server/apps/system_mgmt/urls.py`：在 import 块加 `NetworkWhiteListViewSet`，并在 `error_log` 注册行后追加：

```python
router.register(r"network_white_list", NetworkWhiteListViewSet)
```

（import 块改为包含 `NetworkWhiteListViewSet`，例如在 `LoginModuleViewSet,` 之后插入 `NetworkWhiteListViewSet,`。）

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run pytest apps/system_mgmt/tests/test_network_white_list_views.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 7: Commit**

```bash
git add server/apps/system_mgmt/viewset/network_white_list_viewset.py server/apps/system_mgmt/viewset/__init__.py server/apps/system_mgmt/urls.py server/apps/system_mgmt/tests/test_network_white_list_views.py
git commit -m "feat(system_mgmt): add NetworkWhiteList CRUD viewset with permission + audit + cache bust"
```

---

## Task 6: 注册权限资源（seed）

**Files:**
- Modify: `server/support-files/system_mgmt/menus/system-manager.json`

- [ ] **Step 1: 在「Setting」组 children 追加权限资源**

`server/support-files/system_mgmt/menus/system-manager.json` 中找到 `"name": "Setting"` 组的 `children`（含 `api_secret_key`/`audit_log`/`error_logs`），在 `error_logs` 项之后追加：

```json
{
  "id": "network_white_list",
  "name": "Network Whitelist",
  "operation": [
    "View",
    "Add",
    "Edit",
    "Delete"
  ]
}
```

注意 JSON 逗号：`error_logs` 对象末尾需补 `,` 再接新对象。

- [ ] **Step 2: 校验 JSON 合法**

Run（在 `server/`）: `uv run python -c "import json; json.load(open('support-files/system_mgmt/menus/system-manager.json', encoding='utf-8')); print('ok')"`
Expected: 输出 `ok`。

> 说明：该 seed 在系统初始化（`make server-init` / `batch_init`）时写入权限表。运行时 `is_superuser` 用户与 admin 角色不受影响；普通角色需被授予 `network_white_list-*` 才能访问。

- [ ] **Step 3: Commit**

```bash
git add server/support-files/system_mgmt/menus/system-manager.json
git commit -m "feat(system_mgmt): register network_white_list permission resource"
```

---

## Task 7: 前端 API + 类型

**Files:**
- Modify: `web/src/app/system-manager/api/settings/index.ts`

- [ ] **Step 1: 加类型与 CRUD 方法**

在 `web/src/app/system-manager/api/settings/index.ts` 顶部 interface 区追加：

```typescript
export interface NetworkWhiteListItem {
  id: number;
  network: string;
  remark: string;
  enabled: boolean;
  created_at: string;
  created_by?: string;
}
```

把 `useSettingsApi` 里的解构改为含 `patch`：

```typescript
  const { get, post, del, patch } = useApiClient();
```

在 `createUserApiSecret` 之后、`return {` 之前追加四个方法：

```typescript
  const fetchNetworkWhiteList = useCallback(async (): Promise<NetworkWhiteListItem[]> => {
    return get('/system_mgmt/network_white_list/');
  }, [get]);

  const createNetworkWhiteList = useCallback(
    async (data: { network: string; remark?: string; enabled?: boolean }): Promise<NetworkWhiteListItem> => {
      return post('/system_mgmt/network_white_list/', data);
    },
    [post]
  );

  const updateNetworkWhiteList = useCallback(
    async (id: number, data: { network?: string; remark?: string; enabled?: boolean }): Promise<NetworkWhiteListItem> => {
      return patch(`/system_mgmt/network_white_list/${id}/`, data);
    },
    [patch]
  );

  const deleteNetworkWhiteList = useCallback(async (id: number): Promise<void> => {
    await del(`/system_mgmt/network_white_list/${id}/`);
  }, [del]);
```

把这四个方法加入 `return { ... }`：

```typescript
    fetchNetworkWhiteList,
    createNetworkWhiteList,
    updateNetworkWhiteList,
    deleteNetworkWhiteList,
```

- [ ] **Step 2: 类型检查**

Run（在 `web/`，主仓库）: `pnpm type-check`
Expected: 无新增类型错误。

- [ ] **Step 3: Commit**

```bash
git add web/src/app/system-manager/api/settings/index.ts
git commit -m "feat(web): add network whitelist CRUD api in settings"
```

---

## Task 8: 前端「白名单」页面

**Files:**
- Create: `web/src/app/system-manager/(pages)/settings/network-whitelist/page.tsx`

- [ ] **Step 1: 写页面组件**

`web/src/app/system-manager/(pages)/settings/network-whitelist/page.tsx`：

```tsx
'use client';
import React, { useState, useEffect } from 'react';
import { Button, Table, Space, Popconfirm, message, Spin, Modal, Form, Input, Switch } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import { NetworkWhiteListItem, useSettingsApi } from '@/app/system-manager/api/settings';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

const NetworkWhitelistPage: React.FC = () => {
  const { t } = useTranslation();
  const { fetchNetworkWhiteList, createNetworkWhiteList, updateNetworkWhiteList, deleteNetworkWhiteList } = useSettingsApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [dataSource, setDataSource] = useState<NetworkWhiteListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NetworkWhiteListItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchNetworkWhiteList();
      setDataSource(Array.isArray(data) ? data : []);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true });
    setModalOpen(true);
  };

  const openEdit = (record: NetworkWhiteListItem) => {
    setEditing(record);
    form.setFieldsValue({ network: record.network, remark: record.remark, enabled: record.enabled });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updateNetworkWhiteList(editing.id, values);
      } else {
        await createNetworkWhiteList(values);
      }
      message.success(t('common.updateSuccess'));
      setModalOpen(false);
      fetchData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteNetworkWhiteList(id);
      setDataSource((prev) => prev.filter((item) => item.id !== id));
      message.success(t('common.delSuccess'));
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const columns = [
    { title: t('system.settings.networkWhitelist.network'), dataIndex: 'network', key: 'network', width: 220 },
    { title: t('system.settings.networkWhitelist.remark'), dataIndex: 'remark', key: 'remark', ellipsis: true },
    {
      title: t('system.settings.networkWhitelist.enabled'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 100,
      render: (v: boolean) => (v ? t('common.yes') : t('common.no')),
    },
    {
      title: t('system.settings.networkWhitelist.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (text: string) => (text ? convertToLocalizedTime(text) : '-'),
    },
    {
      title: '',
      key: 'action',
      width: 100,
      render: (_: unknown, record: NetworkWhiteListItem) => (
        <Space size={0}>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button type="text" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('system.settings.networkWhitelist.deleteConfirm')}
              onConfirm={() => handleDelete(record.id)}
              okText={t('common.yes')}
              cancelText={t('common.no')}
            >
              <Button type="text" icon={<DeleteOutlined />} danger />
            </Popconfirm>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="mb-4">
        <TopSection
          title={t('system.settings.networkWhitelist.title')}
          content={t('system.settings.networkWhitelist.content')}
        />
      </div>
      <section className="rounded-md bg-(--color-bg) p-4" style={{ height: 'calc(100vh - 235px)' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px' }}>
            <Spin />
          </div>
        ) : (
          <>
            <div className="flex justify-end mb-4">
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                  {t('system.settings.networkWhitelist.add')}
                </Button>
              </PermissionWrapper>
            </div>
            <Table dataSource={dataSource} columns={columns} pagination={false} rowKey="id" />
          </>
        )}
      </section>

      <Modal
        title={editing ? t('system.settings.networkWhitelist.edit') : t('system.settings.networkWhitelist.add')}
        open={modalOpen}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="network"
            label={t('system.settings.networkWhitelist.network')}
            rules={[{ required: true, message: t('system.settings.networkWhitelist.networkRequired') }]}
            extra={t('system.settings.networkWhitelist.metadataHint')}
          >
            <Input placeholder={t('system.settings.networkWhitelist.networkPlaceholder')} />
          </Form.Item>
          <Form.Item name="remark" label={t('system.settings.networkWhitelist.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="enabled" label={t('system.settings.networkWhitelist.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default NetworkWhitelistPage;
```

- [ ] **Step 2: 类型检查**

Run（在 `web/`，主仓库）: `pnpm type-check`
Expected: 无新增类型错误。

> 若 `common.delSuccess` 等公共 i18n key 不存在，改用页面已确认存在的等价 key（参考 `key/page.tsx` 用法），或在公共 locales 补齐。

- [ ] **Step 3: Commit**

```bash
git add "web/src/app/system-manager/(pages)/settings/network-whitelist/page.tsx"
git commit -m "feat(web): add network whitelist management page"
```

---

## Task 9: 平台设置 tab + i18n

**Files:**
- Modify: `web/src/app/system-manager/constants/menu.json`（zh + en 两块的「平台设置/Setting」children）
- Modify: `web/src/app/system-manager/locales/zh.json`、`en.json`

- [ ] **Step 1: zh 菜单加 tab**

`menu.json` 中 `"title": "平台设置"` 组的 `children`，在「错误日志」对象后追加：

```json
{
  "title": "白名单",
  "url": "/system-manager/settings/network-whitelist",
  "icon": "shield",
  "name": "network_white_list"
}
```

- [ ] **Step 2: en 菜单加 tab**

`menu.json` 中 en 块 `"title": "Platform Settings"`（或对应英文标题）组的 `children`，在 Error Logs 对象后追加：

```json
{
  "title": "Network Whitelist",
  "url": "/system-manager/settings/network-whitelist",
  "icon": "shield",
  "name": "network_white_list"
}
```

> `icon` 用 `shield`；若图标库无此名，挑选语义贴近的安全类图标（参考同文件其它 `icon` 取值）。

- [ ] **Step 3: zh i18n**

`web/src/app/system-manager/locales/zh.json` 的 `system.settings` 下：`tabs` 加 `"networkWhitelist": "白名单"`；并在 `secret` 对象后追加：

```json
"networkWhitelist": {
  "title": "内网白名单",
  "content": "添加可信内网网段（CIDR），命中的地址将被允许访问；云元数据地址不会被放行。",
  "network": "网段(CIDR)",
  "remark": "备注",
  "enabled": "启用",
  "createdAt": "创建时间",
  "add": "新增白名单",
  "edit": "编辑白名单",
  "deleteConfirm": "确定删除该白名单网段吗？",
  "networkPlaceholder": "如 10.11.73.0/24 或 10.11.73.15",
  "networkRequired": "请输入合法的 CIDR 或 IP",
  "metadataHint": "云元数据地址（169.254.169.254 等）不会被放行"
}
```

- [ ] **Step 4: en i18n**

`web/src/app/system-manager/locales/en.json` 对应 `system.settings` 下加同结构英文：

```json
"networkWhitelist": {
  "title": "Network Whitelist",
  "content": "Add trusted internal CIDR ranges. Matching targets are allowed; cloud metadata addresses are never allowed.",
  "network": "Network (CIDR)",
  "remark": "Remark",
  "enabled": "Enabled",
  "createdAt": "Created At",
  "add": "Add Entry",
  "edit": "Edit Entry",
  "deleteConfirm": "Delete this whitelist entry?",
  "networkPlaceholder": "e.g. 10.11.73.0/24 or 10.11.73.15",
  "networkRequired": "Please enter a valid CIDR or IP",
  "metadataHint": "Cloud metadata addresses (e.g. 169.254.169.254) are never allowed"
}
```

并在 en 的 `system.settings.tabs` 加 `"networkWhitelist": "Network Whitelist"`（若该结构存在）。

- [ ] **Step 5: 校验 JSON + 类型检查**

Run（在 `web/`）:
```bash
pnpm type-check
```
并确认 menu.json / zh.json / en.json 为合法 JSON（编辑器无红线）。

- [ ] **Step 6: Storybook 冒烟（主仓库）**

在主仓库 `web/` 跑 Storybook，确认白名单页：列表渲染、新增/编辑 Modal、CIDR 必填校验、删除确认气泡正常；tab 出现在平台设置一排。

- [ ] **Step 7: Commit**

```bash
git add web/src/app/system-manager/constants/menu.json web/src/app/system-manager/locales/zh.json web/src/app/system-manager/locales/en.json
git commit -m "feat(web): add network whitelist tab under platform settings + i18n"
```

---

## Task 10: 全量回归 + 质量检查 + 联调

- [ ] **Step 1: 后端相关测试全绿**

Run（在 `server/`）:
```bash
uv run pytest apps/core/tests/utils/test_ssrf_validator.py apps/system_mgmt/tests/test_network_white_list_serializer_pure.py apps/system_mgmt/tests/test_network_whitelist_cache_service.py apps/system_mgmt/tests/test_network_white_list_views.py -v
```
Expected: 全部 PASS。

- [ ] **Step 2: 后端代码质量**

Run（在 `server/`）:
```bash
uv run flake8 apps/system_mgmt/models/network_white_list.py apps/system_mgmt/serializers/network_white_list_serializer.py apps/system_mgmt/utils/network_whitelist_cache.py apps/system_mgmt/viewset/network_white_list_viewset.py apps/core/utils/ssrf_validator.py
uv run isort apps/system_mgmt apps/core/utils/ssrf_validator.py
uv run black apps/system_mgmt apps/core/utils/ssrf_validator.py
```
Expected: 无 flake8 报错；isort/black 无改动或自动格式化后提交。

- [ ] **Step 3: 前端质量**

Run（在 `web/`）:
```bash
pnpm lint
pnpm type-check
```
Expected: 通过。

- [ ] **Step 4: 端到端联调（手动）**

1. 后端 `network_white_list` CRUD 接口可用；新增 `10.11.73.0/24` 后白名单生效。
2. opspilot skilltool「获取工具」填 `http://10.11.73.15:8000/sse` → 不再报「禁止的网段」，进入真实 MCP 连接。
3. 反例：填未放行的 `http://10.0.0.1` → 仍被「禁止的网段」拦。
4. 元数据反例：白名单加 `169.254.0.0/16`，访问 `169.254.169.254` 仍被云元数据硬挡。

- [ ] **Step 5: 若有格式化改动则 Commit**

```bash
git add -A
git commit -m "chore: lint/format network whitelist feature"
```

---

## Self-Review 备忘（已核对）

- **Spec 覆盖**：模型(§5.1)→T1；序列化器/校验(§5.2)→T2；缓存(§5.3)→T3；校验器三段判定(§5.4/§6)→T4；ViewSet/权限/日志(§5.5)→T5；权限 seed→T6；前端 api/页面/tab/i18n(§5.6)→T7-T9；测试(§7)分散在各任务 + T10；安全不变量(§6)由 T4 用例（元数据永封）+ T2（超网拒绝）+ 缓存 fail-closed（T3）覆盖。
- **类型/命名一致**：模型 `NetworkWhiteList`；表 `system_mgmt_network_white_list`；路由 `network_white_list`；权限资源 `network_white_list`（View/Add/Edit/Delete）；缓存 key `system_settings:network_white_list`；缓存函数 `get_network_whitelist_cidrs` / `invalidate_network_whitelist_cache`；前端 tab `name=network_white_list`、URL `/system-manager/settings/network-whitelist`、i18n 命名空间 `system.settings.networkWhitelist`——全文一致。
- **无占位符**：每个代码步骤均为完整可粘贴代码；唯一"生成项"是迁移文件号（由 `makemigrations` 真实生成，命令已给）。

## specs: 2026-06-22-ssrf-network-whitelist-design.md

- 日期：2026-06-22
- 模块：`server/apps/core`（校验器）、`server/apps/system_mgmt`（模型/API/缓存）、`web/system-manager`（管理界面）
- 状态：设计已确认，待写实现计划
- 交付范围：全栈（后端 + 前端 UI）

## 1. 背景与问题

opspilot skilltool 添加内网工具时，后端走严格的 `SSRFValidator.validate()` 校验，会阻断全部 RFC1918 私网段。现象：填 `http://10.11.73.15:8000/sse` 点「获取工具」报错 `目标地址被禁止: 禁止的网段 10.0.0.0/8`，导致**内网部署的 MCP / DB / K8s 工具完全无法添加**。

校验器现有三档（`server/apps/core/utils/ssrf_validator.py`）：

- `validate()` —— 严格：挡 云元数据 + 私网 + localhost（skilltool 与 Agent 运行时 fetch/browser 都用它）
- `validate_callback()` —— 挡 云元数据 + localhost，放行私网
- `validate_llm_endpoint()` —— 只挡云元数据，放行私网 + localhost

需要一种**可控地放行特定内网网段**的机制，而不是一刀降级整档。

## 2. 目标 / 非目标

**目标**
- 管理员可在「系统管理 → 安全设置」维护一份可信内网网段白名单（CIDR 形式）。
- 严格 `validate()` 的判定改为 **`云元数据硬挡 → 白名单放行 → 私网黑名单`**，全局生效。
- 白名单为空时行为与现状**完全一致**（零回归）。

**非目标**
- 不做按组织 / 按工具的细粒度白名单（YAGNI，将来可在同一缓存层上扩展数据源）。
- 不放宽云元数据防护（任何情况下都硬挡）。
- 不改 `validate_callback` / `validate_llm_endpoint`（它们本就放行私网，白名单对其无意义）。

## 3. 关键决策记录（已与用户确认）

| 维度 | 结论 | 备注 |
|---|---|---|
| 放开范围 | 全部 skilltool 管理端入口起步，**最终选设计 X：全局生效** | 见下 |
| 匹配维度 | **IP / CIDR 网段** | DNS 解析后比对解析到的 IP，保留 DNS-rebinding 防护 |
| 配置载体 | **system_mgmt 专用 model + 管理 UI**（方案 B 精炼版） | 不复用 key-value `SystemSettings` |
| 派发方式 | **设计 X：白名单焊进 `validate()`，全局生效** | 含 Agent 运行时 fetch/browser |
| 模型命名 | `NetworkWhiteList` | 用户指定 |
| 前端落点 | **平台设置（`/system-manager/settings`）下新增「白名单」tab** | 与 密钥/审计日志/错误日志 并列，非"安全设置" |
| 权限资源 | **独立资源 `network_white_list`**（View/Add/Edit/Delete） | 贴合 tab 化权限范式，在 seed 文件注册 |

**设计 X 的已知接受代价（务必在 PR/文档中显式标注）**：白名单同样对 LLM 可控的 `fetch`/`browser`/`website_loader` 生效——提示词注入可诱导 Agent 访问被放行网段。缓解：白名单只填确需的最小网段；云元数据永封；写权限收口到安全设置管理员。

## 4. 架构总览

```
管理员 ──► 平台设置「白名单」tab (web, /system-manager/settings/network-whitelist)
                 │  CRUD  /api/v1/system_mgmt/network_white_list/
                 ▼
        NetworkWhiteListViewSet ──► NetworkWhiteList 表 (system_mgmt)
                 │ 写操作后失效缓存
                 ▼
        network_whitelist_cache  (cache key: system_settings:network_white_list, TTL 300s)
                 ▲ get_network_whitelist_cidrs()（延迟导入 + fail-closed）
                 │
SSRFValidator.validate() ─► _is_blocked_ip()
   顺序：① 云元数据硬挡  ② 白名单放行  ③ 私网黑名单
   （所有严格校验调用方：skilltool 守卫 + fetch/browser/website_loader 统一过这里）
```

## 5. 详细设计

### 5.1 数据模型 `server/apps/system_mgmt/models/network_white_list.py`

```python
from django.db import models
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class NetworkWhiteList(MaintainerInfo, TimeInfo):
    """SSRF 内网白名单条目（CIDR）。命中条目的解析 IP 可绕过私网阻断（云元数据除外）。"""

    network = models.CharField(max_length=64, unique=True)   # 规范化 CIDR：10.11.73.0/24 / 10.11.73.15/32
    remark = models.CharField(max_length=255, default="")    # 备注：为什么放行
    enabled = models.BooleanField(default=True)              # 软开关

    class Meta:
        verbose_name = "Network White List"
        db_table = "system_mgmt_network_white_list"
```

- 继承 `MaintainerInfo`（`created_by`/`updated_by`/`domain`）+ `TimeInfo`（`created_at`/`updated_at`），与仓库其它模型一致。
- **用 `CharField` 而非 PG 专属 `CIDRField`**：仓库需多库支持（PostgreSQL/MySQL/SQLite/Dameng/GaussDB…，见 CLAUDE.md），CIDR 校验在序列化器层用 `ipaddress` 做，不依赖数据库类型。
- `models/__init__.py` 追加 `from .network_white_list import *  # noqa`。
- 生成迁移：`make migrate` / `uv run python manage.py makemigrations system_mgmt`。

### 5.2 校验 / 规范化（序列化器 + 可选 model.clean）

`server/apps/system_mgmt/serializers/network_white_list_serializer.py`：

- `validate_network(value)`：
  - `net = ipaddress.ip_network(value.strip(), strict=False)`，非法 → `ValidationError`；
  - 裸 IP（无 `/`）自动成 `/32`、`/128`；
  - 存规范化字符串 `str(net)`；
  - **安全护栏**：拒绝 `0.0.0.0/0` 与 `::/0`（等于关闭全部防护）。
- 元数据网段无需在此拒绝——§5.4 保证其永远被硬挡，填进来也无效（但可在 UI 文案提示"元数据不会被放行"）。

### 5.3 缓存层 `server/apps/system_mgmt/utils/network_whitelist_cache.py`（仿 `pwd_policy_cache`）

```python
from django.core.cache import cache

NETWORK_WHITELIST_CACHE_KEY = "system_settings:network_white_list"
NETWORK_WHITELIST_CACHE_TTL = 300  # 5 分钟；写操作主动失效

def get_network_whitelist_cidrs() -> list[str]:
    """返回启用中的规范化 CIDR 字符串列表（缓存字符串，避免跨缓存后端 pickle 问题）。"""
    cached = cache.get(NETWORK_WHITELIST_CACHE_KEY)
    if cached is not None:
        return cached
    try:
        from apps.system_mgmt.models.network_white_list import NetworkWhiteList  # 延迟导入，避免 core→system_mgmt 顶层耦合
        rows = list(NetworkWhiteList.objects.filter(enabled=True).values_list("network", flat=True))
    except Exception:
        rows = []  # ★ fail-closed：表不存在 / app 未安装 / DB 异常 → 视为空白名单 → 维持严格
    cache.set(NETWORK_WHITELIST_CACHE_KEY, rows, NETWORK_WHITELIST_CACHE_TTL)
    return rows

def invalidate_network_whitelist_cache() -> None:
    cache.delete(NETWORK_WHITELIST_CACHE_KEY)
```

### 5.4 校验器改造 `server/apps/core/utils/ssrf_validator.py` —— `_is_blocked_ip`（核心）

判定顺序改为（这是全局生效的关键，所有 `validate()` 都过这里）：

```python
@classmethod
def _is_blocked_ip(cls, ip):
    ip_str = str(ip)

    # ① 云元数据永远硬挡（白名单不可覆盖）
    if ip_str in cls.CLOUD_METADATA_HOSTS:
        return True, f"云元数据地址 {ip_str}"
    for network in cls.CLOUD_METADATA_NETWORKS:      # 显式补上网段级元数据硬挡
        try:
            if ip in network:
                return True, f"云元数据地址 {ip_str}"
        except TypeError:
            continue

    # ② 白名单放行（私网黑名单之前）
    for cidr in cls._get_allowed_networks():
        try:
            if ip in cidr:
                return False, ""
        except TypeError:
            continue

    # ③ 私网 / 特殊地址黑名单
    for network in cls.BLOCKED_NETWORKS:
        try:
            if ip in network:
                return True, f"禁止的网段 {network}"
        except TypeError:
            continue
    return False, ""

@classmethod
def _get_allowed_networks(cls):
    """读取并解析白名单 CIDR（延迟导入 + fail-closed）。"""
    try:
        from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_cidrs
        return [ipaddress.ip_network(c, strict=False) for c in get_network_whitelist_cidrs()]
    except Exception:
        return []
```

- `validate()` 主流程不变；仅 `_is_blocked_ip` 的判定顺序与白名单逻辑变化。
- `validate_callback` / `validate_llm_endpoint` 不调 `_is_blocked_ip`、且本就放行私网，**不改**。
- 既有 `allowlist`（域名收紧）参数语义无关，保留不动；两者可正交组合。

### 5.5 管理 API

- `server/apps/system_mgmt/serializers/network_white_list_serializer.py`：`NetworkWhiteListSerializer(ModelSerializer)`，`fields="__all__"` + `validate_network`。
- `server/apps/system_mgmt/viewset/network_white_list_viewset.py`：`NetworkWhiteListViewSet(ModelViewSet)`：
  - 权限：独立资源 `network_white_list`——`@HasPermission("network_white_list-View", "system-manager")`（list/retrieve）/ `-Add`（create）/ `-Edit`（update/partial_update）/ `-Delete`（destroy），与 `api_secret_key` 等平台设置 tab 的权限范式一致。
  - 写操作（create/update/destroy）成功后：`invalidate_network_whitelist_cache()` + `log_operation(request, action, "system-manager", f"...内网白名单: {network}")`。
  - `created_by`/`updated_by` 由 `request.user` 注入（参考其它 system_mgmt viewset 写法）。
- `server/apps/system_mgmt/viewset/__init__.py` 导出；`server/apps/system_mgmt/urls.py` `router.register(r"network_white_list", NetworkWhiteListViewSet)` → `api/v1/system_mgmt/network_white_list/`。
- **权限 seed**：`server/support-files/system_mgmt/menus/system-manager.json` 的 `"Setting"` 组 `children` 追加：
  ```json
  { "id": "network_white_list", "name": "Network Whitelist", "operation": ["View", "Add", "Edit", "Delete"] }
  ```
  并视需要把 `network_white_list-*` 加入相应角色（`admin` 的 `menus: []` 默认全量；如需 `security` 角色可用则补 4 条）。

### 5.6 前端（web / system-manager，全栈范围）

落点：**平台设置（`/system-manager/settings`）新增「白名单」tab**，与 密钥/审计日志/错误日志 并列（截图里 门户/许可 是企业版注入，社区 menu.json 无）。tab 由 `constants/menu.json` 的 `"平台设置"/"Setting"` 组 `children` 驱动，页面落在 `(pages)/settings/<route>/page.tsx`，沿用密钥页范式（`TopSection` + antd `Table` + `PermissionWrapper`）。

- 菜单 tab：`web/src/app/system-manager/constants/menu.json` 的「平台设置」`children` 追加（**zh 与 en 两份都加**）：
  ```jsonc
  // zh
  { "title": "白名单", "url": "/system-manager/settings/network-whitelist", "icon": "<图标>", "name": "network_white_list" }
  // en
  { "title": "Network Whitelist", "url": "/system-manager/settings/network-whitelist", "icon": "<图标>", "name": "network_white_list" }
  ```
- 页面：`web/src/app/system-manager/(pages)/settings/network-whitelist/page.tsx`——antd `Table` 列出 CIDR / 备注 / 启停 / 创建时间 / 操作；新增/编辑 Modal（CIDR 输入 + 前端格式校验 + 备注 + 启停 Switch）；按钮包 `PermissionWrapper requiredPermissions={['Add'|'Edit'|'Delete']}`；文案提示"云元数据地址不会被放行"。参考实现：`(pages)/settings/key/page.tsx`。
- API：`web/src/app/system-manager/api/settings/index.ts` 的 `useSettingsApi()` 增 CRUD（`fetchNetworkWhiteList` / `createNetworkWhiteList` / `updateNetworkWhiteList` / `deleteNetworkWhiteList`），打 `/system_mgmt/network_white_list/`。
- i18n：社区版 locales 增 `system.settings.networkWhitelist.*` 文案（zh/en）。
- 注意事项：
  - web 前端有**企业版/社区版拆分**——社区端路由由 `prepare-enterprise.mjs` 自动生成（别手改生成产物），i18n 文案在社区版 locales。
  - worktree 内前端难跑，**前端验证去主仓库走 Storybook**（含整页/带数据场景），不启 dev server。

## 6. 安全边界与不变量（实现必须守住）

- ✅ 云元数据 `169.254.169.254`/`169.254.170.2`/`fd00:ec2::254` 永封；§5.4 的元数据检查排在白名单**之前**，即便有人把 `169.254.0.0/16` 填进白名单也无法暴露元数据。
- ✅ `0.0.0.0/0`、`::/0` 入库即被序列化器拒绝。
- ✅ fail-closed：白名单读取/解析任何异常 → 视为空 → 维持严格校验。
- ✅ 写权限收口到 `network_white_list-Add/Edit/Delete`（平台设置管理员），在 seed 文件注册。
- ⚠️ 已接受代价（设计 X）：白名单对 Agent 运行时 fetch/browser 同样生效（见 §3）。

## 7. 测试方案

**后端校验器**（`server/apps/core/tests/utils/test_ssrf_validator.py` 追加，mock `_get_allowed_networks` 或缓存函数）：

- 白名单内私网（如 `10.11.73.0/24` 覆盖 `10.11.73.15`）→ `validate` 通过；
- 不在白名单的私网（如 `10.0.0.1`）→ 仍抛 `SSRFError(禁止的网段)`；
- **元数据 `169.254.169.254` 即便加入白名单仍被挡**；
- 空白名单 → 与现状一致（既有严格模式用例全绿，零回归）；
- `0.0.0.0/0`/`::/0` 序列化器校验拒绝。

**system_mgmt**（`server/apps/system_mgmt/tests/`）：

- CRUD + 权限门（`security_settings-View/Edit`）；
- 序列化器 CIDR 规范化（裸 IP→/32）、非法值拒绝、超网拒绝；
- 写操作触发缓存失效（mock `invalidate_network_whitelist_cache` 断言被调）。

**前端**：Storybook（主仓库）覆盖列表/新增/编辑/校验态。

> 后端 pytest 在**主仓库**跑（worktree 缺 MINIO 等环境变量）；运行环境见 `server/.env` + `server/local_settings.py`，解释器 `D:\app\venv\bkliteserver`。

## 8. 改动文件清单

**后端（新增）**
- `server/apps/system_mgmt/models/network_white_list.py`
- `server/apps/system_mgmt/serializers/network_white_list_serializer.py`
- `server/apps/system_mgmt/viewset/network_white_list_viewset.py`
- `server/apps/system_mgmt/utils/network_whitelist_cache.py`
- `server/apps/system_mgmt/migrations/XXXX_networkwhitelist.py`（生成）

**后端（修改）**
- `server/apps/core/utils/ssrf_validator.py`（`_is_blocked_ip` 顺序 + `_get_allowed_networks`）
- `server/apps/system_mgmt/models/__init__.py`、`viewset/__init__.py`、`urls.py`
- `server/support-files/system_mgmt/menus/system-manager.json`（注册 `network_white_list` 权限资源）

**前端**
- `web/src/app/system-manager/(pages)/settings/network-whitelist/page.tsx`（新增）
- `web/src/app/system-manager/api/settings/index.ts`（`useSettingsApi` 增 CRUD）
- `web/src/app/system-manager/constants/menu.json`（平台设置组增「白名单」tab，zh/en）
- 社区版 i18n locales（`system.settings.networkWhitelist.*`，zh/en）

**测试**
- `server/apps/core/tests/utils/test_ssrf_validator.py`（追加）
- `server/apps/system_mgmt/tests/test_network_white_list*.py`（新增）

## 9. 兼容性与回滚

- 默认零回归：白名单空表时 `_is_blocked_ip` 行为与改造前等价。
- 回滚：删除/停用白名单条目即恢复严格；代码回滚仅需还原 `_is_blocked_ip`（其余为新增文件，互不影响）。
- 性能：`validate` 热路径上白名单走 5 分钟缓存 + 少量 CIDR 解析，开销可忽略。

## 10. 联调验证步骤（实现后）

1. 后端：`network_white_list` CRUD 接口通；新增 `10.11.73.0/24` 后查缓存失效生效。
2. skilltool「获取工具」填 `http://10.11.73.15:8000/sse` → 不再报 `禁止的网段`，进入真实 MCP 连接。
3. 反例：填未放行的 `http://10.0.0.1` → 仍被 `禁止的网段` 拦。
4. 元数据反例：白名单加 `169.254.0.0/16`，访问 `169.254.169.254` 仍被云元数据硬挡。
5. 前端：Storybook 验证列表/新增/编辑/校验态。

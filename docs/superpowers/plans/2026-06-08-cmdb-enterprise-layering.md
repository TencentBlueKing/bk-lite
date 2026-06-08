# CMDB Enterprise Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a consistent CMDB enterprise extension model so commercial code lives under `server/apps/cmdb/enterprise`, community code owns explicit extension facades, and existing collect enterprise behavior is routed through those facades without scattered dynamic imports.

**Architecture:** Keep enterprise capability additive-only. Introduce one small shared provider loader, then add fixed facades for `collection`, `model_ops`, and `instance_ops`. Migrate the existing collect enterprise hooks (`tree.py`, plugin package loading, `NodeParams` registration) to the new collect facade first, then wire empty-but-real model and instance facades into representative view flows so future commercial requirements have a stable entrypoint.

**Tech Stack:** Python 3.12, Django/DRF, existing CMDB tests under `server/apps/cmdb/tests`, pytest via `uv run pytest`.

---

## File Structure

- Create: `server/apps/cmdb/extensions/__init__.py` — shared CMDB extension package marker.
- Create: `server/apps/cmdb/extensions/loader.py` — one helper that loads a domain provider or returns a default factory when the provider module is absent.
- Modify: `server/apps/cmdb/tests/test_import_helpers.py` — add pure tests for provider loading fallback, success, and contract errors without creating a new test file.
- Create: `server/apps/cmdb/collection/extensions.py` — collect-domain contract object plus `get_collect_enterprise_extension()`.
- Create: `server/apps/cmdb/enterprise/collect/__init__.py` — collect enterprise package marker.
- Create: `server/apps/cmdb/enterprise/collect/provider.py` — wraps current legacy `enterprise/tree.py` and package-based collect registration into the new collect contract.
- Modify: `server/apps/cmdb/services/collect_object_tree.py:1-76` — stop importing `apps.cmdb.enterprise.tree` directly; consume the collect facade instead.
- Modify: `server/apps/cmdb/collection/plugins/loader.py:1-58` — replace hard-coded enterprise package names with collect facade package discovery.
- Modify: `server/apps/cmdb/node_configs/__init__.py:1-55` — load enterprise node-param packages from the collect facade instead of directly hard-coding `apps.cmdb.enterprise`.
- Modify: `server/apps/cmdb/tests/test_collect_object_tree.py` — convert tree tests from legacy module patching to facade/provider patching and cover package metadata.
- Modify: `server/apps/cmdb/tests/test_node_params_multicred.py` — add a focused regression for collect-facade-driven node param package registration without creating a new file.
- Create: `server/apps/cmdb/model_ops/__init__.py` — model domain package marker.
- Create: `server/apps/cmdb/model_ops/extensions.py` — model-domain contract and facade entry.
- Create: `server/apps/cmdb/enterprise/model_ops/__init__.py` — enterprise model domain package marker.
- Create: `server/apps/cmdb/enterprise/model_ops/provider.py` — empty default model enterprise provider for future features.
- Modify: `server/apps/cmdb/views/model.py:1-130` — enrich model detail/list responses through the model facade without changing current API shape when enterprise is absent.
- Modify: `server/apps/cmdb/tests/test_model_views.py` — add monkeypatched model-enterprise facade regressions on `get_model_info()` and `list()`.
- Create: `server/apps/cmdb/instance_ops/__init__.py` — instance domain package marker.
- Create: `server/apps/cmdb/instance_ops/extensions.py` — instance-domain contract and facade entry.
- Create: `server/apps/cmdb/enterprise/instance_ops/__init__.py` — enterprise instance domain package marker.
- Create: `server/apps/cmdb/enterprise/instance_ops/provider.py` — empty default instance enterprise provider for future features.
- Modify: `server/apps/cmdb/views/instance.py:190-283` — enrich search and retrieve payloads through the instance facade while preserving current permission flow.
- Modify: `server/apps/cmdb/tests/test_instance_views.py` — add monkeypatched instance-enterprise facade regressions on `search()` and `retrieve()`.

## Task 1: Introduce one shared enterprise provider loader

**Files:**
- Create: `server/apps/cmdb/extensions/__init__.py`
- Create: `server/apps/cmdb/extensions/loader.py`
- Modify: `server/apps/cmdb/tests/test_import_helpers.py`

- [ ] **Step 1: Write the failing pure loader tests**

```python
# server/apps/cmdb/tests/test_import_helpers.py
import sys
import types

import pytest

from apps.cmdb.extensions.loader import load_provider


def test_load_provider_returns_default_when_module_missing():
    factory = load_provider(
        "apps.cmdb.enterprise.model_ops.provider",
        "get_model_enterprise_extension",
        default=lambda: "fallback",
    )
    assert factory() == "fallback"


def test_load_provider_returns_provider_when_present(monkeypatch):
    fake = types.ModuleType("apps.cmdb.enterprise.model_ops.provider")
    fake.get_model_enterprise_extension = lambda: "enterprise"
    monkeypatch.setitem(sys.modules, "apps.cmdb.enterprise.model_ops.provider", fake)
    factory = load_provider(
        "apps.cmdb.enterprise.model_ops.provider",
        "get_model_enterprise_extension",
        default=lambda: "fallback",
    )
    assert factory() == "enterprise"


def test_load_provider_raises_when_contract_attr_missing(monkeypatch):
    fake = types.ModuleType("apps.cmdb.enterprise.instance_ops.provider")
    monkeypatch.setitem(sys.modules, "apps.cmdb.enterprise.instance_ops.provider", fake)
    with pytest.raises(AttributeError, match="get_instance_enterprise_extension"):
        load_provider(
            "apps.cmdb.enterprise.instance_ops.provider",
            "get_instance_enterprise_extension",
            default=lambda: "fallback",
        )
```

- [ ] **Step 2: Run the focused loader tests to verify they fail**

Run: `cd server && uv run pytest apps/cmdb/tests/test_import_helpers.py -k "load_provider" -v`

Expected: FAIL because `apps.cmdb.extensions.loader` does not exist yet.

- [ ] **Step 3: Write the minimal shared loader**

```python
# server/apps/cmdb/extensions/loader.py
from importlib import import_module


def load_provider(module_path: str, attr_name: str, *, default):
    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name == module_path:
            return default
        raise

    if not hasattr(module, attr_name):
        raise AttributeError(f"{module_path} must define {attr_name}")
    return getattr(module, attr_name)
```

```python
# server/apps/cmdb/extensions/__init__.py
"""CMDB explicit extension facades."""
```

- [ ] **Step 4: Run the focused loader tests to verify they pass**

Run: `cd server && uv run pytest apps/cmdb/tests/test_import_helpers.py -k "load_provider" -v`

Expected: PASS with fallback, success, and contract-missing paths covered.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/extensions/__init__.py \
        server/apps/cmdb/extensions/loader.py \
        server/apps/cmdb/tests/test_import_helpers.py
git commit -m "feat(cmdb): add enterprise provider loader"
```

## Task 2: Add the collect facade and route collect object tree through it

**Files:**
- Create: `server/apps/cmdb/collection/extensions.py`
- Create: `server/apps/cmdb/enterprise/collect/__init__.py`
- Create: `server/apps/cmdb/enterprise/collect/provider.py`
- Modify: `server/apps/cmdb/services/collect_object_tree.py`
- Modify: `server/apps/cmdb/tests/test_collect_object_tree.py`

- [ ] **Step 1: Write the failing collect facade tests**

```python
# server/apps/cmdb/tests/test_collect_object_tree.py
import sys
import types

from apps.cmdb.collection.extensions import (
    CollectEnterpriseExtension,
    get_collect_enterprise_extension,
)
from apps.cmdb.services.collect_object_tree import get_collect_obj_tree


def test_get_collect_enterprise_extension_missing_provider():
    sys.modules.pop("apps.cmdb.enterprise.collect.provider", None)
    extension = get_collect_enterprise_extension()
    assert extension.collect_tree == []
    assert extension.plugin_packages == ()
    assert extension.node_param_packages == ()


def test_get_collect_enterprise_extension_reads_provider(monkeypatch):
    fake = types.ModuleType("apps.cmdb.enterprise.collect.provider")
    fake.get_collect_enterprise_extension = lambda: CollectEnterpriseExtension(
        collect_tree=[{"id": "middleware", "children": [{"model_id": "enterprise_demo"}]}],
        plugin_packages=("apps.cmdb.enterprise",),
        node_param_packages=("apps.cmdb.enterprise",),
    )
    monkeypatch.setitem(sys.modules, "apps.cmdb.enterprise.collect.provider", fake)
    extension = get_collect_enterprise_extension()
    assert extension.plugin_packages == ("apps.cmdb.enterprise",)
    assert extension.node_param_packages == ("apps.cmdb.enterprise",)


def test_get_collect_obj_tree_uses_collect_extension(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.collect_object_tree.get_collect_enterprise_extension",
        lambda: CollectEnterpriseExtension(
            collect_tree=[{"id": "middleware", "children": [{"model_id": "_ent_new_model", "label": "企业新增"}]}],
            plugin_packages=(),
            node_param_packages=(),
        ),
    )
    tree = get_collect_obj_tree()
    category = next(item for item in tree if item["id"] == "middleware")
    assert any(child.get("model_id") == "_ent_new_model" for child in category["children"])
```

- [ ] **Step 2: Run the focused collect tests to verify they fail**

Run: `cd server && uv run pytest apps/cmdb/tests/test_collect_object_tree.py -k "collect_enterprise_extension or uses_collect_extension" -v`

Expected: FAIL because the collect facade and provider contract do not exist yet, and `collect_object_tree.py` still imports `apps.cmdb.enterprise.tree` directly.

- [ ] **Step 3: Implement the collect contract and provider wrapper**

```python
# server/apps/cmdb/collection/extensions.py
from dataclasses import dataclass, field

from apps.cmdb.extensions.loader import load_provider


@dataclass(frozen=True)
class CollectEnterpriseExtension:
    collect_tree: list[dict] = field(default_factory=list)
    plugin_packages: tuple[str, ...] = ()
    node_param_packages: tuple[str, ...] = ()


_EMPTY_COLLECT_EXTENSION = CollectEnterpriseExtension()


def get_collect_enterprise_extension() -> CollectEnterpriseExtension:
    factory = load_provider(
        "apps.cmdb.enterprise.collect.provider",
        "get_collect_enterprise_extension",
        default=lambda: _EMPTY_COLLECT_EXTENSION,
    )
    return factory()
```

```python
# server/apps/cmdb/enterprise/collect/__init__.py
"""CMDB collect enterprise providers."""
```

```python
# server/apps/cmdb/enterprise/collect/provider.py
from copy import deepcopy
from importlib import import_module

from apps.cmdb.collection.extensions import CollectEnterpriseExtension


def _optional_module(module_path: str):
    try:
        return import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name == module_path:
            return None
        raise


def get_collect_enterprise_extension() -> CollectEnterpriseExtension:
    tree_module = _optional_module("apps.cmdb.enterprise.tree")
    collect_tree = deepcopy(getattr(tree_module, "ENTERPRISE_COLLECT_OBJ_TREE", [])) if tree_module else []
    return CollectEnterpriseExtension(
        collect_tree=collect_tree,
        plugin_packages=("apps.cmdb.enterprise",),
        node_param_packages=("apps.cmdb.enterprise",),
    )
```

```python
# server/apps/cmdb/services/collect_object_tree.py
from copy import deepcopy

from apps.cmdb.collection.extensions import get_collect_enterprise_extension
from apps.cmdb.constants.constants import COLLECT_OBJ_TREE


def _get_enterprise_collect_obj_tree():
    return deepcopy(get_collect_enterprise_extension().collect_tree)
```

- [ ] **Step 4: Run the focused collect tests to verify they pass**

Run: `cd server && uv run pytest apps/cmdb/tests/test_collect_object_tree.py -k "collect_enterprise_extension or uses_collect_extension" -v`

Expected: PASS with collect tree merging driven by the new facade/provider pair.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/collection/extensions.py \
        server/apps/cmdb/enterprise/collect/__init__.py \
        server/apps/cmdb/enterprise/collect/provider.py \
        server/apps/cmdb/services/collect_object_tree.py \
        server/apps/cmdb/tests/test_collect_object_tree.py
git commit -m "refactor(cmdb): add collect enterprise facade"
```

## Task 3: Route plugin loading and NodeParams registration through the collect facade

**Files:**
- Modify: `server/apps/cmdb/collection/plugins/loader.py`
- Modify: `server/apps/cmdb/node_configs/__init__.py`
- Modify: `server/apps/cmdb/tests/test_node_params_multicred.py`

- [ ] **Step 1: Write the failing collect package-registration regression**

```python
# server/apps/cmdb/tests/test_node_params_multicred.py
from apps.cmdb.collection.extensions import CollectEnterpriseExtension


def test_collect_extension_exposes_enterprise_registration_packages(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.collection.extensions.load_provider",
        lambda *args, **kwargs: lambda: CollectEnterpriseExtension(
            collect_tree=[],
            plugin_packages=("apps.cmdb.enterprise",),
            node_param_packages=("apps.cmdb.enterprise",),
        ),
    )
    extension = __import__("apps.cmdb.collection.extensions", fromlist=["get_collect_enterprise_extension"])
    resolved = extension.get_collect_enterprise_extension()
    assert resolved.plugin_packages == ("apps.cmdb.enterprise",)
    assert resolved.node_param_packages == ("apps.cmdb.enterprise",)
```

- [ ] **Step 2: Run the focused registration regression to verify the facade contract is visible**

Run: `cd server && uv run pytest apps/cmdb/tests/test_node_params_multicred.py -k "registration_packages" -v`

Expected: PASS only after the collect facade exists and exposes package metadata in a stable shape.

- [ ] **Step 3: Switch loader and node registration to the collect facade**

```python
# server/apps/cmdb/collection/plugins/loader.py
from apps.cmdb.collection.extensions import get_collect_enterprise_extension


class CollectionPluginLoader:
    _loaded = False
    _package_names = ["apps.cmdb.collection.plugins.community"]

    @classmethod
    def load_plugins(cls):
        if cls._loaded:
            return True

        package_names = list(
            dict.fromkeys(
                [*cls._package_names, *get_collect_enterprise_extension().plugin_packages]
            )
        )
        has_error = False
        for package_name in package_names:
            if not cls._load_package(package_name):
                has_error = True
        cls._loaded = not has_error
        return cls._loaded
```

```python
# server/apps/cmdb/node_configs/__init__.py
from apps.cmdb.collection.extensions import get_collect_enterprise_extension


def _auto_register_node_params():
    current_dir = Path(__file__).parent
    package_name = __name__

    _import_modules_in_package(package_name, [str(current_dir)])

    for package_name in get_collect_enterprise_extension().node_param_packages:
        _auto_register_from_package(package_name)
```

- [ ] **Step 4: Run the focused regression and a one-line import smoke**

Run: `cd server && uv run pytest apps/cmdb/tests/test_node_params_multicred.py -k "registration_packages" -v`

Expected: PASS with the collect facade contract still intact.

Run: `cd server && uv run python -c "from apps.cmdb.collection.plugins.loader import CollectionPluginLoader; from apps.cmdb.node_configs import BaseNodeParams; CollectionPluginLoader._loaded = False; CollectionPluginLoader.load_plugins(); print('collect-extension-smoke-ok', bool(BaseNodeParams._registry))"`

Expected: Prints `collect-extension-smoke-ok True` (or at minimum a truthy registry) without direct `apps.cmdb.enterprise` imports remaining in community call sites.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/collection/plugins/loader.py \
        server/apps/cmdb/node_configs/__init__.py \
        server/apps/cmdb/tests/test_node_params_multicred.py
git commit -m "refactor(cmdb): route collect enterprise packages through facade"
```

## Task 4: Add the model facade and wire representative model responses

**Files:**
- Create: `server/apps/cmdb/model_ops/__init__.py`
- Create: `server/apps/cmdb/model_ops/extensions.py`
- Create: `server/apps/cmdb/enterprise/model_ops/__init__.py`
- Create: `server/apps/cmdb/enterprise/model_ops/provider.py`
- Modify: `server/apps/cmdb/views/model.py`
- Modify: `server/apps/cmdb/tests/test_model_views.py`

- [ ] **Step 1: Write the failing model enterprise facade regressions**

```python
# server/apps/cmdb/tests/test_model_views.py
class _ModelEnterpriseExtension:
    def extend_model_info(self, request, model_info):
        data = dict(model_info)
        data["enterprise_actions"] = ["sync_to_enterprise"]
        return data

    def extend_model_list(self, request, model_list):
        return [{**item, "enterprise_enabled": True} for item in model_list]


@pytest.mark.django_db
def test_get_model_info_applies_enterprise_extension(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info",
        lambda model_id: {"model_id": "host", "model_name": "主机", "group": [1]},
    )
    monkeypatch.setattr(
        f"{VIEWS}.get_model_enterprise_extension",
        lambda: _ModelEnterpriseExtension(),
    )
    response = ModelViewSet.as_view({"get": "get_model_info"})(_req("get", superuser), model_id="host")
    assert _body(response)["data"]["enterprise_actions"] == ["sync_to_enterprise"]


@pytest.mark.django_db
def test_list_models_applies_enterprise_extension(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model",
        lambda language=None, permissions_map=None: [{"model_id": "host", "group": [1]}],
    )
    monkeypatch.setattr(
        f"{VIEWS}.get_model_enterprise_extension",
        lambda: _ModelEnterpriseExtension(),
    )
    response = ModelViewSet.as_view({"get": "list"})(_req("get", superuser))
    assert _body(response)["data"][0]["enterprise_enabled"] is True
```

- [ ] **Step 2: Run the focused model tests to verify they fail**

Run: `cd server && uv run pytest apps/cmdb/tests/test_model_views.py -k "enterprise_extension" -v`

Expected: FAIL because `get_model_enterprise_extension()` does not exist in `views/model.py`, and model responses do not yet pass through a facade.

- [ ] **Step 3: Implement the model facade and wire the view paths**

```python
# server/apps/cmdb/model_ops/__init__.py
"""CMDB model enterprise facades."""
```

```python
# server/apps/cmdb/model_ops/extensions.py
from dataclasses import dataclass

from apps.cmdb.extensions.loader import load_provider


@dataclass(frozen=True)
class ModelEnterpriseExtension:
    def extend_model_info(self, request, model_info: dict) -> dict:
        return model_info

    def extend_model_list(self, request, model_list: list[dict]) -> list[dict]:
        return model_list


_EMPTY_MODEL_EXTENSION = ModelEnterpriseExtension()


def get_model_enterprise_extension() -> ModelEnterpriseExtension:
    factory = load_provider(
        "apps.cmdb.enterprise.model_ops.provider",
        "get_model_enterprise_extension",
        default=lambda: _EMPTY_MODEL_EXTENSION,
    )
    return factory()
```

```python
# server/apps/cmdb/enterprise/model_ops/__init__.py
"""CMDB enterprise model providers."""
```

```python
# server/apps/cmdb/enterprise/model_ops/provider.py
from apps.cmdb.model_ops.extensions import ModelEnterpriseExtension


def get_model_enterprise_extension() -> ModelEnterpriseExtension:
    return ModelEnterpriseExtension()
```

```python
# server/apps/cmdb/views/model.py
from apps.cmdb.model_ops.extensions import get_model_enterprise_extension


class ModelViewSet(CmdbPermissionMixin, viewsets.ViewSet):
    @HasPermission("model_management-View")
    @action(detail=False, methods=["get"], url_path="get_model_info/(?P<model_id>.+?)")
    def get_model_info(self, request, model_id: str):
        extension = get_model_enterprise_extension()
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request,
            model_id=model_info["model_id"],
            permission_type=PERMISSION_MODEL,
        )
        permission_error = self.require_model_view_permission(
            request,
            model_info,
            default_group_id=self.default_group_id,
            error_message="抱歉！您没有此模型的权限",
            permissions_map=permissions_map,
        )
        if permission_error:
            return permission_error

        self.model_add_permission(
            permission_instances_map=permissions_map,
            model_list=[model_info],
            default_group=self.default_group_id,
        )
        model_info = extension.extend_model_info(request, model_info)
        return WebUtils.response_success(model_info)

    @HasPermission("model_management-View")
    def list(self, request):
        extension = get_model_enterprise_extension()
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request,
            model_id="",
            permission_type=PERMISSION_MODEL,
        )
        current_team = get_current_team_from_request(request)
        default_group_id = self.default_group_id
        default_group_permission = {"permission_instances_map": {}, "inst_names": []}
        if default_group_id != current_team:
            default_group_permission["__default_model"] = [VIEW]

        default_group_id_permission = permissions_map.pop(default_group_id, default_group_permission)
        permissions_map[default_group_id] = default_group_id_permission
        result = ModelManage.search_model(language=request.user.locale, permissions_map=permissions_map)
        permissions_map[default_group_id]["inst_names"] = default_group_id_permission["inst_names"]
        self.model_add_permission(
            permission_instances_map=permissions_map,
            model_list=result,
            default_group=default_group_id,
        )
        result = extension.extend_model_list(request, result)
        return WebUtils.response_success(result)
```

- [ ] **Step 4: Run the focused model tests to verify they pass**

Run: `cd server && uv run pytest apps/cmdb/tests/test_model_views.py -k "enterprise_extension" -v`

Expected: PASS with the default provider remaining no-op and monkeypatched enterprise enrichments applied to detail/list responses.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/model_ops/__init__.py \
        server/apps/cmdb/model_ops/extensions.py \
        server/apps/cmdb/enterprise/model_ops/__init__.py \
        server/apps/cmdb/enterprise/model_ops/provider.py \
        server/apps/cmdb/views/model.py \
        server/apps/cmdb/tests/test_model_views.py
git commit -m "feat(cmdb): add model enterprise facade"
```

## Task 5: Add the instance facade and wire representative instance responses

**Files:**
- Create: `server/apps/cmdb/instance_ops/__init__.py`
- Create: `server/apps/cmdb/instance_ops/extensions.py`
- Create: `server/apps/cmdb/enterprise/instance_ops/__init__.py`
- Create: `server/apps/cmdb/enterprise/instance_ops/provider.py`
- Modify: `server/apps/cmdb/views/instance.py`
- Modify: `server/apps/cmdb/tests/test_instance_views.py`

- [ ] **Step 1: Write the failing instance enterprise facade regressions**

```python
# server/apps/cmdb/tests/test_instance_views.py
class _InstanceEnterpriseExtension:
    def extend_search_payload(self, request, payload):
        data = dict(payload)
        data["enterprise_summary"] = {"enabled": True}
        return data

    def extend_instance_detail(self, request, instance):
        data = dict(instance)
        data["enterprise_tabs"] = ["risk"]
        return data


@pytest.mark.django_db
def test_search_applies_instance_enterprise_extension(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.instance_list",
        lambda *args, **kwargs: ([{"_id": 1, "inst_name": "h", "organization": [1], "_creator": "admin"}], 1),
    )
    monkeypatch.setattr(
        f"{VIEWS}.get_instance_enterprise_extension",
        lambda: _InstanceEnterpriseExtension(),
    )
    response = _call({"post": "search"}, _req("post", superuser, data={"model_id": "host"}))
    assert _body(response)["data"]["enterprise_summary"] == {"enabled": True}


@pytest.mark.django_db
def test_retrieve_applies_instance_enterprise_extension(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 5, "model_id": "host", "inst_name": "h", "organization": [1], "_creator": "bob"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.get_instance_enterprise_extension",
        lambda: _InstanceEnterpriseExtension(),
    )
    response = _call({"get": "retrieve"}, _req("get", superuser), pk="5")
    assert _body(response)["data"]["enterprise_tabs"] == ["risk"]
```

- [ ] **Step 2: Run the focused instance tests to verify they fail**

Run: `cd server && uv run pytest apps/cmdb/tests/test_instance_views.py -k "enterprise_extension" -v`

Expected: FAIL because `get_instance_enterprise_extension()` does not exist in `views/instance.py`, and instance payloads do not yet flow through an explicit facade.

- [ ] **Step 3: Implement the instance facade and wire the view paths**

```python
# server/apps/cmdb/instance_ops/__init__.py
"""CMDB instance enterprise facades."""
```

```python
# server/apps/cmdb/instance_ops/extensions.py
from dataclasses import dataclass

from apps.cmdb.extensions.loader import load_provider


@dataclass(frozen=True)
class InstanceEnterpriseExtension:
    def extend_search_payload(self, request, payload: dict) -> dict:
        return payload

    def extend_instance_detail(self, request, instance: dict) -> dict:
        return instance


_EMPTY_INSTANCE_EXTENSION = InstanceEnterpriseExtension()


def get_instance_enterprise_extension() -> InstanceEnterpriseExtension:
    factory = load_provider(
        "apps.cmdb.enterprise.instance_ops.provider",
        "get_instance_enterprise_extension",
        default=lambda: _EMPTY_INSTANCE_EXTENSION,
    )
    return factory()
```

```python
# server/apps/cmdb/enterprise/instance_ops/__init__.py
"""CMDB enterprise instance providers."""
```

```python
# server/apps/cmdb/enterprise/instance_ops/provider.py
from apps.cmdb.instance_ops.extensions import InstanceEnterpriseExtension


def get_instance_enterprise_extension() -> InstanceEnterpriseExtension:
    return InstanceEnterpriseExtension()
```

```python
# server/apps/cmdb/views/instance.py
from apps.cmdb.instance_ops.extensions import get_instance_enterprise_extension


class InstanceViewSet(CmdbPermissionMixin, viewsets.ViewSet):
    @HasPermission("asset_info-View")
    @action(methods=["post"], detail=False)
    def search(self, request):
        extension = get_instance_enterprise_extension()
        model_id = request.data.get("model_id")
        if not model_id:
            return WebUtils.response_error("model_id不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        query_list = self._normalize_query_list(request.data.get("query_list", []))
        page = self._parse_positive_int(request.data.get("page", 1), field_name="page", default=1)
        page_size = self._parse_positive_int(request.data.get("page_size", 10), field_name="page_size", default=10)
        case_sensitive = request.data.get("case_sensitive", True)
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request, model_id)
        instance_list, count = InstanceManage.instance_list(
            request,
            model_id,
            query_list=query_list,
            permissions_map=permissions_map,
            page=page,
            page_size=page_size,
            case_sensitive=case_sensitive,
        )
        self.add_instance_permission(
            instances=instance_list,
            permission_instances_map=permissions_map,
            creator=request.user.username,
        )
        payload = {"insts": instance_list, "count": count}
        payload = extension.extend_search_payload(request, payload)
        return WebUtils.response_success(payload)

    @HasPermission("asset_info-View")
    def retrieve(self, request, pk: str):
        extension = get_instance_enterprise_extension()
        instance = InstanceManage.query_entity_by_id(int(pk))
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        if self.check_creator_and_organizations(request, instance):
            instance["permission"] = [VIEW, OPERATE]
            instance = extension.extend_instance_detail(request, instance)
            return WebUtils.response_success(instance)

        organizations = self.organizations(request, instance)
        if not organizations:
            return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

        model_id = instance["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=model_id)
        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_INSTANCES,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=instance,
        )
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

        self.add_instance_permission(
            instances=[instance],
            permission_instances_map=permissions_map,
            creator=request.user.username,
        )
        instance = extension.extend_instance_detail(request, instance)
        return WebUtils.response_success(instance)
```

- [ ] **Step 4: Run the focused instance tests to verify they pass**

Run: `cd server && uv run pytest apps/cmdb/tests/test_instance_views.py -k "enterprise_extension" -v`

Expected: PASS with search/retrieve payload enrichment isolated behind the instance facade and default behavior unchanged when enterprise is absent.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/instance_ops/__init__.py \
        server/apps/cmdb/instance_ops/extensions.py \
        server/apps/cmdb/enterprise/instance_ops/__init__.py \
        server/apps/cmdb/enterprise/instance_ops/provider.py \
        server/apps/cmdb/views/instance.py \
        server/apps/cmdb/tests/test_instance_views.py
git commit -m "feat(cmdb): add instance enterprise facade"
```

## Final Verification

- [ ] **Run the focused CMDB enterprise layering suite**

```bash
cd server && uv run pytest \
    apps/cmdb/tests/test_import_helpers.py \
    apps/cmdb/tests/test_collect_object_tree.py \
    apps/cmdb/tests/test_node_params_multicred.py \
    apps/cmdb/tests/test_model_views.py \
    apps/cmdb/tests/test_instance_views.py -v
```

Expected: PASS with provider loading, collect extension routing, model facade wiring, and instance facade wiring all green.

- [ ] **Run the standard server entry after the focused suite passes**

```bash
cd server && make test
```

Expected: PASS, or if repository baseline is already red, isolate and record unrelated pre-existing failures before proceeding.

## Self-Review

1. **Spec coverage:** The plan implements the approved design in order: one shared loader, collect-domain facade migration, collect plugin/node registration convergence, model facade wiring, and instance facade wiring. It also preserves the additive-only rule by keeping absent enterprise providers on an empty-contract path.
2. **Placeholder scan:** No unfinished markers, cross-task shorthand, or content-free “write tests” steps remain; every task names exact files, commands, and code to add.
3. **Type consistency:** The same contract names and factory names are used throughout: `CollectEnterpriseExtension`, `ModelEnterpriseExtension`, `InstanceEnterpriseExtension`, `get_collect_enterprise_extension()`, `get_model_enterprise_extension()`, and `get_instance_enterprise_extension()`.

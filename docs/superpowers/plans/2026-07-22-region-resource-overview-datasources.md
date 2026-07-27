# Region Resource Overview Datasources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two permission-aware CMDB datasources that expose configured region tags and summarize one region's instance counts by visible model classification for the existing multiValue widget.

**Architecture:** Put tag-candidate parsing and classification aggregation in a focused pure service. Keep NATS handlers thin: resolve language and permission maps, call existing CMDB model/classification/instance services, and delegate deterministic transformation to the new service. Register two built-in datasource definitions linked by stable `rest_api` reference.

**Tech Stack:** Python 3.12, Django 4.2, pytest, unittest.mock, FalkorDB-backed CMDB services, NATS handler registry, JSON built-in datasource definitions.

## Global Constraints

- The region tag key is exactly lowercase `region`; do not add a configurable `tag_key` parameter.
- Region options come from visible, authorized model tag candidate definitions, even when no instance currently uses the region.
- Resource counts must intersect model permission, instance permission, organization scope, visible models, visible classifications, and the exact instance tag `region:<value>`.
- Omit zero-count classifications; sort by count descending, then localized classification name ascending.
- One multiValue widget stores one `region`; do not add a new card component or an all-regions response.
- Do not modify existing model classification/count, `get_model_inst_statistics`, TopN, or multiValue behavior.
- Use existing CMDB graph services and Django ORM conventions; do not introduce raw SQL or fetch all instances into Python.
- Preserve unrelated staged and untracked workspace changes; task commits must name only their own files.

---

## File Structure

- Create `server/apps/cmdb/services/region_resource_overview.py`: pure parsing, deduplication, visibility filtering, classification accumulation, and stable sorting.
- Create `server/apps/cmdb/tests/test_region_resource_overview_service.py`: fast unit coverage for valid, legacy, malformed, hidden, zero, and ordering cases.
- Modify `server/apps/cmdb/nats/nats.py`: import the service and register `get_region_options` plus `get_region_resource_overview`.
- Create `server/apps/cmdb/tests/test_nats_region_resource_overview.py`: isolated handler tests for permission propagation, tag filter construction, language, empty responses, and exception propagation.
- Modify `server/apps/operation_analysis/support-files/source_api.json`: add the two datasource contracts.
- Create `server/apps/operation_analysis/tests/test_region_resource_overview_datasource_definitions.py`: verify JSON shape and stable dynamic source linkage.

### Task 1: Build the region candidate and classification aggregation service

**Files:**
- Create: `server/apps/cmdb/services/region_resource_overview.py`
- Test: `server/apps/cmdb/tests/test_region_resource_overview_service.py`

**Interfaces:**
- Consumes: model dictionaries returned by `ModelManage.search_model`, classification dictionaries returned by `ClassificationManage.search_model_classification`, and `{model_id: count}` returned by `InstanceManage.group_inst_count`.
- Produces: `extract_region_options(models, visible_classification_ids) -> list[dict[str, str]]` and `build_region_resource_items(models, classifications, model_counts) -> list[dict[str, str | int]]`.

- [ ] **Step 1: Write failing service tests**

Create `test_region_resource_overview_service.py`:

```python
import json

import pytest

from apps.cmdb.services.region_resource_overview import (
    build_region_resource_items,
    extract_region_options,
)


@pytest.mark.unit
def test_extract_region_options_supports_list_and_legacy_json_attrs():
    tag_attr = {
        "attr_id": "tag",
        "attr_type": "tag",
        "option": {
            "mode": "free",
            "options": [
                {"key": "region", "value": " 本部 "},
                {"key": "env", "value": "prod"},
                {"key": "Region", "value": "ignored"},
            ],
        },
    }
    models = [
        {"model_id": "host", "classification_id": "host", "attrs": [tag_attr]},
        {
            "model_id": "mysql",
            "classification_id": "database",
            "attrs": json.dumps([
                {
                    "attr_id": "tag",
                    "attr_type": "tag",
                    "option": {
                        "mode": "strict",
                        "options": [
                            {"key": "region", "value": "东区"},
                            {"key": "region", "value": "本部"},
                        ],
                    },
                }
            ], ensure_ascii=False),
        },
    ]

    assert extract_region_options(models, {"host", "database"}) == [
        {"label": "东区", "value": "东区"},
        {"label": "本部", "value": "本部"},
    ]


@pytest.mark.unit
def test_extract_region_options_ignores_hidden_classification_and_malformed_data():
    models = [
        {
            "model_id": "hidden",
            "classification_id": "hidden_classification",
            "attrs": [{
                "attr_id": "tag",
                "attr_type": "tag",
                "option": {"options": [{"key": "region", "value": "秘密地区"}]},
            }],
        },
        {"model_id": "broken-json", "classification_id": "host", "attrs": "not-json"},
        {"model_id": "wrong-options", "classification_id": "host", "attrs": [{
            "attr_id": "tag", "attr_type": "tag", "option": {"options": {}},
        }]},
        {"model_id": "bad-items", "classification_id": "host", "attrs": [{
            "attr_id": "tag",
            "attr_type": "tag",
            "option": {"options": [None, {}, {"key": "region", "value": "  "}]},
        }]},
    ]

    assert extract_region_options(models, {"host"}) == []


@pytest.mark.unit
def test_build_region_resource_items_accumulates_filters_and_sorts():
    models = [
        {"model_id": "mysql", "classification_id": "database"},
        {"model_id": "postgres", "classification_id": "database"},
        {"model_id": "linux", "classification_id": "host"},
        {"model_id": "nginx", "classification_id": "middleware"},
        {"model_id": "zero", "classification_id": "middleware"},
        {"model_id": "missing-class", "classification_id": "missing"},
        {"model_id": "unclassified"},
    ]
    classifications = [
        {"classification_id": "database", "classification_name": "数据库"},
        {"classification_id": "host", "classification_name": "主机"},
        {"classification_id": "middleware", "classification_name": "中间件"},
    ]
    model_counts = {
        "mysql": 150,
        "postgres": 150,
        "linux": 200,
        "nginx": 200,
        "zero": 0,
        "missing-class": 999,
        "unclassified": 999,
        "unknown-model": 999,
    }

    assert build_region_resource_items(models, classifications, model_counts) == [
        {"label": "数据库", "value": 300},
        {"label": "中间件", "value": 200},
        {"label": "主机", "value": 200},
    ]


@pytest.mark.unit
def test_build_region_resource_items_returns_empty_for_no_positive_visible_counts():
    assert build_region_resource_items(
        [{"model_id": "host", "classification_id": "host"}],
        [{"classification_id": "host", "classification_name": "主机"}],
        {"host": 0},
    ) == []
```

- [ ] **Step 2: Run the service tests and verify RED**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_region_resource_overview_service.py -q
```

Expected: FAIL during collection because `apps.cmdb.services.region_resource_overview` does not exist.

- [ ] **Step 3: Implement the minimal pure service**

Create `region_resource_overview.py`:

```python
import json
from collections import defaultdict


REGION_TAG_KEY = "region"


def _parse_attrs(raw_attrs):
    if isinstance(raw_attrs, list):
        return raw_attrs
    if isinstance(raw_attrs, str):
        try:
            parsed = json.loads(raw_attrs.replace('\\"', '"'))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def extract_region_options(models, visible_classification_ids):
    values = set()
    for model in models:
        if model.get("classification_id") not in visible_classification_ids:
            continue
        attrs = _parse_attrs(model.get("attrs"))
        tag_attr = next(
            (
                attr
                for attr in attrs
                if isinstance(attr, dict)
                and attr.get("attr_id") == "tag"
                and attr.get("attr_type") == "tag"
            ),
            None,
        )
        if not tag_attr:
            continue
        option = tag_attr.get("option")
        options = option.get("options") if isinstance(option, dict) else None
        if not isinstance(options, list):
            continue
        for item in options:
            if not isinstance(item, dict) or item.get("key") != REGION_TAG_KEY:
                continue
            value = str(item.get("value") or "").strip()
            if value:
                values.add(value)
    return [{"label": value, "value": value} for value in sorted(values)]


def build_region_resource_items(models, classifications, model_counts):
    classification_names = {
        item.get("classification_id"): item.get("classification_name", "")
        for item in classifications
        if item.get("classification_id")
    }
    totals = defaultdict(int)
    for model in models:
        classification_id = model.get("classification_id")
        model_id = model.get("model_id")
        if classification_id not in classification_names or not model_id:
            continue
        count = model_counts.get(model_id, 0)
        if isinstance(count, (int, float)) and count > 0:
            totals[classification_id] += count

    items = [
        {"label": classification_names[classification_id], "value": count}
        for classification_id, count in totals.items()
        if count > 0
    ]
    items.sort(key=lambda item: (-item["value"], item["label"]))
    return items
```

Keep the service free of request, NATS, permission, and graph-client imports.

- [ ] **Step 4: Run service verification**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_region_resource_overview_service.py -q
```

Expected: 4 tests PASS.

Run:

```powershell
uv run python -m py_compile apps/cmdb/services/region_resource_overview.py apps/cmdb/tests/test_region_resource_overview_service.py
```

Expected: exit code 0.

- [ ] **Step 5: Commit the service**

```powershell
git add -- server/apps/cmdb/services/region_resource_overview.py server/apps/cmdb/tests/test_region_resource_overview_service.py
git commit -m "feat: add CMDB region resource overview service"
```

### Task 2: Add the two NATS datasource handlers

**Files:**
- Modify: `server/apps/cmdb/nats/nats.py`
- Create: `server/apps/cmdb/tests/test_nats_region_resource_overview.py`

**Interfaces:**
- Consumes: `_resolve_nats_cmdb_language`, `_build_nats_model_permission_map`, `_build_nats_permission_map`, `ModelManage.search_model`, `ClassificationManage.search_model_classification`, `InstanceManage.group_inst_count`, and Task 1 service functions.
- Produces: `get_region_options(user_info=None, **kwargs) -> {"items": list}` and `get_region_resource_overview(region=None, user_info=None, **kwargs) -> {"items": list}`.

- [ ] **Step 1: Write failing handler tests**

Create `test_nats_region_resource_overview.py`:

```python
from unittest.mock import patch

import pytest

from apps.cmdb.nats import nats


USER_INFO = {"team": 1, "user": "alice", "language": "zh-CN"}
MODEL_PERMISSIONS = {1: {"inst_names": []}}
INSTANCE_PERMISSIONS = {1: {"inst_names": []}}
CLASSIFICATIONS = [{"classification_id": "host", "classification_name": "主机"}]
MODELS = [{
    "model_id": "linux",
    "model_name": "Linux",
    "classification_id": "host",
    "attrs": [{
        "attr_id": "tag",
        "attr_type": "tag",
        "option": {"options": [{"key": "region", "value": "本部"}]},
    }],
}]


@pytest.mark.unit
class TestGetRegionOptions:
    @patch("apps.cmdb.nats.nats.extract_region_options")
    @patch.object(nats.ClassificationManage, "search_model_classification")
    @patch.object(nats.ModelManage, "search_model")
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_passes_visible_authorized_models_to_service(
        self, permission_mock, models_mock, classifications_mock, extract_mock
    ):
        models_mock.return_value = MODELS
        classifications_mock.return_value = CLASSIFICATIONS
        extract_mock.return_value = [{"label": "本部", "value": "本部"}]

        assert nats.get_region_options(user_info=USER_INFO) == {
            "items": [{"label": "本部", "value": "本部"}]
        }
        models_mock.assert_called_once_with(language="zh", permissions_map=MODEL_PERMISSIONS)
        classifications_mock.assert_called_once_with(language="zh")
        extract_mock.assert_called_once_with(MODELS, {"host"})

    @patch.object(nats, "_build_nats_model_permission_map", return_value=None)
    def test_returns_empty_without_model_permission(self, permission_mock):
        assert nats.get_region_options(user_info=USER_INFO) == {"items": []}


@pytest.mark.unit
class TestGetRegionResourceOverview:
    @pytest.mark.parametrize("region", [None, "", "   "])
    def test_returns_empty_for_blank_region(self, region):
        assert nats.get_region_resource_overview(
            region=region, user_info=USER_INFO
        ) == {"items": []}

    @patch("apps.cmdb.nats.nats.build_region_resource_items")
    @patch("apps.cmdb.nats.nats.extract_region_options")
    @patch.object(nats.InstanceManage, "group_inst_count")
    @patch.object(nats.ClassificationManage, "search_model_classification")
    @patch.object(nats.ModelManage, "search_model")
    @patch.object(nats, "_build_nats_permission_map", return_value=INSTANCE_PERMISSIONS)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_queries_exact_region_tag_and_builds_items(
        self,
        model_permission_mock,
        instance_permission_mock,
        models_mock,
        classifications_mock,
        count_mock,
        extract_mock,
        build_mock,
    ):
        models_mock.return_value = MODELS
        classifications_mock.return_value = CLASSIFICATIONS
        extract_mock.return_value = [{"label": "本部", "value": "本部"}]
        count_mock.return_value = {"linux": 3}
        build_mock.return_value = [{"label": "主机", "value": 3}]

        assert nats.get_region_resource_overview(
            region=" 本部 ", user_info=USER_INFO
        ) == {"items": [{"label": "主机", "value": 3}]}
        count_mock.assert_called_once_with(
            group_by_attr="model_id",
            permissions_map=INSTANCE_PERMISSIONS,
            params=[{"field": "tag", "type": "list[]", "value": ["region:本部"]}],
        )
        build_mock.assert_called_once_with(MODELS, CLASSIFICATIONS, {"linux": 3})

    @patch.object(nats.InstanceManage, "group_inst_count")
    @patch("apps.cmdb.nats.nats.extract_region_options", return_value=[])
    @patch.object(nats.ClassificationManage, "search_model_classification", return_value=CLASSIFICATIONS)
    @patch.object(nats.ModelManage, "search_model", return_value=MODELS)
    @patch.object(nats, "_build_nats_permission_map", return_value=INSTANCE_PERMISSIONS)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_returns_empty_for_unknown_or_unauthorized_region(
        self,
        model_permission_mock,
        instance_permission_mock,
        models_mock,
        classifications_mock,
        extract_mock,
        count_mock,
    ):
        assert nats.get_region_resource_overview(
            region="秘密地区", user_info=USER_INFO
        ) == {"items": []}
        count_mock.assert_not_called()

    @patch.object(nats, "_build_nats_permission_map", return_value=None)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_returns_empty_without_instance_permission(
        self, model_permission_mock, instance_permission_mock
    ):
        assert nats.get_region_resource_overview(
            region="本部", user_info=USER_INFO
        ) == {"items": []}
```

Add one exception contract without swallowing the error:

```python
@pytest.mark.unit
@patch.object(nats.ModelManage, "search_model", side_effect=RuntimeError("graph failed"))
@patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
def test_get_region_options_propagates_service_errors(permission_mock, models_mock):
    with pytest.raises(RuntimeError, match="graph failed"):
        nats.get_region_options(user_info=USER_INFO)
```

- [ ] **Step 2: Run handler tests and verify RED**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_nats_region_resource_overview.py -q
```

Expected: FAIL because both NATS handler functions are missing.

- [ ] **Step 3: Import service functions and implement thin handlers**

Add this import near the existing CMDB service imports in `nats.py`:

```python
from apps.cmdb.services.region_resource_overview import (
    build_region_resource_items,
    extract_region_options,
)
```

Register the handlers near the existing model classification/count datasource handlers:

```python
@nats_client.register
def get_region_options(user_info=None, **kwargs):
    language = _resolve_nats_cmdb_language(user_info)
    model_permissions = _build_nats_model_permission_map(user_info)
    if model_permissions is None:
        return {"items": []}

    models = ModelManage.search_model(
        language=language,
        permissions_map=model_permissions,
    )
    classifications = ClassificationManage.search_model_classification(language=language)
    visible_classification_ids = {
        item.get("classification_id")
        for item in classifications
        if item.get("classification_id")
    }
    return {"items": extract_region_options(models, visible_classification_ids)}


@nats_client.register
def get_region_resource_overview(region=None, user_info=None, **kwargs):
    region = str(region or "").strip()
    if not region:
        return {"items": []}

    language = _resolve_nats_cmdb_language(user_info)
    model_permissions = _build_nats_model_permission_map(user_info)
    instance_permissions = _build_nats_permission_map(user_info)
    if model_permissions is None or instance_permissions is None:
        return {"items": []}

    models = ModelManage.search_model(
        language=language,
        permissions_map=model_permissions,
    )
    classifications = ClassificationManage.search_model_classification(language=language)
    visible_classification_ids = {
        item.get("classification_id")
        for item in classifications
        if item.get("classification_id")
    }
    allowed_regions = {
        item["value"]
        for item in extract_region_options(models, visible_classification_ids)
    }
    if region not in allowed_regions:
        return {"items": []}

    model_counts = InstanceManage.group_inst_count(
        group_by_attr="model_id",
        permissions_map=instance_permissions,
        params=[{"field": "tag", "type": "list[]", "value": [f"region:{region}"]}],
    )
    return {
        "items": build_region_resource_items(models, classifications, model_counts)
    }
```

Do not add exception handling around graph/service calls.

- [ ] **Step 4: Run handler and neighboring regression tests**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_nats_region_resource_overview.py apps/cmdb/tests/test_region_resource_overview_service.py -q
```

Expected: all new tests PASS.

Run the adjacent datasource-handler regressions:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_nats_model_count_datasources.py -q
```

Expected: PASS; the existing classification/count handlers remain unchanged.

- [ ] **Step 5: Commit the NATS handlers**

```powershell
git add -- server/apps/cmdb/nats/nats.py server/apps/cmdb/tests/test_nats_region_resource_overview.py
git commit -m "feat: add CMDB region overview datasource handlers"
```

### Task 3: Register the two built-in datasource definitions

**Files:**
- Modify: `server/apps/operation_analysis/support-files/source_api.json`
- Create: `server/apps/operation_analysis/tests/test_region_resource_overview_datasource_definitions.py`

**Interfaces:**
- Consumes: NATS routes `cmdb/get_region_options` and `cmdb/get_region_resource_overview` from Task 2.
- Produces: one non-chart option datasource and one `multiValue` datasource with a required dynamic `region` parameter.

- [ ] **Step 1: Write the failing datasource contract test**

Create `test_region_resource_overview_datasource_definitions.py`:

```python
import json
from pathlib import Path


SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"


def _sources_by_api():
    entries = json.loads(SOURCE_API.read_text(encoding="utf-8"))
    return {item["rest_api"]: item for item in entries}


def test_cmdb_region_options_datasource_contract():
    source = _sources_by_api()["cmdb/get_region_options"]
    assert source["chart_type"] == []
    assert source["params"] == []
    assert {field["key"] for field in source["field_schema"]} == {"label", "value"}
    assert {field["value_type"] for field in source["field_schema"]} == {"string"}


def test_cmdb_region_resource_overview_datasource_contract():
    source = _sources_by_api()["cmdb/get_region_resource_overview"]
    assert source["chart_type"] == ["multiValue"]
    param = next(item for item in source["params"] if item["name"] == "region")
    assert param["type"] == "string"
    assert param["required"] is True
    assert param["inputConfig"]["control"] == "select"
    assert param["inputConfig"]["optionsSource"] == {
        "type": "dynamic",
        "sourceRef": {"type": "rest_api", "value": "cmdb/get_region_options"},
        "valueField": "value",
        "labelField": "label",
    }
    field_types = {field["key"]: field["value_type"] for field in source["field_schema"]}
    assert field_types == {"label": "string", "value": "number"}
```

- [ ] **Step 2: Run the definition test and verify RED**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/operation_analysis/tests/test_region_resource_overview_datasource_definitions.py -q
```

Expected: FAIL with `KeyError: 'cmdb/get_region_options'`.

- [ ] **Step 3: Add the exact JSON datasource definitions**

Append these objects before the closing array bracket in `source_api.json`, preserving valid commas:

```json
{
  "name": "CMDB地区列表",
  "desc": "返回当前用户可见模型定义的全部region标签候选值，供运营分析参数动态选项使用",
  "rest_api": "cmdb/get_region_options",
  "tag": ["cmdb"],
  "chart_type": [],
  "params": [],
  "field_schema": [
    {"key": "label", "title": "地区名称", "value_type": "string", "description": "region标签候选项的地区名称"},
    {"key": "value", "title": "地区值", "value_type": "string", "description": "传给地区资源概览接口的region参数值"}
  ]
},
{
  "name": "地区资源概览",
  "desc": "按region标签统计当前权限范围内各CMDB模型分类的实例数量",
  "rest_api": "cmdb/get_region_resource_overview",
  "tag": ["cmdb"],
  "chart_type": ["multiValue"],
  "params": [
    {
      "name": "region",
      "type": "string",
      "value": "",
      "alias_name": "地区",
      "filterType": "params",
      "required": true,
      "inputConfig": {
        "control": "select",
        "optionsSource": {
          "type": "dynamic",
          "sourceRef": {"type": "rest_api", "value": "cmdb/get_region_options"},
          "valueField": "value",
          "labelField": "label"
        }
      }
    }
  ],
  "field_schema": [
    {"key": "label", "title": "资源分类", "value_type": "string", "description": "当前语言下的CMDB模型分类名称"},
    {"key": "value", "title": "实例数量", "value_type": "number", "description": "指定地区和当前权限范围内的分类实例总数"}
  ]
}
```

- [ ] **Step 4: Run definition and initialization regressions**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/operation_analysis/tests/test_region_resource_overview_datasource_definitions.py apps/operation_analysis/tests/test_cmdb_model_count_datasource_definitions.py -q
```

Expected: PASS; both the new region definitions and existing CMDB model count definitions remain valid.

Run:

```powershell
uv run pytest -o addopts= apps/operation_analysis/tests/test_management_commands.py::test_init_source_api_data_creates_tags_and_sources -q
```

Expected: PASS and `init_source_api_data` accepts both new entries.

- [ ] **Step 5: Commit the datasource definitions**

```powershell
git add -- server/apps/operation_analysis/support-files/source_api.json server/apps/operation_analysis/tests/test_region_resource_overview_datasource_definitions.py
git commit -m "feat: register CMDB region overview datasources"
```

### Task 4: Run the integrated acceptance gate

**Files:**
- Verify only; do not add production files in this task.

**Interfaces:**
- Consumes: the pure service, both NATS handlers, and both datasource definitions delivered by Tasks 1–3.
- Produces: verification evidence for the complete spec while preserving existing CMDB datasource behavior.

- [ ] **Step 1: Run all focused backend tests**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_region_resource_overview_service.py apps/cmdb/tests/test_nats_region_resource_overview.py apps/operation_analysis/tests/test_region_resource_overview_datasource_definitions.py -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run adjacent CMDB datasource regressions**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_nats_model_count_datasources.py apps/operation_analysis/tests/test_cmdb_model_count_datasource_definitions.py -q
```

Expected: PASS; no existing classification/count contract changes.

- [ ] **Step 3: Validate syntax, JSON, and whitespace**

Run from repository root:

```powershell
uv run python -m py_compile server/apps/cmdb/services/region_resource_overview.py server/apps/cmdb/nats/nats.py server/apps/cmdb/tests/test_region_resource_overview_service.py server/apps/cmdb/tests/test_nats_region_resource_overview.py
uv run python -m json.tool server/apps/operation_analysis/support-files/source_api.json > $null
git diff --check HEAD~3..HEAD
```

Expected: all commands exit 0.

- [ ] **Step 4: Record verified completion in project memory**

After every required check passes, run:

```powershell
pjm note "新增CMDB地区列表与地区资源概览两个NATS数据源：固定region标签候选、权限与可见性过滤、按模型分类汇总、零值过滤和降序排序均通过聚焦测试。" --at "server/apps/cmdb/services/region_resource_overview.py"
```

Expected: projectmem confirms the note was recorded. Do not create an empty verification-only commit.

# CMDB Classification Model Count Datasources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two permission-aware CMDB datasources for model-category selection and per-model instance counts, while making the multiValue widget accept array, `items`, and `data.items` responses.

**Architecture:** Keep the existing `get_model_inst_statistics` and TopN handlers unchanged. Add two focused NATS handlers that reuse CMDB model/instance permission maps and services, register two matching built-in datasource definitions, and normalize the three supported multiValue response envelopes at the shared validator boundary.

**Tech Stack:** Python 3.12, Django 4.2, pytest, unittest.mock, FalkorDB-backed CMDB services, NATS handler registry, TypeScript, React 19, Node assert/tsx.

## Global Constraints

- Do not change `get_model_inst_statistics` or `get_cmdb_model_instance_top` behavior or datasource definitions.
- Both new handlers must apply current model permissions, instance permissions, organization scope, `is_visible` filtering, and request language.
- The count datasource must omit zero-count models and sort by count descending, then localized model name ascending.
- The category datasource returns only visible categories containing at least one visible model the current user may view.
- The multiValue widget must support raw arrays, `{items: [...]}`, and `{data: {items: [...]}}` without weakening existing `label`/`value` validation.
- Use Django ORM and existing CMDB graph service methods; do not add raw SQL or raw Cypher.
- Preserve unrelated staged and untracked workspace changes; every commit must name only its task files.

---

## File Structure

- Modify `web/src/app/ops-analysis/utils/multiValueData.ts`: extract supported response envelopes before applying the existing strict item validation.
- Modify `web/scripts/ops-analysis-multi-value-test.ts`: cover all accepted envelopes, empty envelopes, and malformed wrappers.
- Modify `server/apps/cmdb/nats/nats.py`: add language resolution plus the two registered NATS handlers; reuse existing permission and aggregation services.
- Create `server/apps/cmdb/tests/test_nats_model_count_datasources.py`: isolated unit contracts for permission propagation, visibility, localization, filtering, and sorting.
- Modify `server/apps/operation_analysis/support-files/source_api.json`: register the two built-in datasource definitions and dynamic parameter linkage.
- Create `server/apps/operation_analysis/tests/test_cmdb_model_count_datasource_definitions.py`: validate the JSON contracts without requiring database initialization.

### Task 1: Normalize multiValue response envelopes

**Files:**
- Modify: `web/src/app/ops-analysis/utils/multiValueData.ts`
- Test: `web/scripts/ops-analysis-multi-value-test.ts`

**Interfaces:**
- Consumes: `validateMultiValueData(data: unknown, errorMessage: string)` used by dashboard, screen, and topology renderers.
- Produces: the same `MultiValueValidationResult` interface, with accepted input extended to raw arrays, `{items: unknown[]}`, and `{data: {items: unknown[]}}`.

- [ ] **Step 1: Add failing envelope and malformed-wrapper tests**

Add these cases immediately after the existing valid-array assertion:

```ts
for (const wrapped of [
  { items: [{ label: 'Tomcat', value: 100 }] },
  { data: { items: [{ label: 'Tomcat', value: 100 }] } },
]) {
  assert.deepEqual(validateMultiValueData(wrapped, mismatch), {
    isValid: true,
    items: [{ label: 'Tomcat', value: '100' }],
  });
}

for (const empty of [[], { items: [] }, { data: { items: [] } }]) {
  assert.deepEqual(validateMultiValueData(empty, mismatch), {
    isValid: true,
    items: [],
  });
}

for (const malformed of [
  {},
  { items: null },
  { items: {} },
  { data: null },
  { data: {} },
  { data: { items: 'invalid' } },
]) {
  assert.deepEqual(validateMultiValueData(malformed, mismatch), {
    isValid: false,
    errorMessage: mismatch,
    items: [],
  });
}
```

Remove the existing standalone `{}` invalid case and standalone empty-array assertion so each behavior is asserted once.

- [ ] **Step 2: Run the focused test and verify RED**

Run from `web/`:

```powershell
.\node_modules\.bin\tsx.CMD scripts\ops-analysis-multi-value-test.ts
```

Expected: FAIL because wrapped objects currently return `{isValid: false}`.

- [ ] **Step 3: Add one envelope extraction boundary**

In `multiValueData.ts`, add this helper above `validateMultiValueData` and validate the extracted value:

```ts
const extractMultiValueItems = (data: unknown): unknown => {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== 'object') return data;

  const record = data as Record<string, unknown>;
  if (Object.prototype.hasOwnProperty.call(record, 'items')) {
    return record.items;
  }

  const nested = record.data;
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    const nestedRecord = nested as Record<string, unknown>;
    if (Object.prototype.hasOwnProperty.call(nestedRecord, 'items')) {
      return nestedRecord.items;
    }
  }

  return data;
};
```

Change the beginning of `validateMultiValueData` to:

```ts
const extracted = extractMultiValueItems(data);
if (!Array.isArray(extracted)) {
  return { isValid: false, errorMessage, items: [] };
}

const items: MultiValueItem[] = [];
for (const entry of extracted) {
```

Keep every existing entry-level rule unchanged.

- [ ] **Step 4: Run focused verification**

Run from `web/`:

```powershell
.\node_modules\.bin\tsx.CMD scripts\ops-analysis-multi-value-test.ts
```

Expected: PASS and print the script's success message.

Run:

```powershell
.\node_modules\.bin\eslint.CMD src/app/ops-analysis/utils/multiValueData.ts scripts/ops-analysis-multi-value-test.ts
```

Expected: exit code 0 with no lint errors.

- [ ] **Step 5: Commit the envelope support**

```powershell
git add -- web/src/app/ops-analysis/utils/multiValueData.ts web/scripts/ops-analysis-multi-value-test.ts
git commit -m "feat: support wrapped multi-value responses"
```

### Task 2: Add permission-aware CMDB NATS handlers

**Files:**
- Modify: `server/apps/cmdb/nats/nats.py`
- Create: `server/apps/cmdb/tests/test_nats_model_count_datasources.py`

**Interfaces:**
- Consumes: `_build_nats_model_permission_map(user_info)`, `_build_nats_permission_map(user_info)`, `ClassificationManage.search_model_classification(language=...)`, `ModelManage.search_model(language=..., permissions_map=..., classification_ids=...)`, and `InstanceManage.model_inst_count(permissions_map=...)`.
- Produces: `get_model_classification_options(user_info=None, **kwargs) -> {"items": list[dict]}` and `get_classification_model_instance_counts(classification_id=None, user_info=None, **kwargs) -> {"items": list[dict]}`.

- [ ] **Step 1: Write failing handler contract tests**

Create `test_nats_model_count_datasources.py` with these focused mocks and use `pytest.mark.unit` on the test classes:

```python
from unittest.mock import patch

import pytest

from apps.cmdb.nats import nats


USER_INFO = {"team": 1, "user": "alice", "language": "zh-CN"}
MODEL_PERMISSIONS = {1: {"inst_names": []}}
INSTANCE_PERMISSIONS = {1: {"inst_names": []}}


@pytest.mark.unit
class TestModelClassificationOptions:
    @patch.object(nats.ModelManage, "search_model")
    @patch.object(nats.ClassificationManage, "search_model_classification")
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_returns_visible_authorized_categories_in_cmdb_order(
        self, permission_mock, classifications_mock, models_mock
    ):
        classifications_mock.return_value = [
            {"classification_id": "host", "classification_name": "主机"},
            {"classification_id": "middleware", "classification_name": "中间件"},
            {"classification_id": "database", "classification_name": "数据库"},
        ]
        models_mock.return_value = [
            {"model_id": "nginx", "classification_id": "middleware"},
            {"model_id": "linux", "classification_id": "host"},
        ]

        result = nats.get_model_classification_options(user_info=USER_INFO)

        assert result == {
            "items": [
                {"classification_id": "host", "classification_name": "主机"},
                {"classification_id": "middleware", "classification_name": "中间件"},
            ]
        }
        classifications_mock.assert_called_once_with(language="zh")
        models_mock.assert_called_once_with(language="zh", permissions_map=MODEL_PERMISSIONS)

    @patch.object(nats, "_build_nats_model_permission_map", return_value=None)
    def test_returns_empty_items_without_model_permission(self, permission_mock):
        assert nats.get_model_classification_options(user_info=USER_INFO) == {"items": []}


@pytest.mark.unit
class TestClassificationModelInstanceCounts:
    @patch.object(nats.InstanceManage, "model_inst_count")
    @patch.object(nats.ModelManage, "search_model")
    @patch.object(nats.ClassificationManage, "search_model_classification")
    @patch.object(nats, "_build_nats_permission_map", return_value=INSTANCE_PERMISSIONS)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_filters_zero_and_sorts_count_desc_then_name(
        self,
        model_permission_mock,
        instance_permission_mock,
        classifications_mock,
        models_mock,
        count_mock,
    ):
        classifications_mock.return_value = [
            {"classification_id": "middleware", "classification_name": "中间件"}
        ]
        models_mock.return_value = [
            {"model_id": "apache", "model_name": "Apache", "classification_id": "middleware"},
            {"model_id": "tomcat", "model_name": "Tomcat", "classification_id": "middleware"},
            {"model_id": "nginx", "model_name": "Nginx", "classification_id": "middleware"},
            {"model_id": "zero", "model_name": "Zero", "classification_id": "middleware"},
        ]
        count_mock.return_value = {"apache": 100, "tomcat": 10, "nginx": 10, "zero": 0}

        result = nats.get_classification_model_instance_counts(
            classification_id="middleware", user_info=USER_INFO
        )

        assert result == {
            "items": [
                {"label": "Apache", "value": 100},
                {"label": "Nginx", "value": 10},
                {"label": "Tomcat", "value": 10},
            ]
        }
        models_mock.assert_called_once_with(
            language="zh",
            permissions_map=MODEL_PERMISSIONS,
            classification_ids=["middleware"],
        )
        count_mock.assert_called_once_with(permissions_map=INSTANCE_PERMISSIONS)

    @pytest.mark.parametrize("classification_id", [None, "", "   "])
    def test_returns_empty_items_for_blank_classification(self, classification_id):
        assert nats.get_classification_model_instance_counts(
            classification_id=classification_id, user_info=USER_INFO
        ) == {"items": []}

    @patch.object(nats.ModelManage, "search_model")
    @patch.object(
        nats.ClassificationManage,
        "search_model_classification",
        return_value=[{"classification_id": "host", "classification_name": "主机"}],
    )
    def test_returns_empty_items_for_unknown_or_hidden_classification(
        self, classifications_mock, models_mock
    ):
        assert nats.get_classification_model_instance_counts(
            classification_id="middleware", user_info=USER_INFO
        ) == {"items": []}
        models_mock.assert_not_called()

    @patch.object(
        nats.ClassificationManage,
        "search_model_classification",
        return_value=[{"classification_id": "middleware", "classification_name": "中间件"}],
    )
    @patch.object(nats, "_build_nats_permission_map", return_value=INSTANCE_PERMISSIONS)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=None)
    def test_returns_empty_items_without_model_permission(
        self, model_permission_mock, instance_permission_mock, classifications_mock
    ):
        assert nats.get_classification_model_instance_counts(
            classification_id="middleware", user_info=USER_INFO
        ) == {"items": []}

    @patch.object(
        nats.ClassificationManage,
        "search_model_classification",
        return_value=[{"classification_id": "middleware", "classification_name": "中间件"}],
    )
    @patch.object(nats, "_build_nats_permission_map", return_value=None)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_returns_empty_items_without_instance_permission(
        self, model_permission_mock, instance_permission_mock, classifications_mock
    ):
        assert nats.get_classification_model_instance_counts(
            classification_id="middleware", user_info=USER_INFO
        ) == {"items": []}


@pytest.mark.unit
def test_nats_cmdb_language_normalization():
    assert nats._resolve_nats_cmdb_language({"language": "en-US"}) == "en"
    assert nats._resolve_nats_cmdb_language({"locale": "zh-CN"}) == "zh"
```

- [ ] **Step 2: Run the handler tests and verify RED**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_nats_model_count_datasources.py -q
```

Expected: FAIL with missing `get_model_classification_options` and `get_classification_model_instance_counts` attributes.

- [ ] **Step 3: Implement language normalization and both handlers**

Add a small private helper near the existing NATS permission helpers:

```python
def _resolve_nats_cmdb_language(user_info=None):
    user_info = user_info or {}
    user = user_info.get("user")
    raw_language = (
        user_info.get("locale")
        or user_info.get("language")
        or getattr(user, "locale", None)
        or user_info.get("LANGUAGE_CODE")
        or "zh-CN"
    )
    return "en" if str(raw_language).lower().startswith("en") else "zh"
```

Add two `@nats_client.register` functions near the existing CMDB statistics handlers:

```python
@nats_client.register
def get_model_classification_options(user_info=None, **kwargs):
    language = _resolve_nats_cmdb_language(user_info)
    model_permissions = _build_nats_model_permission_map(user_info)
    if model_permissions is None:
        return {"items": []}

    models = ModelManage.search_model(
        language=language,
        permissions_map=model_permissions,
    )
    allowed_classification_ids = {
        model.get("classification_id")
        for model in models
        if model.get("classification_id")
    }
    classifications = ClassificationManage.search_model_classification(language=language)
    return {
        "items": [
            {
                "classification_id": item["classification_id"],
                "classification_name": item["classification_name"],
            }
            for item in classifications
            if item.get("classification_id") in allowed_classification_ids
        ]
    }


@nats_client.register
def get_classification_model_instance_counts(
    classification_id=None,
    user_info=None,
    **kwargs,
):
    classification_id = str(classification_id or "").strip()
    if not classification_id:
        return {"items": []}

    language = _resolve_nats_cmdb_language(user_info)
    visible_classification_ids = {
        item.get("classification_id")
        for item in ClassificationManage.search_model_classification(language=language)
    }
    if classification_id not in visible_classification_ids:
        return {"items": []}

    model_permissions = _build_nats_model_permission_map(user_info)
    instance_permissions = _build_nats_permission_map(user_info)
    if model_permissions is None or instance_permissions is None:
        return {"items": []}

    models = ModelManage.search_model(
        language=language,
        permissions_map=model_permissions,
        classification_ids=[classification_id],
    )
    counts = InstanceManage.model_inst_count(permissions_map=instance_permissions)
    items = [
        {"label": model.get("model_name", ""), "value": counts.get(model.get("model_id"), 0)}
        for model in models
    ]
    items = [item for item in items if item["value"] > 0]
    items.sort(key=lambda item: (-item["value"], item["label"]))
    return {"items": items}
```

Do not catch service exceptions; let the existing NATS error path surface them.

- [ ] **Step 4: Run backend verification**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_nats_model_count_datasources.py -q
```

Expected: all new tests PASS.

Run regression coverage for the unchanged neighboring handlers:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_rack_room_service.py -q
```

Expected: PASS; `get_room_list` permission behavior remains unchanged.

- [ ] **Step 5: Commit the handlers**

```powershell
git add -- server/apps/cmdb/nats/nats.py server/apps/cmdb/tests/test_nats_model_count_datasources.py
git commit -m "feat: add CMDB model count datasource handlers"
```

### Task 3: Register the two built-in datasource definitions

**Files:**
- Modify: `server/apps/operation_analysis/support-files/source_api.json`
- Create: `server/apps/operation_analysis/tests/test_cmdb_model_count_datasource_definitions.py`

**Interfaces:**
- Consumes: NATS routes `cmdb/get_model_classification_options` and `cmdb/get_classification_model_instance_counts` from Task 2.
- Produces: one non-chart dynamic option datasource and one `multiValue` datasource whose `classification_id` parameter resolves options by stable `rest_api` reference.

- [ ] **Step 1: Write the failing datasource-definition test**

Create the test file:

```python
import json
from pathlib import Path


SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"


def _sources_by_api():
    entries = json.loads(SOURCE_API.read_text(encoding="utf-8"))
    return {item["rest_api"]: item for item in entries}


def test_cmdb_model_classification_options_datasource_contract():
    source = _sources_by_api()["cmdb/get_model_classification_options"]
    assert source["chart_type"] == []
    assert source["params"] == []
    assert {field["key"] for field in source["field_schema"]} == {
        "classification_id",
        "classification_name",
    }


def test_cmdb_classification_model_instance_count_datasource_contract():
    source = _sources_by_api()["cmdb/get_classification_model_instance_counts"]
    assert source["chart_type"] == ["multiValue"]
    param = next(item for item in source["params"] if item["name"] == "classification_id")
    assert param["required"] is True
    dynamic = param["inputConfig"]["optionsSource"]
    assert dynamic == {
        "type": "dynamic",
        "sourceRef": {
            "type": "rest_api",
            "value": "cmdb/get_model_classification_options",
        },
        "valueField": "classification_id",
        "labelField": "classification_name",
    }
    assert {field["key"] for field in source["field_schema"]} == {"label", "value"}


```

The existing `get_model_inst_statistics` datasource is embedded in
`support-files/builtin_canvases.yaml`, not `source_api.json`; leave that file
untouched and verify its unchanged state through the scoped diff in Task 4.

- [ ] **Step 2: Run the definition test and verify RED**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/operation_analysis/tests/test_cmdb_model_count_datasource_definitions.py -q
```

Expected: FAIL with `KeyError: 'cmdb/get_model_classification_options'`.

- [ ] **Step 3: Add the exact JSON datasource entries**

Append these objects before the closing array bracket in `source_api.json`, preserving valid JSON commas:

```json
{
  "name": "CMDB模型分类列表",
  "desc": "返回当前用户有权查看且包含可见模型的CMDB模型分类，供运营分析参数动态选项使用",
  "rest_api": "cmdb/get_model_classification_options",
  "tag": ["cmdb"],
  "chart_type": [],
  "params": [],
  "field_schema": [
    {"key": "classification_id", "title": "模型分类ID", "value_type": "string", "description": "CMDB模型分类唯一标识"},
    {"key": "classification_name", "title": "模型分类名称", "value_type": "string", "description": "当前语言下的模型分类名称"}
  ]
},
{
  "name": "分类模型实例数量",
  "desc": "按CMDB模型分类统计各可见模型的实例数量，过滤零值并按数量降序返回",
  "rest_api": "cmdb/get_classification_model_instance_counts",
  "tag": ["cmdb"],
  "chart_type": ["multiValue"],
  "params": [
    {
      "name": "classification_id",
      "type": "string",
      "value": "",
      "alias_name": "模型分类",
      "filterType": "params",
      "required": true,
      "inputConfig": {
        "control": "select",
        "optionsSource": {
          "type": "dynamic",
          "sourceRef": {
            "type": "rest_api",
            "value": "cmdb/get_model_classification_options"
          },
          "valueField": "classification_id",
          "labelField": "classification_name"
        }
      }
    }
  ],
  "field_schema": [
    {"key": "label", "title": "模型名称", "value_type": "string", "description": "当前语言下的模型名称"},
    {"key": "value", "title": "实例数量", "value_type": "number", "description": "当前权限范围内的模型实例数量"}
  ]
}
```

- [ ] **Step 4: Run definition and initialization regressions**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/operation_analysis/tests/test_cmdb_model_count_datasource_definitions.py apps/operation_analysis/tests/test_host_resource_top_datasource_definition.py -q
```

Expected: PASS.

Run the focused initialization contract:

```powershell
uv run pytest -o addopts= apps/operation_analysis/tests/test_management_commands.py::test_init_source_api_data_creates_tags_and_sources -q
```

Expected: PASS and both new JSON entries remain compatible with `init_source_api_data`.

- [ ] **Step 5: Commit the datasource definitions**

```powershell
git add -- server/apps/operation_analysis/support-files/source_api.json server/apps/operation_analysis/tests/test_cmdb_model_count_datasource_definitions.py
git commit -m "feat: register CMDB model count datasources"
```

### Task 4: Run the integrated acceptance gate

**Files:**
- Verify only; no production files are added in this task.

**Interfaces:**
- Consumes: the shared multiValue validator, both NATS handlers, and both datasource JSON entries delivered by Tasks 1–3.
- Produces: evidence that the full feature contract passes without changing the existing model statistics datasource.

- [ ] **Step 1: Run all focused backend tests together**

Run from `server/`:

```powershell
uv run pytest -o addopts= apps/cmdb/tests/test_nats_model_count_datasources.py apps/operation_analysis/tests/test_cmdb_model_count_datasource_definitions.py apps/operation_analysis/tests/test_host_resource_top_datasource_definition.py -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run the frontend contract and lint**

Run from `web/`:

```powershell
.\node_modules\.bin\tsx.CMD scripts\ops-analysis-multi-value-test.ts
.\node_modules\.bin\eslint.CMD src/app/ops-analysis/utils/multiValueData.ts scripts/ops-analysis-multi-value-test.ts
```

Expected: the contract prints success and ESLint exits 0.

- [ ] **Step 3: Validate file integrity and scope**

Run from repository root:

```powershell
git diff --check HEAD~3..HEAD
git status --short
```

Expected: no whitespace errors. Status may still show the user's pre-existing unrelated changes, but no uncommitted files from Tasks 1–3.

- [ ] **Step 4: Record the verified feature in project memory**

After all checks pass, run:

```powershell
pjm note "新增CMDB模型分类选项和分类模型实例数量两个NATS数据源；权限、可见性、本地化、零值过滤与降序排序均通过聚焦测试；multiValue兼容数组、items和data.items三种响应。" --at "server/apps/cmdb/nats/nats.py"
```

Expected: projectmem confirms the note was recorded. Do not create an empty verification-only commit.

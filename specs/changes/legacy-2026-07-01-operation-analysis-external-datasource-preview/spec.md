# Historical Superpowers change: 2026-07-01-operation-analysis-external-datasource-preview

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-01-operation-analysis-external-datasource-preview.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first-stage external datasource preview path for operation analysis: choose a source type, test/preview data, return `items/count/fields`, and render a raw table preview.

**Architecture:** Keep `DataSourceAPIModel` as the datasource owner and add generic connector fields beside the existing NATS fields. Route runtime preview calls through a small connector registry with focused executors for REST API and MySQL/PostgreSQL, while NATS continues using the existing path. The preview response is intentionally table-first: `items` drives display, `count` supports pagination, and `fields` is a lightweight `field_schema` draft.

**Tech Stack:** Django 4.2, DRF viewsets, Python 3.12, SQLAlchemy, httpx/requests-compatible HTTP, Next.js 16, React 19, TypeScript, Ant Design, existing BK-Lite request and table components.

---

## File Structure

Backend files:

- Modify: `server/apps/operation_analysis/models/datasource_models.py`
  Add `source_type`, `connection_config`, and `query_config` to `DataSourceAPIModel`; keep NATS fields.
- Create: `server/apps/operation_analysis/migrations/0015_datasource_connector_fields.py`
  Add model fields with backwards-compatible defaults.
- Modify: `server/apps/operation_analysis/serializers/datasource_serializers.py`
  Validate source type, config shapes, `field_schema`, and redact sensitive config in responses.
- Create: `server/apps/operation_analysis/services/datasource_preview/__init__.py`
  Export preview service interfaces.
- Create: `server/apps/operation_analysis/services/datasource_preview/schema.py`
  Infer first-stage fields from the first non-empty row and scan sample values for simple types.
- Create: `server/apps/operation_analysis/services/datasource_preview/base.py`
  Define `PreviewResult`, `ConnectorError`, and executor interface.
- Create: `server/apps/operation_analysis/services/datasource_preview/registry.py`
  Map `source_type` to executor classes.
- Create: `server/apps/operation_analysis/services/datasource_preview/rest_api.py`
  Implement REST API preview with timeout, response path, response size limit, and sensitive header handling.
- Create: `server/apps/operation_analysis/services/datasource_preview/database.py`
  Implement MySQL/PostgreSQL preview with SQLAlchemy, read-only SELECT guard, `limit`, and timeout.
- Modify: `server/apps/operation_analysis/views/datasource_view.py`
  Add `preview` collection action and `preview_saved` detail action; preserve existing `get_source_data`.
- Create: `server/apps/operation_analysis/tests/test_datasource_preview_schema.py`
  Unit tests for field inference.
- Create: `server/apps/operation_analysis/tests/test_datasource_preview_view.py`
  API tests for preview actions, permissions, errors, and saved datasource preview.
- Create: `server/apps/operation_analysis/tests/test_datasource_preview_rest_api.py`
  Unit tests for REST response normalization and response path.
- Create: `server/apps/operation_analysis/tests/test_datasource_preview_database.py`
  Unit tests for SQL guard and result normalization.

Frontend files:

- Modify: `web/src/app/ops-analysis/types/dataSource.ts`
  Add source type, connector configs, preview request/response types.
- Modify: `web/src/app/ops-analysis/api/dataSource.ts`
  Add save-before-preview and saved-preview API methods.
- Create: `web/src/app/ops-analysis/components/dataSourcePreviewTable.tsx`
  Reusable raw preview table using `fields` first and `items[0]` fallback.
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx`
  Add source type selection, dynamic config fields, preview action, and `field_schema` seeding from returned `fields`.
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx`
  Add source type column and keep existing NATS rows readable.
- Modify: `web/src/app/ops-analysis/locales/zh.json`
  Add labels and errors for external datasource preview.
- Modify: `web/src/app/ops-analysis/locales/en.json`
  Add matching English strings.

Docs:

- Keep: `docs/superpowers/specs/2026-07-01-operation-analysis-external-datasource-preview-design.md`
  Include this design doc in the same implementation commit as code.

---

### Task 1: Backend Model And Serializer Shape

**Files:**
- Modify: `server/apps/operation_analysis/models/datasource_models.py`
- Create: `server/apps/operation_analysis/migrations/0015_datasource_connector_fields.py`
- Modify: `server/apps/operation_analysis/serializers/datasource_serializers.py`
- Test: `server/apps/operation_analysis/tests/test_datasource_filters_serializers.py`

- [ ] **Step 1: Write the failing serializer tests**

Append these tests to `server/apps/operation_analysis/tests/test_datasource_filters_serializers.py`:

```python
import pytest
from rest_framework.exceptions import ValidationError

from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer


def test_datasource_serializer_accepts_rest_api_connector_config():
    serializer = DataSourceAPIModelSerializer(
        data={
            "name": "外部订单 API",
            "rest_api": "",
            "source_type": "rest_api",
            "connection_config": {
                "url": "https://example.com/orders",
                "method": "GET",
                "headers": {"Authorization": "Bearer token"},
                "timeout": 10,
            },
            "query_config": {"response_path": "data.items", "limit": 100},
            "params": [],
            "chart_type": ["table"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
        }
    )

    assert serializer.is_valid(), serializer.errors


def test_datasource_serializer_rejects_unknown_source_type():
    serializer = DataSourceAPIModelSerializer(
        data={
            "name": "bad",
            "rest_api": "",
            "source_type": "ftp",
            "connection_config": {},
            "query_config": {},
            "params": [],
            "chart_type": ["table"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
        }
    )

    assert not serializer.is_valid()
    assert "source_type" in serializer.errors
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_filters_serializers.py -q
```

Expected: the new tests fail because `source_type`, `connection_config`, and `query_config` are not model fields.

- [ ] **Step 3: Add model fields**

In `server/apps/operation_analysis/models/datasource_models.py`, add these fields to `DataSourceAPIModel` after `desc`:

```python
    SOURCE_TYPE_NATS = "nats"
    SOURCE_TYPE_MYSQL = "mysql"
    SOURCE_TYPE_POSTGRESQL = "postgresql"
    SOURCE_TYPE_REST_API = "rest_api"
    SOURCE_TYPE_EXCEL = "excel"

    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_NATS, "NATS"),
        (SOURCE_TYPE_MYSQL, "MySQL"),
        (SOURCE_TYPE_POSTGRESQL, "PostgreSQL"),
        (SOURCE_TYPE_REST_API, "REST API"),
        (SOURCE_TYPE_EXCEL, "Excel"),
    ]

    source_type = models.CharField(
        max_length=32,
        choices=SOURCE_TYPE_CHOICES,
        default=SOURCE_TYPE_NATS,
        verbose_name="数据来源类型",
    )
    connection_config = JSONField(default=dict, blank=True, verbose_name="连接配置")
    query_config = JSONField(default=dict, blank=True, verbose_name="取数配置")
```

- [ ] **Step 4: Add migration**

Create `server/apps/operation_analysis/migrations/0015_datasource_connector_fields.py`:

```python
# Generated for external datasource preview connector fields.

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import JSONField


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0014_screen_report"),
    ]

    operations = [
        migrations.AddField(
            model_name="datasourceapimodel",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("nats", "NATS"),
                    ("mysql", "MySQL"),
                    ("postgresql", "PostgreSQL"),
                    ("rest_api", "REST API"),
                    ("excel", "Excel"),
                ],
                default="nats",
                max_length=32,
                verbose_name="数据来源类型",
            ),
        ),
        migrations.AddField(
            model_name="datasourceapimodel",
            name="connection_config",
            field=JSONField(blank=True, default=dict, verbose_name="连接配置"),
        ),
        migrations.AddField(
            model_name="datasourceapimodel",
            name="query_config",
            field=JSONField(blank=True, default=dict, verbose_name="取数配置"),
        ),
    ]
```

If the dependency name differs in the local migration graph, replace `"0014_screen_report"` with the newest migration shown by:

```bash
cd server && uv run python manage.py showmigrations operation_analysis
```

- [ ] **Step 5: Add serializer validation and redaction**

In `server/apps/operation_analysis/serializers/datasource_serializers.py`, add helpers near imports:

```python
SENSITIVE_CONFIG_KEYS = {"password", "token", "authorization", "api_key", "secret", "headers"}


def redact_sensitive_config(value):
    if not isinstance(value, dict):
        return value

    redacted = {}
    for key, item in value.items():
        normalized = str(key).lower()
        if normalized in SENSITIVE_CONFIG_KEYS or any(part in normalized for part in ("password", "token", "secret")):
            redacted[key] = "******" if item not in (None, "") else item
        elif isinstance(item, dict):
            redacted[key] = redact_sensitive_config(item)
        else:
            redacted[key] = item
    return redacted
```

Inside `DataSourceAPIModelSerializer`, add:

```python
    def validate_source_type(self, value):
        allowed = {choice[0] for choice in DataSourceAPIModel.SOURCE_TYPE_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("source_type 不支持")
        return value

    def validate_connection_config(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("connection_config 必须为对象")
        return value

    def validate_query_config(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("query_config 必须为对象")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["connection_config"] = redact_sensitive_config(data.get("connection_config"))
        return data
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_filters_serializers.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit only this task if working in small commits**

```bash
git add server/apps/operation_analysis/models/datasource_models.py \
  server/apps/operation_analysis/migrations/0015_datasource_connector_fields.py \
  server/apps/operation_analysis/serializers/datasource_serializers.py \
  server/apps/operation_analysis/tests/test_datasource_filters_serializers.py
git commit -m "feat: add operation analysis datasource connector fields"
```

---

### Task 2: Preview Contract And Field Inference

**Files:**
- Create: `server/apps/operation_analysis/services/datasource_preview/__init__.py`
- Create: `server/apps/operation_analysis/services/datasource_preview/base.py`
- Create: `server/apps/operation_analysis/services/datasource_preview/schema.py`
- Test: `server/apps/operation_analysis/tests/test_datasource_preview_schema.py`

- [ ] **Step 1: Write field inference tests**

Create `server/apps/operation_analysis/tests/test_datasource_preview_schema.py`:

```python
from apps.operation_analysis.services.datasource_preview.schema import infer_fields


def test_infer_fields_uses_first_non_empty_object_keys():
    rows = [
        {},
        {"date": "2026-06-01", "users": 120, "enabled": True},
        {"date": "2026-06-02", "users": "180", "enabled": False, "late_field": "ignored"},
    ]

    assert infer_fields(rows) == [
        {"key": "date", "title": "date", "value_type": "datetime"},
        {"key": "users", "title": "users", "value_type": "number"},
        {"key": "enabled", "title": "enabled", "value_type": "boolean"},
    ]


def test_infer_fields_downgrades_type_conflict_to_string():
    rows = [
        {"value": 1},
        {"value": "not-number"},
    ]

    assert infer_fields(rows) == [
        {"key": "value", "title": "value", "value_type": "string"},
    ]


def test_infer_fields_returns_empty_for_empty_rows():
    assert infer_fields([]) == []
    assert infer_fields([{}, None, "x"]) == []
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_preview_schema.py -q
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Create preview base contract**

Create `server/apps/operation_analysis/services/datasource_preview/base.py`:

```python
from dataclasses import dataclass
from typing import Any


class ConnectorError(Exception):
    def __init__(self, message: str, code: str = "preview_failed", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


@dataclass
class PreviewResult:
    items: list[dict[str, Any]]
    count: int
    fields: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "count": self.count,
            "fields": self.fields,
        }


class BaseConnectorExecutor:
    source_type = ""

    def test_connection(self, connection_config: dict[str, Any]) -> None:
        return None

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
    ) -> PreviewResult:
        raise NotImplementedError
```

- [ ] **Step 4: Create field inference implementation**

Create `server/apps/operation_analysis/services/datasource_preview/schema.py`:

```python
from datetime import datetime
from typing import Any


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def _is_boolean_values(values: list[Any]) -> bool:
    return bool(values) and all(isinstance(value, bool) for value in values)


def _is_number_values(values: list[Any]) -> bool:
    if not values:
        return False
    for value in values:
        if isinstance(value, bool):
            return False
        try:
            float(value)
        except (TypeError, ValueError):
            return False
    return True


def _is_datetime_values(values: list[Any]) -> bool:
    if not values:
        return False
    for value in values:
        if isinstance(value, datetime):
            continue
        if not isinstance(value, str):
            return False
        text = value.strip()
        if not text:
            return False
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            datetime.fromisoformat(normalized)
        except ValueError:
            return False
    return True


def _infer_value_type(values: list[Any]) -> str:
    non_empty = [value for value in values if not _is_empty(value)]
    if _is_boolean_values(non_empty):
        return "boolean"
    if _is_number_values(non_empty):
        return "number"
    if _is_datetime_values(non_empty):
        return "datetime"
    return "string"


def infer_fields(rows: list[Any], sample_size: int = 100) -> list[dict[str, str]]:
    first_record = next((row for row in rows if isinstance(row, dict) and row), None)
    if not first_record:
        return []

    keys = list(first_record.keys())
    sample_rows = [row for row in rows[:sample_size] if isinstance(row, dict)]

    return [
        {
            "key": key,
            "title": key,
            "value_type": _infer_value_type([row.get(key) for row in sample_rows]),
        }
        for key in keys
    ]
```

- [ ] **Step 5: Create package export**

Create `server/apps/operation_analysis/services/datasource_preview/__init__.py`:

```python
from apps.operation_analysis.services.datasource_preview.base import BaseConnectorExecutor, ConnectorError, PreviewResult
from apps.operation_analysis.services.datasource_preview.schema import infer_fields

__all__ = [
    "BaseConnectorExecutor",
    "ConnectorError",
    "PreviewResult",
    "infer_fields",
]
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_preview_schema.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit only this task if working in small commits**

```bash
git add server/apps/operation_analysis/services/datasource_preview \
  server/apps/operation_analysis/tests/test_datasource_preview_schema.py
git commit -m "feat: add datasource preview field inference"
```

---

### Task 3: REST API Preview Executor

**Files:**
- Create: `server/apps/operation_analysis/services/datasource_preview/rest_api.py`
- Test: `server/apps/operation_analysis/tests/test_datasource_preview_rest_api.py`

- [ ] **Step 1: Write REST executor tests**

Create `server/apps/operation_analysis/tests/test_datasource_preview_rest_api.py`:

```python
from types import SimpleNamespace

import pytest

from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.rest_api import RestApiConnectorExecutor, extract_response_path, normalize_rest_items


def test_extract_response_path_reads_nested_list():
    payload = {"data": {"items": [{"name": "a"}]}}
    assert extract_response_path(payload, "data.items") == [{"name": "a"}]


def test_normalize_rest_items_accepts_list_and_items_dict():
    assert normalize_rest_items([{"a": 1}]) == ([{"a": 1}], 1)
    assert normalize_rest_items({"items": [{"a": 1}], "count": 5}) == ([{"a": 1}], 5)


def test_normalize_rest_items_rejects_scalar():
    with pytest.raises(ConnectorError) as exc:
        normalize_rest_items({"ok": True})

    assert exc.value.code == "rest_response_not_list"


def test_rest_preview_uses_http_client_and_infers_fields():
    calls = []

    class FakeResponse:
        headers = {"content-length": "64"}

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"items": [{"date": "2026-06-01", "users": 120}], "count": 1}}

    class FakeClient:
        def request(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    executor = RestApiConnectorExecutor(http_client=FakeClient())
    result = executor.preview(
        {
            "url": "https://example.com/orders",
            "method": "GET",
            "headers": {"Authorization": "Bearer x"},
            "timeout": 3,
        },
        {"response_path": "data", "limit": 100},
        limit=100,
    )

    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == "https://example.com/orders"
    assert result.as_dict() == {
        "items": [{"date": "2026-06-01", "users": 120}],
        "count": 1,
        "fields": [
            {"key": "date", "title": "date", "value_type": "datetime"},
            {"key": "users", "title": "users", "value_type": "number"},
        ],
    }
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_preview_rest_api.py -q
```

Expected: FAIL because `rest_api.py` does not exist.

- [ ] **Step 3: Implement REST executor**

Create `server/apps/operation_analysis/services/datasource_preview/rest_api.py`:

```python
from typing import Any

import requests

from apps.operation_analysis.services.datasource_preview.base import BaseConnectorExecutor, ConnectorError, PreviewResult
from apps.operation_analysis.services.datasource_preview.schema import infer_fields

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def extract_response_path(payload: Any, response_path: str | None) -> Any:
    if not response_path:
        return payload

    current = payload
    for part in response_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        raise ConnectorError(f"响应路径不存在: {response_path}", code="rest_response_path_missing", status_code=400)
    return current


def normalize_rest_items(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if isinstance(payload, list):
        items = payload
        count = len(items)
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items = payload["items"]
        count = int(payload.get("count") or len(items))
    else:
        raise ConnectorError("REST API 响应必须是对象数组或包含 items 数组的对象", code="rest_response_not_list", status_code=400)

    normalized = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({"value": item})
    return normalized, count


class RestApiConnectorExecutor(BaseConnectorExecutor):
    source_type = "rest_api"

    def __init__(self, http_client=None):
        self.http_client = http_client or requests

    def test_connection(self, connection_config: dict[str, Any]) -> None:
        self.preview(connection_config, {"limit": 1}, limit=1)

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
    ) -> PreviewResult:
        url = connection_config.get("url")
        if not url:
            raise ConnectorError("REST API URL 不能为空", code="rest_url_required", status_code=400)

        method = str(connection_config.get("method") or "GET").upper()
        if method not in {"GET", "POST"}:
            raise ConnectorError("REST API 预览仅支持 GET/POST", code="rest_method_not_supported", status_code=400)

        timeout = min(int(connection_config.get("timeout") or 10), 30)
        headers = connection_config.get("headers") if isinstance(connection_config.get("headers"), dict) else {}
        params = query_config.get("params") if isinstance(query_config.get("params"), dict) else {}
        body = query_config.get("body") if isinstance(query_config.get("body"), dict) else None

        try:
            response = self.http_client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=body if method == "POST" else None,
                timeout=timeout,
            )
            content_length = int(response.headers.get("content-length") or 0)
            if content_length > MAX_RESPONSE_BYTES:
                raise ConnectorError("REST API 响应体过大", code="rest_response_too_large", status_code=400)
            response.raise_for_status()
            payload = response.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError(f"REST API 请求失败: {exc}", code="rest_request_failed", status_code=502)

        selected = extract_response_path(payload, query_config.get("response_path"))
        items, count = normalize_rest_items(selected)
        limited_items = items[:limit]
        return PreviewResult(items=limited_items, count=count, fields=infer_fields(limited_items))
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_preview_rest_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit only this task if working in small commits**

```bash
git add server/apps/operation_analysis/services/datasource_preview/rest_api.py \
  server/apps/operation_analysis/tests/test_datasource_preview_rest_api.py
git commit -m "feat: add REST datasource preview executor"
```

---

### Task 4: Database Preview Executor

**Files:**
- Create: `server/apps/operation_analysis/services/datasource_preview/database.py`
- Test: `server/apps/operation_analysis/tests/test_datasource_preview_database.py`

- [ ] **Step 1: Write database executor tests**

Create `server/apps/operation_analysis/tests/test_datasource_preview_database.py`:

```python
import pytest

from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.database import build_preview_sql, ensure_select_sql, normalize_db_rows


def test_ensure_select_sql_accepts_single_select():
    assert ensure_select_sql(" select id, name from users ") == "select id, name from users"


@pytest.mark.parametrize("sql", ["delete from users", "select 1; select 2", "update users set name='x'"])
def test_ensure_select_sql_rejects_dangerous_sql(sql):
    with pytest.raises(ConnectorError):
        ensure_select_sql(sql)


def test_build_preview_sql_from_table_name_quotes_identifier():
    assert build_preview_sql({"table": "orders"}, 100) == "SELECT * FROM `orders` LIMIT 100"


def test_build_preview_sql_adds_limit_to_select():
    assert build_preview_sql({"sql": "select id from orders"}, 20) == "select id from orders LIMIT 20"


def test_normalize_db_rows_converts_row_mappings():
    rows = [{"id": 1, "name": "a"}]
    assert normalize_db_rows(rows) == [{"id": 1, "name": "a"}]
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_preview_database.py -q
```

Expected: FAIL because `database.py` does not exist.

- [ ] **Step 3: Implement database executor**

Create `server/apps/operation_analysis/services/datasource_preview/database.py`:

```python
import re
from typing import Any

from sqlalchemy import create_engine, text

from apps.operation_analysis.services.datasource_preview.base import BaseConnectorExecutor, ConnectorError, PreviewResult
from apps.operation_analysis.services.datasource_preview.schema import infer_fields

SELECT_RE = re.compile(r"^\s*select\b", re.IGNORECASE)
LIMIT_RE = re.compile(r"\blimit\s+\d+\s*$", re.IGNORECASE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ensure_select_sql(sql: str) -> str:
    cleaned = (sql or "").strip()
    if not cleaned:
        raise ConnectorError("SQL 不能为空", code="db_sql_required", status_code=400)
    if ";" in cleaned:
        raise ConnectorError("SQL 预览不支持多语句", code="db_sql_multi_statement", status_code=400)
    if not SELECT_RE.match(cleaned):
        raise ConnectorError("SQL 预览仅支持 SELECT", code="db_sql_not_select", status_code=400)
    return cleaned


def quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.match(identifier or ""):
        raise ConnectorError("表名格式不合法", code="db_table_invalid", status_code=400)
    return f"`{identifier}`"


def build_preview_sql(query_config: dict[str, Any], limit: int) -> str:
    if query_config.get("sql"):
        sql = ensure_select_sql(str(query_config["sql"]))
        if LIMIT_RE.search(sql):
            return sql
        return f"{sql} LIMIT {limit}"

    table = query_config.get("table")
    if not table:
        raise ConnectorError("请选择表或填写 SELECT 查询", code="db_query_required", status_code=400)
    return f"SELECT * FROM {quote_identifier(str(table))} LIMIT {limit}"


def normalize_db_rows(rows: list[Any]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        if isinstance(row, dict):
            normalized.append(dict(row))
        elif hasattr(row, "_mapping"):
            normalized.append(dict(row._mapping))
        else:
            normalized.append(dict(row))
    return normalized


def build_database_url(source_type: str, connection_config: dict[str, Any]) -> str:
    username = connection_config.get("username")
    password = connection_config.get("password")
    host = connection_config.get("host")
    port = connection_config.get("port")
    database = connection_config.get("database")
    if not all([username, password, host, port, database]):
        raise ConnectorError("数据库连接信息不完整", code="db_config_incomplete", status_code=400)

    if source_type == "mysql":
        return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
    if source_type == "postgresql":
        return f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
    raise ConnectorError("数据库类型不支持", code="db_type_not_supported", status_code=400)


class DatabaseConnectorExecutor(BaseConnectorExecutor):
    def __init__(self, source_type: str, engine_factory=create_engine):
        self.source_type = source_type
        self.engine_factory = engine_factory

    def test_connection(self, connection_config: dict[str, Any]) -> None:
        database_url = build_database_url(self.source_type, connection_config)
        engine = self.engine_factory(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
    ) -> PreviewResult:
        safe_limit = min(max(int(limit or 100), 1), 1000)
        database_url = build_database_url(self.source_type, connection_config)
        sql = build_preview_sql(query_config, safe_limit)

        try:
            engine = self.engine_factory(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
            with engine.connect() as conn:
                rows = conn.execute(text(sql)).fetchmany(safe_limit)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError(f"数据库预览失败: {exc}", code="db_preview_failed", status_code=502)

        items = normalize_db_rows(rows)
        return PreviewResult(items=items, count=len(items), fields=infer_fields(items))
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_preview_database.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit only this task if working in small commits**

```bash
git add server/apps/operation_analysis/services/datasource_preview/database.py \
  server/apps/operation_analysis/tests/test_datasource_preview_database.py
git commit -m "feat: add database datasource preview executor"
```

---

### Task 5: Connector Registry And Preview API

**Files:**
- Create: `server/apps/operation_analysis/services/datasource_preview/registry.py`
- Modify: `server/apps/operation_analysis/views/datasource_view.py`
- Test: `server/apps/operation_analysis/tests/test_datasource_preview_view.py`

- [ ] **Step 1: Write preview API tests**

Create `server/apps/operation_analysis/tests/test_datasource_preview_view.py`:

```python
import json
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.views import datasource_view


def _request(user, data=None):
    factory = APIRequestFactory()
    request = factory.post("/operation_analysis/api/data_source/preview/", data=data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


@pytest.mark.django_db
def test_preview_unsaved_datasource_returns_connector_result(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True

    class FakeExecutor:
        def preview(self, connection_config, query_config, limit=100):
            return SimpleNamespace(
                as_dict=lambda: {
                    "items": [{"date": "2026-06-01", "users": 120}],
                    "count": 1,
                    "fields": [{"key": "date", "title": "date", "value_type": "datetime"}],
                }
            )

    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: FakeExecutor())
    request = _request(
        authenticated_user,
        data={
            "source_type": "rest_api",
            "connection_config": {"url": "https://example.com"},
            "query_config": {"response_path": "items"},
            "limit": 100,
        },
    )

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "preview"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["count"] == 1


@pytest.mark.django_db
def test_preview_rejects_unsupported_source_type(authenticated_user):
    authenticated_user.is_superuser = True
    request = _request(authenticated_user, data={"source_type": "ftp"})

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "preview"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert "source_type" in payload["message"]
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_preview_view.py -q
```

Expected: FAIL because `preview` action and registry do not exist.

- [ ] **Step 3: Implement registry**

Create `server/apps/operation_analysis/services/datasource_preview/registry.py`:

```python
from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.database import DatabaseConnectorExecutor
from apps.operation_analysis.services.datasource_preview.rest_api import RestApiConnectorExecutor


def get_preview_executor(source_type: str):
    if source_type == "rest_api":
        return RestApiConnectorExecutor()
    if source_type in {"mysql", "postgresql"}:
        return DatabaseConnectorExecutor(source_type=source_type)
    raise ConnectorError("source_type 不支持预览", code="source_type_not_supported", status_code=400)
```

- [ ] **Step 4: Add view imports**

In `server/apps/operation_analysis/views/datasource_view.py`, add:

```python
from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.registry import get_preview_executor
```

- [ ] **Step 5: Add preview actions**

Inside `DataSourceAPIModelViewSet`, before `retrieve`, add:

```python
    def _execute_preview(self, source_type, connection_config, query_config, limit):
        executor = get_preview_executor(source_type)
        return executor.preview(
            connection_config=connection_config or {},
            query_config=query_config or {},
            limit=limit,
        )

    @HasPermission("data_source-View")
    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request, *args, **kwargs):
        source_type = request.data.get("source_type")
        if source_type not in {"rest_api", "mysql", "postgresql"}:
            return _build_error_response("source_type 不支持预览", status.HTTP_400_BAD_REQUEST)

        try:
            limit = int(request.data.get("limit") or 100)
        except (TypeError, ValueError):
            return _build_error_response("limit 必须是整数", status.HTTP_400_BAD_REQUEST)

        try:
            result = self._execute_preview(
                source_type=source_type,
                connection_config=request.data.get("connection_config") or {},
                query_config=request.data.get("query_config") or {},
                limit=limit,
            )
        except ConnectorError as exc:
            return _build_error_response(exc.message, exc.status_code)

        return Response(result.as_dict())

    @HasPermission("data_source-View")
    @action(detail=True, methods=["post"], url_path="preview")
    def preview_saved(self, request, *args, **kwargs):
        instance = self.get_object()
        current_team = self._parse_current_team_cookie(request)
        if current_team not in (instance.groups or []):
            return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)

        try:
            limit = int(request.data.get("limit") or 100)
        except (TypeError, ValueError):
            return _build_error_response("limit 必须是整数", status.HTTP_400_BAD_REQUEST)

        try:
            result = self._execute_preview(
                source_type=instance.source_type,
                connection_config=instance.connection_config or {},
                query_config=instance.query_config or {},
                limit=limit,
            )
        except ConnectorError as exc:
            return _build_error_response(exc.message, exc.status_code)

        return Response(result.as_dict())
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_datasource_preview_view.py apps/operation_analysis/tests/test_datasource_view.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit only this task if working in small commits**

```bash
git add server/apps/operation_analysis/services/datasource_preview/registry.py \
  server/apps/operation_analysis/views/datasource_view.py \
  server/apps/operation_analysis/tests/test_datasource_preview_view.py
git commit -m "feat: add datasource preview API"
```

---

### Task 6: Frontend Types, API Methods, And Preview Table

**Files:**
- Modify: `web/src/app/ops-analysis/types/dataSource.ts`
- Modify: `web/src/app/ops-analysis/api/dataSource.ts`
- Create: `web/src/app/ops-analysis/components/dataSourcePreviewTable.tsx`

- [ ] **Step 1: Add TypeScript types**

In `web/src/app/ops-analysis/types/dataSource.ts`, add:

```ts
export type DataSourceType = 'nats' | 'mysql' | 'postgresql' | 'rest_api' | 'excel';

export interface DataSourcePreviewRequest {
  source_type: DataSourceType;
  connection_config?: Record<string, any>;
  query_config?: Record<string, any>;
  limit?: number;
}

export interface DataSourcePreviewResponse {
  items: Record<string, any>[];
  count: number;
  fields: ResponseFieldDefinition[];
}
```

Extend `DatasourceItem`:

```ts
  source_type?: DataSourceType;
  connection_config?: Record<string, any>;
  query_config?: Record<string, any>;
```

- [ ] **Step 2: Add API methods**

In `web/src/app/ops-analysis/api/dataSource.ts`, add:

```ts
  const previewDataSource = useCallback(async (data: any) => {
    return post('/operation_analysis/api/data_source/preview/', data);
  }, [post]);

  const previewSavedDataSource = useCallback(async (id: number, data?: any) => {
    return post(`/operation_analysis/api/data_source/${id}/preview/`, data || {});
  }, [post]);
```

Add them to the returned object:

```ts
    previewDataSource,
    previewSavedDataSource,
```

- [ ] **Step 3: Create preview table component**

Create `web/src/app/ops-analysis/components/dataSourcePreviewTable.tsx`:

```tsx
'use client';

import React, { useMemo } from 'react';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';

interface DataSourcePreviewTableProps {
  items?: Record<string, any>[];
  fields?: ResponseFieldDefinition[];
  loading?: boolean;
}

const toText = (value: unknown) => {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const DataSourcePreviewTable: React.FC<DataSourcePreviewTableProps> = ({
  items = [],
  fields = [],
  loading = false,
}) => {
  const columns = useMemo<ColumnsType<Record<string, any>>>(() => {
    const sourceFields =
      fields.length > 0
        ? fields
        : items[0]
          ? Object.keys(items[0]).map((key) => ({ key, title: key, value_type: 'string' as const }))
          : [];

    return sourceFields.map((field) => ({
      title: field.title || field.key,
      dataIndex: field.key,
      key: field.key,
      ellipsis: true,
      render: (value: unknown) => toText(value),
    }));
  }, [fields, items]);

  return (
    <CustomTable
      size="small"
      rowKey={(_, index) => String(index ?? 0)}
      columns={columns}
      dataSource={items}
      loading={loading}
      pagination={{ pageSize: 10, showSizeChanger: false }}
      scroll={{ x: 'max-content' }}
    />
  );
};

export default DataSourcePreviewTable;
```

- [ ] **Step 4: Run frontend type check**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS or only pre-existing unrelated errors. If unrelated errors appear, capture them in the final implementation notes.

- [ ] **Step 5: Commit only this task if working in small commits**

```bash
git add web/src/app/ops-analysis/types/dataSource.ts \
  web/src/app/ops-analysis/api/dataSource.ts \
  web/src/app/ops-analysis/components/dataSourcePreviewTable.tsx
git commit -m "feat: add datasource preview frontend contract"
```

---

### Task 7: Frontend Create/Edit Preview Flow

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`

- [ ] **Step 1: Add locale strings**

In `web/src/app/ops-analysis/locales/zh.json`, add these keys under `dataSource`:

```json
"sourceType": "数据来源类型",
"sourceTypes": {
  "nats": "NATS",
  "mysql": "MySQL",
  "postgresql": "PostgreSQL",
  "rest_api": "REST API",
  "excel": "Excel"
},
"connectionConfig": "连接配置",
"queryConfig": "取数配置",
"preview": "预览数据",
"previewSuccess": "预览成功",
"previewFailed": "预览失败",
"previewEmpty": "暂无预览数据",
"responsePath": "响应路径",
"dbHost": "主机",
"dbPort": "端口",
"dbName": "数据库",
"dbUsername": "用户名",
"dbPassword": "密码",
"dbTable": "表名",
"dbSql": "SELECT 查询",
"apiUrl": "API 地址",
"apiMethod": "请求方法"
```

In `web/src/app/ops-analysis/locales/en.json`, add matching keys:

```json
"sourceType": "Source Type",
"sourceTypes": {
  "nats": "NATS",
  "mysql": "MySQL",
  "postgresql": "PostgreSQL",
  "rest_api": "REST API",
  "excel": "Excel"
},
"connectionConfig": "Connection",
"queryConfig": "Query",
"preview": "Preview Data",
"previewSuccess": "Preview succeeded",
"previewFailed": "Preview failed",
"previewEmpty": "No preview data",
"responsePath": "Response Path",
"dbHost": "Host",
"dbPort": "Port",
"dbName": "Database",
"dbUsername": "Username",
"dbPassword": "Password",
"dbTable": "Table",
"dbSql": "SELECT Query",
"apiUrl": "API URL",
"apiMethod": "Method"
```

Use valid JSON commas based on the surrounding file.

- [ ] **Step 2: Wire preview state and API**

In `operateModal.tsx`, add imports:

```tsx
import DataSourcePreviewTable from '@/app/ops-analysis/components/dataSourcePreviewTable';
import type { DataSourcePreviewResponse, DataSourceType } from '@/app/ops-analysis/types/dataSource';
```

Change API destructuring:

```tsx
  const { createDataSource, updateDataSource, previewDataSource, previewSavedDataSource } = useDataSourceApi();
```

Add state near other state:

```tsx
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewData, setPreviewData] = React.useState<DataSourcePreviewResponse | null>(null);
```

Clear preview state in the modal open effect:

```tsx
    setPreviewData(null);
```

- [ ] **Step 3: Add source type options**

In `operateModal.tsx`, add:

```tsx
  const sourceTypeOptions = [
    { label: t('dataSource.sourceTypes.nats'), value: 'nats' },
    { label: t('dataSource.sourceTypes.rest_api'), value: 'rest_api' },
    { label: t('dataSource.sourceTypes.mysql'), value: 'mysql' },
    { label: t('dataSource.sourceTypes.postgresql'), value: 'postgresql' },
  ];
```

When creating a new datasource, set default source type:

```tsx
      form.setFieldValue('source_type', 'nats');
```

- [ ] **Step 4: Add preview handler**

In `operateModal.tsx`, add before `handleSubmit`:

```tsx
  const buildPreviewPayload = () => {
    const values = form.getFieldsValue();
    return {
      source_type: values.source_type,
      connection_config: values.connection_config || {},
      query_config: values.query_config || {},
      limit: 100,
    };
  };

  const handlePreview = async () => {
    try {
      setPreviewLoading(true);
      const values = form.getFieldsValue();
      const response = currentRow?.id
        ? await previewSavedDataSource(currentRow.id, { limit: 100 })
        : await previewDataSource(buildPreviewPayload());

      setPreviewData(response);
      if (Array.isArray(response?.fields) && response.fields.length > 0) {
        setSchemaFields(response.fields.map((field: ResponseFieldDefinition) => ({
          ...field,
          id: uuidv4(),
        })));
      }
      message.success(t('dataSource.previewSuccess'));
    } catch (error: any) {
      message.error(error?.message || t('dataSource.previewFailed'));
    } finally {
      setPreviewLoading(false);
    }
  };
```

- [ ] **Step 5: Add dynamic form section**

In the drawer form JSX, add source type before the existing REST API field:

```tsx
        <Form.Item
          name="source_type"
          label={t('dataSource.sourceType')}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Select options={sourceTypeOptions} />
        </Form.Item>
```

Add a `Form.Item shouldUpdate` block below it:

```tsx
        <Form.Item shouldUpdate noStyle>
          {({ getFieldValue }) => {
            const sourceType = getFieldValue('source_type') as DataSourceType;

            if (sourceType === 'rest_api') {
              return (
                <>
                  <Form.Item name={['connection_config', 'url']} label={t('dataSource.apiUrl')} rules={[{ required: true, message: t('common.inputMsg') }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name={['connection_config', 'method']} label={t('dataSource.apiMethod')} initialValue="GET">
                    <Select options={[{ label: 'GET', value: 'GET' }, { label: 'POST', value: 'POST' }]} />
                  </Form.Item>
                  <Form.Item name={['query_config', 'response_path']} label={t('dataSource.responsePath')}>
                    <Input placeholder="data.items" />
                  </Form.Item>
                </>
              );
            }

            if (sourceType === 'mysql' || sourceType === 'postgresql') {
              return (
                <>
                  <Form.Item name={['connection_config', 'host']} label={t('dataSource.dbHost')} rules={[{ required: true, message: t('common.inputMsg') }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name={['connection_config', 'port']} label={t('dataSource.dbPort')} rules={[{ required: true, message: t('common.inputMsg') }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name={['connection_config', 'database']} label={t('dataSource.dbName')} rules={[{ required: true, message: t('common.inputMsg') }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name={['connection_config', 'username']} label={t('dataSource.dbUsername')} rules={[{ required: true, message: t('common.inputMsg') }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name={['connection_config', 'password']} label={t('dataSource.dbPassword')} rules={[{ required: true, message: t('common.inputMsg') }]}>
                    <Input.Password />
                  </Form.Item>
                  <Form.Item name={['query_config', 'table']} label={t('dataSource.dbTable')}>
                    <Input />
                  </Form.Item>
                  <Form.Item name={['query_config', 'sql']} label={t('dataSource.dbSql')}>
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </>
              );
            }

            return null;
          }}
        </Form.Item>
```

- [ ] **Step 6: Add preview UI**

In the drawer form JSX below field schema config, add:

```tsx
        <div className="mb-4">
          <Button loading={previewLoading} onClick={handlePreview}>
            {t('dataSource.preview')}
          </Button>
        </div>

        {previewData && (
          <DataSourcePreviewTable
            items={previewData.items}
            fields={previewData.fields}
            loading={previewLoading}
          />
        )}
```

- [ ] **Step 7: Include connector fields in submit payload**

In the existing submit handler, ensure payload includes:

```tsx
      source_type: values.source_type || 'nats',
      connection_config: values.connection_config || {},
      query_config: values.query_config || {},
```

When building `field_schema`, keep the existing `schemaFields` mapping so preview-seeded fields save.

- [ ] **Step 8: Add source type column**

In `page.tsx`, add a column after name:

```tsx
    {
      title: t('dataSource.sourceType'),
      dataIndex: 'source_type',
      key: 'source_type',
      width: 140,
      render: (value: string) => t(`dataSource.sourceTypes.${value || 'nats'}`),
    },
```

- [ ] **Step 9: Run frontend checks**

Run:

```bash
cd web && pnpm lint && pnpm type-check
```

Expected: PASS or only pre-existing unrelated failures. Record unrelated failures in the final notes.

- [ ] **Step 10: Commit only this task if working in small commits**

```bash
git add 'web/src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx' \
  'web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx' \
  web/src/app/ops-analysis/locales/zh.json \
  web/src/app/ops-analysis/locales/en.json
git commit -m "feat: add datasource preview form flow"
```

---

### Task 8: Final Verification And Documentation Bundle

**Files:**
- Keep: `docs/superpowers/specs/2026-07-01-operation-analysis-external-datasource-preview-design.md`
- Keep: `docs/superpowers/plans/2026-07-01-operation-analysis-external-datasource-preview.md`
- Verify all backend and frontend changed files.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
cd server && uv run pytest \
  apps/operation_analysis/tests/test_datasource_preview_schema.py \
  apps/operation_analysis/tests/test_datasource_preview_rest_api.py \
  apps/operation_analysis/tests/test_datasource_preview_database.py \
  apps/operation_analysis/tests/test_datasource_preview_view.py \
  apps/operation_analysis/tests/test_datasource_view.py \
  apps/operation_analysis/tests/test_datasource_filters_serializers.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend checks**

Run:

```bash
cd web && pnpm lint && pnpm type-check
```

Expected: PASS or only unrelated pre-existing failures.

- [ ] **Step 3: Run server migration check**

Run:

```bash
cd server && uv run python manage.py makemigrations --check --dry-run
```

Expected: "No changes detected" after the migration file is committed.

- [ ] **Step 4: Review staged diff**

Run:

```bash
git diff --check
git diff --stat
```

Expected: no whitespace errors. Stat should include only operation analysis preview code, locale/type/API changes, the design doc, and this plan.

- [ ] **Step 5: Commit implementation and docs together**

```bash
git add docs/superpowers/specs/2026-07-01-operation-analysis-external-datasource-preview-design.md \
  docs/superpowers/plans/2026-07-01-operation-analysis-external-datasource-preview.md \
  server/apps/operation_analysis \
  'web/src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx' \
  'web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx' \
  web/src/app/ops-analysis/types/dataSource.ts \
  web/src/app/ops-analysis/api/dataSource.ts \
  web/src/app/ops-analysis/components/dataSourcePreviewTable.tsx \
  web/src/app/ops-analysis/locales/zh.json \
  web/src/app/ops-analysis/locales/en.json
git commit -m "feat: add operation analysis external datasource preview"
```

Expected: commit succeeds and includes the design doc with code.

---

## Self-Review

Spec coverage:

- Source type entry: Task 1 backend fields and Task 7 frontend source selector.
- REST API preview: Task 3 executor, Task 5 API, Task 7 UI.
- MySQL/PostgreSQL preview: Task 4 executor, Task 5 API, Task 7 UI.
- `items/count/fields`: Task 2 contract, Task 3/4 executors, Task 5 API, Task 6 frontend types/table.
- `fields` as non-hard dependency: Task 6 preview table uses `fields` first and falls back to `items[0]`.
- First-stage simple inference: Task 2 uses first non-empty object keys and scans only those keys.
- NATS compatibility: Task 1 keeps defaults as `nats`; Task 5 adds new preview action without replacing `get_source_data`.
- Security baseline: Task 3 timeout/size guard, Task 4 SELECT/limit guard, Task 1 redaction, Task 5 group check for saved preview.
- Docs and commit bundling: Task 8 commits design and plan with implementation.

Placeholder scan:

- No deferred implementation markers are used.
- All tasks include concrete files, commands, expected outcomes, and code snippets for core changes.

Type consistency:

- Backend uses `source_type`, `connection_config`, `query_config`, `items`, `count`, and `fields` consistently.
- Frontend uses `DataSourceType`, `DataSourcePreviewRequest`, and `DataSourcePreviewResponse` consistently.

## specs: 2026-07-01-operation-analysis-external-datasource-preview-design.md

日期：2026-07-01

## 背景

当前运营分析的数据源主体模型已经具备 `name`、`rest_api`、`params`、`field_schema`、`chart_type` 等基础抽象，但运行时仍然围绕 NATS 命名空间和 NATS 调用链路展开。这个模式适合内部工程化接入，不适合 PLG 场景下的外部客户自助接入。

本设计聚焦第一阶段：先验证外部数据源从配置、连接、取样到前端表格预览的链路。它不是完整的数据集平台，也不是 OLAP 或 BI 语义层。

## 目标

第一阶段交付“外部数据源快速预览链路”：

1. 用户按数据来源类型创建数据源，而不是先理解 NATS 命名空间。
2. 支持外部来源的最小连接和取样能力。
3. 服务端统一返回原始表格数据、总数和字段推断结果。
4. 前端展示一个原始表格预览组件，验证取数链路成立。
5. 保留现有 NATS 数据源，不推翻已有模型和页面骨架。

## 非目标

第一阶段不做以下能力：

1. 完整 OLAP、跨源 Join、语义层、物化刷新。
2. 复杂图表自动生成。
3. 调度同步、增量同步、数据仓库存储。
4. 完整数据治理、血缘、口径管理。
5. Excel 的生产级数据管理。Excel 可作为后续导入型数据源处理。

## 分层判断

推荐产品和技术分层如下：

```text
外部数据来源
  ├─ 数据库 MySQL / PostgreSQL
  ├─ HTTP API REST API
  ├─ 文件导入 Excel
  └─ 内部高级来源 NATS
        ↓
连接器层
  - 连接、认证、连通性校验、取样、字段探测
        ↓
数据源层
  - 定义取数对象：表 / SQL / API path / Excel sheet / NATS method
  - 保存取数参数、分页、limit、返回路径
        ↓
数据集层
  - 字段结构、字段语义、维度/指标、默认过滤、复用配置
        ↓
轻分析层
  - 聚合、过滤、趋势、排行、明细查询
        ↓
视图与模板层
  - 表格、趋势图、柱状图、饼图、单值卡、TopN、仪表盘模板
        ↓
业务消费层
  - 日常分析、专题看板、大屏展示、运营复盘

横切能力
  - 权限、凭据、审计、脱敏、限流、超时、错误诊断
```

第一阶段只打通：

```text
连接器配置 -> 测试连接 -> 取样 preview -> 推断字段 -> 原始表格预览
```

原始表格预览可以绕过轻分析层。轻分析层是标准化配置后的增强能力，不是快速见数的前置条件。

## 推荐范围

推荐第一阶段采用“REST API + 数据库取样打透”的范围：

1. REST API：验证远程响应解析、认证、response path、字段推断。
2. MySQL / PostgreSQL：验证数据库连接、只读查询、limit、结果集标准化。
3. NATS：保留现有入口和运行链路，作为内部高级来源。
4. Excel：保留产品位置，后续作为导入型数据源处理。

这样能验证两类差异最大的来源：REST API 的响应解析，以及数据库的连接和查询执行。

## 数据模型建议

继续保留 `DataSourceAPIModel` 作为数据源主体。新增通用连接器字段，现有 `rest_api` 和 `namespaces` 用于兼容 NATS。

建议字段：

```text
source_type
  nats | mysql | postgresql | rest_api | excel

connection_config
  连接地址、端口、库名、账号、密码、REST URL、认证方式等

query_config
  表名、只读查询、REST method、headers、params、response_path、limit 等

field_schema
  字段配置。预览阶段由 fields 自动生成草稿，标准化阶段允许用户修正
```

`rest_api` 字段不再作为新连接器的统一运行字段。它保留给历史 NATS 数据源和存量导入导出兼容。

## 连接器执行器

后端增加连接器注册和执行器抽象：

```text
ConnectorRegistry
  - 根据 source_type 找到执行器

ConnectorExecutor
  - test_connection(config)
  - preview(config, query, limit)
  - infer_schema(items)
```

第一阶段执行器：

1. `NatsConnectorExecutor`：包装现有 `GetNatsData`，保持兼容。
2. `RestApiConnectorExecutor`：发起受限 HTTP 请求，解析 `response_path`。
3. `DatabaseConnectorExecutor`：支持 MySQL / PostgreSQL 连接和只读取样。

## 预览接口

建议提供两个入口：

```text
POST /operation_analysis/api/data_source/preview/
POST /operation_analysis/api/data_source/{id}/preview/
```

第一个用于保存前预览，第二个用于已保存数据源重新预览。

统一返回：

```json
{
  "items": [
    { "date": "2026-06-01", "channel": "官网", "users": 120 }
  ],
  "count": 1,
  "fields": [
    { "key": "date", "title": "date", "value_type": "datetime" },
    { "key": "channel", "title": "channel", "value_type": "string" },
    { "key": "users", "title": "users", "value_type": "number" }
  ]
}
```

字段含义：

1. `items`：当前样例数据行，表格展示的最小依赖。
2. `count`：总数或当前可确认数量，用于分页和用户感知。
3. `fields`：字段推断结果，用作 `field_schema` 草稿，不作为表格预览硬依赖。

前端容错规则：

```text
有 fields -> 按 fields 生成列
无 fields -> 从 items 第一行推断列
items 为空 -> 展示空状态和字段探测结果，如果有 fields
```

## fields 推断策略

第一阶段只做基础类型推断：

```text
boolean
  true / false

number
  多数非空值可解析为有限数字

datetime
  多数非空值可解析为日期时间

string
  默认类型
```

推断规则：

1. 找到第一条非空对象记录，使用这条记录的 key 生成字段列表。
2. 只针对已生成字段扫描前 50 到 100 行样例数据，用于判断基础类型。
3. 忽略空值后判断类型。
4. 类型冲突时降级为 `string`。
5. `title` 默认等于 `key`，后续由用户在标准化阶段修改。

第一阶段不合并样例数据中出现过的所有 key。这样可以降低实现复杂度，优先验证取数、预览和字段草稿链路。代价是：如果后续行出现第一条记录没有的稀疏字段，一期不会自动展示这些字段。

第一阶段不加入 `role`、`aggregation`、`unit`、`semantic_type` 等高级语义，避免把 fields 变成轻分析层配置。

## 前端交互

数据源创建入口调整为按来源类型开始：

```text
选择来源类型
  -> 填连接信息
  -> 测试连接
  -> 配置取样对象
  -> 点击预览
  -> 查看表格和字段
  -> 保存数据源
```

预览区展示：

1. 连接状态。
2. 错误信息和修复建议。
3. 字段列表：字段名、显示名、类型。
4. 前 N 行数据表格。
5. “使用当前字段配置”或保存时自动写入 `field_schema`。

前端可以复用现有表格解析能力。当前表格组件已经支持数组和 `{ items, count }` 结构，并可以从 `field_schema` 或首行数据推断列。

## 安全和权限

第一阶段必须保留最低安全边界。

数据库：

1. 产品建议使用只读账号。
2. 服务端强制 `limit`，默认 100，最大值需要配置上限。
3. 优先支持“选择表 + 自动 SELECT”。
4. 如允许 SQL，只允许单条 `SELECT`，禁止 DDL、DML、多语句。
5. 设置连接超时和查询超时。

REST API：

1. 设置请求超时。
2. 限制响应体大小。
3. Header、Token 等敏感字段加密存储、脱敏返回。
4. 保留 SSRF 防护扩展点。后续可复用现有网络白名单设计。

通用：

1. 沿用 `groups` 做组织范围隔离。
2. 预览、创建、修改、删除写入操作日志。
3. 凭据加密存储。
4. 前端不回显明文密钥。
5. 错误分类为连接失败、认证失败、查询失败、解析失败、无数据、权限不足。

## 可行性

可行性较高。

已有基础：

1. 后端已有 `DataSourceAPIModel`，可作为主体对象演进。
2. 前端已有表格组件，能消费数组和 `{ items, count }`。
3. 后端依赖已有 `sqlalchemy`、`pymysql`、`psycopg2-binary`、`httpx`、`requests`、`pandas`、`openpyxl`。
4. 现有 `field_schema` 可承接 `fields` 推断结果。

主要复杂度：

1. NATS 专用运行链路需要抽象成按 `source_type` 路由。
2. 数据库预览要做只读和 limit 约束。
3. REST API 要处理 response path、认证、超时和响应大小。
4. 凭据加密和脱敏需要避免泄漏。

## 复杂度估算

按 REST API + MySQL / PostgreSQL 取样打透估算：

| 模块 | 复杂度 | 说明 |
|---|---:|---|
| 模型扩展与迁移 | 中 | 新增 source_type、connection_config、query_config，兼容 NATS |
| 执行器抽象 | 中 | registry + executor 接口 |
| REST API preview | 中 | 请求、认证、response_path、错误处理 |
| DB preview | 中偏高 | 连接、只读限制、limit、类型转换 |
| fields 推断 | 低 | 基于第一条非空记录生成字段，扫描样例行推断基础类型 |
| 前端动态表单 | 中 | 按 source_type 展示不同配置 |
| 表格预览组件 | 低到中 | 复用现有表格能力 |
| 测试 | 中 | executor fake、错误分类、权限、参数校验 |

预计 8 到 12 个工作日可完成可联调版本。如果只做 REST API，预计 4 到 6 个工作日。

## 实施顺序

1. 增加数据源类型和通用配置字段，保持 NATS 兼容。
2. 增加连接器 registry 和 executor 抽象。
3. 实现 REST API preview，先打通最短链路。
4. 实现 MySQL / PostgreSQL preview，加入只读和 limit 约束。
5. 实现 `fields` 推断并写入预览返回。
6. 前端增加来源类型选择、动态连接表单和预览区。
7. 预览成功后允许将 `fields` 保存为 `field_schema` 草稿。
8. 补充测试和错误状态。

## 验收标准

1. 数据源入口可以按来源类型创建数据源。
2. REST API 数据源可以配置 URL、认证参数、response path，并预览表格。
3. MySQL / PostgreSQL 数据源可以测试连接并预览表格。
4. 预览接口返回 `items`、`count`、`fields`。
5. 没有 `fields` 时前端仍可从 `items` 推断表格列。
6. 预览失败能区分连接、认证、查询、解析、权限和空数据。
7. 敏感配置加密存储并脱敏返回。
8. NATS 存量数据源仍可使用现有取数链路。

## 后续演进

第二阶段可以在第一阶段基础上继续建设：

1. Excel 导入型数据源。
2. 合并样例数据中出现过的所有 key，提升稀疏字段发现能力。
3. 数据集层标准化配置。
4. 字段角色：时间、维度、指标。
5. 图表推荐。
6. 一份数据集多个组件复用。
7. 轻分析层的聚合、过滤、趋势、排行。
8. 调度刷新和缓存策略。

## 结论

第一阶段建议聚焦“外部数据源快速预览链路”。核心价值是让用户先把数据接进来并看到原始表格，再进入字段标准化和图表配置。

`fields` 应加入预览返回，但作为增强信息和 `field_schema` 草稿，不作为表格展示硬依赖。这样既能快速见数，又能为后续数据集和轻分析层留下稳定接口。

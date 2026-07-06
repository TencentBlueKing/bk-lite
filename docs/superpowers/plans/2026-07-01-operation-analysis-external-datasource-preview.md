# Operation Analysis External Datasource Preview Implementation Plan

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

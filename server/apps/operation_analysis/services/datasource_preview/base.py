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
    warnings: list[str] | None = None
    raw_items: list[dict[str, Any]] | None = None
    raw_count: int | None = None
    raw_fields: list[dict[str, str]] | None = None
    transform_error: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "items": self.items,
            "count": self.count,
            "fields": self.fields,
        }
        if self.warnings:
            payload["warnings"] = self.warnings
        if self.raw_items is not None:
            payload["raw_items"] = self.raw_items
            payload["raw_count"] = self.raw_count if self.raw_count is not None else len(self.raw_items)
            payload["raw_fields"] = self.raw_fields or infer_fields_safe(self.raw_items)
        if self.transform_error:
            payload["transform_error"] = self.transform_error
        return payload


def infer_fields_safe(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    try:
        from apps.operation_analysis.services.datasource_preview.schema import infer_fields

        return infer_fields(items)
    except Exception:
        return []


@dataclass
class ExecuteResult:
    data: Any
    warnings: list[str] | None = None


class BaseConnectorExecutor:
    source_type = ""

    def test_connection(self, connection_config: dict[str, Any]) -> None:
        return None

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
        **kwargs: Any,
    ) -> PreviewResult:
        raise NotImplementedError

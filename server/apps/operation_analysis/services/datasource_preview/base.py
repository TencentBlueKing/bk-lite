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

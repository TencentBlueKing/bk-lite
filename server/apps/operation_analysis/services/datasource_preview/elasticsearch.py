"""Elasticsearch 7/8 只读 search/aggs 执行器。"""

from __future__ import annotations

from typing import Any

from apps.operation_analysis.services.datasource_preview.base import BaseConnectorExecutor, ConnectorError, PreviewResult
from apps.operation_analysis.services.datasource_preview.elasticsearch_client import ElasticsearchSearchClient, normalize_elasticsearch_config
from apps.operation_analysis.services.datasource_preview.elasticsearch_query import (
    MAX_ROWS,
    flatten_search_response,
    prepare_search_body,
    validate_index_name,
)
from apps.operation_analysis.services.datasource_preview.schema import infer_fields
from apps.operation_analysis.services.user_messages import oa_message


def _contains_opensearch(value: Any) -> bool:
    if isinstance(value, str):
        return "opensearch" in value.lower()
    if isinstance(value, dict):
        return any(_contains_opensearch(key) or _contains_opensearch(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_opensearch(item) for item in value)
    return False


def assert_supported_cluster(info: dict) -> None:
    if not isinstance(info, dict):
        raise ConnectorError(
            oa_message("messages.es_response_invalid", "Elasticsearch 响应格式无效"),
            code="elasticsearch_response_invalid",
            status_code=502,
        )
    if _contains_opensearch(info):
        raise ConnectorError(
            oa_message("messages.es_distribution_unsupported", "仅支持 Elasticsearch 7 和 8"),
            code="elasticsearch_distribution_unsupported",
            status_code=400,
        )
    version = info.get("version") if isinstance(info.get("version"), dict) else {}
    major = str(version.get("number") or "").split(".", 1)[0]
    if major not in {"7", "8"}:
        raise ConnectorError(
            oa_message("messages.es_distribution_unsupported", "仅支持 Elasticsearch 7 和 8"),
            code="elasticsearch_distribution_unsupported",
            status_code=400,
        )


class ElasticsearchConnectorExecutor(BaseConnectorExecutor):
    source_type = "elasticsearch"

    def __init__(self, client=None):
        self.client = client or ElasticsearchSearchClient()

    def test_connection(self, connection_config: dict[str, Any]) -> None:
        normalized = normalize_elasticsearch_config(connection_config)
        info = self.client.info(normalized)
        assert_supported_cluster(info)

    def execute(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        *,
        limit: int = MAX_ROWS,
    ) -> tuple[list[dict], list[str]]:
        normalized = normalize_elasticsearch_config(connection_config)
        index = validate_index_name(normalized.get("index") or "")
        body = prepare_search_body(query_config)
        info = self.client.info(normalized)
        assert_supported_cluster(info)
        payload = self.client.search(normalized, index, body)
        row_limit = min(max(int(limit or MAX_ROWS), 1), MAX_ROWS)
        rows, truncated = flatten_search_response(payload, max_rows=row_limit)
        warnings = []
        if truncated:
            warnings.append(
                oa_message(
                    "messages.es_rows_truncated",
                    "结果已截断为 {limit} 行",
                    limit=row_limit,
                )
            )
        return rows, warnings

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
        **kwargs,
    ) -> PreviewResult:
        try:
            rows, warnings = self.execute(connection_config, query_config, limit=limit)
        except ConnectorError:
            raise
        except Exception as exc:
            from apps.operation_analysis.services.datasource_preview.elasticsearch_client import log_elasticsearch_failure

            log_elasticsearch_failure("search", exc)
            raise ConnectorError(
                oa_message("messages.es_query_failed", "Elasticsearch 查询失败"),
                code="elasticsearch_query_failed",
                status_code=502,
            ) from exc
        return PreviewResult(items=rows, count=len(rows), fields=infer_fields(rows), warnings=warnings or None)

"""Elasticsearch 连接：出站、只读 DSL、展平、版本和运行时取数。"""

import base64
import json
from types import SimpleNamespace

import pytest
from rest_framework import status

from apps.operation_analysis.constants.import_export import SENSITIVE_PLACEHOLDER, is_sensitive_field_name
from apps.operation_analysis.models.datasource_models import DataConnection, DataSourceAPIModel
from apps.operation_analysis.schemas.import_export_schema import DatasourceItem
from apps.operation_analysis.serializers.datasource_serializers import transform_config_for_source_type
from apps.operation_analysis.services.data_connection.config_crypto import encrypt_connection_config
from apps.operation_analysis.services.data_connection.resolver import resolve_datasource_connection
from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.elasticsearch import ElasticsearchConnectorExecutor
from apps.operation_analysis.services.datasource_preview.elasticsearch_client import normalize_elasticsearch_config
from apps.operation_analysis.services.datasource_preview.elasticsearch_egress import validate_elasticsearch_url
from apps.operation_analysis.services.datasource_preview.elasticsearch_query import (
    flatten_search_response,
    prepare_search_body,
    validate_stored_query_config,
)
from apps.operation_analysis.services.import_export.export_service import ExportService
from apps.operation_analysis.views import datasource_view

PRIVATE_ADDRINFO = [(2, 1, 6, "", ("10.1.2.3", 9200))]
METADATA_ADDRINFO = [(2, 1, 6, "", ("169.254.169.254", 80))]
PUBLIC_ADDRINFO = [(2, 1, 6, "", ("8.8.8.8", 443))]
MIXED_ADDRINFO = [(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("169.254.169.254", 80))]


def _resolve(addrinfo):
    def getaddrinfo(hostname, port, proto=0):
        return addrinfo

    return getaddrinfo


def test_private_and_public_targets_are_allowed_without_whitelist():
    assert validate_elasticsearch_url("http://10.1.1.8:9200") == "http://10.1.1.8:9200"
    assert validate_elasticsearch_url("https://192.168.1.9:9200") == "https://192.168.1.9:9200"
    assert validate_elasticsearch_url("http://172.16.4.4:9200") == "http://172.16.4.4:9200"
    assert validate_elasticsearch_url("http://8.8.8.8:9200") == "http://8.8.8.8:9200"


@pytest.mark.parametrize(
    "url",
    [
        "http://[64:ff9b::a9fe:a9fe]/",
        "http://[64:ff9b::7f00:1]:9200",
        "http://[64:ff9b::a9fe:1]/",
    ],
)
def test_nat64_well_known_prefix_is_blocked(url):
    with pytest.raises(ConnectorError) as exc:
        validate_elasticsearch_url(url)
    assert exc.value.code == "elasticsearch_target_forbidden"


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/latest/meta-data/",
        "http://metadata.aliyun.com/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://localhost:9200",
        "http://127.0.0.1:9200",
        "file:///etc/passwd",
        "http://user:pass@10.1.1.8:9200",
        "http://10.1.1.8:9200,http://10.1.1.9:9200",
    ],
)
def test_metadata_and_dangerous_targets_are_blocked(url):
    with pytest.raises(ConnectorError) as exc:
        validate_elasticsearch_url(url)
    assert exc.value.code in {"elasticsearch_target_forbidden", "elasticsearch_url_invalid"}


def test_hostname_allows_rfc1918_and_blocks_metadata_resolution(monkeypatch):
    monkeypatch.setattr(
        "apps.operation_analysis.services.datasource_preview.elasticsearch_egress.socket.getaddrinfo",
        _resolve(PRIVATE_ADDRINFO),
    )
    assert validate_elasticsearch_url("http://es.internal:9200").startswith("http://es.internal")

    monkeypatch.setattr(
        "apps.operation_analysis.services.datasource_preview.elasticsearch_egress.socket.getaddrinfo",
        _resolve(METADATA_ADDRINFO),
    )
    with pytest.raises(ConnectorError) as exc:
        validate_elasticsearch_url("http://es.internal:9200")
    assert exc.value.code == "elasticsearch_target_forbidden"

    monkeypatch.setattr(
        "apps.operation_analysis.services.datasource_preview.elasticsearch_egress.socket.getaddrinfo",
        _resolve(MIXED_ADDRINFO),
    )
    with pytest.raises(ConnectorError):
        validate_elasticsearch_url("http://es.internal:9200")

    monkeypatch.setattr(
        "apps.operation_analysis.services.datasource_preview.elasticsearch_egress.socket.getaddrinfo",
        _resolve(PUBLIC_ADDRINFO),
    )
    validate_elasticsearch_url("https://es.example:9200")


def test_query_body_stays_read_only_without_param_or_time_injection():
    body = prepare_search_body({"body": {"query": {"term": {"service": "{{service}}"}}, "size": 20, "sort": ["@timestamp"]}})
    assert body["query"]["term"]["service"] == "{{service}}"
    assert body["size"] == 20

    with pytest.raises(ConnectorError) as script_error:
        prepare_search_body({"body": {"query": {"script_score": {"script": {"source": "return 1"}}}}})
    assert script_error.value.code == "elasticsearch_query_forbidden"

    with pytest.raises(ConnectorError) as string_script:
        prepare_search_body({"body": {"aggs": {"by_status": {"terms": {"field": "status", "script": "doc['status'].value"}}}}})
    assert string_script.value.code == "elasticsearch_query_forbidden"

    with pytest.raises(ConnectorError) as long_timeout:
        prepare_search_body({"body": {"query": {"match_all": {}}, "timeout": "2m"}})
    assert long_timeout.value.code == "elasticsearch_query_invalid"
    allowed = prepare_search_body({"body": {"query": {"match_all": {}}, "timeout": "30s"}})
    assert allowed["timeout"] == "30s"

    with pytest.raises(ConnectorError) as timed:
        prepare_search_body({"body": {"query": {"match_all": {}}}, "time_field": "@timestamp"})
    assert timed.value.code == "elasticsearch_query_forbidden"


def _assert_query_forbidden(query_config):
    with pytest.raises(ConnectorError) as exc:
        prepare_search_body(query_config)
    assert exc.value.code == "elasticsearch_query_forbidden"
    with pytest.raises(ConnectorError) as stored:
        validate_stored_query_config(query_config)
    assert stored.value.code == "elasticsearch_query_forbidden"


def test_scripted_metric_and_wrapper_queries_are_rejected():
    _assert_query_forbidden(
        {
            "body": {
                "aggs": {
                    "profit": {
                        "scripted_metric": {
                            "init_script": "state.transactions = []",
                            "map_script": "state.transactions.add(1)",
                            "combine_script": "return state.transactions",
                            "reduce_script": "return states",
                        }
                    }
                }
            }
        }
    )
    _assert_query_forbidden(
        {
            "body": {
                "aggs": {
                    "profit": {
                        "scripted_metric": {
                            "init_script": {"source": "state.transactions = []"},
                            "map_script": {"source": "state.transactions.add(1)"},
                            "combine_script": {"source": "return state"},
                            "reduce_script": {"source": "return states[0]"},
                        }
                    }
                }
            }
        }
    )
    _assert_query_forbidden({"body": {"aggs": {"by_status": {"terms": {"field": "status", "map_script": "doc['status'].value"}}}}})
    _assert_query_forbidden(
        {
            "body": {
                "aggs": {
                    "by_status": {
                        "terms": {"field": "status", "map_script": {"source": "doc['status'].value"}},
                    }
                }
            }
        }
    )
    hidden_script = base64.b64encode(json.dumps({"script": {"source": "return true"}}).encode()).decode()
    _assert_query_forbidden({"body": {"query": {"wrapper": {"query": hidden_script}}}})
    hidden_metric = base64.b64encode(
        json.dumps({"scripted_metric": {"map_script": "state.n = 1", "reduce_script": "return states"}}).encode()
    ).decode()
    nested = base64.b64encode(json.dumps({"wrapper": {"query": hidden_metric}}).encode()).decode()
    _assert_query_forbidden({"body": {"query": {"wrapper": {"query": nested}}}})
    _assert_query_forbidden({"body": {"query": {"wrapper": {"query": "not-base64!!!"}}}})

    benign = base64.b64encode(json.dumps({"match_all": {}}).encode()).decode()
    body = prepare_search_body({"body": {"query": {"wrapper": {"query": benign}}}})
    assert body["query"]["wrapper"]["query"] == benign
    validate_stored_query_config({"body": {"query": {"wrapper": {"query": benign}}}})


def test_aggs_force_size_zero_without_injecting_canvas_time():
    body = prepare_search_body({"body": {"query": {"match_all": {}}, "aggs": {"by_status": {"terms": {"field": "status"}}}}})
    assert body["size"] == 0
    assert body["query"] == {"match_all": {}}


def test_flatten_aggs_to_name_value_and_hits_source_for_tables():
    agg_rows, truncated = flatten_search_response(
        {
            "aggregations": {
                "by_status": {
                    "buckets": [
                        {"key": "ok", "doc_count": 3, "avg_cost": {"value": 1.5}},
                        {"key": "bad", "doc_count": 1, "avg_cost": {"value": 4}},
                    ]
                }
            }
        },
        max_rows=10,
    )
    assert truncated is False
    assert agg_rows[0]["name"] == "ok"
    assert agg_rows[0]["value"] == 1.5
    assert agg_rows[0]["count"] == 3

    hit_rows, _truncated = flatten_search_response(
        {"hits": {"hits": [{"_source": {"resource_name": "MySQL", "resource_count": 18}}]}},
        max_rows=10,
    )
    assert hit_rows == [{"resource_name": "MySQL", "resource_count": 18}]

    limited, was_truncated = flatten_search_response(
        {"aggregations": {"by_status": {"buckets": [{"key": "a", "doc_count": 1}, {"key": "b", "doc_count": 2}]}}},
        max_rows=1,
    )
    assert was_truncated is True
    assert limited == [{"name": "a", "by_status": "a", "doc_count": 1, "count": 1, "value": 1}]


def test_cluster_info_accepts_es7_and_es8_and_rejects_opensearch_and_es9():
    class Client:
        def __init__(self, info):
            self._info = info

        def info(self, _config):
            return self._info

        def search(self, _config, index, body):
            return {"hits": {"hits": [{"_source": {"name": index, "value": body["size"]}}]}}

    executor = ElasticsearchConnectorExecutor(client=Client({"version": {"number": "7.17.13"}, "tagline": "You Know, for Search"}))
    executor.test_connection({"url": "http://10.0.0.8:9200", "auth_type": "none", "index": "logs"})

    executor = ElasticsearchConnectorExecutor(client=Client({"version": {"number": "8.12.0"}, "tagline": "You Know, for Search"}))
    rows, _warnings = executor.execute(
        {"url": "http://10.0.0.8:9200", "auth_type": "none", "index": "logs"},
        {"body": {"size": 5, "query": {"match_all": {}}}},
    )
    assert rows == [{"name": "logs", "value": 5}]

    for info in (
        {"version": {"number": "2.11.0", "distribution": "opensearch"}, "tagline": "The OpenSearch Project"},
        {"version": {"number": "7.10.2", "distribution": "opensearch"}, "tagline": "You Know, for Search"},
        {"version": {"number": "9.0.0"}, "tagline": "You Know, for Search"},
    ):
        with pytest.raises(ConnectorError) as exc:
            ElasticsearchConnectorExecutor(client=Client(info)).test_connection({"url": "http://10.0.0.8:9200", "auth_type": "none", "index": "logs"})
        assert exc.value.code == "elasticsearch_distribution_unsupported"


def test_auth_shape_rejects_mtls_and_disabled_verification():
    basic = normalize_elasticsearch_config(
        {
            "url": "https://10.0.0.8:9200",
            "auth_type": "basic",
            "username": "ops",
            "password": "secret",
            "index": "logs",
        }
    )
    assert basic["auth_type"] == "basic"
    api_key = normalize_elasticsearch_config({"url": "http://10.0.0.8:9200", "auth_type": "api_key", "api_key": "id:secret", "index": "logs"})
    assert api_key["api_key"] == ("id", "secret")
    with pytest.raises(ConnectorError):
        normalize_elasticsearch_config({"url": "https://10.0.0.8:9200", "auth_type": "none", "client_cert": "pem", "index": "logs"})
    with pytest.raises(ConnectorError):
        normalize_elasticsearch_config({"url": "https://10.0.0.8:9200", "auth_type": "none", "verify_certs": False, "index": "logs"})


def test_connection_library_requires_an_index():
    from apps.operation_analysis.serializers.data_connection_serializers import DataConnectionTestSerializer

    missing = DataConnectionTestSerializer(data={"connection_type": "elasticsearch", "config": {"url": "http://10.0.0.8:9200", "auth_type": "none"}})
    assert missing.is_valid() is False
    present = DataConnectionTestSerializer(
        data={
            "connection_type": "elasticsearch",
            "config": {"url": "http://10.0.0.8:9200", "auth_type": "none", "index": "logs-*"},
        }
    )
    assert present.is_valid(), present.errors


def test_api_key_is_sensitive_for_export_sanitize():
    assert is_sensitive_field_name("api_key") is True
    masked = ExportService.mask_sensitive_fields({"url": "http://10.0.0.8:9200", "api_key": "id:secret", "index": "logs"})
    assert masked["api_key"] == SENSITIVE_PLACEHOLDER
    assert masked["url"] == "http://10.0.0.8:9200"
    assert masked["index"] == "logs"


def test_import_schema_accepts_elasticsearch_and_rejects_script():
    item = DatasourceItem(
        key="es-logs",
        name="日志",
        source_type="elasticsearch",
        connection_config={"url": "http://10.0.0.8:9200", "auth_type": "none", "index": "logs-*"},
        query_config={"body": {"size": 10, "query": {"match_all": {}}}},
    )
    assert item.source_type == "elasticsearch"
    with pytest.raises(ValueError):
        DatasourceItem(
            key="es-time",
            name="时间",
            source_type="elasticsearch",
            connection_config={"url": "http://10.0.0.8:9200", "auth_type": "none", "index": "logs"},
            query_config={"body": {"query": {"match_all": {}}}, "time_field": "@timestamp"},
        )

    with pytest.raises(ValueError):
        DatasourceItem(
            key="es-script",
            name="脚本",
            source_type="elasticsearch",
            connection_config={"url": "http://10.0.0.8:9200", "auth_type": "none", "index": "logs"},
            query_config={"body": {"query": {"script": {"source": "return 1"}}}},
        )


def test_transform_stays_disabled_for_elasticsearch():
    assert transform_config_for_source_type("elasticsearch", {"enabled": True, "language": "python", "script": "return rows"}) == {
        "enabled": False,
        "language": "python",
        "script": "",
    }


def test_resolver_overrides_index_like_database_name():
    connection = DataConnection(
        name="es-main",
        connection_type=DataConnection.TYPE_ELASTICSEARCH,
        groups=[1],
        is_active=True,
        config=encrypt_connection_config({"url": "http://10.0.0.8:9200", "auth_type": "api_key", "api_key": "id:secret", "index": "logs"}),
    )
    connection.pk = 7
    datasource = DataSourceAPIModel(
        name="es-ds",
        source_type=DataSourceAPIModel.SOURCE_TYPE_ELASTICSEARCH,
        groups=[1],
        connection=connection,
        connection_overrides={"index": "logs-override"},
        query_config={"body": {"size": 1}},
    )
    resolved = resolve_datasource_connection(datasource, current_team=1)
    assert resolved["index"] == "logs-override"
    assert resolved["url"] == "http://10.0.0.8:9200"
    assert resolved["api_key"] == "id:secret"


def test_get_source_data_ignores_widget_query_and_canvas_time(monkeypatch):
    from rest_framework.test import APIRequestFactory, force_authenticate

    factory = APIRequestFactory()
    user = SimpleNamespace(is_superuser=True, is_authenticated=True, pk=1)

    def call(body):
        request = factory.post("/data-source/get_source_data/1/", body, format="json")
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)
        view = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})
        return view(request, pk="1")

    class Client:
        def __init__(self):
            self.searches = []

        def info(self, _config):
            return {"version": {"number": "8.11.0"}, "tagline": "You Know, for Search"}

        def search(self, _config, index, body):
            self.searches.append({"index": index, "body": body})
            return {"hits": {"hits": [{"_source": {"name": "ok", "value": 2}}]}}

    client = Client()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: ElasticsearchConnectorExecutor(client=client))
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="es-demo",
            groups=[1],
            source_type=DataSourceAPIModel.SOURCE_TYPE_ELASTICSEARCH,
            connection_id=None,
            connection_config={"url": "http://10.0.0.8:9200", "auth_type": "none", "index": "logs"},
            query_config={"body": {"size": 10, "query": {"match_all": {}}}},
            params=[],
            rest_api="",
            transform_config={},
        ),
    )

    rejected = call(
        {"timeRange": ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"], "query": {"match_all": {"boost": 2}}},
    )
    assert rejected.status_code == status.HTTP_400_BAD_REQUEST
    assert client.searches == []

    response = call({})
    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"] == [{"name": "ok", "value": 2}]
    assert client.searches[0]["index"] == "logs"
    assert client.searches[0]["body"]["query"] == {"match_all": {}}
    assert "range" not in client.searches[0]["body"]["query"]


def test_client_uses_library_without_sniff(monkeypatch):
    captured = {}

    class FakeElasticsearch:
        def __init__(self, *args, **kwargs):
            captured["hosts"] = kwargs.get("hosts")
            captured["sniff_on_start"] = kwargs.get("sniff_on_start")
            captured["max_retries"] = kwargs.get("max_retries")
            captured["api_key"] = kwargs.get("api_key")

        def info(self):
            return {"version": {"number": "8.0.0"}, "tagline": "You Know, for Search"}

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(
        "apps.operation_analysis.services.datasource_preview.elasticsearch_client.Elasticsearch",
        FakeElasticsearch,
        raising=False,
    )
    # build_elasticsearch_client imports Elasticsearch inside the function.
    import apps.operation_analysis.services.datasource_preview.elasticsearch_client as client_module

    monkeypatch.setattr(client_module, "build_elasticsearch_client", client_module.build_elasticsearch_client)
    original_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name == "elasticsearch":
            return SimpleNamespace(Elasticsearch=FakeElasticsearch)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    from apps.operation_analysis.services.datasource_preview.elasticsearch_client import ElasticsearchSearchClient

    ElasticsearchSearchClient().info({"url": "http://10.0.0.8:9200", "auth_type": "api_key", "api_key": "id:secret", "index": "logs"})
    assert captured["hosts"] == [{"host": "10.0.0.8", "port": 9200, "use_ssl": False}]
    assert captured["sniff_on_start"] is False
    assert captured["max_retries"] == 0
    assert captured["api_key"] == ("id", "secret")
    assert captured["closed"] is True


def test_hostname_is_pinned_to_the_resolved_address(monkeypatch):
    monkeypatch.setattr(
        "apps.operation_analysis.services.datasource_preview.elasticsearch_egress.socket.getaddrinfo",
        _resolve(PRIVATE_ADDRINFO),
    )
    captured = {}

    class FakeElasticsearch:
        def __init__(self, *args, **kwargs):
            captured["hosts"] = kwargs.get("hosts")
            captured["headers"] = kwargs.get("headers")

        def info(self):
            return {"version": {"number": "8.0.0"}, "tagline": "You Know, for Search"}

        def close(self):
            return None

    original_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name == "elasticsearch":
            return SimpleNamespace(Elasticsearch=FakeElasticsearch)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    from apps.operation_analysis.services.datasource_preview.elasticsearch_client import ElasticsearchSearchClient

    ElasticsearchSearchClient().info({"url": "http://es.internal:9200", "auth_type": "none", "index": "logs"})
    assert captured["hosts"] == [{"host": "10.1.2.3", "port": 9200, "use_ssl": False}]
    assert captured["headers"]["Host"] == "es.internal"


def test_transport_failure_logs_one_sanitized_traceback(caplog):
    import logging

    from apps.operation_analysis.services.datasource_preview.elasticsearch_client import ElasticsearchSearchClient

    secret = "es-response-sentinel-9f3c"
    holder = {}

    def factory(_config):
        try:
            raise RuntimeError(secret)
        except RuntimeError as exc:
            holder["error"] = exc
            raise

    with caplog.at_level(logging.DEBUG, logger="operation_analysis"):
        with pytest.raises(ConnectorError) as caught:
            ElasticsearchSearchClient(client_factory=factory).info({"url": "http://10.0.0.8:9200", "auth_type": "none", "index": "logs"})

    assert caught.value.code == "elasticsearch_connection_failed"
    assert secret not in str(caught.value)
    assert str(holder["error"]) == secret
    records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "[ElasticsearchConnector] request failed failed_stage=%s error_type=%s status=%s"
    assert record.args == ("connect", "RuntimeError", "")
    assert record.getMessage() == "[ElasticsearchConnector] request failed failed_stage=connect error_type=RuntimeError status="
    assert record.exc_info[0].__name__ == "_SafeLogError"
    assert record.exc_info[1] is not holder["error"]
    assert record.exc_info[2] is holder["error"].__traceback__
    assert str(record.exc_info[1]) == "RuntimeError"
    formatted = "".join(__import__("traceback").format_exception(*record.exc_info))
    assert "Traceback" in formatted
    assert secret not in formatted
    assert secret not in record.getMessage()

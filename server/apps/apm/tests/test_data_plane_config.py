from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
COLLECTOR_CONFIG = REPOSITORY_ROOT / "deploy/apm/otel/collector.yaml"
EDGE_CONFIG = REPOSITORY_ROOT / "deploy/apm/nginx/apm.conf.template"
COMPOSE_CONFIG = REPOSITORY_ROOT / "deploy/apm/compose.yaml"


def _collector_config():
    return yaml.safe_load(COLLECTOR_CONFIG.read_text())


def _compose_config():
    return yaml.safe_load(COMPOSE_CONFIG.read_text())


def test_span_metrics_uses_all_spans_before_tail_sampling():
    config = _collector_config()
    pipelines = config["service"]["pipelines"]

    assert pipelines["traces/spanmetrics"]["receivers"] == ["otlp"]
    assert pipelines["traces/spanmetrics"]["exporters"] == ["spanmetrics"]
    assert "tail_sampling" not in pipelines["traces/spanmetrics"]["processors"]
    assert "tail_sampling" in pipelines["traces/sampled"]["processors"]


def test_reserved_attributes_are_removed_before_trusted_source_is_injected():
    config = _collector_config()
    expected_prefix = [
        "memory_limiter",
        "attributes/drop_reserved",
        "resource/drop_reserved",
        "transform/drop_nested_reserved",
        "resource/trusted_ingest_source",
        "transform/limits_and_route",
    ]

    for pipeline_name in ("traces/spanmetrics", "traces/sampled"):
        assert config["service"]["pipelines"][pipeline_name]["processors"][:6] == expected_prefix

    receiver = config["receivers"]["otlp"]["protocols"]
    assert receiver["grpc"]["include_metadata"] is True
    assert receiver["http"]["include_metadata"] is True
    trusted_action = config["processors"]["resource/trusted_ingest_source"]["attributes"][0]
    assert trusted_action == {
        "key": "bk.ingest_source.id",
        "from_context": "metadata.x-bk-ingest-source-id",
        "action": "upsert",
    }


def test_span_metric_dimensions_and_queues_are_bounded():
    config = _collector_config()
    spanmetrics = config["connectors"]["spanmetrics"]
    configured_dimensions = {item["name"] for item in spanmetrics["dimensions"]}

    assert configured_dimensions == {
        "service.namespace",
        "service.instance.id",
        "deployment.environment",
        "service.version",
        "bk.ingest_source.id",
    }
    assert spanmetrics["aggregation_cardinality_limit"]
    assert "resource_to_telemetry_conversion" not in config["exporters"]["prometheusremotewrite/victoria_metrics"]
    trace_exporter = config["exporters"]["otlphttp/victoria_traces"]
    assert trace_exporter["sending_queue"]["queue_size"]
    assert trace_exporter["sending_queue"]["storage"] == "file_storage"
    metric_exporter = config["exporters"]["prometheusremotewrite/victoria_metrics"]
    assert metric_exporter["remote_write_queue"]["queue_size"]
    assert "wal" not in metric_exporter


def test_trace_pipeline_drops_sensitive_attributes_and_request_response_bodies_before_storage():
    collector = COLLECTOR_CONFIG.read_text()

    assert "delete_matching_keys(span.attributes" in collector
    assert "delete_matching_keys(resource.attributes" in collector
    assert 'delete_key(span.attributes, "http.request.body")' in collector
    assert 'delete_key(span.attributes, "http.response.body")' in collector
    assert 'delete_key(span.attributes, "bk.apm.original_span_name")' in collector
    for raw_url_key in ("url.full", "url.path", "url.query", "url.fragment", "http.url", "http.target"):
        assert f'delete_key(span.attributes, "{raw_url_key}")' in collector
    assert collector.index("set_semconv_span_name") < collector.index('delete_key(span.attributes, "bk.apm.original_span_name")')
    assert collector.index("delete_matching_keys(span.attributes") < collector.index("otlphttp/victoria_traces")


def test_edge_replaces_internal_identity_and_does_not_overlap_telegraf():
    edge = EDGE_CONFIG.read_text()
    compose = COMPOSE_CONFIG.read_text()

    assert "location = /v1/traces" in edge
    assert "auth_request /_apm_machine_auth" in edge
    assert 'proxy_set_header Authorization ""' in edge
    assert 'proxy_set_header X-BK-Ingest-Source-Id ""' in edge
    assert "proxy_set_header X-BK-Ingest-Source-Id $trusted_ingest_source_id" in edge
    assert "proxy_cache_valid 204 8s" in edge
    assert "/telegraf/api" not in edge
    assert "/telegraf/api" not in compose


def test_data_plane_is_not_a_server_startup_dependency():
    startup = (REPOSITORY_ROOT / "server/support-files/release/startup.sh").read_text()

    assert "apm-otel-collector" not in startup
    assert "victoria-traces" not in startup
    assert "machine-auth" not in startup


def test_collector_queue_is_initialized_once_without_elevating_collector():
    services = _compose_config()["services"]
    queue_init = services["apm-collector-queue-init"]
    collector = services["apm-otel-collector"]

    assert queue_init["user"] == "0:0"
    assert queue_init["network_mode"] == "none"
    assert queue_init["read_only"] is True
    assert queue_init["cap_drop"] == ["ALL"]
    assert set(queue_init["cap_add"]) == {"CHOWN", "DAC_OVERRIDE", "FOWNER"}
    assert "chown" in " ".join(queue_init["command"])
    assert collector["user"] == "${APM_COLLECTOR_UID:-10001}:${APM_COLLECTOR_GID:-10001}"
    assert collector["depends_on"]["apm-collector-queue-init"]["condition"] == "service_completed_successfully"
    assert queue_init["volumes"] == ["apm_collector_queue:/var/lib/otelcol/queue"]

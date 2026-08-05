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


def test_reserved_attributes_are_removed_without_injecting_a_control_plane_source():
    config = _collector_config()
    expected_prefix = [
        "memory_limiter",
        "attributes/drop_reserved",
        "resource/drop_reserved",
        "transform/drop_nested_reserved",
        "transform/limits_and_route",
    ]

    for pipeline_name in ("traces/spanmetrics", "traces/sampled"):
        assert config["service"]["pipelines"][pipeline_name]["processors"][:5] == expected_prefix

    receiver = config["receivers"]["otlp"]["protocols"]
    assert receiver["grpc"]["include_metadata"] is True
    assert receiver["http"]["include_metadata"] is True
    assert "resource/trusted_ingest_source" not in config["processors"]


def test_span_metric_dimensions_and_queues_are_bounded():
    config = _collector_config()
    spanmetrics = config["connectors"]["spanmetrics"]
    configured_dimensions = {item["name"] for item in spanmetrics["dimensions"]}

    assert configured_dimensions == {
        "service.namespace",
        "service.instance.id",
        "deployment.environment",
        "service.version",
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


def test_edge_accepts_bounded_otlp_without_machine_token_auth():
    edge = EDGE_CONFIG.read_text()
    compose = COMPOSE_CONFIG.read_text()

    assert "location = /v1/traces" in edge
    assert "auth_request" not in edge
    assert "machine-auth" not in edge
    assert 'proxy_set_header Authorization ""' in edge
    assert 'proxy_set_header X-BK-Ingest-Source-Id ""' in edge
    assert "/telegraf/api" not in edge
    assert "/telegraf/api" not in compose


def test_edge_accepts_external_otlp_grpc_without_exposing_collector_ports():
    edge = EDGE_CONFIG.read_text()
    services = _compose_config()["services"]
    edge_service = services["apm-edge"]
    collector = services["apm-otel-collector"]

    assert "listen 8081;" in edge
    assert "http2 on;" in edge
    assert "location = /opentelemetry.proto.collector.trace.v1.TraceService/Export" in edge
    assert "auth_request" not in edge
    assert 'grpc_set_header Authorization ""' in edge
    assert 'grpc_set_header X-BK-Ingest-Source-Id ""' in edge
    assert "grpc_pass grpc://apm-otel-collector:4317" in edge
    assert any("${APM_OTLP_GRPC_PORT:-4317}:8081" in port for port in edge_service["ports"])
    assert "ports" not in collector
    assert set(collector["expose"]) >= {"4317", "4318"}


def test_collector_health_is_read_only_through_edge_without_host_port_mapping():
    edge = EDGE_CONFIG.read_text()
    collector = _compose_config()["services"]["apm-otel-collector"]

    assert "location = /healthz/collector" in edge
    assert "proxy_pass_request_body off;" in edge
    assert "proxy_pass http://apm-otel-collector:13133/;" in edge
    assert "ports" not in collector


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

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
REGIONAL_CONFIG = REPOSITORY_ROOT / "deploy/apm/otel/regional.yaml"
SYSTEM_CONFIG = REPOSITORY_ROOT / "deploy/apm/otel/system.yaml"
AGGREGATE_CONFIG = REPOSITORY_ROOT / "deploy/apm/otel/aggregate.yaml"
AGGREGATE_AUTH_CONFIG = REPOSITORY_ROOT / "deploy/apm/otel/aggregate-auth.yaml"
BUILDER_CONFIG = REPOSITORY_ROOT / "deploy/apm/collector/builder-config.yaml"
TRACE_GUARD = REPOSITORY_ROOT / "deploy/apm/collector/processor/traceguardprocessor/processor.go"
NATS_CONFIG = REPOSITORY_ROOT / "deploy/apm/nats/nats-server.conf"
COMPOSE_CONFIG = REPOSITORY_ROOT / "deploy/apm/compose.yaml"
ACCEPTANCE_GUIDE = REPOSITORY_ROOT / "deploy/apm/ACCEPTANCE.md"
CAPACITY_GUIDE = REPOSITORY_ROOT / "deploy/apm/CAPACITY.md"
APM_MAKEFILE = REPOSITORY_ROOT / "deploy/apm/Makefile"
PROXY_COMPOSE = REPOSITORY_ROOT / "agents/webhookd/infra/proxy/docker-compose.yaml"
PROXY_ENV_TEMPLATE = REPOSITORY_ROOT / "agents/webhookd/infra/proxy/env.template"
PROXY_NATS_TEMPLATE = REPOSITORY_ROOT / "agents/webhookd/infra/proxy/conf/nats/nats.conf.template"
SERVER_ENV_TEMPLATE = REPOSITORY_ROOT / "server/support-files/env/.env.apm.example"


def _yaml(path: Path):
    return yaml.safe_load(path.read_text())


def test_custom_distribution_contains_real_trace_transport_components():
    config = _yaml(BUILDER_CONFIG)

    assert config["dist"]["otelcol_version"] == "0.153.0"
    assert config["dist"]["version"] == "0.153.0-bklite.3"
    assert any("natsjetstreamexporter" in item["gomod"] for item in config["exporters"])
    assert any("prometheusremotewriteexporter v0.153.0" in item["gomod"] for item in config["exporters"])
    assert any("natsjetstreamreceiver" in item["gomod"] for item in config["receivers"])
    assert any("filestorage" in item["gomod"] for item in config["extensions"])
    assert any("basicauthextension v0.153.0" in item["gomod"] for item in config["extensions"])
    assert any("traceguardprocessor" in item["gomod"] for item in config["processors"])
    assert any("filterprocessor v0.153.0" in item["gomod"] for item in config["processors"])
    assert any("transformprocessor v0.153.0" in item["gomod"] for item in config["processors"])
    assert any("deltatocumulativeprocessor v0.153.0" in item["gomod"] for item in config["processors"])
    assert any("routingconnector v0.153.0" in item["gomod"] for item in config["connectors"])
    assert any("spanmetricsconnector v0.153.0" in item["gomod"] for item in config["connectors"])
    assert any("countconnector v0.153.0" in item["gomod"] for item in config["connectors"])


def test_regional_pipeline_cleans_and_stamps_before_persistent_nats_publish():
    config = _yaml(REGIONAL_CONFIG)
    pipeline = config["service"]["pipelines"]["traces"]

    assert pipeline["receivers"] == ["otlp"]
    assert pipeline["processors"] == [
        "memory_limiter",
        "trace_guard",
        "batch/traces",
    ]
    assert pipeline["exporters"] == ["nats_jetstream"]
    trace_guard = config["processors"]["trace_guard"]
    assert trace_guard["cloud_region_id"] == "${env:APM_CLOUD_REGION_ID}"
    assert trace_guard["max_resource_attributes"] == 64
    assert trace_guard["max_scope_attributes"] == 32
    assert trace_guard["max_span_attributes"] == 100
    assert trace_guard["max_event_attributes"] == 32
    assert trace_guard["max_link_attributes"] == 32
    assert trace_guard["max_attribute_runes"] == 4096
    exporter = config["exporters"]["nats_jetstream"]
    assert config["receivers"]["otlp"]["protocols"]["http"]["max_request_body_size"] == 8388608
    assert exporter["subject"] == "apm.traces.${env:APM_CLOUD_REGION_ID}"
    assert exporter["max_message_bytes"] == "${env:APM_NATS_MAX_MESSAGE_BYTES}"
    assert exporter["sending_queue"]["storage"] == "file_storage"
    assert exporter["sending_queue"]["sizer"] == "bytes"
    assert exporter["sending_queue"]["queue_size"] == "${env:APM_REGIONAL_QUEUE_MAX_BYTES}"
    assert exporter["retry_on_failure"]["max_elapsed_time"] == "0s"


def test_regional_pipeline_removes_reserved_sensitive_body_and_raw_url_attributes():
    guard = TRACE_GUARD.read_text()

    assert 'strings.HasPrefix(key, "bk.")' in guard
    assert "authorization|cookie|password" in guard
    for key in (
        "body",
        "http.request.body",
        "http.response.body",
        "request.body",
        "response.body",
        "url.full",
        "url.path",
        "url.query",
        "url.fragment",
        "http.url",
        "http.target",
    ):
        assert f'"{key}"' in guard
    assert "span.Events()" in guard
    assert "span.Links()" in guard
    assert 'PutStr("bk.cloud_region.id", cfg.CloudRegionID)' in guard


def test_system_pipeline_only_acks_after_direct_victoria_traces_export():
    config = _yaml(SYSTEM_CONFIG)
    rendered = SYSTEM_CONFIG.read_text()
    receiver = config["receivers"]["nats_jetstream"]
    exporter = config["exporters"]["otlp_http/victoria_traces"]
    pipeline = config["service"]["pipelines"]["traces"]

    assert receiver["filter_subject"] == "apm.traces.>"
    assert receiver["stream"] == "${env:APM_NATS_STREAM}"
    assert receiver["consumer"] == "${env:APM_NATS_CONSUMER}"
    assert receiver["pull_max_messages"] == "${env:APM_NATS_MAX_ACK_PENDING}"
    assert list(config["service"]["pipelines"]) == ["traces"]
    assert pipeline == {
        "receivers": ["nats_jetstream"],
        "processors": ["memory_limiter"],
        "exporters": ["otlp_http/victoria_traces"],
    }
    assert "connectors" not in config
    assert exporter["traces_endpoint"] == "${env:APM_VICTORIATRACES_OTLP_ENDPOINT}"
    assert exporter["sending_queue"]["enabled"] is False
    assert "batch/traces" not in config["processors"]
    assert "AGG_" not in rendered
    assert "APM_AGG_" not in rendered
    assert "span_metrics" not in rendered
    assert "prometheusremotewrite" not in rendered
    assert "VICTORIAMETRICS_HOST" not in rendered
    assert not (REPOSITORY_ROOT / "deploy/apm/otel/system-traces.yaml").exists()
    assert not (REPOSITORY_ROOT / "deploy/apm/otel/system-auth.yaml").exists()


def test_aggregate_pipeline_limits_memory_before_counting_and_splits_once():
    config = _yaml(AGGREGATE_CONFIG)
    rendered = AGGREGATE_CONFIG.read_text()
    pipelines = config["service"]["pipelines"]
    span_metrics = config["connectors"]["span_metrics"]
    remote_write = config["exporters"]["prometheusremotewrite/agg"]
    narrow = config["processors"]["transform/narrow_resource"]["trace_statements"][0]
    late_window = "span.end_time_unix_nano < UnixNano(Now()) - 300000000000"

    nats_pipelines = [name for name, item in pipelines.items() if "nats_jetstream" in item.get("receivers", [])]
    assert nats_pipelines == ["traces"]
    assert pipelines["traces"] == {
        "receivers": ["nats_jetstream"],
        "processors": ["memory_limiter", "filter/entry", "transform/narrow_resource"],
        "exporters": ["routing"],
    }
    assert pipelines["traces/aggregate"] == {
        "receivers": ["routing"],
        "exporters": ["span_metrics"],
    }
    assert pipelines["traces/late"] == {
        "receivers": ["routing"],
        "exporters": ["count/late"],
    }
    assert pipelines["metrics/apm_agg"] == {
        "receivers": ["span_metrics"],
        "exporters": ["prometheusremotewrite/agg"],
    }
    assert pipelines["metrics/apm_late"] == {
        "receivers": ["count/late"],
        "processors": ["batch/late", "transform/late_observed_at", "deltatocumulative"],
        "exporters": ["prometheusremotewrite/agg"],
    }
    for name, item in pipelines.items():
        processors = item.get("processors", [])
        if name == "traces":
            assert processors[0] == "memory_limiter"
        else:
            assert "memory_limiter" not in processors
    assert config["processors"]["filter/entry"]["error_mode"] == "ignore"
    assert "filter/drop_late" not in config["processors"]
    assert "filter/only_late" not in config["processors"]
    assert config["processors"]["transform/narrow_resource"]["error_mode"] == "ignore"
    routing = config["connectors"]["routing"]
    assert routing["default_pipelines"] == ["traces/aggregate"]
    assert routing["table"] == [
        {
            "context": "span",
            "condition": late_window,
            "pipelines": ["traces/late"],
        }
    ]
    assert "action" not in routing["table"][0]
    observed_at = config["processors"]["transform/late_observed_at"]
    assert observed_at["error_mode"] == "ignore"
    assert observed_at["metric_statements"][0]["statements"] == [
        "set(start_time, Now())",
        "set(time, Now())",
    ]
    assert config["connectors"]["count/late"]["spans"]["apm.aggregate.late_spans"]["conditions"] == [late_window]
    assert narrow["context"] == "resource"
    assert 'keep_keys(attributes, ["service.namespace", "service.name", "deployment.environment"])' in narrow["statements"]
    assert span_metrics["namespace"] == "apm"
    assert span_metrics["exclude_dimensions"] == ["span.kind", "collector.instance.id"]
    assert span_metrics["exemplars"]["enabled"] is False
    assert span_metrics["histogram"]["unit"] == "ms"
    assert span_metrics["histogram"]["explicit"]["buckets"] == [
        "5ms",
        "10ms",
        "25ms",
        "50ms",
        "100ms",
        "200ms",
        "300ms",
        "500ms",
        "800ms",
        "1000ms",
        "2000ms",
        "3000ms",
        "5000ms",
        "10000ms",
    ]
    assert span_metrics["aggregation_cardinality_limit"] == "${env:APM_AGG_CARDINALITY_LIMIT:-500}"
    assert span_metrics["series_expiration"] == "${env:APM_AGG_SERIES_EXPIRATION:-1h}"
    assert "metrics_expiration" not in span_metrics
    assert span_metrics["resource_metrics_cache_size"] == 1000
    assert span_metrics["resource_metrics_key_attributes"] == [
        "service.namespace",
        "service.name",
        "deployment.environment",
    ]
    assert span_metrics["add_resource_attributes"] is False
    assert remote_write["endpoint"] == "${env:AGG_VICTORIAMETRICS_WRITE_URL}"
    assert remote_write["external_labels"]["shard"] == "${env:APM_AGG_SHARD}"
    assert remote_write["resource_to_telemetry_conversion"]["enabled"] is False
    assert remote_write["target_info"]["enabled"] is False
    assert remote_write["disable_scope_info"] is True
    assert "auth" not in remote_write
    assert "basicauth" not in config["extensions"]
    assert "VICTORIAMETRICS_HOST" not in rendered
    assert "APM_VICTORIATRACES" not in rendered
    assert "300e9" not in rendered
    assert config["receivers"]["nats_jetstream"]["downstream_timeout"] == "20s"
    auth = _yaml(AGGREGATE_AUTH_CONFIG)
    assert auth["extensions"]["basicauth/agg"]["client_auth"]["username"] == "${env:AGG_VICTORIAMETRICS_USER}"
    assert auth["extensions"]["basicauth/agg"]["client_auth"]["password"] == "${env:AGG_VICTORIAMETRICS_PASSWORD}"
    assert auth["exporters"]["prometheusremotewrite/agg"]["auth"]["authenticator"] == "basicauth/agg"


def test_apm_compose_keeps_victoria_traces_and_a_separate_aggregate_store():
    compose = _yaml(COMPOSE_CONFIG)
    services = compose["services"]
    regional = services["apm-regional-collector"]
    traces = services["apm-victoria-traces"]
    system = services["apm-system-collector"]
    aggregate = services["apm-aggregate-metrics"]
    aggregate_collector = services["apm-aggregate-collector"]

    assert "apm-edge" not in services
    assert "apm-victoriametrics" not in services
    assert all("victoriametrics" not in name.lower() for name in services)
    assert any(":4318" in port for port in regional["ports"])
    assert any(":4317" in port for port in regional["ports"])
    assert any(":8888" in port for port in regional["ports"])
    assert any(":8888" in port for port in system["ports"])
    assert "-servicegraph.enableTask=true" in traces["command"]
    assert "-retentionPeriod=${APM_TRACE_RETENTION:-35d}" in traces["command"]
    assert regional["image"] == "${APM_COLLECTOR_IMAGE:-bklite/apm-otel-collector:0.153.0-bklite.3}"
    assert system["image"] == regional["image"]
    assert aggregate_collector["image"] == regional["image"]
    assert aggregate["ports"] == ["${APM_AGG_METRICS_BIND:-127.0.0.1}:${APM_AGG_METRICS_PORT:-18428}:8428"]
    assert "AGG_VICTORIAMETRICS_WRITE_URL" not in system["environment"]
    assert "APM_AGG_SHARD" not in system["environment"]
    assert "apm-aggregate-metrics" not in system["depends_on"]
    assert "apm-victoria-traces" not in aggregate_collector["depends_on"]
    assert aggregate_collector["depends_on"]["apm-aggregate-metrics"]["condition"] == "service_started"
    assert aggregate_collector["environment"]["APM_NATS_CONSUMER"] == "${APM_AGG_NATS_CONSUMER:-BKLITE_APM_AGGREGATE}"
    assert aggregate_collector["environment"]["AGG_VICTORIAMETRICS_WRITE_URL"] == (
        "${AGG_VICTORIAMETRICS_WRITE_URL:-http://apm-aggregate-metrics:8428/api/v1/write}"
    )
    assert aggregate_collector["environment"]["APM_AGG_SHARD"] == "${APM_AGG_SHARD:-local-aggregate}"
    assert aggregate_collector["environment"]["APM_AGG_CARDINALITY_LIMIT"] == "${APM_AGG_CARDINALITY_LIMIT:-500}"
    assert aggregate_collector["environment"]["APM_AGG_SERIES_EXPIRATION"] == "${APM_AGG_SERIES_EXPIRATION:-1h}"
    assert aggregate_collector["environment"]["APM_COLLECTOR_MEMORY_LIMIT_MIB"] == "${APM_AGG_COLLECTOR_MEMORY_LIMIT_MIB:-512}"
    assert aggregate_collector["environment"]["APM_COLLECTOR_MEMORY_SPIKE_MIB"] == "${APM_AGG_COLLECTOR_MEMORY_SPIKE_MIB:-128}"
    assert aggregate_collector["mem_limit"] == "${APM_AGG_COLLECTOR_CONTAINER_MEMORY_LIMIT:-640m}"
    rendered = COMPOSE_CONFIG.read_text()
    assert "tail_sampling" not in rendered
    assert "spanmetrics" not in rendered
    assert "/telegraf/api" not in rendered
    assert "VICTORIAMETRICS_HOST" not in rendered


def test_jetstream_and_durable_consumer_are_bounded_and_ack_explicit():
    compose = COMPOSE_CONFIG.read_text()

    assert '--subjects "apm.traces.>"' in compose
    assert "--max-bytes" in compose
    assert "--max-age" in compose
    assert '--max-msg-size "${APM_NATS_MAX_MESSAGE_BYTES:-8388608}"' in compose
    assert "--dupe-window" in compose
    assert "--ack explicit" in compose
    assert '--wait "${APM_NATS_ACK_WAIT:-60s}"' in compose
    assert "--max-deliver" in compose
    assert "--max-pending" in compose
    assert "stream info APM_TRACES" in compose
    assert "consumer info APM_TRACES BKLITE_APM_SYSTEM" in compose
    assert "consumer info APM_TRACES BKLITE_APM_AGGREGATE" in compose
    assert "--deliver all" in compose
    assert "--deliver new" in compose
    assert "${APM_AGG_NATS_ACK_WAIT:-30s}" in compose
    assert "${APM_AGG_NATS_MAX_DELIVER:-3}" in compose


def test_nats_accounts_constrain_regional_publish_and_system_ack_permissions():
    config = NATS_CONFIG.read_text()

    assert "publish: $NATS_REGION_PUBLISH_SUBJECT" in config
    assert 'subscribe: "_INBOX.>"' in config
    assert '"$JS.API.CONSUMER.MSG.NEXT.APM_TRACES.*"' in config
    assert '"$JS.ACK.APM_TRACES.>"' in config
    assert "max_payload: 8MB" in config
    assert "max_file_store: 1GB" in config


def test_data_plane_is_not_a_server_startup_dependency():
    startup = (REPOSITORY_ROOT / "server/support-files/release/startup.sh").read_text()

    assert "apm-regional-collector" not in startup
    assert "apm-system-collector" not in startup
    assert "apm-nats" not in startup
    assert "victoria-traces" not in startup


def test_regional_queue_is_initialized_once_without_elevating_collector():
    services = _yaml(COMPOSE_CONFIG)["services"]
    queue_init = services["apm-regional-queue-init"]
    collector = services["apm-regional-collector"]

    assert queue_init["user"] == "0:0"
    assert queue_init["network_mode"] == "none"
    assert queue_init["read_only"] is True
    assert queue_init["cap_drop"] == ["ALL"]
    assert set(queue_init["cap_add"]) == {"CHOWN", "DAC_OVERRIDE", "FOWNER"}
    assert "chown" in " ".join(queue_init["command"])
    assert collector["user"] == "${APM_COLLECTOR_UID:-65532}:${APM_COLLECTOR_GID:-65532}"
    assert collector["depends_on"]["apm-regional-queue-init"]["condition"] == "service_completed_successfully"
    assert queue_init["volumes"] == ["apm_regional_queue:/var/lib/otelcol/queue"]


def test_runtime_health_metrics_and_first_rollout_are_explicit():
    exporter = (REPOSITORY_ROOT / "deploy/apm/collector/exporter/natsjetstreamexporter/factory.go").read_text()
    receiver = (REPOSITORY_ROOT / "deploy/apm/collector/receiver/natsjetstreamreceiver/factory.go").read_text()
    acceptance = ACCEPTANCE_GUIDE.read_text()
    capacity = CAPACITY_GUIDE.read_text()

    assert "last_publish_ack_unixtime" in exporter
    assert "last_delivery_ack_unixtime" in receiver
    assert "APM 从未正式部署" in acceptance
    assert "首次上线没有旧 APM 数据面可恢复" in acceptance
    assert "不得临时引入其他接收代理" in acceptance
    assert "恢复旧 Edge" not in acceptance
    assert "regional_queue_bytes" in capacity
    assert "victoria_traces_bytes" in capacity
    assert "70%" in capacity and "85%" in capacity
    assert "每服务资源" in capacity
    assert "500 × 1000 × 18" in capacity
    assert "90000" not in capacity
    assert "9 万" not in capacity
    assert 'otel_metric_overflow="true"' in capacity
    assert "不是发布流水线设计文档" in acceptance
    readme = (REPOSITORY_ROOT / "deploy/apm/README.md").read_text()
    assert "契约夹具" in readme
    assert "也不替运维设计流水线" in readme
    assert "aggregate.yaml" in readme
    assert "aggregate-auth.yaml" in readme
    assert "BKLITE_APM_AGGREGATE" in readme
    assert "system-traces.yaml" not in readme
    assert "system-auth.yaml" not in readme
    assert "AGG_VICTORIAMETRICS_WRITE_URL" in readme
    assert "不回落" in readme
    assert "每服务资源" in readme
    assert "90000" not in readme
    operations = (REPOSITORY_ROOT / "docs/operations/aggregate-metrics-store.md").read_text()
    rollout = (REPOSITORY_ROOT / "docs/operations/apm-rum-query-performance-rollout.md").read_text()
    overflow_query = 'count(apm_calls_total{otel_metric_overflow="true"}) > 0'
    assert overflow_query in operations
    assert overflow_query in rollout
    assert "90000" not in operations
    assert "9 万" not in operations
    assert "90000" not in rollout
    assert "聚合写入可单独回退" in acceptance
    assert "system-traces.yaml" not in acceptance
    develop = (REPOSITORY_ROOT / "DEVELOP.md").read_text()
    assert "聚合写入可单独回退" in develop
    assert "不恢复 spanmetrics" not in develop
    assert "system-traces.yaml" not in develop


def test_apm_data_plane_has_makefile_lifecycle_and_server_runtime_contract():
    apm_makefile = APM_MAKEFILE.read_text()
    server_env = SERVER_ENV_TEMPLATE.read_text()

    for target in ("up:", "down:", "ps:", "logs:", "validate:", "test:", "contract:"):
        assert target in apm_makefile
    for key in (
        "APM_VICTORIATRACES_QUERY_ENDPOINT",
        "APM_REGIONAL_COLLECTOR_HEALTH_ENDPOINT",
        "APM_REGIONAL_COLLECTOR_METRICS_ENDPOINT",
        "APM_NATS_MONITOR_ENDPOINT",
        "APM_SYSTEM_COLLECTOR_HEALTH_ENDPOINT",
        "APM_VICTORIATRACES_HEALTH_ENDPOINT",
    ):
        assert f"{key}=" in server_env


def test_managed_region_proxy_exposes_otlp_http_to_the_regional_collector():
    services = _yaml(PROXY_COMPOSE)["services"]
    collector = services["apm-regional-collector"]
    queue_init = services["apm-regional-queue-init"]
    proxy_environment = PROXY_ENV_TEMPLATE.read_text()
    nats_template = PROXY_NATS_TEMPLATE.read_text()

    assert collector["image"] == "${DOCKER_IMAGE_APM_COLLECTOR}"
    assert "4318:4318" in collector["ports"]
    assert collector["environment"]["APM_CLOUD_REGION_ID"] == "${ZONE_ID}"
    assert collector["environment"]["APM_NATS_URL"] == ("tls://${APM_NATS_USERNAME}:${APM_NATS_PASSWORD}@nats:4222")
    assert collector["depends_on"]["apm-regional-queue-init"]["condition"] == "service_completed_successfully"
    assert queue_init["network_mode"] == "none"
    assert "DOCKER_IMAGE_APM_COLLECTOR=" in proxy_environment
    assert "APM_NATS_USERNAME=${APM_NATS_USERNAME}" in proxy_environment
    assert "APM_NATS_PASSWORD=${APM_NATS_PASSWORD}" in proxy_environment
    assert 'publish = ["apm.traces.${ZONE_ID}"]' in nats_template
    assert 'subscribe = ["_INBOX.>"]' in nats_template

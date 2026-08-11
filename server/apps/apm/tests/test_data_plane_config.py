from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
REGIONAL_CONFIG = REPOSITORY_ROOT / "deploy/apm/otel/regional.yaml"
SYSTEM_CONFIG = REPOSITORY_ROOT / "deploy/apm/otel/system.yaml"
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
    assert any("natsjetstreamexporter" in item["gomod"] for item in config["exporters"])
    assert any("natsjetstreamreceiver" in item["gomod"] for item in config["receivers"])
    assert any("filestorage" in item["gomod"] for item in config["extensions"])
    assert any("traceguardprocessor" in item["gomod"] for item in config["processors"])


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
    receiver = config["receivers"]["nats_jetstream"]
    exporter = config["exporters"]["otlphttp/victoria_traces"]
    pipeline = config["service"]["pipelines"]["traces"]

    assert receiver["filter_subject"] == "apm.traces.>"
    assert receiver["stream"] == "${env:APM_NATS_STREAM}"
    assert receiver["consumer"] == "${env:APM_NATS_CONSUMER}"
    assert receiver["pull_max_messages"] == "${env:APM_NATS_MAX_ACK_PENDING}"
    assert pipeline == {
        "receivers": ["nats_jetstream"],
        "processors": ["memory_limiter"],
        "exporters": ["otlphttp/victoria_traces"],
    }
    assert exporter["traces_endpoint"] == "${env:APM_VICTORIATRACES_OTLP_ENDPOINT}"
    assert exporter["sending_queue"]["enabled"] is False
    assert "batch" not in config["processors"]


def test_apm_compose_is_traces_only_without_edge_or_victoria_metrics():
    compose = _yaml(COMPOSE_CONFIG)
    services = compose["services"]
    regional = services["apm-regional-collector"]
    traces = services["apm-victoria-traces"]

    assert "apm-edge" not in services
    assert "apm-victoriametrics" not in services
    assert all("victoriametrics" not in name.lower() for name in services)
    assert any(":4318" in port for port in regional["ports"])
    assert any(":4317" in port for port in regional["ports"])
    assert any(":8888" in port for port in regional["ports"])
    assert any(":8888" in port for port in services["apm-system-collector"]["ports"])
    assert "-servicegraph.enableTask=true" in traces["command"]
    assert "-retentionPeriod=${APM_TRACE_RETENTION:-35d}" in traces["command"]
    rendered = COMPOSE_CONFIG.read_text()
    assert "tail_sampling" not in rendered
    assert "spanmetrics" not in rendered
    assert "/telegraf/api" not in rendered


def test_jetstream_and_durable_consumer_are_bounded_and_ack_explicit():
    compose = COMPOSE_CONFIG.read_text()

    assert '--subjects "apm.traces.>"' in compose
    assert "--max-bytes" in compose
    assert "--max-age" in compose
    assert "--max-msg-size" in compose
    assert "--dupe-window" in compose
    assert "--ack explicit" in compose
    assert '--wait "${APM_NATS_ACK_WAIT:-60s}"' in compose
    assert "--max-deliver" in compose
    assert "--max-pending" in compose
    assert "stream info APM_TRACES" in compose
    assert "consumer info APM_TRACES BKLITE_APM_SYSTEM" in compose


def test_nats_accounts_constrain_regional_publish_and_system_ack_permissions():
    config = NATS_CONFIG.read_text()

    assert "publish: $NATS_REGION_PUBLISH_SUBJECT" in config
    assert 'subscribe: "_INBOX.>"' in config
    assert '"$JS.API.CONSUMER.MSG.NEXT.APM_TRACES.*"' in config
    assert '"$JS.ACK.APM_TRACES.>"' in config
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
    assert "不是发布流水线设计文档" in acceptance
    readme = (REPOSITORY_ROOT / "deploy/apm/README.md").read_text()
    assert "契约夹具" in readme
    assert "也不替运维设计流水线" in readme


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
    assert collector["environment"]["APM_NATS_URL"] == (
        "tls://${APM_NATS_USERNAME}:${APM_NATS_PASSWORD}@nats:4222"
    )
    assert collector["depends_on"]["apm-regional-queue-init"]["condition"] == "service_completed_successfully"
    assert queue_init["network_mode"] == "none"
    assert "DOCKER_IMAGE_APM_COLLECTOR=" in proxy_environment
    assert "APM_NATS_USERNAME=${APM_NATS_USERNAME}" in proxy_environment
    assert "APM_NATS_PASSWORD=${APM_NATS_PASSWORD}" in proxy_environment
    assert 'publish = ["apm.traces.${ZONE_ID}"]' in nats_template
    assert 'subscribe = ["_INBOX.>"]' in nats_template

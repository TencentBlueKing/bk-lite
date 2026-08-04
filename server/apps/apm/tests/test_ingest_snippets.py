import pytest

from apps.apm.services import DjangoIntegrationConfigurationService
from apps.apm.services.contracts import IngestSnippetRequest


@pytest.mark.parametrize(
    ("runtime", "expected_identity"),
    [
        ("kubernetes", "${POD_UID:?POD_UID is required}"),
        ("docker", "${HOSTNAME:?container instance id is required}"),
        ("host", "${BK_INSTANCE_ID:?stable platform instance id is required}"),
        ("other", "${APM_INSTANCE_ID:-$(uuidgen)}"),
    ],
)
def test_snippet_uses_a_runtime_instance_identity_instead_of_a_shared_constant(runtime, expected_identity):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        IngestSnippetRequest(
            language="python",
            runtime=runtime,
            endpoint="https://apm.example.com/",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.2.3",
            environment="production",
        )
    )

    assert expected_identity in snippet.code
    assert "service.instance.id=${OTEL_SERVICE_INSTANCE_ID}" in snippet.code
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in snippet.environment
    assert "service.namespace=shop" in snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]
    assert "service.name=checkout" in snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]
    assert "service.version=1.2.3" in snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]
    assert snippet.environment["OTEL_EXPORTER_OTLP_ENDPOINT"] == "https://apm.example.com"


def test_snippet_uses_http_protocol_and_language_specific_launch_command():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        IngestSnippetRequest(
            language="java",
            runtime="kubernetes",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="",
            environment="production",
        )
    )

    assert snippet.environment["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"
    assert "opentelemetry-javaagent.jar" in snippet.code


@pytest.mark.parametrize(
    ("language", "expected_install", "expected_start"),
    [
        ("python", 'python -m pip install "opentelemetry-distro[otlp]"', "opentelemetry-instrument python app.py"),
        ("nodejs", "npm install --save @opentelemetry/auto-instrumentations-node", "node --require"),
        ("java", "curl --fail --silent --show-error --location", "java -javaagent:./opentelemetry-javaagent.jar"),
        ("go", "go get go.opentelemetry.io/otel", "Initialize the OpenTelemetry Go SDK"),
    ],
)
def test_host_snippet_installs_or_bootstraps_the_selected_sdk(language, expected_install, expected_start):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        IngestSnippetRequest(
            language=language,
            runtime="host",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
        )
    )

    assert expected_install in snippet.code
    assert expected_start in snippet.code
    assert "# 1. 安装探针" in snippet.code
    assert "# 2. 配置上报" in snippet.code
    assert "# 3. 启动应用" in snippet.code


def test_docker_snippet_uses_runtime_environment_injection_instead_of_host_exports():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        IngestSnippetRequest(
            language="nodejs",
            runtime="docker",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
        )
    )

    assert "docker run" in snippet.code
    assert "-e OTEL_EXPORTER_OTLP_ENDPOINT=https://apm.example.com" in snippet.code
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in snippet.code
    assert "NODE_OPTIONS=" in snippet.code
    assert "export OTEL_EXPORTER_OTLP_ENDPOINT" not in snippet.code

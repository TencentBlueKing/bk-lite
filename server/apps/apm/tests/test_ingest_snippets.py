import os
import shlex
import subprocess

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
    assert "service.instance.id=${OTEL_SERVICE_INSTANCE_ID}" in snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]
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


@pytest.mark.parametrize("runtime", ["host", "docker"])
def test_snippet_quotes_untrusted_values_as_posix_shell_literals(runtime):
    malicious = "checkout'\n$(printf injected) `printf injected` ; #"
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        IngestSnippetRequest(
            language="python",
            runtime=runtime,
            endpoint="https://apm.example.com",
            service_namespace=malicious,
            service_name=malicious,
            service_version=malicious,
            environment=malicious,
        )
    )

    assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0
    assert malicious in snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]

    if runtime == "host":
        instance_export = next(line for line in snippet.code.splitlines() if line.startswith("export OTEL_SERVICE_INSTANCE_ID="))
        resource_export = snippet.code.split("export OTEL_RESOURCE_ATTRIBUTES=", maxsplit=1)[1].split("\n\n# 3.", maxsplit=1)[0]
        script = f"{instance_export}\nexport OTEL_RESOURCE_ATTRIBUTES={resource_export}"
        script += '\nprintf %s "$OTEL_RESOURCE_ATTRIBUTES"'
        environment = {**os.environ, "BK_INSTANCE_ID": "host-instance"}
        expected_instance = "host-instance"
    else:
        tokens = shlex.split(snippet.code, comments=True)
        command_index = next(index for index in range(len(tokens) - 2) if tokens[index : index + 2] == ["sh", "-c"])
        script_token = next(token for token in tokens[command_index + 2 :] if token.strip())
        script = script_token.split("; exec ", maxsplit=1)[0]
        script += '; printf %s "$OTEL_RESOURCE_ATTRIBUTES"'
        environment = {**os.environ, "HOSTNAME": "container-instance"}
        expected_instance = "container-instance"

    rendered = subprocess.run(
        ["sh", "-c", script],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert rendered.stdout == (
        f"service.namespace={malicious},service.name={malicious},service.version={malicious},"
        f"deployment.environment={malicious},service.instance.id={expected_instance}"
    )

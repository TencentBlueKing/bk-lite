import os
import shlex
import subprocess
import uuid
from unittest.mock import Mock
from urllib.parse import unquote

import pytest
import yaml

from apps.apm.services import DjangoIntegrationConfigurationService
from apps.apm.services.contracts import IngestSnippetRequest
from apps.apm.services.integration_configuration import CloudRegionConfigurationError

_PROBE_DOWNLOAD_URLS = {
    "java": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-javaagent.jar",
    "python": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-python-wheels.tar.gz",
    "nodejs": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-js-auto.tgz",
    "go": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-go-sdk.zip",
}


def _request(**kwargs) -> IngestSnippetRequest:
    language = kwargs["language"]
    kwargs.setdefault("probe_download_url", _PROBE_DOWNLOAD_URLS[language])
    return IngestSnippetRequest(**kwargs)


def _configuration_script(code: str) -> str:
    section = code.split("# 2. 配置上报", maxsplit=1)[1].split("# 3. 启动应用", maxsplit=1)[0]
    return section.split("\n", maxsplit=1)[1]


def test_region_resolution_fails_closed_without_organization_scope():
    node_mgmt = Mock()
    node_mgmt.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]

    with pytest.raises(CloudRegionConfigurationError) as exc_info:
        DjangoIntegrationConfigurationService().resolve_region(node_mgmt, 7, organization_ids=[])

    assert exc_info.value.code == "cloud_region_receiver_unavailable"
    node_mgmt.cloud_region_list.assert_not_called()
    node_mgmt.get_cloud_region_proxy_address.assert_not_called()


@pytest.mark.parametrize("runtime", ["kubernetes", "docker", "host", "other"])
def test_snippet_uses_a_runtime_instance_identity_instead_of_a_shared_constant(runtime):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="python",
            runtime=runtime,
            endpoint="https://apm.example.com/",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.2.3",
            environment="production",
        )
    )

    assert "service.instance.id=${OTEL_SERVICE_INSTANCE_ID}" in snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]
    assert "BK_INSTANCE_ID" not in snippet.code
    if runtime == "kubernetes":
        assert "fieldPath: metadata.uid" in snippet.code
    else:
        assert "APM_INSTANCE_ID" in snippet.code
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in snippet.environment
    assert "service.namespace=shop" in snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]
    assert "service.name=checkout" in snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]
    assert "service.version=1.2.3" in snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]
    assert snippet.environment["OTEL_EXPORTER_OTLP_ENDPOINT"] == "https://apm.example.com"


def test_snippet_uses_http_protocol_and_language_specific_launch_command():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
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


def test_host_snippet_generates_a_valid_instance_id_without_platform_variables():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="nodejs",
            runtime="host",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.2.3",
            environment="production",
        )
    )
    configuration = _configuration_script(snippet.code)
    generated = subprocess.run(
        ["sh", "-c", f'{configuration}\nprintf %s "$OTEL_SERVICE_INSTANCE_ID"'],
        env={key: value for key, value in os.environ.items() if key != "APM_INSTANCE_ID"},
        text=True,
        capture_output=True,
        check=True,
    ).stdout

    assert uuid.UUID(generated).version == 4


def test_host_snippet_fails_closed_when_uuid_sources_are_unavailable(tmp_path):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="nodejs",
            runtime="host",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.2.3",
            environment="production",
        )
    )
    configuration = _configuration_script(snippet.code)

    failed = subprocess.run(
        ["/bin/sh", "-c", configuration],
        env={"PATH": str(tmp_path)},
        text=True,
        capture_output=True,
    )

    assert failed.returncode != 0
    assert "service.instance.id" in failed.stderr


@pytest.mark.parametrize(
    ("runtime", "runtime_environment", "expected"),
    [
        ("host", {"APM_INSTANCE_ID": "host-replica-a"}, "host-replica-a"),
        ("other", {"APM_INSTANCE_ID": "custom-runtime-a"}, "custom-runtime-a"),
    ],
)
def test_non_docker_runtime_profile_selects_and_validates_one_process_identity(runtime, runtime_environment, expected):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="python",
            runtime=runtime,
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
        )
    )
    configuration = _configuration_script(snippet.code)

    rendered = subprocess.run(
        ["sh", "-c", f'{configuration}\nprintf %s "$OTEL_SERVICE_INSTANCE_ID"'],
        env={**os.environ, **runtime_environment},
        text=True,
        capture_output=True,
        check=True,
    )

    assert rendered.stdout == expected


@pytest.mark.parametrize("invalid", ["", "shared,replica", "line\nbreak", "x" * 513])
def test_explicit_instance_identity_fails_closed_outside_the_safe_boundary(invalid):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="python",
            runtime="other",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
        )
    )
    configuration = _configuration_script(snippet.code)

    failed = subprocess.run(
        ["sh", "-c", configuration],
        env={**os.environ, "APM_INSTANCE_ID": invalid},
        text=True,
        capture_output=True,
    )

    assert failed.returncode != 0
    assert "service.instance.id" in failed.stderr


@pytest.mark.parametrize(
    ("language", "expected_install", "expected_start"),
    [
        ("python", '--no-index --find-links otel-python-wheels "opentelemetry-distro[otlp]"', "opentelemetry-instrument python app.py"),
        ("nodejs", "npm install --offline --save ./opentelemetry-js-auto.tgz", "node --require"),
        ("java", "curl --fail --silent --show-error --location", "java -javaagent:./opentelemetry-javaagent.jar"),
        ("go", 'export GOPROXY="file://$(pwd)/.otel-go-sdk"', "Go 无通用零代码探针"),
    ],
)
def test_host_snippet_installs_or_bootstraps_the_selected_sdk(language, expected_install, expected_start):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
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
    assert _PROBE_DOWNLOAD_URLS[language] in snippet.code
    assert "pypi.org" not in snippet.code
    assert "npmjs" not in snippet.code
    assert "github.com" not in snippet.code
    assert "go get " not in snippet.code
    assert "# 1. 安装探针" in snippet.code
    assert "# 2. 配置上报" in snippet.code
    assert "# 3. 启动应用" in snippet.code


@pytest.mark.parametrize("language", ["python", "nodejs", "java", "go"])
@pytest.mark.parametrize("runtime", ["host", "docker"])
def test_snippet_downloads_probe_from_the_system_address_instead_of_the_public_internet(language, runtime):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language=language,
            runtime=runtime,
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
        )
    )

    assert _PROBE_DOWNLOAD_URLS[language] in snippet.code
    assert "github.com" not in snippet.code
    assert "pypi.org" not in snippet.code
    assert "npmjs" not in snippet.code
    assert "go get " not in snippet.code
    assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0


@pytest.mark.parametrize("language", ["python", "nodejs", "java", "go"])
@pytest.mark.parametrize("runtime", ["host", "docker", "kubernetes", "other"])
def test_snippet_fails_closed_without_a_resolved_system_download_address(language, runtime):
    with pytest.raises(ValueError, match="probe_download_url"):
        DjangoIntegrationConfigurationService().render_snippet(
            IngestSnippetRequest(
                language=language,
                runtime=runtime,
                endpoint="https://apm.example.com",
                service_namespace="shop",
                service_name="checkout",
                service_version="1.0",
                environment="production",
            )
        )


@pytest.mark.parametrize(
    ("language", "artifact_name"),
    [
        ("java", "opentelemetry-javaagent.jar"),
        ("python", "opentelemetry-python-wheels.tar.gz"),
        ("nodejs", "opentelemetry-js-auto.tgz"),
        ("go", "opentelemetry-go-sdk.zip"),
    ],
)
def test_resolve_region_builds_the_probe_download_url_from_node_server_url(language, artifact_name):
    node_mgmt = Mock()
    node_mgmt.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]
    node_mgmt.get_cloud_region_proxy_address.return_value = "apm-east.example.com"
    node_mgmt.get_cloud_region_public_config.return_value = {"NODE_SERVER_URL": "http://10.10.10.1:8011"}

    endpoints = DjangoIntegrationConfigurationService().resolve_region(
        node_mgmt,
        7,
        organization_ids=[10],
        include_probe_download=True,
        probe_artifact_name=artifact_name,
    )

    assert endpoints.http_endpoint == "http://apm-east.example.com:4318"
    assert endpoints.probe_download_url == f"http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/{artifact_name}"
    node_mgmt.get_cloud_region_public_config.assert_called_once_with(7)


def test_resolve_region_skips_env_config_when_probe_download_is_not_needed():
    node_mgmt = Mock()
    node_mgmt.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]
    node_mgmt.get_cloud_region_proxy_address.return_value = "apm-east.example.com"

    endpoints = DjangoIntegrationConfigurationService().resolve_region(node_mgmt, 7, organization_ids=[10])

    assert endpoints.probe_download_url == ""
    node_mgmt.get_cloud_region_public_config.assert_not_called()


@pytest.mark.parametrize("env_config", [{}, {"NODE_SERVER_URL": "ftp://10.10.10.1:8011"}, "not-a-dict"])
def test_resolve_region_fails_closed_when_the_probe_download_address_is_unavailable(env_config):
    node_mgmt = Mock()
    node_mgmt.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]
    node_mgmt.get_cloud_region_proxy_address.return_value = "apm-east.example.com"
    node_mgmt.get_cloud_region_public_config.return_value = env_config

    with pytest.raises(CloudRegionConfigurationError) as exc_info:
        DjangoIntegrationConfigurationService().resolve_region(
            node_mgmt,
            7,
            organization_ids=[10],
            include_probe_download=True,
            probe_artifact_name="opentelemetry-javaagent.jar",
        )

    assert exc_info.value.code == "probe_download_unavailable"


def test_docker_snippet_uses_runtime_environment_injection_instead_of_host_exports():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
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


def test_kubernetes_snippet_uses_downward_api_pod_uid_and_standard_otel_environment():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="python",
            runtime="kubernetes",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
        )
    )

    manifest = yaml.safe_load(snippet.code)
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    environment = {item["name"]: item for item in container["env"]}

    assert container["name"] == "YOUR_CONTAINER_NAME"
    assert environment["POD_UID"]["valueFrom"]["fieldRef"] == {
        "apiVersion": "v1",
        "fieldPath": "metadata.uid",
    }
    assert environment["OTEL_SERVICE_INSTANCE_ID"]["value"] == "$(POD_UID)"
    assert environment["OTEL_EXPORTER_OTLP_ENDPOINT"]["value"] == "https://apm.example.com"
    assert "service.instance.id=$(OTEL_SERVICE_INSTANCE_ID)" in environment["OTEL_RESOURCE_ATTRIBUTES"]["value"]
    assert "${POD_UID" not in snippet.code
    assert _PROBE_DOWNLOAD_URLS["python"] in snippet.code
    assert "pypi.org" not in snippet.code


def test_go_snippet_is_an_explicit_manual_sdk_guide_with_complete_provider_setup():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="go",
            runtime="host",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
        )
    )

    assert "Go 无通用零代码探针" in snippet.code
    assert _PROBE_DOWNLOAD_URLS["go"] in snippet.code
    assert "go get " not in snippet.code
    assert "telemetry/otel.go.example" in snippet.code
    assert "func NewTracerProvider(ctx context.Context) (*sdktrace.TracerProvider, error)" in snippet.code
    assert "otlptracehttp.New(ctx)" in snippet.code
    assert "resource.WithFromEnv()" in snippet.code
    assert "sdktrace.WithBatcher(exporter)" in snippet.code
    assert "defer tracerProvider.Shutdown" in snippet.code
    assert "Initialize the OpenTelemetry Go SDK" not in snippet.code
    assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0


@pytest.mark.parametrize("runtime", ["host", "docker"])
def test_snippet_separately_quotes_shell_literals_and_encodes_otel_resource_values(runtime):
    malicious = "checkout%'\n,forged.key=forged $(printf injected) `printf injected` ; # 界"
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
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
    resource_dto = snippet.environment["OTEL_RESOURCE_ATTRIBUTES"]
    assert "forged.key=forged" not in resource_dto.split(",")
    assert "%25" in resource_dto
    assert "%2Cforged.key%3Dforged" in resource_dto
    assert "%0A" in resource_dto
    assert "%E7%95%8C" in resource_dto

    if runtime == "host":
        configuration = _configuration_script(snippet.code)
        script = f'{configuration}\nprintf %s "$OTEL_RESOURCE_ATTRIBUTES"'
        environment = {**os.environ, "APM_INSTANCE_ID": "host-instance"}
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
    pairs = dict(item.split("=", maxsplit=1) for item in rendered.stdout.split(","))
    assert {key: unquote(value) for key, value in pairs.items()} == {
        "service.namespace": malicious,
        "service.name": malicious,
        "service.version": malicious,
        "deployment.environment": malicious,
        "service.instance.id": expected_instance,
    }

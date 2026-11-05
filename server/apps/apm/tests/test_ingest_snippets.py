import hashlib
import os
import re
import shlex
import subprocess
import uuid
from unittest.mock import Mock
from urllib.parse import unquote

import pytest
import yaml

from apps.apm.serializers.control_plane import IngestSnippetSerializer
from apps.apm.services import DjangoIntegrationConfigurationService
from apps.apm.services.contracts import IngestSnippetRequest
from apps.apm.services.integration_configuration import CloudRegionConfigurationError
from apps.apm.services.probe_artifacts import JAVA_AGENT_ARTIFACT_NAME, ProbeArtifactNotFound, ProbeSelectionError, get_probe_artifact_sha256

_PROBE_DOWNLOAD_URLS = {
    "java": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-javaagent.jar",
    "python": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-python-wheels.tar.gz",
    "nodejs": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-js-auto.tgz",
    "go": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-go-sdk.zip",
    "dotnet": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-dotnet-auto-linux-glibc-x64.zip",
    "php": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-php-auto-linux-glibc-x64.tar.gz",
    "obi": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-ebpf-obi-linux-amd64.tar.gz",
    "ruby": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-ruby-sdk.tar.gz",
    "cpp": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-cpp-sdk.tar.gz",
    "erlang": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-erlang-sdk.tar.gz",
    "swift": "http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/opentelemetry-swift-sdk.tar.gz",
}
_PROBE_BYTES = b"probe-bytes"
_PROBE_SHA256 = hashlib.sha256(_PROBE_BYTES).hexdigest()


@pytest.fixture(autouse=True)
def _stub_probe_artifact_sha256(monkeypatch):
    monkeypatch.setattr(
        "apps.apm.services.integration_configuration.get_probe_artifact_sha256",
        lambda artifact_name: _PROBE_SHA256,
        raising=False,
    )


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
    assert "OTEL_TRACES_SAMPLER" not in snippet.environment
    assert "OTEL_TRACES_SAMPLER" not in snippet.code


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


def _snippet_payload(**overrides):
    payload = {
        "application_id": "shop",
        "cloud_region_id": 7,
        "language": "python",
        "runtime": "host",
        "service_name": "checkout",
        "environment": "production",
    }
    payload.update(overrides)
    return payload


def test_ingest_snippet_serializer_defaults_sample_rate_to_full():
    serializer = IngestSnippetSerializer(data=_snippet_payload())

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["sample_rate"] == 100


@pytest.mark.parametrize("sample_rate", [0, 101])
def test_ingest_snippet_serializer_rejects_sample_rate_outside_percent(sample_rate):
    serializer = IngestSnippetSerializer(data=_snippet_payload(sample_rate=sample_rate))

    assert serializer.is_valid() is False
    assert "sample_rate" in serializer.errors


@pytest.mark.parametrize("runtime", ["kubernetes", "docker", "host"])
def test_reduced_sample_rate_writes_parentbased_traceidratio(runtime):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="python",
            runtime=runtime,
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
            sample_rate=10,
        )
    )

    assert snippet.environment["OTEL_TRACES_SAMPLER"] == "parentbased_traceidratio"
    assert snippet.environment["OTEL_TRACES_SAMPLER_ARG"] == "0.1"
    assert "OTEL_TRACES_SAMPLER" in snippet.code
    assert "0.1" in snippet.code


def test_one_percent_sample_rate_uses_two_decimal_ratio():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="java",
            runtime="host",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
            sample_rate=1,
        )
    )

    assert snippet.environment["OTEL_TRACES_SAMPLER_ARG"] == "0.01"


def test_invalid_sample_rate_is_rejected_before_rendering():
    with pytest.raises(ValueError, match="sample_rate"):
        DjangoIntegrationConfigurationService().render_snippet(
            _request(
                language="python",
                runtime="host",
                endpoint="https://apm.example.com",
                service_namespace="shop",
                service_name="checkout",
                service_version="1.0",
                environment="production",
                sample_rate=0,
            )
        )


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
        ("java", "curl --fail --silent --show-error --location --insecure", "java -javaagent:./opentelemetry-javaagent.jar"),
        ("go", 'export GOPROXY="file://$(pwd)/.otel-go-sdk"', "Go 无通用零代码探针"),
        ("dotnet", '. "$OTEL_DOTNET_AUTO_HOME/instrument.sh"', "dotnet App.dll"),
        ("php", "COMPOSER_DISABLE_NETWORK=1", "php app.php"),
        ("ruby", "gem install --local --no-document --ignore-dependencies", "opentelemetry-instrumentation-rack"),
        ("cpp", "opentelemetry-cpp-sdk.tar.gz", "opentelemetry-cpp v1.30.0"),
        ("erlang", "opentelemetry-erlang-sdk.tar.gz", "opentelemetry 1.7.0"),
        ("swift", "opentelemetry-swift-sdk.tar.gz", "opentelemetry-swift 2.6.0"),
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
    assert "https://github.com" not in snippet.code
    assert "packagist.org" not in snippet.code
    assert "go get " not in snippet.code
    assert "nuget.org" not in snippet.code
    assert "rubygems.org" not in snippet.code
    assert "hex.pm" not in snippet.code
    assert "# 1. 安装探针" in snippet.code
    assert "# 2. 配置上报" in snippet.code
    assert "# 3. 启动应用" in snippet.code


@pytest.mark.parametrize("language", ["python", "nodejs", "java", "go", "dotnet", "php", "ruby", "cpp", "erlang", "swift"])
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
    assert "--insecure" in snippet.code
    assert "https://github.com" not in snippet.code
    assert "pypi.org" not in snippet.code
    assert "npmjs" not in snippet.code
    assert "go get " not in snippet.code
    assert "nuget.org" not in snippet.code
    assert "rubygems.org" not in snippet.code
    assert "hex.pm" not in snippet.code
    assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0


def _install_section(code: str, runtime: str) -> str:
    marker = "# 1. 安装探针（将以下命令写入应用 Dockerfile）" if runtime == "docker" else "# 1. 安装探针"
    return code.split(marker, maxsplit=1)[1].split("# 2. 配置上报", maxsplit=1)[0]


def _checksum_command(code: str, runtime: str) -> str:
    match = re.search(
        r"if command -v sha256sum >/dev/null 2>&1; then.*?shasum -a 256 -c -; fi",
        _install_section(code, runtime),
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(0)


@pytest.mark.parametrize("language", ["python", "nodejs", "java", "go", "dotnet", "php", "ruby", "cpp", "erlang", "swift"])
@pytest.mark.parametrize("runtime", ["host", "docker"])
def test_snippet_verifies_server_sha256_after_each_probe_download(language, runtime, tmp_path):
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
    install = _install_section(snippet.code, runtime)
    curl_at = install.find("curl --fail")
    digest_at = install.find(_PROBE_SHA256)

    assert "--insecure" in snippet.code
    assert len(_PROBE_SHA256) == 64
    assert curl_at != -1
    assert digest_at > curl_at
    assert "sha256sum -c -" in install
    assert "shasum -a 256 -c -" in install

    artifact = tmp_path / "probe.bin"
    verify = re.sub(
        r"printf '%s  %s\\n' " + re.escape(shlex.quote(_PROBE_SHA256)) + r" \S+",
        f"printf '%s  %s\\n' {shlex.quote(_PROBE_SHA256)} {shlex.quote(str(artifact))}",
        _checksum_command(snippet.code, runtime),
    )
    artifact.write_bytes(b"tampered")
    failed = subprocess.run(["sh", "-c", verify], text=True, capture_output=True)
    assert failed.returncode != 0

    artifact.write_bytes(_PROBE_BYTES)
    passed = subprocess.run(["sh", "-c", verify], text=True, capture_output=True)
    assert passed.returncode == 0
    assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0


def test_host_snippet_fails_closed_when_probe_artifact_sha256_is_unavailable(monkeypatch):
    def missing(artifact_name):
        raise ProbeArtifactNotFound(artifact_name)

    monkeypatch.setattr(
        "apps.apm.services.integration_configuration.get_probe_artifact_sha256",
        missing,
        raising=False,
    )

    with pytest.raises(ProbeArtifactNotFound):
        DjangoIntegrationConfigurationService().render_snippet(
            _request(
                language="java",
                runtime="host",
                endpoint="https://apm.example.com",
                service_namespace="shop",
                service_name="checkout",
                service_version="1.0",
                environment="production",
            )
        )


def test_host_snippet_fails_closed_instead_of_embedding_an_empty_probe_sha256(monkeypatch):
    monkeypatch.setattr(
        "apps.apm.services.integration_configuration.get_probe_artifact_sha256",
        lambda artifact_name: "",
        raising=False,
    )

    with pytest.raises((ProbeArtifactNotFound, ValueError)):
        DjangoIntegrationConfigurationService().render_snippet(
            _request(
                language="python",
                runtime="docker",
                endpoint="https://apm.example.com",
                service_namespace="shop",
                service_name="checkout",
                service_version="1.0",
                environment="production",
            )
        )


@pytest.mark.parametrize("language", ["python", "nodejs", "java", "go", "dotnet", "php", "ruby", "cpp", "erlang", "swift"])
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
        ("dotnet", "opentelemetry-dotnet-auto-linux-glibc-x64.zip"),
        ("php", "opentelemetry-php-auto-linux-glibc-x64.tar.gz"),
        ("dotnet-windows", "opentelemetry-dotnet-auto-windows.zip"),
        ("obi", "opentelemetry-ebpf-obi-linux-amd64.tar.gz"),
        ("ruby", "opentelemetry-ruby-sdk.tar.gz"),
        ("cpp", "opentelemetry-cpp-sdk.tar.gz"),
        ("erlang", "opentelemetry-erlang-sdk.tar.gz"),
        ("swift", "opentelemetry-swift-sdk.tar.gz"),
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
    assert "https://github.com" not in snippet.code
    assert "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp" in snippet.code
    assert "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc" in snippet.code
    assert "go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin" in snippet.code
    assert "go.opentelemetry.io/contrib/instrumentation/github.com/labstack/echo/otelecho" in snippet.code
    assert snippet.code.count("go mod download") == 1
    assert "telemetry/otel.go.example" in snippet.code
    assert "func NewTracerProvider(ctx context.Context) (*sdktrace.TracerProvider, error)" in snippet.code
    assert "otlptracehttp.New(ctx)" in snippet.code
    assert "resource.WithFromEnv()" in snippet.code
    assert "sdktrace.WithBatcher(exporter)" in snippet.code
    assert "defer tracerProvider.Shutdown" in snippet.code
    assert "Initialize the OpenTelemetry Go SDK" not in snippet.code
    assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0


@pytest.mark.parametrize("runtime", ["host", "docker", "kubernetes"])
def test_dotnet_snippet_uses_the_glibc_x64_auto_probe_and_keeps_traces_only(runtime):
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="dotnet",
            runtime=runtime,
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
        )
    )

    assert _PROBE_DOWNLOAD_URLS["dotnet"] in snippet.code
    assert "仅支持 Linux x86_64 glibc（Ubuntu / Debian / CentOS 及同类容器镜像）；不支持 Alpine、ARM64、Windows" in snippet.code
    assert "CORECLR_PROFILER_PATH" in snippet.code
    assert "linux-x64/OpenTelemetry.AutoInstrumentation.Native.so" in snippet.code
    assert "DOTNET_ADDITIONAL_DEPS" in snippet.code
    assert "DOTNET_SHARED_STORE" in snippet.code
    assert "dotnet App.dll" in snippet.code
    assert "OTEL_METRICS_EXPORTER" in snippet.code
    assert "OTEL_LOGS_EXPORTER" in snippet.code
    assert snippet.environment["OTEL_METRICS_EXPORTER"] == "none"
    assert snippet.environment["OTEL_LOGS_EXPORTER"] == "none"
    assert "github.com" not in snippet.code
    assert "nuget.org" not in snippet.code
    assert "rubygems.org" not in snippet.code
    assert "hex.pm" not in snippet.code
    assert "otel-dotnet-auto-install.sh" not in snippet.code
    if runtime == "host":
        assert '. "$OTEL_DOTNET_AUTO_HOME/instrument.sh"' in snippet.code
        assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0
    if runtime == "docker":
        assert "/otel-dotnet-auto" in snippet.code
        assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0
    if runtime == "kubernetes":
        manifest = yaml.safe_load(snippet.code)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        environment = {item["name"]: item["value"] for item in container["env"] if "value" in item}
        assert environment["CORECLR_PROFILER_PATH"] == ("/otel-dotnet-auto/linux-x64/OpenTelemetry.AutoInstrumentation.Native.so")
        assert environment["DOTNET_ADDITIONAL_DEPS"] == "/otel-dotnet-auto/AdditionalDeps"
        assert environment["DOTNET_SHARED_STORE"] == "/otel-dotnet-auto/store"
        assert environment["OTEL_METRICS_EXPORTER"] == "none"
        assert environment["OTEL_LOGS_EXPORTER"] == "none"


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


@pytest.mark.parametrize("language", ["python", "nodejs", "java", "go", "dotnet", "php", "ruby", "cpp", "erlang", "swift"])
@pytest.mark.parametrize("runtime", ["host", "docker"])
def test_host_and_docker_snippets_require_probe_hash_for_any_language(monkeypatch, language, runtime):
    def missing(artifact_name):
        raise ProbeArtifactNotFound(artifact_name)

    monkeypatch.setattr(
        "apps.apm.services.integration_configuration.get_probe_artifact_sha256",
        missing,
        raising=False,
    )

    with pytest.raises(ProbeArtifactNotFound):
        DjangoIntegrationConfigurationService().render_snippet(
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


@pytest.mark.parametrize("language", ["python", "nodejs", "java", "go", "dotnet", "php", "ruby", "cpp", "erlang", "swift"])
def test_kubernetes_snippets_do_not_hash_probe_artifacts(monkeypatch, language):
    def missing(artifact_name):
        raise ProbeArtifactNotFound(artifact_name)

    monkeypatch.setattr(
        "apps.apm.services.integration_configuration.get_probe_artifact_sha256",
        missing,
        raising=False,
    )

    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language=language,
            runtime="kubernetes",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
        )
    )

    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in snippet.code


def test_probe_artifact_sha256_streams_allowlisted_object_and_caches(monkeypatch):
    from apps.apm.services import probe_artifacts as probe_artifacts_module

    probe_artifacts_module._PROBE_ARTIFACT_SHA256_CACHE.clear()
    calls = []

    def fake_stream(artifact_name):
        calls.append(artifact_name)
        return iter([b"ab", b"cd"]), artifact_name

    monkeypatch.setattr(probe_artifacts_module, "open_probe_artifact_stream", fake_stream)

    digest = get_probe_artifact_sha256(JAVA_AGENT_ARTIFACT_NAME)

    assert digest == hashlib.sha256(b"abcd").hexdigest()
    assert get_probe_artifact_sha256(JAVA_AGENT_ARTIFACT_NAME) == digest
    assert calls == [JAVA_AGENT_ARTIFACT_NAME]


def test_probe_artifact_sha256_rejects_names_outside_the_allowlist():
    with pytest.raises(ProbeArtifactNotFound):
        get_probe_artifact_sha256("etc-passwd")


def test_probe_artifact_sha256_does_not_cache_missing_artifacts(monkeypatch):
    from apps.apm.services import probe_artifacts as probe_artifacts_module

    probe_artifacts_module._PROBE_ARTIFACT_SHA256_CACHE.clear()

    def missing(artifact_name):
        raise ProbeArtifactNotFound(artifact_name)

    monkeypatch.setattr(probe_artifacts_module, "open_probe_artifact_stream", missing)

    with pytest.raises(ProbeArtifactNotFound):
        get_probe_artifact_sha256(JAVA_AGENT_ARTIFACT_NAME)

    assert JAVA_AGENT_ARTIFACT_NAME not in probe_artifacts_module._PROBE_ARTIFACT_SHA256_CACHE


def test_upload_probe_artifact_invalidates_sha256_cache(monkeypatch, tmp_path):
    from apps.apm.services import probe_artifacts as probe_artifacts_module
    from apps.apm.services.probe_artifacts import upload_probe_artifact

    probe_artifacts_module._PROBE_ARTIFACT_SHA256_CACHE[JAVA_AGENT_ARTIFACT_NAME] = "a" * 64

    class FakeJetStream:
        async def connect(self):
            pass

        async def put(self, key, data, description=None):
            data.read()

        async def close(self):
            pass

    monkeypatch.setattr(probe_artifacts_module, "JetStreamService", FakeJetStream)
    file_path = tmp_path / "opentelemetry-javaagent.jar"
    file_path.write_bytes(b"jar-bytes")

    upload_probe_artifact(JAVA_AGENT_ARTIFACT_NAME, str(file_path))

    assert JAVA_AGENT_ARTIFACT_NAME not in probe_artifacts_module._PROBE_ARTIFACT_SHA256_CACHE


def test_php_snippet_pins_nts_packages_and_stays_offline():
    for runtime in ("host", "docker", "kubernetes", "other"):
        snippet = DjangoIntegrationConfigurationService().render_snippet(
            _request(
                language="php",
                runtime=runtime,
                endpoint="https://apm.example.com",
                service_namespace="shop",
                service_name="checkout",
                service_version="1.0",
                environment="production",
            )
        )

        assert "PHP 8.1" in snippet.code or "8.1|8.2|8.3|8.4" in snippet.code
        assert "NTS" in snippet.code or "ZTS" in snippet.code
        assert "open-telemetry/sdk:1.15.0" in snippet.code
        assert "open-telemetry/opentelemetry-auto-slim:1.5.1" in snippet.code
        assert "open-telemetry/opentelemetry-auto-pdo:0.6.0" in snippet.code
        assert "open-telemetry/opentelemetry-auto-mysqli:0.5.0" in snippet.code
        assert "packagist.org" not in snippet.code
        assert "pecl" not in snippet.code
        assert "https://github.com" not in snippet.code
        assert snippet.environment["OTEL_METRICS_EXPORTER"] == "none"
        assert snippet.environment["OTEL_PHP_AUTOLOAD_ENABLED"] == "true"
        if runtime == "kubernetes":
            manifest = yaml.safe_load(snippet.code)
            assert manifest["spec"]["template"]["spec"]["containers"][0]["name"] == "YOUR_CONTAINER_NAME"
            assert "sha256sum" not in snippet.code
        else:
            assert "COMPOSER_DISABLE_NETWORK=1" in snippet.code
            assert "8.2|8.3|8.4" in snippet.code
            assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0


def test_windows_dotnet_snippet_checks_sha256_without_restarting_services():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="dotnet",
            runtime="host",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
            probe_platform="windows",
            probe_download_url=("http://bklite.example.com:8011/api/v1/apm/open_api/probe/download/" "opentelemetry-dotnet-auto-windows.zip"),
        )
    )

    assert "opentelemetry-dotnet-auto-windows.zip" in snippet.code
    assert "Get-FileHash" in snippet.code
    assert "ASP.NET Framework" in snippet.code
    assert "Expand-Archive" in snippet.code
    assert "Start the application in this PowerShell session" in snippet.code
    assert "dotnet App.dll" not in snippet.code
    assert "Register-OpenTelemetryForWindowsService" not in snippet.code
    assert "Restart-Service" not in snippet.code
    assert "Set-ItemProperty" not in snippet.code
    assert "MySQL" not in snippet.code
    assert "linux-x64" not in snippet.code
    assert "仅支持 Linux" not in snippet.code
    assert snippet.environment["OTEL_METRICS_EXPORTER"] == "none"
    assert snippet.environment["OTEL_LOGS_EXPORTER"] == "none"


def test_obi_snippet_watches_only_the_given_executable():
    snippet = DjangoIntegrationConfigurationService().render_snippet(
        _request(
            language="obi",
            runtime="host",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            service_version="1.0",
            environment="production",
            process_executable="/usr/bin/checkout",
        )
    )

    assert 'exe_path_glob: ["/usr/bin/checkout"]' in snippet.code
    assert "default_action: exclude" in snippet.code
    assert "metrics: false" in snippet.code
    assert "traces: true" in snippet.code
    assert "meter_provider" not in snippet.code
    assert "open_ports" not in snippet.code
    assert "https://github.com" not in snippet.code
    assert "service.namespace=shop" in snippet.code
    assert "OBI requires a readable /sys/kernel/btf/vmlinux" in snippet.code
    assert "OBI needs root or the capabilities required by OBI v1.0.0" in snippet.code
    assert "同一进程不要再装" in snippet.code
    assert snippet.environment["OTEL_METRICS_EXPORTER"] == "none"
    assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0
    with pytest.raises(ProbeSelectionError) as exc_info:
        DjangoIntegrationConfigurationService().render_snippet(
            _request(
                language="obi",
                runtime="docker",
                endpoint="https://apm.example.com",
                service_namespace="shop",
                service_name="checkout",
                service_version="1.0",
                environment="production",
                process_executable="/usr/bin/checkout",
            )
        )
    assert exc_info.value.code == "obi_runtime_unsupported"


def test_ingest_serializer_rejects_unsupported_probe_selection():
    base = {
        "application_id": "shop",
        "cloud_region_id": 7,
        "service_name": "checkout",
        "environment": "production",
    }
    windows_php = IngestSnippetSerializer(data={**base, "language": "php", "runtime": "host", "probe_platform": "windows"})
    assert windows_php.is_valid() is False
    obi = IngestSnippetSerializer(data={**base, "language": "obi", "runtime": "host"})
    assert obi.is_valid() is False
    selected = IngestSnippetSerializer(data={**base, "language": "obi", "runtime": "host", "process_executable": "/usr/bin/checkout"})
    assert selected.is_valid() is True, selected.errors
    windows_ruby = IngestSnippetSerializer(data={**base, "language": "ruby", "runtime": "host", "probe_platform": "windows"})
    assert windows_ruby.is_valid() is False


def test_manual_sdk_snippets_stay_offline_and_do_not_overwrite_examples():
    expectations = {
        "ruby": ("opentelemetry-sdk 1.13.1", "OpenTelemetry::Instrumentation::Rack", "Ruby 3.3 or newer is required"),
        "cpp": ("opentelemetry-cpp v1.30.0", "SpanKind::kServer", ".otel-cpp-sdk/prefix"),
        "erlang": (
            "opentelemetry 1.7.0",
            "opentelemetry_exporter 1.11.0",
            "ln -sfn ../.otel-erlang-sdk/opentelemetry_api _checkouts/opentelemetry_api",
            "otel_span:end_span",
        ),
        "swift": ("opentelemetry-swift 2.6.0", '.package(path: "../.otel-swift-sdk/opentelemetry-swift")', "OpenTelemetryProtocolExporterHTTP"),
    }
    for language, markers in expectations.items():
        for runtime in ("host", "docker", "kubernetes"):
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
            assert snippet.environment["OTEL_METRICS_EXPORTER"] == "none"
            assert snippet.environment["OTEL_LOGS_EXPORTER"] == "none"
            assert _PROBE_DOWNLOAD_URLS[language] in snippet.code
            assert "https://github.com" not in snippet.code
            assert "rubygems.org" not in snippet.code
            assert "hex.pm" not in snippet.code
            if runtime == "kubernetes":
                assert "sha256sum -c -" not in snippet.code
                continue
            assert subprocess.run(["sh", "-n"], input=snippet.code, text=True, capture_output=True).returncode == 0
            if runtime != "host":
                continue
            for marker in markers:
                assert marker in snippet.code
        if language == "erlang":
            erlang = DjangoIntegrationConfigurationService().render_snippet(
                _request(
                    language="erlang",
                    runtime="host",
                    endpoint="https://apm.example.com",
                    service_namespace="shop",
                    service_name="checkout",
                    service_version="1.0",
                    environment="production",
                )
            )
            assert erlang.environment["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http_protobuf"

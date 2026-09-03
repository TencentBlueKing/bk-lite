import pytest
from rest_framework.test import APIClient

from apps.apm.management.commands.apm_probe_init import Command as ApmProbeInitCommand
from apps.apm.services.probe_artifacts import (
    DOTNET_AUTO_ARTIFACT_NAME,
    GO_SDK_ARTIFACT_NAME,
    JAVA_AGENT_ARTIFACT_NAME,
    LANGUAGE_PROBE_ARTIFACTS,
    NODEJS_AUTO_ARTIFACT_NAME,
    PROBE_ARTIFACT_LEGACY_OBJECT_KEYS,
    PROBE_ARTIFACT_OBJECT_KEYS,
    PYTHON_WHEELS_ARTIFACT_NAME,
    ProbeArtifactNotFound,
    build_probe_artifact_download_url,
    upload_probe_artifact,
)


def test_download_url_only_covers_allowlisted_artifacts():
    assert build_probe_artifact_download_url("http://10.10.10.1:8011/", JAVA_AGENT_ARTIFACT_NAME) == (
        "http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-javaagent.jar"
    )
    assert build_probe_artifact_download_url("http://10.10.10.1:8011", PYTHON_WHEELS_ARTIFACT_NAME).endswith(
        "/opentelemetry-python-wheels.tar.gz"
    )
    assert LANGUAGE_PROBE_ARTIFACTS == {
        "java": JAVA_AGENT_ARTIFACT_NAME,
        "python": PYTHON_WHEELS_ARTIFACT_NAME,
        "nodejs": NODEJS_AUTO_ARTIFACT_NAME,
        "go": GO_SDK_ARTIFACT_NAME,
        "dotnet": DOTNET_AUTO_ARTIFACT_NAME,
    }
    assert DOTNET_AUTO_ARTIFACT_NAME == "opentelemetry-dotnet-auto-linux-glibc-x64.zip"
    assert PROBE_ARTIFACT_OBJECT_KEYS[DOTNET_AUTO_ARTIFACT_NAME] == (
        "apm/probe/dotnet/opentelemetry-dotnet-auto-linux-glibc-x64.zip"
    )
    assert DOTNET_AUTO_ARTIFACT_NAME not in PROBE_ARTIFACT_LEGACY_OBJECT_KEYS
    assert build_probe_artifact_download_url("http://10.10.10.1:8011", DOTNET_AUTO_ARTIFACT_NAME) == (
        "http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-dotnet-auto-linux-glibc-x64.zip"
    )
    with pytest.raises(ProbeArtifactNotFound):
        build_probe_artifact_download_url("http://10.10.10.1:8011", "etc-passwd")


@pytest.mark.django_db
def test_probe_artifact_download_streams_the_allowlisted_file_without_login(monkeypatch):
    monkeypatch.setattr(
        "apps.apm.views.open_probe.open_probe_artifact_stream",
        lambda artifact_name: (iter([b"jar-", b"bytes"]), artifact_name),
    )

    response = APIClient().get(f"/api/v1/apm/open_api/probe/download/{JAVA_AGENT_ARTIFACT_NAME}")

    assert response.status_code == 200
    assert response["Content-Disposition"] == f'attachment; filename="{JAVA_AGENT_ARTIFACT_NAME}"'
    assert b"".join(response.streaming_content) == b"jar-bytes"


@pytest.mark.django_db
def test_probe_artifact_download_rejects_names_outside_the_allowlist():
    response = APIClient().get("/api/v1/apm/open_api/probe/download/etc-passwd")

    assert response.status_code == 404
    assert response.json()["code"] == "probe_artifact_not_found"


@pytest.mark.django_db
@pytest.mark.parametrize("artifact_name", [JAVA_AGENT_ARTIFACT_NAME, DOTNET_AUTO_ARTIFACT_NAME])
def test_probe_artifact_download_returns_404_when_the_object_is_not_initialized(monkeypatch, artifact_name):
    def missing(name):
        raise ProbeArtifactNotFound(name)

    monkeypatch.setattr("apps.apm.views.open_probe.open_probe_artifact_stream", missing)

    response = APIClient().get(f"/api/v1/apm/open_api/probe/download/{artifact_name}")

    assert response.status_code == 404
    assert response.json()["code"] == "probe_artifact_not_found"


@pytest.mark.django_db
def test_probe_artifact_download_reports_storage_unavailability_without_details(monkeypatch):
    def broken(artifact_name):
        raise TimeoutError("nats connect timeout")

    monkeypatch.setattr("apps.apm.views.open_probe.open_probe_artifact_stream", broken)

    response = APIClient().get(f"/api/v1/apm/open_api/probe/download/{JAVA_AGENT_ARTIFACT_NAME}")

    assert response.status_code == 503
    assert response.json()["code"] == "probe_artifact_unavailable"
    assert "nats" not in str(response.json())


def test_upload_probe_artifact_writes_the_allowlisted_object_key(monkeypatch, tmp_path):
    uploads = []

    class FakeJetStream:
        async def connect(self):
            pass

        async def put(self, key, data, description=None):
            uploads.append((key, data.read(), description))

        async def close(self):
            pass

    monkeypatch.setattr("apps.apm.services.probe_artifacts.JetStreamService", FakeJetStream)
    file_path = tmp_path / "opentelemetry-javaagent.jar"
    file_path.write_bytes(b"jar-bytes")

    upload_probe_artifact(JAVA_AGENT_ARTIFACT_NAME, str(file_path))

    assert uploads == [
        (PROBE_ARTIFACT_OBJECT_KEYS[JAVA_AGENT_ARTIFACT_NAME], b"jar-bytes", JAVA_AGENT_ARTIFACT_NAME),
    ]
    assert PROBE_ARTIFACT_OBJECT_KEYS[JAVA_AGENT_ARTIFACT_NAME] == "apm/probe/java/opentelemetry-javaagent.jar"
    assert PROBE_ARTIFACT_LEGACY_OBJECT_KEYS[JAVA_AGENT_ARTIFACT_NAME] == "apm/probe/opentelemetry-javaagent.jar"


def test_upload_probe_artifact_rejects_names_outside_the_allowlist(tmp_path):
    with pytest.raises(ProbeArtifactNotFound):
        upload_probe_artifact("etc-passwd", str(tmp_path / "whatever"))


def test_apm_probe_init_command_uploads_the_selected_artifact(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        "apps.apm.management.commands.apm_probe_init.upload_probe_artifact",
        lambda artifact_name, file_path: captured.update(artifact_name=artifact_name, file_path=file_path),
    )
    file_path = tmp_path / "opentelemetry-javaagent.jar"
    file_path.write_bytes(b"jar-bytes")

    ApmProbeInitCommand().handle(artifact=JAVA_AGENT_ARTIFACT_NAME, file_path=str(file_path))

    assert captured == {"artifact_name": JAVA_AGENT_ARTIFACT_NAME, "file_path": str(file_path)}


def test_apm_probe_init_command_accepts_the_dotnet_glibc_artifact(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        "apps.apm.management.commands.apm_probe_init.upload_probe_artifact",
        lambda artifact_name, file_path: captured.update(artifact_name=artifact_name, file_path=file_path),
    )
    file_path = tmp_path / DOTNET_AUTO_ARTIFACT_NAME
    file_path.write_bytes(b"zip-bytes")

    ApmProbeInitCommand().handle(artifact=DOTNET_AUTO_ARTIFACT_NAME, file_path=str(file_path))

    assert captured == {"artifact_name": DOTNET_AUTO_ARTIFACT_NAME, "file_path": str(file_path)}

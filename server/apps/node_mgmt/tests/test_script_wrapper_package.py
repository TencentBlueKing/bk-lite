from pathlib import Path


FUSION_COLLECTOR_AGENT = (
    Path(__file__).resolve().parents[4] / "agents" / "fusion-collector" / "agent"
)
LINUX_WRAPPER_PATH = "/opt/fusion-collectors/bin/bklite-script-wrapper"
WINDOWS_WRAPPER_PATH = "/opt/release/windows/fusion-collectors/bin/bklite-script-wrapper.exe"


def test_container_packages_script_wrapper_beside_telegraf():
    dockerfile = (FUSION_COLLECTOR_AGENT / "Dockerfile").read_text()
    sidecar = (FUSION_COLLECTOR_AGENT / "sidecar.yml").read_text()

    assert "ADD ./telegraf ./bin/telegraf" in dockerfile
    assert f"COPY --from=script-wrapper-build /out/bklite-script-wrapper {LINUX_WRAPPER_PATH}" in dockerfile
    assert f"COPY --from=script-wrapper-build /out/bklite-script-wrapper.exe {WINDOWS_WRAPPER_PATH}" in dockerfile
    assert "COPY ./script-wrapper /src" in dockerfile
    assert "GOOS=linux GOARCH=${TARGETARCH}" in dockerfile
    assert "GOOS=windows GOARCH=amd64" in dockerfile
    assert "ADD ./telegraf-wrapper" not in dockerfile
    assert "/opt/fusion-collectors/bin/*" in sidecar

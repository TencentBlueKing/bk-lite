import base64
import io
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

INSTALLER = Path(__file__).resolve().parents[1] / "install-proxy-payload.sh"


@pytest.mark.parametrize("failure_stage", ["preflight", "apply", "none"])
def test_upgrade_keeps_previous_installation(tmp_path, failure_stage):
    target = tmp_path / "proxy"
    target.mkdir()
    (target / ".env").write_text("old")
    (target / "docker-compose.yaml").write_text("services: {}\n")
    (target / "local-overrides.txt").write_text("keep")
    flock = tmp_path / "flock"
    flock.write_text("#!/bin/sh\nexit 0\n")
    flock.chmod(0o700)
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/sh\ntest "$(cat .env)" = old && printf "old service recreated\\n"\n')
    docker.chmod(0o700)

    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        for name, contents in {
            ".env": "candidate",
            "conf/nats/nats.conf": "test",
            "conf/certs/proxy.key": "test",
            "conf/certs/ca.crt": "test CA",
            "conf/apm/regional.yaml": "test APM config",
            "conf/traefik/certs/proxy.key": "test",
            "bootstrap.sh": (
                'test "$(cat .env)" = candidate || exit 9\n'
                'if [ "${1:-}" = preflight ]; then\n'
                '  test "$(cat "$2/.env")" = old && [ "$FAILURE_STAGE" != preflight ]\n'
                'else\n'
                '  [ "$FAILURE_STAGE" != apply ]\n'
                'fi\n'
            ),
        }.items():
            data = contents.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

    script = tmp_path / "install.sh"
    encoded = base64.b64encode(archive_bytes.getvalue()).decode()
    script.write_text(f'set -euo pipefail\numask 077\nINSTALL_PATH="{target}"\nARCHIVE="{encoded}"\n' + INSTALLER.read_text())
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=os.environ | {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", "FAILURE_STAGE": failure_stage},
    )
    assert (target / "local-overrides.txt").read_text() == "keep"
    if failure_stage == "none":
        assert result.returncode == 0, result.stderr
        assert (target / ".env").read_text() == "candidate"
        assert next(tmp_path.glob(".proxy.backup.*/previous/.env")).read_text() == "old"
        for name in (".env", "conf/nats/nats.conf", "conf/certs/proxy.key", "conf/traefik/certs/proxy.key"):
            assert (target / name).stat().st_mode & 0o777 == 0o600
        assert target.stat().st_mode & 0o777 == 0o700
        assert (target / "conf/certs").stat().st_mode & 0o777 == 0o711
        for name in ("conf/certs/ca.crt", "conf/apm/regional.yaml"):
            assert (target / name).stat().st_mode & 0o777 == 0o644
    else:
        assert result.returncode != 0
        assert (target / ".env").read_text() == "old"
        assert ("old service recreated" in result.stdout) == (failure_stage == "apply")


@pytest.mark.parametrize(
    "failed_service, https_status, expected_error",
    [
        (None, "307", None),
        ("traefik", "200", "Proxy services are not ready"),
        ("apm-regional-queue-init", "200", "Proxy services are not ready"),
        ("redis", "200", "Proxy services are not ready"),
        (None, "502", "Proxy HTTPS route is not ready"),
        (None, "404", "Proxy HTTPS route is not ready"),
        (None, "TLS_ERROR", "Proxy HTTPS route is not ready"),
    ],
)
def test_bootstrap_requires_services_and_working_https(tmp_path, failed_service, https_status, expected_error):
    import json

    (tmp_path / ".env").touch()
    config = tmp_path / "conf/nats"
    config.mkdir(parents=True)
    (config / "jetstream.json").write_text('{"name":"OBJ_test","mirror":{"external":{"api":"$JS.test.API"}}}')
    bootstrap = tmp_path / "bootstrap.sh"
    bootstrap.write_bytes((INSTALLER.parent / "proxy/bootstrap.sh").read_bytes())

    states = [
        {"Service": service, "State": "running", "Health": "healthy" if service == "redis" else ""}
        for service in ("nats", "nats-executor", "fusion-collector", "apm-regional-collector", "traefik", "stargazer", "redis")
    ]
    states.append({"Service": "apm-regional-queue-init", "State": "exited", "ExitCode": 0})
    for row in states:
        if row["Service"] == failed_service:
            row.update(State="exited", ExitCode=1, Health="unhealthy")

    (tmp_path / "states.json").write_text(json.dumps(states))
    docker = tmp_path / "docker"
    docker.write_text(
        """#!/bin/bash
case "$*" in
    'compose version') exit 0 ;;
    'compose up -d --force-recreate') test -f collected-bin-ready ;;
    'compose ps --all --format json') cat states.json ;;
    'compose --project-directory '*)
        printf '%s\\n' '{"services":{"nats-executor":{"environment":{"NATS_URLS":"tls://admin:test@nats:4222"}},"nats":{"image":"test"},"fusion-collector":{"image":"test"},"traefik":{"command":["--entrypoints.websecure.address=:9443"]}}}'
        ;;
    *'STREAM.INFO.OBJ_test'*)
        printf '%s\\n' '{"config":{"name":"OBJ_test","mirror":{"name":"OBJ_test","external":{"api":"$JS.test.API"}}},"mirror":{"lag":0,"active":1},"state":{"messages":1}}'
        ;;
    *'--entrypoint curl'*'--noproxy *'*'--cacert /tmp/nats/ca.crt'*'https://traefik:9443/'*)
        [ "$HTTPS_STATUS" != TLS_ERROR ] || exit 60
        printf '%s' "$HTTPS_STATUS"
        ;;
    *'--network none'*'cp -ar bin/'*) touch collected-bin-ready ;;
    *) exit 99 ;;
esac
"""
    )
    docker.chmod(0o700)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o700)
    result = subprocess.run(
        ["bash", str(bootstrap)], capture_output=True, text=True,
        env=os.environ | {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", "HTTPS_STATUS": https_status}, timeout=20,
    )
    if expected_error is None:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert expected_error in result.stderr


@pytest.mark.parametrize("old_flag", [False, True])
@pytest.mark.parametrize("previous_port", [4222, 4223, 14222])
def test_preflight_keeps_port_from_known_previous_templates(tmp_path, old_flag, previous_port):
    packaged = (INSTALLER.parent / "proxy/docker-compose.yaml").read_text()
    previous = packaged.replace('"4222:4222"', f'"{previous_port}:4222"')
    if old_flag:
        previous = previous.replace('      - "--providers.file.watch=true"\n',
                                    '      - "--providers.file.watch=true"\n      - "--providers.file.templating=true"\n')
    (tmp_path / "docker-compose.yaml").write_text(packaged)
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "docker-compose.yaml").write_text(previous)
    bootstrap = (INSTALLER.parent / "proxy/bootstrap.sh").read_text()
    start = bootstrap.index("compose_template_supported() {")
    stop = bootstrap.index('if [ "${1:-}" = preflight ]', start)
    stubs = """err() { echo "$1" >&2; exit 1; }
probe_source() { echo '{}'; }
load_compose_env() { :; }
api() { echo 'missing'; }
stream_missing() { [ "$1" = missing ]; }
check_mirror() { :; }
"""
    result = subprocess.run(["bash", "-ec", stubs + bootstrap[start:stop] + '\npreflight "$1"', "_", str(installed)],
                            cwd=tmp_path, check=False)
    if previous_port == 14222:
        assert result.returncode != 0
        assert (tmp_path / "docker-compose.yaml").read_text() == packaged
    else:
        assert result.returncode == 0
        assert (tmp_path / "docker-compose.yaml").read_text() == packaged.replace('"4222:4222"', f'"{previous_port}:4222"')
    assert (installed / "docker-compose.yaml").read_text() == previous

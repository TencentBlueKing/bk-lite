import base64
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

INSTALLER = Path(__file__).resolve().parents[1] / "install-proxy-payload.sh"


@pytest.mark.parametrize("failure_stage", ["preflight", "apply", "backup_rename", "rename", "space", "none"])
def test_upgrade_keeps_previous_installation(tmp_path, failure_stage):
    target = tmp_path / "proxy"
    target.mkdir()
    old_env = (
        "NATS_ADMIN_PASSWORD='old-first-line\nTRAEFIK_WEB_PORT=inside-password\n'\n"
        "PROXY_PUBLIC_PORT: 4243\nCOMPOSE_PROJECT_NAME=existing\n"
        "LOCAL_NOTE='multiline\nNATS_ADMIN_PASSWORD=keep-literal\n'\n"
    )
    (target / ".env").write_text(old_env)
    (target / "docker-compose.yaml").write_text("services: {}\n")
    override = 'services: {example: {ports: ["${PROXY_PUBLIC_PORT:?set port}:4222"]}}\n'
    (target / "docker-compose.override.yaml").write_text(override)
    retained = tmp_path / ".proxy.rollback"
    (retained / "previous").mkdir(parents=True)
    (retained / ".proxy-install-backup").touch()
    (retained / "previous/.env").write_text("oldest")
    legacy = tmp_path / ".proxy.backup.untouched"
    legacy.mkdir()
    (legacy / "readme").write_text("operator backup")

    commands = {
        "flock": "#!/bin/sh\nexit 0\n",
        "docker": '#!/bin/sh\ngrep -q old-first-line .env && printf "old service recreated\\n"\n',
        "mv": (
            '#!/bin/bash\n/bin/mv "$@" || exit $?\n'
            'if [[ "$FAILURE_STAGE" == rename && "$2" == */.proxy.installing/stage ]]; then kill -TERM "$PPID"; fi\n'
            'if [[ "$FAILURE_STAGE" == backup_rename && "$3" == */.proxy.installing/previous ]]; then kill -TERM "$PPID"; fi\n'
        ),
    }
    if failure_stage == "space":
        commands["df"] = '#!/bin/sh\nprintf "%s\\n" "Filesystem 1024-blocks Used Available Capacity Mounted on" "fake 100 99 1 99% /"\n'
        commands["cp"] = '#!/bin/sh\ntouch "$COPY_ATTEMPTED"\nexit 99\n'
    for name, command in commands.items():
        path = tmp_path / name
        path.write_text(command)
        path.chmod(0o700)

    archive_bytes = io.BytesIO()
    generated_env = "NATS_ADMIN_PASSWORD=new-password\nTRAEFIK_WEB_PORT=9443\n"
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        for name, contents in {
            ".env": generated_env,
            "conf/nats/nats.conf": "test",
            "conf/certs/proxy.key": "test",
            "conf/certs/ca.crt": "test CA",
            "conf/apm/regional.yaml": "test APM config",
            "conf/traefik/certs/proxy.key": "test",
            "bootstrap.sh": (
                'grep -qx "PROXY_PUBLIC_PORT: 4243" .env || exit 9\n'
                'if [ "${1:-}" = preflight ]; then\n'
                '  grep -q old-first-line "$2/.env" && [ "$FAILURE_STAGE" != preflight ]\n'
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
    env = os.environ | {
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "FAILURE_STAGE": failure_stage,
        "COPY_ATTEMPTED": str(tmp_path / "copy-attempted"),
    }
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env)
    assert (target / "docker-compose.override.yaml").read_text() == override
    assert (legacy / "readme").read_text() == "operator backup"
    assert not (tmp_path / ".proxy.installing").exists()
    if failure_stage == "none":
        assert result.returncode == 0, result.stderr
        installed_env = (target / ".env").read_text()
        assert installed_env == (
            generated_env + "\nPROXY_PUBLIC_PORT: 4243\nCOMPOSE_PROJECT_NAME=existing\n"
            "LOCAL_NOTE='multiline\nNATS_ADMIN_PASSWORD=keep-literal\n'\n"
        )
        assert (retained / "previous/.env").read_text() == old_env
        assert list(tmp_path.glob(".proxy.rollback*")) == [retained]
        for name in (".env", "conf/nats/nats.conf", "conf/certs/proxy.key", "conf/traefik/certs/proxy.key"):
            assert (target / name).stat().st_mode & 0o777 == 0o600
        assert target.stat().st_mode & 0o777 == 0o700
        assert (target / "conf/certs").stat().st_mode & 0o777 == 0o711
        for name in ("conf/certs/ca.crt", "conf/apm/regional.yaml"):
            assert (target / name).stat().st_mode & 0o777 == 0o644
    else:
        assert result.returncode != 0
        assert (target / ".env").read_text() == old_env
        assert not (target / "previous").exists()
        assert (retained / "previous/.env").read_text() == "oldest"
        assert ("old service recreated" in result.stdout) == (failure_stage == "apply")
    if failure_stage in {"backup_rename", "rename"}:
        assert result.returncode == 143
    if failure_stage == "space":
        assert "Insufficient free space" in result.stderr
        assert not (tmp_path / "copy-attempted").exists()


@pytest.mark.parametrize("free_kib, copied", [(65536, False), (68608, True)])
def test_collector_binary_copy_respects_available_space(tmp_path, free_kib, copied):
    bootstrap = (INSTALLER.parent / "proxy/bootstrap.sh").read_text()
    copy_command = bootstrap.split("# Populate the staged bind mount", 1)[1].split("-c '", 1)[1].split("' || err", 1)[0]
    commands = {
        "du": "#!/bin/sh\necho '3072 bin'\n",
        "df": f"#!/bin/sh\necho header\necho 'device 100000 0 {free_kib} 10% /tmp/bin'\n",
        "cp": "#!/bin/sh\ntouch copied\n",
    }
    for name, command in commands.items():
        path = tmp_path / name
        path.write_text(command)
        path.chmod(0o700)
    result = subprocess.run(
        ["bash", "-c", copy_command],
        cwd=tmp_path,
        env=os.environ | {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is copied
    assert (tmp_path / "copied").exists() is copied
    if not copied:
        assert "Insufficient free space" in result.stderr


@pytest.mark.parametrize(
    "failed_service, https_status, address, expected_error",
    [
        (None, "307", ":9443", None),
        (None, "200", ":9443/tcp", None),
        (None, "200", "0.0.0.0:9443", None),
        (None, "200", "[::]:9443/tcp", None),
        (None, "200", ":9443/udp", "Cannot determine the Proxy HTTPS entry point"),
        ("traefik", "200", ":9443", "Proxy services are not ready"),
        ("apm-regional-queue-init", "200", ":9443", "Proxy services are not ready"),
        ("redis", "200", ":9443", "Proxy services are not ready"),
        (None, "502", ":9443", "Proxy HTTPS route is not ready"),
        (None, "404", ":9443", "Proxy HTTPS route is not ready"),
        (None, "TLS_ERROR", ":9443", "Proxy HTTPS route is not ready"),
    ],
)
def test_bootstrap_requires_services_and_working_https(tmp_path, failed_service, https_status, address, expected_error):

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
        printf '%s\\n' '{"services":{"nats-executor":{"environment":{"NATS_URLS":"tls://admin:test@nats:4222"}},"nats":{"image":"test"},"fusion-collector":{"image":"test"},"traefik":{"command":["--entrypoints.websecure.address='"${HTTPS_ADDRESS}"'"]}}}'
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
        env=os.environ | {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", "HTTPS_STATUS": https_status, "HTTPS_ADDRESS": address}, timeout=20,
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

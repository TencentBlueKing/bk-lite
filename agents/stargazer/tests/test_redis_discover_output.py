"""Redis 发现脚本把算出来的安装路径写进采集结果。"""

import json
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    ROOT / "plugins/inputs/redis/redis_default_discover.sh",
    ROOT / "tests/collect_fixtures/init/redis_default_discover.sh",
    ROOT / "tests/collect_fixtures/init/redis_sentinel_default_discover.sh",
]


def test_emit_writes_computed_install_path():
    for script in SCRIPTS:
        command = f"""
set -eu
eval "$(sed '/^main "$@"$/d' '{script}')"
emit_instance "10.0.0.8" "6379" "standalone" "master" "7.4.9" "/usr/bin/redis-server" "10000" "0" "cluster-1" "[]" "{{}}"
emit_partial_instance "10.0.0.8" "6380" "6.2.1" "/usr/local/bin/redis-server"
"""
        completed = subprocess.run(["sh", "-c", command], check=True, capture_output=True, text=True)
        lines = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        assert lines[0]["install_path"] == "/usr/bin/redis-server"
        assert lines[0]["version"] == "7.4.9"
        assert lines[1]["install_path"] == "/usr/local/bin/redis-server"
        assert lines[1]["version"] == "6.2.1"


def _write_fake_redis_cli(bin_dir: Path) -> None:
    cli = bin_dir / "redis-cli"
    cli.write_text(
        """#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in
    -h|-p|--user) shift 2 ;;
    *) break ;;
  esac
done
if [ "${REDISCLI_AUTH:-}" != "testpass" ]; then
  echo "(error) NOAUTH Authentication required." >&2
  exit 1
fi
cmd="$1"
sub="${2:-}"
name="${3:-}"
case "$cmd" in
  PING) echo PONG ;;
  INFO)
    case "$sub" in
      replication) echo "role:master" ;;
      sentinel) echo "sentinel_masters:0" ;;
      server) printf 'redis_version:7.4.10\\nexecutable:/usr/local/bin/redis-server\\nrun_id:abc\\n' ;;
    esac
    ;;
  CONFIG)
    case "$name" in
      maxclients) printf 'maxclients\\n10000\\n' ;;
      maxmemory) printf 'maxmemory\\n0\\n' ;;
    esac
    ;;
esac
""",
        encoding="utf-8",
    )
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)


def _write_stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _run_discover(tmp_path: Path, *, password: str) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_redis_cli(bin_dir)
    _write_stub(bin_dir, "docker", "#!/bin/sh\nexit 0\n")
    _write_stub(bin_dir, "nc", "#!/bin/sh\nexit 0\n")
    script = ROOT / "plugins/inputs/redis/redis_default_discover.sh"
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["REDIS_TARGET_HOST"] = "127.0.0.1"
    env["REDIS_TARGET_PORTS"] = "6379"
    env["REDIS_DISCOVER_FROM_PROCESS"] = "no"
    env["BK_HOST_INNERIP"] = "10.209.0.13"
    env.pop("REDISCLI_AUTH", None)
    env.pop("REDIS_USER", None)
    if password:
        env["REDISCLI_AUTH"] = password
    completed = subprocess.run(
        ["sh", str(script)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    lines = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    return lines[0]


def test_discover_without_rediscli_auth_emits_partial_instance(tmp_path):
    row = _run_discover(tmp_path, password="")

    assert row["inst_name"] == "10.209.0.13-redis-6379"
    assert row["port"] == "6379"
    assert row["max_conn"] == ""
    assert row["max_mem"] == ""
    assert row["database_role"] == ""


def test_discover_with_rediscli_auth_reads_login_fields(tmp_path):
    row = _run_discover(tmp_path, password="testpass")

    assert row["inst_name"] == "10.209.0.13-redis-6379"
    assert row["version"] == "7.4.10"
    assert row["install_path"] == "/usr/local/bin/redis-server"
    assert row["max_conn"] == "10000"
    assert row["max_mem"] == "0"
    assert row["database_role"] == "master"
    assert row["topo_mode"] == "replication"


def _write_port_nc(bin_dir, open_ports):
    ports = " ".join(sorted(open_ports))
    _write_stub(
        bin_dir,
        "nc",
        f"""#!/bin/sh
port=""
for arg in "$@"; do port="$arg"; done
case " {ports} " in
  *" $port "*) exit 0 ;;
esac
exit 1
""",
    )


def _write_refusing_redis_cli(bin_dir):
    _write_stub(
        bin_dir,
        "redis-cli",
        """#!/bin/sh
echo "Could not connect to Redis: Connection refused" >&2
exit 1
""",
    )


def _run_discover_rows(tmp_path, *, ports, open_ports, password=""):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if password == "testpass":
        _write_fake_redis_cli(bin_dir)
    else:
        _write_refusing_redis_cli(bin_dir)
    _write_stub(bin_dir, "docker", "#!/bin/sh\nexit 0\n")
    _write_stub(bin_dir, "ps", "#!/bin/sh\necho /usr/bin/dockerd\n")
    _write_port_nc(bin_dir, open_ports)
    script = ROOT / "plugins/inputs/redis/redis_default_discover.sh"
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["REDIS_TARGET_HOST"] = "127.0.0.1"
    env["REDIS_DISCOVER_FROM_PROCESS"] = "no"
    env["BK_HOST_INNERIP"] = "10.209.0.13"
    env.pop("REDISCLI_AUTH", None)
    env.pop("REDIS_USER", None)
    if ports is None:
        env.pop("REDIS_TARGET_PORTS", None)
    else:
        env["REDIS_TARGET_PORTS"] = ports
    if password:
        env["REDISCLI_AUTH"] = password
    completed = subprocess.run(["sh", str(script)], check=False, capture_output=True, text=True, env=env)
    assert completed.returncode == 0, completed.stderr
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def test_closed_default_ports_are_not_instances(tmp_path):
    rows = _run_discover_rows(tmp_path, ports=None, open_ports=set())

    assert rows == []


def test_open_port_that_is_not_redis_is_not_an_instance(tmp_path):
    rows = _run_discover_rows(tmp_path, ports="6379,6389", open_ports={"6389"})

    assert rows == []


def _write_listener(bin_dir: Path, install_path: str) -> None:
    _write_stub(bin_dir, "uname", "#!/bin/sh\necho Darwin\n")
    _write_stub(
        bin_dir,
        "lsof",
        f"""#!/bin/sh
if [ "$1" = "-i" ]; then
  echo 4242
  exit 0
fi
echo "redis-ser 4242 user txt REG {install_path}"
""",
    )


def _write_container_docker(bin_dir: Path, log_path: Path) -> None:
    _write_stub(
        bin_dir,
        "docker",
        f"""#!/bin/sh
printf '%s\\n' "$*" >> "{log_path}"
cmd="$1"
shift
case "$cmd" in
  ps) echo abcdef123456 ;;
  port) echo "6379/tcp -> 0.0.0.0:6379" ;;
  exec)
    while [ $# -gt 0 ]; do
      case "$1" in
        -e) shift 2 ;;
        *) break ;;
      esac
    done
    shift
    REDIS_IN_CONTAINER=1 "$@"
    ;;
esac
""",
    )


def _write_split_redis_cli(bin_dir: Path) -> None:
    _write_stub(
        bin_dir,
        "redis-cli",
        """#!/bin/sh
for arg in "$@"; do
  if [ "$arg" = "testpass" ]; then
    echo leaked >&2
    exit 2
  fi
done
if [ "${REDIS_IN_CONTAINER:-}" != "1" ] && [ "${HOST_REDIS_OK:-}" != "1" ]; then
  echo "(error) NOAUTH Authentication required." >&2
  exit 1
fi
if [ "${REDISCLI_AUTH:-}" != "testpass" ]; then
  echo "(error) NOAUTH Authentication required." >&2
  exit 1
fi
while [ $# -gt 0 ]; do
  case "$1" in
    -h|-p|--user) shift 2 ;;
    *) break ;;
  esac
done
cmd="$1"
sub="${2:-}"
name="${3:-}"
case "$cmd" in
  PING) echo PONG ;;
  INFO)
    case "$sub" in
      replication) echo "role:master" ;;
      sentinel) echo "sentinel_masters:0" ;;
      server) printf 'redis_version:7.4.10\\nexecutable:/usr/local/bin/redis-server\\nrun_id:abc\\n' ;;
    esac
    ;;
  CONFIG)
    case "$name" in
      maxclients) printf 'maxclients\\n10000\\n' ;;
      maxmemory) printf 'maxmemory\\n0\\n' ;;
    esac
    ;;
esac
""",
    )


def _run_listener_discover(tmp_path, install_path, with_docker, host_login):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "docker-argv.log"
    _write_split_redis_cli(bin_dir)
    _write_listener(bin_dir, install_path)
    _write_stub(bin_dir, "nc", "#!/bin/sh\nexit 0\n")
    if with_docker:
        _write_container_docker(bin_dir, log_path)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["REDIS_TARGET_HOST"] = "127.0.0.1"
    env["REDIS_TARGET_PORTS"] = "6379"
    env["REDIS_DISCOVER_FROM_PROCESS"] = "no"
    env["BK_HOST_INNERIP"] = "10.209.0.13"
    env["REDISCLI_AUTH"] = "testpass"
    env["HOST_REDIS_OK"] = "1" if host_login else "0"
    completed = subprocess.run(
        ["sh", str(ROOT / "plugins/inputs/redis/redis_default_discover.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    lines = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    return lines[0], log_path.read_text(encoding="utf-8") if log_path.exists() else ""


def test_host_redis_server_does_not_enter_the_container(tmp_path):
    row, docker_log = _run_listener_discover(
        tmp_path,
        install_path="/no/such/redis-server",
        with_docker=True,
        host_login=False,
    )

    assert "exec" not in docker_log
    assert row["install_path"] == "/no/such/redis-server"
    assert row["max_conn"] == ""
    assert row["database_role"] == ""


def test_published_port_login_does_not_enter_the_container(tmp_path):
    row, docker_log = _run_listener_discover(
        tmp_path,
        install_path="/no/such/docker-proxy",
        with_docker=True,
        host_login=True,
    )

    assert "exec" not in docker_log
    assert row["max_conn"] == "10000"
    assert row["database_role"] == "master"
    assert "testpass" not in docker_log


def test_docker_proxy_without_host_login_collects_inside_the_container(tmp_path):
    row, docker_log = _run_listener_discover(
        tmp_path,
        install_path="/no/such/docker-proxy",
        with_docker=True,
        host_login=False,
    )

    assert "exec" in docker_log
    assert "-e REDISCLI_AUTH" in docker_log
    assert "testpass" not in docker_log
    assert row["version"] == "7.4.10"
    assert row["install_path"] == "/usr/local/bin/redis-server"
    assert row["max_conn"] == "10000"
    assert row["max_mem"] == "0"
    assert row["database_role"] == "master"


def test_missing_docker_keeps_the_host_partial_result(tmp_path):
    row, docker_log = _run_listener_discover(
        tmp_path,
        install_path="/no/such/docker-proxy",
        with_docker=False,
        host_login=False,
    )

    assert docker_log == ""
    assert row["install_path"] == "/no/such/docker-proxy"
    assert row["max_conn"] == ""
    assert row["database_role"] == ""


def test_only_the_responding_port_in_a_range_is_kept(tmp_path):
    rows = _run_discover_rows(tmp_path, ports="7000-7001", open_ports={"7000"}, password="testpass")

    assert [row["port"] for row in rows] == ["7000"]
    assert rows[0]["database_role"] == "master"

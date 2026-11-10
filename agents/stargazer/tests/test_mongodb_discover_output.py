"""MongoDB 发现脚本在容器分支读取配置，并且不把口令放进命令参数。"""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/inputs/mongodb/mongodb_default_discover.sh"


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o755)


@pytest.mark.parametrize("authenticated", [False, True])
def test_container_mongo_role_does_not_put_the_password_on_argv(tmp_path, authenticated):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "docker-argv.log"
    secret = "mongo-secret"
    _write(bin_dir / "hostname", "#!/bin/sh\necho 10.10.41.149\n")
    _write(bin_dir / "ps", "#!/bin/sh\nexit 0\n")
    _write(bin_dir / "netstat", "#!/bin/sh\nexit 0\n")
    _write(
        bin_dir / "docker",
        f"""#!/bin/sh
printf '%s\\n' "$*" >> "{log_path}"
cmd="$1"
shift
case "$cmd" in
  ps) printf '%s\n' noshell abcdef123456 ;;
  port) echo "27017/tcp -> 0.0.0.0:27017" ;;
  exec)
    while [ $# -gt 0 ]; do
      case "$1" in
        -e) shift 2 ;;
        *) break ;;
      esac
    done
    id="$1"
    shift
    if [ "$id" = "noshell" ]; then
      echo 'OCI runtime exec failed: exec: "sh": executable file not found'
      exit 1
    fi
    if [ "$1" = "sh" ]; then
      case "$*" in
        *command*-v*mongod*) echo /usr/bin/mongod ;;
        *tr*) echo "--config /etc/mongod.conf" ;;
        *grep*) printf '%s\n' "maxIncomingConnections: 20000" "fork: true" \
          "systemLog:" "  path: /var/log/mongodb/mongod.log" \
          "storage:" "  dbPath: /data/db" ;;
        *mongosh*) echo /usr/bin/mongosh ;;
      esac
      exit 0
    fi
    case "$*" in
      *--version*) echo "db version v7.0.14" ;;
      *--eval*)
        if [ "${{MONGO_PASSWORD:-}}" = "{secret}" ]; then
          echo "role PRIMARY"
        fi
        ;;
    esac
    ;;
esac
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env.pop("MONGO_USER", None)
    env.pop("MONGO_PASSWORD", None)
    env.pop("MONGO_AUTH_DB", None)
    if authenticated:
        env["MONGO_USER"] = "reader"
        env["MONGO_PASSWORD"] = secret
        env["MONGO_AUTH_DB"] = "admin"
    completed = subprocess.run(["bash", str(SCRIPT)], check=False, capture_output=True, text=True, env=env)

    assert completed.returncode == 0, completed.stderr
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["port"] == "27017"
    assert rows[0]["version"] == "7.0.14"
    assert rows[0]["max_incoming_conn"] == "20000"
    assert rows[0]["fork"] == "true"
    assert rows[0]["system_log"] == "/var/log/mongodb/mongod.log"
    assert rows[0]["db_path"] == "/data/db"
    assert rows[0]["database_role"] == ("PRIMARY" if authenticated else "")
    docker_log = log_path.read_text(encoding="utf-8")
    assert secret not in docker_log
    if authenticated:
        assert "-e MONGO_PASSWORD" in docker_log
        assert "process.env.MONGO_PASSWORD" in docker_log
    else:
        assert "-e MONGO_PASSWORD" not in docker_log

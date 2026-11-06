#!/usr/bin/env bash
# 在Linux测试环境执行；PostgreSQL须为可创建测试库的专用临时实例。
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Linux ]; then
    echo "此入口要求Linux环境；本机探针不能替代Linux验收" >&2
    exit 1
fi
for required_command in python redis-server make; do
    command -v "$required_command" >/dev/null || { echo "缺少测试命令：$required_command" >&2; exit 1; }
done
evidence_root=${1:-$(mktemp -d /tmp/bklite-celery-validation.XXXXXX)}
mkdir -p "$evidence_root"
evidence_root=$(cd "$evidence_root" && pwd)
python - <<'PY' > "$evidence_root/environment.json"
import json
import hashlib
import platform
import sys
from pathlib import Path
import celery
import django
import kombu
import redis

if sys.version_info[:2] != (3, 12):
    raise SystemExit("Linux运行层验收要求Python3.12")
sources = [
    *Path("apps/core/celery_runtime").glob("*.py"), *Path("apps/core/tests").glob("*celery*.py"),
    Path("scripts/check_celery_runtime.sh"), Path("pyproject.toml"), Path("support-files/tests/celery-runtime-requirements.txt"),
]
print(json.dumps({
    "platform": platform.platform(), "machine": platform.machine(),
    "python": sys.version, "celery": celery.__version__, "django": django.__version__,
    "kombu": kombu.__version__, "redis_client": redis.__version__,
    "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(sources)},
}, indent=2))
PY
DJANGO_SETTINGS_MODULE=apps.core.tests.celery_postgres_test_settings python -m pytest \
    --noconftest -c /dev/null -p no:cacheprovider \
    apps/core/tests/test_celery_runtime_pure.py \
    apps/core/tests/test_celery_routing_service.py \
    apps/core/tests/test_celery_observation_pure.py \
    apps/core/tests/test_celery_route_migration_service.py \
    apps/core/tests/test_celery_diagnostics_service.py \
    apps/core/tests/test_celery_runtime_commands_service.py \
    apps/core/tests/test_celery_pool_service.py \
    apps/core/tests/test_celery_setup_periodic_service.py \
    apps/core/tests/test_celery_setup_periodic_orm_service.py \
    apps/core/tests/test_release_startup_service.py \
    --cov=apps.core.celery_runtime --cov-report=term-missing --cov-fail-under=75 \
    --basetemp "$evidence_root/orm" --junitxml "$evidence_root/orm.xml" -q
CELERY_RUNTIME_INTEGRATION=1 python -m pytest \
    --noconftest -c /dev/null -p no:django -p no:cacheprovider \
    apps/core/tests/test_celery_runtime_integration.py \
    apps/core/tests/test_celery_migration_integration.py \
    --basetemp "$evidence_root/redis" --junitxml "$evidence_root/redis.xml" -q
python - <<'PY' > "$evidence_root/resources.json"
import json
from pathlib import Path

metrics = {}
for name in ("memory.current", "memory.peak", "memory.max", "pids.max", "cpu.max"):
    try:
        metrics[name] = Path("/sys/fs/cgroup", name).read_text().strip()
    except OSError:
        metrics[name] = None
print(json.dumps(metrics, indent=2))
PY
redis-server --version > "$evidence_root/redis-version.txt"
echo "Linux运行层验收通过；环境、JUnit和worker日志：$evidence_root"

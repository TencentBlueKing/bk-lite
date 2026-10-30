"""启动前校验与配置生成；不导入 Django，不访问数据库。"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from apps.core.celery_runtime.config import POOL_QUEUES, RuntimeConfig
from apps.core.celery_runtime.environment import load_runtime_environment


def check_prefork():
    subprocess.run([sys.executable, "manage.py", "celery_prefork_check"], check=True)


def write_supervisor(path, content):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main():
    load_runtime_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--supervisor", metavar="PATH")
    action.add_argument("--worker", choices=POOL_QUEUES)
    action.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        config = RuntimeConfig.from_env()
        if args.supervisor:
            write_supervisor(args.supervisor, config.supervisor_config())
        elif args.worker:
            command = config.worker_args(args.worker)
            check_prefork()
            os.environ["AUTOSCALE_KEEPALIVE"] = str(config.keepalive)
            os.execv(sys.executable, [sys.executable, "-m", "celery", *command])
        else:
            print(f"Celery 执行池数={len(config.pools)}，所有副本最大并发={config.maximum_concurrency}，预算={config.total_limit}")
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

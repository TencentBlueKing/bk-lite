"""完整门禁：应用与内嵌独立工具在各自进程中收集测试。"""

import os
import subprocess
import sys
from pathlib import Path

PPT_TESTS = Path("apps/opspilot/support-files/skill_packages/ppt-master/scripts/tests")


def run_suites(server_root: Path) -> int:
    server_root = server_root.resolve()
    ppt_tests = server_root / PPT_TESTS
    if not ppt_tests.is_dir():
        raise FileNotFoundError(f"内嵌PPT测试目录不存在：{ppt_tests}")
    reports = server_root / "test-results"
    reports.mkdir(exist_ok=True)
    print("运行Django应用测试套件", flush=True)
    application = subprocess.run(
        [sys.executable, "-m", "pytest", "--ignore", str(ppt_tests), "--junitxml", str(reports / "server.xml")],
        cwd=server_root,
    )
    # 不共享已导入的server.config，也不加载Django的配置、插件和autouse fixture。
    environment = os.environ.copy()
    for key in ("DJANGO_SETTINGS_MODULE", "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_CURRENT_TEST"):
        environment.pop(key, None)
    print("运行内嵌PPT工具测试套件", flush=True)
    embedded = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            os.devnull,
            "--noconftest",
            "-p",
            "no:django",
            "-p",
            "no:dotenv",
            "--junitxml",
            str(reports / "ppt-skill.xml"),
            "tests",
        ],
        cwd=ppt_tests.parent,
        env=environment,
    )
    return application.returncode or embedded.returncode


if __name__ == "__main__":
    raise SystemExit(run_suites(Path(__file__).resolve().parents[2]))

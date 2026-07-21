import importlib
import os
import subprocess
import sys
import warnings
from importlib.metadata import version
from pathlib import Path

import tomllib

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = STARGAZER_ROOT / "pyproject.toml"
LOCK_PATH = STARGAZER_ROOT / "uv.lock"
DOCKERFILE_PATH = STARGAZER_ROOT / "support-files" / "docker" / "Dockerfile"
README_PATH = STARGAZER_ROOT / "README.md"
TASK_QUEUE_CLI_PATH = STARGAZER_ROOT / "scripts" / "clear_task_queue.py"


def _read_toml(path: Path) -> dict:
    with path.open("rb") as file_obj:
        return tomllib.load(file_obj)


def _logical_dockerfile() -> str:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    return content.replace("\\\n", " ")


def test_pyproject_directly_pins_tracerite() -> None:
    dependencies = _read_toml(PYPROJECT_PATH)["project"]["dependencies"]

    assert "tracerite==1.1.3" in dependencies


def test_lock_contains_the_approved_tracerite_version() -> None:
    packages = _read_toml(LOCK_PATH)["package"]
    tracerite_packages = [
        package for package in packages if package["name"] == "tracerite"
    ]

    assert [package["version"] for package in tracerite_packages] == ["1.1.3"]


def test_dockerfile_installs_the_locked_uv_environment() -> None:
    dockerfile = _logical_dockerfile()

    assert "pip3 install uv==0.8.16" in dockerfile
    assert 'ENV PATH="/app/.venv/bin:$PATH"' in dockerfile
    assert dockerfile.count("uv sync ") == 2
    assert dockerfile.count("uv sync --locked --all-groups --all-extras") == 2
    assert '--default-index "$NEXUS_PYTHON_REPOSITY"' in dockerfile
    assert '--allow-insecure-host "$(echo $NEXUS_PYTHON_REPOSITY' in dockerfile
    assert "pip3 install -e" not in dockerfile


def test_docker_context_and_runbook_expose_task_queue_cleanup_cli() -> None:
    dockerfile = _logical_dockerfile()
    readme = README_PATH.read_text(encoding="utf-8")

    assert TASK_QUEUE_CLI_PATH.is_file()
    assert "ADD . ." in dockerfile
    assert "python /app/scripts/clear_task_queue.py" in readme
    assert "--all-pending" in readme
    assert "--include-in-progress" in readme
    assert "FLUSHDB" in readme


def test_locked_sync_rejects_stale_lockfile_offline(tmp_path: Path) -> None:
    uv_environment = {
        **os.environ,
        "UV_CACHE_DIR": str(tmp_path / ".uv-cache"),
    }
    uv_environment.pop("VIRTUAL_ENV", None)
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        """\
[project]
name = "dependency-lock-contract"
version = "0.1.1"
requires-python = ">=3.12"
dependencies = []

[tool.uv]
package = false
""",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        """\
version = 1
revision = 3
requires-python = ">=3.12"

[[package]]
name = "dependency-lock-contract"
version = "0.1.0"
source = { virtual = "." }
""",
        encoding="utf-8",
    )

    locked_sync = subprocess.run(
        ["uv", "sync", "--locked", "--offline", "--python", sys.executable],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=uv_environment,
    )
    output = f"{locked_sync.stdout}\n{locked_sync.stderr}".lower()

    assert locked_sync.returncode != 0
    assert "needs to be updated, but `--locked` was provided" in output


def test_sanic_imports_with_the_approved_tracerite_api() -> None:
    tracerite_html = importlib.import_module("tracerite.html")

    assert version("sanic") == "24.6.0"
    assert version("tracerite") == "1.1.3"
    assert hasattr(tracerite_html, "style")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=(
                "websockets\\.connection was renamed to "
                "websockets\\.protocol"
            ),
            category=DeprecationWarning,
            module="websockets\\.connection",
        )
        importlib.import_module("sanic")

import importlib
import warnings
from importlib.metadata import version
from pathlib import Path

import tomllib

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = STARGAZER_ROOT / "pyproject.toml"
LOCK_PATH = STARGAZER_ROOT / "uv.lock"
DOCKERFILE_PATH = STARGAZER_ROOT / "support-files" / "docker" / "Dockerfile"
README_PATH = STARGAZER_ROOT / "README.md"


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
    tracerite_packages = [package for package in packages if package["name"] == "tracerite"]

    assert [package["version"] for package in tracerite_packages] == ["1.1.3"]


def test_dockerfile_installs_pinned_dependencies_via_pip() -> None:
    dockerfile = _logical_dockerfile()

    assert 'pip3 install -e ".[dev,aliyun,qcloud,huawei,vmware,openstack,qingyun,snmp]"' in dockerfile
    assert 'pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY"' in dockerfile
    # uv sync --locked 会把 index 地址纳入锁校验，与 Nexus 私有源冲突，
    # 不得回到镜像构建路径（TencentBlueKing/bk-lite#4287）
    assert "uv sync" not in dockerfile


def test_arq_queue_runtime_is_absent_from_dependencies_and_runbook() -> None:
    dependencies = _read_toml(PYPROJECT_PATH)["project"]["dependencies"]
    readme = README_PATH.read_text(encoding="utf-8")

    assert not any(item.split("=", 1)[0] == "arq" for item in dependencies)
    assert "ARQ Worker" in readme
    assert "不把 Redis 当作任务队列" in readme


def test_runbook_documents_stateless_runtime_limits() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "MAX_ACTIVE_RUNS" in readme
    assert "MAX_ACTIVE_TARGETS" in readme
    assert "TARGET_TASK_WINDOW" in readme
    assert "REDIS_MAX_CONNECTIONS" in readme
    assert "REDIS_POOL_TIMEOUT" in readme
    assert "REDIS_PROTOCOL" in readme
    assert "PREFLIGHT_TIMEOUT" in readme
    assert "PROBE_TIMEOUT" in readme
    assert "COLLECTION_TIMEOUT" in readme
    assert "PUBLISH_TIMEOUT" in readme
    assert "PREFLIGHT_REACHABILITY" not in readme
    assert "params.ip_precheck" in readme
    assert "MAX_ACTIVE_TARGETS=0" not in readme


def test_sanic_imports_with_the_approved_tracerite_api() -> None:
    tracerite_html = importlib.import_module("tracerite.html")

    assert version("sanic") == "24.6.0"
    assert version("tracerite") == "1.1.3"
    assert hasattr(tracerite_html, "style")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=("websockets\\.connection was renamed to " "websockets\\.protocol"),
            category=DeprecationWarning,
            module="websockets\\.connection",
        )
        importlib.import_module("sanic")

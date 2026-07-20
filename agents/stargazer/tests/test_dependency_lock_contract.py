import importlib
import tomllib
from importlib.metadata import version
from pathlib import Path


STARGAZER_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = STARGAZER_ROOT / "pyproject.toml"
LOCK_PATH = STARGAZER_ROOT / "uv.lock"
DOCKERFILE_PATH = STARGAZER_ROOT / "support-files" / "docker" / "Dockerfile"


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


def test_dockerfile_installs_the_frozen_uv_environment() -> None:
    dockerfile = _logical_dockerfile()

    assert "pip3 install uv==0.8.16" in dockerfile
    assert 'ENV PATH="/app/.venv/bin:$PATH"' in dockerfile
    assert dockerfile.count("uv sync --frozen --all-groups --all-extras") == 2
    assert '--default-index "$NEXUS_PYTHON_REPOSITY"' in dockerfile
    assert '--allow-insecure-host "$(echo $NEXUS_PYTHON_REPOSITY' in dockerfile
    assert "pip3 install -e" not in dockerfile


def test_sanic_imports_with_the_approved_tracerite_api() -> None:
    tracerite_html = importlib.import_module("tracerite.html")

    assert version("sanic") == "24.6.0"
    assert version("tracerite") == "1.1.3"
    assert hasattr(tracerite_html, "style")
    importlib.import_module("sanic")

import os
import shutil
import sys
from pathlib import Path

from core.config import logger


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_dotenv_path() -> str | None:
    candidates = [Path.cwd() / ".env", application_root() / ".env"]
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists() and resolved.is_file():
            return str(resolved)
    return None


def find_config_path(explicit_path: str | None = None) -> str | None:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))

    candidates.extend(
        [
            Path.cwd() / "config.yml",
            Path.cwd() / "config.yaml",
            application_root() / "config.yml",
            application_root() / "config.yaml",
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists() and resolved.is_file():
            return str(resolved)
    return None


def current_entrypoint_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(application_root() / "main.py")]


def _has_ansible_windows_collection(collections_root: str | Path) -> bool:
    root = Path(collections_root).expanduser()
    namespace_root = root if root.name == "ansible_collections" else root / "ansible_collections"
    return (namespace_root / "ansible" / "windows" / "plugins" / "modules" / "win_copy.ps1").is_file()


def configure_ansible_environment() -> None:
    configured_path = os.environ.get("ANSIBLE_COLLECTIONS_PATH")
    if configured_path:
        collection_roots = [path for path in configured_path.split(os.pathsep) if path]
        if not any(_has_ansible_windows_collection(path) for path in collection_roots):
            raise RuntimeError(f"ANSIBLE_COLLECTIONS_PATH does not contain the ansible.windows win_copy module: {configured_path}")
        return
    root = application_root()
    candidates = [
        root / "collections",
        root / "ansible-executor" / "collections",
        root / "_internal" / "collections",
    ]
    invalid_candidates: list[Path] = []
    for collections_dir in candidates:
        if collections_dir.exists() and collections_dir.is_dir():
            if not _has_ansible_windows_collection(collections_dir):
                invalid_candidates.append(collections_dir)
                continue
            os.environ["ANSIBLE_COLLECTIONS_PATH"] = str(collections_dir)
            return
    if invalid_candidates:
        paths = os.pathsep.join(str(path) for path in invalid_candidates)
        raise RuntimeError(f"bundled Ansible collection path does not contain the ansible.windows win_copy module: {paths}")


def repair_ansible_windows_collection_layout(collections_path: str | Path) -> bool:
    collections_root = Path(collections_path)
    windows_root = collections_root / "ansible_collections" / "ansible" / "windows"
    if not windows_root.exists() or not windows_root.is_dir():
        return False

    repaired = False
    for path in windows_root.rglob("*"):
        nested_file = path / path.name
        if not path.is_dir() or not nested_file.is_file():
            continue
        backup_content = nested_file.read_bytes()
        shutil.rmtree(path)
        path.write_bytes(backup_content)
        repaired = True
        logger.warning(
            "repaired ansible windows collection entry: path=%s nested_file=%s",
            path,
            nested_file,
        )

    return repaired

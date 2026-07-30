import shutil
import subprocess
from pathlib import Path


def has_valid_ansible_windows_collection_layout(windows_root: Path) -> bool:
    module_file = windows_root / "plugins" / "modules" / "win_ping.ps1"
    return windows_root.exists() and module_file.is_file()


def ensure_ansible_windows_collection(
    collections_root: Path,
    cwd: Path | None = None,
) -> Path:
    root = Path(collections_root).resolve()
    windows_root = root / "ansible_collections" / "ansible" / "windows"
    if has_valid_ansible_windows_collection_layout(windows_root):
        return windows_root
    if (root / "ansible_collections").exists():
        shutil.rmtree(root / "ansible_collections")
    root.mkdir(parents=True, exist_ok=True)
    requirements_file = Path(__file__).resolve().parent / "collections" / "requirements.yml"
    subprocess.run(
        [
            "ansible-galaxy",
            "collection",
            "install",
            "-r",
            str(requirements_file),
            "-p",
            str(root),
            "--force",
        ],
        check=True,
        cwd=str(Path(cwd).resolve() if cwd else Path.cwd()),
    )
    return windows_root


def ansible_collections_root_to_datas(collections_root: Path) -> list[tuple[str, str]]:
    root = Path(collections_root).resolve() / "ansible_collections"
    return [(str(root), "collections")]

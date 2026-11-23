"""把仓库里的示例目录打成可上传的 zip。"""

import io
import zipfile
from pathlib import Path

_EXAMPLES = Path(__file__).resolve().parent / "examples"
_PACKS = {
    "integration": ("example_integration", "example_integration.zip"),
    "notification_channel": ("example_channel_template", "example_channel_template.zip"),
}


def example_archive(purpose: str) -> tuple[str, bytes]:
    try:
        directory_name, filename = _PACKS[purpose]
    except KeyError as exc:
        raise ValueError("Unknown provider pack example") from exc
    root = _EXAMPLES / directory_name
    if not (root / "__init__.py").is_file():
        raise ValueError("Provider pack example is missing")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            archive.write(path, f"{directory_name}/{path.relative_to(root).as_posix()}")
    return filename, buffer.getvalue()

"""Windows Server 长期服务版清单。

正式发布的下一代在这里加一行显示名和 Build。表单通过只读接口读取同一份清单。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowsServerVersion:
    label: str
    build: str


WINDOWS_SERVER_VERSIONS = (
    WindowsServerVersion("Windows Server 2016", "14393"),
    WindowsServerVersion("Windows Server 2019", "17763"),
    WindowsServerVersion("Windows Server 2022", "20348"),
    WindowsServerVersion("Windows Server 2025", "26100"),
)


def windows_version_options() -> list[dict[str, str]]:
    return [{"label": item.label, "build": item.build} for item in WINDOWS_SERVER_VERSIONS]


def catalog_build_for_product(label: str) -> str:
    normalized = " ".join(str(label or "").split()).casefold()
    if not normalized:
        return ""
    for item in WINDOWS_SERVER_VERSIONS:
        if item.label.casefold() == normalized:
            return item.build
    return ""


def normalize_windows_build(value: str) -> str:
    """取 BuildNumber 的主版本。月度修订号 20348.5761 仍归到 20348。"""
    text = str(value or "").strip()
    if not text:
        return ""
    head = text.split(".", 1)[0]
    return head if head.isdigit() else ""

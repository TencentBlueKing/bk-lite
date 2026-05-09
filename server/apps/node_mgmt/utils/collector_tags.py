from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


ARCHITECTURE_TAGS = {NodeConstants.X86_64_ARCH, NodeConstants.ARM64_ARCH}
OS_TAGS = {NodeConstants.LINUX_OS, NodeConstants.WINDOWS_OS}
APP_TAGS = {key for key, item in CollectorConstants.TAG_ENUM.items() if item["is_app"]}
KIND_TAGS = {key for key, item in CollectorConstants.TAG_ENUM.items() if not item["is_app"]} - OS_TAGS


def normalize_collector_tags(tags: list[str] | None, operating_system: str | None, cpu_architecture: str | None) -> list[str]:
    normalized_tags = []
    for tag in tags or []:
        value = str(tag).strip()
        if value and value not in normalized_tags:
            normalized_tags.append(value)

    normalized_os = str(operating_system or "").strip().lower()
    if normalized_os in OS_TAGS and normalized_os not in normalized_tags:
        normalized_tags.append(normalized_os)

    normalized_arch = normalize_cpu_architecture(cpu_architecture)
    if normalized_arch and normalized_arch not in normalized_tags:
        normalized_tags.append(normalized_arch)

    return normalized_tags


def split_collector_tags(tags: list[str] | None) -> dict[str, list[str]]:
    grouped = {"app": [], "os": [], "kind": [], "architecture": [], "other": []}
    for raw_tag in tags or []:
        tag = str(raw_tag).strip()
        if not tag:
            continue
        if tag in APP_TAGS:
            grouped["app"].append(tag)
        elif tag in OS_TAGS:
            grouped["os"].append(tag)
        elif tag in ARCHITECTURE_TAGS:
            grouped["architecture"].append(tag)
        elif tag in KIND_TAGS:
            grouped["kind"].append(tag)
        else:
            grouped["other"].append(tag)
    return grouped

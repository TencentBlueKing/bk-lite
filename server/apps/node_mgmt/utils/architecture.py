from apps.node_mgmt.constants.node import NodeConstants


def normalize_cpu_architecture(value: str | None) -> str:
    if not value:
        return NodeConstants.UNKNOWN_ARCH

    normalized = str(value).strip().lower()
    return NodeConstants.CPU_ARCH_ALIASES.get(normalized, NodeConstants.UNKNOWN_ARCH)


def display_cpu_architecture(value: str | None) -> str:
    normalized = normalize_cpu_architecture(value)
    if normalized == NodeConstants.ARM64_ARCH:
        return "ARM64"
    if normalized == NodeConstants.X86_64_ARCH:
        return NodeConstants.X86_64_ARCH
    return "--"

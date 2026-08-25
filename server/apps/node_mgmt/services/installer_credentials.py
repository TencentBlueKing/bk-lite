from apps.node_mgmt.constants.node import NodeConstants


INVALID_INSTALLER_CREDENTIALS_MODE_MESSAGE = (
    "NATS_INSTALLER_CREDENTIALS_MODE must be legacy or strict"
)


def normalize_installer_credentials_mode(value, *, allow_missing: bool = False) -> str:
    """规范化安装凭据迁移模式；只有配置项完全不存在时才兼容 legacy。"""
    if value is None and allow_missing:
        return NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_LEGACY

    normalized_value = str(value or "").strip().lower()
    supported_modes = {
        NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_LEGACY,
        NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_STRICT,
    }
    if normalized_value not in supported_modes:
        raise ValueError(INVALID_INSTALLER_CREDENTIALS_MODE_MESSAGE)
    return normalized_value

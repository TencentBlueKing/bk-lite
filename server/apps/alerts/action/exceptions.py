class ConfigError(Exception):
    """配置/数据缺失，记 config_error 不执行。"""


class TargetError(ConfigError):
    """目标主机无法解析（未纳管/不唯一）。"""

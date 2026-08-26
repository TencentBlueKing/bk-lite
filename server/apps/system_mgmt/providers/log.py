"""Provider 包日志入口。

包内 adapter / client 只从这里取 logger，不要 import apps.core.logger。
宿主（loader、runtime、view/serializer）继续直接用 system_mgmt_logger。
"""

from apps.core.logger import system_mgmt_logger as logger

__all__ = ["logger"]

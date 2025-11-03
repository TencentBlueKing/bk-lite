"""自定义异常类型"""


class LangSyncerError(Exception):
    """语言包同步工具基础异常"""

    pass


class ConfigError(LangSyncerError):
    """配置错误"""

    pass


class NotionAPIError(LangSyncerError):
    """Notion API 错误"""

    pass


class FileOperationError(LangSyncerError):
    """文件操作错误"""

    pass

class PackageConstants:
    """包管理相关常量"""

    # 包类型
    TYPE_COLLECTOR = "collector"
    TYPE_CONTROLLER = "controller"

    # 包类型中文名称映射
    TYPE_NAME_MAP = {
        TYPE_COLLECTOR: "采集器",
        TYPE_CONTROLLER: "控制器",
    }

    # 支持的文件扩展名（按优先级排序，双扩展名在前）
    SUPPORTED_EXTENSIONS = [
        '.tar.gz',
        '.tgz',
        '.zip',
        '.tar',
        '.gz',
        '.exe',
        '.deb',
        '.rpm',
    ]

    # 控制器默认包名称
    CONTROLLER_DEFAULT_PACKAGE_NAME = "fusion-collectors"

    # 版本号正则表达式模式
    # 匹配格式: name-version 或 name_version，支持可选的 v 前缀
    # 例如: xx-aa-1.0.0, telegraf-1.28.0, controller-v1.0.0
    VERSION_PATTERN = r'^(.+?)[-_]v?(\d+\.\d+\.\d+(?:\.\d+)?)(?:[-_].*)?$'

    # 错误提示信息
    ERROR_MSG_VERSION_NOT_FOUND = "上传失败，无法从文件名中识别版本号。文件名应包含版本号，格式如: xx-1.28.0.tar.gz"
    ERROR_MSG_TYPE_MISMATCH = "上传失败，上传文件与{type_name}类型不符。期望: {expected}，实际: {actual}"
    ERROR_MSG_VERSION_EXISTS = "上传失败，上传文件版本 {version} 已存在"


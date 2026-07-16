# -- coding: utf-8 --
"""
导入导出常量与枚举定义

本模块定义了YAML导入导出功能所需的全部常量、枚举和阈值配置。
包括：
- 对象类型枚举（画布对象、配置对象）
- 冲突处理策略枚举
- 导入导出阈值限制
- 敏感字段清单
- 错误码定义
"""

from enum import Enum


class ScopeType(str, Enum):
    """
    导出范围类型枚举

    canvas: 画布对象（仪表盘/拓扑/架构图）
    config: 配置对象（数据源/命名空间）
    """

    CANVAS = "canvas"
    CONFIG = "config"


class ObjectType(str, Enum):
    """
    对象类型枚举

    导入导出支持的全部对象类型，与数据库模型一一对应。
    """

    DASHBOARD = "dashboard"
    TOPOLOGY = "topology"
    ARCHITECTURE = "architecture"
    SCREEN = "screen"
    REPORT = "report"
    NETWORK_TOPOLOGY = "networkTopology"
    DATASOURCE = "datasource"
    NAMESPACE = "namespace"


# 画布类型集合，用于判断对象是否为画布对象
CANVAS_TYPES = {
    ObjectType.DASHBOARD,
    ObjectType.TOPOLOGY,
    ObjectType.ARCHITECTURE,
    ObjectType.SCREEN,
    ObjectType.REPORT,
    ObjectType.NETWORK_TOPOLOGY,
}

# 配置对象类型集合
CONFIG_TYPES = {ObjectType.DATASOURCE, ObjectType.NAMESPACE}


class ConflictAction(str, Enum):
    """
    冲突处理策略枚举

    skip: 跳过冲突对象，不执行导入
    overwrite: 全量覆盖目标环境已存在对象
    rename: 使用新名称创建对象，规则为 {原名称}_copy
    """

    SKIP = "skip"
    OVERWRITE = "overwrite"
    RENAME = "rename"


class ImportStatus(str, Enum):
    """
    导入状态枚举

    用于标识单个对象的导入结果状态。
    """

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    OVERWRITTEN = "overwritten"


# ===== 阈值配置 =====
# YAML最大文件大小限制（字节），超过此限制将拒绝导入
YAML_MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2MB

# 单次导入最大对象数量限制，超过此限制将拒绝导入
IMPORT_OBJECT_LIMIT = 200

# YAML schema版本号，用于版本兼容性检查
YAML_SCHEMA_VERSION = "1.1.0"


# ===== 敏感字段配置 =====
# 需要脱敏处理的敏感字段名列表
# 导出时这些字段将被替换为脱敏占位符，导入时需补充实际值
SENSITIVE_FIELDS = frozenset({"password", "secret", "token"})

# 连接器配置允许嵌套自定义 headers/body，敏感键不一定是固定字段名。
# 与数据源 API 的脱敏口径保持一致，避免 Authorization、api_key 等配置随 YAML 导出。
SENSITIVE_FIELD_KEYWORDS = ("password", "token", "secret", "authorization", "api_key", "apikey")


def is_sensitive_field_name(field: object) -> bool:
    normalized = str(field).lower()
    return any(keyword in normalized for keyword in SENSITIVE_FIELD_KEYWORDS)

# 敏感字段脱敏后的占位符值
SENSITIVE_PLACEHOLDER = "******"


# ===== 业务键分隔符 =====
# 用于构建复合业务键，例如 datasource.name + "::" + datasource.rest_api
BUSINESS_KEY_SEPARATOR = "::"


# ===== 重命名后缀 =====
# 冲突处理选择rename时追加的后缀
RENAME_SUFFIX = "_copy"


# ===== 错误码定义 =====
class ImportExportErrorCode:
    """
    导入导出错误码定义

    所有错误码以 OA_ 前缀标识，便于在日志和接口返回中快速定位问题来源。
    """

    # YAML格式与结构错误
    YAML_TOO_LARGE = "OA_YAML_TOO_LARGE"
    IMPORT_OBJECT_LIMIT_EXCEEDED = "OA_IMPORT_OBJECT_LIMIT_EXCEEDED"
    YAML_PARSE_ERROR = "OA_YAML_PARSE_ERROR"
    YAML_SCHEMA_INVALID = "OA_YAML_SCHEMA_INVALID"
    YAML_OBJECT_COUNTS_MISMATCH = "OA_YAML_OBJECT_COUNTS_MISMATCH"
    YAML_EMPTY_IMPORT = "OA_YAML_EMPTY_IMPORT"

    # 非法引用错误
    YAML_ID_REFERENCE_FORBIDDEN = "OA_YAML_ID_REFERENCE_FORBIDDEN"

    # 导入执行错误
    IMPORT_CONFLICT_UNRESOLVED = "OA_IMPORT_CONFLICT_UNRESOLVED"
    IMPORT_TARGET_DIRECTORY_REQUIRED = "OA_IMPORT_TARGET_DIRECTORY_REQUIRED"
    IMPORT_DEPENDENCY_MISSING = "OA_IMPORT_DEPENDENCY_MISSING"
    IMPORT_SECRET_REQUIRED = "OA_IMPORT_SECRET_REQUIRED"
    IMPORT_PERMISSION_DENIED = "OA_IMPORT_PERMISSION_DENIED"


# 错误码对应的默认错误消息
ERROR_MESSAGES = {
    ImportExportErrorCode.YAML_TOO_LARGE: "YAML文件大小超过2MB限制",
    ImportExportErrorCode.IMPORT_OBJECT_LIMIT_EXCEEDED: "导入对象数量超过200个限制",
    ImportExportErrorCode.YAML_PARSE_ERROR: "YAML语法解析错误",
    ImportExportErrorCode.YAML_SCHEMA_INVALID: "YAML schema结构不合法",
    ImportExportErrorCode.YAML_OBJECT_COUNTS_MISMATCH: "YAML对象统计与实际内容不一致",
    ImportExportErrorCode.YAML_EMPTY_IMPORT: "YAML中没有可导入对象",
    ImportExportErrorCode.YAML_ID_REFERENCE_FORBIDDEN: "YAML中不允许使用数据库ID作为引用",
    ImportExportErrorCode.IMPORT_CONFLICT_UNRESOLVED: "存在未决策的冲突对象",
    ImportExportErrorCode.IMPORT_TARGET_DIRECTORY_REQUIRED: "画布导入必须指定目标目录",
    ImportExportErrorCode.IMPORT_DEPENDENCY_MISSING: "依赖对象缺失",
    ImportExportErrorCode.IMPORT_SECRET_REQUIRED: "新建对象缺少必填敏感字段",
    ImportExportErrorCode.IMPORT_PERMISSION_DENIED: "当前用户没有导入所需权限",
}


# ===== 对象章节名称映射 =====
# YAML中各对象类型对应的章节名称
OBJECT_TYPE_TO_SECTION = {
    ObjectType.DASHBOARD: "dashboards",
    ObjectType.TOPOLOGY: "topologies",
    ObjectType.ARCHITECTURE: "architectures",
    ObjectType.SCREEN: "screens",
    ObjectType.REPORT: "reports",
    ObjectType.NETWORK_TOPOLOGY: "network_topologies",
    ObjectType.DATASOURCE: "datasources",
    ObjectType.NAMESPACE: "namespaces",
}

# 章节名称到对象类型的反向映射
SECTION_TO_OBJECT_TYPE = {v: k for k, v in OBJECT_TYPE_TO_SECTION.items()}


# ===== 冲突原因描述 =====
class ConflictReason:
    """冲突原因枚举"""

    # 名称冲突：当前组织可访问该记录
    NAME_CONFLICT = "name_conflict"
    # 无权限冲突：记录存在但当前组织无权访问（只允许重命名）
    NO_PERMISSION_CONFLICT = "no_permission_conflict"


# ===== 警告码定义 =====
class ImportExportWarningCode:
    """导入导出警告码定义"""

    SECRET_PLACEHOLDER = "OA_SECRET_PLACEHOLDER"

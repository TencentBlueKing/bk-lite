"""数据库操作相关常量"""


class DatabaseConstants:
    """数据库批量操作常量"""

    # 批量创建/更新操作的默认批次大小
    BULK_CREATE_BATCH_SIZE = 100
    BULK_UPDATE_BATCH_SIZE = 100


class CloudRegionConstants:
    """云区域相关常量"""

    # 默认云区域配置
    DEFAULT_CLOUD_REGION_ID = 1
    DEFAULT_CLOUD_REGION_NAME = "default"
    DEFAULT_CLOUD_REGION_INTRODUCTION = "default cloud region!"


class EnvVariableConstants:
    """环境变量相关常量"""

    # 默认云区域环境变量前缀
    DEFAULT_ZONE_ENV_PREFIX = "DEFAULT_ZONE_VAR_"

    # 敏感字段识别关键词（用于判断是否需要加密）
    SENSITIVE_FIELD_KEYWORD = "password"

    # 环境变量类型
    TYPE_SECRET = "secret"
    TYPE_NORMAL = ""

    # 敏感信息掩码
    SECRET_MASK = "******"

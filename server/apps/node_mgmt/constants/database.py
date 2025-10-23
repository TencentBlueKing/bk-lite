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


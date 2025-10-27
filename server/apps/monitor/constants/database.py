"""数据库操作相关常量"""


class DatabaseConstants:
    """数据库批量操作常量"""

    # 批量创建/更新操作的默认批次大小
    BULK_CREATE_BATCH_SIZE = 200
    BULK_UPDATE_BATCH_SIZE = 200

    # 特定场景的批次大小
    COLLECT_CONFIG_BATCH_SIZE = 100
    EVENT_RAW_DATA_BATCH_SIZE = 100
    MONITOR_OBJECT_BATCH_SIZE = 100


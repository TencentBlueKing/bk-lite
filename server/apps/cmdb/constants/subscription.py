"""
订阅功能常量定义

包含：
- 筛选类型枚举：FilterType
- 触发类型枚举：TriggerType
- 触发类型显示映射：TRIGGER_TYPE_CHOICES
- 任务调度与锁相关常量
- 查询与展示相关常量
"""
from enum import Enum


class FilterType(str, Enum):
    """实例筛选类型"""

    CONDITION = "condition"  # 过滤条件模式
    INSTANCES = "instances"  # 实例选择模式


class TriggerType(str, Enum):
    """触发事件类型"""

    ATTRIBUTE_CHANGE = "attribute_change"  # 属性变化
    RELATION_CHANGE = "relation_change"  # 关联变化
    EXPIRATION = "expiration"  # 临近到期
    INSTANCE_ADDED = "instance_added"  # 实例新增
    INSTANCE_DELETED = "instance_deleted"  # 实例删除


# 触发类型显示名称映射
TRIGGER_TYPE_CHOICES = {
    TriggerType.ATTRIBUTE_CHANGE.value: "属性变化",
    TriggerType.RELATION_CHANGE.value: "关联变化",
    TriggerType.EXPIRATION.value: "临近到期",
    TriggerType.INSTANCE_ADDED.value: "实例新增",
    TriggerType.INSTANCE_DELETED.value: "实例删除",
}

# ========== 任务调度与锁 ==========

# 规则检查调度间隔（分钟）
SUBSCRIPTION_CHECK_INTERVAL = 2

# 发送锁超时秒数，防止同一分钟内重复执行
# 设为 55 秒略小于 60 秒，确保锁在下一分钟调度前自动过期
SEND_LOCK_TIMEOUT = 55

# ========== 查询与展示 ==========

# 实例分页查询大小
INSTANCE_QUERY_PAGE_SIZE = 1000

# 通知内容展示的最大实例数（超出则聚合展示）
NOTIFICATION_MAX_DISPLAY_INSTANCES = 5

# 值截断最大长度（用于日志和通知展示）
VALUE_TRUNCATE_LENGTH = 50

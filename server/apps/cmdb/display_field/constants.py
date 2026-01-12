# -- coding: utf-8 --
"""
Display Field 模块常量定义

集中管理所有 display_field 相关的常量，避免硬编码和重复定义

注意: DISPLAY_FIELD_CONFIG 已移动到 apps.cmdb.constants.constants 中
"""

# ========== 字段类型常量 ==========

# 需要生成 _display 冗余字段的字段类型
DISPLAY_FIELD_TYPES = frozenset(['organization', 'user', 'enum'])

# 组织类型字段
FIELD_TYPE_ORGANIZATION = 'organization'

# 用户类型字段
FIELD_TYPE_USER = 'user'

# 枚举类型字段
FIELD_TYPE_ENUM = 'enum'

# ========== 字段后缀常量 ==========

# 冗余字段后缀（用于生成 _display 字段名）
DISPLAY_SUFFIX = '_display'

# 例如: organization → organization_display
#      created_by → created_by_display
#      status → status_display


# ========== 分隔符常量 ==========

# 多值字段的分隔符（用于 organization 和 user 类型）
DISPLAY_VALUES_SEPARATOR = ', '

# 例如: "技术部, 运维组, 北京分公司"
#      "管理员(admin), 普通用户(user01)"


# ========== 用户显示格式常量 ==========

# 用户显示格式模板
USER_DISPLAY_FORMAT = '{display_name}({username})'

# 例如: "管理员(admin)"
#      "普通用户(user01)"


# ========== 缓存相关常量 ==========

# 排除字段列表缓存 key
CACHE_KEY_EXCLUDE_FIELDS = 'cmdb:exclude_fields:all'

# 模型字段映射缓存 key
CACHE_KEY_MODEL_FIELDS_MAPPING = 'cmdb:model_fields_mapping'

# 缓存过期时间（秒）- 默认 1 小时
CACHE_TTL_SECONDS = 3600

# ========== 导出兼容 ==========

# 为了向后兼容，保留旧的常量名（已废弃，建议使用上面的新常量）
IS_PLAY_SUFFIX = DISPLAY_SUFFIX  # 已废弃，使用 DISPLAY_SUFFIX

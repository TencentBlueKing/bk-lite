# -- coding: utf-8 --
"""
Display Field 模块常量定义

集中管理所有 display_field 相关的常量，避免硬编码和重复定义

注意: DISPLAY_FIELD_CONFIG 已移动到 apps.cmdb.constants.constants 中
"""

# ========== 字段类型常量 ==========

# 需要生成 _display 冗余字段的字段类型
DISPLAY_FIELD_TYPES = frozenset(["organization", "user", "enum", "tag", "table"])

# 敏感字段类型：值为密文，排除出全文检索且**不**生成 _display（刻意不可搜索）。
# 与展示型/文件型不同——后者排除原值但靠 _display 仍可搜，敏感型则完全不进索引。
SENSITIVE_FIELD_TYPES = frozenset(["pwd"])

# 组织类型字段
FIELD_TYPE_ORGANIZATION = "organization"

# 用户类型字段
FIELD_TYPE_USER = "user"

# 枚举类型字段
FIELD_TYPE_ENUM = "enum"

# 标签类型字段
FIELD_TYPE_TAG = "tag"

# 表格类型字段
FIELD_TYPE_TABLE = "table"

# ========== 字段后缀常量 ==========

# 冗余字段后缀（用于生成 _display 字段名）
DISPLAY_SUFFIX = "_display"

# 例如: organization → organization_display
#      created_by → created_by_display
#      status → status_display


# ========== 分隔符常量 ==========

# 多值字段的分隔符（用于 organization 和 user 类型）
DISPLAY_VALUES_SEPARATOR = ", "

# 例如: "技术部, 运维组, 北京分公司"
#      "管理员(admin), 普通用户(user01)"


# ========== 用户显示格式常量 ==========

# 用户显示格式模板
USER_DISPLAY_FORMAT = "{display_name}({username})"

# 例如: "管理员(admin)"
#      "普通用户(user01)"


# ========== 缓存相关常量 ==========

# 排除字段列表缓存 key
CACHE_KEY_EXCLUDE_FIELDS = "cmdb:exclude_fields:all"

# 模型字段映射缓存 key
CACHE_KEY_MODEL_FIELDS_MAPPING = "cmdb:model_fields_mapping"

# 模型 attrs 缓存 key 前缀
CACHE_KEY_MODEL_ATTRS_PREFIX = "cmdb:model_attrs:"

# P2-2.6: 已缓存 model_id 索引集合,用于 clear_cache 精准删具体 model attrs key
# (本仓 cache 后端 locmem/Django-RedisCache 都不支持 delete_pattern,原兜底只 log warning)
CACHE_KEY_MODEL_ATTRS_INDEX = "cmdb:model_attrs:__index__"

# 缓存过期时间（秒）- 默认 1 小时
CACHE_TTL_SECONDS = 3600

# ========== 导出兼容 ==========

# 为了向后兼容，保留旧的常量名（已废弃，建议使用上面的新常量）
IS_PLAY_SUFFIX = DISPLAY_SUFFIX  # 已废弃，使用 DISPLAY_SUFFIX

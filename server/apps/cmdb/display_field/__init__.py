# -- coding: utf-8 --
"""
显示字段(Display Field)模块

职责：
1. 为 organization/user/enum 类型字段生成可搜索的 _display 冗余字段
2. 维护和同步 _display 字段的数据一致性
3. 管理全文检索需要排除的字段缓存

模块结构：
- handler: 显示字段处理器，负责实例创建/更新时的冗余字段生成
- initializer: 显示字段初始化器，用于历史数据批量初始化
- sync: 显示字段同步器，当组织/用户信息变更时同步更新实例
- cache: 字段缓存管理器，管理需要排除的字段列表和模型字段映射

使用示例：
    # 实例创建时生成 _display 字段
    from apps.cmdb.display_field import DisplayFieldHandler
    instance_data = DisplayFieldHandler.build_display_fields(model_id, instance_data, attrs)
    
    # 批量初始化历史数据
    from apps.cmdb.display_field import DisplayFieldInitializer
    initializer = DisplayFieldInitializer()
    result = initializer.initialize_all()
    
    # 同步用户/组织变更
    from apps.cmdb.display_field import sync_display_fields_for_system_mgmt
    sync_display_fields_for_system_mgmt(users=[{"id": 1, "username": "admin", "display_name": "管理员"}])
    
    # 缓存管理
    from apps.cmdb.display_field import ExcludeFieldsCache
    exclude_fields = ExcludeFieldsCache.get_exclude_fields()
"""

# Constants (常量定义)
from .constants import (
    DISPLAY_FIELD_TYPES,
    DISPLAY_SUFFIX,
    FIELD_TYPE_ORGANIZATION,
    FIELD_TYPE_USER,
    FIELD_TYPE_ENUM,
    DISPLAY_VALUES_SEPARATOR,
    USER_DISPLAY_FORMAT,
)

# Handler (显示字段处理器)
from .handler import (
    DisplayFieldConverter,
    DisplayFieldHandler,
)

# Initializer (显示字段初始化器)
from .initializer import (
    DisplayFieldInitializer,
    display_field_initializer,
)

# Sync (显示字段同步器)
from .sync import (
    DisplayFieldSynchronizer,
    sync_display_fields_for_system_mgmt,
)

# Cache (字段缓存管理器)
from .cache import (
    ExcludeFieldsCache,
    init_all_caches_on_startup,
)

__all__ = [
    # Constants
    'DISPLAY_FIELD_TYPES',
    'DISPLAY_SUFFIX',
    'FIELD_TYPE_ORGANIZATION',
    'FIELD_TYPE_USER',
    'FIELD_TYPE_ENUM',
    'DISPLAY_VALUES_SEPARATOR',
    'USER_DISPLAY_FORMAT',
    
    # Handler
    'DisplayFieldConverter',
    'DisplayFieldHandler',
    
    # Initializer
    'DisplayFieldInitializer',
    'display_field_initializer',
    
    # Sync
    'DisplayFieldSynchronizer',
    'sync_display_fields_for_system_mgmt',
    
    # Cache
    'ExcludeFieldsCache',
    'init_all_caches_on_startup',
]

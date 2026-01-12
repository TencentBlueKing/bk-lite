# -- coding: utf-8 --
"""
排除字段缓存管理器

职责：
1. 项目启动时读取所有模型的 organization/user/enum 类型字段
2. 缓存到 Redis，TTL 为 1 小时
3. 模型字段变更时动态更新缓存
4. 为全文检索提供需要排除的字段列表

缓存策略：
- 缓存key: cmdb:exclude_fields:all
- TTL: 3600秒（1小时）
- 数据格式: ["organization", "created_by", "status", ...]
- 更新时机: 启动时初始化 + 模型字段变更时

设计原则：
- 单次查询：所有缓存数据来自同一次模型查询，避免重复DB访问
- 统一管理：初始化/更新/清空/刷新使用统一的内部逻辑
- 按需构建：根据 cache_key 选择对应的数据构建策略
"""
from typing import List, Set, Dict, Any
from django.core.cache import cache

from apps.cmdb.constants.constants import MODEL
from apps.cmdb.display_field.constants import (
    DISPLAY_FIELD_TYPES,
    CACHE_KEY_EXCLUDE_FIELDS,
    CACHE_KEY_MODEL_FIELDS_MAPPING,
    CACHE_TTL_SECONDS,
)
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.core.logger import cmdb_logger as logger


class ExcludeFieldsCache:
    """
    排除字段缓存管理器
    管理全文检索时需要排除的原始字段列表（organization/user/enum类型）
    使用 Redis 缓存，定期刷新，支持统一的缓存管理逻辑
    
    常量说明:
    - EXCLUDE_FIELDS_KEY: 缓存 key（从 constants 导入）
    - MODEL_FIELDS_MAPPING_KEY: 缓存 key（从 constants 导入）
    - CACHE_TTL: 缓存过期时间（从 constants 导入）
    - EXCLUDE_FIELD_TYPES: 排除的字段类型（从 constants 导入 DISPLAY_FIELD_TYPES）
    - MAPPING_FIELD_TYPES: 需要映射的字段类型（从 DISPLAY_FIELD_TYPES 派生）
    """

    # 缓存配置（使用统一的常量）
    EXCLUDE_FIELDS_KEY = CACHE_KEY_EXCLUDE_FIELDS
    MODEL_FIELDS_MAPPING_KEY = CACHE_KEY_MODEL_FIELDS_MAPPING
    CACHE_TTL = CACHE_TTL_SECONDS

    # 需要排除的字段类型（使用统一的常量）
    EXCLUDE_FIELD_TYPES = DISPLAY_FIELD_TYPES
    # 需要映射的字段类型（用户和组织）
    MAPPING_FIELD_TYPES = {'organization', 'user'}

    # ========== 对外接口 ==========

    @classmethod
    def initialize_all(cls) -> bool:
        """
        初始化所有缓存（项目启动时调用）
        
        工作流程：
        1. 清除所有旧缓存
        2. 查询一次模型数据
        3. 构建所有缓存数据
        4. 存入 Redis
        
        Returns:
            初始化是否成功
            
        Usage:
            from apps.cmdb.display_field.cache import ExcludeFieldsCache
            ExcludeFieldsCache.initialize_all()
        """
        logger.info("[ExcludeFieldsCache] 开始初始化所有缓存（每次启动强制刷新）...")
        
        try:
            # 清除所有缓存
            cls._clear_all_caches()
            
            # 从数据库加载一次模型数据，构建所有缓存
            success = cls._refresh_all_caches()
            
            if success:
                logger.info("[ExcludeFieldsCache] 所有缓存初始化成功")
            else:
                logger.error("[ExcludeFieldsCache] 缓存初始化失败")
            
            return success
            
        except Exception as e:
            logger.error(f"[ExcludeFieldsCache] 缓存初始化异常: {e}", exc_info=True)
            return False

    @classmethod
    def get_exclude_fields(cls) -> List[str]:
        """
        获取需要排除的字段列表（用于全文检索）
        
        Returns:
            需要排除的字段名列表，如 ['organization', 'created_by', 'status']
        """
        return cls._get_or_load_cache(
            cache_key=cls.EXCLUDE_FIELDS_KEY,
            default_value=[],
            cache_name="排除字段列表"
        )

    @classmethod
    def get_model_fields_mapping(cls) -> Dict[str, Dict[str, List[str]]]:
        """
        获取模型字段映射（用于获取每个模型的用户和组织字段）
        
        Returns:
            模型字段映射字典，格式如：
            {
                "host": {
                    "organization": ["organization"],
                    "user": ["manage_user"]
                }
            }
        """
        return cls._get_or_load_cache(
            cache_key=cls.MODEL_FIELDS_MAPPING_KEY,
            default_value={},
            cache_name="模型字段映射"
        )

    @classmethod
    def update_on_model_change(cls, model_id: str) -> bool:
        """
        模型字段变更时更新所有缓存
        
        使用场景：
        - 模型新增字段
        - 模型修改字段类型
        - 模型删除字段
        
        Args:
            model_id: 发生变更的模型ID

        Returns:
            更新是否成功
        """
        logger.info(f"[ExcludeFieldsCache] 模型变更触发缓存更新, 模型: {model_id}")
        
        try:
            # 全量刷新所有缓存（确保完整性）
            success = cls._refresh_all_caches()
            
            if success:
                logger.info(f"[ExcludeFieldsCache] 缓存更新成功, 模型: {model_id}")
            else:
                logger.error(f"[ExcludeFieldsCache] 缓存更新失败, 模型: {model_id}")
            
            return success
            
        except Exception as e:
            logger.error(
                f"[ExcludeFieldsCache] 缓存更新异常, 模型: {model_id}, 错误: {e}",
                exc_info=True
            )
            return False

    @classmethod
    def clear_cache(cls) -> bool:
        """
        清除所有缓存（用于测试或手动刷新）
        
        Returns:
            清除是否成功
        """
        return cls._clear_all_caches()

    @classmethod
    def refresh_cache(cls) -> bool:
        """
        强制刷新所有缓存（从数据库重新加载）
        
        Returns:
            刷新是否成功
        """
        logger.info("[ExcludeFieldsCache] 强制刷新所有缓存...")
        return cls._refresh_all_caches()

    @classmethod
    def get_cache_info(cls) -> dict:
        """
        获取缓存信息（用于监控和调试）
        
        Returns:
            缓存信息字典，包含字段数、缓存键、TTL等
        """
        try:
            exclude_fields = cache.get(cls.EXCLUDE_FIELDS_KEY)
            model_fields_mapping = cache.get(cls.MODEL_FIELDS_MAPPING_KEY)

            return {
                'exclude_fields': {
                    'cache_key': cls.EXCLUDE_FIELDS_KEY,
                    'ttl': cls.CACHE_TTL,
                    'is_cached': exclude_fields is not None,
                    'field_count': len(exclude_fields) if exclude_fields else 0,
                    'fields': exclude_fields if exclude_fields else []
                },
                'model_fields_mapping': {
                    'cache_key': cls.MODEL_FIELDS_MAPPING_KEY,
                    'ttl': cls.CACHE_TTL,
                    'is_cached': model_fields_mapping is not None,
                    'model_count': len(model_fields_mapping) if model_fields_mapping else 0,
                    'mapping': model_fields_mapping if model_fields_mapping else {}
                }
            }
        except Exception as e:
            logger.error(f"[ExcludeFieldsCache] 获取缓存信息失败: {e}")
            return {
                'exclude_fields': {
                    'cache_key': cls.EXCLUDE_FIELDS_KEY,
                    'ttl': cls.CACHE_TTL,
                    'is_cached': False,
                    'field_count': 0,
                    'fields': [],
                    'error': str(e)
                },
                'model_fields_mapping': {
                    'cache_key': cls.MODEL_FIELDS_MAPPING_KEY,
                    'ttl': cls.CACHE_TTL,
                    'is_cached': False,
                    'model_count': 0,
                    'mapping': {},
                    'error': str(e)
                }
            }

    # ========== 内部统一缓存管理逻辑 ==========

    @classmethod
    def _get_or_load_cache(cls, cache_key: str, default_value: Any, cache_name: str) -> Any:
        """
        统一的缓存获取逻辑
        
        Args:
            cache_key: 缓存键
            default_value: 缓存未命中时的默认值
            cache_name: 缓存名称（用于日志）
        
        Returns:
            缓存值或默认值
        """
        try:
            cached_value = cache.get(cache_key)
            
            if cached_value is not None:
                logger.debug(f"[ExcludeFieldsCache] {cache_name}缓存命中")
                return cached_value
            
            # 缓存未命中，重新加载所有缓存
            logger.warning(f"[ExcludeFieldsCache] {cache_name}缓存未命中，重新加载所有缓存...")
            cls._refresh_all_caches()
            
            # 再次尝试获取
            cached_value = cache.get(cache_key)
            return cached_value if cached_value is not None else default_value
            
        except Exception as e:
            logger.error(f"[ExcludeFieldsCache] 获取{cache_name}失败: {e}", exc_info=True)
            return default_value

    @classmethod
    def _refresh_all_caches(cls) -> bool:
        """
        刷新所有缓存（核心逻辑：单次查询，构建所有缓存）
        
        Returns:
            刷新是否成功
        """
        try:
            # 1. 单次查询所有模型数据
            models_data = cls._load_models_from_db()
            
            # 2. 基于同一份数据构建不同缓存
            exclude_fields = cls._build_exclude_fields(models_data)
            model_fields_mapping = cls._build_model_fields_mapping(models_data)
            
            # 3. 保存所有缓存
            success1 = cls._save_cache(cls.EXCLUDE_FIELDS_KEY, exclude_fields)
            success2 = cls._save_cache(cls.MODEL_FIELDS_MAPPING_KEY, model_fields_mapping)
            
            success = success1 and success2
            
            if success:
                logger.info(
                    f"[ExcludeFieldsCache] 所有缓存刷新成功, "
                    f"排除字段数: {len(exclude_fields)}, "
                    f"模型映射数: {len(model_fields_mapping)}"
                )
            
            return success
            
        except Exception as e:
            logger.error(f"[ExcludeFieldsCache] 刷新缓存失败: {e}", exc_info=True)
            return False

    @classmethod
    def _clear_all_caches(cls) -> bool:
        """
        清除所有缓存
        
        Returns:
            清除是否成功
        """
        try:
            cache.delete(cls.EXCLUDE_FIELDS_KEY)
            cache.delete(cls.MODEL_FIELDS_MAPPING_KEY)
            logger.info("[ExcludeFieldsCache] 所有缓存已清除")
            return True
        except Exception as e:
            logger.error(f"[ExcludeFieldsCache] 清除缓存失败: {e}")
            return False

    # ========== 数据加载与构建逻辑 ==========

    @classmethod
    def _load_models_from_db(cls) -> List[Dict[str, Any]]:
        """
        从数据库加载所有模型数据（单次查询，供所有缓存使用）
        
        Returns:
            模型数据列表
        """
        try:
            with GraphClient() as ag:
                models, _ = ag.query_entity(MODEL, [])
            
            return models
            
        except Exception as e:
            logger.error(f"[ExcludeFieldsCache] 从数据库加载模型失败: {e}", exc_info=True)
            return []

    @classmethod
    def _build_exclude_fields(cls, models: List[Dict[str, Any]]) -> List[str]:
        """
        构建排除字段列表（从模型数据中提取）
        
        Args:
            models: 模型数据列表
        
        Returns:
            排除字段列表（去重且排序）
        """
        all_exclude_fields: Set[str] = set()
        
        for model in models:
            model_id = model.get('model_id')
            attrs_json = model.get('attrs', '[]')
            
            try:
                # 延迟导入避免循环依赖
                from apps.cmdb.services.model import ModelManage
                attrs = ModelManage.parse_attrs(attrs_json)
                
                for attr in attrs:
                    attr_id = attr.get('attr_id')
                    attr_type = attr.get('attr_type')
                    
                    if attr_type in cls.EXCLUDE_FIELD_TYPES:
                        all_exclude_fields.add(attr_id)
                        
            except Exception as e:
                logger.warning(f"[ExcludeFieldsCache] 解析模型 {model_id} 字段失败: {e}")
                continue
        
        result = list(all_exclude_fields)
        logger.debug(f"[ExcludeFieldsCache] 构建排除字段列表完成, 字段数: {len(result)}")
        return result

    @classmethod
    def _build_model_fields_mapping(cls, models: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[str]]]:
        """
        构建模型字段映射（从模型数据中提取）
        
        Args:
            models: 模型数据列表
        
        Returns:
            模型字段映射字典，格式如：
            {
                "host": {
                    "organization": ["organization"],
                    "user": ["manage_user"]
                }
            }
        """
        model_fields_mapping = {}
        
        for model in models:
            model_id = model.get('model_id')
            attrs_json = model.get('attrs', '[]')
            
            try:
                # 延迟导入避免循环依赖
                from apps.cmdb.services.model import ModelManage
                attrs = ModelManage.parse_attrs(attrs_json)
                
                # 初始化当前模型的字段映射
                model_mapping = {
                    'organization': [],
                    'user': []
                }
                
                # 提取需要映射的字段
                for attr in attrs:
                    attr_id = attr.get('attr_id')
                    attr_type = attr.get('attr_type')
                    
                    if attr_type == 'organization':
                        model_mapping['organization'].append(attr_id)
                    elif attr_type == 'user':
                        model_mapping['user'].append(attr_id)
                
                # 只保存有用户或组织字段的模型
                if model_mapping['organization'] or model_mapping['user']:
                    model_fields_mapping[model_id] = model_mapping
                    
            except Exception as e:
                logger.warning(f"[ExcludeFieldsCache] 解析模型 {model_id} 字段映射失败: {e}")
                continue
        
        logger.debug(
            f"[ExcludeFieldsCache] 构建模型字段映射完成, "
            f"有映射字段的模型数: {len(model_fields_mapping)}"
        )
        return model_fields_mapping

    @classmethod
    def _save_cache(cls, cache_key: str, data: Any) -> bool:
        """
        统一的缓存保存逻辑
        
        Args:
            cache_key: 缓存键
            data: 要保存的数据
        
        Returns:
            保存是否成功
        """
        try:
            cache.set(cache_key, data, timeout=cls.CACHE_TTL)
            logger.debug(f"[ExcludeFieldsCache] 缓存已更新, key: {cache_key}, TTL: {cls.CACHE_TTL}s")
            return True
            
        except Exception as e:
            logger.error(f"[ExcludeFieldsCache] 保存缓存失败, key: {cache_key}, 错误: {e}", exc_info=True)
            return False


# ========== 项目启动时初始化入口 ==========

def init_all_caches_on_startup() -> bool:
    """
    项目启动时初始化所有缓存（主入口）
    
    该函数应在 Django AppConfig.ready() 中调用，确保项目启动时：
    1. 清除所有旧缓存
    2. 从数据库加载最新模型数据
    3. 构建并缓存所有需要的数据
    
    Returns:
        初始化是否成功
        
    Usage:
        # 在 apps/cmdb/apps.py 的 CmdbConfig.ready() 方法中调用
        from apps.cmdb.display_field import init_all_caches_on_startup
        
        def ready(self):
            init_all_caches_on_startup()
    """
    logger.info("[CacheManager] 项目启动，开始初始化所有缓存...")
    
    try:
        success = ExcludeFieldsCache.initialize_all()
        
        if success:
            logger.info("[CacheManager] 项目启动缓存初始化成功")
        else:
            logger.error("[CacheManager] 项目启动缓存初始化失败")
        
        return success
        
    except Exception as e:
        logger.error(f"[CacheManager] 项目启动缓存初始化异常: {e}", exc_info=True)
        return False


# ========== 向后兼容的便捷方法 ==========

def initialize_exclude_fields_cache() -> bool:
    """
    初始化排除字段缓存（向后兼容方法）
    
    Returns:
        初始化是否成功
    """
    return ExcludeFieldsCache.initialize_all()


def initialize_model_fields_mapping_cache() -> bool:
    """
    初始化模型字段映射缓存（向后兼容方法）
    
    Returns:
        初始化是否成功
    """
    return ExcludeFieldsCache.initialize_all()


# 便捷别名
exclude_fields_cache = ExcludeFieldsCache()

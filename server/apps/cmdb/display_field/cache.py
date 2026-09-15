# -- coding: utf-8 --
"""CMDB 字段元数据缓存。

缓存只保存可重建的查询投影：全局字段元数据在首次使用时从模型事实构建，单模型
attrs 在首次读取时按 model_id 加载，模型写入成功后主动失效相关缓存。项目启动不
读取、不清理也不预热这些缓存。
"""

from typing import Any, Dict, Iterable, List, Set

from django.core.cache import cache

from apps.cmdb.constants.constants import MODEL
from apps.cmdb.display_field.constants import (
    CACHE_KEY_FIELD_METADATA,
    CACHE_KEY_MODEL_ATTRS_INDEX,
    CACHE_KEY_MODEL_ATTRS_PREFIX,
    CACHE_TTL_SECONDS,
    DISPLAY_FIELD_TYPES,
    LEGACY_CACHE_KEY_EXCLUDE_FIELDS,
    LEGACY_CACHE_KEY_MODEL_ATTRS_INDEX,
    LEGACY_CACHE_KEY_MODEL_ATTRS_PREFIX,
    LEGACY_CACHE_KEY_MODEL_FIELDS_MAPPING,
    SENSITIVE_FIELD_TYPES,
)
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_call_chain, safe_exception_info


class ExcludeFieldsCache:
    """为全文检索和展示字段同步提供按需缓存的字段元数据。"""

    FIELD_METADATA_KEY = CACHE_KEY_FIELD_METADATA
    MODEL_ATTRS_KEY_PREFIX = CACHE_KEY_MODEL_ATTRS_PREFIX
    MODEL_ATTRS_INDEX_KEY = CACHE_KEY_MODEL_ATTRS_INDEX
    CACHE_TTL = CACHE_TTL_SECONDS

    EXCLUDE_FIELD_TYPES = DISPLAY_FIELD_TYPES
    MAPPING_FIELD_TYPES = {"organization", "user"}

    @classmethod
    def get_exclude_fields(cls) -> List[str]:
        """返回全文检索应排除的原始字段名。"""
        return list(cls._get_or_load_global_metadata()["exclude_fields"])

    @classmethod
    def get_model_fields_mapping(cls) -> Dict[str, Dict[str, List[str]]]:
        """返回各模型的 organization/user 字段映射。"""
        return dict(cls._get_or_load_global_metadata()["model_fields_mapping"])

    @classmethod
    def get_model_attrs(cls, model_id: str) -> list:
        """按 model_id 返回标准化并补充唯一规则信息后的模型 attrs。"""
        cache_key = cls._model_attrs_key(model_id)
        cached_attrs = cls._read_cache(cache_key)
        if cached_attrs is not None:
            logger.debug("event=cmdb_model_attrs_cache_hit model_id=%s", model_id)
            return cached_attrs

        logger.debug("event=cmdb_model_attrs_cache_miss model_id=%s", model_id)
        attrs = cls._load_model_attrs(model_id)
        cls._cache_model_attrs(model_id, attrs)
        return attrs

    @classmethod
    def update_on_model_change(cls, model_id: str) -> bool:
        """模型结构变化后失效该模型 attrs 和全局字段元数据。"""
        return cls.invalidate_models([model_id], include_global_metadata=True)

    @classmethod
    def invalidate_model_attrs(cls, model_id: str) -> bool:
        """模型展示定义或唯一规则变化后只失效该模型 attrs。"""
        return cls.invalidate_models([model_id], include_global_metadata=False)

    @classmethod
    def invalidate_models(cls, model_ids: Iterable[str], *, include_global_metadata: bool = True) -> bool:
        """批量失效模型缓存，不触发事实源查询。"""
        normalized_ids = sorted({str(model_id).strip() for model_id in model_ids if model_id is not None and str(model_id).strip()})
        keys = [cls._model_attrs_key(model_id) for model_id in normalized_ids]
        keys.extend(f"{LEGACY_CACHE_KEY_MODEL_ATTRS_PREFIX}{model_id}" for model_id in normalized_ids)
        if include_global_metadata:
            keys.extend(
                [
                    cls.FIELD_METADATA_KEY,
                    LEGACY_CACHE_KEY_EXCLUDE_FIELDS,
                    LEGACY_CACHE_KEY_MODEL_FIELDS_MAPPING,
                ]
            )

        try:
            if keys:
                cache.delete_many(keys)
            cls._discard_model_attrs_index(normalized_ids, cls.MODEL_ATTRS_INDEX_KEY)
            cls._discard_model_attrs_index(normalized_ids, LEGACY_CACHE_KEY_MODEL_ATTRS_INDEX)
            logger.debug(
                "event=cmdb_field_cache_invalidated model_count=%s include_global_metadata=%s",
                len(normalized_ids),
                include_global_metadata,
            )
            return True
        except Exception as exc:
            logger.error(
                "event=cmdb_field_cache_invalidation_failed model_count=%s include_global_metadata=%s failed_stage=%s error_type=%s call_chain=%s",
                len(normalized_ids),
                include_global_metadata,
                "delete_cache_keys",
                type(exc).__name__,
                safe_exception_call_chain(exc),
                exc_info=safe_exception_info(exc),
            )
            return False

    @classmethod
    def refresh_cache(cls) -> bool:
        """从模型事实刷新全局字段元数据；失败时保留已有缓存。"""
        try:
            metadata = cls._load_global_metadata()
            if not cls._save_cache(cls.FIELD_METADATA_KEY, metadata):
                return False
            logger.info(
                "event=cmdb_field_metadata_cache_refreshed exclude_field_count=%s mapped_model_count=%s",
                len(metadata["exclude_fields"]),
                len(metadata["model_fields_mapping"]),
            )
            return True
        except Exception as exc:
            logger.error(
                "event=cmdb_field_metadata_cache_refresh_failed failed_stage=%s error_type=%s call_chain=%s",
                "load_model_metadata",
                type(exc).__name__,
                safe_exception_call_chain(exc),
                exc_info=safe_exception_info(exc),
            )
            return False

    @classmethod
    def refresh_model_attrs(cls, model_id: str) -> bool:
        """从模型事实刷新指定模型 attrs；失败时保留已有缓存。"""
        try:
            attrs = cls._load_model_attrs(model_id)
            if not cls._cache_model_attrs(model_id, attrs):
                return False
            logger.info("event=cmdb_model_attrs_cache_refreshed model_id=%s attr_count=%s", model_id, len(attrs))
            return True
        except Exception as exc:
            logger.error(
                "event=cmdb_model_attrs_cache_refresh_failed model_id=%s failed_stage=%s error_type=%s call_chain=%s",
                model_id,
                "load_model_attrs",
                type(exc).__name__,
                safe_exception_call_chain(exc),
                exc_info=safe_exception_info(exc),
            )
            return False

    @classmethod
    def clear_cache(cls) -> bool:
        """清除全局字段元数据和索引登记的单模型 attrs。"""
        try:
            cls._purge_all_model_attrs_cache()
            cache.delete_many(
                [
                    cls.FIELD_METADATA_KEY,
                    LEGACY_CACHE_KEY_EXCLUDE_FIELDS,
                    LEGACY_CACHE_KEY_MODEL_FIELDS_MAPPING,
                ]
            )
            logger.info("event=cmdb_field_cache_cleared")
            return True
        except Exception as exc:
            logger.error(
                "event=cmdb_field_cache_clear_failed failed_stage=%s error_type=%s call_chain=%s",
                "delete_cache_keys",
                type(exc).__name__,
                safe_exception_call_chain(exc),
                exc_info=safe_exception_info(exc),
            )
            return False

    @classmethod
    def get_cache_info(cls) -> dict:
        """返回全局字段元数据缓存的有界状态摘要。"""
        metadata = cls._read_cache(cls.FIELD_METADATA_KEY)
        valid = cls._is_valid_global_metadata(metadata)
        exclude_fields = metadata["exclude_fields"] if valid else []
        model_fields_mapping = metadata["model_fields_mapping"] if valid else {}
        return {
            "exclude_fields": {
                "cache_key": cls.FIELD_METADATA_KEY,
                "ttl": cls.CACHE_TTL,
                "is_cached": valid,
                "field_count": len(exclude_fields),
            },
            "model_fields_mapping": {
                "cache_key": cls.FIELD_METADATA_KEY,
                "ttl": cls.CACHE_TTL,
                "is_cached": valid,
                "model_count": len(model_fields_mapping),
            },
        }

    @classmethod
    def _get_or_load_global_metadata(cls) -> dict:
        metadata = cls._read_cache(cls.FIELD_METADATA_KEY)
        if cls._is_valid_global_metadata(metadata):
            logger.debug("event=cmdb_field_metadata_cache_hit")
            return metadata

        logger.debug("event=cmdb_field_metadata_cache_miss")
        metadata = cls._load_global_metadata()
        cls._save_cache(cls.FIELD_METADATA_KEY, metadata)
        return metadata

    @classmethod
    def _load_global_metadata(cls) -> dict:
        return cls._build_global_metadata(cls._load_models_from_db())

    @classmethod
    def _load_models_from_db(cls) -> List[Dict[str, Any]]:
        with GraphClient() as graph:
            models, _ = graph.query_entity(MODEL, [])
        return models

    @classmethod
    def _load_model_attrs(cls, model_id: str) -> list:
        from apps.cmdb.services.model import ModelManage

        return ModelManage.search_model_attr(model_id)

    @classmethod
    def _build_global_metadata(cls, models: List[Dict[str, Any]]) -> dict:
        parsed_models = cls._parse_models(models)
        return {
            "exclude_fields": cls._build_exclude_fields_from_parsed(parsed_models),
            "model_fields_mapping": cls._build_model_fields_mapping_from_parsed(parsed_models),
        }

    @classmethod
    def _parse_models(cls, models: List[Dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
        from apps.cmdb.services.model import ModelManage

        parsed_models = []
        for model in models:
            model_id = str(model.get("model_id") or "").strip()
            if not model_id:
                raise ValueError("模型字段元数据缺少 model_id")
            attrs = ModelManage.parse_attrs(model.get("attrs", "[]"))
            if not isinstance(attrs, list) or any(not isinstance(attr, dict) for attr in attrs):
                raise ValueError(f"模型 {model_id} 的 attrs 不是对象列表")
            parsed_models.append((model_id, attrs))
        return parsed_models

    @classmethod
    def _build_exclude_fields(cls, models: List[Dict[str, Any]]) -> List[str]:
        """由模型事实构建全文检索排除字段，主要供测试和诊断复用。"""
        return cls._build_exclude_fields_from_parsed(cls._parse_models(models))

    @classmethod
    def _build_exclude_fields_from_parsed(cls, parsed_models: list[tuple[str, list[dict[str, Any]]]]) -> List[str]:
        from apps.cmdb.model_ops.extensions import is_file_attr_type

        exclude_fields: Set[str] = set()
        for model_id, attrs in parsed_models:
            for attr in attrs:
                attr_id = str(attr.get("attr_id") or "").strip()
                if not attr_id:
                    raise ValueError(f"模型 {model_id} 的字段缺少 attr_id")
                attr_type = attr.get("attr_type")
                if attr_type in cls.EXCLUDE_FIELD_TYPES or attr_type in SENSITIVE_FIELD_TYPES or is_file_attr_type(attr_type):
                    exclude_fields.add(attr_id)
        return sorted(exclude_fields)

    @classmethod
    def _build_model_fields_mapping(cls, models: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[str]]]:
        """由模型事实构建 organization/user 字段映射，主要供测试和诊断复用。"""
        return cls._build_model_fields_mapping_from_parsed(cls._parse_models(models))

    @classmethod
    def _build_model_fields_mapping_from_parsed(cls, parsed_models: list[tuple[str, list[dict[str, Any]]]]) -> Dict[str, Dict[str, List[str]]]:
        mapping = {}
        for model_id, attrs in parsed_models:
            model_mapping = {"organization": [], "user": []}
            for attr in attrs:
                attr_id = str(attr.get("attr_id") or "").strip()
                if not attr_id:
                    raise ValueError(f"模型 {model_id} 的字段缺少 attr_id")
                attr_type = attr.get("attr_type")
                if attr_type in cls.MAPPING_FIELD_TYPES:
                    model_mapping[attr_type].append(attr_id)
            if model_mapping["organization"] or model_mapping["user"]:
                model_mapping["organization"].sort()
                model_mapping["user"].sort()
                mapping[model_id] = model_mapping
        return mapping

    @staticmethod
    def _is_valid_global_metadata(metadata: Any) -> bool:
        return (
            isinstance(metadata, dict) and isinstance(metadata.get("exclude_fields"), list) and isinstance(metadata.get("model_fields_mapping"), dict)
        )

    @classmethod
    def _model_attrs_key(cls, model_id: str) -> str:
        return f"{cls.MODEL_ATTRS_KEY_PREFIX}{model_id}"

    @classmethod
    def _cache_model_attrs(cls, model_id: str, attrs: list) -> bool:
        if not cls._save_cache(cls._model_attrs_key(model_id), attrs):
            return False
        index = cls._get_model_attrs_index(cls.MODEL_ATTRS_INDEX_KEY)
        index.add(model_id)
        cls._set_model_attrs_index(index, cls.MODEL_ATTRS_INDEX_KEY)
        return True

    @classmethod
    def _read_cache(cls, cache_key: str) -> Any:
        try:
            return cache.get(cache_key)
        except Exception as exc:
            logger.warning(
                "event=cmdb_field_cache_read_failed cache_key=%s failed_stage=%s error_type=%s",
                cache_key,
                "read_cache",
                type(exc).__name__,
            )
            return None

    @classmethod
    def _save_cache(cls, cache_key: str, data: Any) -> bool:
        try:
            cache.set(cache_key, data, timeout=cls.CACHE_TTL)
            return True
        except Exception as exc:
            logger.warning(
                "event=cmdb_field_cache_write_failed cache_key=%s failed_stage=%s error_type=%s",
                cache_key,
                "write_cache",
                type(exc).__name__,
            )
            return False

    @classmethod
    def _get_model_attrs_index(cls, index_key: str) -> set[str]:
        raw = cls._read_cache(index_key)
        if isinstance(raw, (set, list, tuple)):
            return {str(model_id) for model_id in raw}
        return set()

    @classmethod
    def _set_model_attrs_index(cls, index: set[str], index_key: str) -> bool:
        return cls._save_cache(index_key, sorted(index))

    @classmethod
    def _discard_model_attrs_index(cls, model_ids: Iterable[str], index_key: str) -> None:
        index = cls._get_model_attrs_index(index_key)
        next_index = index - set(model_ids)
        if next_index != index:
            cls._set_model_attrs_index(next_index, index_key)

    @classmethod
    def _purge_all_model_attrs_cache(cls) -> int:
        total = 0
        for index_key, key_prefix in (
            (cls.MODEL_ATTRS_INDEX_KEY, cls.MODEL_ATTRS_KEY_PREFIX),
            (LEGACY_CACHE_KEY_MODEL_ATTRS_INDEX, LEGACY_CACHE_KEY_MODEL_ATTRS_PREFIX),
        ):
            model_ids = cls._get_model_attrs_index(index_key)
            if model_ids:
                cache.delete_many([f"{key_prefix}{model_id}" for model_id in model_ids])
            cache.delete(index_key)
            total += len(model_ids)
        return total


exclude_fields_cache = ExcludeFieldsCache()

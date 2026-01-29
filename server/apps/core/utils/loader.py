import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import yaml

from apps.core.logger import logger

# 全局缓存: {(app, lang): translations_dict}
# 缓存永不过期，进程重启时自动清空，部署时通过 preload_language_cache() 预热
_translation_cache: Dict[Tuple[str, str], dict] = {}
_cache_lock = threading.Lock()


class LanguageLoader:
    def __init__(self, app: str, default_lang: str = "en"):
        self.app = app
        self.base_dir = f"apps/{app}/language"
        self.default_lang = default_lang
        self.translations = self._get_cached_translations(default_lang)

    def _get_cached_translations(self, lang: str) -> dict:
        """
        从缓存获取翻译数据，如果缓存不存在则加载。

        缓存策略:
        - 使用 (app, lang) 作为缓存键
        - 缓存永不过期（进程生命周期内有效）
        - 部署时通过 preload_language_cache() 预热
        - 线程安全
        """
        cache_key = (self.app, lang)

        # 先检查缓存 (无锁快速路径)
        cached = _translation_cache.get(cache_key)
        if cached is not None:
            return cached

        # 缓存未命中，加锁加载
        with _cache_lock:
            # 双重检查，避免重复加载
            cached = _translation_cache.get(cache_key)
            if cached is not None:
                return cached

            # 加载并缓存
            translations = self._load_language_file(lang)
            _translation_cache[cache_key] = translations
            return translations

    def _load_language_file(self, lang: str) -> dict:
        """加载指定语言的 yaml 文件"""
        file_path = os.path.join(self.base_dir, f"{lang}.yaml")

        if not os.path.exists(file_path):
            logger.warning(f"Language file not found: {file_path}, using empty translations")
            return {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load language file: {file_path}, error: {e}")
            return {}

    def load_language(self, lang: str):
        """加载指定语言的yaml文件 (兼容旧接口)"""
        self.translations = self._get_cached_translations(lang)

    def get(self, key: str, default: Optional[str] = None) -> Optional[Any]:
        """
        使用点号路径获取翻译。
        例如:
          os.linux -> language.yaml 中的 os -> linux
          cloud_region.default.name -> language.yaml 中的 cloud_region -> default -> name
        """
        parts = key.split(".")
        if not parts:
            return default

        # 从根节点开始查找
        value = self.translations

        # 递归查找
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
                if value is None:
                    return default
            else:
                return default

        return value if value is not None else default


def clear_language_cache(app: Optional[str] = None, lang: Optional[str] = None) -> None:
    """
    清除语言缓存。

    Args:
        app: 指定应用名称，None 表示所有应用
        lang: 指定语言，None 表示所有语言

    用法:
        clear_language_cache()  # 清除所有缓存
        clear_language_cache(app="opspilot")  # 清除 opspilot 的所有语言缓存
        clear_language_cache(app="opspilot", lang="en")  # 清除特定缓存
    """
    with _cache_lock:
        if app is None and lang is None:
            _translation_cache.clear()
        else:
            keys_to_remove = [key for key in _translation_cache if (app is None or key[0] == app) and (lang is None or key[1] == lang)]
            for key in keys_to_remove:
                del _translation_cache[key]


# 支持的语言列表
SUPPORTED_LANGUAGES = ["en", "zh-Hans"]

# 需要预热的应用列表
PRELOAD_APPS = ["opspilot", "core", "cmdb", "monitor", "node_mgmt", "system_mgmt"]


def preload_language_cache(apps: Optional[List[str]] = None, languages: Optional[List[str]] = None) -> dict:
    """
    预热语言缓存，在部署时（如 batch_init）调用。

    Args:
        apps: 要预热的应用列表，None 表示使用默认列表 PRELOAD_APPS
        languages: 要预热的语言列表，None 表示使用默认列表 SUPPORTED_LANGUAGES

    Returns:
        dict: 预热结果统计 {"loaded": [...], "failed": [...], "skipped": [...]}

    用法:
        # 在 batch_init 命令中调用
        from apps.core.utils.loader import preload_language_cache
        preload_language_cache()  # 预热所有默认应用和语言
    """
    apps = apps or PRELOAD_APPS
    languages = languages or SUPPORTED_LANGUAGES

    result = {"loaded": [], "failed": [], "skipped": []}

    for app in apps:
        for lang in languages:
            cache_key = (app, lang)

            # 跳过已缓存的
            if cache_key in _translation_cache:
                result["skipped"].append(f"{app}/{lang}")
                continue

            try:
                loader = LanguageLoader(app=app, default_lang=lang)
                if loader.translations:
                    result["loaded"].append(f"{app}/{lang}")
                    logger.info(f"Preloaded language cache: {app}/{lang}")
                else:
                    result["skipped"].append(f"{app}/{lang}")
            except Exception as e:
                result["failed"].append(f"{app}/{lang}")
                logger.error(f"Failed to preload language cache {app}/{lang}: {e}")

    logger.info(
        f"Language cache preload complete: "
        f"{len(result['loaded'])} loaded, "
        f"{len(result['skipped'])} skipped, "
        f"{len(result['failed'])} failed"
    )
    return result

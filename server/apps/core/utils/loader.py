import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import yaml

from apps.core.logger import logger

# 全局缓存: {(app, lang): translations_dict}
# 缓存永不过期，进程重启时自动清空，部署时通过 preload_language_cache() 预热
_translation_cache: Dict[Tuple[str, str], dict] = {}
_cache_lock = threading.Lock()

# 插件翻译与调用它的 app 无关；以语言和插件根目录共享，避免 core/cmdb/monitor
# 各自冷加载时重复扫描同一批插件。根目录进入 key，保证测试和运行时配置切换安全。
_plugin_translation_cache: Dict[Tuple[str, str, str], dict] = {}
_plugin_cache_lock = threading.Lock()


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

    def _load_language_dir(self, lang: str) -> dict:
        """扫描 apps/<app>/language/ 下所有 *..yaml,deep-merge。

        目录仅作物理组织;key 第一级 = 文件名(去 .yaml),与历史完全兼容。
        不包括 enterprise、plugins 目录,这两个由 _load_language_file / _load_plugin_language 单独处理。
        只加载文件名匹配目标语言的文件(如 lang='en' 只读 en.yaml,不支持 zh-Hans.yaml 跨语言污染)。
        _legacy.yaml 等以语言后缀命名(如 _legacy_en.yaml)来保持跨语言隔离。
        """
        result = {}
        if not os.path.isdir(self.base_dir):
            return result
        for root, _, files in os.walk(self.base_dir):
            for name in sorted(files):
                if not name.endswith(".yaml"):
                    continue
                # 只加载文件名以目标语言开头/结尾的 yaml
                # 例如 lang='en' 匹配: en.yaml, _legacy_en.yaml, core/monitor_object_en.yaml
                # lang='zh-Hans' 匹配: zh-Hans.yaml, _legacy_zh-Hans.yaml, core/monitor_object_zh-Hans.yaml,
                #   以及无语言后缀的子目录文件(如中文遗留文件 core/monitor_object.yaml)
                # 规则: name 包含目标语言后缀 OR (无任何语言后缀 AND lang in (en, zh-Hans))
                has_lang_suffix = name.startswith(f"{lang}.") or name.endswith(f"_{lang}.yaml") or name == f"{lang}.yaml"
                has_any_lang_suffix = any(name.endswith(f"_{l}.yaml") or name == f"{l}.yaml" for l in ("en", "zh-Hans"))
                if not has_lang_suffix and has_any_lang_suffix:
                    continue
                path = os.path.join(root, name)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        sub = yaml.safe_load(f) or {}
                        result = self._deep_merge(result, sub)
                except Exception as e:
                    logger.error(f"Failed to load language file: {path}, error: {e}")
        return result

    def _load_plugin_language(self, lang: str) -> dict:
        """复用 plugin_migrate 的发现机制找 plugin,扫同目录 language/<lang>.yaml。

        复用 find_files_by_pattern(已支持 3/4 层目录兼容),读 metrics.json 的 plugin 字段
        作为翻译 key 第一段。文件缺失记录 warning,不抛异常;文件内顶层 key 与 plugin 字段
        不一致时记录 error 并跳过。
        """
        # 延迟导入避免 apps.monitor 在 apps.core 启动阶段被全量加载
        from apps.monitor.constants.plugin import PluginConstants
        from apps.monitor.management.utils import find_files_by_pattern

        roots = (PluginConstants.DIRECTORY, PluginConstants.ENTERPRISE_DIRECTORY)
        cache_key = (lang, *roots)
        cached = _plugin_translation_cache.get(cache_key)
        if cached is not None:
            return cached

        with _plugin_cache_lock:
            cached = _plugin_translation_cache.get(cache_key)
            if cached is not None:
                return cached

            collected: Dict[str, Any] = {}
            for root in roots:
                if not os.path.isdir(root):
                    continue
                for metrics_path in find_files_by_pattern(root, filename_pattern="metrics.json"):
                    try:
                        with open(metrics_path, "r", encoding="utf-8") as f:
                            plugin_data = json.load(f)
                    except Exception as e:
                        logger.error(f"Failed to read {metrics_path}: {e}")
                        continue
                    plugin_name = plugin_data.get("plugin")
                    if not plugin_name:
                        continue
                    lang_file = os.path.join(os.path.dirname(metrics_path), "language", f"{lang}.yaml")
                    if not os.path.isfile(lang_file):
                        logger.warning(f"Plugin language missing: {lang_file}")
                        continue
                    try:
                        with open(lang_file, "r", encoding="utf-8") as f:
                            sub = yaml.safe_load(f) or {}
                        if plugin_name in sub:
                            plugin_desc = sub.pop(plugin_name)
                            sub.setdefault("monitor_object_plugin", {})[plugin_name] = plugin_desc
                        collected = self._deep_merge(collected, sub)
                    except Exception as e:
                        logger.error(f"Failed to load {lang_file}: {e}")

            _plugin_translation_cache[cache_key] = collected
            return collected

    def _load_enterprise_language(self, lang: str) -> dict:
        """扫描 apps/<app>/enterprise/language/ 下匹配目标语言的 *.yaml,deep-merge。

        与 _load_language_dir 同样逻辑但扫 enterprise 目录,作为最高优先级覆盖。
        只加载文件名匹配目标语言的文件(如 lang='en' 只读 en.yaml),避免 zh-Hans.yaml
        在 deep-merge 时覆盖英文翻译。
        注:legacy 单文件模式(en.yaml 直接放全部企业翻译)在 Task 5 拆分为子文件前仍被读取。
        """
        result = {}
        enterprise_root = f"apps/{self.app}/enterprise/language"
        if not os.path.isdir(enterprise_root):
            return result
        for root, _, files in os.walk(enterprise_root):
            for name in sorted(files):
                if not name.endswith(".yaml"):
                    continue
                # 与 _load_language_dir 相同过滤:跳过其他语言后缀的 yaml
                has_lang_suffix = (
                    name.startswith(f"{lang}.")
                    or name.endswith(f"_{lang}.yaml")
                    or name == f"{lang}.yaml"
                )
                has_any_lang_suffix = any(
                    name.endswith(f"_{l}.yaml") or name == f"{l}.yaml" for l in ("en", "zh-Hans")
                )
                if not has_lang_suffix and has_any_lang_suffix:
                    continue
                path = os.path.join(root, name)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        sub = yaml.safe_load(f) or {}
                        result = self._deep_merge(result, sub)
                except Exception as e:
                    logger.error(f"Failed to load enterprise language file: {path}, error: {e}")
        return result

    def _load_language_file(self, lang: str) -> dict:
        """加载多源翻译并按优先级合并:base → plugins → enterprise。

        base = apps/<app>/language/ 多 yaml(跨 plugin 共享翻译)
        plugins = apps/monitor/support-files/plugins/**/language/<lang>.yaml(plugin 翻译)
        enterprise = apps/<app>/enterprise/language/ 多 yaml(企业版覆盖,优先级最高)
        """
        base = self._load_language_dir(lang)
        plugins = self._load_plugin_language(lang) if self.app == "monitor" else {}
        enterprise = self._load_enterprise_language(lang)

        result = self._deep_merge(base, plugins)
        result = self._deep_merge(result, enterprise)

        if not result:
            logger.warning(f"No translations loaded for app={self.app} lang={lang}")
        return result

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """深度合并两个字典，override 中的值会覆盖 base 中的值"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

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
            with _plugin_cache_lock:
                _plugin_translation_cache.clear()
        else:
            keys_to_remove = [key for key in _translation_cache if (app is None or key[0] == app) and (lang is None or key[1] == lang)]
            for key in keys_to_remove:
                del _translation_cache[key]
            if app is None or app == "monitor":
                with _plugin_cache_lock:
                    plugin_keys = [key for key in _plugin_translation_cache if lang is None or key[0] == lang]
                    for key in plugin_keys:
                        del _plugin_translation_cache[key]


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

import os

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.loader import LanguageLoader


class SettingLanguage:
    """
    Monitor应用的语言翻译服务
    提供统一的多语言翻译接口
    """

    # 类型名称到YAML文件的映射
    TYPE_MAPPING = {
        "MONITOR_OBJECT_TYPE": "monitor_object_type",
        "MONITOR_OBJECT": "monitor_object",
        "MONITOR_OBJECT_PLUGIN": "monitor_object_plugin",
        "MONITOR_OBJECT_METRIC_GROUP": "monitor_object_metric_group",
        "MONITOR_OBJECT_METRIC": "monitor_object_metric",
    }

    def __init__(self, language: str):
        """
        初始化语言翻译服务

        Args:
            language: 语言代码，如 "zh-Hans", "zh", "en"
        """
        self.language = self._normalize_language(language)
        self.loader = LanguageLoader(app="monitor", default_lang=self.language)

    def _normalize_language(self, language: str) -> str:
        """标准化语言代码"""
        # 优先使用环境变量设置的默认语言
        language = os.getenv("DEFAULT_LANGUAGE", language)

        # 语言代码映射
        lang_map = {
            "zh-Hans": "zh",
            "zh_Hans": "zh",
            "en": "en",
        }

        normalized = lang_map.get(language, language)

        if normalized not in ("zh", "en"):
            raise BaseAppException(f"Language '{language}' not supported")

        return normalized

    def get_val(self, _type: str, key: str):
        """
        获取翻译值

        Args:
            _type: 类型，如 MONITOR_OBJECT_TYPE, MONITOR_OBJECT 等
            key: 要查询的键

        Returns:
            翻译后的值，如果不存在则返回 None

        示例:
            lan.get_val("MONITOR_OBJECT_TYPE", "OS")  # 返回 "操作系统"
            lan.get_val("MONITOR_OBJECT", "Host")     # 返回 "主机"
        """
        yaml_file = self.TYPE_MAPPING.get(_type)
        if not yaml_file:
            return None

        file_data = self.loader.translations.get(yaml_file)
        return file_data.get(key) if file_data else None

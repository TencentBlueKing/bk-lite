import os

import yaml


class LanguageLoader:
    def __init__(self, app: str, default_lang: str = "en"):
        self.base_dir = f"apps/{app}/language"
        self.default_lang = self.map_language(default_lang)
        self.translations = {}
        self.load_language()

    # 语言文件映射zh-Hans - > zh
    def map_language(self, lang: str) -> str:
        """映射语言代码"""
        lang_mappings = {
            "zh-Hans": "zh",
            "zh-CN": "zh",
            "zh": "zh",
            "en-US": "en",
            "en": "en",
        }
        return lang_mappings.get(lang, lang)
    

    def load_language(self):
        """加载指定语言目录下的所有yaml文件"""
        lang_dir = os.path.join(self.base_dir, self.default_lang)
        if not os.path.exists(lang_dir):
            raise FileNotFoundError(f"Language directory '{lang_dir}' not found")

        translations = {}
        for file_name in os.listdir(lang_dir):
            if file_name.endswith(".yaml"):
                file_path = os.path.join(lang_dir, file_name)
                key = os.path.splitext(file_name)[0]  # xxx.yaml -> xxx
                with open(file_path, "r", encoding="utf-8") as f:
                    translations[key] = yaml.safe_load(f) or {}

        self.translations = translations

    def get(self, key: str, default: str = None) -> str:
        """
        使用点号路径获取翻译.
        例如:
          xxx.greeting -> xxx.yaml 中的 greeting
          xxx.error.not_found -> xxx.yaml 中的 error -> not_found
        """
        parts = key.split(".")
        if not parts:
            return default

        # 文件名（不带扩展名）
        file_key = parts[0]
        value = self.translations.get(file_key)

        if value is None:
            return default

        # 递归查找
        for part in parts[1:]:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return default

        return value if value is not None else default


# # 示例用法
# from apps.core.utils.loader import LanguageLoader
# loader = LanguageLoader(app="node_mgmt", default_lang="en")
# print(loader.get("os.linux"))
# print(loader.get("cloudregion.default.name"))

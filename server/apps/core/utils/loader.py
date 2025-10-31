import os

import yaml


class LanguageLoader:
    def __init__(self, app: str, default_lang: str = "en"):
        self.base_dir = f"apps/{app}/language"
        self.default_lang = default_lang
        self.translations = {}
        self.load_language(default_lang)

    def load_language(self, lang: str):
        """加载指定语言目录下的language.yaml文件"""
        lang_dir = os.path.join(self.base_dir, lang)
        if not os.path.exists(lang_dir):
            raise FileNotFoundError(f"Language directory '{lang_dir}' not found")

        # 加载合并后的 language.yaml 文件
        file_path = os.path.join(lang_dir, "language.yaml")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Language file '{file_path}' not found")

        with open(file_path, "r", encoding="utf-8") as f:
            self.translations = yaml.safe_load(f) or {}

    def get(self, key: str, default: str = None) -> str:
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


# # 示例用法
# from apps.core.utils.loader import LanguageLoader
# loader = LanguageLoader(app="node_mgmt", default_lang="en")
# print(loader.get("os.linux"))
# print(loader.get("cloudregion.default.name"))

from apps.core.utils.loader import LanguageLoader


class SettingLanguage:
    """
    CMDB 语言服务，使用统一的 LanguageLoader 加载语言包
    """

    def __init__(self, language: str):
        self.loader = LanguageLoader(app="cmdb", default_lang=language)
        self.language_dict = self.loader.translations

    def get_language_dict(self, language: str):
        """兼容旧方法，已废弃"""
        return self.loader.translations

    def get_val(self, _type: str, key: str):
        """
        获取翻译值
        _type: 类型，如 CLASSIFICATION, MODEL, ATTR, ASSOCIATION_TYPE, ChangeRecordType 等
        key: 键值
        """
        if _type == "ATTR":
            return self.loader.get(f"ATTR.{key}") or self.loader.get("DEFAULT_ATTR")
        return self.loader.get(f"{_type}.{key}")

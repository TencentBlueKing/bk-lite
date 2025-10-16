import os

from apps.core.exceptions.base_app_exception import BaseAppException


class SettingLanguage:
    def __init__(self, language: str):
        self.language_dict = self.get_language_dict(language)

    def get_language_dict(self, language: str):
        default_language = os.getenv("DEFAULT_LANGUAGE")
        if default_language:
            language = default_language
        if language == "zh-Hans":
            from apps.monitor.language.pack.zh import LANGUAGE_DICT
        elif language == "en":
            from apps.monitor.language.pack.en import LANGUAGE_DICT
        else:
            raise BaseAppException("Language not supported")
        return LANGUAGE_DICT

    def get_val(self, _type: str, key: str):
        if _type == "ATTR":
            return self.language_dict.get("ATTR", {}).get(key) or self.language_dict["DEFAULT_ATTR"]
        return self.language_dict.get(_type, {}).get(key)

class SettingLanguage:
    def __init__(self, language: str):
        self.language_dict = self.get_language_dict(language)

    def get_language_dict(self, language: str):
        if language == "zh-Hans":
            from apps.cmdb.language.pack.zh import LANGUAGE_DICT
        elif language == "en":
            from apps.cmdb.language.pack.en import LANGUAGE_DICT
        else:
            raise Exception("Language not supported")
        return LANGUAGE_DICT

    def get_val(self, _type: str, key: str):
        if _type == "ATTR":
            return self.language_dict.get("ATTR", {}).get(key) or self.language_dict["DEFAULT_ATTR"]
        return self.language_dict.get(_type, {}).get(key)

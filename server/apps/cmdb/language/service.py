from apps.core.utils.loader import LanguageLoader


def normalize_cmdb_language(language: str | None) -> str:
    raw = str(language or "zh-Hans").strip()
    if not raw:
        return "zh-Hans"
    return "en" if raw.lower().startswith("en") else "zh-Hans"


class SettingLanguage:
    """
    CMDB 语言服务，使用统一的 LanguageLoader 加载语言包
    """

    def __init__(self, language: str):
        self.loader = LanguageLoader(app="cmdb", default_lang=normalize_cmdb_language(language))
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


def apply_attr_translations(attrs: list, model_id: str, language: str | None = None) -> list:
    """按 locale 覆盖内置属性展示名；attr_group 保持存储名以便与 FieldGroup 对齐。"""
    if not attrs:
        return attrs
    lan = SettingLanguage(language)
    model_attr = lan.loader.get(f"ATTR.{model_id}") or {}
    default_attr = lan.loader.get("DEFAULT_ATTR") or {}
    if not isinstance(model_attr, dict):
        model_attr = {}
    if not isinstance(default_attr, dict):
        default_attr = {}
    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        attr_id = attr.get("attr_id")
        if not attr_id:
            continue
        translated = model_attr.get(attr_id) or default_attr.get(attr_id)
        if translated:
            attr["attr_name"] = translated
    return attrs


def group_display_name(group_name: str | None, language: str | None = None) -> str:
    stored = "" if group_name is None else str(group_name)
    if not stored:
        return stored
    translated = SettingLanguage(language).loader.get(f"ATTR_GROUP.{stored}")
    return translated or stored


def apply_collect_tree_translations(tree: list, language: str | None = None) -> list:
    """按 locale 覆盖采集分类/插件展示名与说明；id 保持存储值。"""
    if not tree:
        return tree
    lan = SettingLanguage(language)
    for group in tree:
        if not isinstance(group, dict):
            continue
        group_id = group.get("id")
        if group_id:
            translated_group = lan.get_val("COLLECT_GROUP", group_id)
            if translated_group:
                group["name"] = translated_group
        for child in group.get("children") or []:
            if not isinstance(child, dict):
                continue
            plugin_id = child.get("id")
            plugin = lan.loader.get(f"COLLECT_PLUGIN.{plugin_id}") if plugin_id else None
            if isinstance(plugin, dict):
                if plugin.get("name"):
                    child["name"] = plugin["name"]
                if plugin.get("desc"):
                    child["desc"] = plugin["desc"]
            tags = child.get("tag")
            if isinstance(tags, list):
                child["tag"] = [lan.loader.get(f"COLLECT_TAG.{tag}") or tag if isinstance(tag, str) else tag for tag in tags]
    return tree


def overlay_collect_digest_message(digest, language: str | None = None):
    """覆盖系统摘要文案；存储值仍是中文身份。"""
    if not isinstance(digest, dict):
        return digest
    message = digest.get("message")
    if not isinstance(message, str) or not message:
        return digest
    translated = SettingLanguage(language).loader.get(f"COLLECT_MESSAGE.{message}")
    if not translated:
        return digest
    overlayed = dict(digest)
    overlayed["message"] = translated
    return overlayed

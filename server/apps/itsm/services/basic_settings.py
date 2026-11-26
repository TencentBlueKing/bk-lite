import re
from pathlib import PurePath

from apps.itsm.models import ItsmSetting

BASIC_SETTINGS_DEFAULTS = {
    "product_name": "ITSM",
    "tab_title": "ITSM",
    "attachment_types": "",
    "show_process_log": True,
    "user_display": "display_name",
}


def normalize_setting(key, value):
    if key in {"product_name", "tab_title"}:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
            raise ValueError("产品名称和页签标题须填写 1 至 100 个字符")
        return value.strip()
    if key == "show_process_log":
        if not isinstance(value, bool):
            raise ValueError("请选择是否展示流转日志")
        return value
    if key == "user_display":
        if value not in ("display_name", "username"):
            raise ValueError("请选择人员名称展示方式")
        return value
    if not isinstance(value, str):
        raise ValueError("请用逗号分隔附件扩展名")
    extensions = [part.strip().lower().removeprefix(".") for part in value.replace("，", ",").split(",") if part.strip()]
    if len(extensions) > 50 or any(not re.fullmatch(r"[a-z0-9]{1,16}", part) for part in extensions):
        raise ValueError("附件类型须为逗号分隔的文件扩展名")
    return ",".join(dict.fromkeys(extensions))


def basic_settings_values(stored):
    values = dict(BASIC_SETTINGS_DEFAULTS)
    if not isinstance(stored, dict):
        return values
    for key in values.keys() & stored.keys():
        try:
            values[key] = normalize_setting(key, stored[key])
        except ValueError:
            continue
    return values


def read_basic_settings(domain):
    stored = ItsmSetting.objects.filter(domain=domain, key="basic").values_list("value", flat=True).first()
    return basic_settings_values(stored)


def attachment_type_allowed(domain, filename):
    allowed = read_basic_settings(domain)["attachment_types"]
    return not allowed or PurePath(filename).suffix.lower().removeprefix(".") in allowed.split(",")

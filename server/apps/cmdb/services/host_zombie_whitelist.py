"""host 模型僵尸机白名单枚举：人工可改，采集不得写入。"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

HOST_MODEL_ID = "host"
ATTR_ID = "zombie_whitelist"
REQUIRED_OPTION_IDS = frozenset({"yes", "no"})

HOST_ZOMBIE_WHITELIST_ATTR = {
    "attr_id": ATTR_ID,
    "attr_name": "僵尸机白名单",
    "attr_type": "enum",
    "attr_group": "基本信息",
    "editable": True,
    "is_only": False,
    "is_required": False,
    "option": [{"id": "yes", "name": "是"}, {"id": "no", "name": "否"}],
    "user_prompt": "",
    "default_value": [],
}


def _enum_option_items(option: Any) -> list[dict[str, Any]]:
    if isinstance(option, list):
        return [item for item in option if isinstance(item, dict)]
    if isinstance(option, dict):
        nested = option.get("option")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    return []


def _option_ids(option: Any) -> set[str]:
    return {str(item.get("id")) for item in _enum_option_items(option) if item.get("id") not in (None, "")}


def _merge_whitelist_options(existing_option: Any) -> Any:
    merged = list(_enum_option_items(existing_option))
    present = {str(item.get("id")) for item in merged if item.get("id") not in (None, "")}
    for item in HOST_ZOMBIE_WHITELIST_ATTR["option"]:
        if item["id"] not in present:
            merged.append(dict(item))
    if isinstance(existing_option, dict):
        patched = dict(existing_option)
        patched["option"] = merged
        return patched
    return merged


def _needs_option_patch(existing: dict[str, Any]) -> bool:
    return not REQUIRED_OPTION_IDS.issubset(_option_ids(existing.get("option")))


def _needs_flag_patch(existing: dict[str, Any]) -> bool:
    return existing.get("editable") is not True or bool(existing.get("is_system_link"))


def ensure_host_zombie_whitelist_attr(*, username: str = "admin") -> bool:
    """幂等创建/补齐 host.zombie_whitelist，保持人工可编辑，不是 system link。"""
    from apps.cmdb.services.model import ModelManage

    model_info = ModelManage.search_model_info(HOST_MODEL_ID)
    if not model_info:
        logger.warning(
            "event=host_zombie_whitelist_ensure_skipped model_id=%s attr_id=%s failed_stage=%s error_type=%s",
            HOST_MODEL_ID,
            ATTR_ID,
            "search_model_info",
            "ModelNotFound",
        )
        return False

    attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
    existing = next((attr for attr in attrs if attr.get("attr_id") == ATTR_ID), None)
    if existing is not None:
        needs_options = _needs_option_patch(existing)
        needs_flags = _needs_flag_patch(existing)
        if needs_options or needs_flags:
            patched = dict(existing)
            if needs_options:
                patched["option"] = _merge_whitelist_options(existing.get("option"))
            if needs_flags:
                patched["editable"] = True
                patched["is_system_link"] = False
            ModelManage.update_model_attr(HOST_MODEL_ID, patched, username=username)
            logger.info(
                "event=host_zombie_whitelist_option_patched model_id=%s attr_id=%s",
                HOST_MODEL_ID,
                ATTR_ID,
            )
        return True

    try:
        ModelManage.create_model_attr(HOST_MODEL_ID, dict(HOST_ZOMBIE_WHITELIST_ATTR), username=username)
    except BaseAppException as exc:
        message = str(getattr(exc, "message", "") or exc)
        if "repetition" in message.lower() or "重复" in message:
            logger.info(
                "event=host_zombie_whitelist_attr_ready model_id=%s attr_id=%s",
                HOST_MODEL_ID,
                ATTR_ID,
            )
            return True
        raise

    logger.info(
        "event=host_zombie_whitelist_attr_created model_id=%s attr_id=%s",
        HOST_MODEL_ID,
        ATTR_ID,
    )
    return True

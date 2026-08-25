"""Host Telegraf disk 文件系统过滤字段的读写投影。

BK-Lite 用自定义字段 disk_include_fstypes / disk_exclude_fstypes，经
[[processors.starlark]] constants 过滤；Telegraf 1.29.5 的 [[inputs.disk]]
只认 ignore_fs / mount_points / ignore_mount_opts，不认这两个字段。

编辑表单绑定 child.content.config.*，json_to_toml 会把 content.config 整段
写回 inputs.<plugin>[0]。若不投影，保存后会把非法字段塞进 inputs.disk，
Telegraf 拒载并报 “fields were not used”。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DISK_FSTYPE_FILTER_KEYS = ("disk_include_fstypes", "disk_exclude_fstypes")


def _iter_starlark_processors(document: dict[str, Any]) -> list[dict[str, Any]]:
    processors = document.get("processors")
    if not isinstance(processors, dict):
        return []
    starlark = processors.get("starlark")
    if isinstance(starlark, list):
        return [item for item in starlark if isinstance(item, dict)]
    if isinstance(starlark, dict):
        return [starlark]
    return []


def _namepass_includes_disk(processor: dict[str, Any]) -> bool:
    namepass = processor.get("namepass")
    if isinstance(namepass, list):
        return any(str(item) == "disk" for item in namepass)
    if isinstance(namepass, str):
        return namepass == "disk"
    return False


def _disk_filter_starlark(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(document, dict):
        return None
    for processor in _iter_starlark_processors(document):
        if not _namepass_includes_disk(processor):
            continue
        constants = processor.get("constants")
        if isinstance(constants, dict):
            return constants
        constants = {}
        processor["constants"] = constants
        return constants
    return None


def expose_disk_fstype_filters_for_edit(content: dict | None) -> dict | None:
    """把 starlark.constants 中的磁盘过滤投影到 content.config，供表单回显。"""
    if not isinstance(content, dict):
        return content
    config = content.get("config")
    if not isinstance(config, dict):
        return content

    constants = _disk_filter_starlark(content.get("_toml_document"))
    if constants is None:
        return content

    projected = deepcopy(config)
    for key in DISK_FSTYPE_FILTER_KEYS:
        if key in constants:
            projected[key] = deepcopy(constants[key])
        else:
            projected.pop(key, None)
    content["config"] = projected
    return content


def sync_disk_fstype_filters_on_writeback(content: dict | None) -> dict | None:
    """把表单写入 content.config 的磁盘过滤挪回 starlark.constants，并清掉 input 上的非法字段。"""
    if not isinstance(content, dict):
        return content
    config = content.get("config")
    if not isinstance(config, dict):
        return content

    pending = {
        key: deepcopy(config.pop(key))
        for key in DISK_FSTYPE_FILTER_KEYS
        if key in config
    }
    if not pending:
        return content

    constants = _disk_filter_starlark(content.get("_toml_document"))
    if constants is None:
        # 无 starlark 段时至少不要把非法字段写进 inputs.*，避免 Telegraf 拒载。
        return content

    for key, value in pending.items():
        constants[key] = value
    return content

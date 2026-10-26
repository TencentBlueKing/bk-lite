# -- coding: utf-8 --
from django.db.models import Q

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.custom_collect_plugin import (
    ALLOWED_OS_TYPES,
    MAX_SCRIPT_BYTES,
    PLUGIN_ID_PATTERN,
    SHELL_BY_OS,
    CustomCollectPlugin,
    script_checksum,
)
from apps.core.exceptions.base_app_exception import BaseAppException


def referencing_tasks(plugin_pk):
    return CollectModels.objects.filter(params__contains={"custom_plugin_pk": int(plugin_pk)})


def reference_count(plugin_pk) -> int:
    return referencing_tasks(plugin_pk).count()


def attach_list_reference_counts(plugins):
    """给本批列表对象填上 reference_count，序列化时不再逐行 COUNT。"""
    plugin_ids = []
    for plugin in plugins:
        plugin_id = getattr(plugin, "id", None)
        if not plugin_id:
            continue
        plugin_ids.append(int(plugin_id))
    counts = _reference_counts(plugin_ids)
    for plugin in plugins:
        plugin_id = getattr(plugin, "id", None)
        if not plugin_id:
            continue
        plugin.reference_count = counts.get(int(plugin_id), 0)


def _reference_counts(plugin_ids):
    unique_ids = list(dict.fromkeys(plugin_ids))
    if not unique_ids:
        return {}
    query = Q()
    for plugin_id in unique_ids:
        query |= Q(params__contains={"custom_plugin_pk": plugin_id})
    counts = {plugin_id: 0 for plugin_id in unique_ids}
    referenced = CollectModels.objects.filter(query).values_list("params", flat=True)
    for params in referenced:
        if not isinstance(params, dict):
            continue
        raw_pk = params.get("custom_plugin_pk")
        if type(raw_pk) is int and raw_pk in counts:
            counts[raw_pk] += 1
    return counts


def ensure_deletable(plugin: CustomCollectPlugin):
    count = reference_count(plugin.id)
    if count:
        raise BaseAppException(f"插件已被 {count} 个采集任务引用，请先解除引用后再删除")


def ensure_model_deletable(model_id: str):
    if not model_id:
        return
    if CustomCollectPlugin.objects.filter(model_id=model_id).exists():
        raise BaseAppException("模型已绑定自定义采集插件，请先处理插件后再删除模型")


def normalize_plugin_id(raw):
    """表单只提交后缀，custom_ 前缀由服务端补上，避免用户删掉预填前缀。"""
    value = str(raw or "").strip().lower()
    if value.startswith("custom_"):
        value = value[len("custom_") :]
    return f"custom_{value}" if value else ""


def validate_plugin_payload(data, *, instance=None):
    """校验创建/更新载荷，返回可写入的字段。不记录脚本正文。"""
    plugin_id = normalize_plugin_id(data.get("plugin_id"))
    if not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
        raise BaseAppException("插件标识须为 2 到 40 位小写字母、数字或下划线")
    if instance is not None and plugin_id != instance.plugin_id:
        raise BaseAppException("插件标识创建后不可修改")

    os_type = str(data.get("os_type") or (instance.os_type if instance else "")).strip()
    if os_type not in ALLOWED_OS_TYPES:
        raise BaseAppException("操作系统仅支持 linux 或 windows")
    if instance is not None and "os_type" in data and os_type != instance.os_type and reference_count(instance.id):
        raise BaseAppException("插件已被采集任务引用，不能修改操作系统")

    shell = str(data.get("shell") or (instance.shell if instance else "")).strip()
    if shell not in SHELL_BY_OS[os_type]:
        raise BaseAppException("脚本解释器与操作系统不匹配")

    model_id = str(data.get("model_id") or (instance.model_id if instance else "")).strip()
    if not model_id:
        raise BaseAppException("目标模型不能为空")
    if instance is not None and "model_id" in data and model_id != instance.model_id and reference_count(instance.id):
        raise BaseAppException("插件已被采集任务引用，不能修改目标模型")

    content = data.get("content", instance.content if instance else None)
    if not isinstance(content, str) or not content.strip():
        raise BaseAppException("脚本内容不能为空")
    try:
        content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise BaseAppException("脚本内容必须是 UTF-8 文本") from exc
    if len(content.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise BaseAppException("脚本内容不能超过 64KB")

    name = str(data.get("name") or (instance.name if instance else "")).strip()
    if not name:
        raise BaseAppException("插件名称不能为空")

    team = data.get("team", instance.team if instance else None)
    if not isinstance(team, list) or not team:
        raise BaseAppException("插件必须归属组织")

    if instance is None and CustomCollectPlugin.objects.filter(plugin_id=plugin_id).exists():
        raise BaseAppException("标识已被占用")

    version = 1 if instance is None else instance.version
    if instance is not None and content != instance.content:
        version = instance.version + 1

    return {
        "name": name,
        "plugin_id": plugin_id,
        "model_id": model_id,
        "os_type": os_type,
        "shell": shell,
        "content": content,
        "content_checksum": script_checksum(content),
        "version": version,
        "desc": str(data.get("desc", instance.desc if instance else "") or "")[:512],
        "team": team,
    }

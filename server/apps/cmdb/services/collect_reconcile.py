"""数据调和的配置读写。判断规则在 field_reconcile，这里只校验成员和顺序。"""

from django.db import transaction

from apps.cmdb.collection.field_reconcile import DEFAULT_STALE_DAYS, MEMBER_SCOPE, STALE_DAYS_SETTING
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.collect_reconcile import CollectReconcile, CollectReconcileOrder
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.models.maintainer_info import maintainer_kwargs

SUPPORTED_TASK_TYPES = {
    CollectPluginTypes.HOST,
    CollectPluginTypes.DB,
    CollectPluginTypes.MIDDLEWARE,
    CollectPluginTypes.PROTOCOL,
    CollectPluginTypes.SNMP,
    CollectPluginTypes.OTHER,
    CollectPluginTypes.CUSTOM_SCRIPT,
}
VMWARE_VC_MODEL = "vmware_vc"
EXCLUDED_COLLECT_FIELDS = {"inst_name", "model_id", "assos", "organization", "collect_task", "collect_time", "auto_collect"}


def read_stale_days() -> int:
    from apps.system_mgmt.models import SystemSettings

    row = SystemSettings.objects.filter(key=STALE_DAYS_SETTING).first()
    if row is None or row.value in (None, ""):
        return DEFAULT_STALE_DAYS
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return DEFAULT_STALE_DAYS


def write_stale_days(value) -> int:
    from apps.system_mgmt.models import SystemSettings

    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationAppException("过期天数必须是整数") from exc
    SystemSettings.objects.update_or_create(key=STALE_DAYS_SETTING, defaults={"value": str(days)})
    return days


def task_collected_fields(task) -> list[str]:
    """转换层写入主实例的模型字段。不读脚本返回名，也不读任务上的 collect_fields。"""
    return _clean_fields(_conversion_model_fields(task))


def _clean_fields(fields) -> list[str]:
    result = []
    for field in fields:
        if not isinstance(field, str) or field in EXCLUDED_COLLECT_FIELDS or field.startswith("_"):
            continue
        if field not in result:
            result.append(field)
    return result


def _conversion_model_fields(task) -> list[str]:
    if task.task_type == CollectPluginTypes.CUSTOM_SCRIPT:
        return _custom_conversion_fields(task.model_id)
    if task.task_type == CollectPluginTypes.SNMP and task.model_id in {"network", "switch", "router", "firewall", "loadbalance"}:
        from apps.cmdb.collection.plugins.community.network.plugins import NETWORK_DEVICE_MAPPING

        return list(NETWORK_DEVICE_MAPPING)
    try:
        from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry

        plugin_cls = CollectionPluginRegistry.get_plugin(task.task_type, task.model_id)
    except ValueError:
        return []
    mappings = getattr(plugin_cls, "field_mappings", None)
    if isinstance(mappings, dict):
        model_mapping = mappings.get(task.model_id)
        if isinstance(model_mapping, dict) and model_mapping:
            return list(model_mapping)
    mapping = getattr(plugin_cls, "field_mapping", None)
    if isinstance(mapping, dict):
        return list(mapping)
    return []


def _custom_conversion_fields(model_id) -> list[str]:
    """自定义脚本把对得上模型属性的标签写成该属性。网络设备沿用设备字段表。"""
    if model_id == "network":
        from apps.cmdb.collection.plugins.community.network.plugins import NETWORK_DEVICE_MAPPING

        return list(NETWORK_DEVICE_MAPPING)
    try:
        from apps.cmdb.services.model import ModelManage

        attrs = ModelManage.search_model_attr(model_id) or []
    except Exception:
        return []
    fields = []
    for attr in attrs:
        attr_id = attr.get("attr_id") if isinstance(attr, dict) else None
        if isinstance(attr_id, str):
            fields.append(attr_id)
    return fields


def task_plugin_key(task) -> str:
    """同一插件的任务字段集合相同，调和成员必须跨插件。"""
    params = task.params if isinstance(task.params, dict) else {}
    plugin_pk = params.get("custom_plugin_pk")
    if task.task_type == CollectPluginTypes.CUSTOM_SCRIPT and plugin_pk:
        return f"custom:{plugin_pk}"
    from apps.cmdb.collection.physical_server_protocol import PHYSICAL_SERVER_MODEL_ID, resolve_physical_server_plugin_id

    if task.model_id == PHYSICAL_SERVER_MODEL_ID:
        return resolve_physical_server_plugin_id(task.model_id, task.driver_type, params.get("collection_protocol"))
    return f"{task.model_id}:{task.task_type}:{task.driver_type or ''}"


def task_plugin_names(tasks) -> dict:
    from apps.cmdb.models.custom_collect_plugin import CustomCollectPlugin

    plugin_ids = []
    for task in tasks:
        params = task.params if isinstance(task.params, dict) else {}
        plugin_pk = params.get("custom_plugin_pk")
        if task.task_type == CollectPluginTypes.CUSTOM_SCRIPT and plugin_pk:
            plugin_ids.append(plugin_pk)
    if not plugin_ids:
        return {}
    return dict(CustomCollectPlugin.objects.filter(id__in=plugin_ids).values_list("id", "name"))


def _ensure_joinable(task, model_id):
    if task.model_id != model_id:
        raise ValidationAppException("采集任务的模型与数据调和不一致")
    if task.task_type not in SUPPORTED_TASK_TYPES:
        raise ValidationAppException("该采集类型不能加入数据调和")
    if task.task_type == CollectPluginTypes.CUSTOM_SCRIPT and task.model_id == VMWARE_VC_MODEL:
        raise ValidationAppException("vmware_vc 自定义脚本不能加入数据调和")


def _visible_tasks(request):
    from apps.cmdb.views.collect import CollectModelViewSet

    view = CollectModelViewSet()
    return view.get_queryset_by_permission(request, CollectModels.objects.all())


def _actor(request):
    user = getattr(request, "user", None)
    return maintainer_kwargs(operator=getattr(user, "username", None) or "", domain=getattr(user, "domain", None))


def load_write_context(task_id):
    """任务执行时读取生效调和。成员不足两个时返回 None，调用方按单任务写入。"""
    member = CollectReconcileOrder.objects.filter(task_id=task_id, scope=MEMBER_SCOPE).select_related("reconcile").first()
    if member is None:
        return None
    rows = list(member.reconcile.orders.order_by("position").values_list("scope", "task_id", "position"))
    members = [str(task) for scope, task, _position in rows if scope == MEMBER_SCOPE]
    if len(members) < 2:
        return None
    field_orders = {}
    for scope, task, _position in rows:
        if scope == MEMBER_SCOPE:
            continue
        field_orders.setdefault(scope, []).append(str(task))
    return {
        "model_id": member.reconcile.model_id,
        "member_order": members,
        "field_orders": field_orders,
        "stale_days": read_stale_days(),
    }


def _initial_field_orders(tasks):
    orders = {}
    for task in tasks:
        for field in task_collected_fields(task):
            orders.setdefault(field, []).append(task.id)
    return orders


def _validate_field_orders(field_orders, tasks):
    by_id = {task.id: task for task in tasks}
    collected = {task.id: set(task_collected_fields(task)) for task in tasks}
    if not isinstance(field_orders, dict):
        raise ValidationAppException("字段顺序格式不正确")
    normalized = {}
    for field, task_ids in field_orders.items():
        if not isinstance(task_ids, list) or len(task_ids) != len(set(task_ids)):
            raise ValidationAppException("字段顺序里的任务不能重复")
        expected = [task.id for task in tasks if field in collected[task.id]]
        if set(task_ids) != set(expected):
            raise ValidationAppException("字段顺序只能包含会采集该字段的成员")
        for task_id in task_ids:
            if task_id not in by_id:
                raise ValidationAppException("字段顺序里的任务不是调和成员")
        normalized[field] = list(task_ids)
    return normalized


@transaction.atomic
def create_reconcile(request, *, name, model_id, task_ids, field_orders=None):
    if not name or not model_id:
        raise ValidationAppException("名称和模型不能为空")
    if len(task_ids) < 2 or len(set(task_ids)) != len(task_ids):
        raise ValidationAppException("至少选择两个不重复的采集任务")
    visible = {task.id: task for task in _visible_tasks(request).filter(id__in=task_ids, model_id=model_id)}
    if set(visible) != set(task_ids):
        raise ValidationAppException("只能选择当前用户可见、且模型一致的采集任务")
    tasks = [visible[task_id] for task_id in task_ids]
    for task in tasks:
        _ensure_joinable(task, model_id)
    if CollectReconcileOrder.objects.filter(task_id__in=task_ids, scope=MEMBER_SCOPE).exists():
        raise ValidationAppException("采集任务已经属于另一条数据调和")
    computed = _initial_field_orders(tasks)
    if field_orders is None:
        field_orders = computed
    else:
        field_orders = _validate_field_orders(field_orders, tasks)
    reconcile = CollectReconcile.objects.create(name=name, model_id=model_id, **_actor(request))
    _replace_orders(reconcile, tasks, field_orders)
    return detail_payload(request, reconcile)


@transaction.atomic
def update_reconcile(request, reconcile_id, *, version, task_ids, field_orders=None, added_task_ids=None, removed_task_ids=None):
    reconcile = CollectReconcile.objects.select_for_update().filter(id=reconcile_id).first()
    if reconcile is None:
        raise ValidationAppException("数据调和不存在")
    if int(version) != reconcile.version:
        raise ValidationAppException("数据调和已被他人修改，请刷新后重试")
    current = list(reconcile.orders.filter(scope=MEMBER_SCOPE).order_by("position").values_list("task_id", flat=True))
    visible_ids = set(_visible_tasks(request).filter(id__in=current).values_list("id", flat=True))
    hidden = [task_id for task_id in current if task_id not in visible_ids]
    added = [int(task_id) for task_id in (added_task_ids or [])]
    removed = [int(task_id) for task_id in (removed_task_ids or [])]
    task_ids = [int(task_id) for task_id in task_ids]
    if any(task_id not in visible_ids for task_id in removed):
        raise ValidationAppException("不能移除没有权限的采集任务")
    visible_kept = [task_id for task_id in current if task_id in visible_ids and task_id not in removed]
    if set(task_ids) != set(visible_kept) | set(added):
        raise ValidationAppException("提交的任务与可见成员不一致")
    if len(task_ids) != len(set(task_ids)):
        raise ValidationAppException("成员顺序里的任务不能重复")
    merged_ids = _place_hidden(current, task_ids, hidden)
    tasks = _locked_tasks(request, reconcile, merged_ids, hidden)
    computed = _initial_field_orders(tasks)
    if field_orders is None:
        field_orders = _carry_field_orders(reconcile, tasks, computed)
    else:
        if visible_ids != set(current):
            raise ValidationAppException("调整字段顺序需要对全部成员有权限")
        submitted = _validate_field_orders(field_orders, tasks)
        field_orders = _carry_field_orders(reconcile, tasks, computed)
        field_orders.update(submitted)
    reconcile.version = reconcile.version + 1
    actor = _actor(request)
    reconcile.updated_by = actor["updated_by"]
    reconcile.updated_by_domain = actor["updated_by_domain"]
    reconcile.save(update_fields=["version", "updated_by", "updated_by_domain", "updated_at"])
    _replace_orders(reconcile, tasks, field_orders)
    return detail_payload(request, reconcile)


def _place_hidden(current, visible_ordered, hidden):
    """隐藏成员留在原来的相对位置，可见成员按新顺序填入其余位置。"""
    hidden_set = set(hidden)
    visible_iter = iter(visible_ordered)
    placed = []
    for task_id in current:
        if task_id in hidden_set:
            placed.append(task_id)
            continue
        nxt = next(visible_iter, None)
        if nxt is not None:
            placed.append(nxt)
    placed.extend(list(visible_iter))
    return placed


def _locked_tasks(request, reconcile, task_ids, hidden_ids):
    found = {task.id: task for task in CollectModels.objects.filter(id__in=task_ids)}
    if set(found) != set(task_ids):
        raise ValidationAppException("采集任务不存在")
    visible = set(_visible_tasks(request).filter(id__in=task_ids).values_list("id", flat=True))
    hidden_set = set(hidden_ids)
    for task_id in task_ids:
        if task_id not in visible and task_id not in hidden_set:
            raise ValidationAppException("只能选择当前用户可见的采集任务")
        _ensure_joinable(found[task_id], reconcile.model_id)
    if CollectReconcileOrder.objects.filter(task_id__in=task_ids, scope=MEMBER_SCOPE).exclude(reconcile_id=reconcile.id).exists():
        raise ValidationAppException("采集任务已经属于另一条数据调和")
    return [found[task_id] for task_id in task_ids]


def _carry_field_orders(reconcile, tasks, computed):
    existing = {}
    for scope, task_id, position in reconcile.orders.exclude(scope=MEMBER_SCOPE).order_by("position").values_list("scope", "task_id", "position"):
        existing.setdefault(scope, []).append(task_id)
    task_ids = {task.id for task in tasks}
    carried = {}
    for field, expected in computed.items():
        previous = [task_id for task_id in existing.get(field, []) if task_id in task_ids and task_id in expected]
        for task_id in expected:
            if task_id not in previous:
                previous.append(task_id)
        carried[field] = previous
    return carried


def _replace_orders(reconcile, tasks, field_orders):
    reconcile.orders.all().delete()
    rows = []
    for position, task in enumerate(tasks):
        rows.append(CollectReconcileOrder(reconcile=reconcile, scope=MEMBER_SCOPE, task=task, position=position))
    for field, task_ids in field_orders.items():
        by_id = {task.id: task for task in tasks}
        for position, task_id in enumerate(task_ids):
            rows.append(CollectReconcileOrder(reconcile=reconcile, scope=field, task=by_id[task_id], position=position))
    CollectReconcileOrder.objects.bulk_create(rows)


def delete_reconcile(request, reconcile_id):
    reconcile = CollectReconcile.objects.filter(id=reconcile_id).first()
    if reconcile is None:
        raise ValidationAppException("数据调和不存在")
    member_ids = list(reconcile.orders.filter(scope=MEMBER_SCOPE).values_list("task_id", flat=True))
    visible = set(_visible_tasks(request).filter(id__in=member_ids).values_list("id", flat=True))
    if set(member_ids) - visible:
        raise ValidationAppException("删除数据调和需要对全部成员有权限")
    reconcile.delete()


def list_payload(request, model_id=None):
    visible_ids = set(_visible_tasks(request).values_list("id", flat=True))
    reconcile_ids = CollectReconcileOrder.objects.filter(scope=MEMBER_SCOPE, task_id__in=visible_ids).values_list("reconcile_id", flat=True)
    queryset = CollectReconcile.objects.filter(id__in=reconcile_ids)
    if model_id:
        queryset = queryset.filter(model_id=model_id)
    rows = [_summary(request, reconcile, visible_ids) for reconcile in queryset.order_by("-updated_at")]
    return {"items": rows}


def detail_payload(request, reconcile):
    visible_ids = set(_visible_tasks(request).values_list("id", flat=True))
    return _summary(request, reconcile, visible_ids, include_fields=True)


def _summary(request, reconcile, visible_ids, include_fields=False):
    orders = list(reconcile.orders.select_related("task").order_by("position"))
    member_rows = [row for row in orders if row.scope == MEMBER_SCOPE and row.task_id in visible_ids]
    plugin_names = task_plugin_names([row.task for row in member_rows])
    members = []
    for row in member_rows:
        params = row.task.params if isinstance(row.task.params, dict) else {}
        plugin_pk = params.get("custom_plugin_pk")
        members.append(
            {
                "id": row.task_id,
                "name": row.task.name,
                "task_type": row.task.task_type,
                "driver_type": row.task.driver_type,
                "plugin_key": task_plugin_key(row.task),
                "plugin_name": plugin_names.get(plugin_pk, ""),
                "custom_plugin_pk": plugin_pk or None,
                "position": row.position,
                "collected_fields": task_collected_fields(row.task),
            }
        )
    payload = {
        "id": reconcile.id,
        "name": reconcile.name,
        "model_id": reconcile.model_id,
        "version": reconcile.version,
        "effective": reconcile.is_effective(),
        "members": members,
        "can_edit_all_members": {row.task_id for row in orders if row.scope == MEMBER_SCOPE} <= visible_ids,
    }
    if include_fields:
        fields = {}
        names = {item["id"]: item["name"] for item in members}
        for row in orders:
            if row.scope == MEMBER_SCOPE or row.task_id not in names:
                continue
            fields.setdefault(row.scope, []).append({"id": row.task_id, "name": names[row.task_id]})
        payload["field_orders"] = [{"field": field, "tasks": tasks} for field, tasks in fields.items()]
    return payload


def candidate_tasks(request, model_id):
    queryset = _visible_tasks(request).filter(model_id=model_id, task_type__in=SUPPORTED_TASK_TYPES)
    if model_id == VMWARE_VC_MODEL:
        queryset = queryset.exclude(task_type=CollectPluginTypes.CUSTOM_SCRIPT)
    tasks = [
        task for task in queryset.order_by("id") if not (task.task_type == CollectPluginTypes.CUSTOM_SCRIPT and task.model_id == VMWARE_VC_MODEL)
    ]
    taken = set(CollectReconcileOrder.objects.filter(scope=MEMBER_SCOPE).values_list("task_id", flat=True))
    plugin_names = task_plugin_names(tasks)
    rows = []
    for task in tasks:
        params = task.params if isinstance(task.params, dict) else {}
        plugin_pk = params.get("custom_plugin_pk")
        rows.append(
            {
                "id": task.id,
                "name": task.name,
                "task_type": task.task_type,
                "driver_type": task.driver_type,
                "model_id": task.model_id,
                "plugin_key": task_plugin_key(task),
                "plugin_name": plugin_names.get(plugin_pk, ""),
                "custom_plugin_pk": plugin_pk or None,
                "ip_range": task.ip_range or "",
                "collected_fields": task_collected_fields(task),
                "in_reconcile": task.id in taken,
            }
        )
    return rows

from apps.cmdb.constants.constants import (
    ENUM_SELECT_MODE_DEFAULT,
    INSTANCE,
    INSTANCE_ASSOCIATION,
    NETWORK_TOPO_NODE_LIMIT,
    OPERATOR_INSTANCE,
    PERMISSION_INSTANCES,
    VIEW,
)
from apps.cmdb.constants.field_constraints import TAG_ATTR_ID, TAG_MODE_FREE
from apps.cmdb.display_field import DisplayFieldHandler
from apps.cmdb.display_field.constants import (
    DISPLAY_FIELD_TYPES,
    DISPLAY_SUFFIX,
    FIELD_TYPE_ENUM,
    FIELD_TYPE_ORGANIZATION,
    FIELD_TYPE_TABLE,
    FIELD_TYPE_TAG,
    FIELD_TYPE_USER,
)
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.graph.format_type import ParameterCollector
from apps.cmdb.instance_ops.extensions import get_instance_enterprise_extension
from apps.cmdb.models.change_record import (
    CREATE_INST,
    CREATE_INST_ASST,
    DELETE_INST,
    DELETE_INST_ASST,
    ORDINARY_ATTRIBUTE_CHANGE,
    RELATION_CHANGE,
    UPDATE_INST,
)
from apps.cmdb.models.show_field import ShowField
from apps.cmdb.permissions.instance_permission import PermissionManage
from apps.cmdb.services.auto_relation_reconcile import schedule_instance_auto_relation_reconcile
from apps.cmdb.services.instance_identity import (
    ensure_instance_identity_immutable,
    normalize_inst_uuid,
    prepare_edge_endpoint_properties,
    prepare_new_instance_identity,
)
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.unique_rule import build_unique_rule_context, collect_instance_unique_conflicts
from apps.cmdb.utils.change_record import batch_create_change_record, create_change_record, create_change_record_by_asso
from apps.cmdb.utils.export import Export
from apps.cmdb.utils.Import import Import
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.cmdb.validators.field_validator import (
    TagFieldConfig,
    normalize_enum_values,
    normalize_tag_field_option,
    normalize_tag_input_values,
    validate_enum_values,
    validate_tag_values,
)
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger


class InstanceBatchError(BaseAppException):
    """批量实例领域错误，使用结构化属性向门面传递失败位置与原因。"""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        index: int | None = None,
        inst_id: int | None = None,
        inst_uuid: str | None = None,
        field: str | None = None,
    ):
        self.reason = reason
        self.index = index
        self.inst_id = inst_id
        self.inst_uuid = inst_uuid
        self.field = field
        data = {
            key: value
            for key, value in {
                "index": index,
                "inst_id": inst_id,
                "inst_uuid": inst_uuid,
                "field": field,
            }.items()
            if value is not None
        }
        super().__init__(message, data=data)


def _normalize_batch_instance_ids(inst_ids: list) -> list[int]:
    normalized_ids = []
    seen_ids = set()
    for inst_id in inst_ids:
        normalized_id = int(inst_id)
        if normalized_id in seen_ids:
            continue
        seen_ids.add(normalized_id)
        normalized_ids.append(normalized_id)
    if not normalized_ids:
        raise InstanceBatchError(
            "实例不存在",
            reason="not_found",
        )
    return normalized_ids


def _find_duplicate_or_unexpected_batch_id(
    expected_ids: list[int],
    returned_items: list[dict],
) -> int | None:
    expected_id_set = set(expected_ids)
    seen_ids = set()
    for item in returned_items:
        if item.get("_id") is None:
            continue
        returned_id = int(item["_id"])
        if returned_id not in expected_id_set or returned_id in seen_ids:
            return returned_id
        seen_ids.add(returned_id)
    return None


def _require_complete_batch_instances(inst_ids: list[int], instances: list[dict]) -> list[dict]:
    instances_by_id = {int(instance["_id"]): instance for instance in instances if instance.get("_id") is not None}
    missing_ids = [inst_id for inst_id in inst_ids if inst_id not in instances_by_id]
    if missing_ids:
        raise InstanceBatchError(
            "实例不存在",
            reason="not_found",
            inst_id=missing_ids[0],
        )
    if len(instances) != len(inst_ids):
        raise InstanceBatchError(
            "实例查询结果不完整",
            reason="incomplete",
            inst_id=_find_duplicate_or_unexpected_batch_id(inst_ids, instances),
        )
    return [instances_by_id[inst_id] for inst_id in inst_ids]


def _normalize_batch_instance_uuids(inst_uuids: list) -> list[str]:
    normalized_uuids = []
    seen_uuids = set()
    for value in inst_uuids:
        normalized = normalize_inst_uuid(value)
        if normalized in seen_uuids:
            continue
        seen_uuids.add(normalized)
        normalized_uuids.append(normalized)
    if not normalized_uuids:
        raise InstanceBatchError(
            "实例不存在",
            reason="not_found",
        )
    return normalized_uuids


def _require_complete_batch_instances_by_uuid(inst_uuids: list[str], instances: list[dict]) -> list[dict]:
    instances_by_uuid = {instance["inst_uuid"]: instance for instance in instances if instance.get("inst_uuid")}
    missing = [value for value in inst_uuids if value not in instances_by_uuid]
    if missing:
        raise InstanceBatchError(
            "实例不存在",
            reason="not_found",
            inst_uuid=missing[0],
        )
    if len(instances) != len(inst_uuids):
        raise InstanceBatchError(
            "实例查询结果不完整",
            reason="incomplete",
            inst_uuid=inst_uuids[0] if inst_uuids else None,
        )
    return [instances_by_uuid[value] for value in inst_uuids]


def _normalize_allowed_org_ids(user_groups: list | None = None, allowed_org_ids: list | None = None) -> set[int]:
    if allowed_org_ids is not None:
        normalized_allowed_org_ids: set[int] = set()
        for org_id in allowed_org_ids:
            if org_id is None:
                continue
            try:
                normalized_allowed_org_ids.add(int(org_id))
            except (TypeError, ValueError) as exc:
                raise BaseAppException("organization 必须是整数数组") from exc
        return normalized_allowed_org_ids

    normalized_org_ids: set[int] = set()
    for item in user_groups or []:
        if isinstance(item, dict):
            org_id = item.get("id")
        else:
            org_id = item
        if org_id is None:
            continue
        try:
            normalized_org_ids.add(int(org_id))
        except (TypeError, ValueError) as exc:
            raise BaseAppException("organization 必须是整数数组") from exc
    return normalized_org_ids


def validate_instance_organization_scope(
    instance_data: dict,
    *,
    user_groups: list | None = None,
    allowed_org_ids: list | None = None,
) -> None:
    if not isinstance(instance_data, dict) or "organization" not in instance_data:
        return

    organization_ids = instance_data.get("organization")
    if organization_ids in (None, ""):
        return

    if not isinstance(organization_ids, list):
        raise BaseAppException("organization 必须是数组")

    normalized_target_org_ids: set[int] = set()
    for org_id in organization_ids:
        if org_id in (None, ""):
            continue
        try:
            normalized_target_org_ids.add(int(org_id))
        except (TypeError, ValueError) as exc:
            raise BaseAppException("organization 必须是整数数组") from exc
    if not normalized_target_org_ids:
        return

    normalized_allowed_org_ids = _normalize_allowed_org_ids(user_groups=user_groups, allowed_org_ids=allowed_org_ids)
    if not normalized_allowed_org_ids:
        raise BaseAppException("缺少 organization 范围上下文，请刷新后重试")

    invalid_org_ids = sorted(normalized_target_org_ids - normalized_allowed_org_ids)
    if invalid_org_ids:
        raise BaseAppException(f"organization {invalid_org_ids} 不在当前选择组织范围内")


def apply_tag_validation_for_instance(
    instance_data: dict,
    attrs: list[dict],
    model_id: str | None = None,
    *,
    persist_options: bool = True,
) -> dict:
    data = dict(instance_data)
    tag_attr = next(
        (attr for attr in attrs if attr.get("attr_type") == "tag" and attr.get("attr_id") == TAG_ATTR_ID),
        None,
    )

    if not tag_attr:
        data.pop(TAG_ATTR_ID, None)
        return data

    if TAG_ATTR_ID not in data:
        return data

    raw_values = normalize_tag_input_values(data.get(TAG_ATTR_ID))
    tag_config: TagFieldConfig = normalize_tag_field_option(tag_attr.get("option") or {})
    validation_result = validate_tag_values(raw_values, tag_config)
    if validation_result.errors:
        raise BaseAppException("; ".join(validation_result.errors))

    normalized_values = [item.raw for item in validation_result.normalized_values]
    data[TAG_ATTR_ID] = normalized_values

    if persist_options and model_id and tag_config.mode == TAG_MODE_FREE and normalized_values:
        ModelManage.merge_tag_options_from_values(model_id, normalized_values)

    return data


def persist_free_tag_options_for_instances(records: list[dict], attrs: list[dict], model_id: str) -> None:
    tag_attr = next(
        (attr for attr in attrs if attr.get("attr_type") == "tag" and attr.get("attr_id") == TAG_ATTR_ID),
        None,
    )
    if not tag_attr or not model_id:
        return

    tag_config: TagFieldConfig = normalize_tag_field_option(tag_attr.get("option") or {})
    if tag_config.mode != TAG_MODE_FREE:
        return

    merged_values = sorted({value for record in records for value in record.get(TAG_ATTR_ID, []) or []})
    if merged_values:
        ModelManage.merge_tag_options_from_values(model_id, merged_values)


def apply_tag_validation_for_batch(
    records: list[dict],
    attrs: list[dict],
    model_id: str | None = None,
    *,
    persist_options: bool = True,
) -> list[dict]:
    normalized_records = [
        apply_tag_validation_for_instance(
            record,
            attrs,
            model_id,
            persist_options=False,
        )
        for record in records
    ]

    if persist_options and model_id:
        persist_free_tag_options_for_instances(normalized_records, attrs, model_id)

    return normalized_records


def apply_enum_validation_for_instance(instance_data: dict, attrs: list[dict]) -> dict:
    """
    校验并规范化实例数据中的枚举字段值

    功能:
    1. 遍历所有 enum 类型字段
    2. 根据 enum_select_mode 校验值的数量
    3. 校验值是否在有效选项范围内
    4. 统一将值存储为列表格式

    Args:
        instance_data: 实例数据字典
        attrs: 模型字段定义列表

    Returns:
        规范化后的实例数据（原对象被修改）

    Raises:
        BaseAppException: 校验失败时抛出
    """
    data = dict(instance_data)

    for attr in attrs:
        if attr.get("attr_type") != "enum":
            continue

        attr_id = attr.get("attr_id", "")
        if not attr_id or attr_id not in data:
            continue

        mode = str(attr.get("enum_select_mode") or ENUM_SELECT_MODE_DEFAULT)
        required = attr.get("is_required", False)
        options = attr.get("option") or []
        option_ids = {str(opt.get("id")) for opt in options if opt}

        raw_value = data.get(attr_id)
        normalized_values = normalize_enum_values(raw_value)

        validate_enum_values(
            values=normalized_values,
            mode=mode,
            option_ids=option_ids,
            required=required,
            attr_id=attr_id,
        )

        data[attr_id] = normalized_values

    return data


class InstanceManage(object):
    @staticmethod
    def _query_instance_map_by_ids(inst_ids: set[int]) -> dict[int, dict]:
        normalized_ids = []
        for inst_id in inst_ids:
            try:
                normalized_ids.append(int(inst_id))
            except (TypeError, ValueError):
                continue
        if not normalized_ids:
            return {}

        with GraphClient() as ag:
            inst_list, _ = ag.query_entity(INSTANCE, [{"field": "id", "type": "id[]", "value": sorted(normalized_ids)}])

        result = {}
        for instance in inst_list:
            if instance.get("_id") is None:
                continue
            try:
                result[int(instance["_id"])] = instance
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def search_inst_batch(model_id: str, inst_uuids=None, inst_names=None, **kwargs) -> dict:
        """按 inst_uuid 或 inst_name 批量查询同一模型下的实例。返回 {str(key): instance}。"""
        if kwargs.get("ids") is not None or kwargs.get("_id") is not None:
            raise BaseAppException("请使用 inst_uuid/inst_uuids 定位实例，不再支持数字 ID")
        inst_uuids = [normalize_inst_uuid(value) for value in (inst_uuids or [])]
        inst_names = [str(n) for n in (inst_names or []) if str(n).strip()]
        if not inst_uuids and not inst_names:
            return {}

        result = {}

        def _run(extra_param):
            params = [{"field": "model_id", "type": "str=", "value": model_id}, extra_param]
            with GraphClient() as ag:
                inst_list, _ = ag.query_entity(INSTANCE, params)
            for inst in inst_list:
                if inst.get("inst_uuid"):
                    result[str(inst["inst_uuid"])] = inst
                if inst.get("inst_name") is not None:
                    result.setdefault(str(inst["inst_name"]), inst)

        if inst_uuids:
            _run({"field": "inst_uuid", "type": "str[]", "value": sorted(set(inst_uuids))})
        if inst_names:
            _run({"field": "inst_name", "type": "str[]", "value": list(set(inst_names))})
        return result

    @staticmethod
    def query_entity_page_by_ids(
        inst_ids: list[int],
        page: int = 1,
        page_size: int = 50,
        order: str = "inst_name",
        filters: list[dict] | None = None,
        permission_map: dict | None = None,
        creator: str = "",
    ):
        """按 ID 候选集在图查询层排序分页，避免先加载实体再在 Service 内切片。"""
        normalized_ids = sorted({int(inst_id) for inst_id in inst_ids if str(inst_id).strip()})
        if not normalized_ids:
            return [], 0

        normalized_page = max(1, int(page))
        normalized_page_size = max(1, int(page_size))
        normalized_order = str(order or "inst_name")
        order_type = "ASC"
        if normalized_order.startswith("-"):
            normalized_order = normalized_order[1:]
            order_type = "DESC"

        with GraphClient() as ag:
            return ag.query_entity(
                INSTANCE,
                [{"field": "id", "type": "id[]", "value": normalized_ids}, *(filters or [])],
                page={"skip": (normalized_page - 1) * normalized_page_size, "limit": normalized_page_size},
                order=normalized_order,
                order_type=order_type,
                format_permission_dict=InstanceManage._build_format_permission_dict(permission_map or {}, creator),
            )

    @staticmethod
    def count_entity_by_ids(
        inst_ids: list[int],
        permission_map: dict | None = None,
        creator: str = "",
        filters: list[dict] | None = None,
    ) -> int:
        normalized_ids = sorted({int(inst_id) for inst_id in inst_ids if str(inst_id).strip()})
        if not normalized_ids:
            return 0
        with GraphClient() as ag:
            _rows, count = ag.query_entity(
                INSTANCE,
                [{"field": "id", "type": "id[]", "value": normalized_ids}, *(filters or [])],
                page={"skip": 0, "limit": 0},
                include_count=True,
                format_permission_dict=InstanceManage._build_format_permission_dict(permission_map or {}, creator),
            )
        return int(count or 0)

    @staticmethod
    def _has_topology_view_permission(instance: dict | None, permission_map: dict | None, user=None) -> bool:
        if instance is None:
            return False
        if not permission_map:
            return True

        username = getattr(user, "username", "") if user is not None else ""
        if username and instance.get("_creator") == username:
            allowed_org_ids = set()
            for org_id in permission_map.keys():
                try:
                    allowed_org_ids.add(int(org_id))
                except (TypeError, ValueError):
                    continue
            instance_org_ids = set()
            for org_id in instance.get("organization", []) or []:
                try:
                    instance_org_ids.add(int(org_id))
                except (TypeError, ValueError):
                    continue
            if allowed_org_ids & instance_org_ids:
                return True

        return CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_INSTANCES,
            operator=VIEW,
            model_id=instance.get("model_id", ""),
            permission_instances_map=permission_map,
            instance=instance,
        )

    @classmethod
    def _collect_topology_node_ids(cls, node: dict | None) -> set[int]:
        if not isinstance(node, dict):
            return set()

        result = set()
        node_id = node.get("_id")
        try:
            if node_id is not None:
                result.add(int(node_id))
        except (TypeError, ValueError):
            pass

        for child in node.get("children") or []:
            result.update(cls._collect_topology_node_ids(child))
        return result

    @classmethod
    def _prune_topology_node(cls, node: dict | None, visible_ids: set[int], center_id: int) -> dict:
        if not isinstance(node, dict):
            return {}

        node_id = node.get("_id")
        try:
            normalized_node_id = int(node_id) if node_id is not None else None
        except (TypeError, ValueError):
            normalized_node_id = None

        if normalized_node_id is None:
            return {}
        if normalized_node_id != center_id and normalized_node_id not in visible_ids:
            return {}

        filtered_node = dict(node)
        filtered_children = []
        for child in node.get("children") or []:
            filtered_child = cls._prune_topology_node(child, visible_ids, center_id)
            if filtered_child:
                filtered_children.append(filtered_child)
        filtered_node["children"] = filtered_children
        return filtered_node

    @classmethod
    def _filter_topology_result(
        cls,
        result: dict,
        center_id: int,
        permission_map: dict | None = None,
        user=None,
    ) -> dict:
        if not isinstance(result, dict) or not permission_map:
            return result

        node_ids = set()
        for key in ("src_result", "dst_result"):
            node_ids.update(cls._collect_topology_node_ids(result.get(key)))
        if not node_ids:
            return result

        instances_map = cls._query_instance_map_by_ids(node_ids)
        visible_ids = {int(center_id)}
        for node_id in node_ids:
            if node_id == center_id:
                continue
            if cls._has_topology_view_permission(instances_map.get(node_id), permission_map, user=user):
                visible_ids.add(node_id)

        filtered_result = dict(result)
        for key in ("src_result", "dst_result"):
            filtered_result[key] = cls._prune_topology_node(result.get(key), visible_ids, int(center_id))
        return filtered_result

    @classmethod
    def _transport_topology_result(cls, result: dict) -> dict:
        """把通用拓扑树递归转换为只暴露 inst_uuid 的 Transport DTO。"""
        if not isinstance(result, dict):
            return result

        graph_ids = set()
        for key in ("src_result", "dst_result"):
            graph_ids.update(cls._collect_topology_node_ids(result.get(key)))
        instances_map = cls._query_instance_map_by_ids(graph_ids) if graph_ids else {}
        uuid_by_id = {
            int(graph_id): item.get("inst_uuid") for graph_id, item in instances_map.items() if isinstance(item, dict) and item.get("inst_uuid")
        }

        def transport_node(node: dict | None) -> dict:
            if not isinstance(node, dict) or node.get("_id") is None:
                return {}
            try:
                graph_id = int(node["_id"])
            except (TypeError, ValueError):
                return {}
            inst_uuid = node.get("inst_uuid") or uuid_by_id.get(graph_id)
            if not inst_uuid:
                return {}
            transported = {key: value for key, value in node.items() if key not in {"_id", "inst_id", "children"}}
            transported["inst_uuid"] = inst_uuid
            transported["children"] = [child for item in node.get("children") or [] if (child := transport_node(item))]
            return transported

        return {
            **result,
            "src_result": transport_node(result.get("src_result")),
            "dst_result": transport_node(result.get("dst_result")),
        }

    @staticmethod
    def _build_format_permission_dict(permission_map: dict, creator: str = "") -> dict:
        format_permission_dict = {}
        for organization_id, organization_permission_data in permission_map.items():
            _query_list = []
            inst_names = organization_permission_data["inst_names"]
            if inst_names:
                _query_list.append({"field": "inst_name", "type": "str[]", "value": inst_names})
                if creator:
                    _query_list.append({"field": "_creator", "type": "str=", "value": creator})
            format_permission_dict[organization_id] = _query_list
        return format_permission_dict

    @staticmethod
    def _build_check_attr_map(attrs: list, for_update: bool = False) -> dict:
        check_attr_map = {"is_only": {}, "is_required": {}}
        if for_update:
            check_attr_map["editable"] = {}

        for attr in attrs:
            attr_id = attr["attr_id"]
            attr_name = attr["attr_name"]
            if attr.get("is_only"):
                check_attr_map["is_only"][attr_id] = attr_name
            if attr.get("is_required"):
                check_attr_map["is_required"][attr_id] = attr_name
            if for_update and (attr.get("editable") or attr.get("is_display_field")):
                check_attr_map["editable"][attr_id] = attr_name

        return check_attr_map

    @staticmethod
    def _build_unique_rule_check_attr_map(model_id: str, attrs: list, for_update: bool = False) -> dict:
        check_attr_map = InstanceManage._build_check_attr_map(attrs, for_update=for_update)
        ctx = build_unique_rule_context(model_id)
        check_attr_map["unique_rules"] = ctx.unique_rules
        check_attr_map["attrs_by_id"] = ctx.attrs_by_id
        return check_attr_map

    @staticmethod
    def _allow_system_link_attrs_for_internal_write(check_attr_map: dict) -> None:
        """内部写路径可更新/清空系统联动字段（模型上 editable=False，用户路径仍剔除）。"""
        from apps.cmdb.services.module_ingest import SYSTEM_LINK_ATTR_IDS

        editable = check_attr_map.setdefault("editable", {})
        for attr_id in SYSTEM_LINK_ATTR_IDS:
            editable.setdefault(attr_id, attr_id)

    @staticmethod
    def _unique_candidate_param(field: str, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, bool):
            return {"field": field, "type": "str=", "value": str(value).lower()}
        if isinstance(value, int):
            return {"field": field, "type": "int=", "value": value}
        if isinstance(value, (dict, list, tuple, set)):
            return None
        return {"field": field, "type": "str=", "value": value}

    @classmethod
    def _query_unique_rule_candidates(cls, graph, model_id: str, item: dict, check_attr_map: dict) -> list[dict]:
        """只查询可能命中内置/联合唯一签名的实例；规则数上限使查询次数有固定上界。"""
        candidate_queries = []
        for field in check_attr_map.get("is_only", {}):
            param = cls._unique_candidate_param(field, item.get(field))
            if param:
                candidate_queries.append([param])

        for rule in check_attr_map.get("unique_rules", []):
            params = [cls._unique_candidate_param(field, item.get(field)) for field in rule.field_ids]
            if params and all(params):
                candidate_queries.append(params)

        candidates = {}
        for unique_params in candidate_queries:
            rows, _ = graph.query_entity(
                INSTANCE,
                [{"field": "model_id", "type": "str=", "value": model_id}, *unique_params],
            )
            for row in rows:
                key = row.get("_id")
                if key is None:
                    key = repr(sorted(row.items()))
                candidates[key] = row
        return list(candidates.values())

    @staticmethod
    def _apply_display_fields_to_update(attrs: list, update_attr: dict) -> None:
        from apps.cmdb.display_field import DisplayFieldConverter

        for attr in attrs:
            attr_id = attr.get("attr_id")
            attr_type = attr.get("attr_type")

            if attr_type not in DISPLAY_FIELD_TYPES or attr_id not in update_attr:
                continue

            display_field_id = f"{attr_id}{DISPLAY_SUFFIX}"
            original_value = update_attr[attr_id]

            if attr_type == FIELD_TYPE_ORGANIZATION:
                display_value = DisplayFieldConverter.convert_organization(original_value)
            elif attr_type == FIELD_TYPE_USER:
                display_value = DisplayFieldConverter.convert_user(original_value)
            elif attr_type == FIELD_TYPE_ENUM:
                display_value = DisplayFieldConverter.convert_enum(original_value, attr.get("option", []))
            elif attr_type == FIELD_TYPE_TAG:
                display_value = DisplayFieldConverter.convert_tag(original_value)
            elif attr_type == FIELD_TYPE_TABLE:
                display_value = DisplayFieldConverter.convert_table(original_value)
            else:
                continue

            update_attr[display_field_id] = display_value

    @classmethod
    def search_inst(
        cls,
        model_id: str,
        inst_name: str = None,
        inst_uuid: str = None,
        *,
        page: int | None = None,
        page_size: int | None = None,
        **kwargs,
    ):
        """查询实例；对外定位键为 inst_uuid，拒绝数字 ID 定位。"""
        if kwargs.get("_id") is not None or kwargs.get("ids") is not None:
            raise BaseAppException("请使用 inst_uuid/inst_uuids 定位实例，不再支持数字 ID")
        with GraphClient() as ag:
            params = [{"field": "model_id", "type": "str=", "value": model_id}]
            if inst_uuid:
                params.append({"field": "inst_uuid", "type": "str=", "value": normalize_inst_uuid(inst_uuid)})
            if inst_name:
                params.append({"field": "inst_name", "type": "str=", "value": inst_name})
            query = {"label": INSTANCE, "params": params}
            if page is not None or page_size is not None:
                normalized_page = max(1, int(page or 1))
                normalized_page_size = max(1, int(page_size or 50))
                query["page"] = {
                    "skip": (normalized_page - 1) * normalized_page_size,
                    "limit": normalized_page_size,
                }
            inst_list, count = ag.query_entity(**query)
        return inst_list, count

    @staticmethod
    def get_permission_params(user_groups, roles):
        """获取用户实例权限查询参数，用户用户查询实例"""
        obj = PermissionManage(user_groups=user_groups, roles=roles)
        permission_params = obj.get_permission_params()
        return permission_params

    @staticmethod
    def check_instances_permission(
        instances: list,
        model_id: str,
        user_groups: list = None,
        roles: list = None,
    ):
        """实例权限校验，用于操作之前"""
        if not instances:
            return

        permission_params = InstanceManage.get_permission_params(user_groups=user_groups or [], roles=roles or [])
        inst_ids = [item["_id"] for item in instances if item.get("_id") is not None]
        query_params = [{"field": "model_id", "type": "str=", "value": model_id}]
        if inst_ids:
            query_params.append({"field": "id", "type": "id[]", "value": inst_ids})
        if permission_params:
            query_params.extend(permission_params)

        with GraphClient() as ag:
            inst_list, count = ag.query_entity(
                label=INSTANCE,
                params=query_params,
            )

        permission_map = {i["_id"]: i for i in inst_list}
        instances_map = {i["_id"]: i for i in instances}

        non_permission_set = set(instances_map.keys()) - set(permission_map.keys())

        if not non_permission_set:
            return
        message = f"实例：{'、'.join([instances_map[i]['inst_name'] for i in non_permission_set])}，无权限！"
        raise BaseAppException(message)

    @staticmethod
    def instance_list(
        model_id: str,
        params: list,
        page: int,
        page_size: int,
        order: str,
        permission_map: dict,
        creator: str = None,
        case_sensitive: bool = True,
    ):
        """实例列表"""

        params.append({"field": "model_id", "type": "str=", "value": model_id})

        format_permission_dict = InstanceManage._build_format_permission_dict(permission_map, creator)

        _page = dict(skip=(page - 1) * page_size, limit=page_size)
        order_type = "ASC"
        if order and order.startswith("-"):
            order = order[1:]
            order_type = "DESC"

        with GraphClient() as ag:
            query = dict(
                label=INSTANCE,
                params=params,
                page=_page,
                order=order,
                order_type=order_type,
                format_permission_dict=format_permission_dict,
                case_sensitive=case_sensitive,
            )
            inst_list, count = ag.query_entity(**query)
        return inst_list, count

    @staticmethod
    def instance_create(
        model_id: str,
        instance_info: dict,
        operator: str,
        allowed_org_ids: list | None = None,
        scenario: str = ORDINARY_ATTRIBUTE_CHANGE,
        record_change: bool = True,
        operation_id: str | None = None,
        schedule_post_actions: bool = True,
    ):
        """创建实例"""
        instance_info = prepare_new_instance_identity(dict(instance_info))
        instance_info.update(model_id=model_id)
        if operation_id:
            instance_info["_cmdb_operation_id"] = operation_id
        attrs = ModelManage.search_model_attr(model_id)
        instance_info = apply_tag_validation_for_instance(instance_info, attrs, model_id)
        instance_info = apply_enum_validation_for_instance(instance_info, attrs)
        if model_id == "subnet":
            from apps.cmdb.services.ipam_subnet import validate_subnet_no_overlap

            validate_subnet_no_overlap(instance_info)
        # 企业版附件/图片字段：校验并把值规范化为元数据 JSON
        instance_info = get_instance_enterprise_extension().normalize_file_fields(model_id, instance_info, attrs, operator=operator)
        validate_instance_organization_scope(instance_info, allowed_org_ids=allowed_org_ids)
        check_attr_map = InstanceManage._build_unique_rule_check_attr_map(
            model_id,
            attrs,
            for_update=False,
        )

        # 为 organization/user/enum 字段生成 _display 冗余字段
        from apps.cmdb.display_field import DisplayFieldHandler
        from apps.cmdb.services.unique_write_lock import UniqueWriteLockService

        instance_info = DisplayFieldHandler.build_display_fields(model_id, instance_info, attrs)
        unique_lock_keys = UniqueWriteLockService.build_lock_keys(model_id, instance_info, check_attr_map)

        with UniqueWriteLockService.hold(unique_lock_keys):
            with GraphClient() as ag:
                exist_items = InstanceManage._query_unique_rule_candidates(ag, model_id, instance_info, check_attr_map)
                result = ag.create_entity(INSTANCE, instance_info, check_attr_map, exist_items, operator, attrs)

        result = dict(result)
        result.pop("_cmdb_operation_id", None)

        # 企业版：实例创建后把引用文件落账（pending→committed 并补 inst_id）
        get_instance_enterprise_extension().commit_instance_files(model_id, result["_id"], result, attrs, operator=operator)

        if record_change:
            create_change_record(
                result["_id"],
                result["model_id"],
                INSTANCE,
                CREATE_INST,
                after_data=result,
                operator=operator,
                model_object=OPERATOR_INSTANCE,
                message=f"创建模型实例. 模型:{result['model_id']} 实例:{result.get('inst_name') or result.get('ip_addr', '')}",
                scenario=scenario,
            )

        if schedule_post_actions:
            try:
                from apps.cmdb.services.auto_relation_reconcile import schedule_instance_auto_relation_reconcile

                schedule_instance_auto_relation_reconcile([result["_id"]])
            except Exception:
                logger.exception(
                    "[InstanceManage] post-create auto_relation hook failed cmdb_id=%s",
                    result.get("_id"),
                )
            if model_id == "host":
                try:
                    result = InstanceManage._best_effort_notify_peers_on_host_create(result, operator=operator, allowed_org_ids=allowed_org_ids)
                except Exception:
                    logger.exception(
                        "[InstanceManage] post-create IoC hook failed cmdb_id=%s",
                        result.get("_id"),
                    )
        return result

    @staticmethod
    def _best_effort_notify_peers_on_host_create(
        result: dict,
        *,
        operator: str,
        allowed_org_ids: list | None,
    ) -> dict:
        """主机新建 IoC 钩子：通知节点 + 监控（best-effort，不阻断创建）。"""
        try:
            from apps.cmdb.services.module_push import CmdbToMonitorPushService

            return CmdbToMonitorPushService.best_effort_notify_on_host_create(
                result,
                operator=operator or "",
                allowed_org_ids=list(allowed_org_ids or []),
            )
        except Exception:
            logger.exception(
                "[InstanceManage] IoC notify peers failed cmdb_id=%s",
                result.get("_id"),
            )
            return result

    @staticmethod
    def _best_effort_auto_link_host_to_node(
        result: dict,
        *,
        operator: str,
        allowed_org_ids: list | None,
    ) -> dict:
        """兼容旧名：转发到 IoC 通知钩子。"""
        try:
            return InstanceManage._best_effort_notify_peers_on_host_create(result, operator=operator, allowed_org_ids=allowed_org_ids)
        except Exception:
            logger.exception(
                "[InstanceManage] auto-link host hook failed cmdb_id=%s",
                result.get("_id"),
            )
            return result

    @staticmethod
    def instance_batch_create(
        model_id: str,
        instances: list,
        operator: str,
        allowed_org_ids: list | None = None,
    ):
        """批量创建实例，任一图写失败时回滚本批已创建节点。"""
        attrs = ModelManage.search_model_attr(model_id)
        check_attr_map = InstanceManage._build_unique_rule_check_attr_map(
            model_id,
            attrs,
            for_update=False,
        )
        prepared = []
        for index, item in enumerate(instances):
            try:
                instance_info = prepare_new_instance_identity({**item, "model_id": model_id})
                instance_info = apply_tag_validation_for_instance(
                    instance_info,
                    attrs,
                    model_id,
                    persist_options=False,
                )
                instance_info = apply_enum_validation_for_instance(instance_info, attrs)
                if model_id == "subnet":
                    from apps.cmdb.services.ipam_subnet import validate_subnet_no_overlap

                    validate_subnet_no_overlap(instance_info)
                instance_info = get_instance_enterprise_extension().normalize_file_fields(
                    model_id,
                    instance_info,
                    attrs,
                    operator=operator,
                )
                validate_instance_organization_scope(
                    instance_info,
                    allowed_org_ids=allowed_org_ids,
                )
                prepared.append(DisplayFieldHandler.build_display_fields(model_id, instance_info, attrs))
            except BaseAppException as exc:
                raise InstanceBatchError(
                    "请求参数非法",
                    reason="validation",
                    index=index,
                ) from exc

        if model_id == "subnet":
            from apps.cmdb.services.ipam_subnet import find_batch_subnet_overlap_index

            conflict_index = find_batch_subnet_overlap_index(prepared)
            if conflict_index is not None:
                raise InstanceBatchError(
                    "请求参数非法",
                    reason="validation",
                    index=conflict_index,
                )

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(
                INSTANCE,
                [{"field": "model_id", "type": "str=", "value": model_id}],
            )
            from apps.cmdb.validators import FieldValidator

            for index, instance_info in enumerate(prepared):
                validation_errors = FieldValidator.validate_instance_data(instance_info, attrs)
                if validation_errors:
                    raise InstanceBatchError(
                        "请求参数非法",
                        reason="validation",
                        index=index,
                    )
                try:
                    ag.check_required_attr(
                        instance_info,
                        check_attr_map.get("is_required", {}),
                    )
                except BaseAppException as exc:
                    raise InstanceBatchError(
                        "请求参数非法",
                        reason="validation",
                        index=index,
                    ) from exc
            conflicts = collect_instance_unique_conflicts(
                check_attr_map,
                prepared,
                exist_items,
            )
            if conflicts:
                conflict = conflicts[0]
                raise InstanceBatchError(
                    "字段值违反唯一性约束",
                    reason="unique_conflict",
                    index=conflict.item_index,
                    field=conflict.field_ids[0],
                )
            persist_free_tag_options_for_instances(prepared, attrs, model_id)
            results = ag.batch_create_entity(
                INSTANCE,
                prepared,
                check_attr_map,
                exist_items,
                operator,
                attrs,
            )
            created = [item["data"] for item in results if item.get("success")]
            failed = next((item for item in results if not item.get("success")), None)
            if failed:
                original_error = BaseAppException(failed.get("message") or "批量创建失败")
                if created:
                    cleanup_ids = [item["_id"] for item in created]
                    try:
                        ag.batch_delete_entity(INSTANCE, cleanup_ids)
                    except Exception as cleanup_exc:
                        logger.error(
                            "[InstanceBatchCreate] rollback failed cleanup_ids=%s " "error_type=%s error_summary=cleanup_failed",
                            cleanup_ids,
                            type(cleanup_exc).__name__,
                        )
                raise original_error

        extension = get_instance_enterprise_extension()
        for item in created:
            extension.commit_instance_files(
                model_id,
                item["_id"],
                item,
                attrs,
                operator=operator,
            )

        change_records = [
            {
                "inst_id": item["_id"],
                "model_id": model_id,
                "after_data": item,
                "model_object": OPERATOR_INSTANCE,
                "message": (f"创建模型实例. 模型:{model_id} " f"实例:{item.get('inst_name') or item.get('ip_addr', '')}"),
            }
            for item in created
        ]
        batch_create_change_record(
            INSTANCE,
            CREATE_INST,
            change_records,
            operator=operator,
        )
        schedule_instance_auto_relation_reconcile([item["_id"] for item in created])
        return created

    @staticmethod
    def instance_update(
        user_groups: list,
        roles: list,
        inst_id: int,
        update_attr: dict,
        operator: str,
        allowed_org_ids: list | None = None,
        scenario: str = ORDINARY_ATTRIBUTE_CHANGE,
        skip_permission_check: bool = False,
        record_change: bool = True,
        operation_id: str | None = None,
        schedule_post_actions: bool = True,
    ):
        """修改实例属性"""
        from apps.cmdb.services.module_ingest import strip_system_link_fields

        update_attr = dict(update_attr)
        ensure_instance_identity_immutable(update_attr)
        # 用户写路径剔除系统联动字段；IoC 回填走 skip_permission_check=True 时保留
        if not skip_permission_check:
            update_attr = strip_system_link_fields(update_attr)
        inst_info = InstanceManage.query_entity_by_id(inst_id)

        if not inst_info:
            raise BaseAppException("实例不存在！")

        model_info = ModelManage.search_model_info(inst_info["model_id"])

        if not skip_permission_check:
            InstanceManage.check_instances_permission(
                [inst_info],
                inst_info["model_id"],
                user_groups=user_groups,
                roles=roles,
            )

        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
        update_attr = apply_tag_validation_for_instance(update_attr, attrs, inst_info["model_id"])
        update_attr = apply_enum_validation_for_instance(update_attr, attrs)
        if inst_info["model_id"] == "subnet":
            from apps.cmdb.services.ipam_subnet import validate_subnet_no_overlap

            merged = {
                "subnet_address": update_attr.get("subnet_address", inst_info.get("subnet_address")),
                "subnet_mask": update_attr.get("subnet_mask", inst_info.get("subnet_mask")),
            }
            validate_subnet_no_overlap(merged, exclude_inst_id=inst_id)
        # 企业版附件/图片字段：校验并规范化（old_instance 用于跨实例引用校验）
        update_attr = get_instance_enterprise_extension().normalize_file_fields(
            inst_info["model_id"], update_attr, attrs, operator=operator, old_instance=inst_info
        )
        validate_instance_organization_scope(update_attr, user_groups=user_groups, allowed_org_ids=allowed_org_ids)
        check_attr_map = InstanceManage._build_unique_rule_check_attr_map(
            inst_info["model_id"],
            attrs,
            for_update=True,
        )
        if skip_permission_check:
            InstanceManage._allow_system_link_attrs_for_internal_write(check_attr_map)

        InstanceManage._apply_display_fields_to_update(attrs, update_attr)
        if operation_id:
            update_attr["_cmdb_operation_id"] = operation_id

        from apps.cmdb.services.unique_write_lock import UniqueWriteLockService

        validation_item = {**inst_info, **update_attr}
        check_attr_map["validation_items"] = [validation_item]
        unique_lock_keys = UniqueWriteLockService.build_lock_keys(inst_info["model_id"], validation_item, check_attr_map)
        with UniqueWriteLockService.hold(unique_lock_keys):
            with GraphClient() as ag:
                exist_items = InstanceManage._query_unique_rule_candidates(ag, inst_info["model_id"], validation_item, check_attr_map)
                exist_items = [i for i in exist_items if i["_id"] != inst_id]
                result = ag.set_entity_properties(
                    INSTANCE,
                    [inst_id],
                    update_attr,
                    check_attr_map,
                    exist_items,
                    attrs=attrs,
                )
            result[0] = dict(result[0])
            result[0].pop("_cmdb_operation_id", None)

            # 企业版：实例更新后落账（引用文件 committed、移除文件 orphaned）
            get_instance_enterprise_extension().commit_instance_files(inst_info["model_id"], result[0]["_id"], result[0], attrs, operator=operator)

            if record_change:
                create_change_record(
                    inst_info["_id"],
                    inst_info["model_id"],
                    INSTANCE,
                    UPDATE_INST,
                    before_data=inst_info,
                    after_data=result[0],
                    operator=operator,
                    model_object=OPERATOR_INSTANCE,
                    message=f"修改模型实例属性. 模型:{model_info['model_name']} 实例:{result[0]['inst_name']}",
                    scenario=scenario,
                )

            if schedule_post_actions:
                from apps.cmdb.services.auto_relation_reconcile import schedule_instance_auto_relation_reconcile

                schedule_instance_auto_relation_reconcile([result[0]["_id"]])

            return result[0]

    @staticmethod
    def instance_update_by_uuid(
        user_groups: list,
        roles: list,
        inst_uuid: str,
        update_attr: dict,
        operator: str,
        allowed_org_ids: list | None = None,
        **kwargs,
    ):
        """按业务身份修改实例，图内部 ID 不越过服务边界。"""
        inst_info = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not inst_info:
            raise BaseAppException("实例不存在！")
        return InstanceManage.instance_update(
            user_groups,
            roles,
            inst_info["_id"],
            update_attr,
            operator,
            allowed_org_ids=allowed_org_ids,
            **kwargs,
        )

    @staticmethod
    def batch_instance_update(
        user_groups: list,
        roles: list,
        inst_ids: list,
        update_attr: dict,
        operator: str,
        allowed_org_ids: list | None = None,
    ):
        """批量修改实例属性"""

        update_attr = dict(update_attr)
        ensure_instance_identity_immutable(update_attr)
        inst_ids = _normalize_batch_instance_ids(inst_ids)
        inst_list = _require_complete_batch_instances(
            inst_ids,
            InstanceManage.query_entity_by_ids(inst_ids),
        )

        model_info = ModelManage.search_model_info(inst_list[0]["model_id"])

        InstanceManage.check_instances_permission(
            inst_list,
            model_info["model_id"],
            user_groups=user_groups,
            roles=roles,
        )

        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
        update_attr = apply_tag_validation_for_instance(update_attr, attrs, model_info["model_id"])
        update_attr = apply_enum_validation_for_instance(update_attr, attrs)
        # 企业版附件/图片字段：校验并规范化（与 instance_create/instance_update 一致）。
        # 单实例编辑（前端 type='edit'）携带 old_instance 以支持保留已提交文件。
        update_attr = get_instance_enterprise_extension().normalize_file_fields(
            model_info["model_id"],
            update_attr,
            attrs,
            operator=operator,
            old_instance=inst_list[0] if len(inst_ids) == 1 else None,
        )
        validate_instance_organization_scope(update_attr, user_groups=user_groups, allowed_org_ids=allowed_org_ids)
        check_attr_map = InstanceManage._build_unique_rule_check_attr_map(
            model_info["model_id"],
            attrs,
            for_update=True,
        )

        InstanceManage._apply_display_fields_to_update(attrs, update_attr)

        with GraphClient() as ag:
            all_exist_items, _ = ag.query_entity(
                INSTANCE,
                [
                    {
                        "field": "model_id",
                        "type": "str=",
                        "value": model_info["model_id"],
                    }
                ],
            )
            merged_instances = [{**instance, **update_attr} for instance in inst_list]
            conflicts = collect_instance_unique_conflicts(
                check_attr_map,
                merged_instances,
                all_exist_items,
                exclude_instance_ids=set(inst_ids),
            )
            if conflicts:
                conflict = conflicts[0]
                conflict_instance = merged_instances[conflict.item_index]
                raise InstanceBatchError(
                    "字段值违反唯一性约束",
                    reason="unique_conflict",
                    inst_id=conflict_instance["_id"],
                    field=conflict.field_ids[0],
                )
            exist_items = [i for i in all_exist_items if i["_id"] not in inst_ids]
            result = ag.set_entity_properties(
                INSTANCE,
                inst_ids,
                update_attr,
                check_attr_map,
                exist_items,
                attrs=attrs,
            )

        result_ids = {int(item["_id"]) for item in result if item.get("_id") is not None}
        missing_result_ids = [inst_id for inst_id in inst_ids if inst_id not in result_ids]
        if missing_result_ids or len(result_ids) != len(inst_ids) or len(result) != len(inst_ids):
            mismatch_id = (
                missing_result_ids[0]
                if missing_result_ids
                else _find_duplicate_or_unexpected_batch_id(
                    inst_ids,
                    result,
                )
            )
            raise InstanceBatchError(
                "批量更新结果不完整",
                reason="incomplete",
                inst_id=mismatch_id,
            )

        # 企业版：实例更新后对每个实例提交文件落账（pending→committed、移除文件标 orphaned）
        ext = get_instance_enterprise_extension()
        for updated in result:
            ext.commit_instance_files(model_info["model_id"], updated["_id"], updated, attrs, operator=operator)

        after_dict = {i["_id"]: i for i in result}
        change_records = [
            dict(
                inst_id=i["_id"],
                model_id=i["model_id"],
                before_data=i,
                after_data=after_dict.get(i["_id"]),
                model_object=OPERATOR_INSTANCE,
                message=f"修改模型实例属性. 模型:{model_info['model_name']} 实例:{i.get('inst_name') or i.get('ip_addr', '')}",
            )
            for i in inst_list
        ]
        batch_create_change_record(INSTANCE, UPDATE_INST, change_records, operator=operator)

        schedule_instance_auto_relation_reconcile([item["_id"] for item in result])

        return result

    @staticmethod
    def instance_batch_delete(user_groups: list, roles: list, inst_ids: list, operator: str):
        """批量删除实例"""
        inst_ids = _normalize_batch_instance_ids(inst_ids)
        inst_list = _require_complete_batch_instances(
            inst_ids,
            InstanceManage.query_entity_by_ids(inst_ids),
        )

        model_info = ModelManage.search_model_info(inst_list[0]["model_id"])

        InstanceManage.check_instances_permission(
            inst_list,
            inst_list[0]["model_id"],
            user_groups=user_groups,
            roles=roles,
        )

        # 先写 PG 变更记录，再删图数据库节点。
        # 若 PG 写入失败则直接抛出，图删除不执行，两侧保持一致；
        # 反之若先删图再写 PG，图删除提交后无法回滚，PG 失败会导致审计日志丢失（#3665）。
        change_records = [
            dict(
                inst_id=i["_id"],
                model_id=i["model_id"],
                before_data=i,
                model_object=OPERATOR_INSTANCE,
                message=f"删除模型实例. 模型:{model_info['model_name']} 实例:{i.get('inst_name') or i.get('ip_addr', '')}",
            )
            for i in inst_list
        ]
        batch_create_change_record(INSTANCE, DELETE_INST, change_records, operator=operator)

        with GraphClient() as ag:
            ag.batch_delete_entity(INSTANCE, inst_ids)

        # 企业版：实例删除后把其附件/图片文件标记为待回收（批量单次处理）
        get_instance_enterprise_extension().on_instances_delete([item["_id"] for item in inst_list])

        from apps.cmdb.services.auto_relation_reconcile import schedule_incoming_rule_full_sync_by_model_ids

        schedule_incoming_rule_full_sync_by_model_ids([item["model_id"] for item in inst_list])

        # IoC：删除后通知节点/监控只清关联 ID（best-effort，不阻断删除）
        try:
            from apps.cmdb.services.module_push import CmdbToMonitorPushService

            CmdbToMonitorPushService.best_effort_notify_on_delete(
                inst_list,
                operator=operator or "",
                allowed_org_ids=None,
            )
        except Exception:
            logger.exception(
                "[InstanceManage] delete IoC notify failed inst_ids=%s",
                inst_ids,
            )

    @staticmethod
    def batch_instance_update_by_uuids(
        user_groups: list,
        roles: list,
        inst_uuids: list[str],
        update_attr: dict,
        operator: str,
        allowed_org_ids: list | None = None,
    ):
        inst_uuids = _normalize_batch_instance_uuids(inst_uuids)
        instances = _require_complete_batch_instances_by_uuid(
            inst_uuids,
            InstanceManage.query_entity_by_uuids(inst_uuids),
        )
        try:
            return InstanceManage.batch_instance_update(
                user_groups,
                roles,
                [item["_id"] for item in instances],
                update_attr,
                operator,
                allowed_org_ids,
            )
        except InstanceBatchError as exc:
            uuid_by_id = {item["_id"]: item.get("inst_uuid") for item in instances}
            raise InstanceBatchError(
                exc.message,
                reason=exc.reason,
                index=exc.index,
                inst_uuid=uuid_by_id.get(exc.inst_id) or exc.inst_uuid,
                field=exc.field,
            ) from exc

    @staticmethod
    def instance_batch_delete_by_uuids(
        user_groups: list,
        roles: list,
        inst_uuids: list[str],
        operator: str,
    ):
        inst_uuids = _normalize_batch_instance_uuids(inst_uuids)
        instances = _require_complete_batch_instances_by_uuid(
            inst_uuids,
            InstanceManage.query_entity_by_uuids(inst_uuids),
        )
        try:
            InstanceManage.instance_batch_delete(
                user_groups,
                roles,
                [item["_id"] for item in instances],
                operator,
            )
        except InstanceBatchError as exc:
            uuid_by_id = {item["_id"]: item.get("inst_uuid") for item in instances}
            raise InstanceBatchError(
                exc.message,
                reason=exc.reason,
                index=exc.index,
                inst_uuid=uuid_by_id.get(exc.inst_id) or exc.inst_uuid,
                field=exc.field,
            ) from exc

    @staticmethod
    def instance_association_instance_list(
        model_id: str,
        inst_id: int,
        *,
        business_only: bool = False,
        language: str = "en",
    ):
        """内部按图节点 ID 查询；解析为 UUID 后走边端点 UUID 属性过滤。"""
        instance = InstanceManage.query_entity_by_id(inst_id)
        if not instance or not instance.get("inst_uuid"):
            return []
        return InstanceManage.instance_association_instance_list_by_uuid(
            model_id,
            instance["inst_uuid"],
            business_only=business_only,
            language=language,
        )

    @staticmethod
    def instance_association_instance_list_by_uuid(
        model_id: str,
        inst_uuid: str,
        *,
        business_only: bool = False,
        language: str = "en",
    ):
        """按边端点 UUID 属性查询关联实例列表。"""
        inst_uuid = normalize_inst_uuid(inst_uuid)
        with GraphClient() as ag:
            src_edge = ag.query_edge(
                INSTANCE_ASSOCIATION,
                [
                    {"field": "src_inst_uuid", "type": "str=", "value": inst_uuid},
                    {"field": "src_model_id", "type": "str=", "value": model_id},
                ],
                return_entity=True,
            )
            dst_edge = ag.query_edge(
                INSTANCE_ASSOCIATION,
                [
                    {"field": "dst_inst_uuid", "type": "str=", "value": inst_uuid},
                    {"field": "dst_model_id", "type": "str=", "value": model_id},
                ],
                return_entity=True,
            )

        edge_items = src_edge + dst_edge
        # 兼容创建时未落盘 model_id 边属性：回退按端点实体过滤
        if not edge_items:
            with GraphClient() as ag:
                all_items = ag.query_edge(INSTANCE_ASSOCIATION, [], return_entity=True)
            edge_items = [
                item
                for item in all_items
                if (
                    ((item.get("src") or {}).get("inst_uuid") == inst_uuid and (item.get("src") or {}).get("model_id") == model_id)
                    or ((item.get("dst") or {}).get("inst_uuid") == inst_uuid and (item.get("dst") or {}).get("model_id") == model_id)
                )
            ]

        visible_associations = {}
        if business_only:
            from apps.cmdb.services.model_visibility import BusinessModelVisibility

            visible_associations = {
                item["model_asst_id"]: item
                for item in BusinessModelVisibility.filter_associations(
                    [item["edge"] for item in edge_items],
                    language=language,
                )
            }
            edge_items = [item for item in edge_items if item["edge"].get("model_asst_id") in visible_associations]

        result = {}
        for item in edge_items:
            edge = item["edge"]
            model_asst_id = edge["model_asst_id"]
            src = item.get("src") or {}
            dst = item.get("dst") or {}
            src_model_id = edge.get("src_model_id") or src.get("model_id")
            dst_model_id = edge.get("dst_model_id") or dst.get("model_id")
            item_key = "src" if model_id == dst_model_id else "dst"
            if model_asst_id not in result:
                visible_association = visible_associations.get(model_asst_id, {})
                result[model_asst_id] = {
                    "src_model_id": src_model_id,
                    "dst_model_id": dst_model_id,
                    "model_asst_id": model_asst_id,
                    "asst_id": edge.get("asst_id"),
                    "src_model_name": visible_association.get("src_model_name", ""),
                    "dst_model_name": visible_association.get("dst_model_name", ""),
                    "src_model_icn": visible_association.get("src_model_icn", ""),
                    "dst_model_icn": visible_association.get("dst_model_icn", ""),
                    "inst_list": [],
                }
            peer = dict(item[item_key])
            peer.update(inst_asst_id=edge["_id"])
            result[model_asst_id]["inst_list"].append(peer)

        return list(result.values())

    @staticmethod
    def instance_association(
        model_id: str,
        inst_id: int,
        *,
        business_only: bool = False,
        language: str = "en",
    ):
        """内部按图节点 ID 查询关联边。"""
        instance = InstanceManage.query_entity_by_id(inst_id)
        if not instance or not instance.get("inst_uuid"):
            return []
        return InstanceManage.instance_association_by_uuid(
            model_id,
            instance["inst_uuid"],
            business_only=business_only,
            language=language,
        )

    @staticmethod
    def instance_association_by_uuid(
        model_id: str,
        inst_uuid: str,
        *,
        business_only: bool = False,
        language: str = "en",
    ):
        """按边端点 UUID 属性查询关联边。"""
        inst_uuid = normalize_inst_uuid(inst_uuid)
        with GraphClient() as ag:
            src_edge = ag.query_edge(
                INSTANCE_ASSOCIATION,
                [
                    {"field": "src_inst_uuid", "type": "str=", "value": inst_uuid},
                    {"field": "src_model_id", "type": "str=", "value": model_id},
                ],
            )
            dst_edge = ag.query_edge(
                INSTANCE_ASSOCIATION,
                [
                    {"field": "dst_inst_uuid", "type": "str=", "value": inst_uuid},
                    {"field": "dst_model_id", "type": "str=", "value": model_id},
                ],
            )
        edges = src_edge + dst_edge
        if not edges:
            with GraphClient() as ag:
                items = ag.query_edge(INSTANCE_ASSOCIATION, [], return_entity=True)
            edges = [
                item["edge"]
                for item in items
                if (
                    ((item.get("src") or {}).get("inst_uuid") == inst_uuid and (item.get("src") or {}).get("model_id") == model_id)
                    or ((item.get("dst") or {}).get("inst_uuid") == inst_uuid and (item.get("dst") or {}).get("model_id") == model_id)
                )
            ]
        if business_only:
            from apps.cmdb.services.model_visibility import BusinessModelVisibility

            return BusinessModelVisibility.filter_associations(
                edges,
                language=language,
            )
        return edges

    @staticmethod
    def instance_association_map(model_id: str, inst_ids: list[int], related_model: str | None = None) -> dict[int, list[int]]:
        """批量查询实例关联映射（内部图 ID）；边过滤优先使用 UUID 端点属性。"""

        normalized_ids: list[int] = []
        seen_ids: set[int] = set()
        for inst_id in inst_ids:
            try:
                normalized_id = int(inst_id)
            except (TypeError, ValueError):
                continue
            if normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            normalized_ids.append(normalized_id)

        if not normalized_ids:
            return {}

        instances = InstanceManage.query_entity_by_ids(normalized_ids)
        uuid_by_id = {int(item["_id"]): item.get("inst_uuid") for item in instances if item.get("_id") is not None and item.get("inst_uuid")}
        id_by_uuid = {uuid: inst_id for inst_id, uuid in uuid_by_id.items()}
        relation_uuid_map = InstanceManage.instance_association_map_by_uuids(
            model_id,
            [uuid_by_id[inst_id] for inst_id in normalized_ids if inst_id in uuid_by_id],
            related_model=related_model,
        )
        missing_related_uuids = sorted(
            {related_uuid for related_uuids in relation_uuid_map.values() for related_uuid in related_uuids if related_uuid not in id_by_uuid}
        )
        if missing_related_uuids:
            for related in InstanceManage.query_entity_by_uuids(missing_related_uuids):
                if related.get("_id") is None or not related.get("inst_uuid"):
                    continue
                id_by_uuid[related["inst_uuid"]] = int(related["_id"])

        relation_map: dict[int, list[int]] = {inst_id: [] for inst_id in normalized_ids}
        for inst_id in normalized_ids:
            inst_uuid = uuid_by_id.get(inst_id)
            if not inst_uuid:
                continue
            related_ids = [id_by_uuid[related_uuid] for related_uuid in relation_uuid_map.get(inst_uuid, []) if related_uuid in id_by_uuid]
            relation_map[inst_id] = sorted(set(related_ids))
        return relation_map

    @staticmethod
    def instance_association_map_by_uuids(
        model_id: str,
        inst_uuids: list[str],
        related_model: str | None = None,
    ) -> dict[str, list[str]]:
        normalized = [normalize_inst_uuid(value) for value in inst_uuids]
        relation_map: dict[str, set[str]] = {value: set() for value in normalized}
        if not relation_map:
            return {}

        with GraphClient() as ag:
            src_query = [
                {"field": "src_inst_uuid", "type": "str[]", "value": normalized},
                {"field": "src_model_id", "type": "str=", "value": model_id},
            ]
            if related_model:
                src_query.append({"field": "dst_model_id", "type": "str=", "value": related_model})
            src_edges = ag.query_edge(INSTANCE_ASSOCIATION, src_query)

            dst_query = [
                {"field": "dst_inst_uuid", "type": "str[]", "value": normalized},
                {"field": "dst_model_id", "type": "str=", "value": model_id},
            ]
            if related_model:
                dst_query.append({"field": "src_model_id", "type": "str=", "value": related_model})
            dst_edges = ag.query_edge(INSTANCE_ASSOCIATION, dst_query)

        for edge in src_edges:
            src_uuid = edge.get("src_inst_uuid")
            dst_uuid = edge.get("dst_inst_uuid")
            if src_uuid in relation_map and dst_uuid:
                relation_map[src_uuid].add(dst_uuid)

        for edge in dst_edges:
            dst_uuid = edge.get("dst_inst_uuid")
            src_uuid = edge.get("src_inst_uuid")
            if dst_uuid in relation_map and src_uuid:
                relation_map[dst_uuid].add(src_uuid)

        # 兼容边上缺少 model_id 属性的存量/旁路写入：回退到端点实体过滤
        if not any(relation_map.values()):
            with GraphClient() as ag:
                items = ag.query_edge(INSTANCE_ASSOCIATION, [], return_entity=True)
            for item in items:
                src = item.get("src") or {}
                dst = item.get("dst") or {}
                src_uuid = src.get("inst_uuid")
                dst_uuid = dst.get("inst_uuid")
                if (
                    src_uuid in relation_map
                    and src.get("model_id") == model_id
                    and (not related_model or dst.get("model_id") == related_model)
                    and dst_uuid
                ):
                    relation_map[src_uuid].add(dst_uuid)
                if (
                    dst_uuid in relation_map
                    and dst.get("model_id") == model_id
                    and (not related_model or src.get("model_id") == related_model)
                    and src_uuid
                ):
                    relation_map[dst_uuid].add(src_uuid)

        return {key: sorted(values) for key, values in relation_map.items()}

    @staticmethod
    def _resolve_association_endpoint_uuids(data: dict) -> tuple[str, str]:
        src_uuid = data.get("src_inst_uuid")
        dst_uuid = data.get("dst_inst_uuid")
        if src_uuid and dst_uuid:
            return normalize_inst_uuid(src_uuid), normalize_inst_uuid(dst_uuid)
        src = InstanceManage.query_entity_by_id(data["src_inst_id"]) if data.get("src_inst_id") is not None else {}
        dst = InstanceManage.query_entity_by_id(data["dst_inst_id"]) if data.get("dst_inst_id") is not None else {}
        if not src.get("inst_uuid") or not dst.get("inst_uuid"):
            raise BaseAppException("实例不存在或缺少 inst_uuid")
        return normalize_inst_uuid(src["inst_uuid"]), normalize_inst_uuid(dst["inst_uuid"])

    @staticmethod
    def check_asso_mapping(data: dict):
        """校验关联关系的约束；边端点以 UUID 属性过滤。"""
        asso_info = ModelManage.model_association_info_search(data["model_asst_id"])
        if not asso_info:
            raise BaseAppException("association not found!")

        # n:n关联不做校验
        if asso_info["mapping"] == "n:n":
            return

        src_uuid, dst_uuid = InstanceManage._resolve_association_endpoint_uuids(data)

        # 1:n关联校验
        if asso_info["mapping"] == "1:n":
            with GraphClient() as ag:
                dst_edge = ag.query_edge(
                    INSTANCE_ASSOCIATION,
                    [
                        {"field": "dst_inst_uuid", "type": "str=", "value": dst_uuid},
                        {"field": "model_asst_id", "type": "str=", "value": data["model_asst_id"]},
                    ],
                )
                if dst_edge:
                    raise BaseAppException("destination instance already exists association!")
        elif asso_info["mapping"] == "n:1":
            with GraphClient() as ag:
                src_edge = ag.query_edge(
                    INSTANCE_ASSOCIATION,
                    [
                        {"field": "src_inst_uuid", "type": "str=", "value": src_uuid},
                        {"field": "model_asst_id", "type": "str=", "value": data["model_asst_id"]},
                    ],
                )
                if src_edge:
                    raise BaseAppException("source instance already exists association!")
        elif asso_info["mapping"] == "1:1":
            with GraphClient() as ag:
                src_edge = ag.query_edge(
                    INSTANCE_ASSOCIATION,
                    [
                        {"field": "src_inst_uuid", "type": "str=", "value": src_uuid},
                        {"field": "model_asst_id", "type": "str=", "value": data["model_asst_id"]},
                    ],
                )
                if src_edge:
                    raise BaseAppException("source instance already exists association!")
                dst_edge = ag.query_edge(
                    INSTANCE_ASSOCIATION,
                    [
                        {"field": "dst_inst_uuid", "type": "str=", "value": dst_uuid},
                        {"field": "model_asst_id", "type": "str=", "value": data["model_asst_id"]},
                    ],
                )
                if dst_edge:
                    raise BaseAppException("destination instance already exists association!")
        else:
            raise BaseAppException("association mapping error! mapping={}".format(asso_info["mapping"]))

    @staticmethod
    def instance_association_create(data: dict, operator: str, scenario: str = RELATION_CHANGE):
        """创建实例关联（内部仍可按图节点 ID 入参）；边端点落盘 UUID 属性。"""

        # 校验关联约束
        InstanceManage.check_asso_mapping(data)
        src = InstanceManage.query_entity_by_id(data["src_inst_id"])
        dst = InstanceManage.query_entity_by_id(data["dst_inst_id"])
        if not src or not dst:
            raise BaseAppException("实例不存在！")
        edge_properties = prepare_edge_endpoint_properties(
            dict(data),
            src_inst_uuid=src.get("inst_uuid"),
            dst_inst_uuid=dst.get("inst_uuid"),
        )
        if "src_model_id" not in edge_properties and src.get("model_id"):
            edge_properties["src_model_id"] = src["model_id"]
        if "dst_model_id" not in edge_properties and dst.get("model_id"):
            edge_properties["dst_model_id"] = dst["model_id"]

        with GraphClient() as ag:
            try:
                edge = ag.create_edge(
                    INSTANCE_ASSOCIATION,
                    data["src_inst_id"],
                    INSTANCE,
                    data["dst_inst_id"],
                    INSTANCE,
                    edge_properties,
                    "model_asst_id",
                )
            except BaseAppException as e:
                if e.message == "edge already exists":
                    raise BaseAppException("instance association repetition")
                # 其它图层异常必须原样抛出，否则下方 edge 未赋值会 UnboundLocalError 掩盖真实错误
                raise

        asso_info = InstanceManage.instance_association_by_asso_id(edge["_id"])
        # 端点实体可能未完全解析（如接口↔接口的并行边场景，query_edge_by_id 偶发回空端点），
        # 这里全部用 .get 兜底，避免拼接变更记录文案时 KeyError 让整个关联创建 500
        src_info = asso_info.get("src") or {}
        dst_info = asso_info.get("dst") or {}
        message = (
            f"创建模型关联关系. 原模型: {src_info.get('model_id', '')} "
            f"原模型实例: {src_info.get('inst_name') or src_info.get('ip_addr', '')} "
            f"目标模型ID: {dst_info.get('model_id', '')} 目标模型实例: "
            f"{dst_info.get('inst_name') or dst_info.get('ip_addr', '')}"
        )
        # 关联关系需先创建图边才能取到 edge._id / asso_info，无法在图写之前先写 PG。
        # 用 try/except 兜底：变更记录写入失败时记录错误日志但不影响关联创建结果，
        # 避免异常向上传播让调用方误判关联创建失败而重试（可能触发"edge already exists"重复异常）。
        # 若需更强一致性保障，可改为 Celery 异步投递（至少一次）——见 #3665。
        try:
            create_change_record_by_asso(
                INSTANCE_ASSOCIATION,
                CREATE_INST_ASST,
                asso_info,
                message=message,
                operator=operator,
                scenario=scenario,
            )
        except Exception as e:  # noqa: 变更记录写入失败不影响关联创建，但必须记录以便排查审计缺失
            logger.error(
                "[instance_association_create] 变更记录写入失败，关联已创建但审计日志可能缺失: " "edge_id=%s, operator=%s, error=%s",
                edge.get("_id"),
                operator,
                e,
            )

        return edge

    @staticmethod
    def _association_edges_by_business_key(*, src_inst_uuid: str, dst_inst_uuid: str, model_asst_id: str) -> list[dict]:
        src_inst_uuid = normalize_inst_uuid(src_inst_uuid)
        dst_inst_uuid = normalize_inst_uuid(dst_inst_uuid)
        with GraphClient() as ag:
            edges = ag.query_edge(
                INSTANCE_ASSOCIATION,
                [
                    {"field": "model_asst_id", "type": "str=", "value": model_asst_id},
                    {"field": "src_inst_uuid", "type": "str=", "value": src_inst_uuid},
                    {"field": "dst_inst_uuid", "type": "str=", "value": dst_inst_uuid},
                ],
                return_entity=True,
            )
        if edges:
            return edges
        with GraphClient() as ag:
            items = ag.query_edge(
                INSTANCE_ASSOCIATION,
                [{"field": "model_asst_id", "type": "str=", "value": model_asst_id}],
                return_entity=True,
            )
        return [
            item
            for item in items
            if (item.get("src") or {}).get("inst_uuid") == src_inst_uuid and (item.get("dst") or {}).get("inst_uuid") == dst_inst_uuid
        ]

    @staticmethod
    def instance_association_create_by_uuid(
        *,
        src_inst_uuid: str,
        dst_inst_uuid: str,
        model_asst_id: str,
        operator: str,
        scenario: str = RELATION_CHANGE,
        edge_properties: dict | None = None,
    ) -> dict:
        src = InstanceManage.query_entity_by_uuid(src_inst_uuid)
        dst = InstanceManage.query_entity_by_uuid(dst_inst_uuid)
        if not src or not dst:
            raise BaseAppException("实例不存在！")
        if InstanceManage._association_edges_by_business_key(
            src_inst_uuid=src["inst_uuid"],
            dst_inst_uuid=dst["inst_uuid"],
            model_asst_id=model_asst_id,
        ):
            raise BaseAppException("instance association repetition")

        asso_info = ModelManage.model_association_info_search(model_asst_id)
        if not asso_info:
            raise BaseAppException("association not found!")
        InstanceManage.check_asso_mapping(
            {
                "model_asst_id": model_asst_id,
                "src_inst_uuid": src["inst_uuid"],
                "dst_inst_uuid": dst["inst_uuid"],
                "src_inst_id": src["_id"],
                "dst_inst_id": dst["_id"],
            }
        )

        semantic_properties = dict(edge_properties or {})
        for forbidden_field in ("src_inst_id", "dst_inst_id", "_id"):
            semantic_properties.pop(forbidden_field, None)
        semantic_properties.update(
            {
                "model_asst_id": model_asst_id,
                "asst_id": asso_info.get("asst_id"),
                "src_model_id": src.get("model_id"),
                "dst_model_id": dst.get("model_id"),
            }
        )
        semantic_properties = prepare_edge_endpoint_properties(
            semantic_properties,
            src_inst_uuid=src["inst_uuid"],
            dst_inst_uuid=dst["inst_uuid"],
        )
        with GraphClient() as ag:
            edge = ag.create_edge(
                INSTANCE_ASSOCIATION,
                src["_id"],
                INSTANCE,
                dst["_id"],
                INSTANCE,
                semantic_properties,
                "model_asst_id",
            )

        asso = InstanceManage.instance_association_by_asso_id(edge["_id"])
        try:
            create_change_record_by_asso(
                INSTANCE_ASSOCIATION,
                CREATE_INST_ASST,
                asso,
                message="创建模型关联关系",
                operator=operator,
                scenario=scenario,
            )
        except Exception as exc:  # noqa: 审计失败不回滚已成功的图边
            logger.error(
                "[instance_association_create_by_uuid] audit failed edge_id=%s error_type=%s",
                edge.get("_id"),
                type(exc).__name__,
            )
        return {
            "model_asst_id": model_asst_id,
            "src_inst_uuid": src["inst_uuid"],
            "dst_inst_uuid": dst["inst_uuid"],
        }

    @staticmethod
    def instance_association_exists(*, src_inst_id: int, dst_inst_id: int, model_asst_id: str) -> bool:
        src = InstanceManage.query_entity_by_id(src_inst_id)
        dst = InstanceManage.query_entity_by_id(dst_inst_id)
        if not src.get("inst_uuid") or not dst.get("inst_uuid"):
            return False
        return bool(
            InstanceManage._association_edges_by_business_key(
                src_inst_uuid=src["inst_uuid"],
                dst_inst_uuid=dst["inst_uuid"],
                model_asst_id=model_asst_id,
            )
        )

    @staticmethod
    def instance_association_delete(asso_id: int, operator: str):
        """删除实例关联（内部图边 ID）。"""
        InstanceManage._instance_association_delete_by_graph_id(asso_id, operator)

    @staticmethod
    def instance_association_delete_by_key(*, src_inst_uuid: str, dst_inst_uuid: str, model_asst_id: str, operator: str) -> dict:
        edges = InstanceManage._association_edges_by_business_key(
            src_inst_uuid=src_inst_uuid,
            dst_inst_uuid=dst_inst_uuid,
            model_asst_id=model_asst_id,
        )
        if len(edges) != 1:
            if len(edges) > 1:
                raise BaseAppException("实例关联业务键不唯一")
            raise BaseAppException("实例关联不存在")
        InstanceManage._instance_association_delete_by_graph_id(edges[0]["edge"]["_id"], operator)
        return {
            "model_asst_id": model_asst_id,
            "src_inst_uuid": normalize_inst_uuid(src_inst_uuid),
            "dst_inst_uuid": normalize_inst_uuid(dst_inst_uuid),
        }

    @staticmethod
    def _instance_association_delete_by_graph_id(asso_id: int, operator: str):
        """图适配器内部按边 ID 删除实例关联。"""

        asso_info = InstanceManage.instance_association_by_asso_id(asso_id)

        with GraphClient() as ag:
            ag.delete_edge(asso_id)

        # 同 create：端点实体可能未完全解析，全部 .get 兜底避免 KeyError
        src_info = asso_info.get("src") or {}
        dst_info = asso_info.get("dst") or {}
        message = (
            f"删除模型关联关系. 原模型: {src_info.get('model_id', '')} 原模型实例: "
            f"{src_info.get('inst_name') or src_info.get('ip_addr', '')} "
            f"目标模型ID: {dst_info.get('model_id', '')} 目标模型实例: "
            f"{dst_info.get('inst_name') or dst_info.get('ip_addr', '')}"
        )
        create_change_record_by_asso(
            INSTANCE_ASSOCIATION,
            DELETE_INST_ASST,
            asso_info,
            message=message,
            operator=operator,
        )

    @staticmethod
    def instance_association_by_asso_id(asso_id: int):
        """根据关联ID查询实例关联"""
        with GraphClient() as ag:
            edge = ag.query_edge_by_id(asso_id, return_entity=True)
        return edge

    @staticmethod
    def query_entity_by_uuid(inst_uuid: str):
        """根据不可变业务 UUID 查询实例详情。"""
        normalized_uuid = normalize_inst_uuid(inst_uuid)
        with GraphClient() as ag:
            query_by_uuid = getattr(ag, "query_entity_by_inst_uuid", None)
            if callable(query_by_uuid):
                return query_by_uuid(normalized_uuid) or {}
            entities, _ = ag.query_entity(
                INSTANCE,
                [{"field": "inst_uuid", "type": "str=", "value": normalized_uuid}],
            )
        if len(entities) > 1:
            raise BaseAppException("inst_uuid 查询结果不唯一")
        return entities[0] if entities else {}

    @staticmethod
    def query_entity_by_uuids(inst_uuids: list[str]):
        """根据不可变业务 UUID 批量查询实例；保持输入顺序并拒绝重复。"""
        normalized = [normalize_inst_uuid(value) for value in inst_uuids]
        if len(set(normalized)) != len(normalized):
            raise BaseAppException("inst_uuid 不允许重复")
        if not normalized:
            return []
        with GraphClient() as ag:
            query_by_uuids = getattr(ag, "query_entity_by_inst_uuids", None)
            if callable(query_by_uuids):
                return query_by_uuids(normalized)
            entities, _ = ag.query_entity(
                INSTANCE,
                [{"field": "inst_uuid", "type": "str[]", "value": normalized}],
            )
        by_uuid = {}
        for item in entities:
            key = item.get("inst_uuid")
            if key in by_uuid:
                raise BaseAppException("inst_uuid 查询结果不唯一")
            by_uuid[key] = item
        return [by_uuid[value] for value in normalized if value in by_uuid]

    @staticmethod
    @staticmethod
    def query_entity_by_id(inst_id: int):
        """根据实例ID查询实例详情"""
        with GraphClient() as ag:
            entity = ag.query_entity_by_id(inst_id)
        return entity

    @staticmethod
    def query_entity_by_ids(inst_ids: list):
        """根据实例ID查询实例详情"""
        with GraphClient() as ag:
            entity_list = ag.query_entity_by_ids(inst_ids)
        return entity_list

    @staticmethod
    def query_entity_by_identity(model_id: str, identity: dict) -> dict:
        if not identity:
            return {}

        params = [{"field": "model_id", "type": "str=", "value": model_id}]
        for field, value in (identity or {}).items():
            if isinstance(value, bool):
                value = str(value).lower()
                field_type = "str="
            elif isinstance(value, int):
                field_type = "int="
            else:
                field_type = "str="
            params.append({"field": field, "type": field_type, "value": value})

        with GraphClient() as ag:
            inst_list, _ = ag.query_entity(INSTANCE, params)
        if len(inst_list) > 1:
            raise BaseAppException("identity 查询结果不唯一")
        return inst_list[0] if inst_list else {}

    # @staticmethod
    # def merge_custom_reporting_instances(
    #         *,
    #         model_id: str,
    #         instances: list[dict],
    #         relations: list[dict],
    #         identity_keys: list[str],
    #         operator: str,
    #         allowed_org_ids: list | None = None,
    # ) -> dict:
    #
    #     return CustomReportingMergeService.merge_instances(
    #         model_id=model_id,
    #         instances=instances,
    #         relations=relations,
    #         identity_keys=identity_keys,
    #         operator=operator,
    #         allowed_org_ids=allowed_org_ids,
    #     )

    @staticmethod
    def download_import_template(model_id: str):
        """下载导入模板"""
        attrs = ModelManage.search_model_attr_v2(model_id)
        association = ModelManage.model_association_search(
            model_id,
            business_only=True,
        )
        return Export(attrs, model_id=model_id, association=association).export_template()

    @staticmethod
    def inst_import(model_id: str, file_stream: bytes, operator: str):
        """实例导入"""
        attrs = ModelManage.search_model_attr_v2(model_id)
        model_info = ModelManage.search_model_info(model_id)

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
        results = Import(model_id, attrs, exist_items, operator).import_inst_list(file_stream)

        change_records = [
            dict(
                inst_id=i["data"]["_id"],
                model_id=i["data"]["model_id"],
                after_data=i["data"],
                model_object=OPERATOR_INSTANCE,
                message=f"导入模型实例. 模型:{model_info['model_name']} 实例:{i['data'].get('inst_name') or i['data'].get('ip_addr', '')}",
            )
            for i in results
            if i["success"]
        ]
        batch_create_change_record(INSTANCE, CREATE_INST, change_records, operator=operator)

        from apps.cmdb.services.auto_relation_reconcile import schedule_instance_auto_relation_reconcile

        schedule_instance_auto_relation_reconcile([item["data"]["_id"] for item in results if item.get("success")])

        return results

    def inst_import_support_edit(
        self,
        model_id: str,
        file_stream: bytes,
        operator: str,
        allowed_org_ids: list = None,
    ):
        """实例导入-支持编辑"""
        attrs = ModelManage.search_model_attr_v2(model_id)
        model_info = ModelManage.search_model_info(model_id)

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])

        _import = Import(model_id, attrs, exist_items, operator)
        add_results, update_results, asso_result = _import.import_inst_list_support_edit(
            file_stream,
            allowed_org_ids=allowed_org_ids,
        )
        # 检查是否存在验证错误
        if _import.validation_errors:
            error_summary = f"数据导入失败：发现 {len(_import.validation_errors)} 个数据验证错误\n"
            error_details = "\n".join(_import.validation_errors)
            logger.warning("[InstanceImport] 数据导入验证失败 model_id=%s, error_count=%s", model_id, len(_import.validation_errors))
            success_count = len([i for i in add_results if i.get("success", False)])
            error_summary += f"已成功导入 {success_count} 条数据，失败 {len(_import.inst_list) - success_count} 条数据。\n 错误信息: {error_summary + error_details}"
            return {"success": False, "message": error_summary}

        add_changes = [
            dict(
                inst_id=i["data"]["_id"],
                model_id=i["data"]["model_id"],
                after_data=i["data"],
                model_object=OPERATOR_INSTANCE,
                message=f"导入模型实例. 模型:{model_info['model_name']} 新增模型实例:{i['data'].get('inst_name') or i['data'].get('ip_addr', '')}",
            )
            for i in add_results
            if i["success"]
        ]
        exist_items__id_map = {i["_id"]: i for i in exist_items}
        update_changes = [
            dict(
                inst_id=i["data"]["_id"],
                model_id=i["data"]["model_id"],
                before_data=exist_items__id_map[i["data"]["_id"]],
                after_data=i["data"],
                model_object=OPERATOR_INSTANCE,
                message=f"导入模型实例. 模型:{model_info['model_name']} 更新模型实例:{i['data'].get('inst_name') or i['data'].get('ip_addr', '')}",
            )
            for i in update_results
            if i["success"]
        ]
        batch_create_change_record(INSTANCE, CREATE_INST, add_changes, operator=operator)
        batch_create_change_record(INSTANCE, UPDATE_INST, update_changes, operator=operator)

        from apps.cmdb.services.auto_relation_reconcile import schedule_instance_auto_relation_reconcile

        schedule_instance_auto_relation_reconcile(
            [item["data"]["_id"] for item in add_results if item.get("success")]
            + [item["data"]["_id"] for item in update_results if item.get("success")]
        )

        res_status, result_message = self.format_result_message(_import.import_result_message)
        logger.info("[InstanceImport] 数据导入成功 model_id=%s", model_id)

        return {"success": res_status, "message": result_message}

    @staticmethod
    def format_result_message(result: dict):
        key_map = {"add": "新增", "update": "更新", "asso": "关联"}
        add_mgs = ""
        res_status = True
        for _key in ["add", "update", "asso"]:
            success_count = result[_key]["success"]
            fail_count = result[_key]["error"]
            data = result[_key]["data"]
            message = " ,".join(data)
            add_mgs += f"{key_map[_key]}: 成功{success_count}个，失败{fail_count}个:{message}\n"
            if fail_count > 0:
                res_status = False

        if res_status:
            add_mgs = ""
        return res_status, add_mgs

    @classmethod
    def topo_search_lite(cls, inst_id: int, depth: int = 3, permission_map: dict | None = None, user=None):
        """拓扑查询（轻量）：限制返回层级，避免一次返回全量树"""
        with GraphClient() as ag:
            result = ag.query_topo_lite(INSTANCE, inst_id, depth=depth)
        return cls._filter_topology_result(result, int(inst_id), permission_map=permission_map, user=user)

    @classmethod
    def topo_search_lite_by_uuid(cls, inst_uuid: str, depth: int = 3, permission_map: dict | None = None, user=None):
        instance = cls.query_entity_by_uuid(inst_uuid)
        if not instance:
            raise BaseAppException("实例不存在！")
        result = cls.topo_search_lite(instance["_id"], depth=depth, permission_map=permission_map, user=user)
        return cls._transport_topology_result(result)

    @classmethod
    def topo_search_expand(
        cls,
        inst_id: int,
        parent_ids: list,
        depth: int = 2,
        permission_map: dict | None = None,
        user=None,
    ):
        """拓扑展开：从指定节点向后展开一层，并过滤父节点列表"""
        with GraphClient() as ag:
            result = ag.query_topo_lite(INSTANCE, inst_id, depth=depth, exclude_ids=parent_ids)
        return cls._filter_topology_result(result, int(inst_id), permission_map=permission_map, user=user)

    @classmethod
    def topo_search_expand_by_uuid(
        cls,
        inst_uuid: str,
        parent_uuids: list[str],
        depth: int = 2,
        permission_map: dict | None = None,
        user=None,
    ):
        instance = cls.query_entity_by_uuid(inst_uuid)
        if not instance:
            raise BaseAppException("实例不存在！")
        parents = cls.query_entity_by_uuids(parent_uuids) if parent_uuids else []
        if len(parents) != len(parent_uuids or []):
            raise BaseAppException("父实例不存在！")
        result = cls.topo_search_expand(
            instance["_id"],
            [item["_id"] for item in parents],
            depth=depth,
            permission_map=permission_map,
            user=user,
        )
        return cls._transport_topology_result(result)

    @staticmethod
    def inst_export(
        model_id: str,
        ids: list,
        permissions_map: dict = {},
        created: str = "",
        creator: str = "",
        attr_list: list = [],
        association_list: list = [],
    ):
        """实例导出"""
        attrs = ModelManage.search_model_attr_v2(model_id)
        association = ModelManage.model_association_search(
            model_id,
            business_only=True,
        )
        format_permission_dict = InstanceManage._build_format_permission_dict(permissions_map, creator)
        # 添加调试日志
        logger.info(f"导出参数 - model_id: {model_id}, ids: {ids}, association_list: {association_list}")
        logger.info(f"查询到的所有关联关系: {len(association)} 个")
        if ids:
            query_list = [
                {"field": "id", "type": "id[]", "value": ids},
                {"field": "model_id", "type": "str=", "value": model_id},
            ]
        else:
            query_list = [{"field": "model_id", "type": "str=", "value": model_id}]

        with GraphClient() as ag:
            # 使用新的基础权限过滤方法获取有权限的实例
            query = dict(
                label=INSTANCE,
                params=query_list,
                format_permission_dict=format_permission_dict,
            )
            inst_list, _ = ag.query_entity(**query)
        if attr_list:
            attr_map = {attr["attr_id"]: attr for attr in attrs}
            attrs = [attr_map[attr_id] for attr_id in attr_list if attr_id in attr_map]
        else:
            attrs = attrs
        # 只有当用户明确选择了关联关系时才包含关联关系
        association = [i for i in association if i["model_asst_id"] in association_list] if association_list else []

        logger.info(f"过滤后的关联关系: {len(association)} 个")

        return Export(attrs, model_id=model_id, association=association).export_inst_list(inst_list)

    @staticmethod
    def topo_search(inst_id: int):
        """拓扑查询"""
        with GraphClient() as ag:
            result = ag.query_topo(INSTANCE, inst_id)
        return result

    @staticmethod
    def network_topology(
        inst_id: int,
        model_id: str,
        depth: int = 1,
        permission_map: dict = None,
        user=None,
        node_limit: int = NETWORK_TOPO_NODE_LIMIT,
    ) -> dict:
        """网络设备拓扑：以该设备为中心，按 depth 跳广度优先展开接口直连的对端设备。

        - 复用单跳图查询 query_network_topo，逐层 BFS，每个节点带 hop（距中心跳数）与
          expanded（其邻居是否已在本次结果中完整加载，供前端判断哪些节点可继续点开）。
        - 节点数达 node_limit 时停止新增并置 truncated=True（截断并提示，不静默丢弃）。
        - 按 permission_map 剔除无权限对端；按 relationship_id 去重。
        返回 {center, nodes, links, truncated}。
        """
        depth = max(1, int(depth))
        center_id = str(inst_id)
        # 中心节点先占位，名称/模型在查询其行后用权威值回填；无任何连线时兜底查实例
        nodes = {
            center_id: {
                "id": center_id,
                "name": None,
                "model_id": model_id,
                "hop": 0,
                "expanded": False,
            }
        }
        links = {}
        truncated = False

        frontier = [(center_id, model_id)]
        # 单跳查询逐层 BFS：整轮复用一个图连接，避免每个设备各开/关一次连接
        with GraphClient() as ag:
            for hop in range(depth):
                # 先查完本跳所有设备，收集行；再统一判权限/上限，决定哪些对端可加入与下探
                hop_rows = []
                for dev_id, dev_model in frontier:
                    rows = ag.query_network_topo(int(dev_id), f"interface_belong_{dev_model}") or []
                    nodes[dev_id]["expanded"] = True
                    # 当前设备名称/模型用查询行的权威值回填一次即可
                    if rows:
                        nodes[dev_id]["name"] = rows[0]["dev_name"]
                        nodes[dev_id]["model_id"] = rows[0]["dev_model"]
                    hop_rows.extend(rows)

                # 本跳新发现的对端：无权限的直接剪枝（不加节点、不加边、不再下探），
                # 因此「仅经无权限设备可达」的更深设备不会变成孤点
                new_peer_ids = {str(r["peer_id"]) for r in hop_rows if str(r["peer_id"]) not in nodes}
                denied = set()
                if permission_map and new_peer_ids:
                    instances_map = InstanceManage._query_instance_map_by_ids({int(i) for i in new_peer_ids})
                    for pid in new_peer_ids:
                        if not InstanceManage._has_topology_view_permission(instances_map.get(int(pid)), permission_map, user=user):
                            denied.add(pid)

                next_frontier = []
                for row in hop_rows:
                    peer_id = str(row["peer_id"])
                    if peer_id in denied:
                        continue
                    if peer_id not in nodes:
                        if len(nodes) >= node_limit:
                            truncated = True
                            continue
                        nodes[peer_id] = {
                            "id": peer_id,
                            "name": row["peer_name"],
                            "model_id": row["peer_model"],
                            "hop": hop + 1,
                            "expanded": False,
                        }
                        next_frontier.append((peer_id, row["peer_model"]))
                    rel_id = str(row["rel_id"])
                    if rel_id not in links:
                        links[rel_id] = {
                            "relationship_id": rel_id,
                            "source_device": str(row["dev_id"]),
                            "source_inst_name": row["local_if"],
                            "target_device": peer_id,
                            "target_inst_name": row["peer_if"],
                            "asst_id": "connect",
                            "model_asst_id": "interface_connect_interface",
                            "src_inst_uuid": str(row.get("local_if_uuid") or "") or None,
                            "dst_inst_uuid": str(row.get("peer_if_uuid") or "") or None,
                        }
                frontier = next_frontier
                if not frontier:
                    break

        # 中心无任何连线：兜底查实例补全名称
        if nodes[center_id]["name"] is None:
            instance = InstanceManage.query_entity_by_id(int(inst_id)) or {}
            nodes[center_id]["name"] = instance.get("inst_name", center_id)
            nodes[center_id]["model_id"] = instance.get("model_id", model_id)
            nodes[center_id]["expanded"] = True

        # 权限已在 BFS 逐跳剪枝（无权限对端不加入）；此处仅清理因节点上限截断而悬空的连线
        links = {rid: l for rid, l in links.items() if l["source_device"] in nodes and l["target_device"] in nodes}

        return {
            "center": nodes[center_id],
            "nodes": list(nodes.values()),
            "links": list(links.values()),
            "truncated": truncated,
        }

    @staticmethod
    def _remap_network_topology_device_ids_to_uuids(result: dict) -> dict:
        """对外网络拓扑把设备节点/连线端点从图 _id 映射为 inst_uuid。"""
        nodes = list(result.get("nodes") or [])
        graph_ids = set()
        for node in nodes:
            try:
                graph_ids.add(int(node.get("id")))
            except (TypeError, ValueError):
                continue
        instances_map = InstanceManage._query_instance_map_by_ids(graph_ids) if graph_ids else {}
        id_to_uuid = {
            str(graph_id): str(inst.get("inst_uuid")) for graph_id, inst in instances_map.items() if isinstance(inst, dict) and inst.get("inst_uuid")
        }

        remapped_nodes = []
        for node in nodes:
            node_id = str(node.get("id"))
            remapped = dict(node)
            remapped["id"] = id_to_uuid.get(node_id, node_id)
            remapped_nodes.append(remapped)

        remapped_links = []
        for link in result.get("links") or []:
            remapped = dict(link)
            src = str(link.get("source_device"))
            dst = str(link.get("target_device"))
            remapped["source_device"] = id_to_uuid.get(src, src)
            remapped["target_device"] = id_to_uuid.get(dst, dst)
            remapped_links.append(remapped)

        center = result.get("center") or {}
        center_id = str(center.get("id"))
        remapped_center = dict(center)
        remapped_center["id"] = id_to_uuid.get(center_id, center_id)

        return {
            **result,
            "center": remapped_center,
            "nodes": remapped_nodes,
            "links": remapped_links,
        }

    @staticmethod
    def network_topology_by_uuid(
        inst_uuid: str,
        model_id: str,
        depth: int = 1,
        permission_map: dict = None,
        user=None,
        node_limit: int = NETWORK_TOPO_NODE_LIMIT,
    ) -> dict:
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance or instance.get("model_id") != model_id:
            raise BaseAppException("实例不存在！")
        result = InstanceManage.network_topology(
            instance["_id"],
            model_id,
            depth=depth,
            permission_map=permission_map,
            user=user,
            node_limit=node_limit,
        )
        return InstanceManage._remap_network_topology_device_ids_to_uuids(result)

    @staticmethod
    def network_topology_among_uuids(
        inst_uuids: list[str],
        permission_maps: dict | None = None,
        user=None,
    ) -> dict:
        """按勾选设备做接口直连诱导子图：节点闭集，边只保留两端都在集合内。"""
        from apps.cmdb.services.topology_theme import is_network_device_model

        closed_set_error = "设备列表包含无效或不允许的网络设备，请重新配置"
        normalized = [normalize_inst_uuid(value) for value in inst_uuids]
        if not normalized:
            raise BaseAppException(closed_set_error)
        if len(set(normalized)) != len(normalized):
            raise BaseAppException(closed_set_error)

        entities = InstanceManage.query_entity_by_uuids(normalized)
        if len(entities) != len(normalized):
            raise BaseAppException(closed_set_error)

        network_model_ok: dict[str, bool] = {}
        for entity in entities:
            model_id = str(entity.get("model_id") or "")
            if model_id not in network_model_ok:
                network_model_ok[model_id] = is_network_device_model(model_id)
            if not network_model_ok[model_id]:
                raise BaseAppException(closed_set_error)
            permission_map = (permission_maps or {}).get(model_id) if permission_maps else None
            if permission_maps is not None and not InstanceManage._has_topology_view_permission(entity, permission_map, user=user):
                raise BaseAppException(closed_set_error)

        selected_graph_ids = {str(entity["_id"]) for entity in entities}
        id_to_uuid = {str(entity["_id"]): str(entity.get("inst_uuid")) for entity in entities}
        nodes = [
            {
                "id": str(entity.get("inst_uuid")),
                "name": entity.get("inst_name") or str(entity.get("inst_uuid")),
                "model_id": str(entity.get("model_id") or ""),
                "hop": 0,
                "expanded": True,
            }
            for entity in entities
        ]
        links = {}
        with GraphClient() as ag:
            for entity in entities:
                model_id = str(entity.get("model_id") or "")
                rows = ag.query_network_topo(int(entity["_id"]), f"interface_belong_{model_id}") or []
                for row in rows:
                    peer_id = str(row["peer_id"])
                    if peer_id not in selected_graph_ids:
                        continue
                    rel_id = str(row["rel_id"])
                    if rel_id in links:
                        continue
                    source_id = str(row["dev_id"])
                    links[rel_id] = {
                        "relationship_id": rel_id,
                        "source_device": id_to_uuid.get(source_id, source_id),
                        "source_inst_name": row["local_if"],
                        "target_device": id_to_uuid.get(peer_id, peer_id),
                        "target_inst_name": row["peer_if"],
                        "asst_id": "connect",
                        "model_asst_id": "interface_connect_interface",
                        "src_inst_uuid": str(row.get("local_if_uuid") or "") or None,
                        "dst_inst_uuid": str(row.get("peer_if_uuid") or "") or None,
                    }

        return {
            "nodes": nodes,
            "links": list(links.values()),
            "truncated": False,
        }

    @staticmethod
    def topo_search_by_uuid(inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            raise BaseAppException("实例不存在！")
        return InstanceManage.topo_search(instance["_id"])

    @staticmethod
    def topo_search_test_config_by_uuid(inst_uuid: str, model_id: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance or instance.get("model_id") != model_id:
            raise BaseAppException("实例不存在！")
        return InstanceManage.topo_search_test_config(instance["_id"], model_id)

    @staticmethod
    def topo_search_test_config(inst_id: int, model_id: str):
        """拓扑查询"""
        with GraphClient() as ag:
            result = ag.query_topo_test_config(INSTANCE, inst_id, model_id)
        return result

    @staticmethod
    def create_or_update(data: dict):
        if not data["show_fields"]:
            raise BaseAppException("展示字段不能为空！")
        ShowField.objects.update_or_create(
            defaults=data,
            model_id=data["model_id"],
            created_by=data["created_by"],
        )
        return data

    @staticmethod
    def get_info(model_id: str, created_by: str):
        obj = ShowField.objects.filter(created_by=created_by, model_id=model_id).first()
        result = dict(model_id=obj.model_id, show_fields=obj.show_fields) if obj else None
        return result

    @staticmethod
    def format_instance_permission_data(rules):
        # 构建实例权限过滤参数
        result = []
        if not rules:
            return result

        for group_id, models in rules.items():
            for model_id, permissions in models.items():
                # 检查是否有具体的实例权限限制
                has_specific_instances = False
                specific_instance_names = []

                for perm in permissions:
                    # id为'0'或'-1'表示全选，不需要过滤
                    if perm.get("id") not in ["0", "-1"]:
                        has_specific_instances = True
                        # 这里的id实际上是inst_name
                        specific_instance_names.append(perm.get("id"))

                # 如果有具体的实例权限限制，添加到过滤参数中
                if has_specific_instances and specific_instance_names:
                    result.append({"model_id": model_id, "inst_names": specific_instance_names})
        return result

    @staticmethod
    def add_inst_name_permission(inst_names):
        if not inst_names:
            return ""
        return f"n.inst_name IN {inst_names}"

    @classmethod
    def group_inst_count(cls, group_by_attr: str, permissions_map: dict, params: list = None, creator: str = ""):
        format_permission_dict = cls._build_format_permission_dict(permissions_map, creator)

        with GraphClient() as ag:
            data = ag.entity_count(
                label=INSTANCE,
                group_by_attr=group_by_attr,
                params=params or [],
                format_permission_dict=format_permission_dict,
            )
        return data

    @classmethod
    def model_inst_count(cls, permissions_map: dict, creator: str = ""):
        return cls.group_inst_count(group_by_attr="model_id", permissions_map=permissions_map, creator=creator)

    @classmethod
    def license_instance_count(cls) -> dict:
        """许可用量：原生自动发现且属于收费模型目录的实例数。"""
        from apps.cmdb.constants.license_catalog import CMDB_LICENSE_MODEL_IDS

        return cls.group_inst_count(
            group_by_attr="model_id",
            permissions_map={},
            params=[
                {"field": "auto_collect", "type": "bool", "value": True},
                {"field": "model_id", "type": "str[]", "value": list(CMDB_LICENSE_MODEL_IDS)},
            ],
            creator="",
        )

    @classmethod
    def _build_permission_params(cls, permission_map: dict, creator: str = ""):
        """
        构建权限参数（统一方法，供全文检索系列接口使用）

        Args:
            permission_map: 权限映射字典
            creator: 创建者

        Returns:
            permission_params: 权限过滤字符串
        """
        with GraphClient() as ag:
            # 使用共享的参数收集器（参数化模式）
            param_collector = ParameterCollector() if ag.ENABLE_PARAMETERIZATION else None

            # 构建权限过滤字符串：组织边界必须保留在单组织分支内，
            # 仅在该分支内部组合实例名/创建人条件；多个组织分支之间再 OR。
            permission_filters = []
            for organization_id, organization_permission_data in permission_map.items():
                organization_query = [{"field": "organization", "type": "list[]", "value": [organization_id]}]
                organization_str, _ = ag.format_search_params(
                    organization_query,
                    param_type="AND",
                    param_collector=param_collector,
                )
                if not organization_str:
                    continue

                branch_conditions = []
                inst_names = organization_permission_data.get("inst_names", [])
                if inst_names:
                    branch_conditions.append({"field": "inst_name", "type": "str[]", "value": inst_names})
                    if creator:
                        branch_conditions.append({"field": "_creator", "type": "str=", "value": creator})

                if branch_conditions:
                    branch_str, _ = ag.format_search_params(
                        branch_conditions,
                        param_type="OR",
                        param_collector=param_collector,
                    )
                    if branch_str:
                        permission_filters.append(f"({organization_str} AND {branch_str})")
                        continue

                permission_filters.append(organization_str)

            # 多个组织的权限条件用 OR 连接
            permission_params = " OR ".join(permission_filters) if permission_filters else ""

            # 返回权限参数和参数字典
            if ag.ENABLE_PARAMETERIZATION and param_collector:
                return permission_params, param_collector.get_params()
            else:
                return permission_params, {}

    @classmethod
    def fulltext_search(
        cls,
        search: str,
        permission_map: dict,
        creator: str = "",
        case_sensitive: bool = False,
    ):
        """
        全文检索（兼容旧接口）

        Args:
            search: 搜索关键词
            permission_map: 权限映射
            creator: 创建者
            case_sensitive: 是否精确匹配（True=精确匹配，False=不区分大小写模糊匹配，默认False）

        Returns:
            实例列表
        """
        logger.info(f"[InstanceManage.fulltext_search] 搜索关键词: {search}, 区分大小写: {case_sensitive}")

        # 构建权限参数
        permission_params, _ = cls._build_permission_params(permission_map, creator)

        with GraphClient() as ag:
            # 调用 full_text，保留全文搜索逻辑
            data = ag.full_text(
                search=search,
                permission_params=permission_params,
                inst_name_params="",  # 实例名称权限已包含在 permission_params 中
                created="",  # 创建人权限已包含在 permission_params 中
                case_sensitive=case_sensitive,
            )

        logger.info(f"[InstanceManage.fulltext_search] 返回 {len(data)} 条结果")
        return data

    @classmethod
    def fulltext_search_stats(
        cls,
        search: str,
        permission_map: dict,
        creator: str = "",
        case_sensitive: bool = False,
    ):
        """
        全文检索 - 模型统计接口
        返回搜索结果中每个模型的总数统计

        Args:
            search: 搜索关键词
            permission_map: 权限映射
            creator: 创建者
            case_sensitive: 是否精确匹配（True=精确匹配，False=不区分大小写模糊匹配，默认False）

        Returns:
            {
                "total": 156,
                "model_stats": [{"model_id": "Center", "count": 45}, ...]
            }
        """
        logger.info(f"[InstanceManage.fulltext_search_stats] 搜索关键词: {search}, 区分大小写: {case_sensitive}")

        # 构建权限参数（统一逻辑）
        permission_params, permission_params_dict = cls._build_permission_params(permission_map, creator)

        with GraphClient() as ag:
            # 调用新的统计接口
            result = ag.full_text_stats(
                search=search,
                permission_params=permission_params,
                inst_name_params="",  # 实例名称权限已包含在 permission_params 中
                created="",  # 创建人权限已包含在 permission_params 中
                case_sensitive=case_sensitive,
                permission_params_dict=permission_params_dict,  # 传递参数字典
            )

        logger.info(f"[InstanceManage.fulltext_search_stats] 返回统计: 总数={result.get('total', 0)}, 模型数={len(result.get('model_stats', []))}")
        return result

    @classmethod
    def fulltext_search_by_model(
        cls,
        search: str,
        model_id: str,
        permission_map: dict,
        creator: str = "",
        page: int = 1,
        page_size: int = 10,
        case_sensitive: bool = False,
    ):
        """
        全文检索 - 模型数据查询接口
        返回指定模型的分页数据

        Args:
            search: 搜索关键词
            model_id: 模型ID
            permission_map: 权限映射
            creator: 创建者
            page: 页码（从1开始）
            page_size: 每页大小
            case_sensitive: 是否精确匹配（True=精确匹配，False=不区分大小写模糊匹配，默认False）

        Returns:
            {
                "model_id": "Center",
                "total": 45,
                "page": 1,
                "page_size": 10,
                "data": [{...}, {...}]
            }
        """
        logger.info(
            f"[InstanceManage.fulltext_search_by_model] 搜索关键词: {search}, 模型: {model_id}, " f"页码: {page}, 每页: {page_size}, 区分大小写: {case_sensitive}"
        )

        # 构建权限参数（统一逻辑）
        permission_params, permission_params_dict = cls._build_permission_params(permission_map, creator)

        with GraphClient() as ag:
            # 调用新的分页查询接口
            result = ag.full_text_by_model(
                search=search,
                model_id=model_id,
                permission_params=permission_params,
                inst_name_params="",  # 实例名称权限已包含在 permission_params 中
                created="",  # 创建人权限已包含在 permission_params 中
                page=page,
                page_size=page_size,
                case_sensitive=case_sensitive,
                permission_params_dict=permission_params_dict,  # 传递参数字典
            )

        logger.info(
            f"[InstanceManage.fulltext_search_by_model] 返回结果: 模型={model_id}, 总数={result.get('total', 0)}, "
            f"当前页={result.get('page', 0)}, 数据条数={len(result.get('data', []))}"
        )
        return result

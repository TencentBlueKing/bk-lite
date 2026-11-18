from apps.cmdb.collection.field_reconcile import COLLECT_SOURCES_ATTR, stamp_manual_sources
from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
from apps.cmdb.display_field import DisplayFieldConverter
from apps.cmdb.display_field.constants import DISPLAY_SUFFIX
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.change_record import OWNER_HANDOVER, UPDATE_INST
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.base import format_groups_params
from apps.cmdb.utils.change_record import batch_create_change_record, format_instance_audit_message
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.exceptions.base_app_exception import BaseAppException

QUERY_PAGE = 200
MAX_PAGES = 200
WRITE_BATCH = 200


class GraphOwnerCatalog:
    def __init__(self, graph_factory=None, model_search=None):
        self.graph_factory = graph_factory or GraphClient
        self.model_search = model_search or (lambda: ModelManage.search_model(language="zh-Hans"))

    def list_models(self):
        result = []
        for model in self.model_search() or []:
            attrs = model.get("attrs") or []
            if isinstance(attrs, str):
                attrs = ModelManage.parse_attrs(attrs)
            fields = []
            for attr in attrs:
                if not isinstance(attr, dict) or attr.get("is_display_field"):
                    continue
                if attr.get("attr_type") != "user" or not attr.get("attr_id"):
                    continue
                fields.append({"attr_id": attr["attr_id"], "attr_name": attr.get("attr_name") or attr["attr_id"]})
            if not fields:
                continue
            result.append(
                {
                    "model_id": model["model_id"],
                    "model_name": model.get("model_name") or model["model_id"],
                    "fields": fields,
                }
            )
        return result

    def find_instances(self, model_id, user_id, field_ids):
        merged = {}
        with self.graph_factory() as graph:
            for field_id in field_ids:
                skip = 0
                for _page in range(MAX_PAGES):
                    rows, count = graph.query_entity(
                        INSTANCE,
                        [
                            {"field": "model_id", "type": "str=", "value": model_id},
                            {"field": field_id, "type": "list_any[]", "value": [int(user_id)]},
                        ],
                        page={"skip": skip, "limit": QUERY_PAGE},
                    )
                    for row in rows or []:
                        key = row.get("inst_uuid") or row.get("_id")
                        merged[key] = row
                    got = len(rows or [])
                    skip += got
                    if got < QUERY_PAGE or (count is not None and skip >= count):
                        break
                else:
                    raise BaseAppException("负责人匹配实例过多，请缩小模型范围")
        return list(merged.values())

    def get_instance(self, model_id, inst_uuid):
        with self.graph_factory() as graph:
            rows, _count = graph.query_entity(
                INSTANCE,
                [
                    {"field": "model_id", "type": "str=", "value": model_id},
                    {"field": "inst_uuid", "type": "str=", "value": inst_uuid},
                ],
                page={"skip": 0, "limit": 1},
            )
        return rows[0] if rows else None

    def get_instances(self, inst_uuids):
        unique = list(dict.fromkeys(item for item in inst_uuids if item))
        found = {}
        if not unique:
            return found
        with self.graph_factory() as graph:
            for start in range(0, len(unique), QUERY_PAGE):
                chunk = unique[start : start + QUERY_PAGE]
                rows, _count = graph.query_entity(
                    INSTANCE,
                    [{"field": "inst_uuid", "type": "str[]", "value": chunk}],
                    page={"skip": 0, "limit": len(chunk)},
                )
                for row in rows or []:
                    if row.get("inst_uuid"):
                        found[row["inst_uuid"]] = row
        return found


class InstanceHandoverWriter:
    batch_size = WRITE_BATCH

    def __init__(self, user, team_id, include_children):
        self.user = user
        self.team_id = int(team_id)
        self.include_children = bool(include_children)

    def apply(self, instance, changes, operator, source_label):
        team_ids = CmdbRulesFormatUtil.get_authorized_team_ids(self.user, self.team_id, self.include_children)
        user_groups = format_groups_params(team_ids or [self.team_id])
        InstanceManage.instance_update_by_uuid(
            user_groups,
            list(getattr(self.user, "roles", []) or []),
            instance["inst_uuid"],
            changes,
            operator,
            scenario=OWNER_HANDOVER,
            schedule_post_actions=False,
            audit_source=source_label,
            audit_action="负责人交接",
        )

    def apply_many(self, rows, operator, source_label):
        """同一字段按实例写入不同的交接结果，并批量记变更记录。"""
        if not rows:
            return
        self._ensure_graph_ids(rows)
        display_cache = {}
        updates = [self._instance_update(row, display_cache) for row in rows]
        with GraphClient() as graph:
            graph.batch_set_node_properties(
                INSTANCE,
                [{"id": int(row["instance"]["_id"]), "properties": update} for row, update in zip(rows, updates)],
            )
        records = []
        for row, update in zip(rows, updates):
            instance = row["instance"]
            records.append(
                {
                    "inst_id": instance["_id"],
                    "inst_uuid": instance.get("inst_uuid"),
                    "model_id": instance["model_id"],
                    "before_data": dict(instance),
                    "after_data": {**instance, **update},
                    "model_object": OPERATOR_INSTANCE,
                    "message": format_instance_audit_message(
                        "负责人交接",
                        row["model_name"],
                        instance.get("inst_name") or "",
                        source=source_label,
                    ),
                }
            )
        batch_create_change_record(INSTANCE, UPDATE_INST, records, operator=operator, scenario=OWNER_HANDOVER)

    @staticmethod
    def _ensure_graph_ids(rows):
        missing = [row["instance"].get("inst_uuid") for row in rows if not row["instance"].get("_id")]
        found = {}
        if any(missing):
            found = {item["inst_uuid"]: item for item in InstanceManage.query_entity_by_uuids(list(dict.fromkeys(item for item in missing if item)))}
        for row in rows:
            instance = row["instance"]
            if instance.get("_id"):
                continue
            fresh = found.get(instance.get("inst_uuid")) or {}
            if not fresh.get("_id"):
                raise BaseAppException("实例不存在！")
            row["instance"] = {**instance, "_id": fresh["_id"]}

    @staticmethod
    def _instance_update(row, display_cache):
        instance = row["instance"]
        update = dict(row["payload"])
        for attr_id, value in list(update.items()):
            cache_key = (attr_id, tuple(value))
            display = display_cache.get(cache_key)
            if display is None:
                display = DisplayFieldConverter.convert_user(list(value))
                display_cache[cache_key] = display
            update[f"{attr_id}{DISPLAY_SUFFIX}"] = display
        stamped = stamp_manual_sources(instance, update)
        if stamped is not None:
            update[COLLECT_SOURCES_ATTR] = stamped
        return update

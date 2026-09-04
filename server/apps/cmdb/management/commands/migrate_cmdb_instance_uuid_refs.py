from uuid import UUID, uuid4

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.change_record import ChangeRecord
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.config_file_version import ConfigFileVersion
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.models.user_personal_config import UserPersonalConfig
from apps.cmdb.models.uuid_migration_state import CmdbUuidMigrationState
from apps.cmdb.services.instance import InstanceManage


def _canonical_uuid(value):
    try:
        return str(UUID(str(value))) if value else None
    except (TypeError, ValueError, AttributeError):
        return None


def _graph_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _instance_uuid_from_record(record):
    return _canonical_uuid((record.after_data or {}).get("inst_uuid") or (record.before_data or {}).get("inst_uuid"))


# 无条件改写：CMDB 图节点 / 关联端点。instance_id 常与云厂商 ID 同名，默认不碰。
_ALWAYS_GRAPH_ID_SCALAR_KEYS = (
    ("_id", "inst_uuid"),
    ("src_inst_id", "src_inst_uuid"),
    ("dst_inst_id", "dst_inst_uuid"),
)
# 仅当同对象已是 CMDB 实例形态时改写 inst_id；instance_id 只在 Operation JSON 显式允许。
_CONTEXT_INST_ID_KEY = ("inst_id", "inst_uuid")
_BARE_INSTANCE_ID_KEY = ("instance_id", "instance_uuid")
_GRAPH_ID_LIST_KEYS = (
    ("subnet_ids", "subnet_uuids"),
    ("instance_ids", "instance_uuids"),
)
_JSON_REWRITE_MAX_DEPTH = 16


class Command(BaseCommand):
    help = (
        "补齐图实例 UUID，并清洗图关系与 CMDB PostgreSQL 活动引用。" "可手动 --dry-run/--apply/--verify；部署后由 Celery 运行期任务自动幂等收敛。" "不进 batch_init 硬门禁（batch_init 只注册运行期任务）。"
    )

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true", help="只生成清洗统计，不写入")
        mode.add_argument("--apply", action="store_true", help="执行幂等清洗并保存断点")
        mode.add_argument("--verify", action="store_true", help="只读验证；存在待清洗项时非零退出")

    def _graph_uuid_map(self, inst_ids):
        if not inst_ids:
            return {}
        cached = {inst_id: self._graph_uuid_by_id[inst_id] for inst_id in set(inst_ids) if inst_id in self._graph_uuid_by_id}
        missing_ids = set(inst_ids) - set(cached)
        if not missing_ids:
            return cached
        entities = InstanceManage.query_entity_by_ids(sorted(missing_ids))
        result = dict(cached)
        for entity in entities:
            inst_uuid = _canonical_uuid(entity.get("inst_uuid"))
            if entity.get("_id") is not None and inst_uuid:
                result[int(entity["_id"])] = inst_uuid
        return result

    def _stage_cursor(self, stage):
        if getattr(self, "_dry_run", False):
            return 0, False
        state, _ = CmdbUuidMigrationState.objects.get_or_create(stage=stage)
        return int(state.cursor or 0), state.completed

    def _save_stage(self, stage, cursor, *, completed=False):
        if getattr(self, "_dry_run", False):
            return
        CmdbUuidMigrationState.objects.update_or_create(
            stage=stage,
            defaults={"cursor": str(cursor or 0), "completed": completed},
        )

    def _model_table_exists(self, model):
        if not hasattr(self, "_existing_tables"):
            self._existing_tables = set(connection.introspection.table_names())
        return model._meta.db_table in self._existing_tables

    def _load_graph_uuid_map(self, batch_size):
        cursor = 0
        seen = set()
        with GraphClient() as graph:
            while True:
                entities, _ = graph.query_entity(
                    INSTANCE,
                    ([{"field": "id", "type": "id>", "value": cursor}] if cursor else []),
                    page={"skip": 0, "limit": batch_size},
                    include_count=False,
                )
                if not entities:
                    break
                for entity in entities:
                    inst_uuid = _canonical_uuid(entity.get("inst_uuid"))
                    if not inst_uuid:
                        continue
                    if inst_uuid in seen:
                        raise CommandError(f"图实例 inst_uuid 重复: {inst_uuid}")
                    seen.add(inst_uuid)
                    self._graph_uuid_by_id[int(entity["_id"])] = inst_uuid
                cursor = int(entities[-1]["_id"])

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        verify = bool(options["verify"])
        dry_run = bool(options["dry_run"] or verify)
        self._dry_run = dry_run
        if batch_size <= 0:
            raise CommandError("batch-size 必须大于 0")

        stats = {
            "graph_instance_scanned": 0,
            "graph_uuid_added": 0,
            "graph_relation_scanned": 0,
            "graph_relation_uuid_set": 0,
            "graph_relation_digit_removed": 0,
            "graph_index_ensured": 0,
            "config_updated": 0,
            "config_orphan_skipped": 0,
            "change_record_updated": 0,
            "change_record_historical_unmapped": 0,
            "subscription_updated": 0,
            "subscription_snapshot_updated": 0,
            "followed_asset_config_updated": 0,
            "followed_asset_unmapped": 0,
            "custom_reporting_pending_updated": 0,
            "custom_reporting_cleanup_updated": 0,
            "custom_reporting_unmapped": 0,
            "collect_task_updated": 0,
            "collect_instance_updated": 0,
            "collect_reference_unmapped": 0,
            "collect_result_snapshot_updated": 0,
            "node_mgmt_sync_detail_updated": 0,
            "operation_target_updated": 0,
            "operation_snapshot_updated": 0,
            "operation_outbox_updated": 0,
            "monitor_cmdb_id_updated": 0,
            "monitor_cmdb_id_unmapped": 0,
            "node_cmdb_id_updated": 0,
            "node_cmdb_id_unmapped": 0,
        }
        self._graph_uuid_by_id = {}
        graph_cursor, graph_completed = self._stage_cursor("graph_instances")
        if graph_cursor or graph_completed:
            self._load_graph_uuid_map(batch_size)
        self._clean_graph(batch_size, dry_run, stats)
        self._clean_config_versions(batch_size, dry_run, stats)
        self._clean_change_records(batch_size, dry_run, stats)
        self._clean_subscriptions(batch_size, dry_run, stats)
        self._clean_subscription_snapshots(batch_size, dry_run, stats)
        self._clean_followed_assets(batch_size, dry_run, stats)
        self._clean_enterprise_custom_reporting(batch_size, dry_run, stats)
        self._clean_collect_tasks(batch_size, dry_run, stats)
        self._clean_collect_instances(batch_size, dry_run, stats)
        self._clean_collect_result_snapshots(batch_size, dry_run, stats)
        self._clean_node_mgmt_sync_details(batch_size, dry_run, stats)
        self._clean_operation_targets(batch_size, dry_run, stats)
        self._clean_operation_snapshots(batch_size, dry_run, stats)
        self._clean_operation_outbox(batch_size, dry_run, stats)
        self._clean_monitor_cmdb_ids(batch_size, dry_run, stats)
        self._clean_node_cmdb_ids(batch_size, dry_run, stats)
        if verify:
            blocker_keys = (
                "graph_uuid_added",
                "graph_relation_uuid_set",
                "graph_relation_digit_removed",
                "config_updated",
                "change_record_updated",
                "subscription_updated",
                "subscription_snapshot_updated",
                "followed_asset_config_updated",
                "followed_asset_unmapped",
                "custom_reporting_pending_updated",
                "custom_reporting_cleanup_updated",
                "custom_reporting_unmapped",
                "collect_task_updated",
                "collect_instance_updated",
                "collect_reference_unmapped",
                "collect_result_snapshot_updated",
                "node_mgmt_sync_detail_updated",
                "operation_target_updated",
                "operation_snapshot_updated",
                "operation_outbox_updated",
                "monitor_cmdb_id_updated",
                "node_cmdb_id_updated",
            )
            blockers = {key: stats[key] for key in blocker_keys if stats[key]}
            if blockers:
                leftover_ids = getattr(self, "_leftover_snapshot_ids", [])
                extra = f" leftover_ids={leftover_ids}" if leftover_ids else ""
                raise CommandError(f"CMDB UUID 迁移验证失败，仍存在待清洗项: {blockers}{extra}")
        self.stdout.write(self.style.SUCCESS(str(stats)))

    def _clean_graph(self, batch_size, dry_run, stats):
        """先建立完整、唯一的 UUID 身份，再写边端点 UUID 并移除数字端点属性。"""
        self._dry_run = dry_run
        uuid_owners = {inst_uuid: graph_id for graph_id, inst_uuid in self._graph_uuid_by_id.items()}
        cursor, completed = self._stage_cursor("graph_instances")
        cursor = None if completed and not cursor else (cursor or None)
        with GraphClient() as graph:
            while True:
                params = []
                if cursor is not None:
                    params.append({"field": "id", "type": "id>", "value": cursor})
                entities, _ = graph.query_entity(
                    INSTANCE,
                    params,
                    page={"skip": 0, "limit": batch_size},
                    include_count=False,
                )
                if not entities:
                    break
                next_cursor = int(entities[-1]["_id"])
                if cursor is not None and next_cursor <= cursor:
                    raise CommandError(f"图实例迁移游标未推进: {cursor}")
                updates = []
                for entity in entities:
                    graph_id = int(entity["_id"])
                    inst_uuid = _canonical_uuid(entity.get("inst_uuid"))
                    if entity.get("inst_uuid") and not inst_uuid:
                        raise CommandError(f"图实例 {graph_id} 的 inst_uuid 非法")
                    if inst_uuid and uuid_owners.get(inst_uuid) not in {None, graph_id}:
                        raise CommandError(f"图实例 inst_uuid 重复: {inst_uuid}")
                    if not inst_uuid:
                        inst_uuid = str(uuid4())
                        while inst_uuid in uuid_owners:
                            inst_uuid = str(uuid4())
                        updates.append({"id": graph_id, "value": inst_uuid})
                    elif str(entity.get("inst_uuid")) != inst_uuid:
                        updates.append({"id": graph_id, "value": inst_uuid})
                    uuid_owners[inst_uuid] = graph_id
                    self._graph_uuid_by_id[graph_id] = inst_uuid
                stats["graph_instance_scanned"] += len(entities)
                stats["graph_uuid_added"] += len(updates)
                if updates and not dry_run:
                    graph.batch_update_node_property_values(INSTANCE, "inst_uuid", updates)
                cursor = next_cursor
                self._save_stage("graph_instances", cursor)

            self._save_stage("graph_instances", cursor or 0, completed=True)

            if not dry_run:
                graph.ensure_node_property_index(INSTANCE, "inst_uuid")
                stats["graph_index_ensured"] = 1

            edges = graph.query_edge(INSTANCE_ASSOCIATION, [], return_entity=True)
            stats["graph_relation_scanned"] = len(edges)
            business_keys = set()
            uuid_edge_ids = []
            digit_edge_ids = []
            for item in edges:
                edge = item.get("edge") or item
                src = item.get("src") or {}
                dst = item.get("dst") or {}
                src_uuid = (
                    _canonical_uuid(edge.get("src_inst_uuid"))
                    or _canonical_uuid(src.get("inst_uuid"))
                    or self._graph_uuid_by_id.get(_graph_id(src.get("_id")))
                    or self._graph_uuid_by_id.get(_graph_id(edge.get("src_inst_id")))
                )
                dst_uuid = (
                    _canonical_uuid(edge.get("dst_inst_uuid"))
                    or _canonical_uuid(dst.get("inst_uuid"))
                    or self._graph_uuid_by_id.get(_graph_id(dst.get("_id")))
                    or self._graph_uuid_by_id.get(_graph_id(edge.get("dst_inst_id")))
                )
                if not src_uuid or not dst_uuid:
                    raise CommandError(f"关系 {edge.get('_id')} 的端点缺少有效 inst_uuid")
                business_key = (edge.get("model_asst_id"), src_uuid, dst_uuid)
                if business_key in business_keys:
                    raise CommandError(f"实例关系业务键重复: {business_key}")
                business_keys.add(business_key)
                edge_id = int(edge["_id"])
                if _canonical_uuid(edge.get("src_inst_uuid")) != src_uuid or _canonical_uuid(edge.get("dst_inst_uuid")) != dst_uuid:
                    uuid_edge_ids.append((edge_id, src_uuid, dst_uuid))
                if "src_inst_id" in edge or "dst_inst_id" in edge:
                    digit_edge_ids.append(edge_id)
            stats["graph_relation_uuid_set"] = len(uuid_edge_ids)
            stats["graph_relation_digit_removed"] = len(digit_edge_ids)
            if not dry_run:
                for edge_id, src_uuid, dst_uuid in uuid_edge_ids:
                    graph.set_edge_properties(
                        edge_id,
                        {"src_inst_uuid": src_uuid, "dst_inst_uuid": dst_uuid},
                    )
                for offset in range(0, len(digit_edge_ids), batch_size):
                    graph.remove_edge_properties(
                        digit_edge_ids[offset : offset + batch_size],
                        ["src_inst_id", "dst_inst_id"],
                    )

    def _clean_config_versions(self, batch_size, dry_run, stats):
        cursor, completed = self._stage_cursor("config_versions")
        if completed:
            return
        while True:
            rows = list(ConfigFileVersion.objects.filter(id__gt=cursor, instance_uuid__isnull=True).order_by("id")[:batch_size])
            if not rows:
                self._save_stage("config_versions", cursor, completed=True)
                return
            cursor = rows[-1].id
            numeric_ids = [int(row.instance_id) for row in rows if str(row.instance_id).isdigit()]
            uuid_map = self._graph_uuid_map(numeric_ids)
            updates = []
            for row in rows:
                inst_uuid = _canonical_uuid(row.instance_id)
                if not inst_uuid and str(row.instance_id).isdigit():
                    inst_uuid = uuid_map.get(int(row.instance_id))
                if inst_uuid:
                    row.instance_uuid = inst_uuid
                    updates.append(row)
                else:
                    stats["config_orphan_skipped"] += 1
            stats["config_updated"] += len(updates)
            if updates and not dry_run:
                ConfigFileVersion.objects.bulk_update(updates, ["instance_uuid"])
            self._save_stage("config_versions", cursor)

    def _clean_change_records(self, batch_size, dry_run, stats):
        cursor, completed = self._stage_cursor("change_records")
        if completed:
            return
        while True:
            records = list(ChangeRecord.objects.filter(id__gt=cursor, inst_uuid__isnull=True).order_by("id")[:batch_size])
            if not records:
                self._save_stage("change_records", cursor, completed=True)
                return
            cursor = records[-1].id
            uuid_map = self._graph_uuid_map([record.inst_id for record in records if record.inst_id is not None])
            updates = []
            for record in records:
                inst_uuid = _instance_uuid_from_record(record) or uuid_map.get(record.inst_id)
                if inst_uuid:
                    record.inst_uuid = inst_uuid
                    updates.append(record)
                else:
                    stats["change_record_historical_unmapped"] += 1
            stats["change_record_updated"] += len(updates)
            if updates and not dry_run:
                ChangeRecord.objects.bulk_update(updates, ["inst_uuid"])
            self._save_stage("change_records", cursor)

    def _clean_subscriptions(self, batch_size, dry_run, stats):
        """双写 instance_uuids，保留 instance_ids，避免 T6 前读侧断裂。"""
        cursor, completed = self._stage_cursor("subscriptions")
        if completed:
            return
        while True:
            rules = list(SubscriptionRule.objects.filter(id__gt=cursor).order_by("id")[:batch_size])
            if not rules:
                self._save_stage("subscriptions", cursor, completed=True)
                return
            cursor = rules[-1].id
            numeric_ids = []
            for rule in rules:
                values = (rule.instance_filter or {}).get("instance_ids", [])
                numeric_ids.extend(int(value) for value in values if str(value).isdigit())
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed = []
            for rule in rules:
                instance_filter = dict(rule.instance_filter or {})
                old_values = instance_filter.get("instance_ids", [])
                if not old_values:
                    continue
                existing_uuids = [uuid_value for uuid_value in instance_filter.get("instance_uuids", []) if _canonical_uuid(uuid_value)]
                uuids = list(existing_uuids)
                for value in old_values:
                    inst_uuid = _canonical_uuid(value)
                    if not inst_uuid and str(value).isdigit():
                        inst_uuid = uuid_map.get(int(value))
                    if inst_uuid and inst_uuid not in uuids:
                        uuids.append(inst_uuid)
                if uuids and uuids != existing_uuids:
                    instance_filter["instance_uuids"] = uuids
                    rule.instance_filter = instance_filter
                    changed.append(rule)
            stats["subscription_updated"] += len(changed)
            if changed and not dry_run:
                SubscriptionRule.objects.bulk_update(changed, ["instance_filter"])
            self._save_stage("subscriptions", cursor)

    def _clean_followed_assets(self, batch_size, dry_run, stats):
        """关注资产仅保留 inst_uuid；无法映射的数字旧值进入 verify 阻断。"""
        cursor, completed = self._stage_cursor("followed_assets")
        if completed:
            return
        while True:
            configs = list(
                UserPersonalConfig.objects.filter(
                    id__gt=cursor,
                    config_key="cmdb_followed_assets",
                ).order_by(
                    "id"
                )[:batch_size]
            )
            if not configs:
                self._save_stage("followed_assets", cursor, completed=True)
                return
            cursor = configs[-1].id
            numeric_ids = []
            for config in configs:
                for item in (config.config_value or {}).get("items", []):
                    value = item.get("inst_id") if isinstance(item, dict) else None
                    if str(value).isdigit():
                        numeric_ids.append(int(value))
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed = []
            for config in configs:
                value = dict(config.config_value or {})
                cleaned_items = []
                item_changed = False
                for item in value.get("items", []):
                    if not isinstance(item, dict):
                        cleaned_items.append(item)
                        continue
                    cleaned = dict(item)
                    inst_uuid = _canonical_uuid(cleaned.get("inst_uuid"))
                    if not inst_uuid and str(cleaned.get("inst_id")).isdigit():
                        inst_uuid = uuid_map.get(int(cleaned["inst_id"]))
                    if inst_uuid:
                        if cleaned.get("inst_uuid") != inst_uuid:
                            cleaned["inst_uuid"] = inst_uuid
                            item_changed = True
                        if "inst_id" in cleaned:
                            cleaned.pop("inst_id", None)
                            item_changed = True
                    elif "inst_id" in cleaned:
                        stats["followed_asset_unmapped"] += 1
                    cleaned_items.append(cleaned)
                if item_changed:
                    value["items"] = cleaned_items
                    config.config_value = value
                    changed.append(config)
            stats["followed_asset_config_updated"] += len(changed)
            if changed and not dry_run:
                UserPersonalConfig.objects.bulk_update(changed, ["config_value"])
            self._save_stage("followed_assets", cursor)

    def _clean_enterprise_custom_reporting(self, batch_size, dry_run, stats):
        """清理 enterprise 待补关系和待审核删除中的跨请求图 ID。"""
        try:
            pending_model = django_apps.get_model("cmdb_enterprise", "CustomReportingPendingRelation")
            review_model = django_apps.get_model("cmdb_enterprise", "CustomReportingCleanupReview")
        except LookupError:
            return

        cursor, completed = self._stage_cursor("custom_reporting_pending")
        if not completed:
            while True:
                rows = list(pending_model.objects.filter(id__gt=cursor).order_by("id")[:batch_size])
                if not rows:
                    self._save_stage("custom_reporting_pending", cursor, completed=True)
                    break
                cursor = rows[-1].id
                numeric_ids = []
                for row in rows:
                    payload = row.relation_payload or {}
                    for endpoint_name in ("source", "target"):
                        endpoint = payload.get(endpoint_name) or {}
                        raw_id = endpoint.get("_id", endpoint.get("inst_id"))
                        if str(raw_id).isdigit():
                            numeric_ids.append(int(raw_id))
                uuid_map = self._graph_uuid_map(numeric_ids)
                changed = []
                for row in rows:
                    payload = dict(row.relation_payload or {})
                    row_changed = False
                    for endpoint_name in ("source", "target"):
                        endpoint = dict(payload.get(endpoint_name) or {})
                        raw_id = endpoint.get("_id", endpoint.get("inst_id"))
                        inst_uuid = _canonical_uuid(endpoint.get("inst_uuid"))
                        if not inst_uuid and str(raw_id).isdigit():
                            inst_uuid = uuid_map.get(int(raw_id))
                        if inst_uuid:
                            original_endpoint = dict(endpoint)
                            endpoint["inst_uuid"] = inst_uuid
                            endpoint.pop("_id", None)
                            endpoint.pop("inst_id", None)
                            if endpoint != original_endpoint:
                                payload[endpoint_name] = endpoint
                                row_changed = True
                        elif raw_id is not None:
                            stats["custom_reporting_unmapped"] += 1
                    if row_changed:
                        row.relation_payload = payload
                        changed.append(row)
                stats["custom_reporting_pending_updated"] += len(changed)
                if changed and not dry_run:
                    pending_model.objects.bulk_update(changed, ["relation_payload"])
                self._save_stage("custom_reporting_pending", cursor)

        cursor, completed = self._stage_cursor("custom_reporting_cleanup")
        if completed:
            return
        while True:
            rows = list(review_model.objects.filter(id__gt=cursor, status="pending").order_by("id")[:batch_size])
            if not rows:
                self._save_stage("custom_reporting_cleanup", cursor, completed=True)
                return
            cursor = rows[-1].id
            numeric_ids = [int(value) for row in rows for value in (row.review_payload or {}).get("delete_ids", []) if str(value).isdigit()]
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed = []
            for row in rows:
                payload = dict(row.review_payload or {})
                delete_ids = payload.get("delete_ids")
                if not isinstance(delete_ids, list):
                    continue
                delete_uuids = [uuid_map.get(int(value)) for value in delete_ids if str(value).isdigit()]
                if len(delete_uuids) != len(delete_ids) or any(not value for value in delete_uuids):
                    stats["custom_reporting_unmapped"] += 1
                    continue
                payload["delete_uuids"] = delete_uuids
                payload.pop("delete_ids", None)
                row.review_payload = payload
                changed.append(row)
            stats["custom_reporting_cleanup_updated"] += len(changed)
            if changed and not dry_run:
                review_model.objects.bulk_update(changed, ["review_payload"])
            self._save_stage("custom_reporting_cleanup", cursor)

    def _clean_collect_tasks(self, batch_size, dry_run, stats):
        """双写 subnet_uuids，保留 subnet_ids。"""
        cursor, completed = self._stage_cursor("collect_tasks")
        if completed:
            return
        while True:
            tasks = list(CollectModels.objects.filter(id__gt=cursor, model_id="ip").order_by("id")[:batch_size])
            if not tasks:
                self._save_stage("collect_tasks", cursor, completed=True)
                return
            cursor = tasks[-1].id
            numeric_ids = []
            for task in tasks:
                for container in (task.instances, task.params):
                    if not isinstance(container, dict):
                        continue
                    numeric_ids.extend(int(value) for value in container.get("subnet_ids", []) if str(value).isdigit())
            uuid_map = self._graph_uuid_map(numeric_ids)
            stats["collect_reference_unmapped"] += len(set(numeric_ids).difference(uuid_map))
            changed = []
            for task in tasks:
                task_changed = False
                for field in ("instances", "params"):
                    container = getattr(task, field)
                    if not isinstance(container, dict) or "subnet_ids" not in container:
                        continue
                    updated = dict(container)
                    old_values = updated.get("subnet_ids", [])
                    existing_uuids = [uuid_value for uuid_value in updated.get("subnet_uuids", []) if _canonical_uuid(uuid_value)]
                    uuids = list(existing_uuids)
                    for value in old_values:
                        inst_uuid = _canonical_uuid(value)
                        if not inst_uuid and str(value).isdigit():
                            inst_uuid = uuid_map.get(int(value))
                        if inst_uuid and inst_uuid not in uuids:
                            uuids.append(inst_uuid)
                    if uuids and uuids != existing_uuids:
                        updated["subnet_uuids"] = uuids
                        setattr(task, field, updated)
                        task_changed = True
                if task_changed:
                    changed.append(task)
            stats["collect_task_updated"] += len(changed)
            if changed and not dry_run:
                CollectModels.objects.bulk_update(changed, ["instances", "params"])
            self._save_stage("collect_tasks", cursor)

    @staticmethod
    def _rewrite_node_mgmt_sync_detail(value, uuid_map):
        if not isinstance(value, dict):
            return value, False
        result = dict(value)
        changed = False
        for bucket_name in ("add", "update"):
            bucket = result.get(bucket_name)
            if not isinstance(bucket, dict) or not isinstance(bucket.get("data"), list):
                continue
            rewritten_rows = []
            for row in bucket["data"]:
                if not isinstance(row, dict) or "_id" not in row:
                    rewritten_rows.append(row)
                    continue
                rewritten = dict(row)
                graph_id = rewritten.get("_id")
                inst_uuid = _canonical_uuid(rewritten.get("inst_uuid"))
                if not inst_uuid and str(graph_id).isdigit():
                    inst_uuid = uuid_map.get(int(graph_id))
                if inst_uuid and rewritten.get("inst_uuid") != inst_uuid:
                    rewritten["inst_uuid"] = inst_uuid
                    changed = True
                rewritten_rows.append(rewritten)
            if rewritten_rows != bucket["data"]:
                rewritten_bucket = dict(bucket)
                rewritten_bucket["data"] = rewritten_rows
                result[bucket_name] = rewritten_bucket
        return result, changed

    def _clean_node_mgmt_sync_details(self, batch_size, dry_run, stats):
        stage = "node_mgmt_sync_details"
        try:
            model = django_apps.get_model("cmdb", "NodeMgmtSyncRun")
        except LookupError:
            self._save_stage(stage, 0, completed=True)
            return
        if not self._model_table_exists(model):
            self._save_stage(stage, 0, completed=True)
            return
        cursor, completed = self._stage_cursor(stage)
        if completed:
            return
        while True:
            rows = list(model.objects.filter(pk__gt=cursor).order_by("pk")[:batch_size])
            if not rows:
                self._save_stage(stage, cursor, completed=True)
                return
            cursor = rows[-1].pk
            numeric_ids = []
            for row in rows:
                detail = row.detail_json if isinstance(row.detail_json, dict) else {}
                for bucket_name in ("add", "update"):
                    bucket = detail.get(bucket_name)
                    for item in (bucket or {}).get("data", []) if isinstance(bucket, dict) else []:
                        if isinstance(item, dict) and str(item.get("_id")).isdigit():
                            numeric_ids.append(int(item["_id"]))
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed_rows = []
            for row in rows:
                rewritten, changed = self._rewrite_node_mgmt_sync_detail(row.detail_json, uuid_map)
                if changed:
                    row.detail_json = rewritten
                    changed_rows.append(row)
            stats["node_mgmt_sync_detail_updated"] += len(changed_rows)
            if changed_rows and not dry_run:
                model.objects.bulk_update(changed_rows, ["detail_json"])
            self._save_stage(stage, cursor)

    def _clean_operation_targets(self, batch_size, dry_run, stats):
        stage = "operation_targets"
        try:
            model = django_apps.get_model("cmdb", "CmdbOperation")
        except LookupError:
            self._save_stage(stage, 0, completed=True)
            return
        if not self._model_table_exists(model):
            self._save_stage(stage, 0, completed=True)
            return
        cursor, completed = self._stage_cursor(stage)
        if completed:
            return
        while True:
            rows = list(model.objects.filter(pk__gt=cursor).order_by("pk")[:batch_size])
            if not rows:
                self._save_stage(stage, cursor, completed=True)
                return
            cursor = rows[-1].pk
            numeric_ids = []
            for row in rows:
                target = row.target if isinstance(row.target, dict) else {}
                value = target.get("instance_id")
                if str(value).isdigit() and not _canonical_uuid(target.get("instance_uuid")):
                    numeric_ids.append(int(value))
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed_rows = []
            for row in rows:
                target = dict(row.target or {}) if isinstance(row.target, dict) else {}
                if _canonical_uuid(target.get("instance_uuid")):
                    continue
                value = target.get("instance_id")
                inst_uuid = _canonical_uuid(value)
                if not inst_uuid and str(value).isdigit():
                    inst_uuid = uuid_map.get(int(value))
                if not inst_uuid:
                    continue
                target["instance_uuid"] = inst_uuid
                row.target = target
                changed_rows.append(row)
            stats["operation_target_updated"] += len(changed_rows)
            if changed_rows and not dry_run:
                with transaction.atomic():
                    model.objects.bulk_update(changed_rows, ["target"])
            self._save_stage(stage, cursor)

    @staticmethod
    def _has_cmdb_instance_context(value):
        if not isinstance(value, dict):
            return False
        if value.get("_id") is not None:
            return True
        return bool(value.get("model_id") and value.get("inst_name"))

    @staticmethod
    def _collect_graph_ids(value, acc, *, depth=0, allow_bare_instance_id=False):
        if depth > _JSON_REWRITE_MAX_DEPTH or value is None:
            return
        if isinstance(value, list):
            for item in value:
                Command._collect_graph_ids(item, acc, depth=depth + 1, allow_bare_instance_id=allow_bare_instance_id)
            return
        if not isinstance(value, dict):
            return
        scalar_keys = list(_ALWAYS_GRAPH_ID_SCALAR_KEYS)
        if allow_bare_instance_id or Command._has_cmdb_instance_context(value):
            scalar_keys.append(_CONTEXT_INST_ID_KEY)
        if allow_bare_instance_id:
            scalar_keys.append(_BARE_INSTANCE_ID_KEY)
        for src_key, _dst_key in scalar_keys:
            graph_id = _graph_id(value.get(src_key))
            if graph_id is not None:
                acc.append(graph_id)
        for src_key, _dst_key in _GRAPH_ID_LIST_KEYS:
            for item in value.get(src_key) or []:
                graph_id = _graph_id(item)
                if graph_id is not None:
                    acc.append(graph_id)
        for child in value.values():
            Command._collect_graph_ids(child, acc, depth=depth + 1, allow_bare_instance_id=allow_bare_instance_id)

    @staticmethod
    def _rewrite_scalar_uuid(result, src_key, dst_key, uuid_map):
        if _canonical_uuid(result.get(dst_key)):
            return False
        raw = result.get(src_key)
        inst_uuid = _canonical_uuid(raw)
        if not inst_uuid:
            graph_id = _graph_id(raw)
            inst_uuid = uuid_map.get(graph_id) if graph_id is not None else None
        if not inst_uuid:
            return False
        result[dst_key] = inst_uuid
        return True

    @staticmethod
    def _rewrite_json_uuids(value, uuid_map, *, depth=0, allow_bare_instance_id=False):
        if depth > _JSON_REWRITE_MAX_DEPTH:
            return value, False
        if isinstance(value, list):
            rewritten_items = []
            changed = False
            for item in value:
                rewritten, item_changed = Command._rewrite_json_uuids(item, uuid_map, depth=depth + 1, allow_bare_instance_id=allow_bare_instance_id)
                rewritten_items.append(rewritten)
                changed = changed or item_changed
            return rewritten_items, changed
        if not isinstance(value, dict):
            return value, False
        result = {}
        changed = False
        for key, child in value.items():
            rewritten, child_changed = Command._rewrite_json_uuids(child, uuid_map, depth=depth + 1, allow_bare_instance_id=allow_bare_instance_id)
            result[key] = rewritten
            changed = changed or child_changed
        for src_key, dst_key in _ALWAYS_GRAPH_ID_SCALAR_KEYS:
            changed = Command._rewrite_scalar_uuid(result, src_key, dst_key, uuid_map) or changed
        if allow_bare_instance_id or Command._has_cmdb_instance_context(result):
            changed = Command._rewrite_scalar_uuid(result, *_CONTEXT_INST_ID_KEY, uuid_map) or changed
        if allow_bare_instance_id:
            changed = Command._rewrite_scalar_uuid(result, *_BARE_INSTANCE_ID_KEY, uuid_map) or changed
        for src_key, dst_key in _GRAPH_ID_LIST_KEYS:
            old_values = result.get(src_key)
            if not isinstance(old_values, list):
                continue
            existing = [uuid_value for uuid_value in (result.get(dst_key) or []) if _canonical_uuid(uuid_value)]
            uuids = list(existing)
            for raw in old_values:
                inst_uuid = _canonical_uuid(raw)
                if not inst_uuid:
                    graph_id = _graph_id(raw)
                    inst_uuid = uuid_map.get(graph_id) if graph_id is not None else None
                if inst_uuid and inst_uuid not in uuids:
                    uuids.append(inst_uuid)
            if uuids and uuids != existing:
                result[dst_key] = uuids
                changed = True
        return result, changed

    @staticmethod
    def _rewrite_subscription_snapshot(snapshot, uuid_map):
        if not isinstance(snapshot, dict):
            return snapshot, False
        result = dict(snapshot)
        changed = False

        existing_uuids = [uuid_value for uuid_value in (result.get("instance_uuids") or []) if _canonical_uuid(uuid_value)]
        uuids = list(existing_uuids)
        for value in result.get("instances") or []:
            inst_uuid = _canonical_uuid(value)
            if not inst_uuid:
                graph_id = _graph_id(value)
                inst_uuid = uuid_map.get(graph_id) if graph_id is not None else None
            if inst_uuid and inst_uuid not in uuids:
                uuids.append(inst_uuid)
        if uuids and uuids != existing_uuids:
            result["instance_uuids"] = uuids
            changed = True

        relations = result.get("relations") if isinstance(result.get("relations"), dict) else {}
        existing_by_uuid = result.get("relations_by_uuid") if isinstance(result.get("relations_by_uuid"), dict) else {}
        relations_by_uuid = {key: dict(value) if isinstance(value, dict) else value for key, value in existing_by_uuid.items()}
        for src_key, models in relations.items():
            src_uuid = _canonical_uuid(src_key)
            if not src_uuid:
                graph_id = _graph_id(src_key)
                src_uuid = uuid_map.get(graph_id) if graph_id is not None else None
            if not src_uuid or not isinstance(models, dict):
                continue
            mapped_models = dict(relations_by_uuid.get(src_uuid) or {})
            model_changed = False
            for model, related_ids in models.items():
                mapped = [uuid_value for uuid_value in (mapped_models.get(model) or []) if _canonical_uuid(uuid_value)]
                original_mapped = list(mapped)
                for related_id in related_ids or []:
                    rel_uuid = _canonical_uuid(related_id)
                    if not rel_uuid:
                        graph_id = _graph_id(related_id)
                        rel_uuid = uuid_map.get(graph_id) if graph_id is not None else None
                    if rel_uuid and rel_uuid not in mapped:
                        mapped.append(rel_uuid)
                if mapped != original_mapped:
                    mapped_models[model] = mapped
                    model_changed = True
                elif mapped and model not in mapped_models:
                    mapped_models[model] = mapped
                    model_changed = True
            if model_changed or (mapped_models and relations_by_uuid.get(src_uuid) != mapped_models):
                relations_by_uuid[src_uuid] = mapped_models
                changed = True
        if relations_by_uuid != existing_by_uuid:
            result["relations_by_uuid"] = relations_by_uuid
            changed = True
        return result, changed

    def _clean_subscription_snapshots(self, batch_size, dry_run, stats):
        """双写 snapshot_data.instance_uuids / relations_by_uuid，保留旧数字键。"""
        cursor, completed = self._stage_cursor("subscription_snapshots")
        if completed:
            return
        while True:
            rules = list(SubscriptionRule.objects.filter(id__gt=cursor).order_by("id")[:batch_size])
            if not rules:
                self._save_stage("subscription_snapshots", cursor, completed=True)
                return
            cursor = rules[-1].id
            numeric_ids = []
            for rule in rules:
                snapshot = rule.snapshot_data if isinstance(rule.snapshot_data, dict) else {}
                for value in snapshot.get("instances") or []:
                    graph_id = _graph_id(value)
                    if graph_id is not None:
                        numeric_ids.append(graph_id)
                relations = snapshot.get("relations") if isinstance(snapshot.get("relations"), dict) else {}
                for src_key, models in relations.items():
                    graph_id = _graph_id(src_key)
                    if graph_id is not None:
                        numeric_ids.append(graph_id)
                    if not isinstance(models, dict):
                        continue
                    for related_ids in models.values():
                        for related_id in related_ids or []:
                            related_graph_id = _graph_id(related_id)
                            if related_graph_id is not None:
                                numeric_ids.append(related_graph_id)
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed = []
            for rule in rules:
                rewritten, row_changed = self._rewrite_subscription_snapshot(rule.snapshot_data, uuid_map)
                if row_changed:
                    rule.snapshot_data = rewritten
                    changed.append(rule)
            stats["subscription_snapshot_updated"] += len(changed)
            if changed and not dry_run:
                SubscriptionRule.objects.bulk_update(changed, ["snapshot_data"])
            self._save_stage("subscription_snapshots", cursor)

    def _clean_collect_instances(self, batch_size, dry_run, stats):
        """全量采集任务 instances/params 补 inst_uuid / subnet_uuids，保留数字键。"""
        cursor, completed = self._stage_cursor("collect_instances")
        if completed:
            return
        while True:
            tasks = list(CollectModels.objects.filter(id__gt=cursor).order_by("id")[:batch_size])
            if not tasks:
                self._save_stage("collect_instances", cursor, completed=True)
                return
            cursor = tasks[-1].id
            numeric_ids = []
            for task in tasks:
                self._collect_graph_ids(task.instances, numeric_ids)
                self._collect_graph_ids(task.params, numeric_ids)
            uuid_map = self._graph_uuid_map(numeric_ids)
            stats["collect_reference_unmapped"] += len(set(numeric_ids).difference(uuid_map))
            changed = []
            for task in tasks:
                rewritten_instances, instances_changed = self._rewrite_json_uuids(task.instances, uuid_map)
                rewritten_params, params_changed = self._rewrite_json_uuids(task.params, uuid_map)
                if not instances_changed and not params_changed:
                    continue
                if instances_changed:
                    task.instances = rewritten_instances
                if params_changed:
                    task.params = rewritten_params
                changed.append(task)
            stats["collect_instance_updated"] += len(changed)
            if changed and not dry_run:
                CollectModels.objects.bulk_update(changed, ["instances", "params"])
            self._save_stage("collect_instances", cursor)

    def _clean_collect_result_snapshots(self, batch_size, dry_run, stats):
        """采集结果快照递归补 inst_uuid；可变 JSON 每次全表重扫，不因 completed 跳过。"""
        cursor, _completed = self._stage_cursor("collect_result_snapshots")
        cursor = 0
        leftover_ids = []
        fields = ("format_data", "collect_data", "collect_digest", "topology_snapshot")
        while True:
            tasks = list(CollectModels.objects.filter(id__gt=cursor).order_by("id")[:batch_size])
            if not tasks:
                self._save_stage("collect_result_snapshots", cursor, completed=True)
                self._leftover_snapshot_ids = leftover_ids[:20]
                return
            cursor = tasks[-1].id
            numeric_ids = []
            for task in tasks:
                for field in fields:
                    self._collect_graph_ids(getattr(task, field), numeric_ids)
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed = []
            for task in tasks:
                row_changed = False
                for field in fields:
                    rewritten, field_changed = self._rewrite_json_uuids(getattr(task, field), uuid_map)
                    if field_changed:
                        setattr(task, field, rewritten)
                        row_changed = True
                if row_changed:
                    changed.append(task)
                    leftover_ids.append(task.id)
            stats["collect_result_snapshot_updated"] += len(changed)
            if changed and not dry_run:
                CollectModels.objects.bulk_update(changed, list(fields))
            self._save_stage("collect_result_snapshots", cursor)

    def _clean_operation_snapshots(self, batch_size, dry_run, stats):
        stage = "operation_snapshots"
        try:
            model = django_apps.get_model("cmdb", "CmdbOperation")
        except LookupError:
            self._save_stage(stage, 0, completed=True)
            return
        if not self._model_table_exists(model):
            self._save_stage(stage, 0, completed=True)
            return
        cursor, completed = self._stage_cursor(stage)
        if completed:
            return
        fields = ("request_snapshot", "result_snapshot")
        while True:
            rows = list(model.objects.filter(pk__gt=cursor).order_by("pk")[:batch_size])
            if not rows:
                self._save_stage(stage, cursor, completed=True)
                return
            cursor = rows[-1].pk
            numeric_ids = []
            for row in rows:
                for field in fields:
                    self._collect_graph_ids(getattr(row, field), numeric_ids, allow_bare_instance_id=True)
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed_rows = []
            for row in rows:
                row_changed = False
                for field in fields:
                    rewritten, field_changed = self._rewrite_json_uuids(getattr(row, field), uuid_map, allow_bare_instance_id=True)
                    if field_changed:
                        setattr(row, field, rewritten)
                        row_changed = True
                if row_changed:
                    changed_rows.append(row)
            stats["operation_snapshot_updated"] += len(changed_rows)
            if changed_rows and not dry_run:
                with transaction.atomic():
                    model.objects.bulk_update(changed_rows, list(fields))
            self._save_stage(stage, cursor)

    def _stage_cursor_str(self, stage):
        if getattr(self, "_dry_run", False):
            return "", False
        state, _ = CmdbUuidMigrationState.objects.get_or_create(stage=stage)
        return str(state.cursor or ""), state.completed

    def _clean_peer_cmdb_id_table(
        self,
        *,
        stage: str,
        app_label: str,
        model_name: str,
        batch_size: int,
        dry_run: bool,
        stats: dict,
        updated_key: str,
        unmapped_key: str,
    ):
        try:
            model = django_apps.get_model(app_label, model_name)
        except LookupError:
            self._save_stage(stage, 0, completed=True)
            return
        if not self._model_table_exists(model):
            self._save_stage(stage, 0, completed=True)
            return
        cursor, completed = self._stage_cursor_str(stage)
        if completed:
            return
        while True:
            qs = model.objects.exclude(cmdb_id__isnull=True).exclude(cmdb_id="").order_by("pk")
            if cursor:
                qs = qs.filter(pk__gt=cursor)
            rows = list(qs[:batch_size])
            if not rows:
                self._save_stage(stage, cursor or 0, completed=True)
                return
            cursor = rows[-1].pk
            numeric_ids = []
            pending = []
            for row in rows:
                value = str(getattr(row, "cmdb_id", "") or "").strip()
                if _canonical_uuid(value):
                    continue
                graph_id = _graph_id(value)
                if graph_id is None:
                    continue
                numeric_ids.append(graph_id)
                pending.append((row, graph_id))
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed_rows = []
            for row, graph_id in pending:
                inst_uuid = uuid_map.get(graph_id)
                if not inst_uuid:
                    stats[unmapped_key] += 1
                    continue
                row.cmdb_id = inst_uuid
                changed_rows.append(row)
            stats[updated_key] += len(changed_rows)
            if changed_rows and not dry_run:
                model.objects.bulk_update(changed_rows, ["cmdb_id"])
            self._save_stage(stage, cursor)

    def _clean_monitor_cmdb_ids(self, batch_size, dry_run, stats):
        self._clean_peer_cmdb_id_table(
            stage="monitor_cmdb_ids",
            app_label="monitor",
            model_name="MonitorInstance",
            batch_size=batch_size,
            dry_run=dry_run,
            stats=stats,
            updated_key="monitor_cmdb_id_updated",
            unmapped_key="monitor_cmdb_id_unmapped",
        )

    def _clean_node_cmdb_ids(self, batch_size, dry_run, stats):
        self._clean_peer_cmdb_id_table(
            stage="node_cmdb_ids",
            app_label="node_mgmt",
            model_name="Node",
            batch_size=batch_size,
            dry_run=dry_run,
            stats=stats,
            updated_key="node_cmdb_id_updated",
            unmapped_key="node_cmdb_id_unmapped",
        )

    def _clean_operation_outbox(self, batch_size, dry_run, stats):
        try:
            model = django_apps.get_model("cmdb", "CmdbOperationOutbox")
        except LookupError:
            self._save_stage("operation_outbox", 0, completed=True)
            return
        stage = "operation_outbox"
        if not self._model_table_exists(model):
            self._save_stage(stage, 0, completed=True)
            return
        cursor, completed = self._stage_cursor(stage)
        if completed:
            return
        while True:
            rows = list(model.objects.filter(pk__gt=cursor).order_by("pk")[:batch_size])
            if not rows:
                self._save_stage(stage, cursor, completed=True)
                return
            cursor = rows[-1].pk
            numeric_ids = []
            pending_rows = []
            for row in rows:
                if getattr(row, "status", None) == "success":
                    continue
                pending_rows.append(row)
                self._collect_graph_ids(row.payload, numeric_ids, allow_bare_instance_id=True)
            uuid_map = self._graph_uuid_map(numeric_ids)
            changed_rows = []
            for row in pending_rows:
                rewritten, changed = self._rewrite_json_uuids(row.payload, uuid_map, allow_bare_instance_id=True)
                if changed:
                    row.payload = rewritten
                    changed_rows.append(row)
            stats["operation_outbox_updated"] += len(changed_rows)
            if changed_rows and not dry_run:
                with transaction.atomic():
                    model.objects.bulk_update(changed_rows, ["payload"])
            self._save_stage(stage, cursor)

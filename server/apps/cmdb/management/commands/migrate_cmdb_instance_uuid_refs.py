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


class Command(BaseCommand):
    help = "在 0044 结构迁移之后补齐图实例 UUID，并清洗图关系与 CMDB PostgreSQL 活动引用。" "不进 batch_init；OA/告警等跨模块留给 T6。"

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
            "followed_asset_config_updated": 0,
            "collect_task_updated": 0,
            "node_mgmt_sync_detail_updated": 0,
            "operation_target_updated": 0,
        }
        self._graph_uuid_by_id = {}
        graph_cursor, graph_completed = self._stage_cursor("graph_instances")
        if graph_cursor or graph_completed:
            self._load_graph_uuid_map(batch_size)
        self._clean_graph(batch_size, dry_run, stats)
        self._clean_config_versions(batch_size, dry_run, stats)
        self._clean_change_records(batch_size, dry_run, stats)
        self._clean_subscriptions(batch_size, dry_run, stats)
        self._clean_followed_assets(batch_size, dry_run, stats)
        self._clean_collect_tasks(batch_size, dry_run, stats)
        self._clean_node_mgmt_sync_details(batch_size, dry_run, stats)
        self._clean_operation_targets(batch_size, dry_run, stats)
        if verify:
            blocker_keys = (
                "graph_uuid_added",
                "graph_relation_uuid_set",
                "graph_relation_digit_removed",
                "config_updated",
                "change_record_updated",
                "subscription_updated",
                "followed_asset_config_updated",
                "collect_task_updated",
                "node_mgmt_sync_detail_updated",
                "operation_target_updated",
            )
            blockers = {key: stats[key] for key in blocker_keys if stats[key]}
            if blockers:
                raise CommandError(f"CMDB UUID 迁移验证失败，仍存在待清洗项: {blockers}")
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
        """双写 inst_uuid，保留 inst_id。"""
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
                    if inst_uuid and cleaned.get("inst_uuid") != inst_uuid:
                        cleaned["inst_uuid"] = inst_uuid
                        item_changed = True
                    cleaned_items.append(cleaned)
                if item_changed:
                    value["items"] = cleaned_items
                    config.config_value = value
                    changed.append(config)
            stats["followed_asset_config_updated"] += len(changed)
            if changed and not dry_run:
                UserPersonalConfig.objects.bulk_update(changed, ["config_value"])
            self._save_stage("followed_assets", cursor)

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
        try:
            model = django_apps.get_model("cmdb", "NodeMgmtSyncRun")
        except LookupError:
            return
        stage = "node_mgmt_sync_details"
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
        try:
            model = django_apps.get_model("cmdb", "CmdbOperation")
        except LookupError:
            return
        stage = "operation_targets"
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

from uuid import UUID

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, models, transaction

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.uuid_migration_state import CmdbUuidMigrationState
from apps.cmdb.services.instance import InstanceManage


def _canonical_uuid(value):
    try:
        return str(UUID(str(value))) if value else None
    except (TypeError, ValueError, AttributeError):
        return None


class Command(BaseCommand):
    _RENDER_SNAPSHOT_MIGRATION_FIELDS = frozenset({"view_sets", "filters", "other"})
    # NetworkTopology 不在此列：其 bk_inst_id 是 WeOps 设备身份，不是 BK-Lite UUID。
    OA_UUID_MODEL_FIELDS = {
        "Dashboard": ("view_sets", "filters", "other"),
        "Topology": ("view_sets", "other"),
        "Architecture": ("view_sets", "other"),
        "Screen": ("view_sets", "other"),
        "Report": ("view_sets", "other"),
        "DashboardReportRenderSnapshot": ("view_sets", "filters", "other"),
    }

    help = (
        "清洗 operation_analysis 画布/组件 JSON 中的 CMDB 实例引用："
        "bk_inst_id→bk_inst_uuid、instId→instUuid。"
        "不含 NetworkTopology：其 bk_inst_id 是 WeOps 设备身份，不是 BK-Lite UUID。"
        "可与 migrate_cmdb_instance_uuid_refs 并行或手动执行；依赖图侧已有 _id→uuid 映射。"
        "部署后由 Celery 运行期任务自动幂等收敛；不进 batch_init 硬门禁。"
    )

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--verify", action="store_true")

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
                self._graph_uuid_by_id[int(entity["_id"])] = inst_uuid
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

    def _preload_graph_uuids(self, batch_size):
        cursor = 0
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
                    if entity.get("_id") is not None and inst_uuid:
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
            "operation_analysis_record_updated": 0,
            "operation_analysis_orphan_removed": 0,
        }
        self._graph_uuid_by_id = {}
        try:
            self._preload_graph_uuids(batch_size)
        except Exception as exc:
            # 允许在无图连接的单测中仅通过 query_entity_by_ids 补映射
            self.stdout.write(self.style.WARNING(f"预加载图 UUID 跳过: {exc}"))

        self._clean_operation_analysis_refs(batch_size, dry_run, stats)
        if verify:
            blockers = {key: stats[key] for key in ("operation_analysis_record_updated",) if stats[key]}
            if blockers:
                raise CommandError(f"OA UUID 迁移验证失败，仍存在待清洗项: {blockers}")
        self.stdout.write(self.style.SUCCESS(str(stats)))

    @staticmethod
    def _collect_legacy_instance_ids(value):
        ids = []
        if isinstance(value, list):
            for item in value:
                ids.extend(Command._collect_legacy_instance_ids(item))
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in {"bk_inst_id", "instId"} and str(item).isdigit():
                    ids.append(int(item))
                else:
                    ids.extend(Command._collect_legacy_instance_ids(item))
        return ids

    def _rewrite_operation_analysis_value(self, value, uuid_map, stats):
        if isinstance(value, list):
            result = []
            changed = False
            for item in value:
                rewritten, item_changed, orphan = self._rewrite_operation_analysis_value(item, uuid_map, stats)
                changed = changed or item_changed
                if orphan:
                    stats["operation_analysis_orphan_removed"] += 1
                    changed = True
                    continue
                result.append(rewritten)
            return result, changed, False
        if not isinstance(value, dict):
            return value, False, False

        result = {}
        changed = False
        identity_keys = {
            "bk_inst_id": "bk_inst_uuid",
            "instId": "instUuid",
        }
        for key, item in value.items():
            target_key = identity_keys.get(key)
            if target_key:
                inst_uuid = _canonical_uuid(item)
                if not inst_uuid and str(item).isdigit():
                    inst_uuid = uuid_map.get(int(item))
                if not inst_uuid:
                    return None, True, True
                result[target_key] = inst_uuid
                changed = True
                continue
            rewritten, item_changed, orphan = self._rewrite_operation_analysis_value(item, uuid_map, stats)
            changed = changed or item_changed
            if orphan:
                stats["operation_analysis_orphan_removed"] += 1
                changed = True
                continue
            result[key] = rewritten

        if isinstance(result.get("nodes"), list) and isinstance(result.get("links"), list):
            node_ids = {node.get("id") for node in result["nodes"] if isinstance(node, dict) and node.get("id")}
            filtered_links = [
                link
                for link in result["links"]
                if isinstance(link, dict) and link.get("source_node_id") in node_ids and link.get("target_node_id") in node_ids
            ]
            if len(filtered_links) != len(result["links"]):
                stats["operation_analysis_orphan_removed"] += len(result["links"]) - len(filtered_links)
                result["links"] = filtered_links
                changed = True
        return result, changed, False

    @classmethod
    def _bulk_update_render_snapshots(cls, model, rows, fields):
        """仅在本维护命令内修订不可变渲染快照的实例身份引用。"""
        unexpected_fields = set(fields) - cls._RENDER_SNAPSHOT_MIGRATION_FIELDS
        if unexpected_fields:
            raise CommandError("渲染快照身份迁移只允许修改 view_sets/filters/other")
        with transaction.atomic():
            updated = 0
            for row in rows:
                values = {field: getattr(row, field) for field in fields}
                updated += models.QuerySet.update(model.objects.filter(pk=row.pk), **values)
        return updated

    def _clean_operation_analysis_refs(self, batch_size, dry_run, stats):
        self._dry_run = dry_run
        for model_name, fields in self.OA_UUID_MODEL_FIELDS.items():
            try:
                model = django_apps.get_model("operation_analysis", model_name)
            except LookupError:
                continue
            stage = f"oa_uuid:{model_name}"
            if not self._model_table_exists(model):
                self._save_stage(stage, 0, completed=True)
                continue
            cursor, completed = self._stage_cursor(stage)
            if completed:
                continue
            while True:
                rows = list(model.objects.filter(pk__gt=cursor).order_by("pk")[:batch_size])
                if not rows:
                    self._save_stage(stage, cursor, completed=True)
                    break
                cursor = rows[-1].pk
                numeric_ids = []
                for row in rows:
                    for field in fields:
                        numeric_ids.extend(self._collect_legacy_instance_ids(getattr(row, field, None)))
                uuid_map = self._graph_uuid_map(numeric_ids)
                changed_rows = []
                for row in rows:
                    row_changed = False
                    for field in fields:
                        rewritten, changed, orphan = self._rewrite_operation_analysis_value(getattr(row, field, None), uuid_map, stats)
                        if orphan:
                            rewritten = {} if isinstance(getattr(row, field, None), dict) else []
                        if changed or orphan:
                            setattr(row, field, rewritten)
                            row_changed = True
                    if row_changed:
                        changed_rows.append(row)
                stats["operation_analysis_record_updated"] += len(changed_rows)
                if changed_rows and not dry_run:
                    if model_name == "DashboardReportRenderSnapshot":
                        self._bulk_update_render_snapshots(model, changed_rows, list(fields))
                    else:
                        model.objects.bulk_update(changed_rows, list(fields))
                self._save_stage(stage, cursor)

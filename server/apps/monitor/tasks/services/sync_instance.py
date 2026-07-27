from apps.core.logger import celery_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models.monitor_object import MonitorObject, MonitorInstance, MonitorInstanceOrganization
from apps.monitor.services.auto_discovery_lifecycle import AutoDiscoveryLifecycleService
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from django.utils import timezone


class SyncInstance:
    def __init__(self):
        self.monitor_map = self.get_monitor_map()
        self.failed_monitor_object_ids = set()
        self.successful_monitor_object_ids = set()

    def get_monitor_map(self):
        monitor_objs = MonitorObject.objects.all()
        return {i.name: i.id for i in monitor_objs}

    @staticmethod
    def parse_organization_id(metric_info):
        organization_id = metric_info.get("metric", {}).get("organization_id")
        if organization_id in (None, ""):
            return None
        try:
            return int(organization_id)
        except (TypeError, ValueError):
            return None

    def get_instance_map_by_metrics(self):
        """通过查询指标获取实例信息"""
        instances_map = {}
        monitor_objs = MonitorObject.objects.all().values(
            *MonitorObjConstants.OBJ_KEYS,
            "level",
            "parent_id",
            "parent__instance_id_keys",
        )
        active_parent_instances = set(
            MonitorInstance.objects.filter(is_deleted=False, is_active=True).values_list(
                "monitor_object_id", "id"
            )
        )

        for monitor_info in monitor_objs:
            if monitor_info["name"] not in self.monitor_map:
                continue
            query = monitor_info["default_metric"]
            if not query:
                continue
            try:
                metrics = VictoriaMetricsAPI().query(query, step="10m")
            except Exception:
                monitor_object_id = self.monitor_map[monitor_info["name"]]
                self.failed_monitor_object_ids.add(monitor_object_id)
                logger.exception(
                    "监控-实例发现查询失败，跳过本对象且保留其现有实例: "
                    f"{monitor_info['name']}"
                )
                continue
            self.successful_monitor_object_ids.add(self.monitor_map[monitor_info["name"]])

            # 记录当前监控对象发现的实例数量
            current_monitor_instance_count = 0

            for metric_info in metrics.get("data", {}).get("result", []):
                metric_labels = metric_info.get("metric", {})
                if monitor_info["level"] == "derivative":
                    parent_keys = monitor_info["parent__instance_id_keys"] or []
                    parent_values = tuple(metric_labels.get(key) for key in parent_keys)
                    parent_identity = (monitor_info["parent_id"], str(parent_values))
                    if (
                        not parent_keys
                        or any(value in (None, "") for value in parent_values)
                        or parent_identity not in active_parent_instances
                    ):
                        continue
                instance_id = tuple([metric_info["metric"].get(i) for i in monitor_info["instance_id_keys"]])
                instance_name = "__".join([str(i) for i in instance_id])
                if not instance_id:
                    continue
                instance_id = str(instance_id)
                instances_map[instance_id] = {
                    "id": instance_id,
                    "name": instance_name,
                    "monitor_object_id": self.monitor_map[monitor_info["name"]],
                    "auto": True,
                    "is_deleted": False,
                    "organization_id": self.parse_organization_id(metric_info),
                }
                current_monitor_instance_count += 1

            obj_msg = f"监控-实例发现{monitor_info['name']},数量:{current_monitor_instance_count}"
            logger.info(obj_msg)
        return instances_map

    @staticmethod
    def build_organization_relations(instance_ids, metrics_instance_map):
        return [
            MonitorInstanceOrganization(
                monitor_instance_id=instance_id,
                organization=metrics_instance_map[instance_id]["organization_id"],
            )
            for instance_id in instance_ids
            if metrics_instance_map[instance_id].get("organization_id") is not None
        ]

    # 查询库中已有的实例
    def get_exist_instance_set(self):
        exist_instances = MonitorInstance.objects.filter().values("id")
        return {i["id"] for i in exist_instances}

    def sync_monitor_instances(self):
        metrics_instance_map = self.get_instance_map_by_metrics()  # VM 指标采集
        vm_all = set(metrics_instance_map.keys())

        # 查询所有实例ID（包括手动和自动），用于判断是否真正需要新增
        all_existing_ids = set(MonitorInstance.objects.values_list("id", flat=True))

        # 只查询自动发现的实例（auto=True），用于后续的恢复和删除逻辑
        all_instances_qs = (
            MonitorInstance.objects.filter(auto=True)
            .exclude(monitor_object_id__in=self.failed_monitor_object_ids)
            .values("id", "is_deleted")
        )
        table_all = {i["id"] for i in all_instances_qs}
        table_deleted = {i["id"] for i in all_instances_qs if i["is_deleted"]}

        # 计算增删改集合
        # add_set: VM中新出现的实例 - 所有已存在的实例（不管手动还是自动），避免主键冲突
        add_set = vm_all - all_existing_ids
        # update_set: VM中出现 且 数据库中已删除的自动发现实例（需要恢复）
        update_set = vm_all & table_deleted
        # 显式标记删除且未重新上报的实例沿用原有物理删除语义。
        delete_set = table_deleted - vm_all
        logger.info(
            f"监控实例同步 - 新增:{len(add_set)}, 恢复:{len(update_set)}, 物理删除:{len(delete_set)}"
        )

        if delete_set:
            from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService

            delete_ids = list(delete_set)
            for offset in range(0, len(delete_ids), MonitorInstanceRemovalService.MAX_BATCH_SIZE):
                MonitorInstanceRemovalService.remove(
                    delete_ids[offset:offset + MonitorInstanceRemovalService.MAX_BATCH_SIZE]
                )

        # 新增实例（完全不存在于数据库的）
        if add_set:
            create_instances = [
                MonitorInstance(
                    **{key: value for key, value in metrics_instance_map[instance_id].items() if key != "organization_id"},
                    last_seen_at=timezone.now(),
                )
                for instance_id in add_set
            ]
            MonitorInstance.objects.bulk_create(create_instances, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
            organization_relations = self.build_organization_relations(add_set, metrics_instance_map)
            if organization_relations:
                MonitorInstanceOrganization.objects.bulk_create(
                    organization_relations,
                    batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE,
                    ignore_conflicts=True,
                )
            logger.info(f"新增自动发现实例: {len(create_instances)}")

        # 恢复已删除的自动发现实例（使用 filter().update() 而不是 bulk_update）
        if update_set:
            updated_count = MonitorInstance.objects.filter(id__in=update_set, is_deleted=True, auto=True).update(
                is_deleted=False,
                is_active=True,
                last_seen_at=timezone.now(),
                missing_duration_seconds=0,
            )
            organization_relations = self.build_organization_relations(update_set, metrics_instance_map)
            if organization_relations:
                MonitorInstanceOrganization.objects.bulk_create(
                    organization_relations,
                    batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE,
                    ignore_conflicts=True,
                )
            logger.info(f"恢复已删除的自动发现实例: {updated_count}")

        AutoDiscoveryLifecycleService.reconcile(
            metrics_instance_map,
            self.successful_monitor_object_ids,
            timezone.now(),
        )

    def run(self):
        """更新监控实例"""
        self.sync_monitor_instances()

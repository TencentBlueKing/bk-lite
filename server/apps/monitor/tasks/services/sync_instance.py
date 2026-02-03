from apps.core.logger import celery_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models.monitor_object import MonitorObject, MonitorInstance
from apps.monitor.services.policy_source_cleanup import cleanup_policy_sources
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class SyncInstance:
    def __init__(self):
        self.monitor_map = self.get_monitor_map()

    def get_monitor_map(self):
        monitor_objs = MonitorObject.objects.all()
        return {i.name: i.id for i in monitor_objs}

    def get_instance_map_by_metrics(self):
        """通过查询指标获取实例信息"""
        instances_map = {}
        monitor_objs = MonitorObject.objects.all().values(*MonitorObjConstants.OBJ_KEYS)

        for monitor_info in monitor_objs:
            if monitor_info["name"] not in self.monitor_map:
                continue
            query = monitor_info["default_metric"]
            if not query:
                continue
            metrics = VictoriaMetricsAPI().query(query, step="10m")

            # 记录当前监控对象发现的实例数量
            current_monitor_instance_count = 0

            for metric_info in metrics.get("data", {}).get("result", []):
                instance_id = tuple(
                    [
                        metric_info["metric"].get(i)
                        for i in monitor_info["instance_id_keys"]
                    ]
                )
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
                }
                current_monitor_instance_count += 1

            obj_msg = f"监控-实例发现{monitor_info['name']},数量:{current_monitor_instance_count}"
            logger.info(obj_msg)
        return instances_map

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
        all_instances_qs = MonitorInstance.objects.filter(auto=True).values(
            "id", "is_deleted"
        )
        table_all = {i["id"] for i in all_instances_qs}
        table_deleted = {i["id"] for i in all_instances_qs if i["is_deleted"]}
        table_alive = table_all - table_deleted

        # 计算增删改集合
        # add_set: VM中新出现的实例 - 所有已存在的实例（不管手动还是自动），避免主键冲突
        add_set = vm_all - all_existing_ids
        # update_set: VM中出现 且 数据库中已删除的自动发现实例（需要恢复）
        update_set = vm_all & table_deleted
        # delete_set: 已删除的自动发现实例 且 不在VM中（可以物理删除）
        delete_set = table_deleted & (table_all - vm_all)

        logger.info(
            f"监控实例同步 - 新增:{len(add_set)}, 恢复:{len(update_set)}, 物理删除:{len(delete_set)}"
        )

        if delete_set:
            cleanup_policy_sources(delete_set)
            deleted_count = MonitorInstance.objects.filter(
                id__in=delete_set, is_deleted=True, auto=True
            ).delete()[0]
            logger.info(f"物理删除已标记删除的自动发现实例: {deleted_count}")

        # 新增实例（完全不存在于数据库的）
        if add_set:
            create_instances = [
                MonitorInstance(**metrics_instance_map[instance_id])
                for instance_id in add_set
            ]
            MonitorInstance.objects.bulk_create(
                create_instances, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
            )
            logger.info(f"新增自动发现实例: {len(create_instances)}")

        # 恢复已删除的自动发现实例（使用 filter().update() 而不是 bulk_update）
        if update_set:
            updated_count = MonitorInstance.objects.filter(
                id__in=update_set, is_deleted=True, auto=True
            ).update(is_deleted=False)
            logger.info(f"恢复已删除的自动发现实例: {updated_count}")

        # ========== 活跃状态管理 ==========
        # 计算本周期不活跃的实例（在数据库中但不在VM中的活跃自动发现实例）
        no_alive_set = table_alive - vm_all

        # 在更新状态之前，先查询上个周期已经不活跃的实例
        previous_inactive_ids = set(
            MonitorInstance.objects.filter(is_active=False, auto=True).values_list(
                "id", flat=True
            )
        )

        # 计算连续两个周期都不活跃的实例
        continuous_inactive_set = previous_inactive_ids & no_alive_set

        # 更新活跃状态
        if no_alive_set:
            # 将本周期不在VM中的活跃自动发现实例标记为不活跃
            updated_count = MonitorInstance.objects.filter(
                id__in=no_alive_set, auto=True
            ).update(is_active=False)
            logger.info(f"标记不活跃实例: {updated_count}")

        if vm_all:
            # 将本周期在VM中的自动发现实例标记为活跃（包括新增和恢复的）
            updated_count = MonitorInstance.objects.filter(
                id__in=vm_all, auto=True
            ).update(is_active=True)
            logger.info(f"标记活跃实例: {updated_count}")

        if continuous_inactive_set:
            cleanup_policy_sources(continuous_inactive_set)
            deleted_count = MonitorInstance.objects.filter(
                id__in=continuous_inactive_set, auto=True
            ).delete()[0]
            logger.info(f"删除连续两周期不活跃的自动发现实例: {deleted_count}")
        else:
            logger.info("无连续不活跃实例需要删除")

    def run(self):
        """更新监控实例"""
        self.sync_monitor_instances()

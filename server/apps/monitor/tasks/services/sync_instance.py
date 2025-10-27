from apps.core.logger import celery_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models.monitor_object import MonitorObject, MonitorInstance
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

        all_instances_qs = MonitorInstance.objects.all().values("id", "is_deleted")
        table_all = {i["id"] for i in all_instances_qs}
        table_deleted = {i["id"] for i in all_instances_qs if i["is_deleted"]}
        table_alive = table_all - table_deleted

        # 计算增删改集合
        add_set = vm_all - table_alive
        update_set = vm_all & table_deleted
        delete_set = table_deleted & (table_all - vm_all)

        # 执行删除（物理删除）
        if delete_set:
            MonitorInstance.objects.filter(id__in=delete_set, is_deleted=True).delete()

        # 需要插入或更新的对象构建
        create_instances = []
        update_instances = []

        for instance_id in (add_set | update_set):
            info = metrics_instance_map[instance_id]
            instance = MonitorInstance(**info)
            if instance_id in update_set:
                update_instances.append(instance)
            else:
                create_instances.append(instance)

        # 新增（完全不存在的）
        if create_instances:
            MonitorInstance.objects.bulk_create(create_instances, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        # 恢复逻辑删除
        if update_instances:
            for instance in update_instances:
                instance.is_deleted = False  # 恢复
            MonitorInstance.objects.bulk_update(update_instances, ["name", "is_deleted", "auto"], batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE)

        # 计算不活跃实例
        no_alive_set = table_alive - vm_all

        # 查询不活跃实例
        no_alive_instances = {i["id"] for i in MonitorInstance.objects.filter(is_active=False, auto=True).values("id")}

        MonitorInstance.objects.filter(id__in=no_alive_set).update(is_active=False)
        MonitorInstance.objects.exclude(id__in=no_alive_set).update(is_active=True)

        if not no_alive_instances:
            return

        # 删除不活跃且为自动发现的实例
        MonitorInstance.objects.filter(id__in=no_alive_instances).delete()


    def run(self):
        """更新监控实例"""
        self.sync_monitor_instances()

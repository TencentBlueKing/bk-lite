from datetime import datetime
from typing import Type

from django.utils import timezone

from apps.cmdb.collection.common import Management
from apps.cmdb.constants.constants import INSTANCE, DataCleanupStrategy
from apps.cmdb.graph.drivers.graph_client import GraphClient


class MetricsCannula:
    def __init__(
        self,
        inst_id,
        organization: list,
        inst_name: str,
        task_id: int,
        collect_plugin: Type,
        manual: bool = False,
        default_metrics: dict = None,
        filter_collect_task=True,
        data_cleanup_strategy: str = None,
        plugin_kwargs: dict = None,
        reconcile_task_assets: bool = False,
        task=None,
    ):
        self.task = task
        self.inst_id = inst_id
        self.organization = organization
        self.task_id = str(task_id)
        self.manual = False if default_metrics else manual
        self.inst_name = inst_name
        self.collect_plugin = collect_plugin
        self.plugin_kwargs = plugin_kwargs or {}
        self.filter_collect_task = filter_collect_task
        self.reconcile_task_assets = reconcile_task_assets
        self.data_cleanup_strategy = data_cleanup_strategy or DataCleanupStrategy.NO_CLEANUP
        self.collect_data = {}
        self.collect_params = {}
        self.raw_data = []
        self.collect_plugin_instance = None
        self.collection_metrics = default_metrics or self.get_collection_metrics()
        self.now_time = datetime.now(timezone.utc).isoformat()
        self.add_list = []
        self.update_list = []
        self.delete_list = []
        self.assos_list = []

    def get_collection_metrics(self):
        """获取采集指标"""
        new_metrics = self.collect_plugin(self.inst_name, self.inst_id, self.task_id, **self.plugin_kwargs)
        self.collect_plugin_instance = new_metrics
        result = new_metrics.run()
        self.collect_data = new_metrics.result
        for i in new_metrics.raw_data:
            if i.get("metric"):
                if i["value"][0]:
                    # 往原始数据中打入vm指标的时间，为“数据实际上报时间”
                    i["metric"]["__time__"] = datetime.fromtimestamp(i["value"][0], timezone.utc).isoformat()
                self.raw_data.append(i["metric"])
        return result

    @staticmethod
    def contrast(old_map, new_map):
        """数据对比"""
        add_list, update_list, delete_list = [], [], []
        for key, info in new_map.items():
            if key not in old_map:
                add_list.append(info)
            else:
                info.update(_id=old_map[key]["_id"])
                update_list.append(info)
        for key, info in old_map.items():
            if key not in new_map:
                delete_list.append(info)
        return add_list, update_list, delete_list

    def _query_task_assets(self, ag, model_id, metrics):
        """当前任务资产参与清理；本轮命中的同组织无任务资产只参与接管。"""
        base_params = [{"field": "model_id", "type": "str=", "value": model_id}]
        old_by_id = {}
        # 历史数据同时存在整数和字符串任务 ID。
        for field_type, task_id in (("str=", self.task_id), ("int=", int(self.task_id))):
            rows, _ = ag.query_entity(INSTANCE, base_params + [{"field": "collect_task", "type": field_type, "value": task_id}])
            old_by_id.update((row["_id"], row) for row in rows)

        organizations = {str(value) for value in (self.organization or [])}
        conflicts = {}
        names = list(dict.fromkeys(row["inst_name"] for row in metrics))
        for start in range(0, len(names), 200):
            candidates, _ = ag.query_entity(INSTANCE, base_params + [{"field": "inst_name", "type": "str[]", "value": names[start : start + 200]}])
            for row in candidates:
                owner = row.get("collect_task")
                if str(owner) == self.task_id:
                    old_by_id[row["_id"]] = row
                elif owner not in (None, ""):
                    conflicts[row["inst_name"]] = "已有资产属于其他采集任务，无法自动接管"
                elif not organizations.intersection(str(value) for value in (row.get("organization") or [])):
                    conflicts[row["inst_name"]] = "已有资产不在当前采集组织范围内，无法自动接管"
                else:
                    old_by_id[row["_id"]] = row

        accepted, failed = [], []
        for row in metrics:
            error = conflicts.get(row["inst_name"])
            if error:
                failed.append({"instance_info": {"model_id": model_id, "inst_name": row["inst_name"]}, "error": error})
            else:
                accepted.append(row)
        old_data = [row for row in old_by_id.values() if row["inst_name"] not in conflicts]
        return old_data, accepted, failed

    def collect_controller(self) -> dict:
        if self.reconcile_task_assets and getattr(self.task, "model_id", None) == "vmware_vc":
            from apps.cmdb.collection.vmware_reconciliation import collect_vmware

            return collect_vmware(self)
        return self._collect_models()

    def _collect_models(self) -> dict:
        result = {}
        all_count = 0
        for model_id, metrics in self.collection_metrics.items():
            all_count += len(metrics)
            params = [
                {"field": "model_id", "type": "str=", "value": model_id},
            ]
            if self.filter_collect_task:
                params.append({"field": "collect_task", "type": "str=", "value": self.task_id})

            with GraphClient() as ag:
                conflicts = []
                if self.reconcile_task_assets:
                    already_data, metrics, conflicts = self._query_task_assets(ag, model_id, metrics)
                else:
                    already_data, _ = ag.query_entity(INSTANCE, params)
                management = Management(
                    self.organization,
                    self.inst_name,
                    model_id,
                    already_data,
                    metrics,
                    ["inst_name"],
                    self.now_time,
                    self.task_id,
                    collect_plugin=(self.collect_plugin_instance or self.collect_plugin),
                    data_cleanup_strategy=self.data_cleanup_strategy,
                    reconcile_task_assets=self.reconcile_task_assets,
                )
                if self.manual:
                    self.add_list.extend(management.add_list)
                    self.delete_list.extend(management.delete_list)
                    # 只更新数据 对于删除创建的数据不做处理
                    collect_result = management.update()
                else:
                    collect_result = management.controller()
                collect_result["update"]["failed"].extend(conflicts)
                result[model_id] = collect_result
        result["__raw_data__"] = self.raw_data
        result["all"] = all_count
        return result

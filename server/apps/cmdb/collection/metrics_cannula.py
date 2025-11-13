from datetime import datetime, timezone
from typing import Type

from apps.cmdb.collection.common import Management
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient


# 指标纳管（纳管控制器）
class MetricsCannula:
    def __init__(self, inst_id, organization: list, inst_name: str, task_id: int, collect_plugin: Type,
                 manual: bool = False, default_metrics: dict = None, filter_collect_task=True):
        self.inst_id = inst_id
        self.organization = organization
        self.task_id = str(task_id)
        self.manual = False if default_metrics else manual  # 是否手动
        self.inst_name = inst_name
        self.collect_plugin = collect_plugin
        self.filter_collect_task = filter_collect_task
        self.collect_data = {}  # 采集后的原始数据
        self.collect_params = {}
        self.collection_metrics = default_metrics or self.get_collection_metrics()
        self.now_time = datetime.now(timezone.utc).isoformat()
        self.add_list = []
        self.update_list = []
        self.delete_list = []
        self.assos_list = []

    def get_collection_metrics(self):
        """获取采集指标"""
        new_metrics = self.collect_plugin(self.inst_name, self.inst_id, self.task_id)
        result = new_metrics.run()
        self.collect_data = new_metrics.result
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

    def collect_controller(self) -> dict:
        result = {}
        for model_id, metrics in self.collection_metrics.items():
            params = [
                {"field": "model_id", "type": "str=", "value": model_id},
            ]
            if self.filter_collect_task:
                params.append({"field": "collect_task", "type": "str=", "value": self.task_id})

            with GraphClient() as ag:
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
                    collect_plugin=self.collect_plugin
                )
                if self.manual:
                    self.add_list.extend(management.add_list)
                    self.delete_list.extend(management.delete_list)
                    # 只更新数据 对于删除创建的数据不做处理
                    collect_result = management.update()
                else:
                    collect_result = management.controller()

                result[model_id] = collect_result

        return result


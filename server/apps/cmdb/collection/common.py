from dotenv import load_dotenv

from apps.cmdb.collect.extensions import get_collect_enterprise_extension
from apps.cmdb.collection.change_records import write_collect_instance_change_records
from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION, DataCleanupStrategy
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException

load_dotenv()


class Management:
    def __init__(
        self,
        organization,
        inst_name,
        model_id,
        old_data,
        new_data,
        unique_keys,
        collect_time,
        task_id,
        collect_plugin=None,
        data_cleanup_strategy=None,
    ):
        self.organization = organization
        self.collect_time = collect_time
        self.collect_plugin = collect_plugin
        self.inst_name = inst_name
        self.model_id = model_id
        self.old_data = old_data
        self.new_data = new_data
        self.unique_keys = unique_keys
        self.check_attr_map = self.get_check_attr_map()
        self.task_id = task_id
        self.data_cleanup_strategy = data_cleanup_strategy or DataCleanupStrategy.NO_CLEANUP
        self.old_map, self.new_map = self.format_data()
        self.add_list, self.update_list, self.delete_list = self.contrast(self.old_map, self.new_map)

    def get_check_attr_map(self):
        attrs = ModelManage.search_model_attr(self.model_id)
        check_attr_map = dict(is_only={}, is_required={}, editable={})
        for attr in attrs:
            if attr.get("is_only", False):
                check_attr_map["is_only"][attr["attr_id"]] = attr["attr_name"]
            if attr.get("is_required", False):
                check_attr_map["is_required"][attr["attr_id"]] = attr["attr_name"]
            if attr.get("editable", True):
                check_attr_map["editable"][attr["attr_id"]] = attr["attr_name"]

        return check_attr_map

    def format_data(self):
        """数据格式化"""
        old_map, new_map = {}, {}
        for info in self.old_data:
            key = tuple(info[key] for key in self.unique_keys)
            old_map[key] = info
        for info in self.new_data:
            key = tuple(info[key] for key in self.unique_keys)
            new_map[key] = info
        return old_map, new_map

    def contrast(self, old_map, new_map):
        add_list, update_list, delete_list = [], [], []
        for key, info in new_map.items():
            info["model_id"] = self.model_id
            if key not in old_map:
                add_list.append(info)
            else:
                info.update(_id=old_map[key]["_id"])
                update_list.append(info)

        should_delete = (
            self.data_cleanup_strategy == DataCleanupStrategy.IMMEDIATELY and getattr(self.collect_plugin, "_MODEL_ID", None) is not None and new_map
        )

        if should_delete:
            for key, info in old_map.items():
                info["model_id"] = self.model_id
                if key not in new_map:
                    delete_list.append(info)

        return add_list, update_list, delete_list

    def _query_existing_unique_candidates(self, ag, inst_list):
        unique_fields = list(self.check_attr_map.get("is_only", {}).keys())
        if not unique_fields:
            return []

        exist_items = []
        seen_ids = set()
        base_params = [{"field": "model_id", "type": "str=", "value": self.model_id}]

        for field in unique_fields:
            values = []
            seen_values = set()
            for instance_info in inst_list:
                value = instance_info.get(field)
                if value in (None, "") or value in seen_values:
                    continue
                seen_values.add(value)
                values.append(value)

            if not values:
                continue

            for params in self._build_unique_candidate_params(base_params, field, values):
                items, _ = ag.query_entity(INSTANCE, params)
                for item in items:
                    item_id = item.get("_id")
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                    exist_items.append(item)

        return exist_items

    @staticmethod
    def _build_unique_candidate_params(base_params, field, values):
        if all(isinstance(value, bool) for value in values):
            return [base_params + [{"field": field, "type": "bool", "value": value}] for value in values]
        if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
            return [base_params + [{"field": field, "type": "int[]", "value": values}]]
        return [base_params + [{"field": field, "type": "str[]", "value": values}]]

    def add_inst(self, inst_list):
        """新增实例"""
        result = {"success": [], "failed": []}
        if not inst_list:
            return result

        with GraphClient() as ag:
            exist_items = self._query_existing_unique_candidates(ag, inst_list)
            for instance_info in inst_list:
                assos = instance_info.pop("assos", [])
                try:
                    instance_info.update(
                        model_id=self.model_id,
                        organization=self.organization,
                        collect_task=self.task_id,
                        auto_collect=True,
                        collect_time=self.collect_time,
                    )
                    entity = ag.create_entity(INSTANCE, instance_info, self.check_attr_map, exist_items)
                    # 创建关联
                    assos_result = self.setting_assos(entity, assos)
                    exist_items.append(entity)
                    result["success"].append(dict(inst_info=entity, assos_result=assos_result))
                except Exception as e:
                    result["failed"].append({"instance_info": instance_info, "error": getattr(e, "message", e)})

        from apps.cmdb.services.auto_relation_reconcile import schedule_instance_auto_relation_reconcile

        schedule_instance_auto_relation_reconcile([item["inst_info"]["_id"] for item in result["success"]])

        return result

    def update_inst(self, inst_list):
        """更新实例"""
        result = {"success": [], "failed": []}
        if not inst_list:
            return result

        with GraphClient() as ag:
            exist_items = self._query_existing_unique_candidates(ag, inst_list)
            for instance_info in inst_list:
                try:
                    instance_info.update(
                        model_id=self.model_id,
                        organization=self.organization,
                        collect_task=self.task_id,
                        auto_collect=True,
                        collect_time=self.collect_time,
                    )
                    assos = instance_info.pop("assos", [])
                    exist_items = [i for i in exist_items if i["_id"] != instance_info["_id"]]
                    entity = ag.set_entity_properties(INSTANCE, [instance_info["_id"]], instance_info, self.check_attr_map, exist_items)
                    # 更新关联
                    assos_result = self.setting_assos(dict(model_id=self.model_id, _id=entity[0]["_id"], inst_name=entity[0]["inst_name"]), assos)
                    exist_items.append(entity[0])
                    result["success"].append(dict(inst_info=entity[0], assos_result=assos_result))
                except Exception as e:
                    result["failed"].append({"instance_info": instance_info, "error": getattr(e, "message", e)})

        from apps.cmdb.services.auto_relation_reconcile import schedule_instance_auto_relation_reconcile

        schedule_instance_auto_relation_reconcile([item["inst_info"]["_id"] for item in result["success"]])
        return result

    @staticmethod
    def delete_inst(inst_list):
        """删除实例"""

        result = {"success": [], "failed": []}

        if not inst_list:
            return result

        with GraphClient() as ag:
            for instance_info in inst_list:
                try:
                    ag.detach_delete_entity(INSTANCE, instance_info["_id"])
                    result["success"].append(instance_info)
                except Exception as e:
                    result["failed"].append({"instance_info": instance_info, "error": getattr(e, "message", e)})

        from apps.cmdb.services.auto_relation_reconcile import schedule_incoming_rule_full_sync_by_model_ids

        schedule_incoming_rule_full_sync_by_model_ids([item["model_id"] for item in result["success"]])
        return result

    def set_asso_info(self, dst_id, src_info, dst_info):
        """设置关联信息"""
        asso_info = dict(
            model_asst_id=dst_info["model_asst_id"],
            src_model_id=src_info["model_id"],
            src_inst_id=src_info["_id"],
            dst_model_id=dst_info["model_id"],
            dst_inst_id=dst_id,
            asst_id=dst_info["asst_id"],
        )
        return asso_info

    def setting_assos(self, src_info, dst_list):
        """设置关联关系"""
        assos_result = {"success": [], "failed": []}
        for dst_info in dst_list:
            dst_id = None
            try:
                with GraphClient() as ag:
                    dst_entity, _ = ag.query_entity(
                        INSTANCE,
                        [
                            {"field": "model_id", "type": "str=", "value": dst_info["model_id"]},
                            {"field": "inst_name", "type": "str=", "value": dst_info["inst_name"]},
                        ],
                    )
                    if not dst_entity:
                        raise BaseAppException(f"target instance {dst_info['model_id']}:{dst_info['inst_name']} not found")

                    dst_id = dst_entity[0]["_id"]
                    asso_info = self.set_asso_info(dst_id, src_info, dst_info)
                    ag.create_edge(INSTANCE_ASSOCIATION, src_info["_id"], INSTANCE, dst_id, INSTANCE, asso_info, "model_asst_id")
                    asso_info["src_inst_name"] = src_info["inst_name"]
                    asso_info["dst_inst_name"] = dst_info["inst_name"]
                    assos_result["success"].append(asso_info)
            except Exception as e:
                error_message = str(getattr(e, "message", e))
                asso_info = self.set_asso_info(dst_id, src_info, dst_info)
                asso_info["src_inst_name"] = src_info["inst_name"]
                asso_info["dst_inst_name"] = dst_info["inst_name"]
                # 关联边已存在即为目标状态，幂等视为成功，避免重复采集把"已存在的关联"误报为失败
                if error_message == "edge already exists":
                    assos_result["success"].append(asso_info)
                    continue
                asso_info.update({"src_info": src_info, "dst_info": dst_info, "error": error_message})
                assos_result["failed"].append(asso_info)
        return assos_result

    def update(self):
        update_result = self.update_inst(self.update_list)
        result = dict(add={"success": [], "failed": []}, update=update_result, delete={"success": [], "failed": []})
        self._after_instances_applied(result)
        return result

    def controller(self):
        delete_result = self.delete_inst(self.delete_list)
        add_result = self.add_inst(self.add_list)
        update_result = self.update_inst(self.update_list)
        result = dict(add=add_result, update=update_result, delete=delete_result)
        self._after_instances_applied(result)
        return result

    def _after_instances_applied(self, result):
        write_collect_instance_change_records(self, result)
        get_collect_enterprise_extension().on_collect_instances_applied(management=self, result=result)

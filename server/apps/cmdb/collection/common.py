from dotenv import load_dotenv

from apps.cmdb.collect.extensions import get_collect_enterprise_extension
from apps.cmdb.collection.change_records import write_collect_instance_change_records
from apps.cmdb.collection.cleanup import cleanup_due, is_collection_target, snapshot_allows_cleanup
from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION, DataCleanupStrategy
from apps.cmdb.constants.field_constraints import TAG_ATTR_ID
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.instance_identity import prepare_new_instance_identity
from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException

load_dotenv()


class Management:
    # 这些字段仅反映采集运行状态，不应触发审计和关联重算。
    RUNTIME_FIELDS = {
        "assos",
        "model_id",
        "organization",
        "collect_task",
        "auto_collect",
        "collect_time",
    }

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
        reconcile_task_assets=False,
        expire_days=0,
        collection_targets=(),
        reconcile=None,
    ):
        self.reconcile = reconcile
        self.reconcile_stats = {"skipped_fields": 0, "org_conflicts": 0, "outside_owner_conflicts": 0, "concurrent_abandons": 0}
        self.organization = organization
        self.collect_time = collect_time
        self.collect_plugin = collect_plugin
        self.inst_name = inst_name
        self.model_id = model_id
        self.old_data = old_data
        self.reconcile_task_assets = reconcile_task_assets
        self.expire_days = expire_days
        self.collection_targets = collection_targets
        self.existing_organizations = {row["_id"]: row.get("organization", []) for row in old_data} if reconcile_task_assets else {}
        self.new_data = new_data
        self.unique_keys = unique_keys
        self.check_attr_map = self.get_check_attr_map()
        self.task_id = task_id
        self.data_cleanup_strategy = data_cleanup_strategy or DataCleanupStrategy.NO_CLEANUP
        self.old_map, self.new_map = self.format_data()
        self.add_list, self.update_list, self.heartbeat_list, self.delete_list = self.contrast(self.old_map, self.new_map)

    def get_check_attr_map(self):
        from apps.cmdb.services.module_ingest import is_unique_identity_attr

        attrs = ModelManage.search_model_attr(self.model_id)
        check_attr_map = dict(is_only={}, is_required={}, editable={})
        for attr in attrs:
            if is_unique_identity_attr(attr):
                check_attr_map["is_only"][attr["attr_id"]] = attr["attr_name"]
            if attr.get("is_required", False):
                check_attr_map["is_required"][attr["attr_id"]] = attr["attr_name"]
            if attr.get("editable", True):
                check_attr_map["editable"][attr["attr_id"]] = attr["attr_name"]

        if self.reconcile_task_assets and self.model_id == "vmware_vc":
            # 内部来源标记随根实例保留，换任务后仍可定位原根；不作为用户模型字段暴露。
            from apps.cmdb.services.vmware_collection_scope import VmwareCollectionScope

            check_attr_map["editable"][VmwareCollectionScope.SOURCE_FIELD] = "vCenter 采集来源"
        if self.reconcile:
            from apps.cmdb.collection.field_reconcile import COLLECT_SOURCES_ATTR

            for field in ("collect_task", "organization", "collect_time", "auto_collect", COLLECT_SOURCES_ATTR):
                check_attr_map["editable"].setdefault(field, field)

        return check_attr_map

    @staticmethod
    def coerce_collected_tag(instance_info: dict) -> dict:
        """采集写入的 tag 必须是列表。空串/字符串会让图查询 Type mismatch。"""
        if not isinstance(instance_info, dict) or TAG_ATTR_ID not in instance_info:
            return instance_info
        value = instance_info[TAG_ATTR_ID]
        if isinstance(value, list):
            return instance_info
        cleaned = dict(instance_info)
        cleaned[TAG_ATTR_ID] = []
        return cleaned

    def format_data(self):
        """数据格式化"""
        old_map, new_map = {}, {}
        for info in self.old_data:
            key = tuple(info[key] for key in self.unique_keys)
            old_map[key] = info
        for info in self.new_data:
            key = tuple(info[key] for key in self.unique_keys)
            new_map[key] = self.coerce_collected_tag(info)
        return old_map, new_map

    @classmethod
    def has_business_changes(cls, old_info, new_info):
        if new_info.get("assos"):
            return True
        for field, new_value in new_info.items():
            if field in cls.RUNTIME_FIELDS or field.startswith("_"):
                continue
            if old_info.get(field) != new_value:
                return True
        return False

    def contrast(self, old_map, new_map):
        if self.reconcile:
            return self._contrast_reconcile(old_map, new_map)
        add_list, update_list, heartbeat_list, delete_list = [], [], [], []
        for key, info in new_map.items():
            info["model_id"] = self.model_id
            if key not in old_map:
                add_list.append(info)
            else:
                info.update(_id=old_map[key]["_id"])
                if self.reconcile_task_assets and "inst_uuid" in old_map[key]:
                    info["inst_uuid"] = old_map[key]["inst_uuid"]
                if self.has_business_changes(old_map[key], info):
                    update_list.append(info)
                else:
                    heartbeat_list.append(info)

        if snapshot_allows_cleanup(self.collect_plugin, self.model_id):
            for key, info in old_map.items():
                info["model_id"] = self.model_id
                if (
                    key not in new_map
                    and str(info.get("collect_task")) == str(self.task_id)
                    and not is_collection_target(info, self.collection_targets)
                    and cleanup_due(self.data_cleanup_strategy, info.get("collect_time"), self.collect_time, self.expire_days)
                ):
                    delete_list.append(info)

        return add_list, update_list, heartbeat_list, delete_list

    def _contrast_reconcile(self, old_map, new_map):
        from apps.cmdb.collection.field_reconcile import (
            COLLECT_SOURCES_ATTR,
            ORG_CONFLICT,
            OUTSIDE_CONFLICT,
            other_member_still_sees,
            plan_collected_instance,
            plan_create,
        )

        add_list, update_list, heartbeat_list, delete_list = [], [], [], []
        ctx = self.reconcile
        for key, info in new_map.items():
            info = dict(info)
            info["model_id"] = self.model_id
            info["_task_organizations"] = self.organization
            if key not in old_map:
                created = plan_create(info, self.task_id, self.collect_time)
                info[COLLECT_SOURCES_ATTR] = created["sources_json"]
                info.pop("_task_organizations", None)
                add_list.append(info)
                continue
            old = old_map[key]
            plan = plan_collected_instance(
                old=old,
                incoming=info,
                task_id=self.task_id,
                member_order=ctx["member_order"],
                field_orders=ctx.get("field_orders") or {},
                now=self.collect_time,
                stale_days=ctx.get("stale_days", 7),
            )
            self.reconcile_stats["skipped_fields"] += plan.get("skipped_fields") or 0
            if plan.get("conflict") == OUTSIDE_CONFLICT:
                self.reconcile_stats["outside_owner_conflicts"] += 1
                self.reconcile_stats.setdefault("conflicts", []).append(
                    {"instance_info": {"model_id": self.model_id, "inst_name": old.get("inst_name")}, "error": OUTSIDE_CONFLICT}
                )
                continue
            if plan.get("conflict") == ORG_CONFLICT:
                self.reconcile_stats["org_conflicts"] += 1
                self.reconcile_stats.setdefault("conflicts", []).append(
                    {"instance_info": {"model_id": self.model_id, "inst_name": old.get("inst_name")}, "error": ORG_CONFLICT}
                )
                continue
            payload = {
                "_id": old["_id"],
                "inst_name": old.get("inst_name"),
                "model_id": self.model_id,
                "collect_task": plan["collect_task"],
                "collect_time": self.collect_time if plan["refresh_collect_time"] else old.get("collect_time"),
                "organization": old.get("organization", self.organization),
                "auto_collect": True,
                COLLECT_SOURCES_ATTR: plan["sources_json"],
                "_expected_collect_sources": old.get(COLLECT_SOURCES_ATTR),
                "suppress_change_record": plan["suppress_change_record"],
            }
            if old.get("inst_uuid"):
                payload["inst_uuid"] = old["inst_uuid"]
            payload.update(plan["properties"])
            payload["_incoming"] = {key: value for key, value in info.items() if key not in {"_task_organizations"} and not str(key).startswith("_")}
            if plan["properties"]:
                update_list.append(payload)
            else:
                heartbeat_list.append(payload)

        if snapshot_allows_cleanup(self.collect_plugin, self.model_id):
            for key, info in old_map.items():
                if key in new_map or str(info.get("collect_task")) != str(self.task_id):
                    continue
                if is_collection_target(info, self.collection_targets):
                    continue
                if not cleanup_due(self.data_cleanup_strategy, info.get("collect_time"), self.collect_time, self.expire_days):
                    continue
                if other_member_still_sees(
                    info.get("collect_task"),
                    info.get(COLLECT_SOURCES_ATTR),
                    ctx["member_order"],
                    self.collect_time,
                    ctx.get("stale_days", 7),
                ):
                    continue
                info["model_id"] = self.model_id
                delete_list.append(info)
        return add_list, update_list, heartbeat_list, delete_list

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
                instance_info = self.coerce_collected_tag(instance_info)
                assos = instance_info.pop("assos", [])
                try:
                    instance_info.update(
                        model_id=self.model_id,
                        organization=self.organization,
                        collect_task=self.task_id,
                        auto_collect=True,
                        collect_time=self.collect_time,
                    )
                    instance_info = prepare_new_instance_identity(instance_info)
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
                instance_info = self.coerce_collected_tag(instance_info)
                try:
                    if self.reconcile:
                        instance_info.update(
                            model_id=self.model_id,
                            organization=self.existing_organizations.get(instance_info["_id"], instance_info.get("organization", self.organization)),
                            auto_collect=True,
                        )
                    else:
                        instance_info.update(
                            model_id=self.model_id,
                            organization=self.existing_organizations.get(instance_info["_id"], self.organization),
                            collect_task=self.task_id,
                            auto_collect=True,
                            collect_time=self.collect_time,
                        )
                    assos = instance_info.pop("assos", [])
                    exist_items = [i for i in exist_items if i["_id"] != instance_info["_id"]]
                    suppress = bool(instance_info.get("suppress_change_record"))
                    entity = self._set_collected_properties(ag, instance_info, exist_items)
                    if not entity:
                        self.reconcile_stats["concurrent_abandons"] += 1
                        continue
                    # 更新关联
                    assos_result = self.setting_assos(dict(model_id=self.model_id, _id=entity[0]["_id"], inst_name=entity[0]["inst_name"]), assos)
                    exist_items.append(entity[0])
                    result["success"].append(dict(inst_info=entity[0], assos_result=assos_result, suppress_change_record=suppress))
                except Exception as e:
                    result["failed"].append({"instance_info": instance_info, "error": getattr(e, "message", e)})

        from apps.cmdb.services.auto_relation_reconcile import schedule_instance_auto_relation_reconcile

        schedule_instance_auto_relation_reconcile([item["inst_info"]["_id"] for item in result["success"]])
        return result

    def _set_collected_properties(self, ag, instance_info, exist_items):
        from apps.cmdb.collection.field_reconcile import COLLECT_SOURCES_ATTR, plan_collected_instance

        incoming = instance_info.pop("_incoming", None)
        expected = instance_info.pop("_expected_collect_sources", None)
        instance_info.pop("suppress_change_record", None)
        conditional = self.reconcile and hasattr(ag, "set_entity_properties_if_sources")

        def write(payload, expected_sources):
            if conditional:
                return ag.set_entity_properties_if_sources(
                    INSTANCE,
                    [payload["_id"]],
                    payload,
                    self.check_attr_map,
                    exist_items,
                    expected_sources,
                )
            return ag.set_entity_properties(INSTANCE, [payload["_id"]], payload, self.check_attr_map, exist_items)

        entity = write(instance_info, expected)
        if entity or not conditional or incoming is None:
            return entity
        fresh_rows, _count = ag.query_entity(INSTANCE, [{"field": "_id", "type": "int=", "value": instance_info["_id"]}])
        fresh = fresh_rows[0] if fresh_rows else None
        if not fresh:
            return None
        plan = plan_collected_instance(
            old=fresh,
            incoming=incoming,
            task_id=self.task_id,
            member_order=self.reconcile["member_order"],
            field_orders=self.reconcile.get("field_orders") or {},
            now=self.collect_time,
            stale_days=self.reconcile.get("stale_days", 7),
        )
        if plan.get("conflict"):
            return None
        retried = {
            "_id": fresh["_id"],
            "inst_name": fresh.get("inst_name"),
            "model_id": self.model_id,
            "collect_task": plan["collect_task"],
            "collect_time": self.collect_time if plan["refresh_collect_time"] else fresh.get("collect_time"),
            "organization": fresh.get("organization", self.organization),
            "auto_collect": True,
            COLLECT_SOURCES_ATTR: plan["sources_json"],
        }
        retried.update(plan["properties"])
        return write(retried, fresh.get(COLLECT_SOURCES_ATTR))

    def refresh_heartbeat(self, inst_list):
        """仅刷新采集运行元数据，不触发关联、审计或自动关联。"""
        result = {"success": [], "failed": []}
        if not inst_list:
            return result

        heartbeat_infos = []
        for instance_info in inst_list:
            payload = {
                "_id": instance_info["_id"],
                "model_id": self.model_id,
                "organization": self.existing_organizations.get(instance_info["_id"], self.organization),
                "collect_task": instance_info.get("collect_task", self.task_id) if self.reconcile else self.task_id,
                "auto_collect": True,
                "collect_time": instance_info.get("collect_time", self.collect_time) if self.reconcile else self.collect_time,
            }
            if self.reconcile and "_collect_sources" in instance_info:
                payload["_collect_sources"] = instance_info["_collect_sources"]
                payload["_expected_collect_sources"] = instance_info.get("_expected_collect_sources")
                payload["suppress_change_record"] = instance_info.get("suppress_change_record", False)
            heartbeat_infos.append(payload)
        with GraphClient() as ag:
            exist_items = self._query_existing_unique_candidates(ag, heartbeat_infos)
            for heartbeat_info in heartbeat_infos:
                try:
                    current_items = [item for item in exist_items if item["_id"] != heartbeat_info["_id"]]
                    suppress = bool(heartbeat_info.get("suppress_change_record"))
                    entity = self._set_collected_properties(ag, heartbeat_info, current_items)
                    if not entity:
                        self.reconcile_stats["concurrent_abandons"] += 1
                        continue
                    result["success"].append({"inst_info": entity[0], "assos_result": {}, "heartbeat": True, "suppress_change_record": suppress})
                except Exception as e:
                    result["failed"].append(
                        {
                            "instance_info": heartbeat_info,
                            "error": getattr(e, "message", e),
                            "heartbeat": True,
                        }
                    )
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
                    if ag.delete_entity_if_unchanged(INSTANCE, instance_info):
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

    @staticmethod
    def _association_endpoints(current_info, listed_info, listed_id):
        """按 model_asst_id 决定图边 src/dst。

        assos 挂在当前落库实体上，listed 是对端。model_asst_id 编码为
        ``{src_model}_{asst}_{dst_model}``，与机柜布局 contains
        （rack_contains_switch：src=容器 dst=设备）以及 belong/run
        （vm_run_host：src=当前 dst=对端）一致。

        contains 如 physcial_server_contains_nic：listed(parent) → current(nic)。
        belong/run 如 vm_run_host：current → listed。无法从 model_asst_id
        判向时保持 current → listed，兼容历史自定义 asst id。
        """
        model_asst_id = listed_info.get("model_asst_id") or ""
        asst_id = listed_info.get("asst_id") or ""
        current_model = current_info.get("model_id") or ""
        listed_model = listed_info.get("model_id") or ""
        listed_as_src_key = f"{listed_model}_{asst_id}_{current_model}"

        if asst_id and model_asst_id == listed_as_src_key:
            src_info = {
                "model_id": listed_model,
                "_id": listed_id,
                "inst_name": listed_info.get("inst_name"),
            }
            dst_info = {
                "model_id": current_model,
                "model_asst_id": model_asst_id,
                "asst_id": asst_id,
                "inst_name": current_info.get("inst_name"),
            }
            return src_info, current_info["_id"], dst_info

        return current_info, listed_id, listed_info

    def setting_assos(self, src_info, dst_list):
        """设置关联关系。src_info 是当前落库实体，dst_list 是其对端 assos。"""
        current_info = src_info
        assos_result = {"success": [], "failed": []}
        for listed_info in dst_list:
            edge_src = current_info
            edge_dst_id = None
            edge_dst_info = listed_info
            try:
                with GraphClient() as ag:
                    listed_entity, _ = ag.query_entity(
                        INSTANCE,
                        [
                            {"field": "model_id", "type": "str=", "value": listed_info["model_id"]},
                            {"field": "inst_name", "type": "str=", "value": listed_info["inst_name"]},
                        ],
                    )
                    if not listed_entity:
                        raise BaseAppException(f"target instance {listed_info['model_id']}:{listed_info['inst_name']} not found")

                    listed_id = listed_entity[0]["_id"]
                    edge_src, edge_dst_id, edge_dst_info = self._association_endpoints(current_info, listed_info, listed_id)
                    asso_info = self.set_asso_info(edge_dst_id, edge_src, edge_dst_info)
                    ag.create_edge(
                        INSTANCE_ASSOCIATION,
                        edge_src["_id"],
                        INSTANCE,
                        edge_dst_id,
                        INSTANCE,
                        asso_info,
                        "model_asst_id",
                    )
                    asso_info["src_inst_name"] = edge_src["inst_name"]
                    asso_info["dst_inst_name"] = edge_dst_info["inst_name"]
                    assos_result["success"].append(asso_info)
            except Exception as e:
                error_message = str(getattr(e, "message", e))
                asso_info = self.set_asso_info(edge_dst_id, edge_src, edge_dst_info)
                asso_info["src_inst_name"] = edge_src.get("inst_name")
                asso_info["dst_inst_name"] = edge_dst_info.get("inst_name")
                # 关联边已存在即为目标状态，幂等视为成功，避免重复采集把"已存在的关联"误报为失败
                if error_message == "edge already exists":
                    assos_result["success"].append(asso_info)
                    continue
                asso_info.update({"src_info": current_info, "dst_info": listed_info, "error": error_message})
                assos_result["failed"].append(asso_info)
        return assos_result

    def update(self):
        update_result = self.update_inst(self.update_list)
        heartbeat_result = self.refresh_heartbeat(self.heartbeat_list)
        update_result["success"].extend(heartbeat_result["success"])
        update_result["failed"].extend(heartbeat_result["failed"])
        result = dict(add={"success": [], "failed": []}, update=update_result, delete={"success": [], "failed": []})
        self._after_instances_applied(result)
        return self._attach_reconcile_stats(result)

    def controller(self):
        add_result = self.add_inst(self.add_list)
        update_result = self.update_inst(self.update_list)
        heartbeat_result = self.refresh_heartbeat(self.heartbeat_list)
        update_result["success"].extend(heartbeat_result["success"])
        update_result["failed"].extend(heartbeat_result["failed"])
        delete_result = {"success": [], "failed": []}
        if not add_result["failed"] and not update_result["failed"]:
            delete_result = self.delete_inst(self.delete_list)
        result = dict(add=add_result, update=update_result, delete=delete_result)
        self._after_instances_applied(result)
        return self._attach_reconcile_stats(result)

    def _attach_reconcile_stats(self, result):
        if not self.reconcile:
            return result
        conflicts = self.reconcile_stats.get("conflicts") or []
        if conflicts:
            result["update"]["failed"].extend(conflicts)
        result["reconcile_stats"] = {key: value for key, value in self.reconcile_stats.items() if key != "conflicts"}
        return result

    def _after_instances_applied(self, result):
        # 心跳更新已落图，但不属于业务变更。
        business_result = {
            operator: {status: [item for item in items if not item.get("heartbeat")] for status, items in result.get(operator, {}).items()}
            for operator in ("add", "update", "delete")
        }
        write_collect_instance_change_records(self, business_result)
        get_collect_enterprise_extension().on_collect_instances_applied(management=self, result=business_result)

# -- coding: utf-8 --
# @File: colletc_service.py
# @Time: 2025/3/3 15:23
# @Author: windyzhao
import copy

from django.db import transaction

from apps.cmdb.constants import CollectRunStatusType, OPERATOR_COLLECT_TASK
from apps.cmdb.models import CREATE_INST, UPDATE_INST, DELETE_INST
from apps.cmdb.services.node_configs import NodeParamsFactory
from apps.cmdb.services.sync_collect import ProtocolCollect
from apps.cmdb.utils.change_record import create_change_record
from apps.core.logger import logger
from apps.core.utils.celery_utils import crontab_format, CeleryUtils
from apps.rpc.node_mgmt import NodeMgmt


class CollectModelService(object):
    TASK = "apps.cmdb.celery_tasks.sync_collect_task"
    NAME = "sync_collect_task"

    @staticmethod
    def format_params(data):
        is_interval, scan_cycle = crontab_format(data["scan_cycle"]["value_type"], data["scan_cycle"]["value"])
        not_required = ["access_point", "ip_range", "instances", "credential", "plugin_id", "params"]
        params = {
            "name": data["name"],
            "task_type": data["task_type"],
            "driver_type": data["driver_type"],
            "model_id": data["model_id"],  # 也就是id
            "timeout": data["timeout"],
            "input_method": data["input_method"],
            "is_interval": is_interval,
            "cycle_value": data["scan_cycle"]["value"],
            "cycle_value_type": data["scan_cycle"]["value_type"],
        }

        for key in not_required:
            if data.get(key):
                params[key] = data[key]

        if is_interval and scan_cycle:
            params["scan_cycle"] = scan_cycle

        return params, is_interval, scan_cycle

    @staticmethod
    def push_butch_node_params(instance):
        """
        格式化调用node的参数 并推送
        """
        node = NodeParamsFactory.get_node_params(instance)
        node_params = node.main()
        logger.info(f"推送节点参数: {node_params}")
        node_mgmt = NodeMgmt()
        result = node_mgmt.batch_setting_node_child_config(node_params)
        logger.info(f"推送节点参数结果: {result}")

    @staticmethod
    def delete_butch_node_params(instance):
        """
        格式化调用node的参数 并删除
        """
        node = NodeParamsFactory.get_node_params(instance)
        node_params = node.main(operator="delete")
        logger.info(f"删除节点参数: {node_params}")
        node_mgmt = NodeMgmt()
        result = node_mgmt.delete_instance_child_config(node_params)
        logger.info(f"删除节点参数结果: {result}")

    @classmethod
    def create(cls, request, view_self):
        create_data, is_interval, scan_cycle = cls.format_params(request.data)

        with transaction.atomic():
            serializer = view_self.get_serializer(data=create_data)
            serializer.is_valid(raise_exception=True)
            view_self.perform_create(serializer)
            instance = serializer.instance

            # 更新定时任务
            if is_interval:
                task_name = f"{cls.NAME}_{instance.id}"
                CeleryUtils.create_or_update_periodic_task(name=task_name, crontab=scan_cycle, args=[instance.id],
                                                           task=cls.TASK)

            if not instance.is_k8s:
                cls.push_butch_node_params(instance)

            create_change_record(operator=request.user.username, model_id=instance.model_id, label="采集任务",
                                 _type=CREATE_INST, message=f"创建采集任务. 任务名称: {instance.name}",
                                 inst_id=instance.id, model_object=OPERATOR_COLLECT_TASK)

        return instance.id

    @classmethod
    def update(cls, request, view_self):
        update_data, is_interval, scan_cycle = cls.format_params(request.data)
        with transaction.atomic():
            instance = view_self.get_object()
            old_instance = copy.deepcopy(instance)
            serializer = view_self.get_serializer(instance, data=update_data, partial=True)
            serializer.is_valid(raise_exception=True)
            view_self.perform_update(serializer)

            task_name = f"{cls.NAME}_{instance.id}"
            # 更新定时任务
            if is_interval:
                CeleryUtils.create_or_update_periodic_task(name=task_name, crontab=scan_cycle,
                                                           args=[instance.id], task=cls.TASK)
            else:
                CeleryUtils.delete_periodic_task(task_name)

            if not instance.is_k8s:
                cls.delete_butch_node_params(old_instance)
                cls.push_butch_node_params(instance)

            create_change_record(operator=request.user.username, model_id=instance.model_id, label="采集任务",
                                 _type=UPDATE_INST, message=f"修改采集任务. 任务名称: {instance.name}",
                                 inst_id=instance.id, model_object=OPERATOR_COLLECT_TASK)

        return instance.id

    @classmethod
    def destroy(cls, request, view_self):
        instance = view_self.get_object()
        instance_id = instance.id
        instance_name = instance.name
        model_id = instance.model_id
        if not instance.is_k8s:
            cls.delete_butch_node_params(instance)
        task_name = f"{cls.NAME}_{instance_id}"
        CeleryUtils.delete_periodic_task(task_name)
        instance.delete()
        create_change_record(operator=request.user.username, model_id=model_id, label="采集任务",
                             _type=DELETE_INST, message=f"删除采集任务. 任务名称: {instance_name}",
                             inst_id=instance_id, model_object=OPERATOR_COLLECT_TASK)
        return instance_id

    @classmethod
    def collect_controller(cls, instance, data) -> dict:
        """
        任务审批，和数据纳管的逻辑保持一致即可
        """

        try:
            result, format_data = ProtocolCollect(instance, data)
            instance.exec_status = CollectRunStatusType.SUCCESS
        except Exception as err:
            import traceback
            logger.error("==任务审批采集失败== task_id={}, error={}".format(instance.id, traceback.format_exc()))
            result = {}
            format_data = {}
            instance.exec_status = CollectRunStatusType.ERROR

        instance.examine = True
        instance.collect_data = result
        instance.format_data = format_data

        instance.collect_digest = {
            "add": len(format_data.get("add", [])),
            "update": len(format_data.get("update", [])),
            "delete": len(format_data.get("delete", [])),
            "association": len(format_data.get("association", [])),
        }
        instance.save()

        return result

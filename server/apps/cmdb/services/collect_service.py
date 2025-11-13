# -- coding: utf-8 --
# @File: colletc_service.py
# @Time: 2025/3/3 15:23
# @Author: windyzhao
import copy

from django.conf import settings
from django.db import transaction
from django.utils.timezone import now

from apps.cmdb.constants.constants import CollectRunStatusType, OPERATOR_COLLECT_TASK
from apps.cmdb.models import CREATE_INST, UPDATE_INST, DELETE_INST, EXECUTE
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.collect_tasks.protocol_collect import ProtocolCollect
from apps.cmdb.utils.change_record import create_change_record
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.celery_utils import crontab_format, CeleryUtils
from apps.core.utils.web_utils import WebUtils
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.stargazer import Stargazer
from apps.cmdb.tasks.celery_tasks import sync_collect_task


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
        result = node_mgmt.batch_add_node_child_config(node_params)
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
        result = node_mgmt.delete_child_configs(node_params)
        logger.info(f"删除节点参数结果: {result}")

    @classmethod
    def create(cls, request, view_self):
        create_data, is_interval, scan_cycle = cls.format_params(request.data)

        # 使用数据库事务保证原子性：DB + 外部操作要么全成功，要么全失败
        with transaction.atomic():
            serializer = view_self.get_serializer(data=create_data)
            serializer.is_valid(raise_exception=True)
            view_self.perform_create(serializer)
            instance = serializer.instance

            # 在事务内执行外部操作，失败时会触发事务回滚
            # 虽然这会导致长事务，但保证了业务的强一致性
            try:
                # 更新定时任务
                if is_interval:
                    task_name = f"{cls.NAME}_{instance.id}"
                    CeleryUtils.create_or_update_periodic_task(name=task_name, crontab=scan_cycle, args=[instance.id],
                                                               task=cls.TASK)

                # RPC 调用：推送节点参数
                if not instance.is_k8s:
                    cls.push_butch_node_params(instance)
            except Exception as e:
                # 外部操作失败，记录详细错误日志并抛出异常，触发事务回滚
                logger.error(f"创建采集任务时外部操作失败，事务将回滚: task_name={instance.name}, error={str(e)}")
                # 重新抛出异常，让事务回滚
                raise BaseAppException(f"创建采集任务失败：{str(e)}")

            # 只有所有操作都成功，才创建变更记录
            create_change_record(operator=request.user.username, model_id=instance.model_id, label="采集任务",
                                 _type=CREATE_INST, message=f"创建采集任务. 任务名称: {instance.name}",
                                 inst_id=instance.id, model_object=OPERATOR_COLLECT_TASK)

        return instance.id

    @classmethod
    def update(cls, request, view_self):
        update_data, is_interval, scan_cycle = cls.format_params(request.data)

        # 获取旧实例数据（在事务外）
        instance = view_self.get_object()
        old_instance = copy.deepcopy(instance)

        # 使用数据库事务保证原子性
        with transaction.atomic():
            serializer = view_self.get_serializer(instance, data=update_data, partial=True)
            serializer.is_valid(raise_exception=True)
            view_self.perform_update(serializer)

            # 在事务内执行外部操作，失败时会触发事务回滚
            try:
                task_name = f"{cls.NAME}_{instance.id}"
                # 更新定时任务
                if is_interval:
                    CeleryUtils.create_or_update_periodic_task(name=task_name, crontab=scan_cycle,
                                                               args=[instance.id], task=cls.TASK)
                else:
                    CeleryUtils.delete_periodic_task(task_name)

                # RPC 调用：先删除旧节点参数，再推送新节点参数
                if not instance.is_k8s:
                    cls.delete_butch_node_params(old_instance)
                    cls.push_butch_node_params(instance)
            except Exception as e:
                # 外部操作失败，记录错误并抛出异常，触发事务回滚
                logger.error(f"更新采集任务时外部操作失败，事务将回滚: task_name={instance.name}, error={str(e)}")
                raise BaseAppException(f"更新采集任务失败：{str(e)}")

            # 只有所有操作都成功，才创建变更记录
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
        is_k8s = instance.is_k8s

        # 复制实例数据用于RPC调用
        instance_copy = copy.deepcopy(instance)

        # 使用数据库事务保证原子性
        # 注意：对于删除操作，先清理外部资源，再删除数据库记录更安全
        # 这样即使外部清理失败，数据库记录还在，可以重试
        with transaction.atomic():
            try:
                # 先清理外部资源（在事务内，失败会回滚）
                task_name = f"{cls.NAME}_{instance_id}"
                CeleryUtils.delete_periodic_task(task_name)

                # RPC 调用：删除节点参数
                if not is_k8s:
                    cls.delete_butch_node_params(instance_copy)
            except Exception as e:
                # 外部资源清理失败，记录错误并抛出异常，触发事务回滚
                logger.error(f"删除采集任务时外部资源清理失败，事务将回滚: task_name={instance_name}, error={str(e)}")
                raise BaseAppException(f"删除采集任务失败：{str(e)}")

            # 外部资源清理成功后，再删除数据库记录
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

    @classmethod
    def list_regions(cls, plugin_id, credential):
        data = {
            "plugin_name": plugin_id,
            "_timeout": 5,
            **credential
        }
        stargazer = Stargazer()
        result = stargazer.list_regions(data)

        return result

    @staticmethod
    def exec_task(instance, username):
        """
        执行任务
        """
        if instance.exec_status == CollectRunStatusType.RUNNING:
            return WebUtils.response_error(error_message="任务正在执行中!无法重复执行！", status_code=400)

        instance.exec_time = now()
        instance.exec_status = CollectRunStatusType.RUNNING
        instance.format_data = {}
        instance.collect_data = {}
        instance.collect_digest = {}
        instance.save()
        if not settings.DEBUG:
            sync_collect_task.delay(instance.id)
        else:
            sync_collect_task(instance.id)

        create_change_record(operator=username, model_id=instance.model_id, label="采集任务",
                             _type=EXECUTE, message=f"执行采集任务. 任务名称: {instance.name}",
                             inst_id=instance.id, model_object=OPERATOR_COLLECT_TASK)

        return WebUtils.response_success(instance.id)

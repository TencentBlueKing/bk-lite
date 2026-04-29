# -- coding: utf-8 --
# @File: colletc_service.py
# @Time: 2025/3/3 15:23
# @Author: windyzhao
import copy

from celery import current_app
from django.conf import settings
from django.db import transaction
from django.utils.timezone import now

from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType, OPERATOR_COLLECT_TASK, DataCleanupStrategy
from apps.cmdb.models import CREATE_INST, UPDATE_INST, DELETE_INST, EXECUTE
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.collection.collect_tasks.protocol_collect import ProtocolCollect
from apps.cmdb.utils.change_record import create_change_record
from apps.cmdb.utils.base import get_current_team_from_request
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.celery_utils import crontab_format, CeleryUtils
from apps.core.utils.web_utils import WebUtils
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.stargazer import Stargazer
from apps.cmdb.tasks.celery_tasks import sync_collect_task
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Node


class CollectModelService(object):
    TASK = "apps.cmdb.tasks.celery_tasks.sync_collect_task"
    NAME = "sync_collect_task"
    # 周期任务达到该分钟阈值时，触发一次“下发后 4 分钟补跑”
    DELAY_SYNC_THRESHOLD_MINUTES = 15
    # 延迟补跑等待时长（秒）
    DELAY_SYNC_COUNTDOWN_SECONDS = 4 * 60

    @staticmethod
    def should_sync_node_params(instance):
        return not instance.is_k8s

    @staticmethod
    def has_permission(request, instance, view_self):
        """
        检查用户是否有权限操作该实例
        """

        user = request.user
        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children", "0") == "1"
        has_permission = view_self.get_has_permission(user, instance, current_team, include_children=include_children)
        if not has_permission:
            raise BaseAppException("您没有操作该采集任务的权限！")

    @staticmethod
    def delete_team(instance_id, old_team, new_team, view_self):
        """
        删除权限规则中的组织
        主要用于更新时删除组织权限
        """
        delete_team = [i for i in old_team if i not in new_team]
        view_self.delete_rules(instance_id, delete_team)

    @staticmethod
    def format_params(data):
        not_required = ["access_point", "ip_range", "instances", "credential", "plugin_id", "params"]
        is_interval, scan_cycle = crontab_format(data["scan_cycle"]["value_type"], data["scan_cycle"]["value"])
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
            "team": data["team"],  # 把组织单独抽出来，方便权限控制
            "expire_days": data.get("expire_days", 0),
            "data_cleanup_strategy": data.get("data_cleanup_strategy", DataCleanupStrategy.NO_CLEANUP),
        }

        for key in not_required:
            if data.get(key):
                params[key] = data[key]

        if is_interval and scan_cycle:
            params["scan_cycle"] = scan_cycle

        return params, is_interval, scan_cycle

    @staticmethod
    def _get_snapshot_item(snapshot):
        if isinstance(snapshot, dict):
            return snapshot
        if isinstance(snapshot, list) and snapshot:
            item = snapshot[0]
            if isinstance(item, dict):
                return item
        return {}

    @staticmethod
    def _get_cloud_region_id_by_node(node_id):
        if node_id in (None, ""):
            return None
        node = Node.objects.filter(id=str(node_id)).only("cloud_region_id").first()
        return getattr(node, "cloud_region_id", None)

    @staticmethod
    def _get_cloud_region_name(cloud_id):
        if cloud_id in (None, ""):
            return ""
        cloud_name = CloudRegion.objects.filter(id=cloud_id).values_list("name", flat=True).first()
        return str(cloud_name or "").strip()

    @classmethod
    def _resolve_host_cloud_meta(cls, params=None, access_point=None, instances=None, prefer_access_point=False):
        params = params if isinstance(params, dict) else {}
        access_point_item = cls._get_snapshot_item(access_point)
        instance_item = cls._get_snapshot_item(instances)

        access_point_cloud = (
            access_point_item.get("cloud")
            or access_point_item.get("cloud_id")
            or access_point_item.get("cloud_region")
        )
        access_point_cloud_name = access_point_item.get("cloud_name") or access_point_item.get("cloud_region_name")

        task_cloud = params.get("cloud") or instance_item.get("cloud") or instance_item.get("cloud_id")
        task_cloud_name = params.get("cloud_name") or instance_item.get("cloud_name")

        if prefer_access_point:
            if access_point_cloud not in (None, ""):
                cloud = access_point_cloud
                cloud_name = access_point_cloud_name or ""
            else:
                cloud = task_cloud
                cloud_name = task_cloud_name
        else:
            cloud = task_cloud or access_point_cloud
            cloud_name = task_cloud_name or access_point_cloud_name

        if cloud in (None, ""):
            node_id = access_point_item.get("id") or access_point_item.get("node_id")
            cloud = cls._get_cloud_region_id_by_node(node_id)

        if not cloud_name:
            cloud_name = cls._get_cloud_region_name(cloud)

        return cloud, cloud_name

    @classmethod
    def enrich_host_cloud_snapshot_payload(cls, data):
        if not isinstance(data, dict) or data.get("task_type") != CollectPluginTypes.HOST:
            return False

        params = data.get("params")
        if not isinstance(params, dict):
            params = {}

        instances = data.get("instances")
        if not isinstance(instances, list):
            instances = []

        cloud, cloud_name = cls._resolve_host_cloud_meta(
            params=params,
            access_point=data.get("access_point"),
            instances=instances,
            prefer_access_point=True,
        )

        changed = False
        if cloud not in (None, "") and params.get("cloud") != cloud:
            params["cloud"] = cloud
            changed = True
        if cloud_name and params.get("cloud_name") != cloud_name:
            params["cloud_name"] = cloud_name
            changed = True

        for instance_item in instances:
            if not isinstance(instance_item, dict):
                continue
            if cloud not in (None, "") and instance_item.get("cloud") != cloud:
                instance_item["cloud"] = cloud
                changed = True
            if cloud_name and instance_item.get("cloud_name") != cloud_name:
                instance_item["cloud_name"] = cloud_name
                changed = True

        data["params"] = params
        data["instances"] = instances
        return changed

    @classmethod
    def repair_host_cloud_snapshot(cls, instance, persist=True):
        if not instance or not instance.is_host:
            return False

        payload = {
            "task_type": instance.task_type,
            "access_point": copy.deepcopy(instance.access_point),
            "instances": copy.deepcopy(instance.instances),
            "params": copy.deepcopy(instance.params),
        }
        changed = cls.enrich_host_cloud_snapshot_payload(payload)
        if not changed:
            cloud, cloud_name = cls._resolve_host_cloud_meta(
                params=payload["params"],
                access_point=payload["access_point"],
                instances=payload["instances"],
                prefer_access_point=False,
            )
            if cloud not in (None, "") and payload["params"].get("cloud") != cloud:
                payload["params"]["cloud"] = cloud
                changed = True
            if cloud_name and payload["params"].get("cloud_name") != cloud_name:
                payload["params"]["cloud_name"] = cloud_name
                changed = True
            for instance_item in payload["instances"]:
                if not isinstance(instance_item, dict):
                    continue
                if cloud not in (None, "") and instance_item.get("cloud") != cloud:
                    instance_item["cloud"] = cloud
                    changed = True
                if cloud_name and instance_item.get("cloud_name") != cloud_name:
                    instance_item["cloud_name"] = cloud_name
                    changed = True
            if not changed:
                return False

        instance.params = payload["params"]
        instance.instances = payload["instances"]
        if persist:
            instance.save(update_fields=["params", "instances"])
        return True

    @staticmethod
    def format_update_credential(instance, data):
        """
        格式化更新时的凭据参数
        """
        credential = data.get("credential")
        if not credential and not instance.is_k8s:
            raise BaseAppException("采集凭据不能为空！")
        if credential and "regions" in credential:
            regions = credential.pop("regions")
            if not credential:
                # 说明之修改了regions
                data["credential"] = instance.decrypt_credentials
                data["credential"]["regions"] = regions
            else:
                data["credential"]["regions"] = regions
        else:
            old_credential = instance.decrypt_credentials
            if not isinstance(old_credential, dict):
                old_credential = {}
            if credential is None:
                data["credential"] = old_credential
                return
            if not isinstance(credential, dict):
                raise BaseAppException("采集凭据格式错误！")
            old_credential.update(credential)
            data["credential"] = old_credential

    @classmethod
    def schedule_delayed_sync_if_needed(cls, instance, is_interval):
        # 仅对开启周期巡检的任务生效
        if not is_interval:
            return
        # 仅“循环分钟”类型才有明确分钟阈值；定点任务不参与补跑策略
        if instance.cycle_value_type != "cycle":
            return

        try:
            cycle_minutes = int(instance.cycle_value or 0)
        except (TypeError, ValueError):
            logger.warning(
                "采集任务周期值非法，跳过延迟补跑: task_id=%s, cycle_value=%s",
                instance.id,
                instance.cycle_value,
            )
            return

        if cycle_minutes < cls.DELAY_SYNC_THRESHOLD_MINUTES:
            return

        # 事务提交后再发 Celery，避免数据库回滚后任务已投递
        transaction.on_commit(
            lambda task_id=instance.id: current_app.send_task(
                cls.TASK,
                args=[task_id],
                countdown=cls.DELAY_SYNC_COUNTDOWN_SECONDS,
            )
        )
        logger.info(
            "已注册采集任务延迟补跑: task_id=%s, countdown=%s, cycle_minutes=%s",
            instance.id,
            cls.DELAY_SYNC_COUNTDOWN_SECONDS,
            cycle_minutes,
        )

    @staticmethod
    def is_schedule_config_changed(old_instance, new_instance):
        # update 仅在调度配置变化时才补跑，避免普通字段编辑导致重复触发
        return any(
            [
                old_instance.is_interval != new_instance.is_interval,
                old_instance.cycle_value_type != new_instance.cycle_value_type,
                str(old_instance.cycle_value or "") != str(new_instance.cycle_value or ""),
                str(old_instance.scan_cycle or "") != str(new_instance.scan_cycle or ""),
            ]
        )

    @staticmethod
    def push_butch_node_params(instance):
        """
        格式化调用node的参数 并推送
        """
        node = NodeParamsFactory.get_node_params(instance)
        node_params = node.main()
        logger.debug(f"推送节点参数: {node_params}")
        node_mgmt = NodeMgmt()
        result = node_mgmt.batch_add_node_child_config(node_params)
        logger.debug(f"推送节点参数结果: {result}")

    @staticmethod
    def delete_butch_node_params(instance):
        """
        格式化调用node的参数 并删除
        """
        node = NodeParamsFactory.get_node_params(instance)
        node_params = node.main(operator="delete")
        logger.debug(f"删除节点参数: {node_params}")
        node_mgmt = NodeMgmt()
        result = node_mgmt.delete_child_configs(node_params)
        logger.debug(f"删除节点参数结果: {result}")

    @classmethod
    def create(cls, request, view_self):
        create_data, is_interval, scan_cycle = cls.format_params(request.data)
        cls.enrich_host_cloud_snapshot_payload(create_data)

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
                    CeleryUtils.create_or_update_periodic_task(name=task_name, crontab=scan_cycle, args=[instance.id], task=cls.TASK)
                    # create 场景满足阈值则注册一次延迟补跑
                    cls.schedule_delayed_sync_if_needed(instance=instance, is_interval=is_interval)

                # RPC 调用：推送节点参数
                if cls.should_sync_node_params(instance):
                    cls.push_butch_node_params(instance)
            except Exception as e:
                # 外部操作失败，记录详细错误日志并抛出异常，触发事务回滚
                logger.error(f"创建采集任务时外部操作失败，事务将回滚: task_name={instance.name}, error={str(e)}")
                # 重新抛出异常，让事务回滚
                raise BaseAppException(f"创建采集任务失败：{str(e)}")

            # 只有所有操作都成功，才创建变更记录
            create_change_record(
                operator=request.user.username,
                model_id=instance.model_id,
                label="采集任务",
                _type=CREATE_INST,
                message=f"创建采集任务. 任务名称: {instance.name}",
                inst_id=instance.id,
                model_object=OPERATOR_COLLECT_TASK,
            )

        return instance.id

    @classmethod
    def update(cls, request, view_self):
        # 获取旧实例数据（在事务外）
        instance = view_self.get_object()
        old_instance = copy.deepcopy(instance)

        cls.has_permission(request, instance, view_self)
        update_data, is_interval, scan_cycle = cls.format_params(request.data)
        cls.format_update_credential(instance, update_data)
        cls.enrich_host_cloud_snapshot_payload(update_data)
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
                    CeleryUtils.create_or_update_periodic_task(name=task_name, crontab=scan_cycle, args=[instance.id], task=cls.TASK)
                    if cls.is_schedule_config_changed(old_instance=old_instance, new_instance=instance):
                        # update 场景仅在调度参数变更时注册延迟补跑
                        cls.schedule_delayed_sync_if_needed(instance=instance, is_interval=is_interval)
                else:
                    CeleryUtils.delete_periodic_task(task_name)

                # RPC 调用：先删除旧节点参数，再推送新节点参数
                if cls.should_sync_node_params(instance):
                    cls.delete_butch_node_params(old_instance)
                    cls.push_butch_node_params(instance)
            except Exception as e:
                # 外部操作失败，记录错误并抛出异常，触发事务回滚
                logger.error(f"更新采集任务时外部操作失败，事务将回滚: task_name={instance.name}, error={str(e)}")
                raise BaseAppException(f"更新采集任务失败：{str(e)}")

            cls.delete_team(instance.id, old_instance.team, request.data["team"], view_self)
            # 只有所有操作都成功，才创建变更记录
            create_change_record(
                operator=request.user.username,
                model_id=instance.model_id,
                label="采集任务",
                _type=UPDATE_INST,
                message=f"修改采集任务. 任务名称: {instance.name}",
                inst_id=instance.id,
                model_object=OPERATOR_COLLECT_TASK,
            )

        return instance.id

    @classmethod
    def destroy(cls, request, view_self):
        instance = view_self.get_object()
        cls.has_permission(request, instance, view_self)
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
                if cls.should_sync_node_params(instance_copy):
                    cls.delete_butch_node_params(instance_copy)
            except Exception as e:
                # 外部资源清理失败，记录错误并抛出异常，触发事务回滚
                logger.error(f"删除采集任务时外部资源清理失败，事务将回滚: task_name={instance_name}, error={str(e)}")
                raise BaseAppException(f"删除采集任务失败：{str(e)}")

            # 外部资源清理成功后，再删除数据库记录
            instance.delete()
            create_change_record(
                operator=request.user.username,
                model_id=model_id,
                label="采集任务",
                _type=DELETE_INST,
                message=f"删除采集任务. 任务名称: {instance_name}",
                inst_id=instance_id,
                model_object=OPERATOR_COLLECT_TASK,
            )

        cls.delete_team(instance_copy.id, instance_copy.team, [], view_self)

        return instance_id

    @classmethod
    def _normalize_cloud_regions(cls, model_id, regions):
        if model_id != "qcloud":
            return regions
        return [
            {
                **region,
                "resource_name": region.get("resource_name") or region.get("RegionName") or region.get("Region") or "",
                "resource_id": region.get("resource_id") or region.get("Region") or region.get("RegionName") or "",
            }
            for region in regions
        ]

    @classmethod
    def list_regions(cls, credential, cloud_name):
        instance_id = f"{cloud_name}_stargazer"
        stargazer = Stargazer(instance_id=instance_id)
        result = stargazer.list_regions(credential)
        regions = result.get("regions", {}) if isinstance(result, dict) else {}
        if result.get("success") and regions.get("success"):
            region_result = cls._normalize_cloud_regions(credential.get("model_id"), regions.get("result", []))
            return {"success": True, "result": region_result, "message": ""}
        regions = result.get("regions", {})
        return {
            "success": False,
            "result": regions.get("result", []),
            "message": regions.get("message", "获取区域失败"),
        }

    @classmethod
    def exec_task(cls, instance, request, view_self):
        """
        执行任务
        """
        cls.has_permission(request=request, instance=instance, view_self=view_self)

        if instance.exec_status == CollectRunStatusType.RUNNING:
            return WebUtils.response_error(error_message="任务正在执行中!无法重复执行！", status_code=400)

        cls.repair_host_cloud_snapshot(instance)
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

        create_change_record(
            operator=request.user.username,
            model_id=instance.model_id,
            label="采集任务",
            _type=EXECUTE,
            message=f"执行采集任务. 任务名称: {instance.name}",
            inst_id=instance.id,
            model_object=OPERATOR_COLLECT_TASK,
        )

        return WebUtils.response_success(instance.id)

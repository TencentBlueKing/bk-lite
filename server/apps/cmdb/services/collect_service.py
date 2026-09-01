# -- coding: utf-8 --
# @File: colletc_service.py
# @Time: 2025/3/3 15:23
# @Author: windyzhao
import copy
import uuid

from celery import current_app
from django.conf import settings
from django.db import transaction
from django.utils.timezone import now

from apps.cmdb.collection.round_sync import uses_vm_reconciliation
from apps.cmdb.constants.constants import OPERATOR_COLLECT_TASK, CollectPluginTypes, CollectRunStatusType, DataCleanupStrategy
from apps.cmdb.models import CREATE_INST, DELETE_INST, EXECUTE, UPDATE_INST
from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.services.collect_credential_contract import API_SECRET_MASK
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_hit_state_service import CollectHitStateService
from apps.cmdb.services.encrypt_collect_password import get_collect_model_passwords
from apps.cmdb.tasks.celery_tasks import sync_collect_task
from apps.cmdb.utils.base import get_current_team_from_request
from apps.cmdb.utils.change_record import create_change_record
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.celery_utils import CeleryUtils, crontab_format
from apps.core.utils.web_utils import WebUtils
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.stargazer import Stargazer


class CollectModelService(object):
    TASK = "apps.cmdb.tasks.celery_tasks.sync_collect_task"
    FIRST_COLLECTION_TASK = "apps.cmdb.tasks.celery_tasks.trigger_first_collection"
    NAME = "sync_collect_task"
    # 周期任务达到该分钟阈值时，触发一次“下发后 4 分钟补跑”
    DELAY_SYNC_THRESHOLD_MINUTES = 15
    # 延迟补跑等待时长（秒）
    DELAY_SYNC_COUNTDOWN_SECONDS = 4 * 60

    # 采集任务快照不纳入超大字段 collect_data / format_data / collect_digest，
    # 避免单条变更记录膨胀到 MB 级。
    _SNAPSHOT_FIELDS = (
        "id",
        "name",
        "task_type",
        "driver_type",
        "model_id",
        "is_interval",
        "cycle_value_type",
        "cycle_value",
        "scan_cycle",
        "ip_range",
        "instances",
        "access_point",
        "credential",
        "timeout",
        "exec_status",
        "task_id",
        "params",
        "plugin_id",
        "input_method",
        "data_cleanup_strategy",
        "expire_days",
        "team",
        "is_system",
        "is_visible",
        "system_code",
    )

    @classmethod
    def _snapshot_task(cls, instance):
        """将采集任务序列化为可入库的快照 dict。"""
        if not instance:
            return {}
        snapshot = {field: getattr(instance, field, None) for field in cls._SNAPSHOT_FIELDS}
        exec_time = getattr(instance, "exec_time", None)
        snapshot["exec_time"] = exec_time.isoformat() if exec_time else None
        return snapshot

    @staticmethod
    def _safe_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _node_mgmt_client():
        return NodeMgmt()

    @staticmethod
    def should_sync_node_params(instance):
        return not instance.is_k8s

    @classmethod
    def should_register_sync_beat(cls, instance):
        """VM 对账任务改由全局守门调度；仅非 VM 链路（如 config_file）保留按任务 beat。"""
        return not uses_vm_reconciliation(instance)

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
        CollectModelService.validate_scan_cycle(data.get("scan_cycle") or {})
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
    def validate_scan_cycle(scan_cycle: dict) -> None:
        if not isinstance(scan_cycle, dict):
            return
        if scan_cycle.get("value_type") != "cycle":
            return

        value = scan_cycle.get("value")
        try:
            interval_minutes = int(value)
        except (TypeError, ValueError) as exc:
            raise BaseAppException("周期任务最小执行间隔为1分钟") from exc

        if interval_minutes < 1:
            raise BaseAppException("周期任务最小执行间隔为1分钟")

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
        rows = CollectModelService._node_mgmt_client().get_nodes_by_ids([str(node_id)])
        if not isinstance(rows, list) or not rows:
            return None
        node = rows[0] if isinstance(rows[0], dict) else {}
        return CollectModelService._safe_int(node.get("cloud_region_id"))

    @staticmethod
    def _get_cloud_region_name(cloud_id):
        if cloud_id in (None, ""):
            return ""
        rows = CollectModelService._node_mgmt_client().cloud_region_list()
        cloud_id = CollectModelService._safe_int(cloud_id)
        if cloud_id is None or not isinstance(rows, list):
            return ""
        for item in rows:
            if not isinstance(item, dict):
                continue
            if CollectModelService._safe_int(item.get("id")) == cloud_id:
                return str(item.get("name") or "").strip()
        return ""

    @classmethod
    def _resolve_host_cloud_meta(cls, params=None, access_point=None, instances=None, prefer_access_point=False):
        params = params if isinstance(params, dict) else {}
        access_point_item = cls._get_snapshot_item(access_point)
        instance_item = cls._get_snapshot_item(instances)

        access_point_cloud = access_point_item.get("cloud") or access_point_item.get("cloud_id") or access_point_item.get("cloud_region")
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
        task_type = getattr(instance, "task_type", "")
        if not credential and not instance.is_k8s and task_type != CollectPluginTypes.IP:
            raise BaseAppException("采集凭据不能为空！")
        old_credential = instance.decrypt_credentials
        if credential is None:
            data["credential"] = old_credential
            return
        encrypted_fields = set(
            get_collect_model_passwords(
                collect_model_id=getattr(instance, "model_id", ""),
                driver_type=getattr(instance, "driver_type", None),
            )
        )

        def without_masked_secrets(item):
            return {key: value for key, value in item.items() if not (key in encrypted_fields and value == API_SECRET_MASK)}

        if isinstance(credential, list):
            old_pool = old_credential if isinstance(old_credential, list) else []
            legacy_single_credential = dict(old_credential) if isinstance(old_credential, dict) and len(credential) == 1 else {}
            legacy_single_credential.pop("credential_id", None)
            old_pool_map = {item.get("credential_id"): dict(item) for item in old_pool if isinstance(item, dict) and item.get("credential_id")}
            merged_pool = []
            for item in credential:
                if not isinstance(item, dict):
                    raise BaseAppException("采集凭据格式错误！")
                credential_id = item.get("credential_id")
                merged = dict(old_pool_map.get(credential_id) or legacy_single_credential)
                merged.update(without_masked_secrets(item))
                merged_pool.append(merged)
            data["credential"] = merged_pool
            return

        if not isinstance(old_credential, dict):
            old_credential = {}
        if not isinstance(credential, dict):
            raise BaseAppException("采集凭据格式错误！")
        old_credential.update(without_masked_secrets(credential))
        data["credential"] = old_credential

    @classmethod
    def schedule_first_collection_if_needed(
        cls,
        instance,
        old_instance=None,
        reason="create",
    ):
        from apps.cmdb.constants import constants as cmdb_constants
        from apps.cmdb.services.first_collection_policy import FirstCollectionPolicy

        if not cmdb_constants.CMDB_FIRST_COLLECTION_ENABLED:
            return False
        if not FirstCollectionPolicy.is_eligible(instance):
            return False

        if old_instance is not None:
            changed_fields = FirstCollectionPolicy.changed_fields(old_instance, instance)
            if not changed_fields:
                return False
            reason = f"update:{','.join(changed_fields)}"

        fingerprint = FirstCollectionPolicy.fingerprint(instance)

        def dispatch_first_collection(
            task_id=instance.id,
            expected=fingerprint,
            trigger_reason=reason,
        ):
            try:
                current_app.send_task(
                    cls.FIRST_COLLECTION_TASK,
                    args=[task_id, expected, trigger_reason],
                )
            except Exception as exc:
                logger.error(
                    "[FirstCollection] 事务后触发投递失败 " "task_id=%s fingerprint=%s reason=%s error_type=%s",
                    task_id,
                    expected[:12],
                    trigger_reason,
                    type(exc).__name__,
                )

        transaction.on_commit(dispatch_first_collection)
        logger.info(
            "[FirstCollection] 已注册事务后触发 task_id=%s fingerprint=%s reason=%s",
            instance.id,
            fingerprint[:12],
            reason,
        )
        return True

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
    def _is_network_collect_task(instance) -> bool:
        return getattr(instance, "model_id", None) == "network" or getattr(instance, "task_type", None) == CollectPluginTypes.SNMP

    @classmethod
    def push_butch_node_params(cls, instance):
        """
        格式化调用node的参数 并推送
        """
        if cls._is_network_collect_task(instance):
            from apps.cmdb.services.network_collection_reconcile import reconcile_network_collection_configs

            logger.debug("[CollectTask] Network 双通道对账推送 task_id=%s", instance.id)
            reconcile_network_collection_configs(instance, delete=False)
            logger.debug("[CollectTask] Network 双通道对账完成 task_id=%s", instance.id)
            return
        node = NodeParamsFactory.get_node_params(instance)
        node_params = node.main()
        logger.debug("[CollectTask] 推送节点参数 task_id=%s", instance.id)
        node_mgmt = NodeMgmt()
        node_mgmt.batch_add_node_child_config(node_params)
        logger.debug("[CollectTask] 推送节点参数完成 task_id=%s", instance.id)

    @classmethod
    def delete_butch_node_params(cls, instance):
        """
        格式化调用node的参数 并删除
        """
        if cls._is_network_collect_task(instance):
            from apps.cmdb.services.network_collection_reconcile import reconcile_network_collection_configs

            logger.debug("[CollectTask] Network 双通道对账删除 task_id=%s", instance.id)
            reconcile_network_collection_configs(instance, delete=True)
            logger.debug("[CollectTask] Network 双通道删除完成 task_id=%s", instance.id)
            return
        node = NodeParamsFactory.get_node_params(instance)
        node_params = node.main(operator="delete")
        logger.debug("[CollectTask] 删除节点参数 task_id=%s", instance.id)
        node_mgmt = NodeMgmt()
        node_mgmt.delete_child_configs(node_params)
        logger.debug("[CollectTask] 删除节点参数完成 task_id=%s", instance.id)

    @staticmethod
    def _request_payload(request, payload=None):
        if payload is not None:
            return payload
        return request.data

    @classmethod
    def create(cls, request, view_self, payload=None):
        create_data, is_interval, scan_cycle = cls.format_params(cls._request_payload(request, payload))
        if create_data.get("credential"):
            create_data["credential"] = CollectCredentialPoolService.normalize_pool(create_data["credential"])
            create_data["credential"] = CollectCredentialPoolService.assign_versions([], create_data["credential"])
            CollectCredentialPoolService.validate_pool_shape(create_data["credential"])
        cls.enrich_host_cloud_snapshot_payload(create_data)

        # 使用数据库事务保证原子性：DB + 外部操作要么全成功，要么全失败
        with transaction.atomic():
            serializer = view_self.get_serializer(data=create_data)
            serializer.is_valid(raise_exception=True)
            view_self.perform_create(serializer)
            instance = serializer.instance

            def sync_external_resources():
                task_name = f"{cls.NAME}_{instance.id}"
                try:
                    # 更新定时任务：VM 对账改由全局守门；仅清理遗留 beat。
                    if is_interval and cls.should_register_sync_beat(instance):
                        CeleryUtils.create_or_update_periodic_task(
                            name=task_name,
                            crontab=scan_cycle,
                            args=[instance.id],
                            task=cls.TASK,
                        )
                        # create 场景满足阈值则注册一次延迟补跑
                        cls.schedule_delayed_sync_if_needed(instance=instance, is_interval=is_interval)
                    else:
                        CeleryUtils.delete_periodic_task(task_name)

                    # RPC 调用：推送节点参数
                    if cls.should_sync_node_params(instance):
                        cls.push_butch_node_params(instance)
                except Exception as e:
                    logger.error(
                        "[CollectTask] 创建采集任务时外部操作失败 task_name=%s, error=%s",
                        instance.name,
                        e,
                        exc_info=True,
                    )
                    raise BaseAppException(f"创建采集任务失败：{str(e)}")

            # 只有所有 DB 操作都成功，才创建变更记录
            create_change_record(
                operator=request.user.username,
                model_id=instance.model_id,
                label="采集任务",
                _type=CREATE_INST,
                message=f"创建采集任务. 任务名称: {instance.name}",
                inst_id=instance.id,
                model_object=OPERATOR_COLLECT_TASK,
                scenario=COLLECT_AUTOMATION_CHANGE,
                after_data=cls._snapshot_task(instance),
            )
            cls.schedule_first_collection_if_needed(instance=instance, reason="create")
            if (is_interval and cls.should_register_sync_beat(instance)) or cls.should_sync_node_params(instance) or uses_vm_reconciliation(instance):
                # DB 事务提交后再同步外部系统，避免回滚后留下幽灵周期任务或节点配置。
                # VM 对账任务也需要 on_commit 以幂等清理遗留 beat。
                transaction.on_commit(sync_external_resources)

        return instance.id

    @classmethod
    def _bump_network_channel_versions(cls, old_instance, update_data):
        """共享字段变更升双通道版本；仅拓扑字段变更只升拓扑版本。"""
        if not cls._is_network_collect_task(old_instance):
            return
        params = dict(update_data.get("params") or old_instance.params or {})
        old_params = dict(old_instance.params or {})
        shared_changed = any(
            [
                update_data.get("credential") is not None,
                update_data.get("instances") is not None,
                update_data.get("ip_range") is not None,
                update_data.get("access_point") is not None,
                update_data.get("timeout") is not None,
            ]
        )
        topo_keys = (
            "has_network_topo",
            "topology_protocols",
            "topology_fallback_strategy",
            "min_confidence",
            "topology_interval_minutes",
            "topology_interval_mode",
        )
        topo_changed = any(old_params.get(k) != params.get(k) for k in topo_keys)
        if shared_changed:
            params["device_channel_config_version"] = int(old_params.get("device_channel_config_version") or 1) + 1
            params["topology_channel_config_version"] = int(old_params.get("topology_channel_config_version") or 1) + 1
        elif topo_changed:
            params["topology_channel_config_version"] = int(old_params.get("topology_channel_config_version") or 1) + 1
            params.setdefault(
                "device_channel_config_version",
                int(old_params.get("device_channel_config_version") or 1),
            )
        else:
            return
        update_data["params"] = params

    @classmethod
    def update(cls, request, view_self, payload=None):
        # 获取旧实例数据（在事务外）
        instance = view_self.get_object()
        old_instance = copy.deepcopy(instance)
        source = cls._request_payload(request, payload)

        cls.has_permission(request, instance, view_self)
        update_data, is_interval, scan_cycle = cls.format_params(source)
        cls.format_update_credential(instance, update_data)
        if update_data.get("credential"):
            old_pool = CollectCredentialPoolService.normalize_pool(instance.decrypt_credentials)
            new_pool = CollectCredentialPoolService.normalize_pool(update_data["credential"])
            new_pool = CollectCredentialPoolService.assign_versions(old_pool, new_pool)
            CollectCredentialPoolService.validate_pool_shape(new_pool)
            update_data["credential"] = new_pool
            credential_pool_diff = CollectCredentialPoolService.diff_pool(old_pool, new_pool)
        else:
            credential_pool_diff = ([], [], [])
        cls.enrich_host_cloud_snapshot_payload(update_data)
        cls._bump_network_channel_versions(old_instance, update_data)
        # 使用数据库事务保证原子性
        with transaction.atomic():
            serializer = view_self.get_serializer(instance, data=update_data, partial=True)
            serializer.is_valid(raise_exception=True)
            view_self.perform_update(serializer)

            def sync_external_resources():
                task_name = f"{cls.NAME}_{instance.id}"
                try:
                    # 更新定时任务：VM 对账改由全局守门；关闭周期或 VM 类型时清理遗留 beat。
                    if is_interval and cls.should_register_sync_beat(instance):
                        CeleryUtils.create_or_update_periodic_task(
                            name=task_name,
                            crontab=scan_cycle,
                            args=[instance.id],
                            task=cls.TASK,
                        )
                        if schedule_changed or first_collection_scheduled:
                            # update 场景仅在调度参数变更时注册延迟补跑
                            cls.schedule_delayed_sync_if_needed(instance=instance, is_interval=is_interval)
                    else:
                        CeleryUtils.delete_periodic_task(task_name)

                    # RPC 调用：先删除旧节点参数，再推送新节点参数
                    if cls.should_sync_node_params(instance):
                        cls.delete_butch_node_params(old_instance)
                        cls.push_butch_node_params(instance)
                except Exception as e:
                    logger.error(
                        "[CollectTask] 更新采集任务时外部操作失败 task_name=%s, error=%s",
                        instance.name,
                        e,
                        exc_info=True,
                    )
                    raise BaseAppException(f"更新采集任务失败：{str(e)}")

            schedule_changed = cls.is_schedule_config_changed(
                old_instance=old_instance,
                new_instance=instance,
            )
            first_collection_scheduled = cls.schedule_first_collection_if_needed(
                instance=instance,
                old_instance=old_instance,
                reason="update",
            )

            cls.delete_team(instance.id, old_instance.team, source["team"], view_self)
            invalidated_credential_ids = list(dict.fromkeys(credential_pool_diff[1] + credential_pool_diff[2]))
            cleared_hit_count = CollectHitStateService.clear_by_credential_ids(instance.id, invalidated_credential_ids)
            logger.info(
                "[CollectCredentialPool] update task_id=%s added=%s removed=%s edited=%s cleared_hit_count=%s",
                instance.id,
                credential_pool_diff[0],
                credential_pool_diff[1],
                credential_pool_diff[2],
                cleared_hit_count,
            )
            # 只有所有 DB 操作都成功，才创建变更记录
            create_change_record(
                operator=request.user.username,
                model_id=instance.model_id,
                label="采集任务",
                _type=UPDATE_INST,
                message=f"修改采集任务. 任务名称: {instance.name}",
                inst_id=instance.id,
                model_object=OPERATOR_COLLECT_TASK,
                scenario=COLLECT_AUTOMATION_CHANGE,
                before_data=cls._snapshot_task(old_instance),
                after_data=cls._snapshot_task(instance),
            )
            transaction.on_commit(sync_external_resources)

        return instance.id

    @classmethod
    def destroy(cls, request, view_self):
        instance = view_self.get_object()
        cls.has_permission(request, instance, view_self)
        instance_id = instance.id
        instance_name = instance.name
        model_id = instance.model_id

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
                logger.error(
                    "[CollectTask] 删除采集任务时外部资源清理失败，事务将回滚 task_name=%s, error=%s",
                    instance_name,
                    e,
                    exc_info=True,
                )
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
                scenario=COLLECT_AUTOMATION_CHANGE,
                before_data=cls._snapshot_task(instance_copy),
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
        # if settings.DEBUG:
        #     cloud_name = f"{cloud_name}_local"
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
    def exec_task(cls, instance, operator):
        """
        执行任务
        """
        if isinstance(instance, CollectModels) and instance.pk:
            with transaction.atomic():
                locked_instance = CollectModels.objects.select_for_update().get(pk=instance.pk)
                return cls._exec_task_after_lock(locked_instance, operator)
        return cls._exec_task_after_lock(instance, operator)

    @classmethod
    def _exec_task_after_lock(cls, instance, operator):
        if instance.exec_status == CollectRunStatusType.RUNNING:
            return WebUtils.response_error(error_message="任务正在执行中!无法重复执行！", status_code=400)

        before_snapshot = cls._snapshot_task(instance)
        cls.repair_host_cloud_snapshot(instance)
        execution_id = uuid.uuid4().hex
        instance.exec_time = now()
        instance.exec_status = CollectRunStatusType.RUNNING
        instance.task_id = execution_id
        instance.format_data = {}
        instance.collect_data = {}
        instance.collect_digest = {}
        instance.save()
        node_config_id = getattr(instance, "node_mgmt_config_id", None)
        node_config_version = getattr(instance, "node_mgmt_config_version", None)
        if not settings.DEBUG:
            transaction.on_commit(
                lambda task_id=instance.id, token=execution_id: cls._dispatch_manual_execution(
                    task_id,
                    token,
                    node_config_id,
                    node_config_version,
                )
            )
        else:
            sync_collect_task(
                instance.id,
                execution_id,
                node_config_id,
                node_config_version,
            )

        create_change_record(
            operator=operator,
            model_id=instance.model_id,
            label="采集任务",
            _type=EXECUTE,
            message=f"执行采集任务. 任务名称: {instance.name}",
            inst_id=instance.id,
            model_object=OPERATOR_COLLECT_TASK,
            scenario=COLLECT_AUTOMATION_CHANGE,
            before_data=before_snapshot,
            after_data=cls._snapshot_task(instance),
        )

        return WebUtils.response_success(instance.id)

    @staticmethod
    def _dispatch_manual_execution(task_id, execution_id, node_config_id, node_config_version):
        try:
            sync_collect_task.delay(
                task_id,
                execution_id,
                node_config_id,
                node_config_version,
            )
        except Exception:
            CollectModels.objects.filter(
                id=task_id,
                task_id=execution_id,
                exec_status=CollectRunStatusType.RUNNING,
            ).update(
                exec_status=CollectRunStatusType.ERROR,
                execution_claim_token=None,
                collect_digest={"message": "采集任务下发失败，请稍后重试"},
            )
            logger.exception(
                "[CollectTask] 手动采集任务下发失败 task_id=%s execution_id=%s",
                task_id,
                execution_id,
            )

import hashlib
import json
from datetime import datetime, timezone
from string import Template

from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from apps.core.utils.safe_template import build_sandboxed_env

from apps.core.logger import node_logger as logger
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.database import DatabaseConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.installer import ControllerTaskNode
from apps.node_mgmt.models.sidecar import Collector, CollectorConfiguration, Node, NodeCollectorConfiguration, NodeOrganization
from apps.node_mgmt.services.cloudregion import RegionService
from apps.node_mgmt.services.sidecar_cache import build_configuration_etag_cache_key
from apps.node_mgmt.tasks.action_task import converge_collector_action_task_for_node
from apps.node_mgmt.tasks.installer import _matches_install_connectivity_target, converge_controller_install_connectivity_for_node
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.utils.crypto_helper import EncryptedJsonResponse
from apps.node_mgmt.utils.sidecar import format_tags_dynamic
from apps.node_mgmt.utils.step_tracker import build_step, now_iso, update_step_by_action
from apps.node_mgmt.utils.task_result_schema import apply_result_envelope, normalize_task_details


class Sidecar:
    CONVERGE_DEBOUNCE_SECONDS = 5
    CPU_ARCHITECTURE_TAG = "cpu_architecture"
    INSTALL_TASK_NODE_TAG = "install_task_node"

    @staticmethod
    def generate_etag(data):
        """根据数据生成干净的 ETag，不加引号"""
        return hashlib.md5(data.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_response_etag(data, request):
        """
        根据响应数据和请求生成 ETag
        考虑加密情况，确保 ETag 基于实际发送内容
        """
        # 检查是否需要加密
        encryption_key = None
        if request:
            encryption_key = request.META.get("HTTP_X_ENCRYPTION_KEY")

        if encryption_key:
            # 如果需要加密，基于加密后的内容生成 ETag
            from apps.node_mgmt.utils.crypto_helper import encrypt_response_data

            try:
                encrypted_content = encrypt_response_data(data, encryption_key)
                return hashlib.md5(encrypted_content.encode("utf-8")).hexdigest()
            except Exception as e:
                # 加密失败，记录警告日志并回退到明文内容，使用 Django JSON 编码器处理 datetime
                logger.warning(f"Failed to encrypt response data for ETag generation: {e}")
                json_content = json.dumps(data, ensure_ascii=False, cls=DjangoJSONEncoder)
                return hashlib.md5(json_content.encode("utf-8")).hexdigest()
        else:
            # 不需要加密，基于 JSON 内容生成 ETag，使用 Django JSON 编码器处理 datetime
            json_content = json.dumps(data, ensure_ascii=False, cls=DjangoJSONEncoder)
            return hashlib.md5(json_content.encode("utf-8")).hexdigest()

    @staticmethod
    def get_node_or_404(request, node_id):
        node = Node.objects.filter(id=node_id).first()
        if not node:
            return None, EncryptedJsonResponse(status=404, data={"error": "Node not found"}, request=request)
        return node, None

    @staticmethod
    def configuration_bound_to_node(node_id, configuration_id):
        return NodeCollectorConfiguration.objects.filter(node_id=node_id, collector_config_id=configuration_id).exists()

    @staticmethod
    def get_bound_assignment_or_404(
        request,
        node_id,
        configuration_id,
        *,
        include_child_configs=False,
        include_collector=False,
    ):
        select_related_fields = ["node", "collector_config"]
        if include_collector:
            select_related_fields.append("collector_config__collector")

        queryset = NodeCollectorConfiguration.objects.filter(node_id=node_id, collector_config_id=configuration_id).select_related(
            *select_related_fields
        )
        if include_child_configs:
            queryset = queryset.prefetch_related("collector_config__childconfig_set")

        assignment = queryset.first()
        if assignment:
            return assignment, None

        node, error_response = Sidecar.get_node_or_404(request, node_id)
        if error_response:
            return None, error_response

        return None, EncryptedJsonResponse(status=404, data={"error": "Configuration not found"}, request=request)

    @staticmethod
    def get_bound_configuration_or_404(
        request,
        node_id,
        configuration_id,
        *,
        include_child_configs=False,
        include_collector=False,
    ):
        queryset = CollectorConfiguration.objects.filter(id=configuration_id, nodes__id=node_id)
        if include_collector:
            queryset = queryset.select_related("collector")
        if include_child_configs:
            queryset = queryset.prefetch_related("childconfig_set")

        configuration = queryset.first()
        if not configuration:
            return None, EncryptedJsonResponse(status=404, data={"error": "Configuration not found"}, request=request)

        return configuration, None

    @staticmethod
    def get_version(request):
        """获取版本信息"""
        return EncryptedJsonResponse({"version": "5.0.0"}, request=request)

    @staticmethod
    def get_collectors(request):
        """获取采集器列表"""

        # 获取客户端的 ETag
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match:
            if_none_match = if_none_match.strip('"')

        # 从缓存中获取采集器的 ETag
        cached_etag = cache.get("collectors_etag")

        # 如果缓存的 ETag 存在且与客户端的相同，则返回 304 Not Modified
        if cached_etag and cached_etag == if_none_match:
            response = HttpResponse(status=304)
            response["ETag"] = cached_etag
            return response

        # 从数据库获取采集器列表
        collectors = list(Collector.objects.values())
        for collector in collectors:
            collector.pop("default_template")

        # 生成新的 ETag - 基于实际响应内容
        collectors_data = {"collectors": collectors}
        new_etag = Sidecar.generate_response_etag(collectors_data, request)

        # 更新缓存中的 ETag
        cache.set("collectors_etag", new_etag, ControllerConstants.E_CACHE_TIMEOUT)

        # 返回采集器列表和新的 ETag
        return EncryptedJsonResponse(collectors_data, headers={"ETag": new_etag}, request=request)

    @staticmethod
    def asso_groups(node_id: str, groups: list):
        if groups:
            NodeOrganization.objects.bulk_create(
                [NodeOrganization(node_id=node_id, organization=group) for group in groups],
                ignore_conflicts=True,
                batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE,
            )

    @staticmethod
    def _collector_status_signature(status_payload: dict) -> str:
        collectors = status_payload.get("collectors", []) if status_payload else []
        if not isinstance(collectors, list):
            collectors = []

        normalized = []
        for item in collectors:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "collector_id": item.get("collector_id"),
                    "status": item.get("status"),
                }
            )

        normalized.sort(key=lambda x: str(x.get("collector_id") or ""))
        payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_debounce_elapsed(cache_key: str) -> bool:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        last_ts = cache.get(cache_key)
        if last_ts is not None and now_ts - int(last_ts) < Sidecar.CONVERGE_DEBOUNCE_SECONDS:
            return False
        cache.set(cache_key, now_ts, timeout=Sidecar.CONVERGE_DEBOUNCE_SECONDS * 6)
        return True

    @staticmethod
    def trigger_converge_tasks_if_needed(node_id: str, node_ip: str, status_payload: dict):
        action_running_exists = CollectorActionTaskNode.objects.filter(
            node_id=node_id,
            status="running",
        ).exists()

        install_running_exists = False
        if node_ip:
            install_running_exists = any(
                _matches_install_connectivity_target(task_node, node_id, node_ip)
                for task_node in ControllerTaskNode.objects.filter(
                    ip=node_ip,
                    status="running",
                    task__type="install",
                )
            )

        if not action_running_exists and not install_running_exists:
            return

        if action_running_exists:
            signature = Sidecar._collector_status_signature(status_payload)
            signature_cache_key = f"node_converge_action_signature_{node_id}"
            debounce_cache_key = f"node_converge_action_debounce_{node_id}"
            last_signature = cache.get(signature_cache_key)
            if signature != last_signature or Sidecar._is_debounce_elapsed(debounce_cache_key):
                cache.set(signature_cache_key, signature, timeout=3600)
                converge_collector_action_task_for_node.delay(node_id)

        if install_running_exists:
            debounce_cache_key = f"node_converge_install_debounce_{node_id}"
            if Sidecar._is_debounce_elapsed(debounce_cache_key):
                converge_controller_install_connectivity_for_node.delay(node_id)

    @staticmethod
    def sync_groups(node_id: str, expected_groups: list):
        """
        Incrementally sync node organization associations.
        Calculates diff between current and expected groups, then adds/removes as needed.

        :param node_id: Node ID
        :param expected_groups: List of organization IDs the node should belong to
        """
        if not expected_groups:
            # No groups expected - remove all associations
            removed_count, _ = NodeOrganization.objects.filter(node_id=node_id).delete()
            if removed_count > 0:
                logger.info("Removed all %d organization associations for node %s", removed_count, node_id)
            return

        expected_set = set(expected_groups)
        current_orgs = set(NodeOrganization.objects.filter(node_id=node_id).values_list("organization", flat=True))

        to_add = expected_set - current_orgs
        to_remove = current_orgs - expected_set

        if to_remove:
            removed_count, _ = NodeOrganization.objects.filter(node_id=node_id, organization__in=to_remove).delete()
            logger.info(
                "Removed %d organization associations for node %s: %s",
                removed_count,
                node_id,
                list(to_remove),
            )

        if to_add:
            NodeOrganization.objects.bulk_create(
                [NodeOrganization(node_id=node_id, organization=org) for org in to_add],
                ignore_conflicts=True,
                batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE,
            )
            logger.info(
                "Added %d organization associations for node %s: %s",
                len(to_add),
                node_id,
                list(to_add),
            )

    @staticmethod
    def _fallback_cpu_architecture(node_id: str, request_data: dict) -> str:
        cpu_architecture = normalize_cpu_architecture(request_data.get("cpu_architecture"))
        if cpu_architecture:
            return cpu_architecture

        cpu_architecture = normalize_cpu_architecture(request_data.get("architecture"))
        if cpu_architecture:
            return cpu_architecture

        tags = request_data.get("tags", [])
        if tags:
            tag_data = format_tags_dynamic(tags, [Sidecar.CPU_ARCHITECTURE_TAG])
            cpu_architectures = tag_data.get(Sidecar.CPU_ARCHITECTURE_TAG, [])
            if cpu_architectures:
                normalized_tag_arch = normalize_cpu_architecture(cpu_architectures[0])
                if normalized_tag_arch:
                    return normalized_tag_arch

        operating_system = str(request_data.get("operating_system", "")).lower()
        node_ip = request_data.get("ip", "")
        if not node_ip or not operating_system:
            return ""

        task_node = ControllerTaskNode.objects.filter(ip=node_ip, os=operating_system).exclude(cpu_architecture="").order_by("-id").first()
        if task_node:
            logger.info(
                "Falling back to install task CPU architecture for node %s: %s",
                node_id,
                task_node.cpu_architecture,
            )
            return normalize_cpu_architecture(task_node.cpu_architecture)

        return ""

    @staticmethod
    def _default_collector_priority(collector_cpu_architecture: str, node_cpu_architecture: str) -> int:
        collector_arch = normalize_cpu_architecture(collector_cpu_architecture)
        node_arch = normalize_cpu_architecture(node_cpu_architecture)

        if node_arch == NodeConstants.ARM64_ARCH:
            if collector_arch == NodeConstants.ARM64_ARCH:
                return 2
            return 0

        if node_arch == NodeConstants.X86_64_ARCH:
            if collector_arch == NodeConstants.X86_64_ARCH:
                return 2
            if not collector_arch:
                return 1
            return 0

        if not collector_arch:
            return 2
        if collector_arch == NodeConstants.X86_64_ARCH:
            return 1
        return 0

    @classmethod
    def _get_default_collectors_for_node(cls, node):
        node_arch = normalize_cpu_architecture(getattr(node, "cpu_architecture", ""))
        if node_arch == NodeConstants.ARM64_ARCH:
            allowed_architectures = [NodeConstants.ARM64_ARCH]
        elif node_arch == NodeConstants.X86_64_ARCH:
            allowed_architectures = [NodeConstants.X86_64_ARCH, ""]
        else:
            allowed_architectures = ["", NodeConstants.X86_64_ARCH]
        collector_objs = Collector.objects.filter(
            controller_default_run=True,
            node_operating_system=node.operating_system,
            cpu_architecture__in=allowed_architectures,
        ).order_by("name", "cpu_architecture", "id")

        selected_collectors = {}
        for collector_obj in collector_objs:
            priority = cls._default_collector_priority(collector_obj.cpu_architecture, node_arch)
            current = selected_collectors.get(collector_obj.name)
            if current is None or priority > current[0]:
                selected_collectors[collector_obj.name] = (priority, collector_obj)

        return {name: collector for name, (_, collector) in selected_collectors.items()}

    @staticmethod
    def update_node_client(request, node_id):
        """更新sidecar客户端信息"""

        # 获取客户端发送的ETag
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match:
            if_none_match = if_none_match.strip('"')

        # 从缓存中获取node的ETag
        cached_etag = cache.get(f"node_etag_{node_id}")

        # 如果缓存的ETag存在且与客户端的相同，则返回304 Not Modified
        if cached_etag and cached_etag == if_none_match:
            # 更新时间, 更新状态
            node_status = request.data.get("node_details", {}).get("status", {})
            Node.objects.filter(id=node_id).update(
                updated_at=datetime.now(timezone.utc).isoformat(),
                status=node_status,
            )

            node_ip = request.data.get("node_details", {}).get("ip", "")
            if not node_ip:
                node_ip = Node.objects.filter(id=node_id).values_list("ip", flat=True).first()
            Sidecar.trigger_converge_tasks_if_needed(node_id, node_ip, node_status)

            response = HttpResponse(status=304)
            response["ETag"] = cached_etag
            return response

        # 从请求体中获取数据
        request_data = dict(
            id=node_id,
            name=request.data.get("node_name", ""),
            **request.data.get("node_details", {}),
        )

        # 操作系统转小写
        request_data.update(operating_system=request_data["operating_system"].lower())
        request_data.update(cpu_architecture=Sidecar._fallback_cpu_architecture(node_id, request_data))
        request_data.pop("architecture", None)

        logger.debug(f"node data: {request_data}")

        # 更新或创建 Sidecar 信息
        node = Node.objects.filter(id=node_id).first()

        # 处理标签数据
        allowed_prefixes = [
            ControllerConstants.GROUP_TAG,
            ControllerConstants.CLOUD_TAG,
            ControllerConstants.INSTALL_METHOD_TAG,
            ControllerConstants.NODE_TYPE_TAG,
            Sidecar.CPU_ARCHITECTURE_TAG,
            Sidecar.INSTALL_TASK_NODE_TAG,
        ]
        tags_data = format_tags_dynamic(request_data.get("tags", []), allowed_prefixes)

        cpu_architecture_tags = tags_data.get(Sidecar.CPU_ARCHITECTURE_TAG, [])
        if cpu_architecture_tags and not request_data.get("cpu_architecture"):
            request_data.update(cpu_architecture=normalize_cpu_architecture(cpu_architecture_tags[0]))

        # 补充云区域关联
        clouds = tags_data.get(ControllerConstants.CLOUD_TAG, [])
        if clouds:
            request_data.update(cloud_region_id=int(clouds[0]))

        # 补充安装方法
        install_methods = tags_data.get(ControllerConstants.INSTALL_METHOD_TAG, [])
        if install_methods:
            if install_methods[0] in [
                ControllerConstants.AUTO,
                ControllerConstants.MANUAL,
            ]:
                request_data.update(install_method=install_methods[0])

        # 补充节点类型
        node_types = tags_data.get(ControllerConstants.NODE_TYPE_TAG, [])
        if node_types:
            request_data.update(node_type=node_types[0])

        resolved_node_type = request_data.get("node_type") or (node.node_type if node else "")
        has_existing_cpu_architecture = bool(getattr(node, "cpu_architecture", ""))
        if (
            resolved_node_type == ControllerConstants.NODE_TYPE_CONTAINER
            and not request_data.get("cpu_architecture")
            and not has_existing_cpu_architecture
        ):
            request_data.update(cpu_architecture=NodeConstants.X86_64_ARCH)

        if not node:
            # 创建节点
            node = Node.objects.create(**request_data)

            # 关联组织
            Sidecar.asso_groups(node_id, tags_data.get(ControllerConstants.GROUP_TAG, []))

            # 创建默认的配置
            Sidecar.create_default_config(node, node_types)

        else:
            # 更新时间
            request_data.update(updated_at=datetime.now(timezone.utc).isoformat())

            # 更新节点
            node_info = {key: val for key, val in request_data.items() if key != "name"}
            if not node_info.get("cpu_architecture"):
                node_info.pop("cpu_architecture", None)
            Node.objects.filter(id=node_id).update(**node_info)

            # Existing node organization ownership is managed by the server/UI.
            # Sidecar may heartbeat with stale group tags before sidecar.yaml is
            # updated, so do not let those tags roll back user edits.

        # 预取相关数据，减少查询次数
        new_obj = Node.objects.prefetch_related("action_set", "collectorconfiguration_set").get(id=node_id)

        # 构造响应数据
        response_data = dict(
            configuration={
                "update_interval": ControllerConstants.DEFAULT_UPDATE_INTERVAL,
                "send_status": True,
            },  # 配置信息, DEFAULT_UPDATE_INTERVAL s更新一次
            configuration_override=True,  # 是否覆盖配置
            actions=[],  # 采集器状态
            assignments=[],  # 采集器配置
        )

        # 节点操作信息
        action_obj = new_obj.action_set.first()
        if action_obj:
            response_data.update(actions=action_obj.action)

            for action_item in action_obj.action:
                task_id = action_item.get("task_id")
                if not task_id:
                    continue
                task_node = CollectorActionTaskNode.objects.filter(task_id=task_id, node_id=node_id).first()
                if task_node and task_node.status == "waiting":
                    task_node.status = "running"
                    task_node.result = apply_result_envelope(
                        {
                            "steps": [
                                build_step(
                                    "consume_ack",
                                    "success",
                                    "Sidecar acknowledged action",
                                    timestamp=now_iso(),
                                    details=normalize_task_details(
                                        {
                                            "delivered": True,
                                            "collector_id": action_item.get("collector_id"),
                                        },
                                        message="Sidecar acknowledged action",
                                    ),
                                ),
                                build_step(
                                    "execute_command",
                                    "running",
                                    "Execute collector action",
                                    timestamp=now_iso(),
                                ),
                            ],
                        },
                        overall_status="running",
                        final_message="Collector action acknowledged by sidecar",
                    )
                    task_node.save(update_fields=["status", "result"])

                elif task_node and task_node.status == "running":
                    result = task_node.result or {}
                    steps = result.get("steps", [])
                    consume_ack_step = next(
                        (step for step in steps if step.get("action") == "consume_ack"),
                        None,
                    )
                    if consume_ack_step and consume_ack_step.get("status") == "running":
                        update_step_by_action(
                            result,
                            "consume_ack",
                            "success",
                            "Sidecar acknowledged action",
                            details=normalize_task_details(
                                {
                                    "delivered": True,
                                    "collector_id": action_item.get("collector_id"),
                                },
                                message="Sidecar acknowledged action",
                            ),
                            timestamp=now_iso(),
                        )

                    execute_step = next(
                        (step for step in steps if step.get("action") == "execute_command"),
                        None,
                    )
                    if not execute_step:
                        steps.append(
                            build_step(
                                "execute_command",
                                "running",
                                "Execute collector action",
                                timestamp=now_iso(),
                            )
                        )

                    result["steps"] = steps
                    task_node.result = apply_result_envelope(
                        result,
                        overall_status="running",
                        final_message="Collector action acknowledged by sidecar",
                    )
                    task_node.save(update_fields=["result"])

                    CollectorActionTask.objects.filter(id=task_id, status="waiting").update(status="running")

            action_obj.delete()

        # 节点配置信息
        assignments = new_obj.collectorconfiguration_set.all()
        if assignments:
            response_data.update(assignments=[{"collector_id": i.collector_id, "configuration_id": i.id} for i in assignments])

        # 生成新的ETag - 基于实际响应内容
        new_etag = Sidecar.generate_response_etag(response_data, request)
        # 更新缓存中的ETag
        cache.set(f"node_etag_{node_id}", new_etag, ControllerConstants.E_CACHE_TIMEOUT)

        # 返回响应
        node_status = request_data.get("status", {})
        Sidecar.trigger_converge_tasks_if_needed(node_id, new_obj.ip, node_status)
        return EncryptedJsonResponse(status=202, data=response_data, headers={"ETag": new_etag}, request=request)

    @staticmethod
    def get_node_config(request, node_id, configuration_id):
        """获取节点配置信息"""

        # 获取客户端发送的 ETag
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match:
            if_none_match = if_none_match.strip('"')

        # 从缓存中获取配置的 ETag
        cache_key = build_configuration_etag_cache_key(node_id, configuration_id)
        cached_etag = cache.get(cache_key)

        # 对比客户端的 ETag 和缓存的 ETag
        if cached_etag and cached_etag == if_none_match:
            if not Sidecar.configuration_bound_to_node(node_id, configuration_id):
                node, error_response = Sidecar.get_node_or_404(request, node_id)
                if error_response:
                    return error_response
                return EncryptedJsonResponse(status=404, data={"error": "Configuration not found"}, request=request)

            response = HttpResponse(status=304)
            response["ETag"] = cached_etag
            return response

        assignment, error_response = Sidecar.get_bound_assignment_or_404(
            request,
            node_id,
            configuration_id,
            include_child_configs=True,
            include_collector=True,
        )
        if error_response:
            return error_response

        node = assignment.node
        configuration = assignment.collector_config

        # 合并子配置内容到模板
        merged_template = configuration.config_template

        collector = configuration.collector
        section_headers = {}
        if collector.default_config:
            section_headers = collector.default_config.get("config_section", {})

        child_configs = list(configuration.childconfig_set.all())
        child_render_variables = Sidecar.collect_child_render_variables(child_configs)

        if child_configs and section_headers:
            grouped_configs = {}
            ungrouped_configs = []
            for child_config in child_configs:
                if child_config.config_section:
                    grouped_configs.setdefault(child_config.config_section, []).append(child_config)
                else:
                    ungrouped_configs.append(child_config)

            for section_key in section_headers.keys():
                configs = grouped_configs.get(section_key, [])
                if configs:
                    header = section_headers.get(section_key, "")
                    if header:
                        merged_template += header
                    for child_config in configs:
                        merged_template += f"\n# {child_config.collect_type} - {child_config.config_type}\n"
                        merged_template += Sidecar.render_template(child_config.content, child_config.env_config)

            for child_config in ungrouped_configs:
                merged_template += f"\n# {child_config.collect_type} - {child_config.config_type}\n"
                merged_template += Sidecar.render_template(child_config.content, child_config.env_config)
        else:
            for child_config in child_configs:
                merged_template += f"\n# {child_config.collect_type} - {child_config.config_type}\n"
                merged_template += Sidecar.render_template(child_config.content, child_config.env_config)

        configuration_data = dict(
            id=configuration.id,
            collector_id=configuration.collector_id,
            name=configuration.name,
            template=merged_template,
            env_config=configuration.env_config or {},
        )
        # TODO test merged_template

        variables = Sidecar.get_variables(node)

        # 如果配置中有 env_config，则合并到变量中
        if configuration_data.get("env_config"):
            variables.update(configuration_data["env_config"])
        variables.update(child_render_variables)

        # 渲染配置模板
        configuration_data["template"] = Sidecar.render_template(configuration_data["template"], variables)

        # 生成新的 ETag - 基于实际响应内容
        new_etag = Sidecar.generate_response_etag(configuration_data, request)

        # 更新缓存中的 ETag
        cache.set(cache_key, new_etag, ControllerConstants.E_CACHE_TIMEOUT)

        # 返回配置信息和新的 ETag
        return EncryptedJsonResponse(configuration_data, headers={"ETag": new_etag}, request=request)

    @staticmethod
    def get_node_config_env(request, node_id, configuration_id):
        assignment, error_response = Sidecar.get_bound_assignment_or_404(
            request,
            node_id,
            configuration_id,
            include_child_configs=True,
        )
        if error_response:
            return error_response

        node = assignment.node
        obj = assignment.collector_config

        cloud_region_secret_env = Sidecar.get_cloud_region_secret_envconfig(node)
        aes_obj = AESCryptor()

        # 合并环境变量：主配置的 env_config
        merged_env_config = {}
        if obj.env_config and isinstance(obj.env_config, dict):
            merged_env_config.update(obj.env_config)

        # 合并子配置的 env_config，按排序顺序处理
        for child_config in obj.childconfig_set.all():
            if child_config.env_config and isinstance(child_config.env_config, dict):
                merged_env_config.update(child_config.env_config)

        # 解密包含password的环境变量
        decrypted_env_config = {}
        for key, value in merged_env_config.items():
            if "password" in key.lower() and value:
                try:
                    # 对包含password的key进行解密
                    decrypted_env_config[key] = aes_obj.decode(str(value))
                except Exception as e:
                    logger.warning(f"Failed to decrypt password field {key}: {e}")
                    # 如果解密失败，可能是明文存储的，直接使用原值
                    decrypted_env_config[key] = str(value)
            else:
                decrypted_env_config[key] = str(value)

        # 合并云区域环境变量（仅 NATS_PASSWORD 和 NATS_ADMIN_PASSWORD，优先级较低，配置级的env_config会覆盖同名变量）
        final_env_config = {}
        final_env_config.update(cloud_region_secret_env)
        final_env_config.update(decrypted_env_config)

        logger.debug(
            "Merged env config for configuration %s: %s variables (NATS_PASSWORD from cloud region: %s, NATS_ADMIN_PASSWORD from cloud region: %s)",
            configuration_id,
            len(final_env_config),
            "yes" if NodeConstants.NATS_PASSWORD_KEY in cloud_region_secret_env else "no",
            "yes" if NodeConstants.NATS_ADMIN_PASSWORD_KEY in cloud_region_secret_env else "no",
        )

        return EncryptedJsonResponse(data=dict(id=configuration_id, env_config=final_env_config), request=request)

    @staticmethod
    def get_cloud_region_envconfig(node_obj):
        """获取云区域环境变量"""
        return RegionService.get_cloud_region_envconfig(node_obj.cloud_region_id)

    @staticmethod
    def get_cloud_region_secret_envconfig(node_obj):
        return RegionService.get_cloud_region_envconfig(
            node_obj.cloud_region_id,
            keys=NodeConstants.CLOUD_REGION_NATS_SECRET_KEYS,
        )

    @staticmethod
    def get_variables(node_obj):
        """获取变量"""
        variables = Sidecar.get_cloud_region_envconfig(node_obj)
        node_dict = {
            "node__id": node_obj.id,
            "node__cloud_region": node_obj.cloud_region_id,
            "node__name": node_obj.name,
            "node__ip": node_obj.ip,
            "node__ip_filter": node_obj.ip.replace(".", "-").replace("*", "-").replace("*", ">"),
            "node__operating_system": node_obj.operating_system,
            "node__collector_configuration_directory": node_obj.collector_configuration_directory,
            "PACKETBEAT_DEVICE": "0" if node_obj.operating_system == "windows" else "any",
        }
        variables.update(node_dict)
        return variables

    @staticmethod
    def collect_child_render_variables(child_configs):
        variables = {}
        for child_config in child_configs:
            for key, value in (child_config.env_config or {}).items():
                if "__" not in key:
                    variables[key] = value
        return variables

    @staticmethod
    def render_template(template_str, variables):
        """
        渲染字符串模板，将 ${变量} 替换为给定的值。

        :param template_str: 包含模板变量的字符串
        :param variables: 字典，包含变量名和对应值
        :return: 渲染后的字符串
        """
        # 排除password相关的变量渲染，走env_config渲染
        _variables = {k: v for k, v in variables.items() if "password" not in k.lower()}
        template_str = template_str.replace("node.", "node__")
        template = Template(template_str)
        return template.safe_substitute(_variables)

    @staticmethod
    def create_default_config(node, node_types):
        collector_objs = Sidecar._get_default_collectors_for_node(node).values()
        variables = Sidecar.get_cloud_region_envconfig(node)
        default_sidecar_mode = variables.get("SIDECAR_INPUT_MODE", "nats")

        resolved_node_types = set(node_types or [])
        if node.node_type:
            resolved_node_types.add(node.node_type)

        is_container_node = ControllerConstants.NODE_TYPE_CONTAINER in resolved_node_types

        for collector_obj in collector_objs:
            try:
                if collector_obj.name in CollectorConstants.DEFAULT_CONTAINER_COLLECTOR_CONFIGS:
                    if not is_container_node:
                        continue

                if not collector_obj.default_config:
                    continue

                config_template = collector_obj.default_config.get(default_sidecar_mode, None)

                if not config_template:
                    continue

                # 如果是容器节点，从 default_config 中获取附加配置并追加到模板后面
                if is_container_node:
                    add_config = collector_obj.default_config.get("add_config", "")
                    if add_config:
                        config_template = config_template + "\n" + add_config
                        logger.info(f"Node {node.id} is a container node, appending add_config for {collector_obj.name}")

                # 渲染模板
                tpl = build_sandboxed_env().from_string(config_template)
                _config_template = tpl.render(variables)

                existing_pre_configuration = CollectorConfiguration.objects.filter(collector=collector_obj, nodes=node, is_pre=True).first()
                if existing_pre_configuration:
                    update_fields = []
                    if existing_pre_configuration.config_template != _config_template:
                        existing_pre_configuration.config_template = _config_template
                        update_fields.append("config_template")
                    if existing_pre_configuration.cloud_region_id != node.cloud_region_id:
                        existing_pre_configuration.cloud_region = node.cloud_region
                        update_fields.append("cloud_region")

                    if update_fields:
                        existing_pre_configuration.save(update_fields=update_fields)
                        logger.info(f"Node {node.id} updated default configuration for collector {collector_obj.name}.")
                    else:
                        logger.info(f"Node {node.id} default configuration for collector {collector_obj.name} is up to date.")
                    continue

                # 如果已经存在关联的自定义配置则跳过，避免覆盖用户配置
                if CollectorConfiguration.objects.filter(collector=collector_obj, nodes=node).exists():
                    logger.info(
                        "Node %s already has a custom configuration for collector %s, " "skipping default configuration creation.",
                        node.id,
                        collector_obj.name,
                    )
                    continue

                configuration = CollectorConfiguration.objects.create(
                    name=f"{collector_obj.name}-{node.id}",
                    collector=collector_obj,
                    config_template=_config_template,
                    is_pre=True,
                    cloud_region=node.cloud_region,
                )
                configuration.nodes.add(node)

            except Exception as e:
                logger.error(f"create node {node.id} {collector_obj.name} default configuration failed {e}")

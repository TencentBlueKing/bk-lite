import ipaddress
import os
from datetime import datetime, timedelta, timezone

from django.utils import timezone as dj_timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import node_logger as logger
from apps.core.utils.current_team_scope import CurrentTeamDataScope, _normalize_organization_ids
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.safe_template import build_sandboxed_env
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import NodeCollectorInstallStatus
from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.sidecar import Action, ChildConfig, Collector, CollectorConfiguration, Node
from apps.node_mgmt.serializers.node import NodeSerializer
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.tasks.action_task import ACTION_TASK_TIMEOUT_SECONDS, timeout_collector_action_task
from apps.node_mgmt.utils.region_display_ip import load_region_display_ips
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import User


def _get_positive_int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1, value)


class NodeService:
    NODE_LIST_PAGE_SIZE_MAX = _get_positive_int_env("NODE_MGMT_NODE_LIST_PAGE_SIZE_MAX", 500)

    @staticmethod
    def _build_scoped_permission(permission_data):
        user_obj = User(username=permission_data["username"], domain=permission_data["domain"])
        include_children_value = permission_data.get("include_children", False)
        include_children = include_children_value is True or (type(include_children_value) is str and include_children_value == "1")
        current_team = permission_data.get("current_team")

        if current_team in (None, ""):
            return {}, None

        try:
            current_team = next(iter(_normalize_organization_ids([current_team])))
        except BaseAppException:
            return {}, None

        scope_result = SystemMgmt(is_local_client=True).get_authorized_groups_scoped(
            {
                "username": permission_data["username"],
                "domain": permission_data["domain"],
                "current_team": current_team,
                "is_superuser": permission_data.get("is_superuser", False),
            },
            include_children=include_children,
        )
        if not isinstance(scope_result, dict) or not scope_result.get("result") or not isinstance(scope_result.get("data"), list):
            return {}, None

        try:
            authorized_groups = _normalize_organization_ids(scope_result["data"])
        except BaseAppException:
            return {}, None
        if not authorized_groups or current_team not in authorized_groups:
            return {}, None

        permission = get_permission_rules(
            user_obj,
            current_team,
            "node_mgmt",
            NodeConstants.MODULE,
            include_children=include_children,
        )
        scope = CurrentTeamDataScope(
            current_team=current_team,
            data_team_ids=authorized_groups,
            include_children=include_children,
            username=permission_data["username"],
            domain=permission_data["domain"],
            is_superuser=permission_data.get("is_superuser", False),
        )
        return permission, scope

    @staticmethod
    def _iter_configuration_ids(raw_configuration_id):
        """sidecar 状态里 configuration_id 可能缺失、是标量，或是历史遗留的列表。"""
        if raw_configuration_id in (None, ""):
            return
        if isinstance(raw_configuration_id, (list, tuple, set)):
            for item in raw_configuration_id:
                if item not in (None, ""):
                    yield item
            return
        yield raw_configuration_id

    @staticmethod
    def _build_node_assignment_map(node_ids):
        """按节点聚合服务端绑定的采集器配置，作为 configuration_* 的权威来源。"""
        assignment_map = {}
        if not node_ids:
            return assignment_map

        rows = CollectorConfiguration.objects.filter(nodes__id__in=node_ids).values(
            "id",
            "name",
            "collector_id",
            "nodes__id",
        )
        for row in rows:
            node_id = row["nodes__id"]
            collector_id = row["collector_id"]
            assignment_map.setdefault(node_id, {}).setdefault(collector_id, []).append({"id": row["id"], "name": row["name"]})
        return assignment_map

    @staticmethod
    def _apply_configuration_fields(collector, bound_configs, configuration_dict):
        """优先用服务端绑定补全配置字段；status 里的 configuration_id 仅作回退。"""
        if bound_configs:
            collector["configuration_id"] = bound_configs[0]["id"]
            collector["configuration_name"] = ", ".join(item["name"] for item in bound_configs if item.get("name")) or None
            return

        config_ids = list(NodeService._iter_configuration_ids(collector.get("configuration_id")))
        config_names = [configuration_dict[config_id].name for config_id in config_ids if config_id in configuration_dict]
        collector["configuration_name"] = ", ".join(config_names) if config_names else None

    @staticmethod
    def process_node_data(node_data):
        """处理节点数据列表，并补充每个节点的采集器名称和采集器配置名称"""
        collector_ids = set()
        configuration_ids = set()

        # 收集所有需要的 collector_id 和 configuration_id
        for node in node_data:
            if "collectors" not in node["status"]:
                continue
            for collector in node["status"]["collectors"]:
                collector_id = collector.get("collector_id")
                if collector_id not in (None, ""):
                    collector_ids.add(collector_id)
                configuration_ids.update(NodeService._iter_configuration_ids(collector.get("configuration_id")))

        # 先查询安装状态，收集安装记录中涉及的 collector_id
        node_ids = [node["id"] for node in node_data]
        node_install_map = {}
        objs = NodeCollectorInstallStatus.objects.filter(node__in=node_ids)
        for obj in objs:
            if obj.status == "success":
                status = 11
            elif obj.status == "error":
                status = 12
            else:
                status = 10

            collector_ids.add(obj.collector_id)
            node_install_map.setdefault(obj.node_id, []).append(dict(collector_id=obj.collector_id, status=status, message=obj.result))

        # 批量查询所有需要的 Collector 和 CollectorConfiguration（仅过滤本页涉及的 ID）
        collectors = Collector.objects.filter(id__in=collector_ids) if collector_ids else []
        collector_dict = {collector.id: collector for collector in collectors}

        # 服务端绑定是 configuration_* 的权威来源；status 字段仅作回退
        node_assignment_map = NodeService._build_node_assignment_map(node_ids)
        for node_assignments in node_assignment_map.values():
            for bound_configs in node_assignments.values():
                configuration_ids.update(item["id"] for item in bound_configs)

        configurations = CollectorConfiguration.objects.filter(id__in=configuration_ids) if configuration_ids else []
        configuration_dict = {config.id: config for config in configurations}

        # 处理节点数据
        for node in node_data:
            node_collector_install = node_install_map.get(node["id"], [])
            if node_collector_install:
                # 为 collectors_install 中的每个项添加 collector_name
                for install_item in node_collector_install:
                    collector_obj = collector_dict.get(install_item["collector_id"])
                    install_item["collector_name"] = collector_obj.name if collector_obj else None

                node["status"]["collectors_install"] = node_collector_install

            if "collectors" not in node["status"]:
                continue

            node_assignments = node_assignment_map.get(node["id"], {})

            # 处理采集器状态：忽略不支持空跑的采集器的特定错误，将其状态改为正常
            for collector in node["status"]["collectors"]:
                collector_id = collector.get("collector_id")
                collector_obj = collector_dict.get(collector_id)
                collector["collector_name"] = collector_obj.name if collector_obj else None

                NodeService._apply_configuration_fields(
                    collector,
                    node_assignments.get(collector_id, []),
                    configuration_dict,
                )

                # 判断是否应该将错误状态改为正常
                if collector["status"] == 2 and collector_obj:  # status=2 表示失败
                    # 检查是否是需要忽略错误的采集器
                    if collector_obj.name in CollectorConstants.IGNORE_ERROR_COLLECTORS:
                        # 检查错误信息是否匹配需要忽略的消息（使用 contains 匹配，兼容动态路径）
                        verbose_msg = collector.get("verbose_message", "")
                        if any(msg in verbose_msg for msg in CollectorConstants.IGNORE_ERROR_COLLECTORS_MESSAGES):
                            # 将状态从失败改为正常
                            collector["status"] = 0
                            collector["message"] = "Running"
                            logger.debug(
                                f"Changed status to Running for collector {collector_obj.name} "
                                f"on node {node.get('name', node['id'])}: {verbose_msg.strip()}"
                            )

        # 计算节点活跃度，一分钟内为活跃
        for node in node_data:
            now_timestamp = int(datetime.now(timezone.utc).timestamp())
            # 解析成 datetime 对象
            updated_at_timestamp = int(datetime.strptime(node["updated_at"], "%Y-%m-%dT%H:%M:%S%z").timestamp())
            # 计算时间差
            time_diff = now_timestamp - updated_at_timestamp
            # 判断是否活跃
            if time_diff < 60:
                node["active"] = True
            else:
                node["active"] = False
        return node_data

    @staticmethod
    def batch_binding_node_configuration(node_ids, collector_configuration_id):
        """批量绑定配置到多个节点"""
        try:
            collector_configuration = CollectorConfiguration.objects.select_related("collector").get(id=collector_configuration_id)
            collector = collector_configuration.collector

            nodes = Node.objects.filter(id__in=node_ids).prefetch_related("collectorconfiguration_set")
            for node in nodes:
                # 检查节点采集器是否已经存在配置文件
                existing_configurations = node.collectorconfiguration_set.filter(collector=collector)
                if existing_configurations.exists():
                    # 覆盖现有配置文件
                    for config in existing_configurations:
                        config.nodes.remove(node)

                # 添加新的配置文件
                collector_configuration.nodes.add(node)

            collector_configuration.save()
            return True, "采集器配置已成功应用到所有节点。"
        except CollectorConfiguration.DoesNotExist:
            return False, "采集器配置不存在。"

    @staticmethod
    def batch_operate_node_collector(
        node_ids,
        collector_id,
        operation,
        created_by="",
        domain="domain.com",
        updated_by_domain="domain.com",
    ):
        """批量操作节点采集器"""
        # 一次性查询所有节点，避免重复查询
        nodes = Node.objects.filter(id__in=node_ids).select_related("cloud_region")
        total_count = nodes.count()
        if total_count == 0:
            raise BaseAppException("No valid nodes found for collector operation")

        cloud_region = None
        first_node = nodes.first()
        if first_node:
            cloud_region = first_node.cloud_region

        task_obj = CollectorActionTask.objects.create(
            collector_id=collector_id,
            cloud_region=cloud_region,
            action=operation,
            status="waiting",
            total_count=total_count,
            created_by=created_by,
            updated_by=created_by,
            domain=domain,
            updated_by_domain=updated_by_domain,
        )

        CollectorActionTaskNode.objects.bulk_create(
            [
                CollectorActionTaskNode(
                    task=task_obj,
                    node_id=node.id,
                    status="waiting",
                    result={},
                )
                for node in nodes
            ],
            batch_size=500,
        )

        task_nodes = {
            item.node_id: item for item in CollectorActionTaskNode.objects.filter(task_id=task_obj.id, node_id__in=[node.id for node in nodes])
        }

        # 如果是 start 或 restart 操作，需要检查并创建默认配置
        if operation in ["start", "restart"]:
            try:
                collector = Collector.objects.get(id=collector_id)

                # 批量查询已有配置的节点，避免N+1查询
                nodes_with_config = CollectorConfiguration.objects.filter(collector=collector, nodes__in=nodes).values_list("nodes__id", flat=True)

                nodes_with_config_set = set(nodes_with_config)

                # 只为没有配置的节点创建默认配置
                for node in nodes:
                    if node.id not in nodes_with_config_set:
                        NodeService._create_collector_default_config(node, collector)

            except Collector.DoesNotExist:
                logger.error(f"Collector {collector_id} does not exist")
            except Exception as e:
                logger.error(f"Error checking/creating default config for collector {collector_id}: {e}")

        # 执行原有的操作逻辑
        for node in nodes:
            action_data = {
                "collector_id": collector_id,
                "properties": {operation: True},
                "task_id": task_obj.id,
            }
            action, created = Action.objects.get_or_create(node=node)
            action.action.append(action_data)
            action.save()

            task_node = task_nodes.get(node.id)
            if task_node and task_node.status == "waiting":
                task_node.status = "running"
                task_node.result = {
                    "overall_status": "running",
                    "final_message": "Collector action submitted",
                    "steps": [
                        {
                            "action": "dispatch_command",
                            "status": "success",
                            "message": "Submit collector action",
                            "timestamp": dj_timezone.now().isoformat(),
                            "details": {
                                "collector_id": collector_id,
                                "operation": operation,
                            },
                        },
                        {
                            "action": "consume_ack",
                            "status": "running",
                            "message": "Wait for sidecar acknowledgment",
                            "timestamp": dj_timezone.now().isoformat(),
                        },
                    ],
                }
                task_node.save(update_fields=["status", "result"])

        timeout_collector_action_task.apply_async(
            args=[task_obj.id],
            countdown=ACTION_TASK_TIMEOUT_SECONDS,
        )

        return task_obj.id

    @staticmethod
    def _create_collector_default_config(node, collector):
        """为节点创建指定采集器的默认配置"""
        try:
            # 检查采集器是否有默认配置
            if not collector.default_config:
                logger.info(f"Collector {collector.name} has no default_config, skipping")
                return

            # 获取云区域环境变量
            variables = Sidecar.get_cloud_region_envconfig(node)
            default_sidecar_mode = variables.get("SIDECAR_INPUT_MODE", "nats")

            # 获取默认配置模板
            config_template = collector.default_config.get(default_sidecar_mode, None)
            if not config_template:
                logger.info(f"Collector {collector.name} has no config template for mode {default_sidecar_mode}, skipping")
                return

            # 检查是否为容器节点
            is_container_node = node.node_type == ControllerConstants.NODE_TYPE_CONTAINER
            if is_container_node:
                add_config = collector.default_config.get("add_config", "")
                if add_config:
                    config_template = config_template + "\n" + add_config
                    logger.info(f"Node {node.id} is a container node, appending add_config for {collector.name}")

            # 渲染模板
            tpl = build_sandboxed_env().from_string(config_template)
            rendered_config = tpl.render(variables)

            # 创建配置
            configuration = CollectorConfiguration.objects.create(
                name=f"{collector.name}-{node.id}",
                collector=collector,
                config_template=rendered_config,
                is_pre=True,
                cloud_region=node.cloud_region,
            )
            configuration.nodes.add(node)
            logger.info(f"Created default configuration for node {node.id} and collector {collector.name}")

        except BaseAppException:
            raise
        except Exception as e:
            logger.error(f"Failed to create default config for node {node.id} and collector {collector.name}: {e}")
            raise BaseAppException(f"节点 {node.id} 自动创建 {collector.name} 父配置失败: {e}") from e

    @staticmethod
    def get_node_list(
        organization_ids,
        cloud_region_id,
        name,
        ip,
        os,
        page,
        page_size,
        is_active,
        is_manual,
        is_container,
        permission_data={},
        skip_permission=False,
    ):
        """获取节点列表"""
        if permission_data:
            permission, scope = NodeService._build_scoped_permission(permission_data)
            # 如果提供了权限信息，使用权限过滤
            if scope is None:
                qs = Node.objects.none()
            else:
                qs = (
                    permission_filter(
                        Node,
                        permission,
                        team_key="nodeorganization__organization__in",
                        id_key="id__in",
                    )
                    .filter(nodeorganization__organization__in=scope.data_team_ids)
                    .distinct()
                )
        elif skip_permission or organization_ids:
            # 系统级调用显式跳过权限检查，或通过 organization_ids 限定范围
            qs = Node.objects.all()
        else:
            # 无权限上下文且无组织限定时，拒绝返回数据（fail-closed）
            qs = Node.objects.none()

        if cloud_region_id:
            qs = qs.filter(cloud_region_id=cloud_region_id)
        if organization_ids:
            qs = qs.filter(nodeorganization__organization__in=organization_ids).distinct()
        if name:
            qs = qs.filter(name__icontains=name)
        if ip:
            qs = qs.filter(ip__icontains=ip)
        if os:
            qs = qs.filter(operating_system__icontains=os)

        # 根据 tags 判断是否自动安装节点
        if is_manual is not None:
            if is_manual is True:
                qs = qs.filter(install_method=ControllerConstants.MANUAL)
            else:
                qs = qs.exclude(install_method=ControllerConstants.MANUAL)

        # 根据 tags 判断是否容器节点
        if is_container is not None:
            if is_container:
                qs = qs.filter(node_type=ControllerConstants.NODE_TYPE_CONTAINER)
            else:
                qs = qs.exclude(node_type=ControllerConstants.NODE_TYPE_CONTAINER)

        # 获取当前时间前一分钟的utc时间
        now = datetime.now(timezone.utc)
        one_minute_ago = now - timedelta(minutes=1)
        if is_active is True:
            qs = qs.filter(updated_at__gte=one_minute_ago)
        elif is_active is False:
            qs = qs.filter(updated_at__lt=one_minute_ago)

        count = qs.count()
        page = NodeService._normalize_page(page)
        page_size = NodeService._normalize_page_size(page_size)
        start = (page - 1) * page_size
        end = start + page_size
        nodes = qs[start:end]

        # 应用预加载优化，避免 N+1 查询
        nodes = NodeSerializer.setup_eager_loading(nodes)

        serializer = NodeSerializer(nodes, many=True)
        node_data = serializer.data
        return dict(count=count, nodes=node_data)

    @staticmethod
    def get_nodes_by_ips(
        ips,
        *,
        organization_ids=None,
        cloud_region_id=None,
        permission_data=None,
        skip_permission=False,
    ):
        """按 IP 集合精确查询 Job 执行所需的最小节点信息。"""
        if not isinstance(ips, (list, tuple, set)):
            raise BaseAppException("ips 必须是 IP 列表")
        if len(ips) > NodeService.NODE_LIST_PAGE_SIZE_MAX:
            raise BaseAppException(f"单次最多查询 {NodeService.NODE_LIST_PAGE_SIZE_MAX} 个 IP")
        normalized_ips = set()
        for ip in ips:
            if not isinstance(ip, str) or not ip.strip() or len(ip) > 64:
                raise BaseAppException("ips 只能包含非空 IP 字符串")
            try:
                normalized_ips.add(str(ipaddress.ip_address(ip.strip())))
            except ValueError as error:
                raise BaseAppException(f"非法 IP: {ip}") from error
        normalized_ips = sorted(normalized_ips)
        if not normalized_ips:
            return {"nodes": []}

        permission_data = permission_data or {}
        if not isinstance(permission_data, dict):
            raise BaseAppException("permission_data 参数非法")
        organization_ids = organization_ids or []
        if organization_ids:
            organization_ids = list(_normalize_organization_ids(organization_ids))
        if permission_data:
            permission, scope = NodeService._build_scoped_permission(permission_data)
            if scope is None:
                qs = Node.objects.none()
            else:
                qs = (
                    permission_filter(
                        Node,
                        permission,
                        team_key="nodeorganization__organization__in",
                        id_key="id__in",
                    )
                    .filter(nodeorganization__organization__in=scope.data_team_ids)
                    .distinct()
                )
        elif skip_permission is True or organization_ids:
            qs = Node.objects.all()
        else:
            qs = Node.objects.none()

        if organization_ids:
            qs = qs.filter(nodeorganization__organization__in=organization_ids).distinct()
        if cloud_region_id:
            qs = qs.filter(cloud_region_id=cloud_region_id)
        nodes = list(qs.filter(ip__in=normalized_ips).order_by("ip", "id").values("id", "ip", "operating_system"))
        return {"nodes": nodes}

    @staticmethod
    def get_nodes_with_child_config(node_ids, collector, collect_type):
        """返回关联了指定采集器子配置的节点 ID。"""
        normalized_node_ids = list({str(node_id) for node_id in node_ids if node_id not in (None, "")})
        if not normalized_node_ids:
            return []
        if len(normalized_node_ids) > NodeService.NODE_LIST_PAGE_SIZE_MAX:
            raise BaseAppException(f"单次最多查询 {NodeService.NODE_LIST_PAGE_SIZE_MAX} 个节点")

        configured_node_ids = ChildConfig.objects.filter(
            collector_config__nodes__id__in=normalized_node_ids,
            collector_config__collector__name=collector,
            collect_type=collect_type,
        ).values_list("collector_config__nodes__id", flat=True)
        return sorted(set(configured_node_ids))

    @staticmethod
    def _normalize_page(page):
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 1
        return max(1, page)

    @staticmethod
    def _normalize_page_size(page_size):
        try:
            page_size = int(page_size)
        except (TypeError, ValueError):
            page_size = 10
        if page_size == -1:
            return NodeService.NODE_LIST_PAGE_SIZE_MAX
        return max(1, min(page_size, NodeService.NODE_LIST_PAGE_SIZE_MAX))

    @staticmethod
    def get_authorized_nodes_by_ids(node_ids, permission_data=None):
        if not node_ids:
            return []

        permission_data = permission_data or {}
        normalized_node_ids = list({str(node_id) for node_id in node_ids if node_id not in (None, "")})
        if not normalized_node_ids:
            return []

        if permission_data:
            permission, scope = NodeService._build_scoped_permission(permission_data)
            if scope is None:
                qs = Node.objects.none()
            else:
                qs = (
                    permission_filter(
                        Node,
                        permission,
                        team_key="nodeorganization__organization__in",
                        id_key="id__in",
                    )
                    .filter(nodeorganization__organization__in=scope.data_team_ids)
                    .distinct()
                )
        else:
            qs = Node.objects.none()

        nodes = qs.filter(id__in=normalized_node_ids).distinct().prefetch_related("nodeorganization_set")
        return [
            {
                "id": node.id,
                "name": node.name,
                "ip": node.ip,
                "node_type": node.node_type,
                "organization_ids": [rel.organization for rel in node.nodeorganization_set.all()],
            }
            for node in nodes
        ]

    @staticmethod
    def get_node_names_by_ids(node_ids):
        normalized_node_ids = list({str(node_id) for node_id in node_ids if node_id not in (None, "")})
        if not normalized_node_ids:
            return []

        return list(Node.objects.filter(id__in=normalized_node_ids).values("id", "name"))

    @staticmethod
    def get_nodes_by_ids(node_ids):
        normalized_node_ids = list({str(node_id) for node_id in node_ids if node_id not in (None, "")})
        if not normalized_node_ids:
            return []

        nodes = list(Node.objects.filter(id__in=normalized_node_ids).select_related("cloud_region").prefetch_related("nodeorganization_set"))
        region_display_ips = load_region_display_ips(
            {node.cloud_region_id for node in nodes if node.node_type == ControllerConstants.NODE_TYPE_CONTAINER}
        )
        return [
            {
                "id": node.id,
                "name": node.name,
                "ip": node.ip,
                "cloud_region_id": node.cloud_region_id,
                "cloud_region_name": getattr(node.cloud_region, "name", ""),
                "node_type": node.node_type,
                "operating_system": node.operating_system,
                "organization_ids": [rel.organization for rel in node.nodeorganization_set.all()],
                "region_display_ip": region_display_ips.get(node.cloud_region_id, ""),
            }
            for node in nodes
        ]

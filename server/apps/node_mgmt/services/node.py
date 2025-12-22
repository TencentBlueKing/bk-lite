from datetime import timezone

from apps.core.utils.permission_utils import get_permission_rules
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import NodeCollectorInstallStatus
from apps.node_mgmt.models.sidecar import Node, Collector, CollectorConfiguration, Action
from apps.node_mgmt.serializers.node import NodeSerializer
from datetime import datetime, timedelta

from apps.system_mgmt.models import User
from apps.core.logger import node_logger as logger
from apps.node_mgmt.services.sidecar import Sidecar
from jinja2 import Template as JinjaTemplate


class NodeService:
    @staticmethod
    def process_node_data(node_data):
        """处理节点数据列表，并补充每个节点的采集器名称和采集器配置名称"""
        configuration_ids = set()

        # 收集所有需要的 collector_id 和 configuration_id
        for node in node_data:
            if 'collectors' not in node['status']:
                continue
            for collector in node['status']['collectors']:
                configuration_ids.add(collector['configuration_id'])

        # 批量查询所有需要的 Collector 和 CollectorConfiguration
        collectors = Collector.objects.all()
        collector_dict = {collector.id: collector for collector in collectors}

        configurations = CollectorConfiguration.objects.filter(id__in=configuration_ids)
        configuration_dict = {config.id: config for config in configurations}

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


            node_install_map.setdefault(obj.node_id, []).append(
                dict(collector_id=obj.collector_id, status=status, message=obj.result)
            )

        # 处理节点数据
        for node in node_data:
            node_collector_install = node_install_map.get(node["id"], [])
            if node_collector_install:
                # 为 collectors_install 中的每个项添加 collector_name
                for install_item in node_collector_install:
                    collector_obj = collector_dict.get(install_item['collector_id'])
                    install_item['collector_name'] = collector_obj.name if collector_obj else None

                node["status"]["collectors_install"] = node_collector_install

            if 'collectors' not in node['status']:
                continue

            # 处理采集器状态：忽略不支持空跑的采集器的特定错误，将其状态改为正常
            for collector in node['status']['collectors']:
                collector_obj = collector_dict.get(collector['collector_id'])
                collector['collector_name'] = collector_obj.name if collector_obj else None

                configuration_obj = configuration_dict.get(collector['configuration_id'])
                collector['configuration_name'] = configuration_obj.name if configuration_obj else None

                # 判断是否应该将错误状态改为正常
                if collector['status'] == 2 and collector_obj:  # status=2 表示失败
                    # 检查是否是需要忽略错误的采集器
                    if collector_obj.name in CollectorConstants.IGNORE_ERROR_COLLECTORS:
                        # 检查错误信息是否匹配需要忽略的消息
                        verbose_msg = collector.get('verbose_message', '')
                        if verbose_msg in CollectorConstants.IGNORE_ERROR_COLLECTORS_MESSAGES:
                            # 将状态从失败改为正常
                            collector['status'] = 0
                            collector['message'] = 'Running'
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
            collector_configuration = CollectorConfiguration.objects.select_related('collector').get(
                id=collector_configuration_id)
            collector = collector_configuration.collector

            nodes = Node.objects.filter(id__in=node_ids).prefetch_related('collectorconfiguration_set')
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
    def batch_operate_node_collector(node_ids, collector_id, operation):
        """批量操作节点采集器"""
        # 一次性查询所有节点，避免重复查询
        nodes = Node.objects.filter(id__in=node_ids).select_related('cloud_region')

        # 如果是 start 或 restart 操作，需要检查并创建默认配置
        if operation in ['start', 'restart']:
            try:
                collector = Collector.objects.get(id=collector_id)

                # 批量查询已有配置的节点，避免N+1查询
                nodes_with_config = CollectorConfiguration.objects.filter(
                    collector=collector,
                    nodes__in=nodes
                ).values_list('nodes__id', flat=True)

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
                "properties": {operation: True}
            }
            action, created = Action.objects.get_or_create(node=node)
            action.action.append(action_data)
            action.save()

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
            tpl = JinjaTemplate(config_template)
            rendered_config = tpl.render(variables)

            # 创建配置
            configuration = CollectorConfiguration.objects.create(
                name=f'{collector.name}-{node.id}',
                collector=collector,
                config_template=rendered_config,
                is_pre=True,
                cloud_region=node.cloud_region
            )
            configuration.nodes.add(node)
            logger.info(f"Created default configuration for node {node.id} and collector {collector.name}")

        except Exception as e:
            logger.error(f"Failed to create default config for node {node.id} and collector {collector.name}: {e}")

    @staticmethod
    def get_node_list(organization_ids, cloud_region_id, name, ip, os, page, page_size, is_active, is_manual, is_container, permission_data={}):
        """获取节点列表"""
        if permission_data:
            user_obj = User(username=permission_data["username"], domain=permission_data["domain"])
            from apps.core.utils.permission_utils import permission_filter
            permission = get_permission_rules(
                user_obj,
                permission_data["current_team"],
                "node_mgmt",
                NodeConstants.MODULE,
            )
            # 如果提供了权限信息，使用权限过滤
            qs = permission_filter(Node, permission, team_key="nodeorganization__organization__in", id_key="id__in")
        else:
            # 兼容原有调用方式
            qs = Node.objects.all()

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
        if page_size == -1:
            nodes = qs
        else:
            start = (page - 1) * page_size
            end = start + page_size
            nodes = qs[start:end]

        # 应用预加载优化，避免 N+1 查询
        nodes = NodeSerializer.setup_eager_loading(nodes)

        serializer = NodeSerializer(nodes, many=True)
        node_data = serializer.data
        return dict(count=count, nodes=node_data)

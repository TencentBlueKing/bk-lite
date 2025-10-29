from datetime import timezone
import time

from apps.core.logger import node_logger
from apps.core.utils.permission_utils import get_permission_rules
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import NodeCollectorInstallStatus
from apps.node_mgmt.models.sidecar import Node, Collector, CollectorConfiguration, Action
from apps.node_mgmt.serializers.node import NodeSerializer
from datetime import datetime, timedelta

from apps.system_mgmt.models import User


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
                dict( collector_id=obj.collector_id, status=status, message=obj.result)
            )

        # 处理节点数据
        for node in node_data:
            node_collector_install = node_install_map.get(node["id"], [])
            if node_collector_install:
                node["status"]["collectors_install"] = node_collector_install
            if 'collectors' not in node['status']:
                continue
            for collector in node['status']['collectors']:
                collector_obj = collector_dict.get(collector['collector_id'])
                collector['collector_name'] = collector_obj.name if collector_obj else None

                configuration_obj = configuration_dict.get(collector['configuration_id'])
                collector['configuration_name'] = configuration_obj.name if configuration_obj else None

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
        nodes = Node.objects.filter(id__in=node_ids)
        for node in nodes:
            action_data = {
                "collector_id": collector_id,
                "properties": {operation: True}
            }
            action, created = Action.objects.get_or_create(node=node)
            action.action.append(action_data)
            action.save()

    @staticmethod
    def get_node_list(organization_ids, cloud_region_id, name, ip, os, page, page_size, is_active, permission_data={}):
        """获取节点列表"""
        start_time = time.time()
        node_logger.info(f"[get_node_list] 开始查询节点列表, 参数: organization_ids={organization_ids}, cloud_region_id={cloud_region_id}, name={name}, ip={ip}, os={os}, page={page}, page_size={page_size}, is_active={is_active}, has_permission={bool(permission_data)}")

        if permission_data:
            step_start = time.time()
            user_obj = User(username=permission_data["username"], domain=permission_data["domain"])

            from apps.core.utils.permission_utils import permission_filter
            permission = get_permission_rules(
                user_obj,
                permission_data["current_team"],
                "node_mgmt",
                NodeConstants.MODULE,
            )
            node_logger.info(f"[get_node_list] 权限规则获取完成, 耗时: {time.time() - step_start:.3f}s")

            step_start = time.time()
            # 如果提供了权限信息，使用权限过滤
            qs = permission_filter(Node, permission, team_key="nodeorganization__organization__in", id_key="id__in")
            node_logger.info(f"[get_node_list] 权限过滤完成, 耗时: {time.time() - step_start:.3f}s")
        else:
            # 兼容原有调用方式
            qs = Node.objects.all()

        step_start = time.time()
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
        node_logger.info(f"[get_node_list] 筛选条件应用完成, 耗时: {time.time() - step_start:.3f}s")

        step_start = time.time()
        # 获取当前时间前一分钟的utc时间
        now = datetime.now(timezone.utc)
        one_minute_ago = now - timedelta(minutes=1)
        if is_active is True:
            qs = qs.filter(updated_at__gte=one_minute_ago)
        elif is_active is False:
            qs = qs.filter(updated_at__lt=one_minute_ago)
        node_logger.info(f"[get_node_list] 活跃度筛选完成, 耗时: {time.time() - step_start:.3f}s")

        step_start = time.time()
        count = qs.count()
        node_logger.info(f"[get_node_list] 总数统计完成, count={count}, 耗时: {time.time() - step_start:.3f}s")

        step_start = time.time()
        if page_size == -1:
            nodes = qs
        else:
            start = (page - 1) * page_size
            end = start + page_size
            nodes = qs[start:end]
        node_logger.info(f"[get_node_list] 分页数据获取完成, 实际获取数量={len(nodes)}, 耗时: {time.time() - step_start:.3f}s")

        step_start = time.time()
        serializer = NodeSerializer(nodes, many=True)
        node_logger.info(f"[get_node_list] 序列化初始化完成, 耗时: {time.time() - step_start:.3f}s")

        step_start = time.time()
        # 如果有权限信息，为每个节点添加权限
        node_data = serializer.data
        node_logger.info(f"[get_node_list] 序列化数据提取完成, 耗时: {time.time() - step_start:.3f}s")

        total_time = time.time() - start_time
        node_logger.info(f"[get_node_list] 查询完成, 总耗时: {total_time:.3f}s")

        return dict(count=count, nodes=node_data)

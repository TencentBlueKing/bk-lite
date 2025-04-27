from apps.node_mgmt.models.sidecar import Node, CollectorConfiguration


class CollectorConfigurationService:
    @staticmethod
    def apply_to_node(node_id, collector_configuration_id):
        """将采集器配置应用到指定节点"""
        try:
            node = Node.objects.get(id=node_id)
            collector_configuration = CollectorConfiguration.objects.get(id=collector_configuration_id)
            collector = collector_configuration.collector

            # 检查节点是否已经有该配置文件对应的采集器关联的配置文件
            existing_configurations = node.collectorconfiguration_set.filter(collector=collector)
            if existing_configurations.exists():
                # 覆盖现有配置文件
                for config in existing_configurations:
                    config.nodes.remove(node)

            # 添加新的配置文件
            collector_configuration.nodes.add(node)
            collector_configuration.save()
        except Node.DoesNotExist:
            return False, f"节点{node_id}不存在"
        except CollectorConfiguration.DoesNotExist:
            return False, f"采集器配置{collector_configuration_id}不存在"
        return True, ""

    @staticmethod
    def calculate_node_count(configurations):
        """补充字段：已经应用了该配置文件的节点数量"""
        node_ids = {node_id for config in configurations for node_id in config['nodes']}
        nodes = Node.objects.filter(id__in=node_ids).values('id', 'status')

        node_status_map = {node['id']: node['status'] for node in nodes}

        for config in configurations:
            apply_node_count = 0
            applied_nodes = []
            for node_id in config['nodes']:
                node_status = node_status_map.get(node_id, {})
                if 'collectors' in node_status:
                    for collector in node_status['collectors']:
                        if config['id'] in collector.get('configuration_id', []):
                            apply_node_count += 1
                            applied_nodes.append(node_id)
            config['node_count'] = apply_node_count
            # 计算未应用的节点
            config['not_applied_nodes'] = list(set(config['nodes']) - set(applied_nodes))
            # 仅保留已经应用的节点
            config['nodes'] = applied_nodes
        return configurations

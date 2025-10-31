from apps.rpc.base import RpcClient, AppClient


class NodeMgmt(object):
    def __init__(self, is_local_client=False):
        self.client = AppClient("apps.node_mgmt.nats.node") if is_local_client else RpcClient()

    def get_module_data(self, **kwargs):
        """
        :param module: 模块
        :param child_module: 子模块
        :param page: 页码
        :param page_size: 页条目数
        :param group_id: 组ID
        """
        return_data = self.client.run("get_node_module_data", **kwargs)
        return return_data

    def get_module_list(self, **kwargs):
        """
        :param module: 模块
        :return: 模块的枚举值列表
        """
        return_data = self.client.run("get_node_module_list", **kwargs)
        return return_data

    def cloud_region_list(self):
        """
        :return: 云区域列表
        """
        return_data = self.client.run("cloud_region_list")
        return return_data

    def node_list(self, query_data):
        """
        :param query_data: 查询条件
        {
            "cloud_region_id": 1,
            "organization_ids": ["1", "2"],
            "name": "node_name",
            "ip": "10.10.10.1",
            "os": "linux/windows",
            "page": 1,
            "page_size": 10,
        }
        """
        return_data = self.client.run("node_list", query_data)
        return return_data

    def batch_create_configs_and_child_configs(self, configs: list, child_configs: list):
        """
        批量创建配置和子配置
        :param configs: 配置列表
        :param child_configs: 子配置列表
        """
        return_data = self.client.run("batch_create_configs_and_child_configs", configs, child_configs)
        return return_data

    def batch_add_node_child_config(self, configs: list):
        """
        批量创建子配置
        :param configs: 配置列表，每个配置包含以下字段：
            - id: 子配置ID
            - collect_type: 采集类型
            - type: 配置类型
            - content: 配置内容
            - node_id: 节点ID
            - collector_name: 采集器名称
            - env_config: 环境变量配置（可选）
            - sort_order: 排序（可选）
        """
        return_data = self.client.run("batch_add_node_child_config", configs)
        return return_data

    def batch_add_node_config(self, configs: list):
        """
        批量创建配置
        :param configs: 配置列表，每个配置包含以下字段：
            - id: 配置ID
            - name: 配置名称
            - content: 配置内容
            - node_id: 节点ID
            - collector_name: 采集器名称
            - env_config: 环境变量配置（可选）
        """
        return_data = self.client.run("batch_add_node_config", configs)
        return return_data

    def get_child_configs_by_ids(self, ids):
        """
        :param ids: 子配置ID列表
        """
        return_data = self.client.run("get_child_configs_by_ids", ids)
        return return_data

    def get_configs_by_ids(self, ids):
        """
        :param ids: 配置ID列表
        """
        return_data = self.client.run("get_configs_by_ids", ids)
        return return_data

    def update_child_config_content(self, id, content, env_config=None):
        """
        :param id: 子配置ID
        :param content: 子配置内容
        """
        return_data = self.client.run("update_child_config_content", {"id": id, "content": content, "env_config": env_config})
        return return_data

    def update_config_content(self, id, content, env_config=None):
        """
        :param id: 配置ID
        :param content: 配置内容
        """
        return_data = self.client.run("update_config_content", {"id": id, "content": content, "env_config": env_config})
        return return_data

    def delete_child_configs(self, ids):
        """
        :param ids: 子配置ID列表
        """
        return_data = self.client.run("delete_child_configs", ids)
        return return_data

    def delete_configs(self, ids):
        """
        :param ids: 配置ID列表
        """
        return_data = self.client.run("delete_configs", ids)
        return return_data

    def collectors_import(self, collectors: list):
        """
        导入采集器
        :param collectors: 采集器列表
        """
        return_data = self.client.run("import_collectors", collectors)
        return return_data

    def cloudregion_tls_env_by_node_id(self, node_id):
        """
        获取节点对应云区域的TLS配置
        :param node_id: 节点ID
        """
        return_data = self.client.run("cloudregion_tls_env_by_node_id", node_id)
        return return_data

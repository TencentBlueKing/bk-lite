import os

from apps.rpc.base import RpcClient, AppClient


class CMDB(object):
    def __init__(self, is_local_client=False):
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        self.client = (
            AppClient("apps.cmdb.nats.nats") if is_local_client else RpcClient()
        )

    def get_module_data(self, **kwargs):
        """
        :param module: 模块
        :param child_module: 子模块
        :param page: 页码
        :param page_size: 页条目数
        :param group_id: 组ID
        """
        return_data = self.client.run("get_cmdb_module_data", **kwargs)
        return return_data

    def get_module_list(self, **kwargs):
        """
        :param module: 模块
        :return: 模块的枚举值列表
        """
        return_data = self.client.run("get_cmdb_module_list", **kwargs)
        return return_data

    def search_instances(self, **kwargs):
        """
        告警丰富查询CMDB接口
        :return: 模块的枚举值列表
        """
        return_data = self.client.run("search_instances", **kwargs)
        return return_data

    def search_instances_batch(self, **kwargs):
        """告警丰富批量查询 CMDB 实例。"""
        return self.client.run("search_instances_batch", **kwargs)

    def list_instances(self, **kwargs):
        """
        查询单个模型下的实例列表（分页 + 过滤）
        :param params: {"model_id": .., "params": [..], "page": .., "page_size": .., "order": "", "format": True}
        :return: {"count": .., "items": [..]}
        """
        return self.client.run("list_instances", **kwargs)

    def search_model_attrs(self, **kwargs):
        """
        查询模型属性列表
        :param params: {"model_id": ..}
        """
        return self.client.run("search_model_attrs", **kwargs)

    def search_models(self, **kwargs):
        """
        查询模型列表
        :param params: {"classification_id": .., "include_hidden": False}
        """
        return self.client.run("search_models", **kwargs)

    def search_classifications(self, **kwargs):
        """
        查询模型分类列表
        :param params: {"include_hidden": False}
        """
        return self.client.run("search_classifications", **kwargs)

    def search_model_associations(self, **kwargs):
        """
        查询模型关联定义
        :param params: {"model_id": ..}
        """
        return self.client.run("search_model_associations", **kwargs)

    def search_instance_associations(self, **kwargs):
        """
        查询实例关联列表
        :param params: {"model_id": .., "inst_id": ..}
        """
        return self.client.run("search_instance_associations", **kwargs)

    def create_instance_association(self, **kwargs):
        """
        创建实例关联
        :param params: {"src_inst_id": .., "dst_inst_id": .., "model_asst_id": .., "operator": ..}
        """
        return self.client.run("create_instance_association", **kwargs)

    def delete_instance_association(self, **kwargs):
        """
        删除实例关联
        :param params: {"asso_id": .., "operator": ..}
        """
        return self.client.run("delete_instance_association", **kwargs)

    def sync_display_fields(self, **kwargs):
        """
        同步组织/用户的 _display 字段
        :param organizations: 组织变更数据列表 [{"id": 1, "name": "新组织名"}]
        :param users: 用户变更数据列表 [{"id": 1, "username": "admin", "display_name": "新显示名"}]
        :return: 任务提交结果 {"task_id": "uuid", "status": "submitted"}
        """
        return_data = self.client.run("sync_display_fields", **kwargs)
        return return_data

    def model_inst_count(self, **kwargs):
        """
        获取模型实例数量
        :return: 模型实例数量
        """
        return_data = self.client.run("model_inst_count", **kwargs)
        return return_data
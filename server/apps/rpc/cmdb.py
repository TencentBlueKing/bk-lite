import os

from apps.rpc.base import AppClient, RpcClient


class CMDB(object):
    def __init__(self, is_local_client=False):
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        self.client = AppClient("apps.cmdb.nats.nats") if is_local_client else RpcClient()

    def _run_params_handler(self, method_name, kwargs):
        transport_keys = {"_timeout", "_raw"}
        transport_kwargs = {key: kwargs[key] for key in transport_keys if key in kwargs} if isinstance(self.client, RpcClient) else {}
        payload_kwargs = {key: value for key, value in kwargs.items() if key not in transport_keys}
        params = payload_kwargs.pop("params", None)
        if isinstance(params, dict):
            conflicts = sorted(set(params).intersection(payload_kwargs))
            if conflicts:
                raise ValueError(f"CMDB RPC params conflict: {conflicts}")
            params = {**params, **payload_kwargs}
        elif params is None:
            params = payload_kwargs
        else:
            # list_instances 的业务查询条件也名为 params；它不是 RPC envelope。
            params = {"params": params, **payload_kwargs}
        return self.client.run(method_name, params=params, **transport_kwargs)

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
        告警丰富查询CMDB接口（UUID 定位）
        :param kwargs/params: {"protocol_version": "2", "model_id": .., "inst_uuid": .., "inst_name": .., "organization_ids": [..]}
        """
        return_data = self._run_params_handler("search_instances", kwargs)
        return return_data

    def search_instances_batch(self, **kwargs):
        """告警丰富批量查询 CMDB 实例（UUID）。
        :param kwargs/params: {"protocol_version": "2", "model_id": .., "inst_uuids": [..], "inst_names": [..], "organization_ids": [..]}
        """
        return self._run_params_handler("search_instances_batch", kwargs)

    def list_instances(self, **kwargs):
        """
        查询单个模型下的实例列表（分页 + 过滤，返回不含图 _id）
        :param params: {"protocol_version": "2", "model_id": .., "organization_ids": [..],
                        "params": [..], "page": .., "page_size": .., "order": "", "format": True}
        :return: {"count": .., "items": [..]}
        """
        return self._run_params_handler("list_instances", kwargs)

    def search_model_attrs(self, **kwargs):
        """
        查询模型属性列表
        :param params: {"model_id": ..}
        """
        return self._run_params_handler("search_model_attrs", kwargs)

    def search_models(self, **kwargs):
        """
        查询模型列表
        :param params: {"classification_id": .., "include_hidden": False}
        """
        return self._run_params_handler("search_models", kwargs)

    def search_classifications(self, **kwargs):
        """
        查询模型分类列表
        :param params: {"include_hidden": False}
        """
        return self._run_params_handler("search_classifications", kwargs)

    def search_model_associations(self, **kwargs):
        """
        查询模型关联定义
        :param params: {"model_id": ..}
        """
        return self._run_params_handler("search_model_associations", kwargs)

    def search_instance_associations(self, **kwargs):
        """
        查询实例关联列表
        :param params: {"protocol_version": "2", "model_id": .., "inst_uuid": .., "organization_ids": [..]}
        """
        return self._run_params_handler("search_instance_associations", kwargs)

    def create_instance_association(self, **kwargs):
        """
        创建实例关联
        :param params: {"protocol_version": "2", "src_inst_uuid": .., "dst_inst_uuid": .., "model_asst_id": .., "operator": ..}
        """
        return self._run_params_handler("create_instance_association", kwargs)

    def delete_instance_association(self, **kwargs):
        """
        删除实例关联（业务键）
        :param params: {"protocol_version": "2", "src_inst_uuid": .., "dst_inst_uuid": .., "model_asst_id": .., "operator": ..}
        """
        return self._run_params_handler("delete_instance_association", kwargs)

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

    def license_instance_count(self, **kwargs):
        """许可管理专用：原生自动发现的收费模型实例数量。"""
        return self.client.run("license_cmdb_instance_count", **kwargs)

    def get_monitor_ids_by_inst_uuids(self, **kwargs):
        return self.client.run("get_monitor_ids_by_inst_uuids", **kwargs)

    def ingest_from_source(self, **kwargs):
        """跨模块推送写入 CMDB（host：node_id 优先 + 存量认领）。

        NATS handler 签名为 ingest_from_source(params)，须整包为 params，
        不可把 envelope 字段摊成顶层 kwargs（否则 TypeError: unexpected keyword）。
        """
        return self.client.run("ingest_from_source", params=kwargs)

    def create_manual_config_files(self, **kwargs):
        """批量手动写入配置文件版本（UUID 定位，幂等跳过已有文件）。

        :param kwargs/params: {"protocol_version": "2", "allowed_org_ids": [..], "items": [..]}
        """
        return self._run_params_handler("create_manual_config_files", kwargs)

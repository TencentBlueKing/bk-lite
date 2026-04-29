# -- coding: utf-8 --
# @File: config_factory.py
# @Time: 2025/11/13 14:37
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class NodeParamsFactory:
    """
    工厂类，根据 instance 的 model_id 返回对应的 NodeParams 实例
    """

    @staticmethod
    def get_params_class(model_id, driver_type=None):
        model_id = model_id.replace("_account", "")
        # 优先按 (model_id, driver_type) 分流，确保 physcial_server 的 SSH/job 与 IPMI/protocol
        # 可以命中不同的 NodeParams 实现。
        params_cls = BaseNodeParams._registry.get((model_id, driver_type))
        if params_cls is None:
            # 兼容历史采集对象：如果某个 model 还没有 driver-specific 注册，则回退到旧实现。
            params_cls = BaseNodeParams._registry.get((model_id, None))
        if params_cls is None:
            raise ValueError(f"不支持的 model_id: {model_id}")
        return params_cls

    @staticmethod
    def get_node_params(instance):
        params_cls = NodeParamsFactory.get_params_class(instance.model_id, instance.driver_type)
        return params_cls(instance)

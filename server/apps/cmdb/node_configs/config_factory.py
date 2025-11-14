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
    def get_node_params(instance):
        params_cls = BaseNodeParams._registry.get(instance.model_id)
        if params_cls is None:
            raise ValueError(f"不支持的 model_id: {instance.model_id}")
        return params_cls(instance)

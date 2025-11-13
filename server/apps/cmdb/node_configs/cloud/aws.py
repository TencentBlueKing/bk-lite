# -- coding: utf-8 --
# @File: aws.py
# @Time: 2025/11/13 14:30
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class AWSNodeParams(BaseNodeParams):
    supported_model_id = "aws"
    plugin_name = "aws_info"
    interval = 300  # AWS采集间隔：300秒

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: "aws_info"})

    def set_credential(self, *args, **kwargs):
        """
        生成 AWS 的凭据
        """
        return {
            "access_key_id": self.credential.get("access_key_id", ""),
            "secret_access_key": self.credential.get("secret_access_key", ""),
        }

    def get_instance_id(self, instance):
        """
        获取实例 ID
        """
        return f"{self.instance.id}_{instance['inst_name']}"

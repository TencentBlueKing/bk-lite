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
        _access_key_id = f"PASSWORD_access_key_id_{self._instance_id}"
        _secret_access_key = f"PASSWORD_secret_access_key_{self._instance_id}"
        return {
            "access_key_id": "${" + _access_key_id + "}",
            "secret_access_key": "${" + _secret_access_key + "}",
        }

    def env_config(self, *args, **kwargs):
        env_config = {
            f"PASSWORD_access_key_id_{self._instance_id}": self.credential.get("access_key_id", ""),
            f"PASSWORD_secret_access_key_{self._instance_id}": self.credential.get("secret_access_key", ""),
        }
        return env_config

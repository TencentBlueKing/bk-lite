# -- coding: utf-8 --
# @File: aliyun.py
# @Time: 2025/11/13 14:24
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class AliyunNodeParams(BaseNodeParams):
    supported_model_id = "aliyun"
    plugin_name = "aliyun_info"
    interval = 300  # 阿里云采集间隔：300秒

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "endpoint"

    def set_credential(self, *args, **kwargs):
        _access_key = f"PASSWORD_access_key_{self._instance_id}"
        _access_secret = f"PASSWORD_access_secret_{self._instance_id}"
        regions_id = self.credential["regions"]["resource_id"]
        credential_data = {
            "access_key": "${" + _access_key + "}",
            "access_secret": "${" + _access_secret + "}",
            "region_id": regions_id
        }
        return credential_data

    def env_config(self, *args, **kwargs):
        env_config = {
            f"PASSWORD_access_key_{self._instance_id}": self.credential.get("accessKey", ""),
            f"PASSWORD_access_secret_{self._instance_id}": self.credential.get("accessSecret", ""),
        }
        return env_config

    @classmethod
    def build_region_credential(cls, raw_credential):
        """
        1. 保存任务的时候 迷失密钥是 accessKey 和 accessSecret
        2. 构建区域凭据的时候 迷失密钥是 access_key 和 access_secret

        {"model_id":"qcloud",
        "cloud_id":1,
        "access_key":"AKID5SmwvhSinodHixv4BF",
        "access_secret":"5762zpOSM5dz84vsla"}

        """
        raw_credential = raw_credential or {}
        access_key = raw_credential.pop("access_key", None)
        access_secret = raw_credential.pop("access_secret", None)
        return {
            "secret_id": access_key or raw_credential.get("accessKey", ""),
            "secret_key": access_secret or raw_credential.get("accessSecret"),
        }
    @property
    def password(self):
        # 返回腾讯云的密码数据
        return self.build_region_credential(self.credential)

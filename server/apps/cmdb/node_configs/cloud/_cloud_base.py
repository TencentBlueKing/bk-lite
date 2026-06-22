# -- coding: utf-8 --
"""私有云（ak/sk 风格）NodeParams 通用 Mixin。

补齐 hwcloud/openstack/manageone/smartx/fusioninsight 的「采集触发链路」：
此前这些云只在 collection/plugins 注册了「读取/落库」侧，缺 node_configs 的
NodeParams（采集下发侧），导致 NodeParamsFactory.get_params_class 抛
ValueError，采集器永不被触发。

下发给 stargazer 采集器的参数键，严格对齐各采集器 __init__ 读取的键：
  account  = params.get("username") or params.get("accessKey")
  password = params.get("password") or params.get("accessSecret")
  region   = params.get("region")
  host     = params.get("host")
凭据来自云任务凭据（accessKey/accessSecret + regions），host 来自所选平台实例的
endpoint/global_domain_name 或任务 params.host（见前端 cloudTask.tsx）。

Mixin 不直接继承 BaseNodeParams，避免触发其 __init_subclass__ 的空注册告警；
具体云类以 (CloudAkSkNodeParamsMixin, BaseNodeParams) 组合，由后者完成注册。
"""


class CloudAkSkNodeParamsMixin:
    interval = 300  # 云采集默认间隔（秒）

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 注册 model_id → plugin_name（与 aliyun/qcloud 一致）
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})

    def _region_id(self):
        """区域 ID：取自云凭据的 regions.resource_id（与 aliyun 一致）。"""
        regions = self.credential.get("regions") or {}
        if isinstance(regions, dict):
            return regions.get("resource_id", "") or ""
        return ""

    def _host_value(self):
        """平台地址：优先任务 params.host；否则取所选实例的 endpoint/global_domain_name。"""
        params = getattr(self.instance, "params", None) or {}
        if isinstance(params, dict) and params.get("host"):
            return params.get("host")
        instances = getattr(self.instance, "instances", None) or []
        if instances:
            first = instances[0] or {}
            return first.get("endpoint") or first.get("global_domain_name") or ""
        return ""

    def get_hosts(self):
        """以 'host' 为键下发平台地址（采集器读 params.get('host')），不走 hosts 拆分。"""
        return "host", self._host_value()

    def set_credential(self, *args, **kwargs):
        """ak/sk 经环境变量引用下发（密钥不落明文），region 随凭据下发。"""
        _ak = f"PASSWORD_access_key_{self._instance_id}"
        _sk = f"PASSWORD_access_secret_{self._instance_id}"
        credential_data = {
            "accessKey": "${" + _ak + "}",
            "accessSecret": "${" + _sk + "}",
        }
        region = self._region_id()
        if region:
            credential_data["region"] = region
        # project_id：华为云 SDK 构造必需；凭据/任务捕获到才下发（不臆造）
        project_id = self.credential.get("project_id", "") or ""
        if project_id:
            credential_data["project_id"] = project_id
        return credential_data

    def env_config(self, *args, **kwargs):
        return {
            f"PASSWORD_access_key_{self._instance_id}": self.credential.get("accessKey", ""),
            f"PASSWORD_access_secret_{self._instance_id}": self.credential.get("accessSecret", ""),
        }

    @classmethod
    def build_region_credential(cls, raw_credential):
        raw_credential = raw_credential or {}
        access_key = raw_credential.pop("access_key", None)
        access_secret = raw_credential.pop("access_secret", None)
        return {
            "accessKey": access_key or raw_credential.get("accessKey", ""),
            "accessSecret": access_secret or raw_credential.get("accessSecret", ""),
        }

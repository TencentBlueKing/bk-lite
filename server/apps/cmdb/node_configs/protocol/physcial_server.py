# -- coding: utf-8 --
from apps.cmdb.collection.physical_server_protocol import PHYSICAL_SERVER_PROTOCOLS, normalize_physical_server_protocol
from apps.cmdb.node_configs.base import BaseNodeParams


class PhysicalServerProtocolNodeParams(BaseNodeParams):
    supported_model_id = "physcial_server"
    supported_driver_type = "protocol"
    # 复用现有 physcial_server 插件目录，通过 protocol executor 分派带外采集协议。
    plugin_name = "physcial_server_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host_field = "ip_addr"
        self.executor_type = "protocol"
        self.collection_protocol = normalize_physical_server_protocol((self.instance.params or {}).get("collection_protocol"))
        if self.collection_protocol not in PHYSICAL_SERVER_PROTOCOLS:
            raise ValueError("物理服务器协议仅支持 ipmi 或 redfish")

    def _password_env_name(self, index=None):
        if index is None:
            return f"PASSWORD_password_{self._instance_id}"
        return f"PASSWORD_password_{self._instance_id}_{index}"

    def _build_credential_payload(self, credential, index=None):
        password_key = self._password_env_name(index)
        is_redfish = self.collection_protocol == "redfish"
        credential_data = {
            "port": credential.get("port", 443 if is_redfish else 623),
            "username": credential.get("username", credential.get("user", "")),
            "password": "${" + password_key + "}",
        }
        if is_redfish:
            credential_data["verify_tls"] = credential.get("verify_tls", True)
        else:
            privilege = credential.get("privilege")
            if privilege:
                credential_data["privilege"] = privilege
        for metadata_field in ("credential_id", "credential_version"):
            if credential.get(metadata_field) not in (None, ""):
                credential_data[metadata_field] = credential[metadata_field]
        return credential_data

    def set_credential(self, *args, **kwargs):
        credential_data = self._build_credential_payload(self.credential)
        is_redfish = self.collection_protocol == "redfish"
        credential_data.update(
            collection_protocol=self.collection_protocol,
            # Redfish 的端口与 TLS 策略属于每组凭据，目标级 HTTPS
            # 预检无法代表后续凭据，交给凭据级 probe/collect 处理。
            preflight_kind="none" if is_redfish else "snmp",
            preflight_kind_explicit=True,
            rotate_on_credential_failure=True,
        )
        if is_redfish:
            credential_data["ssl"] = True
        return credential_data

    def env_config(self, *args, **kwargs):
        if self.has_multiple_credentials:
            return {
                self._password_env_name(index): credential.get("password", "")
                for index, credential in enumerate(self.credential_pool or [])
                if isinstance(credential, dict)
            }
        return {self._password_env_name(): self.credential.get("password", "")}

    def build_credentials_pool(self):
        if not self.has_multiple_credentials:
            return []
        return [
            self._build_credential_payload(credential, index)
            for index, credential in enumerate(self.credential_pool or [])
            if isinstance(credential, dict)
        ]

    @staticmethod
    def strip_flattened_credential_fields(params, credentials_pool):
        if str(params.get("collection_protocol") or "ipmi").strip().lower() == "redfish":
            return BaseNodeParams.strip_flattened_credential_fields(params, credentials_pool)
        port = params.get("port")
        params = BaseNodeParams.strip_flattened_credential_fields(params, credentials_pool)
        if port not in (None, ""):
            params["port"] = port
        return params


# 保留旧导入名，避免企业扩展或存量测试直接导入时中断。
PhysicalServerIPMINodeParams = PhysicalServerProtocolNodeParams

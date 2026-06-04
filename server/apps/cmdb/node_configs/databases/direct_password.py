# -- coding: utf-8 --


class DirectPasswordNodeParamsMixin:
    default_port = None

    def set_credential(self, *args, **kwargs):
        return self._build_credential_payload(self.credential)

    def env_config(self, *args, **kwargs):
        if not self.credential:
            return {}
        env = {}
        if self.has_multiple_credentials:
            for index, credential in enumerate(self.credential_pool or []):
                env[self._password_env_name(index)] = credential.get("password", "")
        else:
            env[self._password_env_name()] = self.credential.get("password", "")
        return env

    def build_credentials_pool(self):
        if not self.has_multiple_credentials:
            return []
        return [
            self._build_credential_payload(credential, index)
            for index, credential in enumerate(self.credential_pool or [])
            if isinstance(credential, dict)
        ]

    def build_extra_credential_fields(self, credential):
        return {}

    def _build_credential_payload(self, credential, index=None):
        if not isinstance(credential, dict):
            return {}
        payload = {
            "port": credential.get("port", self.default_port),
            "user": credential.get("user", ""),
            "password": "${" + self._password_env_name(index) + "}",
        }
        if credential.get("credential_id"):
            payload["credential_id"] = credential.get("credential_id")
        payload.update(self.build_extra_credential_fields(credential))
        return payload

    def _password_env_name(self, index=None):
        if index is None:
            return f"PASSWORD_password_{self._instance_id}"
        return f"PASSWORD_password_{self._instance_id}_{index}"
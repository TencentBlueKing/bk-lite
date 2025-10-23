import base64
import os

import requests

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.crypto.password_crypto import PasswordCrypto


class ChatServerHelper(object):
    @staticmethod
    def get_user():
        """Encode the password using base64 encoding."""
        crypto = PasswordCrypto(os.getenv("SECRET_KEY"))
        user = {
            "admin": crypto.encrypt(os.getenv("ADMIN_PASSWORD")),
        }
        return user

    @classmethod
    def get_chat_server_header(cls):
        user = cls.get_user()
        # 返回header， basic auth
        username = "admin"
        password = user.get(username)
        if not password:
            return {}

        auth_string = f"{username}:{password}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        headers = {"Authorization": f"Basic {encoded_auth}"}
        return headers

    @classmethod
    def post_chat_server(cls, params, url, stream=False, timeout=300):
        headers = cls.get_chat_server_header()
        # SSL验证配置 - 从环境变量读取
        ssl_verify = os.getenv("METIS_SSL_VERIFY", "false").lower() == "true"
        try:
            response = requests.post(
                url, headers=headers, json=params, stream=stream, verify=ssl_verify, timeout=timeout
            )
        except Exception as e:
            logger.error(f"调用接口失败:  {url} ")
            logger.exception(e)
            return {}
        if response.status_code != 200:
            logger.error(f"调用接口失败: {response.status_code} {url} {response.text}")
            return {}
        result = response.json()
        if result.get("status", "success") != "success":
            logger.error(f"调用接口失败: {response.status_code} {url} {response.text}")
            return {}
        return result

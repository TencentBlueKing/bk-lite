import time

import requests

# 所有钉钉接口请求的超时时间（连接，读取），避免接口挂起时阻塞 worker
_REQUEST_TIMEOUT = (5, 10)
# access_token 过期前的提前刷新缓冲（秒）
_TOKEN_EXPIRY_BUFFER = 60


class DingTalkClient(object):
    def __init__(self, app_key, app_secret):
        self.app_key = app_key
        self.app_secret = app_secret
        # 复用 TCP 连接，减少握手开销
        self.session = requests.Session()
        self._access_token = None
        self._access_token_expire_at = 0.0

    def get_access_token(self):
        # 命中未过期的缓存则直接复用，避免每次请求都去换取 token
        now = time.time()
        if self._access_token and now < self._access_token_expire_at:
            return self._access_token

        url = "https://oapi.dingtalk.com/gettoken"
        params = {"appkey": self.app_key, "appsecret": self.app_secret}
        response = self.session.get(url, params=params, timeout=_REQUEST_TIMEOUT)
        data = response.json()
        if data.get("errcode") != 0:
            raise Exception(f"获取access_token失败: {data.get('errmsg')}")

        self._access_token = data["access_token"]
        # 钉钉默认 expires_in 为 7200 秒，预留缓冲提前刷新
        expires_in = data.get("expires_in", 7200)
        self._access_token_expire_at = now + max(expires_in - _TOKEN_EXPIRY_BUFFER, 0)
        return self._access_token

    def get_user_info(self, user_id):
        access_token = self.get_access_token()
        url = "https://oapi.dingtalk.com/topapi/v2/user/get"
        params = {"access_token": access_token, "userid": user_id}
        response = self.session.get(url, params=params, timeout=_REQUEST_TIMEOUT)
        data = response.json()
        if data.get("errcode") != 0:
            raise Exception(f"获取用户信息失败: {data.get('errmsg')}")
        return data["result"]

    def get_user_department(self, user_id):
        url = "https://oapi.dingtalk.com/topapi/v2/department/listparentbyuser"
        params = {"access_token": self.get_access_token()}
        kwargs = {"userid": user_id}
        response = self.session.post(url, params=params, json=kwargs, timeout=_REQUEST_TIMEOUT)
        data = response.json()
        if data.get("errcode") != 0:
            raise Exception(f"获取用户信息失败: {data.get('errmsg')}")
        return_data = []
        for i in data["result"].get("parent_list", []):
            return_data.extend(i.get("parent_dept_id_list", []))
        return list(set(return_data))

    def get_department_name(self, dept_id):
        url = "https://oapi.dingtalk.com/topapi/v2/department/get"
        params = {"access_token": self.get_access_token()}
        kwargs = {"dept_id": dept_id}
        response = self.session.post(url, params=params, json=kwargs, timeout=_REQUEST_TIMEOUT)
        data = response.json()
        if data.get("errcode") != 0:
            raise Exception(f"获取部门信息失败: {data.get('errmsg')}")
        return data["result"]["name"]

    def close(self):
        """关闭底层 requests.Session，释放连接池，避免 socket 泄漏。"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

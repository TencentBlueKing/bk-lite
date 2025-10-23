import requests


class DingTalkClient(object):
    def __init__(self, app_key, app_secret):
        self.app_key = app_key
        self.app_secret = app_secret

    def get_access_token(self):
        url = "https://oapi.dingtalk.com/gettoken"
        params = {"appkey": self.app_key, "appsecret": self.app_secret}
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("errcode") != 0:
            raise Exception(f"获取access_token失败: {data.get('errmsg')}")
        return data["access_token"]

    def get_user_info(self, user_id):
        access_token = self.get_access_token()
        url = "https://oapi.dingtalk.com/topapi/v2/user/get"
        params = {"access_token": access_token, "userid": user_id}
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("errcode") != 0:
            raise Exception(f"获取用户信息失败: {data.get('errmsg')}")
        return data["result"]

    def get_user_department(self, user_id):
        url = "https://oapi.dingtalk.com/topapi/v2/department/listparentbyuser"
        params = {"access_token": self.get_access_token()}
        kwargs = {"userid": user_id}
        response = requests.post(url, params=params, json=kwargs)
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
        response = requests.post(url, params=params, json=kwargs)
        data = response.json()
        if data.get("errcode") != 0:
            raise Exception(f"获取部门信息失败: {data.get('errmsg')}")
        return data["result"]["name"]

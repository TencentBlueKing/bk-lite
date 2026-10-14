# -*- coding: UTF-8 -*-
import base64
import json
import re

import requests
import rsa
from core.logger import logger



class CwTKE:
    def __init__(self, host, username, password, cluster, api_version, namespace=""):
        """
        初始化
        :param authorization: 认证令牌
        :param cluster: kubernetes 集群的名称
        :param namespace: 应用程序的名称空间
        """
        self.host = host
        self.username = username
        self.password = password
        self.cluster = cluster
        self.api_version = api_version
        self.namespace = namespace
        self.headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json;charset=UTF-8",
            "Accept-Language": "zh_CN",
            "Authorization": f"Bearer {self._log_on()}",
        }

    def __getattr__(self, method_name):
        params = {
            "host": self.host,
            "cluster": self.cluster,
            "headers": self.headers,
            "api_version": self.api_version,
            "namespace": self.namespace,
        }
        return TKE(name=method_name, **params)

    def _log_on(self, proto="https", auth="local", http_proxy=None):
        proxy = {"http": http_proxy, "https": http_proxy} if http_proxy else None
        headers = {"Referer": f"{proto}://{self.host}/console-acp"}
        response = requests.get(
            f"{proto}://{self.host}/console-acp/api/v1/token/login",
            headers=headers,
            proxies=proxy,
            timeout=10,
            verify=False,
        )
        resp_dict = response.json()
        auth_url, state = resp_dict.get("auth_url"), resp_dict.get("state")
        r2 = requests.get(auth_url, headers=headers, proxies=proxy, timeout=10, verify=False)
        req = re.findall(r"/dex/auth/{auth}\?req=(\w{1,})".replace("{auth}", auth), r2.text)[0]
        ret = requests.get(f"{proto}://{self.host}/dex/pubkey", proxies=proxy, verify=False)
        content = ret.json()
        ts_num = content.get("ts")
        pub_key = rsa.PublicKey.load_pkcs1_openssl_pem(content.get("pubkey"))
        data = {"ts": ts_num, "password": self.password}
        crypto = rsa.encrypt(json.dumps(data).encode("utf8"), pub_key)
        pwd = str(base64.b64encode(crypto), "utf8")
        r3 = requests.post(
            f"https://{self.host}/dex/auth/{auth}?req={req}",
            params={"req": req, "login": self.username, "encrypt": pwd},
            headers=headers,
            proxies=proxy,
            timeout=10,
            verify=False,
        )
        code = re.findall(r"code=(\w{1,})", r3.history[1].text)[0]
        r4 = requests.get(
            f"{proto}://{self.host}/console-acp/api/v1/token/callback",
            params={"code": code, "state": state},
            headers=headers,
            proxies=proxy,
            timeout=10,
            verify=False,
        )
        return r4.json().get("id_token")


class TKE:
    def __init__(self, name, **kwargs):
        self.name = name
        self.host = "http://" + kwargs.get("host")
        self.headers = kwargs.get("headers")
        self.cluster = kwargs.get("cluster")
        self.namespace = kwargs.get("namespace")
        self.api_version = kwargs.get("api_version")
        self.head_url = f"{self.host}/acp/v1/kubernetes/{self.cluster}"
        self.head_url_api = f"{self.host}/kubernetes/{self.cluster}/apis"

    def __getattr__(self, item):
        return {"result": False, "message": "请求的方法不存在"}

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @staticmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        url_par = f"{self.head_url_api}/{self.api_version}/namespaces/{self.namespace}/applications"
        rep = requests.get(url=url_par, headers=self.headers)
        if rep.status_code == 200:
            return {"result": True}
        else:
            return {"result": False}

    # ***********************  application应用  ******************************************
    def list_applications(self, names=None, path_par=""):
        """
        获取应用列表
        :param names:  应用列表名
        :param path_par: 拼接好的路径参数 eg：limit=20&keyword=tes&field=metadata.name
        :return:
        """
        if names:
            return self.get_application_spec(names[0])
        url_par = f"{self.head_url_api}/{self.api_version}/namespaces/{self.namespace}/applications"
        if url_par:
            url_par = f"{url_par}?{path_par}"
        rep = self.__handle_requests(url_par, "get")
        return self._handle_result_date(rep, "application")

    def get_application_spec(self, name):
        """
        获取name应用
        :param name: 应用名字
        :return:
        """
        url_par = f"{self.head_url}/namespaces/{self.namespace}/applications/{name}"
        rep = self.__handle_requests(url_par, "get")
        return self._handle_result_date(rep, "application")

    def create_application(self, dict_json):
        """
        创建应用
        :param dict_json: 创建应用的参数
        :return:
        """
        url_par = f"{self.head_url}/namespaces/{self.namespace}/applications"
        rep = self.__handle_requests(url_par, "post", dict_json)
        return self._handle_create_result(rep, "application")

    def delete_application(self, name):
        """
        删除应用
        :return:
        """
        url_par = f"{self.head_url_api}/{self.api_version}/namespaces/{self.namespace}/applications/{name}"
        rep = self.__handle_requests(url_par, "delete")
        return self._handle_delete_result(rep, "application")

    def update_application(self, name, data_json, force_update_pod="false"):
        """
        更新application
        :param name: 应用名
        :param data_json: 更新的json数据
        :param force_update_pod:
        :return:
        """
        url_par = f"{self.head_url}/namespaces/{self.namespace}/applications/{name}?forceUpdatePod={force_update_pod}"
        rep = self.__handle_requests(url_par, "put", data_json)
        return self._handle_update_result(rep, "application")

    # ***********************  deployment部署  ******************************************
    def list_deployments(self, names=None, path_par=""):
        """
        查看部署列表
        :param names:
        :param path_par:
        :return:
        """
        url_par = f"{self.head_url_api}/apps/v1/namespaces/{self.namespace}/deployments"
        if url_par:
            url_par = f"{url_par}?{path_par}"
        rep = self.__handle_requests(url_par, "get")
        return self._handle_result_date(rep, "deployment")

    def get_deployment_spec(self, name):
        """
        查看指定的部署的详细信息
        :param name:
        :return:
        """
        url_par = f"{self.head_url}/hpa/{self.namespace}/deployment/{name}"
        rep = self.__handle_requests(url_par, "get")
        return self._handle_result_date(rep, "deployment")

    @staticmethod
    def application_format(dict_data):
        result = dict_data
        return result

    @staticmethod
    def deployment_format(dict_data):
        return dict_data

    @staticmethod
    def _handle_create_result(rep, resource_name):
        if rep.ok:
            return {"result": True, "data": rep.json()}
        else:
            return {"result": False, "message": f"create {resource_name} fail"}

    @staticmethod
    def _handle_delete_result(rep, resource_name):
        if rep.ok:
            return {"result": True}
        else:
            return {"result": False, "message": f"delete {resource_name} fail"}

    @staticmethod
    def _handle_update_result(rep, resource_name):
        if rep.ok:
            return {"result": True, "data": rep.json()}
        else:
            return {"result": False, "message": f"update {resource_name} fail"}

    @classmethod
    def _handle_result_date(cls, rep, resource_name):
        """
        处理接口返回Response对象
        :param rep: Response对象
        :param resource_name: 资源名
        :return:
        """
        if rep.ok:
            dict_data = rep.json()
            return {"result": True, "data": getattr(cls, f"{resource_name}_format")(dict_data)}
        return {"result": False, "message": f"get {resource_name} fail"}

    def __handle_requests(self, url_par, request_method, params=None):
        """
        统一发送接口请求，获取接口返回数据
        :param request_method: 请求方法.
        :param url_par: 配置的 url 名称.
        :param params: 接口所需要的参数.
        :rtype: Response 对象
        """
        request_method = request_method.lower()
        if request_method == "get":
            rep = requests.get(url=url_par, headers=self.headers, params=params, verify=False)
        elif request_method == "post":
            rep = requests.post(url=url_par, headers=self.headers, json=params, verify=False)
        elif request_method == "put":
            rep = requests.put(url=url_par, headers=self.headers, data=params)
        elif request_method == "delete":
            rep = requests.delete(url=url_par, headers=self.headers, data=params)
        else:
            raise ValueError(f"{request_method} method not in ['get', 'create', 'put', 'delete'")
        return rep


if __name__ == "__main__":
    cw = CwTKE("1.14.47.204", "user@qq.com", "P$Pd5Q1a*x2i", "global", "app.k8s.io/v1beta1")
    print(getattr(cw, "list_applications")())

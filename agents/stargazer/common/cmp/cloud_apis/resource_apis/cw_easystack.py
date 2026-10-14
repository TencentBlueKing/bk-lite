# -*- coding: UTF-8 -*-
import json

import requests

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.cloud_constant import CloudPlatform
from common.cmp.cloud_apis.constant import CloudResourceType
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.cloud_apis.resource_apis.utils import fail, success
from core.logger import logger

https_port = "443"


class CwEasyStack(object):
    """
    通过该类创建EasyStack的Client实例，调用EasyStackapi接口
    注意是 HTTP 的协议，并不是 HTTPS
    """

    def __init__(self, username, password, region="", host="", **kwargs):
        """
        初始化方法，创建实例
        """
        self.username = username
        self.password = password
        self.region = region
        self.host = host
        self.https_port = kwargs.get("https_port", https_port)
        self.project_id = kwargs.pop("project_id")
        self.token = self._log_on("http://keystone.{}/v3/auth/tokens".format(self.host))

    def __getattr__(self, item):
        """
        private方法，返回对应的接口类
        """
        return EasyStack(
            name=item,
            project_id=self.project_id,
            host=self.host,
            username=self.username,
            password=self.password,
            https_port=self.https_port,
            token=self.token,
        )

    def _log_on(self, auth_url):
        """
        登录验证，认证方式为Token认证，通过Token认证通用请求
        """
        data = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {"user": {"id": self.username, "password": self.password}},
                },
                "scope": {"project": {"domain": {"name": "Default"}, "id": self.project_id}},
            }
        }
        headers = {"Content-Type": "application/json"}
        token = ""

        try:
            result = requests.post(auth_url, headers=headers, json=data)
        except Exception as e:
            logger.exception(e)
            return ""
        if result.status_code == 201 and "X-Subject-Token" in result.headers:
            token = result.headers["X-Subject-Token"]
        else:
            logger.error("easystack获取token失败,错误状态码{}, 请求url{}".format(result.status_code, auth_url))
            logger.error("请求体{}".format(data))
        return token


class EasyStack(PrivateCloudManage):
    """
    EasyStack接口类
    """

    def __init__(self, name, project_id, host, https_port, username, password, token):
        """
        初始化方法
        """
        self.project_id = project_id
        self.host = host
        self.https_port = https_port
        self.name = name
        self.username = username
        self.password = password
        self.token = token
        self.cw_headers = {
            "Content-Type": "application/json",
            "X-Auth-Token": self.token,
        }

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        """
        check if this object works.
        :return: A dict with a “key: value” pair of object. The key name is result, and the value is a boolean type.
        :rtype: dict
        """
        if self.token:
            return {"result": True}
        return {"result": False}

    def list_vms(self, ids="", **kwargs):
        """
        查询所有项目的云主机
        """
        # if ids:
        #     return self.get_vm_detail(ids[0])
        url = "http://nova.{}/v2.1/{}/servers/detail?all_tenants=1".format(self.host, self.project_id)
        headers = self.cw_headers
        return request_get_list(url, headers, "server", project_id=self.project_id)


# ***********************Common****************************************


resource_type_dict = {
    "network": CloudResourceType.VPC.value,
    "volume": CloudResourceType.DISK.value,
    "volume_type": "volume_type",
    "flavor": CloudResourceType.INSTANCE_TYPE.value,
    "server": CloudResourceType.VM.value,
}


def request_get_list(url, headers, resource_type, **kwargs):
    """
    list 请求格式方法
    """
    try:
        result = requests.get(url, verify=False, headers=headers)
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    data = []
    if result.status_code < 300:
        content = json.loads(result.content)
        for i in content.get(resource_type + "s", []):
            if resource_type in resource_type_dict:
                resource_type = resource_type_dict[resource_type]
            data.append(
                get_format_method(
                    CloudPlatform.EasyStack,
                    resource_type,
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i, **kwargs)
            )
        return success(data)
    else:
        logger.error(result.content)
        return fail("获取{}资源列表错误".format(resource_type))

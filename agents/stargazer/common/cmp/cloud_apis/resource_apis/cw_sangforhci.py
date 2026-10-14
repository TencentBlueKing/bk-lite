# -*- coding: UTF-8 -*-
import time
from binascii import a2b_hex, b2a_hex

import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.number import bytes_to_long

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.cloud_object.base import VM
from core.logger import logger



def character_conversion_timestamp(time_str):
    """
    时间字符串转为时间戳
    :param time_str:
    :return:
    """
    time_array = time.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    time_stamp = int(time.mktime(time_array)) * 1000
    return time_stamp


def encrypt_with_modulus(content, modulus=None):
    content = content.encode("utf-8")
    e = int(0x10001)
    n = bytes_to_long(a2b_hex(modulus))
    rsa_key = RSA.construct((n, e))
    # generate/export public key
    public_key = rsa_key.publickey()
    cipher = PKCS1_v1_5.new(public_key)
    content = cipher.encrypt(content)
    content = b2a_hex(content)
    return str(content.decode("utf-8"))


def get_resource_uri(op, basic_url, **kwargs):
    return (
        {
            "login": "{basic_url}/vapi/json/access/ticket",
            "get_public_key": "{basic_url}/vapi/json/public_key",
            "get_vms": "{basic_url}/vapi/json/cluster/vms",
        }
        .get(op, "")
        .format(basic_url=basic_url, **kwargs)
    )


def split_list(_list, count=100):
    n = len(_list)
    sublists = [_list[i : i + count] for i in range(0, n, count)]
    return sublists


def handle_request(method, url, **kwargs):
    try:
        resp = requests.request(method, url, **kwargs)
    except Exception:
        logger.exception(f"请求失败,url:{url},method:{method},kwargs:{kwargs}")
        return {"result": False, "message": f"请求失败,url:{url},method:{method},kwargs:{kwargs}", "data": {}}
    if resp.status_code > 300:
        return {
            "result": False,
            "message": f"请求错误,status_code:{resp.status_code},message:{resp.content.decode('utf-8')}",
            "data": {},
        }
    logger.debug(f"请求成功,url:{url},method:{method},kwargs:{kwargs}")
    data = resp.json()
    success = data["success"]
    if not success:
        return {
            "result": False,
            "message": f"请求错误,status_code:{resp.status_code},data:{data}",
            "data": {},
        }
    return {"result": True, "data": data}


class CwSangforHCI(object):
    def __init__(self, account, password, region, host="", scheme="https", **kwargs):
        self.account = account
        self.password = password
        self.region = region
        self.host = host
        self.scheme = scheme
        self.kwargs = kwargs
        self._handle_request = handle_request
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.basic_url = f"{self.scheme}://{self.host}"

        csrf_token, ticket = self.login()
        self.cw_headers = {"Cookie": f"LoginAuthCookie={ticket}", "CSRFPreventionToken": csrf_token}

    def login(self):
        """登录获取运维面token"""

        key_url = get_resource_uri("get_public_key", self.basic_url)
        key_resp = self._handle_request("GET", key_url, verify=False)
        if not key_resp["result"]:
            raise Exception(key_resp["message"])
        public_key = key_resp["data"].get("data", {})
        secret_pw = encrypt_with_modulus(self.password, public_key)
        data = {"username": self.account, "password": secret_pw}
        url = get_resource_uri("login", self.basic_url)
        resp = self._handle_request("POST", url, data=data, verify=False)
        if not resp["result"]:
            raise Exception(resp["message"])
        csrf_token = resp["data"].get("data", {}).get("CSRFPreventionToken", "")
        ticket = resp["data"].get("data", {}).get("ticket", "")
        logger.debug("登录成功")
        return csrf_token, ticket

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @staticmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def __getattr__(self, item):
        params = {
            "cw_headers": self.cw_headers,
            "region": self.region,
            "host": self.host,
            "account": self.account,
            "basic_url": self.basic_url,
        }
        return SangforHCI(name=item, **params)


class SangforHCI(PrivateCloudManage):
    """
    This class providing all operations on MANAGEONE plcatform.
    """

    METRIC_LIST = [
        "cpu_ratio",  # CPU 利用率
        "mem_used",  # 内存使用量
        "mem_ratio",  # 内存利用率
        "io_ratio",  # 磁盘利用率
        "diskread",  # IO 读速率
        "diskwrite",  # IO 写速率
        "netin",  # 网卡接收速率
        "netin_packet",  # 网卡接收包速率
        "netout",  # 网卡发送速率
        "netout_packet",  # 网卡发送包速率
    ]

    def __init__(self, name, **kwargs):
        self.name = name
        self.cw_headers = kwargs.get("cw_headers", "")
        self.basic_url = kwargs.get("basic_url", "")
        self._handle_request = handle_request

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @staticmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def __vm_obj_format(self, vm_obj, os_version_dict=None):
        """
        Format VM Object.
        :param vm_obj: the object of a specific vm.
        :rtype: dict
        """
        return VM(
            cloud_type="sanforhci",
            resource_id=vm_obj.get("vmid", ""),
            resource_name=vm_obj.get("name", ""),
            vcpus=vm_obj.get("cpus", ""),
            os_name=vm_obj.get("osname", ""),
            inner_ip=vm_obj.get("nets", [])[0].get("ip", "") if vm_obj.get("nets", []) else "",
            status=vm_obj.get("status", ""),
            memory=vm_obj.get("mem_total", 0) // 1024 // 1024,
            extra={},
        ).to_dict()

    def list_vms(self, **kwargs):
        """
        Get vm list on cloud platforms.
        """

        params = {"group_type": "group", "stype": "all", "sgroupid": "all", "snet": "1", "ip": "1"}
        url = get_resource_uri("get_vms", self.basic_url)
        resp = self._handle_request("GET", url, headers=self.cw_headers, params=params, verify=False)
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}

        result = resp["data"]
        group_items = result.get("data", [])
        # 按分组
        vm_list = []
        total_num = 0
        for group_item in group_items:
            group_vms = group_item.get("data", [])
            for _vm in group_vms:
                # 不获取模板数据
                _vm_type = _vm.get(
                    "vmtype",
                )
                if _vm_type == "tpl":
                    continue
                vm_data = self.__vm_obj_format(_vm)
                vm_list.append(vm_data)
                total_num += 1
        return {"result": True, "data": vm_list, "total": total_num}

    # ------------------***** monitor *****-------------------
    def get_weops_monitor_data(self, **kwargs):
        """
        Get monitor data from a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        try:
            resource_id = kwargs.get("resourceId", "")
            resource_id_list = resource_id.split(",")
            resource_id_set = set(map(int, resource_id_list))
            timestamp = int(time.time() * 1000)
            metrics = kwargs.get("Metrics", self.METRIC_LIST)
            # 仅获取在运行的虚机的指标
            params = {"group_type": "group", "stype": "all", "sgroupid": "all", "sstatus": "running"}
            url = get_resource_uri("get_vms", self.basic_url)
            resp = self._handle_request("GET", url, headers=self.cw_headers, params=params, verify=False)
            if not resp["result"]:
                return {"result": False, "message": resp["message"]}

            result = resp["data"]
            group_items = result.get("data", [])
            # 按分组
            running_vms = {}
            res = {}
            for group_item in group_items:
                group_vms = group_item.get("data", [])
                for _vm in group_vms:
                    resource_id = _vm["vmid"]
                    if resource_id not in resource_id_set:
                        continue
                    running_vms.update({resource_id: _vm})

            for vm_id, vm_obj in running_vms.items():
                for metric in metrics:
                    value = vm_obj.get(metric)
                    if value is None:
                        continue
                    value = float(value)
                    if metric == "mem_used":
                        value = value // 1024 // 1024
                    if "ratio" in metric:
                        value *= 100
                    res.setdefault(str(vm_id), {}).setdefault(metric, []).append((timestamp, round(value, 2)))
            return {"result": True, "data": res}
        except Exception:
            logger.exception(f"get_weops_monitor error,kwargs:{kwargs}")
        return {"result": False, "message": "get_weops_monitor error"}

    def get_load_monitor_data(self, **kwargs):
        return {"result": False, "message": "不支持"}

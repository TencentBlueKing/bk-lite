# -*- coding: UTF-8 -*-
import json

import requests
from requests.auth import HTTPDigestAuth

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.cloud_constant import CloudPlatform
from common.cmp.cloud_apis.constant import CloudResourceType
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.cloud_apis.resource_apis.utils import fail, success
from core.logger import logger



class CwCas(object):
    """
    通过该类创建CAS实例，调用CASapi接口
    """

    def __init__(self, username, password, region="", host="", port=8080, **kwargs):
        """
        初始化方法，创建Client实例。
        """
        self.username = username
        self.password = password
        self.region = region
        self.host = host
        self.http_port = port
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}
        self.auth = self._log_on()

    def __getattr__(self, item):
        """
        private方法，返回对应的接口类
        """
        return Cas(name=item, host=self.host, http_port=self.http_port, auth=self.auth, cw_headers=self.headers)

    def _log_on(self):
        """
        登录验证
        """
        return HTTPDigestAuth(self.username, self.password)


class Cas(PrivateCloudManage):
    """
    CAS接口类
    """

    def __init__(self, name, host, http_port, auth, cw_headers):
        """
        初始化方法
        """
        self.name = name
        self.host = host
        self.http_port = http_port
        self.auth = auth
        self.cw_headers = cw_headers

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        """
        检查连接是否成功
        """
        res = self.list_vms()
        if res.get("result"):
            return success("连接成功")
        else:
            return fail("连接失败")

    def list_hosts(self):
        """
        查询所有主机
        """
        url = "http://{}:{}/cas/casrs/host".format(self.host, self.http_port)
        return requests.get(url, headers=self.cw_headers, auth=self.auth)

    def list_vms(self, ids=None, **kwargs):
        """
        查询主机所有的虚拟机
        """
        if ids:
            return self.list_vm_details(ids)
        url = "http://{}:{}/cas/casrs/vm/vmList/".format(self.host, self.http_port)
        optional_par = ["hostId", "offset", "limit", "sortField", "sortDir"]
        query_url = request_optional_params_url(optional_par, **kwargs)
        if query_url:
            url = f"{url}?{query_url}"
        return request_get_list(url, headers=self.cw_headers, resource_type="vm", auth=self.auth)

    def list_vm_details(self, vm_id):
        """
        查询虚拟机全部信息
        """
        vm_id = int(vm_id)
        url = "http://{}:{}/cas/casrs/vm/detail/{}".format(self.host, self.http_port, vm_id)
        return request_get(url, headers=self.cw_headers, resource_type="vm", auth=self.auth)

    def get_vm_detail(self, vm_id):
        # 区别查询虚拟机全部信息，少了detail,查询所得信息量较少
        """
        查询虚拟机详情信息
        """
        vm_id = int(vm_id)
        url = "http://{}:{}/cas/casrs/vm/{}".format(self.host, self.http_port, vm_id)
        res = requests.post(url, headers=self.cw_headers, auth=self.auth)
        if res.status_code < 300:
            return {"result": True, "message": "查询成功"}
        else:
            return {"result": False, "message": "查询失败"}

    def list_vm_template(self, **kwargs):
        """
        查询虚拟机模板列表
        """
        url = "http://{}:{}/cas/casrs/vmTemplate/vmTemplateList".format(self.host, self.http_port)
        optional_par = ["offset", "limit", "sortFold", "sortDir"]  # 确少参数数据类型转换
        query_url = request_optional_params_url(optional_par, **kwargs)
        if query_url:
            url = f"{url}?{query_url}"
        return requests.get(url, headers=self.cw_headers, auth=self.auth)

    def create_vm(self, **kwargs):
        """
        创建虚拟机
        """
        must_par = [
            "name",
            "title",
            "hostId",
            "autoMigrate",
            "memory",
            "memoryInit",
            "memoryUnit",
            "memoryBacking",
            "memoryPriority",
            "autoMen",
            "hugepage",
            "cpuSockets",
            "cpuCores",
            "formatEnable",
            "maxCpuSocket",
            "cpuMode",
            "cpuShares",
            "blkiotune",
            "osBit",
            "system",
            "osVersion",
        ]
        check_must_parameters(must_par, **kwargs)
        url = "http://{}:{}/cas/casrs/vm/add".format(self.host, self.http_port)
        body = {
            "name": kwargs.get("name"),
            "title": kwargs.get("title"),
            "hostId": int(kwargs.get("hostId")),
            "autoMigrate": int(kwargs.get("autoMigrate")),
            "memory": int(kwargs.get("memory")),
            "memoryInit": kwargs.get("memoryInit"),
            "memoryUnit": kwargs.get("memoryUnit"),
            "memoryBacking": kwargs.get("memoryBacking"),
            "memoryPriority": kwargs.get("memoryPriority"),
            "autoMem": kwargs.get("autoMem"),
            "hugepage": kwargs.get("hugepage"),
            "cpuSockets": kwargs.get("cpuSockets"),
            "cpuCores": kwargs.get("cpuCores"),
            "formatEnable": 1,
            "maxCpuSocket": kwargs.get("maxCpuSockets"),
            "cpuMode": kwargs.get("cpuMode"),
            "cpuShares": kwargs.get("cpuShare"),
            "blkiotune": kwargs.get("blkiotune"),
            "osBit": kwargs.get("osBit"),
            "system": kwargs.get("system"),
            "osVersion": kwargs.get("sosVersion"),
        }
        list_optional_params = [
            "description",
            "autoLoadVirtio",
            "clusterId",
            "hostPoolId",
            "priority",
            "memoryLimit",
            "memoryLimitUnit",
            "cpu",
            "cpuMax",
            "imgFileName",
            "imgFileType",
            "vmType",
            "viewType",
            "auto",
            "bootingDevice",
            "autoBooting",
            "autoTools",
            "cpuQuota",
            "cpuQuotaUnit",
            "cpuGurantee",
            "enableReduceCPU",
            "domainCpuGlobalQuota",
            "bindcpuList",
            "network",
            "storage",
            "usb",
            "pci",
        ]
        for i in list_optional_params:
            if i in kwargs:
                body[i] = kwargs[i]
        res = requests.post(url, headers=self.cw_headers, data=json.dumps(body), auth=self.auth)
        if res.status_code < 300:
            return {"result": True, "message": "创建成功"}
        else:
            return {"result": False, "message": "创建失败"}

    def start_vm(self, vm_id, *args, **kwargs):
        """
        启动虚拟机
        """
        vm_id = int(vm_id)
        url = "http://{}:{}/cas/casrs/vm/start/{}".format(self.host, self.http_port, vm_id)
        return request_put(url, headers=self.cw_headers, auth=self.auth)

    def stop_vm(self, vm_id, *args, **kwargs):
        """
        关闭虚拟机
        """
        vm_id = int(vm_id)
        url = "http://{}:{}/cas/casrs/vm/stop/{}".format(self.host, self.http_port, vm_id)
        return request_put(url, headers=self.cw_headers, auth=self.auth)

    def get_vm_network(self, vm_id):
        """
        查询虚拟机网络信息
        """
        vm_id = int(vm_id)
        url = "http://{}:{}/cas/casrs/vm/network/{}".format(self.host, self.http_port, vm_id)
        return requests.get(url, headers=self.cw_headers, auth=self.auth)

    def modify_vm(self, *args, **kwargs):
        """
        修改虚拟机基本信息
        """
        must_par = ["pae", "acpi", "apic", "clock", "autpMigrate", "blkiotune", "autoMem"]
        check_must_parameters(must_par, **kwargs)
        url = "http://{}:{}/cas/casrs/vm/modify".format(self.host, self.http_port)
        body = {
            "id": kwargs.get("id"),
            "uuid": kwargs.get("uuid"),
            "basic": {
                "pae": kwargs.get("pae"),
                "acpi": kwargs.get("acpi"),
                "apic": kwargs.get("apic"),
                "clock": kwargs.get("clock"),
                "autoMigrate": kwargs.get("autoMigrate"),
                "blkiotune": kwargs.get("blkiotune"),
                "autoMem": kwargs.get("autoMem"),
            },
        }
        list_optional_params = [
            "desc",
            "timeSync",
            "osha",
            "haManage",
            "startPriority",
            "autoTools",
            "vmType",
            "castoolsType",
            "enableIntegrityCheck",
        ]
        for i in list_optional_params:
            if i in kwargs:
                body["basic"][i] = kwargs[i]
        return requests.put(url, headers=self.cw_headers, data=json.dumps(body), auth=self.auth)

    def modify_vm_cpu(self, **kwargs):
        """
        修改CPU配置
        """
        must_par = ["cpuSokets", "cpuCores", "cpuShares"]
        check_must_parameters(must_par, **kwargs)
        url = "http://{}:{}/cas/casrs/vm/modify".format(self.host, self.http_port)
        body = {
            "id": kwargs.get("id"),
            "uuid": kwargs.get("uuid"),
            "cpu": {
                "cpuSockets": int(kwargs.get("cpuSockets")),
                "cpuCores": int(kwargs.get("cpuCores")),
                "cpuShares": int(kwargs.get("cpuShares")),
            },
        }
        list_optional_params = [
            "cpuMode",
            "cpuArch",
            "enableReduce",
            "rdt",
            "cpuGurantee",
            "cpuQupta",
            "cpuQuptaUnit",
            "bindcpuList",
        ]
        for i in list_optional_params:
            if i in kwargs:
                body["cpu"][i] = kwargs[i]
        return requests.put(url, headers=self.cw_headers, data=json.dumps(body), auth=self.auth)

    def modify_vm_memory(self, **kwargs):
        """
        修改内存配置
        """
        must_par = ["size"]
        check_must_parameters(must_par, **kwargs)
        url = "http://{}:{}/cas/casrs/vm/modify".format(self.host, self.http_port)
        body = {
            "id": kwargs.get("id"),
            "uuid": kwargs.get("uuid"),
            "memory": {
                "size": int(kwargs.get("size")),
            },
        }
        list_optional_params = [
            "memoryBacking",
            "memoryUnit",
            "memoryInit",
            "memoryLimit",
            "memoryLimitUnit",
            "memoryPriority",
            "autoMem",
            "hugepage",
        ]
        for i in list_optional_params:
            if i in kwargs:
                body["memory"][i] = kwargs[i]
        return requests.put(url, headers=self.cw_headers, data=json.dumps(body), auth=self.auth)

    def modify_vm_storage(self, **kwargs):
        """
        修改虚拟机存储配置
        """
        must_par = ["device", "format", "size", "cacheType"]
        check_must_parameters(must_par, **kwargs)
        url = "http://{}:{}/cas/casrs/vm/modify".format(self.host, self.http_port)
        body = {
            "id": kwargs.get("id"),
            "uuid": kwargs.get("uuid"),
            "storage": {
                "device": kwargs.get("device"),
                "format": kwargs.get("format"),
                "size": kwargs.get("size"),
                "cacheType": kwargs.get("cacheType"),
            },
        }
        list_optional_params = [
            "hotPluggable",
            "diskMode",
            "clusterSize",
            "readBytesSec",
            "writeBytesSec",
            "readIopsSec",
            "writeIopsSec",
            "mode",
            "deviceName",
        ]
        for i in list_optional_params:
            if i in kwargs:
                body["storage"][i] = kwargs[i]
        return requests.put(url, headers=self.cw_headers, data=json.dumps(body), auth=self.auth)

    def add_vm_disk(self, *args, **kwargs):
        """
        虚拟机添加虚拟硬盘
        """
        url = "http://{}:{}/cas/casrs/vm/addDevice".format(self.host, self.http_port)
        body = {
            "id": kwargs.get("id"),
            "uuid": kwargs.get("uuid"),
            "storage": {
                "targetBus": kwargs.get("targetBus"),
                "device": kwargs.get("device"),
                "deviceName": kwargs.get("deviceName"),
                "path": kwargs.get("path"),
                # "poolName": kwargs.get("poolName"),
                "format": kwargs.get("format"),
                "size": kwargs.get("size"),
                "cacheType": kwargs.get("cacheType"),
            },
        }
        list_optional_params = [
            "mode",
            "poolName",
            "fileName",
            "readIopsSec",
            "writeIopsSec",
            "pathType",
            "clusterSize",
            "fileType",
            "controller",
            "hotPluggable",
            "i2chache",
            "serial",
        ]
        for i in list_optional_params:
            if i in kwargs:
                body["storage"][i] = kwargs[i]
        return requests.put(url, headers=self.cw_headers, data=json.dumps(body), auth=self.auth)

    def del_vm_disk(self, vm_id, **kwargs):
        """
        卸载虚拟机虚拟硬盘
        """
        url = "http://{}:{}/cas/casrs/vm/delDevice".format(self.host, self.http_port)
        body = {
            "id": vm_id,
            "uuid": kwargs.get("uuid"),
            "title": kwargs.get("title"),
            "name": kwargs.get("name"),
            "storage": {"deviceName": kwargs.get("deviceName"), "path": kwargs.get("path")},
        }
        return request_put(url, headers=self.cw_headers, auth=self.auth, data=json.dumps(body))

    def delete_vm(self, vm_id, *args, **kwargs):
        """
        删除虚拟机
        """
        vm_id = int(vm_id)
        url = "http://{}:{}/cas/casrs/vm/delete/{}".format(self.host, self.http_port, vm_id)
        return requests.delete(url, headers=self.cw_headers, auth=self.auth)

    def add_vm_console(self, **kwargs):
        """
        为指定虚拟机添加控制台
        """
        url = "http://{}:{}/cas/casrs/vm/addDevice".format(self.host, self.http_port)
        body = {
            "id": kwargs.get("id"),
            "uuid": kwargs.get("uuid"),
            "title": kwargs.get("title"),
            "name": kwargs.get("name"),
            "vnc": {
                "type": kwargs.get("type"),
                "port": kwargs.get("port"),
                "address": kwargs.get("address"),
                "portIpv6": kwargs.get("portIpv6"),
                "password": kwargs.get("password"),
                "enableVncProxy": kwargs.get("enableVncProxy"),
                "enableSpiceCompress": kwargs.get("enableSpiceCompress"),
            },
        }
        return requests.put(url, headers=self.cw_headers, data=json.dumps(body), auth=self.auth)

    def get_host_cpu_used(self, vm_id):
        """
        查询虚拟机cpu使用率
        """
        vm_id = int(vm_id)
        url = "http://{}:{}/cas/casrs/vm/id/{}/monitor".format(self.host, self.http_port, vm_id)
        res = requests.get(url, headers=self.cw_headers, auth=self.auth)
        result = json.loads(res.content)
        cpu_used = result.get("cpuRate")
        return cpu_used

    def get_host_memory_used(self, vm_id):
        """
        查询虚拟机内存使用率
        """
        vm_id = int(vm_id)
        url = "http://{}:{}/cas/casrs/host/id/{}/monitor".format(self.host, self.http_port, vm_id)
        res = requests.get(url, headers=self.cw_headers, auth=self.auth)
        result = json.loads(res.content)
        memory_used = result.get("menRate")
        return memory_used

    def list_task_message(self, msg_id):
        """
        根据任务id查询任务详细信息
        """
        msg_id = int(msg_id)
        url = "http://{}:{}/cas/casrs/message/{}".format(self.host, self.http_port, msg_id)
        return requests.get(url, headers=self.cw_headers, auth=self.auth)

    def get_vm_monitor_info(self, **kwargs):
        """
        从报表数据查询多个uuid获取虚拟机性能数据
        """
        json_params = {
            "uuid": kwargs.get("vm_uuid_list"),
            "startTimeLong": kwargs.get("start_time"),
            "endTimeLong": kwargs.get("end_time"),
        }
        url = "http://{}:{}/cas/casrs/vm/mixPerfData".format(self.host, self.http_port)
        res = requests.get(url, headers=self.cw_headers, json=json_params, auth=self.auth)
        result = json.loads(res.content)
        monitor_info = result.get("domainPerfDatas")
        return monitor_info

    @staticmethod
    def control_dict_or_list(control_info):
        """处理字段或列表信息"""
        if isinstance(control_info, list):
            return control_info[0]
        elif isinstance(control_info, dict):
            return control_info
        else:
            return {}

    def _control_vm_monitor_info(self, monitor_info):
        """处理虚拟机监控数据"""
        dict_info = {}
        get_net = self.control_dict_or_list(monitor_info.get("net"))
        get_disk = self.control_dict_or_list(monitor_info.get("disk"))
        net_info = {"read_flow": get_net.get("readFlow") or 0, "write_flow": get_net.get("writeFlow") or 0}
        disk_info = {"read_reqest": get_disk.get("readReqest") or 0, "write_reqest": get_disk.get("writeReqest") or 0}
        dict_info.update(
            {
                "cpu_rate": monitor_info.get("cpuRate") or 0,
                "mem_rate": monitor_info.get("memRate") or 0,
                "net": net_info,
                "disk": disk_info,
            }
        )
        return dict_info

    def list_vm_monitor(self, vm_id):
        """
        查询虚拟机监控信息-查询虚拟机的性能监控数据(uuid也适用)
        """
        vm_id = int(vm_id)
        url = "http://{}:{}/cas/casrs/vm/id/{}/monitor".format(self.host, self.http_port, vm_id)
        result = requests.get(url, headers=self.cw_headers, auth=self.auth)
        if result.status_code < 300:
            json_result = json.loads(result.content)
            logger.exception("获取监控数据1--{}".format(json_result))
            dict_info = self._control_vm_monitor_info(json_result)
            logger.exception("获取监控数据2--{}".format(dict_info))
            return {"result": True, "data": [dict_info]}
        else:
            return {"result": False, "data": []}

    @staticmethod
    def _control_vm_warn_info(warn_info):
        """处理虚拟机告警数据，过滤只获取虚拟机的数据"""
        list_info = [i for i in warn_info if i.get("uuid")]
        return list_info

    def list_warn_info(self, **kwargs):
        """
        获取告警列表信息
        """
        url = "http://{}:{}/cas/casrs/warnManage/warnManageList".format(self.host, self.http_port)
        optional_par = ["offset", "limit", "eventTime_from", "eventTime_to", "state", "sortDir", "sortField"]
        query_url = request_optional_params_url(optional_par, **kwargs)
        if query_url:
            url = f"{url}?{query_url}"
        result = requests.get(url, headers=self.cw_headers, auth=self.auth)
        if result.status_code < 300:
            json_result = json.loads(result.content)
            warn_info_list = json_result.get("event")
            list_info = self._control_vm_warn_info(warn_info_list)
            return {"result": True, "data": list_info}
        else:
            return {"result": False, "data": []}


# ***********************Common****************************************


resource_type_dict = {
    "network": CloudResourceType.VPC.value,
    "volume": CloudResourceType.DISK.value,
    "volume_type": "volume_type",
    "flavor": CloudResourceType.INSTANCE_TYPE.value,
    "vm": CloudResourceType.VM.value,
}


def request_get(url, headers, resource_type, auth, **kwargs):
    """
    get请求格式方法
    """
    format_type = resource_type
    try:
        result = requests.get(url, verify=False, headers=headers, auth=auth)
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    if result.status_code < 300:
        content = json.loads(result.content)
        if resource_type in resource_type_dict:
            format_type = resource_type_dict[resource_type]
        data = get_format_method(
            CloudPlatform.Cas, format_type, project_id=kwargs.get("project_id"), region_id=kwargs.get("region_id")
        )(content.get(resource_type, {}), **kwargs)
        return success([data])
    else:
        logger.error(result.content)
        return fail("获取{}资源详情错误".format(resource_type))


def request_get_list(url, headers, resource_type, auth, **kwargs):
    """
    list 请求格式方法
    """
    try:
        result = requests.get(url, verify=False, headers=headers, auth=auth)
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    data = []
    if result.status_code < 300:
        content = json.loads(result.content)
        for i in content.get("domain", []):
            if resource_type in resource_type_dict:
                resource_type = resource_type_dict[resource_type]
            data.append(get_format_method(CloudPlatform.Cas, resource_type)(i, **kwargs))
        return success(data)
    else:
        logger.error(result.content)
        return fail("获取{}资源列表错误".format(resource_type))


def check_must_parameters(par_list, **kwargs):
    """检验必传参数"""
    for key in par_list:
        if key not in kwargs:
            raise ValueError(f"need parameter {key}")


def request_optional_params_url(optional_par, **kwargs):
    """处理路径参数"""
    par_list = [f"{key}={kwargs[key]}" for key in optional_par if key in kwargs]
    return "&".join(par_list)


def request_post(url, headers, auth, **kwargs):
    """
    post 请求方法
    """
    try:
        result = requests.post(url, verify=False, headers=headers, auth=auth, data=json.dumps(kwargs))
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    if result.status_code < 300:
        try:
            content = json.loads(result.content)
        except Exception:
            content = result.content
        return success(content)
    else:
        logger.error(result.content)
        return fail("操作失败")


def request_put(url, headers, auth, **kwargs):
    """
    put 请求方法
    """
    try:
        result = requests.put(url, verify=False, headers=headers, auth=auth, data=json.dumps(kwargs))
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    if result.status_code < 300:
        return success()
    else:
        logger.error(result.content)
        return fail("操作失败")


def request_delete(url, headers, auth):
    """DELETE请求方法"""
    try:
        result = requests.delete(url, verify=False, auth=auth, headers=headers)
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    if result.status_code < 300:
        return success()
    else:
        logger.error(result.content)
        return fail("操作失败")

# -*- coding: UTF-8 -*-
import datetime
import os
import time
import typing

import requests
from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.cloud_object.base import VM, BusinessRegion, DataStore, HostMachine
from core.logger import logger

MANAGEONE_REQUEST_TIMEOUT = (10, 60)

# from common.cmp.cloud_apis.constant import CloudResourceType, CloudType, SnapshotStatus, VMStatusType, VolumeStatus,
# VPCStatus
# from common.cmp.cloud_apis.resource_apis.constant import (
#     FCDiskStatus,
#     FCSnapshotStatus,
#     FCVMStatus,
#     MANAGEONEDiskType,
#     MANAGEONESiteStatus,
#     MANAGEONESnapshotType,
# )
# from common.cmp.cloud_apis.resource_apis.utils import check_required_params, fail, set_optional_params
# from common.cmp.models import AccountConfig
# from common.cmp.cloud_apis.constant import CloudResourceType, CloudType
# from common.cmp.cloud_apis.resource_apis.utils import fail


def character_conversion_timestamp(time_str):
    """
    时间字符串转为时间戳
    :param time_str:
    :return:
    """
    time_array = time.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    time_stamp = int(time.mktime(time_array)) * 1000
    return time_stamp


def get_resource_uri(op, basic_url, **kwargs):
    if int(os.getenv("manageone_use_mock", "0")) or int(os.getenv("CMP_USE_MOCK", "0")):
        basic_url = "http://yapi.canway.top/mock/2429"  # mock
    return (
        {
            "oc_get_token": "{basic_url}/rest/plat/smapp/v1/sessions",
            "list_resource": "{basic_url}/rest/{res_type}/v1/instances/{class_name}",
            "get_monitor": "{basic_url}/rest/performance/v1/data-svc/history-data/action/query",
            "get_analysis": "{basic_url}/rest/analysis/v1/datasets/{stat_type}",
        }
        .get(op, "")
        .format(basic_url=basic_url, **kwargs)
    )


def split_list(_list, count=100):
    n = len(_list)
    sublists = [_list[i : i + count] for i in range(0, n, count)]
    return sublists


def handle_request(method, url, **kwargs):
    kwargs["timeout"] = MANAGEONE_REQUEST_TIMEOUT
    try:
        resp = requests.request(method, url, **kwargs)
    except Exception:
        logger.exception("请求失败,url:%s,method:%s", url, method)
        return {"result": False, "message": f"请求失败,url:{url},method:{method},kwargs:{kwargs}", "data": {}}
    if resp.status_code > 300:
        logger.error(
            "请求失败,url:%s,method:%s,status_code:%s",
            url,
            method,
            resp.status_code,
        )
        return {
            "result": False,
            "message": f"请求错误,status_code:{resp.status_code},message:{resp.content.decode('utf-8')}",
            "data": {},
        }
    logger.debug("请求成功,url:%s,method:%s", url, method)
    return {"result": True, "data": resp.json()}


class CwManageOne(object):
    def __init__(self, account, password, region="dsj-region-1", host="hcs.dsj", scheme="https", **kwargs):
        self.account = account
        self.password = password
        self.region = region or "dsj-region-1"
        host = host or "hcs.dsj"
        self.scheme = scheme
        self.api_version = kwargs.get("version", "8.2.0")
        self.kwargs = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.host = f"oc.{self.region}.{host}"  # 运维面前缀
        self.basic_url = f"{self.scheme}://{self.host}"
        self._handle_request = handle_request
        if self.api_version in ["8.2.0"]:
            self.cw_headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json",
            }
            self.auth_token = self.get_token()
            self.cw_headers.update({"X-Auth-Token": self.auth_token, "Accept-Charset": "utf-8;q=1"})

        else:
            # todo后续支持其他差异化版本
            raise Exception("版本不支持,检查是否为8.2.0")

    def get_token(self):
        """登录获取运维面token"""

        data = {"grantType": "password", "userName": self.account, "value": self.password}

        url = get_resource_uri("oc_get_token", self.basic_url)
        resp = self._handle_request("PUT", url, headers=self.cw_headers, json=data, verify=False)
        if not resp["result"]:
            return ""
        auth_token = resp["data"].get("accessSession", "")
        logger.debug(
            "获取运维面token成功,token_present:%s",
            bool(auth_token),
        )
        return auth_token

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
        return ManageOne(auth_token=self.auth_token, name=item, **params)


class ManageOne(PrivateCloudManage):
    """
    This class providing all operations on MANAGEONE plcatform.
    """

    CLOUD_VM = "CLOUD_VM"
    SYS_PhysicalHost = "SYS_PhysicalHost"  # 宿主机
    SYS_StorDevice = "SYS_StorDevice"  # 存储设备
    SYS_BusinessRegion = "SYS_BusinessRegion"  # 云平台
    CLOUD_FLOATING_IPS = "CLOUD_FLOATING_IPS"  # 弹性IP
    CLOUD_ELB = "CLOUD_ELB"  # 负载均衡
    CLOUD_ELB_POOL = "CLOUD_ELB_POOL"  # 负载均衡集群
    CLOUD_ELB_POOL_MEMBERS = "CLOUD_ELB_POOL_MEMBERS"  # 负载均衡集群成员
    ALL_RESOURCES = [CLOUD_VM, SYS_PhysicalHost, SYS_StorDevice, SYS_BusinessRegion, CLOUD_FLOATING_IPS, CLOUD_ELB]
    OBJ_RES_MAP = {
        "mo_server": CLOUD_VM,
        "mo_cloud": SYS_BusinessRegion,
        "mo_host": SYS_PhysicalHost,
        "mo_ds": SYS_StorDevice,
        "mo_elb": CLOUD_ELB,
        "mo_ip": CLOUD_FLOATING_IPS,
    }
    INDICATOR_NAME_ID_MAP = {
        CLOUD_VM: {
            "cpuUsage": 562958543421441,  # CPU使用率
            "memoryUsage": 562958543486979,  # 内存使用率
            "diskUsage": 562958543618052,  # 云硬盘使用率
            "diskIoIn": 562958543618061,  # 云硬盘IO写入
            "diskIoOut": 562958543618062,  # 云硬盘IO读出
            "nicByteIn": 562958543552537,  # 网络流入速率
            "nicByteOut": 562958543552538,  # 网络流出速率
            "disk_read_requests_rate": 562958543618072,  # 磁盘读操作速率
            "disk_write_requests_rate": 562958543618073,  # 磁盘写操作速率
        },
        SYS_PhysicalHost: {
            "cpuUsage": 1407379178586113,  # CPU使用率
            "memoryUsage": 1407379178651656,  # 内存使用率
            "diskUsage": 1407379178782740,  # 磁盘使用率
            "nicByteIn": 1407379178717195,  # 网络流入速率
            "nicByteOut": 1407379178717196,  # 网络流出速率
            "diskIoOut": 1407379178782739,  # 磁盘IO读出
            "diskIoIn": 1407379178782738,  # 磁盘IO读入
            "nicPkgRcv": 1407379178717199,  # 网络接收包速
            "nicPkgSend": 1407379178717198,  # 网络发送包率
            "nicDropPercent": 1407379178717197,  # 网络丢包百分比
            "diskIopsRead": 1407379178782742,  # 磁盘读IOPS
            "diskIopsWrite": 1407379178782741,  # 磁盘写IOPS
        },
        CLOUD_FLOATING_IPS: {
            "up_stream": 562971428257793,  # 上行流量
            "upstream_bandwidth": 562971428257794,  # 上行带宽
            "down_stream": 562971428257795,  # 下行流量
            "downstream_bandwidth": 562971428257796,  # 下行带宽
            "upstream_bandwidth_usage": 562971428257797,  # 出网带宽使用率
        },
        CLOUD_ELB: {
            "concurrentConnections": 281487861678081,  # 并发连接数
            "activeConnections": 281487861678082,  # 并发连接数
            "inactiveConnections": 281487861678083,  # 并发连接数
            "newConnections": 281487861678084,  # 并发连接数
            "flowPacketIn": 281487861743617,  # 并发连接数
            "flowPacketOut": 281487861743618,  # 并发连接数
            "nicByteIn": 281487861743619,  # 并发连接数
            "nicByteOut": 281487861743620,  # 并发连接数
            "abnormalHost": 281487861743621,  # 并发连接数
            "normalHost": 281487861743622,  # 并发连接数
        },
    }
    EX_METRICS = {
        CLOUD_VM: ["status"],  # 状态
        SYS_PhysicalHost: ["status"],  # 状态
        CLOUD_FLOATING_IPS: ["status"],  # 状态
        CLOUD_ELB: ["status"],  # 状态
        SYS_StorDevice: ["status", "usedCapacity", "capacityRatio"],  # 状态  # 使用容量  # 容量使用率
        SYS_BusinessRegion: [
            "status",  # 状态
            "usedCapacity",  # 磁盘使用量
            "capacityUsageRatio",  # 磁盘使用率
            "vcpusUsed",  # vcpu使用量
            "vcpusUsedRatio",  # vcpu使用率
            "memoryUsed",  # 内存使用率
            "memoryUsedRatio",  # 内存使用率
        ],
    }
    CLASSNAME_FUNC_MAP = {
        CLOUD_VM: "_vm_obj_format",
        SYS_PhysicalHost: "_host_obj_format",
        SYS_StorDevice: "_store_obj_format",
        SYS_BusinessRegion: "_biz_obj_format",
        CLOUD_ELB: "_elb_obj_format",
        CLOUD_ELB_POOL: "_elb_pool_obj_format",
        CLOUD_ELB_POOL_MEMBERS: "_elb_pool_members_obj_format",
        CLOUD_FLOATING_IPS: "_ip_obj_format",
    }
    OBJ_TYPE_MAP = {
        CLOUD_VM: 562958543355904,
        SYS_PhysicalHost: 1407379178520576,
        CLOUD_ELB: 281487861612544,
        CLOUD_FLOATING_IPS: 562971428257792,
    }
    ANALYSIS_MAP = {
        "stat-hypervisor": [
            ("sum", "metrics.vcpus"),
            ("sum", "metrics.vcpusUsed"),
            ("sum", "metrics.vcpusLeft"),
            ("sum", "metrics.memory"),
            ("sum", "metrics.memoryUsed"),
            ("sum", "metrics.memoryLeft"),
        ],
        "stat-cloud-storage-pool": [
            ("sum", "metrics.totalCapacity"),
            ("sum", "metrics.usedCapacity"),
            ("sum", "metrics.freeCapacity"),
        ],
    }

    def __init__(self, auth_token, name, **kwargs):
        self.auth_token = auth_token
        self.name = name
        self.cw_headers = kwargs.get("cw_headers", "")
        self.basic_url = kwargs.get("basic_url", "")
        self._handle_request = handle_request

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @staticmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_res_type(self, classname: str) -> str:
        if classname.startswith("CLOUD"):
            return "tenant-resource"
        elif classname.startswith("SYS"):
            return "cmdb"
        else:
            raise Exception(f"classname Error :{classname}")

    def get_format(self, classname: str) -> typing.Callable:
        func_name = self.CLASSNAME_FUNC_MAP.get(classname, "")
        func = getattr(self, func_name)
        if not func:
            raise Exception(f"Format Not Define :{classname}")
        return func

    def get_connection_result(self):
        """
        check if this object works.
        :return: A dict with a “key: value” pair of object. The key name is result, and the value is a boolean type.
        :rtype: dict
        """
        if self.auth_token:
            return {"result": True}
        return {"result": False}

    def _vm_obj_format(self, vm_obj, **kwargs):
        """
        Format VM Object.
        :param vm_obj: the object of a specific vm.
        :rtype: dict
        """
        return VM(
            cloud_type="manageone",
            resource_id=vm_obj.get("resId", ""),
            resource_name=vm_obj.get("name", ""),
            vcpus=vm_obj.get("flavorVcpu", ""),
            os_name=vm_obj.get("osVersion", ""),
            inner_ip=vm_obj.get("privateIps", "").replace("@", ""),
            floating_ip=vm_obj.get("floatingIp", "").replace("@", ""),
            status=vm_obj.get("status", ""),
            region=vm_obj.get("bizRegionNativeId", ""),
            charge_type=vm_obj.get("payModel", ""),
            create_time=vm_obj.get("createdAt", "")[:19].replace("T", " "),
            host_id=vm_obj.get("physicalHostId", ""),
            extra={},
        ).to_dict()

    def _ip_obj_format(self, obj, **kwargs):
        """
        Format Floating Ips Object.
        :param obj: the object of a floating ips.
        :rtype: dict
        """
        return obj

    def _elb_obj_format(self, obj, **kwargs):
        """
        Format ELB Object.
        :param obj: the object of a specific elb.
        :rtype: dict
        """
        return obj

    def _elb_pool_obj_format(self, obj, **kwargs):
        """
        Format ELB Pool Object.
        :param obj: the object of a specific elb pool.
        :rtype: dict
        """
        return obj

    def _elb_pool_members_obj_format(self, obj, **kwargs):
        """
        Format ELB POOL MEMBER Object.
        :param obj: the object of a specific elb pool members.
        :rtype: dict
        """
        return obj

    def _host_obj_format(self, obj, **kwargs):
        """
        Format host Object.
        :param obj: the object of a specific host.
        :rtype: dict
        """
        return HostMachine(
            cloud_type="manageone",
            resource_id=obj.get("resId", ""),
            resource_name=obj.get("name", ""),
            ip_addr=obj.get("ipAddress", ""),
            ip_bmc=obj.get("bmcIp", ""),
            hypervisor_type=obj.get("hypervisorType", ""),
            cpu=obj.get("totalVcpuCores", ""),
            memory=obj.get("totalVmemoryMB", ""),
            biz_region_id=obj.get("logicalRegionId", ""),
            extra={},
        ).to_dict()

    def _store_obj_format(self, obj, **kwargs):
        """
        Format datastore Object.
        :param obj: the object of a specific store.
        :rtype: dict
        """
        return DataStore(
            cloud_type="manageone",
            resource_id=obj.get("resId", ""),
            resource_name=obj.get("name", ""),
            ip_addr=obj.get("ipAddress", ""),
            storage_gb=obj.get("totalCapacity", ""),
            biz_region_id=obj.get("logicalRegionId", ""),
        ).to_dict()

    def _biz_obj_format(self, obj, **kwargs):
        """
        Format Biz Object.
        :param obj: the object of a specific biz.
        :param metric_data: the metric data of a specific biz.
        :rtype: dict
        """
        metric_data = kwargs.get("metric", {})

        return BusinessRegion(
            cloud_type="manageone",
            resource_id=obj.get("resId", ""),
            resource_name=obj.get("name", ""),
            cloud_version=obj.get("solutionVersion", ""),
            brand=obj.get("manufacturer", ""),
            vcpus=str(round(int(metric_data.get("vcpus", "") or 0), 3) or ""),
            memory_mb=str(round(float(metric_data.get("memory", "") or 0), 3) or ""),
            storage_gb=str(round((metric_data.get("totalCapacity", 0) or 0) * 1024, 3) or ""),
        ).to_dict()

    def _get_analysis(self, stat_type, metrics: typing.List[typing.Tuple[str, str]] = None):
        params = {"pageSize": 1000, "pageNo": 1}
        metrics = metrics or []
        data = {
            "filters": {"dimensions": [{"field": "dimensions.logicLoc.manageFlagName", "values": ["管理", "非管理"]}]},
            "dimensions": [{"field": "dimensions.logicLoc.regionName", "index": 1}],
            "metrics": [],
        }
        for agg_type, field in metrics:
            data["metrics"].append(
                {
                    "aggType": agg_type,
                    "field": field,
                }
            )
        url = get_resource_uri("get_analysis", self.basic_url, stat_type=stat_type)
        resp = self._handle_request("POST", url, headers=self.cw_headers, params=params, json=data, verify=False)
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}
        stat_data: list = resp["data"]["datas"]
        return {region_stat["regionName"]: region_stat for region_stat in stat_data}

    def list_resource(self, classname, append_metric=False, format=True):
        params = {"pageSize": 1, "pageNo": 1}
        url = get_resource_uri("list_resource", self.basic_url, res_type=self.get_res_type(classname), class_name=classname)
        resp = self._handle_request("GET", url, headers=self.cw_headers, params=params, verify=False)
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}

        result = resp["data"]
        total_num = result.get("totalNum", 0)
        if total_num == 0:
            return {"result": True, "data": [], "total": total_num}
        res_list = []
        every = 100  # 每次100条
        count = total_num // every if total_num % every == 0 else total_num // every + 1  # 请求次数
        all_result = True
        all_message = ""
        metric_data = {}
        if classname == self.SYS_BusinessRegion and append_metric:
            for stat_type, metrics in self.ANALYSIS_MAP.items():
                data = self._get_analysis(stat_type, metrics)
                for i, v in data.items():
                    metric_data.setdefault(i, {}).update(v)
        for i in range(count):
            params = {"pageSize": 1000, "pageNo": i + 1}
            resp = self._handle_request("GET", url, headers=self.cw_headers, params=params, verify=False)
            if not resp["result"]:
                all_result = False
                all_message = resp["message"]
                break
            obj_list = resp["data"].get("objList", [])
            for _obj in obj_list:
                _obj_metric = metric_data.get(_obj.get("name", ""), {})
                _obj.update(_obj_metric)
                if format:
                    _obj = self.get_format(classname)(_obj, metric=_obj_metric)
                res_list.append(_obj)
        if not all_result:
            return {"result": all_result, "message": all_message}
        return {"result": True, "data": res_list, "total": total_num}

    def list_vms(self, **kwargs):
        """
        Get vm list on cloud platforms.
        """
        return self.list_resource(self.CLOUD_VM)

    def list_hosts(self, *args, **kwargs):
        """查询宿主机"""
        return self.list_resource(self.SYS_PhysicalHost)

    def list_biz_regions(self, *args, **kwargs):
        """查询云平台"""
        return self.list_resource(self.SYS_BusinessRegion, append_metric=True)

    def list_ds(self, *args, **kwargs):
        """查询存储设备"""
        return self.list_resource(self.SYS_StorDevice)

    def list_floating_ips(self, *args, **kwargs):
        """查询"""
        return self.list_resource(self.CLOUD_FLOATING_IPS)

    def list_elb(self, *args, **kwargs):
        """查询负载均衡"""
        return self.list_resource(self.CLOUD_ELB)

    def list_elb_pool(self, *args, **kwargs):
        """查询负载均衡集群"""
        return self.list_resource(self.CLOUD_ELB_POOL)

    def list_elb_pool_members(self, *args, **kwargs):
        """查询负载均衡集群成员"""
        return self.list_resource(self.CLOUD_ELB_POOL_MEMBERS)

    def list_all_resources(self, **kwargs):
        mo_cloud = self.list_biz_regions()
        mo_host = self.list_hosts()
        mo_ds = self.list_ds()
        mo_server = self.list_vms()
        mo_ip = self.list_floating_ips()
        mo_elb = self.list_elb()
        mo_elb_pool = self.list_elb_pool()
        mo_elb_pool_member = self.list_elb_pool_members()
        if not all(map(lambda x: x["result"], [mo_cloud, mo_host, mo_ds, mo_server])):
            raise {"result": False, "message": "Get Resource Error"}
        # 添加关联
        list(map(lambda x: x.update(association={"mo_cloud": x["biz_region_id"]}), mo_host["data"]))
        list(map(lambda x: x.update(association={"mo_cloud": x["biz_region_id"]}), mo_ds["data"]))
        list(map(lambda x: x.update(association={"mo_host": x["host_id"]}), mo_server["data"]))

        # 遍历mo_ip["data"],构建ip与id的映射关系
        ip_id_map = {}
        pool_member_vm_map = {}
        pool_elb_map = {}
        for ip in mo_ip["data"]:
            ip_id_map[ip["floatingIpAddress"]] = ip["id"]

        for elb_pool in mo_elb_pool["data"]:
            pool_elb_map[elb_pool["id"]] = elb_pool["elbId"]

        for elb_pool_member in mo_elb_pool_member["data"]:
            pool_member_vm_map[elb_pool_member["vmId"]] = pool_elb_map.get(elb_pool_member["poolId"], None)

        for i in mo_server["data"]:
            i.update(floating_ip_id=ip_id_map.get(i["floating_ip"], None))
            i.update(elb_id=pool_member_vm_map.get(i["resource_id"], None))

        logger.debug(
            "event=manageone_inventory_collected clouds=%s hosts=%s datastores=%s servers=%s floating_ips=%s elbs=%s",
            len(mo_cloud["data"]),
            len(mo_host["data"]),
            len(mo_ds["data"]),
            len(mo_server["data"]),
            len(mo_ip["data"]),
            len(mo_elb["data"]),
        )
        return {
            "result": "True",
            "data": {
                "mo_cloud": mo_cloud["data"],
                "mo_host": mo_host["data"],
                "mo_ds": mo_ds["data"],
                "mo_server": mo_server["data"],
                "mo_ip": mo_ip["data"],
                "mo_elb": mo_elb["data"],
            },
        }

    # ------------------***** monitor *****-------------------
    def get_weops_monitor_data(self, **kwargs):
        """
        Get monitor data from a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        try:
            now_time = datetime.datetime.now() + datetime.timedelta(minutes=-5)
            hour_time = datetime.datetime.now() + datetime.timedelta(hours=-1)
            timestamp = int(time.time() * 1000)
            resource_id = kwargs.get("resourceId", "")
            resources = kwargs.get("context", {}).get("resources", [])
            if not resources:
                return {"result": False, "message": "未获取到实例信息"}
            bk_obj_id = resources[0]["bk_obj_id"]
            classname = self.OBJ_RES_MAP.get(bk_obj_id)
            if not classname:
                return {"result": False, "message": "找不到对应的模型"}

            resource_id_list = resource_id.split(",")
            sub_lists = split_list(resource_id_list, 3)  # 考虑的指标较多,会超过指标*实例>100
            start_time = character_conversion_timestamp(kwargs.get("StartTime", now_time))
            end_time = character_conversion_timestamp(kwargs.get("EndTime", hour_time))
            obj_metric_dict = self.INDICATOR_NAME_ID_MAP.get(classname, {})
            indicator_id_name_map = {str(value): key for key, value in obj_metric_dict.items()}

            metrics = kwargs.get("Metrics", list(obj_metric_dict.keys()) + list(self.EX_METRICS.get(classname, [])))
            indicator_ids = [obj_metric_dict[metric] for metric in metrics if metric in obj_metric_dict.keys()]
            indicator_str_ids = [str(i) for i in indicator_ids]
            res = {}
            if indicator_str_ids:
                result = {}
                for sub_list in sub_lists:
                    data = {
                        "obj_type_id": self.OBJ_TYPE_MAP.get(classname),
                        "indicator_ids": indicator_ids,
                        "obj_ids": sub_list,
                        # "interval" : "ORIGINAL",
                        "range": "BEGIN_END_TIME",
                        "begin_time": start_time,
                        "end_time": end_time,
                    }

                    url = get_resource_uri("get_monitor", self.basic_url)
                    resp = self._handle_request("POST", url, headers=self.cw_headers, json=data, verify=False)
                    if not resp["result"]:
                        continue

                    sub_result = resp["data"].get("data", {})
                    result.update(sub_result)

                    for obj, metrics_data in result.items():
                        if obj not in resource_id_list:
                            continue
                        for indicator_id, metric_value in metrics_data.items():
                            if indicator_id not in indicator_str_ids:
                                continue
                            ts_value = metric_value.get("series", [])
                            if not ts_value:
                                continue
                            timestamp, value = tuple(ts_value[-1].items())[0]
                            if value is None:
                                continue
                            value = round(float(value), 2)
                            res.setdefault(obj, {}).setdefault(indicator_id_name_map.get(indicator_id, ""), []).append((int(timestamp), value))
            ex_metrics = self.EX_METRICS.get(classname, [])
            resource_params = {"format": False}
            if classname == self.SYS_BusinessRegion:
                resource_params.update(append_metric=True)
            resp = self.list_resource(classname, **resource_params)
            if not resp["result"]:
                return {"result": False, "data": "API获取资源失败"}
            for resource in resp["data"]:
                resource_id = resource.get("resId")
                if resource_id not in resource_id_list:
                    continue
                for metric in ex_metrics:
                    try:
                        value = self.get_ex_metrics(classname, metric, resource)
                        res.setdefault(resource_id, {}).setdefault(metric, []).append((int(timestamp), value))
                    except Exception:
                        logger.exception(f"get_ex_metrics error classname:{classname},metric:{metric},resource:{resource}")
                        continue
            return {"result": True, "data": res}
        except Exception:
            logger.exception(f"get_weops_monitor error,kwargs:{kwargs}")
        return {"result": False, "message": "get_weops_monitor error"}

    def get_ex_metrics(self, classname, metric, resource_data):
        if metric == "status":
            return int(resource_data.get("status").lower() in ["normal", "active"])
        elif classname == self.SYS_StorDevice and metric == "capacityRatio":
            return round(resource_data.get("usedCapacity") / resource_data.get("totalCapacity") * 100, 2)
        elif classname == self.SYS_BusinessRegion and metric == "capacityUsageRatio":
            return round(resource_data.get("usedCapacity") / resource_data.get("totalCapacity") * 100, 2)
        elif classname == self.SYS_BusinessRegion and metric == "vcpusUsedRatio":
            return round(resource_data.get("vcpusUsed") / resource_data.get("vcpus") * 100, 2)
        elif classname == self.SYS_BusinessRegion and metric == "memoryUsedRatio":
            return round(resource_data.get("memoryUsed") / resource_data.get("memory") * 100, 2)
        elif classname == self.SYS_BusinessRegion and metric == "usedCapacity":
            return round(resource_data.get("usedCapacity") * 1024, 2)
        else:
            return round(resource_data.get(metric), 2)

    def get_load_monitor_data(self, **kwargs):
        return {"result": False, "message": "不支持"}

    def get_biz_metric(self, res_id):
        pass

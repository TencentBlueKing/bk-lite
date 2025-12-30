# -*- coding: UTF-8 -*-
import datetime
import hashlib
import json
import logging
import time
import uuid

import requests
from obs import ObsClient

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.cloud_object.base import (  # LocalStorage,
    VM,
    VPC,
    Bucket,
    Disk,
    Eip,
    Image,
    LoadBalancer,
    LoadBalancerListener,
    PrivateStorage,
    Region,
    RelayRule,
    RouteEntry,
    RouteTable,
    SecurityGroup,
    SecurityGroupRule,
    Snapshot,
    Subnet,
    Zone,
)
from common.cmp.cloud_apis.constant import CloudResourceType, CloudType, SnapshotStatus, VMStatusType, VolumeStatus, VPCStatus
from common.cmp.cloud_apis.resource_apis.constant import (
    FCDiskStatus,
    FCSnapshotStatus,
    FCVMStatus,
    FusionComputeDiskType,
    FusionComputeSiteStatus,
    FusionComputeSnapshotType,
)
from common.cmp.cloud_apis.resource_apis.utils import check_required_params, fail, set_optional_params
from common.cmp.models import AccountConfig

logger = logging.getLogger("root")


def urn_transform_uri(urn):
    """
    将资源的urn资源标识转化为uri请求标识，urn:sites:61EF0A3D:hosts:453->/service/sites/61EF0A3D/hosts/453
    :param urn:
    :return:
    """
    return urn.replace(":", "/").replace("urn", "/service")


def character_conversion_timestamp(time_str):
    """
    时间字符串转为时间戳
    :param time_str:
    :return:
    """
    time_array = time.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    time_stamp = int(time.mktime(time_array))
    return time_stamp


def get_resource_uri(base_url, resource_uri=None):
    return {
        # site base
        "site_uri": "{}/service/sites".format(base_url),
        # host
        "host_uri": "{}{}/hosts".format(base_url, resource_uri),
        "host_statistics_uri": "{}{}/hosts/statistics".format(base_url, resource_uri),
        # cluster
        "cluster_uri": "{}{}/clusters".format(base_url, resource_uri),
        "cluster_compute_resource_uri": "{}{}/computeresource".format(base_url, resource_uri),
        "cluster_all_vm_compute_resource_uri": "{}{}/allvmcomputeresource".format(base_url, resource_uri),
        # vm
        "vms_uri": "{}{}/vms".format(base_url, resource_uri),
        "vm_action_url": "{}/rest/orchestration/v3.0/fcecs/servers/action".format(base_url),
        "image_action_url": "{}/rest/orchestration/v3.0/fcecs/templates/action".format(base_url),
        "query_image_url": "{}/rest/orchestration/v3.0/fcecs/templates".format(base_url),
        "vm_server_url": "{}/rest/orchestration/v3.0/fcecs/servers".format(base_url),
        "get_resource_pools_url": "{}/rest/serviceaccess/v3.0/cloud-infras".format(base_url),
        # os version
        "os_version": "{}{}/vms/osversions".format(base_url, resource_uri),
        # vm action
        "vm_start_uri": "{}{}/action/start".format(base_url, resource_uri),
        "vm_stop_uri": "{}{}/action/stop".format(base_url, resource_uri),
        "vm_reboot_uri": "{}{}/action/reboot".format(base_url, resource_uri),
        "vm_add_disk_uri": "{}{}/action/createattachvol".format(base_url, resource_uri),
        "vm_attach_disk_uri": "{}{}/action/attachvol".format(base_url, resource_uri),
        "vm_snapshot_uri": "{}{}/snapshots".format(base_url, resource_uri),
        "vm_snapshot_resume_uri": "{}{}/action/resumevm".format(base_url, resource_uri),
        "vm_disk_expand_uri": "{}{}/action/expandvol".format(base_url, resource_uri),
        "vm_disk_delete_uri": "{}{}/action/recyclevol".format(base_url, resource_uri),
        "vm_detach_disk_uri": "{}{}/action/detachvol".format(base_url, resource_uri),
        # disk
        "disk_uri": "{}{}/volumes".format(base_url, resource_uri),
        "disk_expand_uri": "{}{}/action/expandVol".format(base_url, resource_uri),
        "datastore_volumes": "{}{}/volumes/querydatastorevolumes".format(base_url, resource_uri),
        # storage
        "storage_uri": "{}{}/datastores".format(base_url, resource_uri),
        "block_storages_url": "{}/rest/orchestration/v3.0/fcevs/volumes".format(base_url),
        # security group
        "security_group_uri": "{}{}/securitygroups".format(base_url, resource_uri),
        "security_group_url": "{}/v2.0/security-groups".format(base_url),
        # security-group-rule
        "security_group_rule_url": "{}/v2.0/security-group-rules".format(base_url),
        # vpc
        "vpc_url": "{}/rest/orchestration/v3.0/fcvpc/vpcs".format(base_url),
        # route_table
        "route_table_url": "{}/csbservice/routeTables/findPageRouteTablesList".format(base_url),
        # route_entry
        "route_entry_url": "{}/v2.0/vpc/routes".format(base_url),
        # public_ips
        "public_ips_url": "{}/v1/{}/publicips".format(base_url, resource_uri),
        # eip
        "eip_url": "{}/v2.0/floatingips".format(base_url),
        # load_balancer
        "load_balancer_url": "{}/v2.0/lbaas/loadbalancers".format(base_url),
        # listener
        "listener_url": "{}/v3/{}/elb/listeners".format(base_url, resource_uri),
        # network
        "dvswitch_uri": "{}{}/dvswitchs".format(base_url, resource_uri),
        "dvswitch_url": "{}/rest/orchestration/v3.0/fcvpc/networks".format(base_url),
        # port group
        "port_group_uri": "{}{}/portgroups".format(base_url, resource_uri),
        # resource uri
        "resource_uri": "{}{}".format(base_url, resource_uri),
        # monitor url
        "objectmetric_curvedata": "{}{}/monitors/objectmetric-curvedata".format(base_url, resource_uri),
        # order_url
        "order": "{}/rest/subscription/v3.0/subscriptions".format(base_url),
        # ports_url
        "ports_url": "{}/v2.0/ports",
    }


def handle_vm_status(status):
    if FCVMStatus.RUNNING.value == status:
        return VMStatusType.RUNNING.value
    elif FCVMStatus.CREATING.value == status:
        return VMStatusType.BUILD.value
    elif FCVMStatus.STOPPED.value == status:
        return VMStatusType.STOP.value
    elif FCVMStatus.UNKNOWN.value == status:
        return VMStatusType.ERROR.value
    else:
        return VMStatusType.MODIFYING.value


def handle_disk_status(status):
    if FCDiskStatus.USE.value == status:
        return VolumeStatus.AVAILABLE.value
    elif "in-use" == status:
        return VolumeStatus.IN_USE.value
    elif FCDiskStatus.CREATING.value == status:
        return VolumeStatus.CREATING.value
    else:
        return VolumeStatus.MODIFYING.value


def handle_snapshot_status(status):
    if FCSnapshotStatus.READY.value == status:
        return SnapshotStatus.AVAILABLE.value
    elif FCSnapshotStatus.CREATING.value == status:
        return SnapshotStatus.CREATING.value
    elif FCSnapshotStatus.FAILED.value == status:
        return SnapshotStatus.ERROR.value
    else:
        return SnapshotStatus.UNKNOWN.value


class CwFusionCompute(object):
    def __init__(self, account, password, region, host="", **kwargs):
        self.account = account
        self.password = password
        self.host = host
        self.region = region
        self.project_id = kwargs.get("project_id", "")
        self.pool_id = kwargs.get("domain_id", "")
        self.api_version = kwargs.get("version", "6.5")
        # self.https_port = kwargs.get("https_port", "7443")
        # self.http_port = kwargs.get("http_port", "7070")
        self.kwargs = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)

        if self.api_version == "6.5":
            self.cw_headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json;version=%s;charset=UTF-8" % self.api_version,
                "Accept-Language": "zh_CN",
            }
            self.auth_token = self._log_on()
        else:
            self.cw_headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json;charset=UTF-8",
                "Accept-Language": "zh_CN",
            }
            self.auth_token, self.user_id = self._log_on_new()

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @staticmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def __getattr__(self, item):
        params = {}
        if item != "get_connection_result":
            self.cw_headers.update({"X-Auth-Token": self.auth_token, "region": self.region})
            params = {
                "cw_headers": self.cw_headers,
                "region": self.region,
                "project_id": self.project_id,
                "domain_id": self.pool_id,
                "host": self.host,
                "account": self.account,
                "user_id": self.user_id,
            }
        if self.api_version == "6.5":
            params.update({"basic_url": "https://{}:{}".format(self.host, self.https_port)})
            return FusionComputeTest(auth_token=self.auth_token, name=item, **params)
        else:
            return FusionComputeNew(auth_token=self.auth_token, name=item, **params)

    # 登录
    def _log_on(self):
        try:
            url = "https://{}:{}/service/session".format(self.host, self.https_port)
            headers = {
                "X-Auth-User": self.account,
                # "X-Auth-Key": hashlib.sha256(self.password).hexdigest(),
                "X-Auth-Key": hashlib.sha256(self.password.encode("utf8")).hexdigest(),
                "X-Auth-UserType": "0",
                # "X-ENCRIPT-ALGORITHM": "1"
            }
            headers.update(self.cw_headers)
            resp = requests.post(url=url, headers=headers, json=None, verify=False)
            auth_token = ""
            if resp.status_code < 300:
                auth_token = resp.headers.get("X-Auth-Token", "")
            else:
                logger.exception(eval(resp.content)["errorDes"])
            return auth_token
        except Exception as e:
            logger.exception(e)
            return ""

    def _log_on_new(self):
        """8.0.3 获取 token"""
        try:
            url = "https://{}.{}/v3/auth/tokens".format("iam-apigateway-proxy", self.host)
            json_params = {
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {"domain": {"name": self.account}, "name": self.account, "password": self.password}
                        },
                    },
                    "scope": {"project": {"id": self.project_id, "domain": {"name": self.account}}},
                }
            }
            resp = requests.post(url=url, headers=self.cw_headers, json=json_params, verify=False)
            auth_token = ""
            user_id = ""
            if resp.status_code < 300:
                auth_token = resp.headers.get("X-Subject-Token", "")
                user_id = resp.json().get("token").get("user").get("id")
            else:
                logger.exception("获取Token失败")
            return auth_token, user_id
        except Exception as e:
            logger.exception(e)
            return "", ""


class FusionComputeTest(PrivateCloudManage):
    """
    This class providing all operations on fusioncompute plcatform.
    """

    def __init__(self, auth_token, name, **kwargs):
        self.auth_token = auth_token
        self.name = name
        self.cw_headers = kwargs.get("cw_headers", "")
        self.basic_url = kwargs.get("basic_url", "")

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @staticmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        """
        check if this object works.
        :return: A dict with a “key: value” pair of object. The key name is result, and the value is a boolean type.
        :rtype: dict
        """
        if self.auth_token:
            return {"result": True}
        return {"result": False}

    @staticmethod
    def __site_format(site_obj):
        if site_obj:
            return Region(
                resource_id=site_obj["urn"],
                resource_name=site_obj["name"],
                cloud_type=CloudType.FUSIONCOMPUTE.value,
                # text=site_obj["name"],
                # platform_type=CloudType.FUSIONCOMPUTE.value,
                desc="",
                status="AVAILABLE",
                extra={
                    "site_ip": site_obj["ip"],
                    "isDc": site_obj["isDC"],
                    "isSelf": site_obj["isSelf"],
                    "site_status": FusionComputeSiteStatus[site_obj["status"] + "_cn"],
                },
            ).to_dict()
        else:
            return None

    def __get_sites(self):
        """
        Get all site.(site is the highest level of the resource pool.)
        :return: site info list.
        """
        site_list = []
        site_uri = get_resource_uri(self.basic_url)["site_uri"]
        resp = requests.get(url=site_uri, headers=self.cw_headers, params=None, verify=False)
        if resp.status_code < 300:
            for i in resp.json().get("sites", ""):
                site_list.append(self.__site_format(i))
        return site_list

    # 将fusioncompute的多site抽象成多region
    def get_regions(self, **kwargs):
        """
        Get regions list.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": True, "data": self.__get_sites()}

    def __zone_format(self, zone_obj):
        if zone_obj:
            return Zone(
                id=zone_obj["urn"],
                name=zone_obj["name"],
                platform_type=CloudType.FUSIONCOMPUTE.value,
                description="",
                status="",
                created_time="",
                updated_time="",
                extra={},
            ).to_dict()
        else:
            return None

    # 将fusioncompute的cluster抽象成多zone
    def get_zones(self, **kwargs):
        """
        Get cluster and host list.
        :rtype: dict
        """
        cluster_list_rs = self.get_clusters()
        zone_list = []
        if cluster_list_rs["result"]:
            zone_list = [self.__zone_format(cur_cluster) for cur_cluster in cluster_list_rs["data"]]
        return {"result": True, "data": zone_list}

    def get_projects(self, **kwargs):
        """
        get project list on cloud platforms
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "无项目信息！"}

    def get_domains(self, **kwargs):
        """
        get domain list on cloud platforms
        :param kwargs: accept multiple key value pair arguments
        :rtype: dict
        """
        return {"result": False, "message": "无域名信息！"}

    # ------------------***** compute *****-------------------
    def get_flavors(self, **kwargs):
        """
        get flavor list on cloud platforms
        :param kwargs:
        :rtype: dict
        """
        return {"result": False, "message": "无配置列表信息！"}

    def get_flavor_detail(self, uuid=None, **kwargs):
        """
        Get a specific flavor.
        :param uuid: flavor universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "无查看详细配置信息！"}

    def __vm_obj_format(self, vm_obj, os_version_dict=None):
        """
        Format VM Object.
        :param vm_obj: the object of a specific vm.
        :rtype: dict
        """
        if not vm_obj:
            return None
        site_urn = vm_obj["urn"].split(":vms:")[0]
        site_obj = None
        site_list = self.__get_sites()
        for cur_site in site_list:
            if cur_site["id"] == site_urn:
                site_obj = cur_site
        vm_config = vm_obj["vmConfig"]
        vcpus = vm_config["cpu"]["quantity"]
        mem = vm_config["memory"]["quantityMB"]
        os_type = vm_obj["osOptions"]["osType"]
        os_type_id = vm_obj["osOptions"]["osVersion"]
        os_name = None
        if os_version_dict:
            os_list = os_version_dict[os_type.lower()]
            for cur_os in os_list:
                if os_type_id == cur_os["id"]:
                    os_name = cur_os.get("versionDes")
                    break
        # handle disk
        disk_list = []
        for cur_disk in vm_config.get("disks"):
            disk_site_obj = None
            for cur_site in site_list:
                if cur_site["id"] == cur_disk["volumeUrn"].split(":volumes:")[0]:
                    disk_site_obj = cur_site
                    break
            disk_list.append(
                {
                    "id": cur_disk["volumeUrn"],
                    "name": cur_disk["diskName"],
                    "device_type": FusionComputeDiskType[cur_disk["type"] + "_cn"],
                    "is_attached": True,
                    "status": "使用中",
                    "platform_type": "vmware_vc",
                    "disk_type": "系统盘" if cur_disk["systemVolume"] else "数据盘",
                    "disk_size": cur_disk["quantityGB"],
                    "description": "",
                    "encrypted": "",
                    "tags": [],
                    "disk_format": cur_disk["volumeFormat"],
                    "project_info": {},
                    "region_info": disk_site_obj,
                    "zone_info": {},
                    "host_info": {"id": vm_obj["urn"], "name": vm_obj["name"]},
                    "snapshot_info": [],
                    "charge_info": {},
                    "created_time": "",
                    "updated_time": "",
                    "extra": {"datastoreName": cur_disk["datastoreName"]},
                }
            )

        inner_ip_list = []
        nic_info = []
        for nic in vm_config["nics"]:
            inner_ip_list.append(nic["ip"])
            nic_info.append({"ip": nic["ip"], "name": nic["name"], "mac": nic["mac"]})
        vm_security_group = self.__get_vms_from_security_groups(site_urn)
        return VM(
            id=vm_obj["urn"],
            name=vm_obj["name"],
            status=handle_vm_status(vm_obj["status"]),
            platform_type=CloudType.FUSIONCOMPUTE.value,
            vcpus=vcpus,
            mem=mem,
            uuid=vm_obj["uuid"],
            flavor_info={},
            image_info={},
            os_name=os_name,
            disk_info=disk_list,
            inner_ip=inner_ip_list,
            public_ip=[],
            nic_info=nic_info,
            security_group_info=[{"id": cur_sg} for cur_sg in vm_security_group.get(vm_obj["urn"], [])],
            project_info={},
            tags=[],
            description=vm_obj["description"],
            snapshot_info=self.list_vm_snapshots(vm_obj["urn"]).get("data"),
            host_id=vm_obj.get("hostUrn"),
            host_name=vm_obj.get("hostName"),
            created_time="",
            updated_time="",
            region_info=site_obj,
            region_id=site_obj["id"],
            region_name=site_obj["name"],
            end_time="",
            charge_type="",
            zone_info={},
            extra={
                "osType": os_type,
            },
        ).to_dict()

    def __vm_detail(self, vm_urn):
        """
        Get a specific vm detail info.
        :param vm_urn: VM Uniform Resource Name(urn).
        :return: vm detail dict.
        """
        vm_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_urn))["resource_uri"]
        resp = requests.get(url=vm_uri, headers=self.cw_headers, params=None, verify=False)
        if resp.status_code < 300:
            return resp.json()
        else:
            return None

    def get_site_vms(self, site_urn, **kwargs):
        """
        Get all vms on a specific site.
        :param site_urn: Site Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        -------------------
        * limit: Maximum number of items to return. If the value is -1, it will return all vms.(optional)
                 type: int
                 default: -1
        * offset: The initial index from which to return the results.(optional)
                  type: int
                  default: 0
        * is_template: Is it a vm template.(optional)
                      type: boolean.
                      default is False
        -------------------
        :return: tuple(vm list, total size)
        """
        flag = False
        if kwargs.get("limit") is None or int(kwargs.get("limit")) == -1:
            flag = True
            limit = 20
        else:
            limit = int(kwargs.get("limit"))
        vms_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["vms_uri"]
        params = {
            "isTemplate": kwargs.get("is_template", False),
            "limit": limit,
            "offset": int(kwargs.get("offset", 0)),
        }
        vm_list = []
        while True:
            site_vm_rs = requests.get(url=vms_uri, headers=self.cw_headers, params=params, verify=False)
            if site_vm_rs.status_code == 200:
                site_vm_dict = site_vm_rs.json()
                vm_number = site_vm_dict["total"]
                vm_list.extend(site_vm_dict["vms"])
                total = vm_number
                if flag and vm_number > (params["limit"] + params["offset"]):
                    params["offset"] += params["limit"]
                    continue
                else:
                    break
            else:
                vm_list = []
                total = 0
                break
        return vm_list, total

    def get_os_versions(self, site_urn):
        os_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["os_version"]
        resp = requests.get(url=os_uri, headers=self.cw_headers, params=None, verify=False)
        if resp.status_code == 200:
            return resp.json()
        else:
            return None

    def get_vms(self, **kwargs):
        """
        Get vm list on cloud platforms.
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * site_urn: Site Uniform Resource Name(urn).(optional)
                    type: string
        * is_template: is template
                       type: boolean
                       default: False
        -----------------
        :rtype: dict
        """
        if kwargs.get("site_urn"):
            vm_list = []
            os_version_dict = self.get_os_versions(kwargs["site_urn"])
            site_vm_list, total_size = self.get_site_vms(
                kwargs.get("site_urn"), is_template=kwargs.get("is_template", False)
            )
            for cur_vm_obj in site_vm_list:
                vm_detail = self.__vm_detail(cur_vm_obj["urn"])
                vm_list.append(self.__vm_obj_format(vm_detail, os_version_dict))
            return {"result": True, "data": vm_list, "total": total_size}
        else:
            vm_list = []
            total = 0
            for cur_site in self.__get_sites():
                os_version_dict = self.get_os_versions(cur_site["id"])
                cur_site_vm_list, cur_total_size = self.get_site_vms(
                    cur_site["id"], is_template=kwargs.get("is_template", False)
                )
                for cur_vm_obj in cur_site_vm_list:
                    vm_detail = self.__vm_detail(cur_vm_obj["urn"])
                    vm_list.append(self.__vm_obj_format(vm_detail, os_version_dict))
                total += cur_total_size
        return {"result": True, "data": vm_list, "total": total}

    def get_vm_detail(self, vm_urn):
        """
        Get a specific vm.
        :param vm_urn: VM Uniform Resource Name(urn).
        :rtype: dict
        """
        vm_obj = self.__vm_detail(vm_urn)
        return {"result": True, "data": self.__vm_obj_format(vm_obj)}

    def create_vm(self, **kwargs):
        """
        Create a vm.
        :param kwargs: accept multiple key value pair arguments.
                    site_urn:站点信息。类型：string。必选
                    name：虚拟机名称 长度为[0,256]。类型：string。
                    description：虚拟机描述信息 长度[0,1024]。类型：string。
                    group：虚拟机组名称。类型：string。
                    location：虚拟机所属，可以是集群或主机。类型：string。必选
                    isBindingHost：是否与主机绑定。类型：boolean。
                    template_id: 模板Id，类型：string.
                    vmConfig：虚拟机配置。类型：vmConfig。必选。
                        vmConfig：
                           cpu：CPU规格，创建时必选，查询响应中必选。其他情况下可选。类型：structure。
                                quantity:虚拟机的总核数。类型：integer。
                                coresPerSocket：每CPU插槽的CPU核数，要求能够整除虚拟机的总核数。类型：integer。
                                reservation：虚拟机cpu的预留值，单位为MHz，默认0，0代表不预留。类型：integer。
                                weight：虚拟机cpu的份额，个数。默认quantity*1000。类型：integer。
                                limit：虚拟机cpu上限，单位是MHz，默认为0，0代表不限制。类型：integer。
                                cpuHotPlug：CPU热插拔开关（预留），作用是通过开关判断虚拟机是否支持CPU热插拔，
                                包括: 0 : 禁用CPU热插拔、1: 启用CPU热插、2: 启用CPU热插拔，可选，默认为0，
                                表示禁用CPU热插拔。类型：integer。
                                affinitySet：表示虚拟机只能运行在节点的这些CPU上。类型：integer[]。
                                hanaAffinitySet:表示设置每个vcpu的绑定位图，与affinitySet不能同时为有效值。类型：structure[]
                                    vcpuScope：Vcpu编号。类型：integer。
                                    pcpuScope：Pcpu位图。类型：string。
                           Memory：内存规格。创建时必选，查询响应中必选。其他情况下可选。类型：structure。
                                quantityMB:虚拟机内存总大小(单位M).类型：integer。
                                reservation:虚拟机内存的预留值，单位为M。默认0，0代表不预留。类型：integer。
                                weight:虚拟机内存的份额，个数，默认quantity*10。类型：integer。
                                limit:虚拟机内存上限，单位是M，大小为虚拟机内存大小。类型：integer。
                                memHotPlug:mem热插开关（预留），作用是通过开关判断虚拟机是否支持内存热插，包括禁用内存热插(0)、
                                启用内存热插(1)，默认禁用内存热插拔(0)。类型：integer。
                           disks：磁盘规格。类型：structure[]。最多为28个。
                                pciType：磁盘挂载的总线类型。类型：String。
                                sequenceNum：磁盘对应的总线槽位编号。类型：integer。
                                volumeUrn：硬盘对应卷标识，表示使用已有的卷。类型：String。
                                volumeUrl：卷的URL。类型：String。
                                volumeUuid：注册虚拟机时必选。类型：String。
                                quantityGB：虚拟机磁盘大小。类型：integer。
                                isDataCopy：克隆/模板部署时，是否从虚拟机/模板对应的硬盘复制数据。类型：boolean。
                                datastoreUrn：存储URI地址。类型：String。
                                isThin：是否精简制备. 在volumeUrn不携带时，生效。可选，默认false.类型：boolean。
                                indepDisk：是否独立磁盘，可选字段，不携带时表示否。类型：boolean。
                                persistentDisk：是否持久化磁盘。类型：boolean。
                                storageType：存储类型。类型：String。
                                volType：磁盘类型参数，支持创建、查询虚拟机接口，取值为：0：普通卷。1：延迟置零卷
                                类型：integer。
                                maxReadBytes：每秒最大读字节数，单位为KB/s，类型：long。
                                maxWriteBytes：每秒最大写字节数，单位为KB/s，类型：long。
                                maxReadRequest：每秒最大读请求个数，单位为个/s，类型：long。
                                maxWriteRequest：每秒最大写请求个数，单位为个/s，类型：long。
                                type：卷类型，注册虚拟机（必选）。类型：String。
                                diskName：卷名称,长度[0,256]，可以重复。类型：String。
                                ioWeight：磁盘IO控制，用于动态调整IO（预留）。类型：long。
                                datastoreName：磁盘所在datastore名称，类型：String。
                                isCoverData：是否覆盖指定卷（已有卷）中原有的数据。类型：boolean。
                            nics：可选。类型：ref[]。
                                name：虚拟机网卡名称。类型：string
                                urn：网卡标识，仅查询响应中携带。类型：string
                                uri：访问网卡的uri，仅查询响应中携带。
                                portGroupUrn：portGroup 标识，必选。修改网卡时可选。类型：string
                                portGroupName：portGroup名称，可选。类型：string
                                mac：Mac地址，系统内部分配。类型：string
                                ip：Ipv4地址，系统内部分配或从虚拟机内部获取的ip。类型：string[]
                                ips6：IPv6地址列表。类型：string[]
                                sequenceNum：网卡对应的总线编号，0-11。可选。类型：integer。
                                virtIo：网卡类型。类型：integer。
                                ipList：虚拟机所有网卡的IP地址。类型：string。
                                nicType：网卡类型。类型：integer。
                                portId：虚拟机交换机端口 ID，可选。类型：string。
                                isDisableSG：是否去使能安全组。默认值0；1：不支持安全组；0：支持安全组，类型：integer
                            usb：USB配置，可选，包括控制器和设备。类型：structure。
                            gpu：目前只支持一个，即gpu与虚拟机一对一关系。类型：Structure[]。
                    autoBoot：是否自动启动。类型：boolean。
                    osOptions：虚拟机操作系统信息。类型：ref。可选。
                       osType：虚拟机操作系统类型，创建虚拟机时必选。类型：string。
                       osVersion：操作系统版本号，创建虚拟机时必选，修改时可选。类型：integer。
                       guestOSName：guestOS名称，可选。类型：string。
                    vncAccessInfo：VNC设置，目前仅支持设置vncpassword。类型：structure。
                        hostIp：虚拟机所在主机IP地址，null为非法值，其他未合法值。类型：string。
                        vncPort：虚拟机VNC端口，-1为非法值，其他为合法值。类型：integer。
                        vncPassword：虚拟机VNC密码。类型：string。
                        vncOldPassword：当前虚拟机VNC密码，修改VNC密码时有效。类型：string。
                    isTemplate：部署成vm还是模板，true：模版，false:虚拟机，默认false, 即：vm类型：boolean。
                    isLinkClone：和isTemplate不能同时为true。true为创建链接克隆虚拟机，默认是false。类型：boolean。
                    regionInfo：ID盘信息。类型：string。
                    vmCustomization：虚拟机自定义配置。类型：ref.
                        password：虚拟机密码，类型：string。
                        osType：操作系统类型：类型：string。
                        workgroup：虚拟机工作组，可选；类型：string。
                        nicSpecification：网卡配置。类型：structure[]
                            sequenceNum：自定义规范的网卡对应编号，1-12。必选。不可重复，类型：integer
                            ip：虚拟机网卡IP地址，可选。类型：string。必选
                            netmask：虚拟机网卡子网掩码，可选；类型：string。必选。
                            gateway：虚拟机网卡默认网关，可选；类型：string。
                            setdns：虚拟机网卡首选DNS服务器，可选；类型：string。
        :rtype: dict
        """
        list_required_params = ["name", "vmConfig", "site_urn", "location", "vmCustomization", "template_id"]
        check_required_params(list_required_params, kwargs)
        vms_uri = "{}/{}/action/clone".format(
            get_resource_uri(self.basic_url, urn_transform_uri(kwargs.get("site_urn")))["vms_uri"],
            kwargs.get("template_id").split(":")[4].strip(),
        )
        body = {
            "name": kwargs.get("name"),
            "parentObjUrn": "urn:sites:61EF0A3D",
            "vmConfig": kwargs.get("vmConfig"),
            "location": kwargs.get("location"),
            "vmCustomization": kwargs.get("vmCustomization"),
        }
        res = requests.post(url=vms_uri, headers=self.cw_headers, json=body, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.content}
        else:
            return {"result": False, "message": "create vm failed"}

    def start_vm(self, vm_id, *args, **kwargs):
        """
        Start a vm.
        :param vm_id: VM Uniform Resource Name(urn).
        :rtype: dict
        """
        vm_start_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_id))["vm_start_uri"]
        res = requests.post(url=vm_start_uri, headers=self.cw_headers, json=None, verify=False)
        if res.status_code == 200:
            return {"result": True}
        else:
            return {"result": False, "message": res.text}

    def stop_vm(self, vm_id, **kwargs):
        """
        Stop a vm.
        :param vm_id: VM Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        --------------
        mode: stop mode.(option)
              type: string
              safe | force
              default is safe.
        --------------
        :rtype: dict
        """
        vm_stop_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_id))["vm_stop_uri"]
        param = {"mode": kwargs.get("mode", "safe")}
        res = requests.post(url=vm_stop_uri, headers=self.cw_headers, json=param, verify=False)
        if res.status_code == 200:
            return {"result": True}
        else:
            return {"result": False, "message": res.text}

    def restart_vm(self, vm_urn, **kwargs):
        """
        Restart a vm.
        :param vm_urn: VM Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        --------------
        mode: stop mode.(option)
              type: string
              safe | force
              default is safe.
        --------------
        :rtype: dict
        """
        vm_reboot_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_urn))["vm_reboot_uri"]
        param = {"mode": kwargs.get("mode", "safe")}
        res = requests.post(url=vm_reboot_uri, headers=self.cw_headers, json=param, verify=False)
        if res.status_code == 200:
            return {"result": True}
        else:
            return {"result": False, "message": res.text}

    def modify_vm(self, vm_urn, **kwargs):
        """
        Resize a vm.
        :param vm_urn: VM Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        ----------------
        * name: the name of the vm.(optional)
                type: string
        * description: the description of the vm.(optional)
                       type: string
        * group: the group name of the vm.(optional)
                 type: string
        * location: vm location.(optional)
                    type: string
        * externalUuid: modify external uuid.(optional)
                        type: string
        * isTemplate: is template.(optional)
                      type: boolean
        * cpu: (optional).
            type: structure
            properties:
                * quantity: cpu cores. range [1, 64](optional)
                            type: integer
                * coresPerSocket: cpu cores per socket.(optional)
                                  type: integer
                * reservation: cpu reservation. MHz.(optional)
                               type: integer
                * weight: cpu weight.(optional)
                          type: integer
                * limit: cpu limit. MHz.(optional)
                         type: integer
                * cpuHotPlug: cpu hot plug. 0: disable, 1: enable
                              type: integer
                * affinitySet: cpu affinity set. assign vm run on a specific cpu.
                               type: integer[]
        * memory: (optional)
            type: structure
            properties:
                * quantity: memory size.(optional). MB
                            type: integer
                * reservation: memory reservation.(optional). MB
                * weight: memory weight.(optional)
                          type: integer
                * limit: memory limit.(optional)
                         type: integer
                * memHotPlug: memory hot plug. 0: disable, 1: enable
                              type: integer
        * properties: (optional)
            type:: map
            properties:
                * bootOption: vm boot option.(optional)
                              cdrom | disk | pxe
                              type: string
                * isEnableHa: enable HA.(optianal)
                              type: boolean
                * ......
                * ......
        ----------------
        :rtype: dict
        """
        vm_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_urn))["resource_uri"]
        res = requests.put(url=vm_uri, headers=self.cw_headers, json=kwargs, verify=False)
        if res.status_code == 200:
            return {"result": True}
        else:
            return {"result": False, "message": res.text}

    def destroy_vm(self, vm_id):
        """
        Destroy a vm.
        :param vm_id: VM Uniform Resource Name(urn).
        :rtype: dict
        """
        vm_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_id))["resource_uri"]
        res = requests.delete(url=vm_uri, headers=self.cw_headers, json=None, verify=False)
        if res.status_code == 200:
            return {"result": True}
        else:
            return {"result": False, "message": res.text}

    def get_available_specs(self, **kwargs):
        """
        Get available specs.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        try:
            return {"result": True, "data": kwargs["config"]}
        except Exception as e:
            logger.exception("get available vm failed!")
            return {"result": False, "message": str(e)}

    def add_vm_disk(self, vm_urn, **kwargs):
        """
        Create a disk and attach to a specific vm.
        :param vm_urn: VM Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * name: the name of disk.(required)
                type: string
        * quantityGB: disk size.(required) GB
                      type: integer
        * datastoreUrn: data storage urn.(required)
                        type: string
        * isThin: is thin.(required)
                  type: boolean
        * type: disk type.(required)
                normal | share
                type: string
        -----------------
        :rtype: dict
        """
        vm_add_disk_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_urn))["vm_add_disk_uri"]
        json_obj = {
            "name": kwargs.get("name", ""),
            "quantityGB": kwargs.get("quantityGB", 1),
            "datastoreUrn": kwargs.get("datastoreUrn"),
            "isThin": kwargs.get("isThin", False),
            "type": kwargs.get("type", "normal"),
        }
        res = requests.post(url=vm_add_disk_uri, headers=self.cw_headers, json=json_obj, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def remote_connect_vm(self, **kwargs):
        """
        Connect to a remote vm desktop.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "远程登入方法暂时未实现！"}

    def get_vm_disks(self, ids):
        """
        Get all disks from a specific VM instance.
        :param ids: []
        :rtype: dict
        """
        vm_obj = self.__vm_detail(ids[0])
        vm_disk_list = []
        for cur_disk in vm_obj["vmConfig"]["disks"]:
            disk_obj = {
                "disk_name": cur_disk.get("diskName"),
                "disk_size": cur_disk.get("quantityGB"),
                "type": "system" if cur_disk.get("systemVolume") else "data",
                "disk_zone": cur_disk.get("volumeUrn"),
                "disk_store_name": cur_disk.get("datastoreName"),
                "disk_number": cur_disk.get("sequenceNum"),
            }
            vm_disk_list.append(disk_obj)
        return {"result": True, "data": vm_disk_list}

    # ------------------***** snapshot *****------------------
    def __snapshot_format(self, snapshot_obj):
        """
        Format snapshot object.
        :param snapshot_obj: snapshot object.
        :return: dict
        """
        snapshot_list = []
        for cur_obj in snapshot_obj:
            site_urn = cur_obj["urn"].split(":vms:")[0]
            site_obj = None
            site_list = self.__get_sites()
            for cur_site in site_list:
                if cur_site["id"] == site_urn:
                    site_obj = cur_site
                    break
            snapshot_detail = self.get_snapshot_detail(cur_obj["urn"])
            if snapshot_detail:
                snapshot_list.append(
                    Snapshot(
                        id=snapshot_detail["urn"],
                        name=snapshot_detail["name"],
                        snapshot_type=FusionComputeSnapshotType[snapshot_detail["type"] + "_cn"],
                        snapshot_size=float(snapshot_detail["snapProvisionSize"]) / 1024,
                        disk_id=snapshot_detail["volsnapshots"][0]["volumeUrn"],
                        disk_name="",
                        status=handle_snapshot_status(snapshot_detail["status"]),
                        platform_type=CloudType.FUSIONCOMPUTE.value,
                        encrypted="",
                        tags=[],
                        server_id="",
                        server_name="",
                        description=snapshot_detail["description"],
                        created_time=snapshot_detail["createTime"],
                        updated_time="",
                        project_info={},
                        region_info=site_obj,
                        zone_info={},
                        extra={},
                    ).to_dict()
                )
            if cur_obj["childSnapshots"]:
                snapshot_rs = self.__snapshot_format(cur_obj["childSnapshots"])
                if snapshot_rs:
                    snapshot_list.extend(snapshot_rs)
                else:
                    return None
        return snapshot_list

    def create_snapshot(self, vm_urn, **kwargs):
        """
        Create a snapshot from a specific vm.
        :param vm_urn: VM Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * name: the name of new snapshot.(required)
                type: string
        * description: Description of the snapshot.(optional)
                       type: string
        * needMemoryShot: memory snapshot(optional)
                          type: boolean
                          default: false
        * isConsistent: is consistent.(optional)
                        type: boolean
                        default: false
        * type: snapshot type.(optional)
                type: string
                normal | backup | CBTbackup
                default: normal
        ---------------
        :rtype: dict
        """
        json_obj = {
            "name": kwargs.get("name"),
            "description": kwargs.get("description"),
            "needMemoryShot": kwargs.get("needMemoryShot", False),
            "isConsistent": kwargs.get("isConsistent", False),
            "type": kwargs.get("type", "normal"),
        }
        vm_snapshot_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_urn))["vm_snapshot_uri"]
        res = requests.post(url=vm_snapshot_uri, headers=self.cw_headers, json=json_obj, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()["urn"]}
        else:
            return {"result": False, "message": res.text}

    def delete_snapshot(self, snapshot_id, *args, **kwargs):
        """
        Delete a snapshot from a specific vm
        :param snapshot_id: Snapshot Uniform Resource Name(urn).
        :rtype: dict
        """
        vm_snapshot_uri = get_resource_uri(self.basic_url, urn_transform_uri(snapshot_id))["resource_uri"]
        res = requests.delete(url=vm_snapshot_uri, headers=self.cw_headers, json=None, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def list_snapshots(self, **kwargs):
        """
        Get all snapshots.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "暂不支持获取所有虚拟机快照！"}

    def list_vm_snapshots(self, ids):
        """
        Get all snapshots from a specific vm.
        :param ids:
        :rtype: dict
        """
        vm_snapshot_uri = get_resource_uri(self.basic_url, urn_transform_uri(ids[0]))["vm_snapshot_uri"]
        res = requests.get(url=vm_snapshot_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": self.__snapshot_format(res.json()["rootSnapshots"])}
        else:
            return {"result": False, "message": res.text}

    def get_snapshot_detail(self, snapshot_urn, **kwargs):
        """
        Get a specific snapshot detail info.
        :param snapshot_urn: Snapshot Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * refresh_flag: refresh snapshot
                        type: boolean
                        default: False
        --------------
        :rtype: dict
        """
        refresh_flag = kwargs.get("refresh_flag", False)
        params = {"refreshflag": refresh_flag}
        snapshot_uri = get_resource_uri(self.basic_url, urn_transform_uri(snapshot_urn))["resource_uri"]
        res = requests.get(url=snapshot_uri, headers=self.cw_headers, params=params, verify=False)
        if res.status_code == 200:
            return res.json()
        else:
            return None

    def restore_snapshot(self, snapshot_id):
        """
        Recover a specific vm from a specific snapshot.
        :param snapshot_id: Snapshot Uniform Resource Name(urn).
        :rtype: dict
        """
        vm_snapshot_resume_uri = get_resource_uri(self.basic_url, urn_transform_uri(snapshot_id))[
            "vm_snapshot_resume_uri"
        ]
        res = requests.post(url=vm_snapshot_resume_uri, headers=self.cw_headers, json=None, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    # ------------------***** tag *****------------------
    def create_tag(self, **kwargs):
        """
        Create a tag.
        :param kwargs: accept multiple key value pair arguments.
        :return:
        """
        return {"result": False, "message": "FusionCompute无标签创建功能！"}

    def delete_tag(self, **kwargs):
        """
        Delete a tag.
        :param kwargs:
        :return: accept multiple key value pair arguments.
        """
        return {"result": False, "message": "FusionCompute无标签删除功能！"}

    def update_tag(self, uuid, **kwargs):
        """
        Update key-value of a tag.
        :param uuid: tag universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "FusionCompute无标签更新功能！"}

    def get_tags(self, **kwargs):
        """
        Get tag list on cloud platforms.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "FusionCompute无获取标签列表功能！"}

    def remove_resource_tag(self, uuid, **kwargs):
        """
        Delete a specific tag from a specific resource.
        :param uuid: the ID of resource
        :param kwargs: accept multiple key value pair arguments.
        """
        return {"result": False, "message": "FusionCompute无删除指定资源的标签创建功能！"}

    def get_resource_tags(self, uuid, **kwargs):
        """
        Get all tags from a specific resource.
        :param uuid: the ID of resource
        :param kwargs: accept multiple key value pair arguments.
        """
        return {"result": False, "message": "FusionCompute无获取指定资源的标签功能！"}

    # ------------------***** storage *****-------------------
    def __get_ds_disks(self, site_urn, ds_urn):
        """
        Get all disk under a specific datastore.
        :param site_urn: Site Uniform Resource Name(urn).
        :param ds_urn: Data Store Uniform Resource Name(urn).
        :return: tuple(disk list, disk number)
        """
        flag = False
        disk_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["datastore_volumes"]
        params = {"limit": 20, "offset": 0, "dsUrn": ds_urn}
        disk_list_total = []
        disk_num_total = 0
        while True:
            res = requests.get(url=disk_uri, headers=self.cw_headers, params=params, verify=False)
            if res.status_code == 200:
                disk_obj = res.json()
                disk_number = disk_obj["total"]
                disk_num_total += len(disk_obj["volumes"])
                disk_list_total.extend(disk_obj["volumes"])
                if flag and disk_number > (params["limit"] + params["offset"]):
                    params["offset"] += params["limit"]
                    continue
                else:
                    break
            else:
                disk_list_total = []
                disk_num_total = 0
                break
        return disk_list_total, disk_num_total

    def __get_site_disks(self, site_urn, **kwargs):
        """
        Get all disk from a specific site.
        :param site_urn: Site Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        :return: tuple(disk list, disk number)
        """
        local_storage_rs = self.get_local_storage(site_urn=site_urn)
        if local_storage_rs["result"]:
            disk_list_total = []
            disk_num_total = 0
            for cur_ds in local_storage_rs["data"]:
                cur_disk_list, cur_num = self.__get_ds_disks(site_urn, cur_ds["id"])
                disk_list_total.extend(cur_disk_list)
                disk_num_total += cur_num
            return disk_list_total, disk_num_total
        else:
            return [], 0

    def __disk_format(self, disk_obj, site_obj):
        disk_origin_obj = self.__disk_detail(disk_obj["urn"])
        if disk_origin_obj:
            disk_obj.update(disk_origin_obj)
        disk_name = disk_obj["name"]
        if disk_obj.get("vmUrn"):
            status = handle_disk_status("in-use")
        else:
            status = handle_disk_status(disk_obj["status"])
        if disk_obj:
            return Disk(
                id=disk_obj["urn"],
                name=disk_name,
                device_type=FusionComputeDiskType[disk_obj["type"].lower() + "_cn"],
                status=status,
                disk_size=disk_obj.get("quantityGB"),
                platform_type=CloudType.FUSIONCOMPUTE.value,
                is_attached=True if disk_obj.get("vmUrn") else False,
                disk_type="系统盘" if disk_name.endswith("-vda") else "数据盘",
                description="",
                encrypted="",
                tags=[],
                disk_format=disk_obj["volumeFormat"],
                project_info={},
                region_info=site_obj,
                zone_id="",
                zone_name="",
                server_id=disk_obj["vmUrn"] if disk_obj.get("vmUrn") else "",
                server_name=disk_obj["vmName"] if disk_obj.get("vmUrn") else "",
                snapshot_info=[],
                charge_type="",
                end_time="",
                created_time="",
                updated_time="",
                extra={
                    "isThin": "精简置备" if disk_obj.get("isThin") else "厚置备",
                    "datastoreName": disk_obj.get("datastoreName"),
                    "datastoreUrn": disk_obj.get("datastoreUrn"),
                },
            ).to_dict()
        else:
            return None

    def __disk_detail(self, disk_urn, **kwargs):
        """
        Get a specific disk detail info.
        :param disk_urn: Disk Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        ------------------
        * refreshflag: refresh snapshot.
                       type: boolean
                       default: false
        ------------------
        :return: disk detail dict.
        """
        params = {"refreshflag": kwargs.get("refreshflag", False)}
        disk_uri = get_resource_uri(self.basic_url, urn_transform_uri(disk_urn))["resource_uri"]
        res = requests.get(url=disk_uri, headers=self.cw_headers, params=params, verify=False)
        if res.status_code == 200:
            return res.json()
        else:
            return None

    def get_disks(self, **kwargs):
        """
        Get disk list on cloud platforms.
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * site_urn: search disk from a specific site. if this property is not set,
                    it will return all disk from all sites.(optional)
                    type: string
        ---------------
        :rtype: dict
        """
        site_list = self.__get_sites()
        if kwargs.get("site_urn"):
            disk_list, disk_number = self.__get_site_disks(kwargs.get("site_urn"))
            site_obj = None
            for cur_site in site_list:
                if cur_site["id"] == kwargs.get("site_urn"):
                    site_obj = cur_site
                    break
            return {
                "result": True,
                "data": [self.__disk_format(cur_disk, site_obj) for cur_disk in disk_list],
                "total": disk_number,
            }
        else:
            disk_total_list = []
            total_num = 0
            for cur_site in site_list:
                disk_list, disk_number = self.__get_site_disks(cur_site.get("id"))
                total_num += disk_number
                disk_format_list = []
                for cur_disk in disk_list:
                    disk_format_list.append(self.__disk_format(cur_disk, cur_site))
                disk_total_list.extend(disk_format_list)
            return {"result": True, "data": disk_total_list, "total": total_num}

    def get_disk_detail(self, disk_urn, **kwargs):
        """
        Get a specific disk.
        :param disk_urn: Disk Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        ------------------
        * refreshflag: refresh snapshot.
                       type: boolean
                       default: false
        ------------------
        :rtype: dict
        """
        disk_format_obj = None
        site_obj = None
        site_list = self.__get_sites()
        site_urn = disk_urn.split(":volumes:")[0]
        for cur_site in site_list:
            if cur_site["id"] == site_urn:
                site_obj = cur_site
                break
        disk_list, disk_number = self.__get_site_disks(site_urn)
        for cur_disk in disk_list:
            if cur_disk["urn"] == disk_urn:
                disk_format_obj = self.__disk_format(cur_disk, site_obj)
                break
        return {"result": True, "data": disk_format_obj}

    def create_disk(self, **kwargs):
        """
        Create a disk.
        :param kwargs: accept multiple key value pair arguments.
        ----------------
        * name: the name of disk.(required)
                type: string
        * site_urn: Site Uniform Resource Name(urn).(required)
        * quantityGB: disk size(GB).(required)
                      type: integer
        * datastoreUrn: Datastore Uniform Resource Name(urn).(required)
                        type: string
        * type: disk type.(required)
                type: string
                normal | share
        * isThin: is thin.(optional)
                  type: boolean
                  default: false
        * ......
        * ......
        ----------------
        :rtype: dict
        """
        json_obj = kwargs
        disk_uri = get_resource_uri(self.basic_url, urn_transform_uri(kwargs["site_urn"]))["disk_uri"]
        res = requests.post(url=disk_uri, headers=self.cw_headers, json=json_obj, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()["urn"]}
        else:
            return {"result": False, "message": res.text}

    def attach_disk(self, **kwargs):
        """
        Attach a specific disk to a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        ----------------
        * vm_urn: VM Uniform Resource Name(urn).
                  type: string
        * disk_urn: Disk Uniform Resource Name(urn).(required)
                    type: string
        * pci_type: bus type.(optional)
                    type: string
                    IDE | SCSI | VIRTIO
                    default: VIRTIO
        * sequence_num: disk slot.(optional)
                       type: integer
        ----------------
        :rtype: dict
        """
        json_obj = {"volUrn": kwargs.get("disk_urn"), "pciType": kwargs.get("pci_type", "VIRTIO")}
        if kwargs.get("sequenceNum"):
            json_obj.update({"sequenceNum": kwargs.get("sequenceNum")})
        vm_attach_disk_uri = get_resource_uri(self.basic_url, urn_transform_uri(kwargs.get("vm_urn")))[
            "vm_attach_disk_uri"
        ]
        res = requests.post(url=vm_attach_disk_uri, headers=self.cw_headers, json=json_obj, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def detach_disk(self, **kwargs):
        """
        Detach a specific disk from a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        : vm_urn: VM Uniform Resource Name(urn).(required)
                  type: str
        * disk_urn: Disk Uniform Resource Name(urn).(required)
                    type: string
        * is_format: format disk.(optional)
                     type: boolean
                     default: false
        ---------------
        :rtype: dict
        """
        vm_urn = kwargs.get("vm_urn")
        json_obj = {"volUrn": kwargs.get("disk_urn"), "isFormat": kwargs.get("is_format", False)}
        vm_detach_disk_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_urn))["vm_detach_disk_uri"]
        res = requests.post(url=vm_detach_disk_uri, headers=self.cw_headers, json=json_obj, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def delete_disk(self, disk_id, *args, **kwargs):
        """
        Delete a specific disk.
        :param disk_id: Disk Uniform Resource Name(urn).
        :rtype: dict
        """
        disk_delete_uri = get_resource_uri(self.basic_url, urn_transform_uri(disk_id))["resource_uri"]
        res = requests.delete(url=disk_delete_uri, headers=self.cw_headers, json=None, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def extend_disk(self, disk_urn, **kwargs):
        """
        extend a specific available disk
        :param disk_urn: Disk Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * size: the size of disk(GB).(required)
                type: long
        -----------------
        :rtype: dict
        """
        json_obj = {"size": int(kwargs.get("size")) * 1024}
        disk_extend__uri = get_resource_uri(self.basic_url, urn_transform_uri(disk_urn))["disk_expand_uri"]
        res = requests.post(url=disk_extend__uri, headers=self.cw_headers, json=json_obj, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def __image_format(self, image_obj):
        if image_obj:
            return Image(
                id=image_obj["id"],
                name=image_obj["name"],
                image_size="",
                status="",
                platform_type=CloudType.FUSIONCOMPUTE.value,
                image_platform=image_obj["os_name"],
                image_type="私有",
                tags=image_obj["tags"],
                description=image_obj["description"],
                created_time=image_obj["created_time"],
                updated_time=image_obj["updated_time"],
                os_arch="",
                os_bit="",
                os_type=image_obj["extra"]["osType"],
                image_format="",
                project_info=image_obj["project_info"],
                region_info=image_obj["region_info"],
                zone_info=image_obj["zone_info"],
                visibility="",
                extra={},
            ).to_dict()
        else:
            return None

    def get_images(self, **kwargs):
        """
        Get image list.
        :param kwargs: accept multiple key value pair arguments.
        ------------------
        * site_urn: get all images under the specific site.
                    if this value is not set, it will return all images from all sites.(optional)
        ------------------
        :rtype: dict
        """
        template_rs = self.get_vms(is_template=True)
        if template_rs["result"]:
            return {
                "result": True,
                "data": [self.__image_format(cur_temp) for cur_temp in template_rs["data"]],
                "total": template_rs["total"],
            }
        else:
            return {"result": True, "data": [], "total": 0}

    def get_image_detail(self, image_urn):
        """
        Get a specific image.
        :param image_urn: Image Uniform Resource Name(urn).
        :rtype: dict
        """
        image_obj = self.__vm_detail(image_urn)
        return {"result": True, "data": image_obj}

    def delete_image(self, image_urn, *args, **kwargs):
        """
        Delete a specific image.
        :param image_urn: Image Uniform Resource Name(urn).
        :rtype: dict
        """
        return self.destroy_vm(image_urn)

    # ------------------***** network *****-------------------
    def __security_group_format(self, security_group_obj, site_urn):
        if security_group_obj:
            return SecurityGroup(
                id=security_group_obj.get("sgId"),
                name=security_group_obj.get("sgName"),
                platform_type=CloudType.FUSIONCOMPUTE.value,
                description="",
                tags=[],
                scope="",
                project_info={},
                region_info={"id": site_urn},
                security_group_rule_info=[],
                created_time="",
                updated_time="",
                extra={},
            ).to_dict()
        else:
            return None

    def __get_vms_from_security_groups(self, site_urn):
        security_group_list = self.__get_security_groups_origin(site_urn)
        vm_sg_dict = {}
        for cur_sg in security_group_list:
            for cur_vm in cur_sg["vmList"]:
                if vm_sg_dict.get(cur_vm["vmUrn"], None):
                    vm_sg_dict[cur_vm["vmUrn"]].append(cur_sg.get("sgId"))
                else:
                    vm_sg_dict[cur_vm["vmUrn"]] = [cur_sg.get("sgId")]
        return vm_sg_dict

    def __get_security_groups_origin(self, site_urn):
        """
        Get origin security group list.
        :param site_urn:
        :return: list
        """
        security_group_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["security_group_uri"]
        res = requests.get(url=security_group_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code == 200:
            return res.json()["securityGroups"]
        else:
            logger.exception("get security group from openstack api failed.")
            return []

    def get_security_groups(self):
        """
        Get security group list.
        :rtype: dict
        """
        return {"result": False, "message": "FusionCompute安全组较复杂，暂不支持！"}

    def get_security_group_detail(self, sg_urn, **kwargs):
        """
        Get a specific security group.
        :param sg_urn: security group urn.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "方法未实现，无相关api文档！"}

    def destroy_security_group(self, uuid, **kwargs):
        """
        Delete a specific security group.
        :param uuid: uuid: security group universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "方法未实现，无相关api文档！"}

    def create_security_group(self, **kwargs):
        """
        Create a specific security group.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "方法未实现，无相关api文档！"}

    def modify_security_group(self, uuid, **kwargs):
        """
        Modify a specific security group.
        :param uuid: uuid: security group universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "方法未实现，无相关api文档！"}

    def get_security_group_rule(self, uuid, **kwargs):
        """
        Get a specific rule info from a specific security group.
        :param uuid: uuid: security group rule universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "方法未实现，无相关api文档！"}

    def create_security_group_rule(self, **kwargs):
        """
        Create a specific rule from a specific security group.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "方法未实现，无相关api文档！"}

    def destroy_security_group_rule(self, uuid, **kwargs):
        """
        Delete a specific rule info from a specific security group.
        :param uuid: uuid: security group rule universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "方法未实现，无相关api文档！"}

    def __vswitch_format(self, vswitch_obj):
        if vswitch_obj:
            site_urn = vswitch_obj["urn"].split(":dvswitchs:")[0]
            return VPC(
                id=vswitch_obj["urn"],
                name=vswitch_obj["name"],
                platform_type=CloudType.FUSIONCOMPUTE.value,
                status=VPCStatus.ACTIVE.value,
                router_info=[],
                network_addr="",
                is_default=None,
                region_info={"id": site_urn},
                zone_info={"id": ""},
                project_info={},
                description=vswitch_obj["description"],
                tags=[],
                updated_time="",
                created_time="",
                resource_group="",
                extra={},
            ).to_dict()
        return None

    def __get_site_vpcs(self, site_urn):
        """
        Get dvswitch list from a specific site.
        :param site_urn: Site Uniform Resource Name(urn).
        :return: dvswitch list
        """
        dvswitch_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["dvswitch_uri"]
        res = requests.get(url=dvswitch_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code == 200:
            return res.json()["dvSwitchs"]
        else:
            return []

    def get_vpcs(self, **kwargs):
        """
        Get all dvswitchs from all sites.
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        :param site_urn: Site Uniform Resource Name(urn).
        ---------------
        :rtype: dict
        """
        if kwargs.get("site_urn"):
            vpc_list = self.__get_site_vpcs(kwargs.get("site_urn"))
            vpc_format_list = [self.__vswitch_format(self.get_vpc_detail(cur_vpc["urn"])) for cur_vpc in vpc_list]
            return {"result": True, "data": vpc_format_list}
        else:
            dvswitch_list = []
            for cur_site in self.__get_sites():
                site_vpc_list = self.__get_site_vpcs(cur_site["id"])
                vpc_format_list = [
                    self.__vswitch_format(self.get_vpc_detail(cur_vpc["urn"])) for cur_vpc in site_vpc_list
                ]
                dvswitch_list.extend(vpc_format_list)
        return {"result": True, "data": dvswitch_list}

    def create_vpc(self, **kwargs):
        """
        Create a dvswitch.
        :param site_urn: Site Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        -----------------------
        * name: the name of dvswitch.(required)
                type: string
        * description: the description of dvswitch.(optional)
                       type: string
        * type: dvswitch type.(required)
                type: integer
                0: vSwitch 普通模式
                1: eSwitch-VMDQ 直通模式
                2: SR-IOV 直通模式
        * vlanPoolSet: set vlan pool.(optional)
                         type: structure[]
                         * startVlanId: start vlan id.
                                          type: integer
                                          range 1-4096
                         * endVlanId: end vlan id.
                                        type: integer
                                        range 1-4096
        * vxlanPoolSet: set vxlan pool.(optional)
                          type: structure[]
                          * startVxlanId: start vxlan id.
                                            type: integer
                                            range 4096-16777215
                          * endVxlanId: end vxlan id.
                                          type: integer
                                          range 4096-16777215
        * hostPortSet: set host port
                         type: structure[]
                         * host_urn: host urn.
                                     type: string
                         * prort_urn: port urn.
                                      type: string
                         * vtep_info: vtep info.
                                      type: struct
                         * slave_port_info: slave port info.
                                            type: struct
        * isIgmpSnooping: Is IGMP snooping.(optional)
                            type: boolean
        * physnetName: the name of physical network.(optional)
                        type: string
        * mtu: (optional)
               type: integer.
        -----------------------
        :rtype: dict
        """
        site_urn = kwargs.pop("site_urn")
        dvswitch_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["dvswitch_uri"]
        res = requests.post(url=dvswitch_uri, headers=self.cw_headers, json=kwargs, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()["urn"]}
        else:
            return {"result": False, "message": res.text}

    def delete_vpc(self, vpc_id, *args, **kwargs):
        """
        Delete a specific dvswtich.
        :param vpc_id: VDSwitch Uniform Resource Name(urn).
        :rtype: dict
        """
        dvswitch_uri = get_resource_uri(self.basic_url, urn_transform_uri(vpc_id))["resource_uri"]
        res = requests.delete(url=dvswitch_uri, headers=self.cw_headers, json=None, verify=False)
        if res.status_code == 200:
            return {"result": True}
        else:
            return {"result": False, "message": res.text}

    def modify_vpc(self, vpc_urn, **kwargs):
        """
        Modify a specific dvswitch.
        :param vpc_urn: VDSwitch Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * name: the name of dvswitch.(optional)
                type: string
        * description: the description of dvswitch.(optional)
                       type: string
        * isIgmpSnooping: is igmp snooping.(optional)
                            type: boolean
        ---------------
        :rtype: dict
        """
        dvswitch_uri = get_resource_uri(self.basic_url, urn_transform_uri(vpc_urn))["resource_uri"]
        res = requests.put(url=dvswitch_uri, headers=self.cw_headers, json=kwargs, verify=False)
        if res.status_code == 200:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def get_vpc_detail(self, vpc_urn):
        """
        Get a specific vdswitch.
        :param vpc_urn: VDSwitch Uniform Resource Name(urn).
        :rtype: dict
        """
        dvswitch_uri = get_resource_uri(self.basic_url, urn_transform_uri(vpc_urn))["resource_uri"]
        res = requests.get(url=dvswitch_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code == 200:
            return res.json()
        else:
            return None

    def get_public_ip(self, **kwargs):
        """
        Get a public ip address from a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "FusionCompute不支持查看公网IP！"}

    def __port_group_format(self, port_group_obj):
        if port_group_obj:
            return Subnet(
                id=port_group_obj["urn"],
                name=port_group_obj["name"],
                vpc_id=port_group_obj["urn"].split(":portgroups:")[0],
                status="可用",
                platform_type=CloudType.FUSIONCOMPUTE.value,
                updated_time="",
                created_time="",
                tags=[],
                description=port_group_obj["description"],
                vm_host_id="",
                project_info={},
                region_info={},
                zone_info={},
                extra={"vlanId": port_group_obj.get("vlanId")},
            ).to_dict()
        else:
            return None

    def _port_groups_in_vswtich(self, dvswitch_urn):
        port_group_list = []
        port_group_uri = get_resource_uri(self.basic_url, urn_transform_uri(dvswitch_urn))["port_group_uri"]
        params = {"limit": 20, "offset": 0}
        while True:
            res = requests.get(url=port_group_uri, headers=self.cw_headers, params=params, verify=False)
            if res.status_code == 200:
                port_group_obj = res.json()
                port_group_number = port_group_obj["total"]
                total = port_group_number
                cur_port_group_list = [
                    self.__port_group_format(cur_port_group) for cur_port_group in port_group_obj["portGroups"]
                ]
                port_group_list.extend(cur_port_group_list)
                if port_group_number > (params["limit"] + params["offset"]):
                    params["offset"] += params["limit"]
                    continue
                else:
                    break
            else:
                port_group_list = []
                total = 0
                break
        return port_group_list, total

    def list_subnets(self, dvswitch_urn=None):
        """
        Get port group list from a specific dvswitch.
        :param dvswitch_urn: DVSwitch Uniform Resource Name(urn).
        # :param kwargs: accept multiple key value pair arguments.
        # ----------------------
        # * limit: Maximum number of items to return. If the value is -1, it will return all disks.(required)
        #          type: int
        #          default is -1
        # * offset: The initial index from which to return the results.(required)
        #           type: int
        #           default: 0
        # ----------------------
        :rtype: dict
        """
        port_group_list = []
        total_num = 0
        if dvswitch_urn:
            port_group_list, total_num = self._port_groups_in_vswtich(dvswitch_urn)
        else:
            vswitch_rs = self.get_vpcs()
            if vswitch_rs["result"]:
                for cur_vswitch in vswitch_rs["data"]:
                    cur_port_group_list, cur_total_num = self._port_groups_in_vswtich(cur_vswitch["id"])
                    port_group_list.extend(cur_port_group_list)
                    total_num += cur_total_num
        return {"result": True, "total": total_num, "data": port_group_list}

    def get_subnet_detail(self, subnet_urn):
        """
        Get a specific port group info.
        :param subnet_urn: PortGroup Uniform Resource Name(urn).
        :rtype: dict
        """
        port_group_uri = get_resource_uri(self.basic_url, urn_transform_uri(subnet_urn))["resource_uri"]
        res = requests.get(url=port_group_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def create_subnet(self, **kwargs):
        """
        Create a port group from a specific DVSwtich.
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * name: the name of port group.(required)
                type: string
        * subnetUrn: Subnet Uniform Resource Name(urn).(optonal)
                      type: string
        * portType: port type.(optonal)
                     type: integer
                     0: Access
                     1: Trunk
                     default: 0
        * vlanId: the ID of vlan.(If port type is access, this field is optional.)
                   type: boolean
                   range: 0 - 4094
                   default: 0
        * vxlanId: the ID of vxlan.(If port type is access, this field is optional.)
                    type: boolean
                    range: 4096 - 16777215
                    default: 0
        * vlanRange: the range of vlan.(If port type is trunk, this field is required)
                      type: string
        * description: the description of subnet.
                       type: string
                       default: ''
        * ......
        * ......
        -----------------
        :rtype: dict
        """
        vpc_urn = kwargs.pop("vpc_urn")
        port_group_uri = get_resource_uri(self.basic_url, urn_transform_uri(vpc_urn))["port_group_uri"]
        res = requests.post(url=port_group_uri, headers=self.cw_headers, json=kwargs, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()["urn"]}
        else:
            return {"result": False, "message": res.text}

    def delete_subnet(self, subnet_id, **kwargs):
        """
        Delete a port group.
        :param subnet_id: PortGroup Uniform Resource Name(urn).
        :rtype: dict
        """
        port_group_uri = get_resource_uri(self.basic_url, urn_transform_uri(subnet_id))["resource_uri"]
        res = requests.delete(url=port_group_uri, headers=self.cw_headers, json=None, verify=False)
        if res.status_code < 300:
            return {"result": True}
        else:
            return {"result": False, "message": res.text}

    def modify_subnet(self, port_group_urn, **kwargs):
        """
        Create a port group from a specific DVSwtich.
        :param port_group_urn: Port Group Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * name: the name of port group.(required)
                type: string
        * subnetUrn: Subnet Uniform Resource Name(urn).
                      type: string
        * portType: port type.(optonal)
                     type: integer
                     0: Access
                     1: Trunk
                     default: 0
        * vlanId: the ID of vlan.(If port type is access, this field is optional.)
                   type: boolean
                   range: 0 - 4094
                   default: 0
        * vxlanId: the ID of vxlan.(If port type is access, this field is optional.)
                    type: boolean
                    range: 4096 - 16777215
                    default: 0
        * vlanRange: the range of vlan.(If port type is trunk, this field is required)
                      type: string
        * description: the description of subnet.
                       type: string
                       default: ''
        * ......
        * ......
        """
        port_group_uri = get_resource_uri(self.basic_url, urn_transform_uri(port_group_urn))["port_group_uri"]
        res = requests.put(url=port_group_uri, headers=self.cw_headers, json=kwargs, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    # ------------------***** charge *****-------------------
    def get_virtual_cost(self, **kwargs):
        """
        Get current cost budget.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": True, "data": []}

    # ------------------***** monitor *****-------------------
    def get_monitor_data(self, **kwargs):
        """
        Get monitor data from a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        now_time = datetime.datetime.now() + datetime.timedelta(minutes=-5)
        hour_time = datetime.datetime.now() + datetime.timedelta(hours=-1)
        resource_id = kwargs.get("resourceId", "")
        resource_id_list = resource_id.split(",")

        metric_list = ("cpu_usage", "mem_usage", "disk_usage")
        interval = "300"
        time_difference = character_conversion_timestamp(
            kwargs.get("EndTime", now_time)
        ) - character_conversion_timestamp(kwargs.get("StartTime", hour_time))
        if time_difference > 86400:
            interval = "3600"
        if time_difference > 604800:
            interval = "86400"
        try:
            for vm_id in resource_id_list:
                res = {}
                for cur_site in self.__get_sites():
                    items = []
                    monitor_url = get_resource_uri(self.basic_url, urn_transform_uri(cur_site["id"]))[
                        "objectmetric_curvedata"
                    ]
                    args = []
                    for i in metric_list:
                        args.append(
                            {
                                "urn": vm_id,
                                "metricId": i,
                                "startTime": str(character_conversion_timestamp(kwargs.get("StartTime", hour_time))),
                                "endTime": str(character_conversion_timestamp(kwargs.get("EndTime", now_time))),
                                "interval": interval,
                            }
                        )
                    resp = requests.post(url=monitor_url, headers=self.cw_headers, json=args, verify=False)
                    if resp.status_code < 300:
                        items = resp.json()["items"]
                        break
                    else:
                        logger.error(resp)
                res = {resource_id: {}}
                cpu_data = []
                memory_data = []
                disk_data = []
                for i in items:
                    if i["metricId"] == "cpu_usage":
                        for metricValue in i["metricValue"]:
                            cpu_data.append([metricValue["time"], float("%.2f" % (float(metricValue["value"])))])
                    if i["metricId"] == "mem_usage":
                        for metricValue in i["metricValue"]:
                            memory_data.append([metricValue["time"], float("%.2f" % (float(metricValue["value"])))])
                    if i["metricId"] == "disk_usage":
                        for metricValue in i["metricValue"]:
                            disk_data.append([metricValue["time"], float("%.2f" % (float(metricValue["value"])))])
                res[resource_id].update({"cpu_data": cpu_data})
                res[resource_id].update({"memory_data": memory_data})
                res[resource_id].update({"disk_data": disk_data})
            res["result"] = True
            return res
        except Exception as e:
            logger.exception("get_monitor_data")
            return {"result": False, "message": str(e)}

    def get_load_monitor_data(self, **kwargs):
        return {"result": False, "message": "不支持"}

    # ------------***** private cloud compute *****------------

    def __get_site_host(self, site_urn, **kwargs):
        """
        Get host list from a specific site.
        * site_urn: Site Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * scope: search scope. If this field is not set,
                 it will return all host including hosts under cluster.
                 But if the value of this filed is default, it will
                 return hosts which are not under cluster.(optional)
                 type: string
        ---------------
        :rtype: tuple(host list, host number)
        """
        host_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["host_uri"]
        params = None
        if kwargs.get("scope"):
            params = {"scope": kwargs.get("scope")}
        res = requests.get(url=host_uri, headers=self.cw_headers, params=params, verify=False)
        if res.status_code < 300:
            host_obj = res.json()
            host_list = host_obj["hosts"]
            host_num = host_obj["total"]
        else:
            host_list = []
            host_num = 0
        return host_list, host_num

    def get_hosts(self, **kwargs):
        """
        Get host list.
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * site_urn: Site Uniform Resource Name(urn).(optional)
                    type: string
        * scope: search scope. If this field is not set,
                 it will return all host including hosts under cluster.
                 But if the value of this filed is default, it will
                 return hosts which are not under cluster.(optional)
                 type: string
        ---------------
        :rtype: dict
        """
        if kwargs.get("site_urn"):
            site_urn = kwargs.pop("site_urn")
            host_list, host_num = self.__get_site_host(site_urn, **kwargs)
            return {"result": True, "data": host_list, "total": host_num}
        else:
            host_total_list = []
            total_num = 0
            for cur_site in self.__get_sites():
                cur_host_list, cur_host_num = self.__get_site_host(cur_site["id"], **kwargs)
                total_num += cur_host_num
                host_total_list.extend(cur_host_list)
        return {"result": True, "data": host_total_list, "total": total_num}

    def get_host_detail(self, host_urn):
        """
        Get a specific host info.
        :param host_urn: Host Uniform Resource Name(urn).
        :rtype: dict
        """
        host_uri = get_resource_uri(self.basic_url, urn_transform_uri(host_urn))["resource_uri"]
        res = requests.get(url=host_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def __get_site_clusters(self, site_urn):
        """
        Get cluster list from a specific site.
        * site_urn: Site Uniform Resource Name(urn).
        :rtype: list
        """
        cluster_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["cluster_uri"]
        res = requests.get(url=cluster_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code < 300:
            return res.json()["clusters"]
        else:
            return []

    def get_clusters(self, **kwargs):
        """
        Get cluster list.
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * site_urn: Site Uniform Resource Name(urn).(optional)
                    type: string
        -----------------
        :rtype: dict
        """
        if kwargs.get("site_urn"):
            site_urn = kwargs.pop("site_urn")
            cluster_list = self.__get_site_clusters(site_urn)
            return {"result": True, "data": cluster_list}
        else:
            cluster_total_list = []
            for cur_site in self.__get_sites():
                cur_cluster_list = self.__get_site_clusters(cur_site["id"])
                cluster_total_list.extend(cur_cluster_list)
        return {"result": True, "data": cluster_total_list}

    def get_cluster_detail(self, cluster_urn):
        """
        Get a specific cluster.
        :param cluster_urn: Cluster Uniform Resource Name(urn).
        :rtype: dict
        """
        cluster_uri = get_resource_uri(self.basic_url, urn_transform_uri(cluster_urn))["resource_uri"]
        res = requests.get(url=cluster_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    # ------------***** private cloud storage *****-------------
    def __get_resource_storages(self, site_urn, **kwargs):
        """
        Get all data storages on a specific resource.
        :param site_urn: Site Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * limit: Maximum number of items to return. If the value is -1, it will return all storages.(optional)
                 range 1~100, -1
                 type: int
                 default: -1
        * offset: The initial index from which to return the results.(optional)
                  type: int
                  default: 0
        * scope: query scope.(optional)
                 type string
                 default storageUnitUrn
        --------------
        :return: tuple(storage list, total size)
        """
        flag = False
        if kwargs.get("limit") is None or int(kwargs.get("limit")) == -1:
            flag = True
            limit = 20
        else:
            limit = int(kwargs.get("limit"))
        storages_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["storage_uri"]
        params = {"limit": limit, "offset": int(kwargs.get("offset", 0))}
        if kwargs.get("scope"):
            params.update({"scope": kwargs.get("scope")})
        storage_list = []
        while True:
            site_storage_rs = requests.get(url=storages_uri, headers=self.cw_headers, params=params, verify=False)
            if site_storage_rs.status_code < 300:
                site_storage_dict = site_storage_rs.json()
                storage_number = site_storage_dict["total"]
                storage_list.extend(site_storage_dict["datastores"])
                total = storage_number
                if flag and storage_number > (params["limit"] + params["offset"]):
                    params["offset"] += params["limit"]
                    continue
                else:
                    break
            else:
                storage_list = []
                total = 0
                break
        return storage_list, total

    def __storage_format(self, storage_obj):
        if storage_obj:
            return PrivateStorage(
                resource_id=storage_obj["urn"],
                resource_name=storage_obj["name"],
                status="ERROR" if storage_obj["status"] == "ABNORMAL" else "AVAILABLE",
                cloud_type=CloudType.FUSIONCOMPUTE.value,
                capacity=storage_obj["actualCapacityGB"],
                used_capacity=storage_obj["actualCapacityGB"] - storage_obj["actualFreeSizeGB"],
                allocated_capacity=storage_obj["usedSizeGB"],
                host_id=storage_obj["hosts"],
                extra={},
            ).to_dict()
        else:
            return None

    def get_local_storage(self, **kwargs):
        """
        Get all data storage list.
        :param kwargs: accept multiple key value pair arguments.
        ------------------
        * site_urn: get all images under the specific site.
                    if this value is not set, it will return all images from all sites.(optional)
        ------------------
        :rtype: dict
        """
        storage_list = []
        total_num = 0
        if kwargs.get("site_urn"):
            storage_list, total_num = self.__get_resource_storages(kwargs.get("site_urn"))
        else:
            site_list = self.__get_sites()
            for cur_site in site_list:
                cur_site_storage_list, cur_total_size = self.__get_resource_storages(cur_site["resource_id"])
                storage_list.extend(cur_site_storage_list)
                total_num += cur_total_size
        return {
            "result": True,
            "data": [self.__storage_format(cur_storage) for cur_storage in storage_list],
            "total": total_num,
        }

    def get_local_storage_detail(self, region):
        """
        Get all data storage from a specific site.
        :param region: Site Uniform Resource Name(urn).(required)
        :rtype: dict
        """
        storage_list, total_num = self.__get_resource_storages(region)
        return {
            "result": True,
            "data": [self.__storage_format(cur_storage) for cur_storage in storage_list],
            "total": total_num,
        }

    def get_avail_storage_disks(self, site_urn, ds_urn):
        """
        Get all available disk from a specific datastore
        :param site_urn: Site Uniform Resource Name(urn).
        :param ds_urn: Data Store Uniform Resource Name(urn).
        :return: tuple(disk list, disk number)
        """
        disk_list_total, disk_num_total = self.__get_ds_disks(site_urn, ds_urn)
        return [
            {"id": disk_obj["urn"], "name": disk_obj["name"]}
            for disk_obj in disk_list_total
            if disk_obj["status"] == "USE" and not disk_obj.get("vmUrn")
        ]

    # ------------***** fusioncompute private *****-------------
    def destroy_vm_disk(self, vm_urn, **kwargs):
        """
        Delete a specific disk a specific vm.
        :param vm_urn: VM Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * disk_urn: Disk Uniform Resource Name(urn).(required)
                  type: string
        -----------------
        :rtype: dict
        """
        json_obj = {"volUrn": kwargs.get("disk_urn")}
        vm_disk_delete_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_urn))["vm_disk_delete_uri"]
        res = requests.post(url=vm_disk_delete_uri, headers=self.cw_headers, json=json_obj, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def extend_vm_disk(self, vm_urn, **kwargs):
        """
        extend a specific disk from a vm
        :param vm_urn: VM Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * disk_urn: Disk Uniform Resource Name(urn).(required)
                  type: string
        * size: the size of disk(GB).(required)
                type: long
        -----------------
        :rtype: dict
        """
        json_obj = {"volUrn": kwargs.get("disk_urn"), "size": int(kwargs.get("size")) * 1024}
        vm_disk_extend_uri = get_resource_uri(self.basic_url, urn_transform_uri(vm_urn))["vm_disk_expand_uri"]
        res = requests.post(url=vm_disk_extend_uri, headers=self.cw_headers, json=json_obj, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def get_host_statistics(self, site_urn, **kwargs):
        """
        Get host statistics from a specific site.
        :param site_urn: Site Uniform Resource Name(urn).
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * scope: search scope, if this field is not set, it will return all hosts from a site.(optional)
                 type: string
                 value: eg. a cluster urn
        -----------------
        :rtype: dict
        """
        params = None
        if kwargs.get("scope"):
            params = {"scope": kwargs.get("scope")}
        host_statistics_uri = get_resource_uri(self.basic_url, urn_transform_uri(site_urn))["host_statistics_uri"]
        res = requests.get(url=host_statistics_uri, headers=self.cw_headers, params=params, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def get_cluster_compute_resource(self, cluster_urn):
        """
        Get compute resource from a specific cluster.
        :param cluster_urn: Cluster Uniform Resource Name(urn).
        :rtype: dict
        """
        cluster_compute_resource_uri = get_resource_uri(self.basic_url, urn_transform_uri(cluster_urn))[
            "cluster_compute_resource_uri"
        ]
        res = requests.get(url=cluster_compute_resource_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def get_cluster_all_vm_compute_resource(self, cluster_urn):
        """
        Get compute resource from a specific cluster.
        :param cluster_urn: Cluster Uniform Resource Name(urn).
        :rtype: dict
        """
        cluster_all_vm_compute_resource_uri = get_resource_uri(self.basic_url, urn_transform_uri(cluster_urn))[
            "cluster_all_vm_compute_resource_uri"
        ]
        res = requests.get(url=cluster_all_vm_compute_resource_uri, headers=self.cw_headers, params=None, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()}
        else:
            return {"result": False, "message": res.text}

    def get_folder_list(self, site):
        """
        查询文件夹列表(包括子文件夹)
        :param site:
        :return:
        """
        site_uri = urn_transform_uri(site)
        folder_uri = "{}{}/folder".format(self.basic_url, site_uri)
        params = {"type": 1}
        resp = requests.get(url=folder_uri, headers=self.cw_headers, params=params, verify=False)
        if resp.status_code < 300:
            folders = resp.json()["folders"]
            folder_list = self.format_folder_list(folders, folder_uri, params)
            return {"result": True, "data": folder_list}
        else:
            logger.exception(eval(resp.content)["errorDes"])
            return {"result": False, "message": eval(resp.content)["errorDes"]}

    def format_folder_list(self, folders, folder_uri, params):
        """
        递归子文件夹
        :param folders:
        :param folder_uri:
        :param params:
        :return:
        """
        return_data = []
        for i in folders:
            params["parentObjUrn"] = i["urn"]
            resp = requests.get(url=folder_uri, headers=self.cw_headers, params=params, verify=False)
            if resp.status_code < 300:
                i = dict(i, **{"id": i["urn"]})
                i["children"] = self.format_folder_list(resp.json()["folders"], folder_uri, params)
                return_data.append(i)
        return return_data


class FusionComputeNew(PrivateCloudManage):
    """
    FusionCompute 8.0.3.
    """

    resource_map = {
        "vm": ("servers", "server"),
        "list_route_entry": ("routes", "route"),
        # "eip": ("publicips", "publicip"),
        # FusionCloud eip 返回数据用此字段取值
        "floatingips": ("floatingips", "floatingips"),
        "rule": ("l7policies", "l7policie"),
        "zone": ("available_zones", "available_zones"),
        "region": ("regions", "regions"),
    }

    product_id_map = {
        "ecs": "938ca08a18dd48e596bbd4f81d6a30b5",
        "evs": "b23630ce0989449e8db99dd1f54a7b74",
        "vpc": "45b1c7384c65451fb01c574e4ef4f259",
        "elb": "86264b9194514e3f83bdb4b1fb958260",
        "fcecs": "458eaaa73a5b44939905bc27b9af3b1b",
        "fcevs": "a1c8a6a61c814bd38a0d6f2d6269ae75",
        "fcvpc": "054ba2fa5c774ae6b86944259819dafa",
    }

    def __init__(self, auth_token, name, **kwargs):
        self.auth_token = auth_token
        self.name = name
        self.cw_headers = kwargs.get("cw_headers", "")
        self.basic_url = kwargs.get("basic_url", "")
        self.region = kwargs.get("region", "")
        self.project_id = kwargs.get("project_id", "")
        self.host = kwargs.get("host", "")
        self.pool_id = kwargs.get("domain_id", "")  # 资源池ID
        self.host = kwargs.get("host", "")
        self.account = kwargs.get("account", "")
        self.user_id = kwargs.get("user_id", "")

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @staticmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        """
        check if this object works.
        :return: A dict with a “key: value” pair of object. The key name is result, and the value is a boolean type.
        :rtype: dict
        """
        if self.auth_token:
            return {"result": True}
        else:
            return {"result": False}

    @staticmethod
    def _handle_result(res, action_name):
        """处理结果函数"""
        if CloudResourceType.BUCKET.value in action_name:
            return {"result": True, "data": ""}
        if res.status_code < 300:
            if not res.content:
                return {"result": True, "data": ""}
            return {"result": True, "data": res.json().get("id")}
        return {"result": False, "message": f"{action_name} failed"}

    def _handle_list_result(self, res, resource_name, action_name):
        resources, resource = self.resource_map[resource_name]
        if res.status_code < 300:
            data_dict = res.json()
            res_list = data_dict.get(resources, [])
            if res_list:
                vm_list = [getattr(self, f"{resource_name}_format")(cur) for cur in res_list]
                return {"result": True, "data": vm_list}
            return {"result": True, "data": [getattr(self, f"{resource_name}_format")(data_dict.get(resource))]}
        return {"result": False, "message": f"{action_name} failed {res.json()}"}

    @staticmethod
    def handle_order_result(order_id):
        return {"result": True, "order_id": order_id}

    def _handle_list_result_page(self, res, resource_name, action_name):
        resources, resource = self.resource_map[resource_name]
        res_list = res.get(resources, [])
        if res_list:
            vm_list = [getattr(self, f"{resource_name}_format")(cur) for cur in res_list]
            return {"result": True, "data": vm_list}
        return {"result": True, "data": []}

    def list_regions(self, *args, **kwargs):
        """查询区域列表"""
        url_par = f"https://sc.{self.host}/silvan/rest/v1.0/regions"
        res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
        return self._handle_list_result(res, "region", "list_regions")

    def list_zones(self, *args, **kwargs):
        """查询可用区域列表"""
        url_par = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcserviceaccess/available-zones"
            f"?cloud_infra_id={self.pool_id}"
        )
        res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
        return self._handle_list_result(res, "zone", "list_ones")

    def list_pools(self, *args, **kwargs):
        # 逻辑
        url_par = f"https://sc.{self.host}/rest/serviceaccess/v3.0/cloud-infras"
        res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
        # 返回
        data = []
        if res.status_code < 300:
            data = [{"resource_id": i["id"], "resource_name": i["name"]} for i in res.json().get("records")]
        return {"result": True, "data": data}

    def list_project(self, *args, **kwargs):
        """查询项目编号"""
        url_par = f"https://sc.{self.host}/v3/auth/projects"
        res = requests.get(url=url_par, headers=self.cw_headers)
        return self._handle_result(res, "list_project")

    def list_clusters(self, **kwargs):
        """查询集群"""
        url_par = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcserviceaccess/clusters?cloud_infra_id={self.pool_id}"
        )
        res = requests.get(url=url_par, headers=self.cw_headers)
        if res.status_code < 300:
            resource = res.json()
            return resource["clusters"]
        return {"result": False, "message": "查询集群失败"}

    def list_order_resource(self, order_id, resource_name):
        """查询订单中的资源列表(都是走的单个)"""
        par_url = f"https://sc.{self.host}/rest/order/v3.0/orders/{order_id}/resources"
        res = requests.get(url=par_url, headers=self.cw_headers, verify=False)
        if res.status_code < 300:
            resource = res.json()
            if resource:
                for item in resource:
                    if item.get("resource_name") == resource_name:
                        return {"result": True, "data": item}
            return {"result": True, "data": None}
        return {"result": False, "message": "订单查询失败"}

    # ------------------***** vm *****-----------------
    def __get_resource_pools(self):
        """
        虚拟机-获取资源池列表.
        :rtype: dict
        """
        get_resource_pools_url = get_resource_uri(f"https://sc.{self.host}")["get_resource_pools_url"]
        vm_res = requests.get(url=get_resource_pools_url, headers=self.cw_headers, verify=False)
        return self._handle_result(vm_res, "get_resource_pools")

    def list_vms(self, ids=None, **kwargs):
        """
        虚拟机-列表查询.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        cloud_infra_id: 云资源池 ID
        --------------
        :rtype: dict
        """
        if ids:
            kwargs["vm_id"] = ids[0]
            return self.get_vm_detail(**kwargs)
        else:
            start = 0
            limit = 50
            vm_res_dict = dict()
            vm_res_dict["servers"] = []
            tag = True
            while tag:
                vm_url = (
                    f"https://sc.{self.host}/rest/orchestration/v3.0/fcecs/servers?cloud_infra_id={self.pool_id}"
                    f"&limit={limit}&start={start}"
                )
                try:
                    vm_res = requests.get(url=vm_url, headers=self.cw_headers, verify=False)
                except Exception as e:
                    return fail(f"请求异常, {e}")
                if vm_res.status_code < 300:
                    data_dict = vm_res.json()
                    total_num = len(data_dict.get("servers"))
                    if total_num == 0:
                        return {"result": True, "data": []}
                    start += 50
                    if total_num < 50:
                        tag = False
                    vm_res_dict["servers"].extend(data_dict.get("servers"))
                else:
                    logger.exception("list_vms: {}".format(vm_res.json()))
                    return {"result": False, "message": f"list_vms failed {vm_res.json()}"}
            return self._handle_list_result_page(vm_res_dict, "vm", "list_vms")

    def get_vm_detail(self, **kwargs):
        """
        虚拟机-详情查询.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        id: 弹性云服务器资源 ID
        cloud_infra_id: 云资源池 ID
        --------------
        :rtype: dict
        """
        get_params = {"cloud_infra_id": self.pool_id}
        vm_action_url = "{}/{}".format(
            get_resource_uri(f"https://sc.{self.host}")["vm_server_url"], kwargs.get("vm_id")
        )
        vm_res = requests.get(url=vm_action_url, headers=self.cw_headers, params=get_params, verify=False)
        if vm_res.status_code < 300:
            if kwargs.get("flag"):
                return {"result": True, "data": [vm_res.json().get("server", {})]}
            return {"result": True, "data": [self.vm_format(vm_res.json().get("server", {}))]}
        return {"result": False, "message": "get_vm_detail failed"}

    def create_vm(self, **kwargs):
        """
        创建虚拟机(订单接口)
        :param kwargs: accept multiple key value pair arguments.
        --------------
        operate_type: 申请，固定值 apply.
        project_id: 项目ID
        region_id: 区域ID
        time_zone: 参考当地时区
        tenancy: 申请时长，单位为天，为“0”时，表示不限时长，必选
        service_type: 弹性云服务器，填写选择的service_type，必选，ecs
        tenantId: 项目ID，必选
        availability_zone: 可用分区id，步骤3拿到，必选
        name: ECS名称，自定义即可，必选
        imageRef: 镜像Id，步骤5拿到，必选
        flavorRef: 规格Id，步骤5拿到，必选
        root_volume:volumetype: ECS系统盘大小，自定义，必选
        vpcid: vpc的Id，步骤6拿到，必选。
        nics:subnet_id: 此处需填写子网Id，步骤7拿到，必选
        nics:"binding:profile":disable_security_groups: 是否关闭安全组，默认打开，必选。
        security_groups:id: 安全组Id，步骤8拿到，必选
        counts: 需要创建的弹性云服务器个数，自定义即可，最大支持一次性创建20台，必选
        extendparam:regionID: 区域id，步骤3拿到，必选
        metadata:op_svc_userid: 用户的Id，步骤1拿到，必选
        metadata:__instance_vwatchdog: 是否开启软件狗（软件狗为虚拟机提供一种心跳检测机制，主要用于监视虚拟机内部系统的健康状况），
        如需开启软件狗，请确保所选镜像已安装符合标准IPMI软件狗的喂狗程序，否则可能导致虚拟机反复重启。开启：true，关闭：false。必选。
        metadata:_ha_policy_type: 是否启用ECS HA（启用HA功能后，如果云服务器或者云服务器所在主机故障，系统会在其他主机上重建云服务器，
        保证业务连续性）。该能力受管理员配置的全局HA策略限制，只有在管理员配置了全局HA策略后，基于云主机的HA策略才会生效。
        开启：remote_rebuild，关闭：close。必选。
        power_on: 创建出来的虚拟机状态。true为开机状态，false为关机
        tags: 标签
        user_data: 用于ManageOne页面显示订购虚拟机的参数
        secret_params: 必选参数（键必须有，值可为空）
        --------------
        """
        vm_params = {
            "project_id": self.project_id,
            "region_id": self.region,
            "cloud_infra_id": self.pool_id,
            "cluster_id": kwargs.get("cluster_id"),
            "user_id": self.user_id,
            "name": kwargs.get("name"),
            "count": 1,
            "az_id": kwargs.get("az_id"),
            "type": "normal",
            "template_id": kwargs.get("template_id"),
            "vmSpec": {
                "nics": [{"network_id": kwargs.get("network_id"), "network_type": "INTERNAL"}],
                "template_vols": [
                    {
                        "size": kwargs.get("size", 100),
                        "datastore_id": kwargs.get("datastore_id"),
                        "config_type": "2",
                        "type": "normal",
                    }
                ],
                "cpu": {"count": kwargs.get("cpu_count")},
                "memory": {"count": kwargs.get("memory_count")},
            },
        }
        body = {
            "subscriptions": [
                {
                    "operate_type": "apply",
                    "project_id": self.project_id,
                    "product_id": self.product_id_map.get("fcecs"),
                    "region_id": self.region,
                    "cloud_infra_id": self.pool_id,
                    "tenancy": "0",
                    "service_type": "fcecs",
                    "params": json.dumps(vm_params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "创建虚拟机失败"}

    def destroy_vm(self, **kwargs):
        """虚拟机删除"""
        params = {
            "project_id": self.project_id,
            "region_id": self.region,
            "cloud_infra_id": self.pool_id,
            "user_id": self.user_id,
            "ids": [{"id": kwargs.get("vm_id"), "name": kwargs.get("name")}],
        }
        body = {
            "subscriptions": [
                {
                    "service_type": "fcecs",
                    "operate_type": "delete",
                    "project_id": self.project_id,
                    "region_id": self.region,
                    "cloud_infra_id": self.pool_id,
                    "params": json.dumps(params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "delete_vm fail"}

    def __vm_action(self, cloud_infra_id, vm_ids, action_type, action_mode=None):
        """
        虚拟机操作-开机、关机、重启.
        :param cloud_infra_id: 云资源池 ID.
        :param vm_ids: 弹性云服务器的 ID 列表.
        :param action_type: 操作类型，"start"为开机，"stop"为关机，"reboot"是重启.
        :param action_mode: 当作为开机与重启时，"safe"是安全、"force"为强制.
        :return: :class:`Response <Response>` object
        :rtype: requests.Response
        """
        json_params = {"cloud_infra_id": cloud_infra_id, "vmIds": [vm_ids], "type": action_type, "mode": action_mode}
        vm_action_url = get_resource_uri(f"https://sc.{self.host}")["vm_action_url"]
        res = requests.post(url=vm_action_url, headers=self.cw_headers, json=json_params, verify=False)
        return res

    def start_vm(self, vm_id, **kwargs):
        """
        虚拟机开机.
        :param vm_id: vm ID.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        vm_ids: 云服务器 ID列表
        --------------
        :rtype: dict
        """
        action_res = self.__vm_action(self.pool_id, vm_id, "start")
        return self._handle_result(action_res, "start_vm")

    def stop_vm(self, vm_id, **kwargs):
        """
        虚拟机关机.
        :param cloud_infra_id: 云资源池 ID.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        vm_ids: 云服务器 ID列表
        action_mode: type: string
                     safe | force
                     default is safe.
        --------------
        :rtype: dict
        """
        action_mode = kwargs.get("action_mode", "force")
        action_res = self.__vm_action(self.pool_id, vm_id, "stop", action_mode)
        return self._handle_result(action_res, "stop_vm")

    def restart_vm(self, vm_id, **kwargs):
        """
        虚拟机重启.
        :param cloud_infra_id: 云资源池 ID.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        vm_ids: 云服务器 ID列表
        action_mode: type: string
                     safe | force
                     default is safe.
        --------------
        :rtype: dict
        """
        action_mode = kwargs.get("action_mode", "safe")
        action_res = self.__vm_action(self.pool_id, vm_id, "reboot", action_mode)
        return self._handle_result(action_res, "restart_vm")

    def renew_vm(self, **kwargs):
        """虚拟机续费"""
        list_required_params = ["vm_id", "name", "tenancy"]
        check_required_params(list_required_params, kwargs)
        params = {
            "ids": [
                {
                    "id": kwargs.get("vm_id"),
                    "name": kwargs.get("name"),
                    "service_type": "ecs",
                    "tenancy": kwargs.get("tenancy"),
                }
            ]
        }
        body = {
            "subscriptions": [
                {
                    "operate_type": "delay",
                    "project_id": self.project_id,
                    "service_type": "ecs",
                    "params": json.dumps(params),
                    "secret_params": "",
                    "region_id": kwargs.get("region_id", self.region),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        return self._handle_result(res, "renew_vm")

    def modify_prepay_vm(self, **kwargs):
        """虚拟机升降配"""
        params = {
            "region_id": self.region,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "cloud_infra_id": self.pool_id,
            "ids": [
                {
                    "id": kwargs.get("vm_id"),
                    "name": kwargs.get("name"),
                }
            ],
            "modify_flavor_spec": {"cpu": {"count": kwargs.get("cpu")}, "memory": {"count": kwargs.get("memory")}},
        }
        body = {
            "subscriptions": [
                {
                    "service_type": "fcecs",
                    "operate_type": "modify",
                    "project_id": self.project_id,
                    "cloud_infra_id": self.pool_id,
                    "params": json.dumps(params),
                    "secret_params": "",
                    "region_id": self.region,
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "虚拟机升降配失败"}

    def reset_instances_password(self, **kwargs):
        """虚拟机重置密码"""
        server_id = kwargs.get("server_id")
        body = {"reset-password": {"new_password": kwargs.get("new_password")}}
        url_par = f"{self.basic_url}/v1/{self.project_id}/cloudservers/{server_id}/os-reset-password"
        res = requests.put(url=url_par, headers=self.cw_headers, json=body, verify=False)
        return self._handle_result(res, "reset_instances_password")

    # ------------------***** 镜像 *****-------------------
    def create_image(self, **kwargs):
        """
        虚拟机-创建自定义镜像.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        template_id: 镜像 ID
        is_template: type: boolean
                     true | false
                     为 true 指弹性云服务器转为镜像
                     为 false 指镜像转为弹性云服务器
        --------------
        :rtype: dict
        """
        json_params = {
            "cloud_infra_id": self.pool_id,
            "template_id": kwargs.get("template_id"),
            "is_template": kwargs.get("is_template"),
        }
        image_url = get_resource_uri(f"https://sc.{self.host}")["image_action_url"]
        creat_res = requests.post(url=image_url, headers=self.cw_headers, json=json_params, verify=False)
        return self._handle_result(creat_res, "create_image")

    def image_create_object(self, **kwargs):
        """
        镜像创建实例.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        template_id: 镜像 ID
        is_template: type: boolean
                     true | false
                     为 true 指弹性云服务器转为镜像
                     为 false 指镜像转为弹性云服务器
        --------------
        :rtype: dict
        """
        json_params = {"cloud_infra_id": self.pool_id, "template_id": kwargs.get("template_id"), "is_template": False}
        image_url = get_resource_uri(self.basic_url)["image_action_url"]
        creat_res = requests.post(url=image_url, headers=self.cw_headers, json=json_params, verify=False)
        return self._handle_result(creat_res, "image_create_object")

    def list_images(self, ids=None, **kwargs):
        """
        镜像-获取镜像列表.
        :param ids: image ID.
        :rtype: dict
        """
        image_url = f"https://sc.{self.host}/rest/orchestration/v3.0/fcecs/templates?cloud_infra_id={self.pool_id}"
        image_res_list = []
        if ids:
            image_url = f"{image_url}&id={ids[0]}"
            get_res = requests.get(url=image_url, headers=self.cw_headers, verify=False)
            if get_res.status_code < 300:
                data_dict = get_res.json()
                image_res_list = data_dict.get("templates", [])
            else:
                return {"result": False, "message": f"list_images failed {get_res.json()}"}
        else:
            tag = True
            while tag:
                start = 0
                limit = 50
                image_url_new = f"{image_url}&limit={limit}&start={start}"
                try:
                    get_res = requests.get(url=image_url_new, headers=self.cw_headers, verify=False)
                except Exception as e:
                    logger.exception(e)
                    return fail(f"请求异常: {str(e)}")
                if get_res.status_code < 300:
                    data_dict = get_res.json()
                    total_num = len(data_dict.get("templates"))
                    start += 50
                    if total_num < 50:
                        tag = False
                    image_res_list.extend(data_dict.get("templates", []))
                else:
                    logger.exception("list_images: {}".format(get_res.json()))
                    return {"result": False, "message": f"list_images failed {get_res.json()}"}
        image_list = [self.image_format(cur_image) for cur_image in image_res_list]
        return {"result": True, "data": image_list}

    def image_create_instance(self, **kwargs):
        """自定义镜像创建实例"""
        kwargs["is_template"] = kwargs.get("is_template", False)
        list_required_params = ["template_id", "cloud_infra_id", "is_template"]
        check_required_params(list_required_params, kwargs)
        url_par = f"https://sc.{self.host}/rest/orchestration/v3.0/fcecs/templates/action"
        request_headers = self.cw_headers.copy()
        request_headers.update({"region": self.region})
        body = {}
        set_par = ["template_id", "cloud_infra_id", "is_template"]
        set_optional_params(set_par, kwargs, body)
        res = requests.post(url=url_par, headers=request_headers, json=body, verify=False)
        return self._handle_result(res, "image_create_instance")

    @staticmethod
    def image_related_object(self):
        """镜像相关实例查询"""
        return {"result": False, "message": "FusionCompute无镜像相关实例查询功能！"}

    def delete_image(self, **kwargs):
        """
        镜像-删除镜像.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        template_id: 镜像 ID
        cloud_infra_id: 云资源池 ID
        --------------
        :rtype: dict
        """
        template_id = kwargs.get("template_id")
        cloud_infra_id = self.pool_id
        delete_url = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcecs/templates/"
            f"{template_id}?cloud_infra_id={cloud_infra_id}"
        )
        get_res = requests.delete(url=delete_url, headers=self.cw_headers, verify=False)
        return self._handle_result(get_res, "delete_image")

    # ------------------***** 快照 *****-------------------
    def create_snapshot(self, **kwargs):
        """虚拟机创建快照"""
        params = {
            "action": "create_snapshot",
            "region_id": self.region,
            "project_id": self.project_id,
            "cloud_infra_id": self.pool_id,
            "user_id": self.user_id,
            "ids": [
                {
                    "id": kwargs.get("vm_id"),
                    "name": kwargs.get("name"),
                    "force": False,
                }
            ],
        }
        body = {
            "subscriptions": [
                {
                    "service_type": kwargs.get("service_type", "fcecs"),
                    "operate_type": "snapshot",
                    "project_id": self.project_id,
                    "product_id": self.product_id_map.get("fcecs"),
                    "region_id": self.region,
                    "cloud_infra_id": self.pool_id,
                    "secret_params": "",
                    "params": json.dumps(params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "创建虚拟机创建快照"}

    def list_snapshots(self, server_ids=None, ids=None, **kwargs):
        """
        查询快照列表.
        :param ids:
        :param kwargs:
        :return:
        """
        if ids:
            kwargs["snapshot_id"] = ids[0]
            return self.get_snapshot_detail(**kwargs)
        snapshot_list_all = []
        for server_id in server_ids:
            image_url = (
                f"https://sc.{self.host}/rest/orchestration/v3.0/fcecs/servers/{server_id}"
                f"/snapshots?cloud_infra_id={self.pool_id}"
            )
            get_res = requests.get(url=image_url, headers=self.cw_headers, verify=False)
            if get_res.status_code < 300:
                data_dict = get_res.json()
                snapshot_res = data_dict.get("snapshots", [])
                snapshot_res_list = self.get_all_snapshot(snapshot_res[0]) if snapshot_res else []
                snapshot_list = [
                    self.snapshot_format(snapshot_res_dict, server_id) for snapshot_res_dict in snapshot_res_list
                ]
                snapshot_list_all.extend(snapshot_list)
        return {"result": True, "data": snapshot_list_all}

    @staticmethod
    def get_all_snapshot(snapshots):
        snapshot_list = []

        def inner_callback(snapshots):
            snapshot_list.append(snapshots)
            child_snapshot = snapshots.get("childSnapshots")
            if child_snapshot:
                return inner_callback(child_snapshot[0])

        inner_callback(snapshots)
        return snapshot_list

    def get_snapshot_detail(self, **kwargs):
        """
        查询快照详情.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        cloud_infra_id: 云资源池 ID.
        server_id: 弹性云服务器 ID.
        snapshot_id: 弹性云服务器快照 ID.
        --------------
        :rtype: dict
        """
        cloud_infra_id = self.pool_id
        server_id = kwargs.get("server_ids")[0]
        snapshot_id = kwargs.get("snapshot_id")
        image_url = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcecs/servers/{server_id}"
            f"/snapshots/{snapshot_id}?cloud_infra_id={cloud_infra_id}"
        )
        get_res = requests.get(url=image_url, headers=self.cw_headers, verify=False)
        if get_res.status_code < 300:
            data_dict = get_res.json()
            snapshot_res = data_dict.get("current", {})
            return {"result": True, "data": [self.snapshot_format(snapshot_res, server_id)]}
        return {"result": False, "message": "查询快照详情失败"}

    def snapshot_rollback_to_ecs(self, **kwargs):
        """
        通过快照恢复弹性云服务器.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        server_id: 弹性云服务器 ID.
        snapshot_id: 弹性云服务器快照 ID.
        cloud_infra_id: 云资源池 ID.
        region: 区域.
        --------------
        :rtype: dict
        """

        image_url = "{}/{}/snapshots/{}?cloud_infra_id={}".format(
            get_resource_uri(self.basic_url)["vm_server_url"],
            kwargs.get("server_id"),
            kwargs.get("snapshot_id"),
            kwargs.get("cloud_infra_id"),
        )
        request_headers = self.cw_headers.copy()
        request_headers.update({"region": self.region})
        creat_res = requests.post(url=image_url, headers=request_headers, verify=False)
        return self._handle_result(creat_res, "snapshot_rollback_to_ecs")

    def delete_snapshot(self, snapshot_id, *args, **kwargs):
        """删除虚拟机快照"""
        params = {
            "region_id": self.region,
            "action": "delete_snapshot",
            "project_id": self.project_id,
            "cloud_infra_id": self.pool_id,
            "user_id": self.user_id,
            "ids": [{"id": kwargs.get("vm_id"), "service_type": "fcecs", "snapshot_id": snapshot_id}],
        }
        body = {
            "subscriptions": [
                {
                    "service_type": "fcecs",
                    "operate_type": "snapshot",
                    "project_id": self.project_id,
                    "params": json.dumps(params),
                    "cloud_infra_id": self.pool_id,
                    "region_id": self.region,
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "delete snapshot fail"}

    @staticmethod
    def apply_auto_snapshot_policy(self):
        """设置自动快照策略"""
        return {"result": False, "message": "FusionCompute无设置自动快照策略功能！"}

    @staticmethod
    def cancel_auto_snapshot_policy(self):
        """取消自动快照策略"""
        return {"result": False, "message": "FusionCompute无取消自动快照策略功能！"}

    # ------------------***** 块存储 *****-----------------
    def create_disk(self, **kwargs):
        """创建块存储"""
        disk_params = {
            "project_id": self.project_id,
            "region_id": self.region,
            "cloud_infra_id": self.pool_id,
            "user_id": self.user_id,
            "name": kwargs.get("name"),
            "count": 1,
            "az_id": kwargs.get("az_id"),
            "size": kwargs.get("size"),
            "type": kwargs.get("type"),
            "config_Type": "2",
            "datastoreUrn": kwargs.get("datastoreUrn"),
            "indep_disk": True,
            "server": kwargs.get("server", []),
        }
        body = {
            "subscriptions": [
                {
                    "project_id": self.project_id,
                    "region_id": self.region,
                    "cloud_infra_id": self.pool_id,
                    "product_id": self.product_id_map.get("fcevs"),
                    "tenancy": "0",
                    "operate_type": "apply",
                    "service_type": "fcevs",
                    "params": json.dumps(disk_params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "创建磁盘失败"}

    def list_disks(self, ids=None, **kwargs):
        """
        查询云硬盘详情列表.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        cloud_infra_id: 云资源池 ID.
        region: 区域.
        --------------
        :rtype: dict
        """
        if ids:
            kwargs["volume_id"] = ids[0]
            return self.get_disk_detail(**kwargs)
        disk_url = f"https://sc.{self.host}/rest/orchestration/v3.0/fcevs/volumes"
        start = 0
        limit = 50
        tag = True
        disk_res_list = []
        while tag:
            body = {
                "cloud_infra_id": self.pool_id,
                "start": start,
                "limit": limit,
            }
            try:
                post_res = requests.post(url=disk_url, headers=self.cw_headers, json=body, verify=False)
            except Exception as e:
                logger.exception(e)
                return fail(f"请求异常: {str(e)}")
            if post_res.status_code < 300:
                data_dict = post_res.json()
                total_num = len(data_dict.get("volumes", []))
                if total_num < 50:
                    tag = False
                start += 50
                disk_res_list.extend(data_dict.get("volumes", []))
        disk_list = [self.disk_format(disk_obj) for disk_obj in disk_res_list]
        return {"result": True, "data": disk_list}

    def get_disk_detail(self, **kwargs):
        """
        查询单个云硬盘详情.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        volume_id: 云硬盘数据库 ID.
        --------------
        :rtype: dict
        """
        get_url = "{}/{}?cloud_infra_id={}".format(
            get_resource_uri(f"https://sc.{self.host}")["block_storages_url"], kwargs.get("volume_id"), self.pool_id
        )
        get_res = requests.get(url=get_url, headers=self.cw_headers, verify=False)
        data_dict = get_res.json()
        return {"result": True, "data": [self.disk_format(data_dict)]}

    def disk_action(self, **kwargs):
        """
        挂载/卸载云硬盘.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        cloud_infra_id: 云资源池 ID.
        volume_id: 云硬盘 ID.
        action: 操作类型.
                type: string
                attach | detach
                挂载 | 卸载
        vm_id: 云主机ID.
        --------------
        :rtype: dict
        """
        post_params = {"cloud_infra_id": self.pool_id, "action": kwargs.get("action"), "vm_id": [kwargs.get("vm_id")]}
        post_url = "{}/{}/action".format(
            get_resource_uri(f"https://sc.{self.host}")["block_storages_url"],
            kwargs.get("volume_id"),
        )
        try:
            post_res = requests.post(url=post_url, headers=self.cw_headers, json=post_params, verify=False)
            if post_res.status_code < 300:
                return {"result": True, "data": post_res.json()}
        except Exception:
            return {"result": False, "message": "挂载云硬盘失败！" if kwargs.get("action") == "attach " else "卸载云硬盘失败！"}

    def delete_disk(self, disk_id, **kwargs):
        """云硬盘删除"""
        disk_params = {
            "ids": [{"id": disk_id, "name": kwargs.get("name")}],
            "project_id": self.project_id,
            "region_id": self.region,
            "cloud_infra_id": self.pool_id,
            "user_id": self.user_id,
        }
        body = {
            "subscriptions": [
                {
                    "operate_type": "delete",
                    "project_id": self.project_id,
                    "region_id": self.region,
                    "service_type": "fcevs",
                    "cloud_infra_id": self.pool_id,
                    "params": json.dumps(disk_params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "delete_disk fail"}

    # ------------------***** 安全组 *****-----------------
    def list_security_groups(self, ids=None, **kwargs):
        """
        查询安全组列表.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        cloud_infra_id: 云资源池 ID.
        --------------
        :rtype: dict
        """
        url_par = f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/security-groups"
        if ids:
            return self.get_security_group_detail(ids[0])
        url_par = f"{url_par}?cloud_infra_id={self.pool_id}"
        start = 0
        limit = 50
        tag = True
        security_group_list = []
        while tag:
            url_par_new = f"{url_par}&limit={limit}&start={start}"
            get_res = requests.get(url=url_par_new, headers=self.cw_headers, verify=False)
            if get_res.status_code < 300:
                data_dict = get_res.json()
                security_group_res_list = data_dict.get("securityGroups", [])
                total_num = len(security_group_res_list)
                start += 50
                if total_num < 50:
                    tag = False
                security_group_list.extend([self.security_group_format(sg_obj) for sg_obj in security_group_res_list])
            else:
                return {"result": False, "message": "list_security_groups fail"}
        return {"result": True, "data": security_group_list}

    def get_security_group_detail(self, security_group_id):
        """
        查询安全组详情.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        security_group_id: 安全组ID.
        cloud_infra_id: 云资源池 ID.
        --------------
        :rtype: dict
        """
        url_par = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/security-groups/{security_group_id}"
            f"?cloud_infra_id={self.pool_id}"
        )
        get_res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
        if get_res.status_code < 300:
            return {"result": True, "data": [self.security_group_format(get_res.json().get("security_group", {}))]}
        return {"result": False, "message": "get_security_group_detail failed"}

    def create_security_group(self, **kwargs):
        """
        创建安全组.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        cloud_infra_id: 云资源池 ID.
        sgName: 安全组名称。长度范围是1~256个字符.
        region：地域
        --------------
        :rtype: dict
        """
        url_par = f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/security-groups"
        post_params = {
            "cloud_infra_id": self.pool_id,
            "sgName": kwargs.get("name"),
            "sgDescription": kwargs.get("description"),
        }
        get_res = requests.post(url=url_par, headers=self.cw_headers, json=post_params, verify=False)
        if get_res.status_code < 300:
            return {"result": True, "data": get_res.json().get("sgId")}
        return {"result": False, "message": "create_security_group failed"}

    def get_interface(self, server_id, **kwargs):
        """查询云服务器网卡"""
        get_res = requests.get(
            url="{}/v2/{}/servers/{}/os-interface".format(self.basic_url, self.project_id, server_id),
            headers=self.cw_headers,
            verify=False,
        )
        return self._handle_result(get_res, "get_security_group_detail")

    def _get_nic_id(self, server_id):
        """获取虚拟机网卡ID"""
        get_params = {"cloud_infra_id": self.pool_id}
        vm_action_url = "{}/{}".format(get_resource_uri(f"https://sc.{self.host}")["vm_server_url"], server_id)
        vm_res = requests.get(url=vm_action_url, headers=self.cw_headers, params=get_params, verify=False)
        return vm_res.json()

    def instance_security_group_action(self, **kwargs):
        """虚拟机添加/移除安全组"""
        post_params = {
            "cloudInfraId": self.pool_id,
        }
        if kwargs.get("enableSecurityGroup"):
            post_params.update(
                {
                    "securityGroupId": kwargs.get("securityGroupId"),
                    "enableSecurityGroup": kwargs.get("enableSecurityGroup"),
                }
            )
        else:
            post_params.update({"enableSecurityGroup": kwargs.get("enableSecurityGroup")})
        server_id = kwargs.get("server_id")
        # 获取虚拟机详情，拿到网卡 ID
        nic_id = kwargs.get("nic_id")
        action_url = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcecs/servers/" f"{server_id}/nics/{nic_id}/securitygroup"
        )
        try:
            get_res = requests.put(url=action_url, headers=self.cw_headers, json=post_params, verify=False)
            if get_res.status_code < 300:
                return {"result": True}
        except Exception:
            return {"result": False, "message": "relation_instance failed"}

    def delete_security_group(self, **kwargs):
        """
        删除安全组.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        security_group_id: 安全组ID.
        region：地域
        --------------
        :rtype: dict
        """
        security_group_id = kwargs.get("security_group_id")
        url_par = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/security-groups/{security_group_id}?"
            f"cloud_infra_id={self.pool_id}"
        )
        get_res = requests.delete(url=url_par, headers=self.cw_headers, verify=False)
        if get_res.status_code < 300:
            return {"result": True}

    @staticmethod
    def add_relation(self):
        """新增关联"""
        return {"result": False, "message": "FusionCompute无新增关联功能！"}

    @staticmethod
    def remove_security_group(self):
        """移出安全组"""
        return {"result": False, "message": "FusionCompute无移出安全组功能！"}

    # ------------------***** 安全组规则列表 *****-----------------
    def list_security_group_rules(self, security_group_id, **kwargs):
        """
        查询安全组规则列表， direction 1 表示出站，0 表示入站.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        ids: 安全组规则 ID.
        --------------
        :rtype: dict
        """
        cloud_infra_id = self.pool_id
        url_par = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/securitygroups/"
            f"{security_group_id}/security-group-rules"
        )
        url_par = f"{url_par}?cloud_infra_id={cloud_infra_id}"
        start = 0
        limit = 50
        tag = True
        sgr_res_list = []
        while tag:
            url_par_new = f"{url_par}&limit={limit}&start={start}"
            get_res = requests.get(url=url_par_new, headers=self.cw_headers, verify=False)
            if get_res.status_code < 300:
                data_dict = get_res.json()
                total_num = len(data_dict.get("security_group_rules", []))
                start += 50
                if total_num < 50:
                    tag = False
                sgr_res_list.extend(data_dict.get("security_group_rules", []))
            else:
                logger.exception("list_vms: {}".format(get_res.json()))
                return {"result": False, "message": f"list_vms failed {get_res.json()}"}
        return {"result": True, "data": [self.sgr_format(sgr_obj) for sgr_obj in sgr_res_list]}

    def create_security_group_rule(self, **kwargs):
        """创建安全组规则"""
        security_group_id = kwargs.get("security_group_id")
        url_par = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/securitygroups/"
            f"{security_group_id}/security-group-rules"
        )
        # list_required_params = \
        #     ["security_group_id", "ip_protocol", "ip_ranges", "from_port", "to_port", "direction"]
        # check_required_params(list_required_params, kwargs)
        params = {"cloud_infra_id": self.pool_id, "security_group_rule": kwargs.get("security_group_rule", [])}
        # list_params = ["ip_protocol", "ip_ranges", "allowed_sg_id", "from_port", "to_port", "direction"]
        # set_optional_params(list_params, kwargs, params["security_group_rule"])
        res = requests.post(url=url_par, headers=self.cw_headers, json=params, verify=False)
        return self._handle_result(res, "create_security_group_rule")

    def delete_security_group_rule(self, rule_ids, **kwargs):
        """删除安全组规则"""
        security_group_id = kwargs.get("security_group_ids")
        url_par = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/securitygroups/{security_group_id}"
            f"/security-group-rules/delete"
        )
        body = {"cloud_infra_id": self.pool_id, "rule_ids": rule_ids}
        res = requests.post(url=url_par, headers=self.cw_headers, json=body, verify=False)
        return self._handle_result(res, "delete_security_group_rule")

    # ------------------***** VPC *****-------------------
    def list_vpcs(self, ids=None, **kwargs):
        """查询VPC列表"""
        vpc_url = f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/vpcs"
        if ids:
            kwargs["vpc_id"] = ids[0]
            return self.get_vpc_detail(**kwargs)
        url_par = "{}?cloud_infra_id={}".format(vpc_url, self.pool_id)
        vpc_res_list = []
        start = 0
        limit = 50
        tag = True
        while tag:
            url_par_new = f"{url_par}&limit={limit}&start={start}"
            try:
                get_res = requests.get(url=url_par_new, headers=self.cw_headers, verify=False)
            except Exception as e:
                logger.exception(e)
                return fail(f"请求异常: {str(e)}")
            if get_res.status_code < 300:
                data_dict = get_res.json()
                total_num = len(data_dict.get("vpcs", []))
                start += 50
                if total_num < 50:
                    tag = False
                vpc_res_list.extend(data_dict.get("vpcs", []))
            else:
                return {"result": False, "message": get_res.json()}
        vpc_list = [self.vpc_format(cur_vpc) for cur_vpc in vpc_res_list]
        return {"result": True, "data": vpc_list}

    def get_vpc_detail(self, **kwargs):
        """查询VPC详情"""
        list_required_params = ["vpc_id"]
        check_required_params(list_required_params, kwargs)
        vpc_url = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/vpcs/{kwargs['vpc_id']}"
            f"?cloud_infra_id={self.pool_id}"
        )
        res = requests.get(url=vpc_url, headers=self.cw_headers, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": [self.vpc_format(res.json())]}
        else:
            return {"result": False, "message": res.json()}

    def create_vpc(self, **kwargs):
        vpc_params = {
            # 屏蔽子网相关逻辑
            # "networks": [
            #     {
            #         "vlan": kwargs.get("vlan"),
            #         "name": kwargs.get("network_name"),
            #         "dvs_urn": kwargs.get("dvs_urn"),
            #     }
            # ],
            "project_id": self.project_id,
            "region_id": self.region,
            "cloud_infra_id": self.pool_id,
            "user_id": self.user_id,
            "name": kwargs.get("name"),
            "count": 1,
        }
        body = {
            "subscriptions": [
                {
                    "project_id": self.project_id,
                    "region_id": self.region,
                    "cloud_infra_id": self.pool_id,
                    "product_id": self.product_id_map.get("fcvpc"),
                    "tenancy": "0",
                    "operate_type": "apply",
                    "service_type": "fcvpc",
                    "params": json.dumps(vpc_params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "创建VPC失败"}

    def delete_vpc(self, vpc_id, *args, **kwargs):
        vpc_params = {
            "ids": [{"id": vpc_id, "name": kwargs.get("name")}],
            "project_id": self.project_id,
            "region_id": self.region,
            "cloud_infra_id": self.pool_id,
            "user_id": self.user_id,
        }
        body = {
            "subscriptions": [
                {
                    "operate_type": "delete",
                    "project_id": self.project_id,
                    "region_id": self.region,
                    "cloud_infra_id": self.pool_id,
                    "service_type": "fcvpc",
                    "params": json.dumps(vpc_params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "删除VPC失败"}

    # ------------------***** subnet *****-------------------
    def list_subnets(self, vpc_id, ids=None, **kwargs):
        """查询子网列表"""
        if ids:
            kwargs["subnet_id"] = ids[0]
            return self.get_subnet_detail(**kwargs)
        url = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/networks"
            f"?cloud_infra_id={self.pool_id}&vpc_id={vpc_id}"
        )
        start = 0
        limit = 50
        tag = True
        subnet_res_list = []
        while tag:
            new_url = f"{url}&limit={limit}&start={start}"
            try:
                res = requests.get(new_url, headers=self.cw_headers, verify=False)
            except Exception as e:
                logger.exception(e)
                return fail(f"请求异常: {str(e)}")
            if res.status_code < 300:
                data_dict = res.json()
                total_num = len(data_dict.get("networks", []))
                start += 50
                if total_num < 50:
                    tag = False
                subnet_res_list.extend(data_dict.get("networks", []))
        vm_list = [self.subnet_format(cur_subnet) for cur_subnet in subnet_res_list]
        return {"result": True, "data": vm_list}

    def get_subnet_detail(self, **kwargs):
        """查询子网详情"""
        list_required_params = ["vpc_id", "subnet_id"]
        check_required_params(list_required_params, kwargs)
        url = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/networks/{kwargs['subnet_id']}"
            f"?cloud_infra_id={self.pool_id}&vpc_id={kwargs['vpc_id']}"
        )
        res = requests.get(url=url, headers=self.cw_headers, params=kwargs, verify=False)
        return {"result": True, "data": [self.subnet_format(res.json())]}

    def create_subnet(self, **kwargs):
        """创建子网"""
        list_required_params = ["vpc_id", "name", "vlan", "dvs_urn"]
        check_required_params(list_required_params, kwargs)
        kwargs.update({"cloud_infra_id": self.pool_id})
        request_headers = self.cw_headers.copy()
        request_headers.update({"region": self.region})
        res = requests.post(
            url=get_resource_uri(f"https://sc.{self.host}")["dvswitch_url"],
            headers=request_headers,
            json=kwargs,
            verify=False,
        )
        return self._handle_result(res, "create_subnet")

    def delete_subnet(self, subnet_id, **kwargs):
        """删除子网"""
        list_required_params = ["vpc_id"]
        check_required_params(list_required_params, kwargs)
        request_headers = self.cw_headers.copy()
        request_headers["region"] = self.region
        try:
            res = requests.delete(
                url="{}/{}?cloud_infra_id={}&vpc_id={}".format(
                    get_resource_uri(f"https://sc.{self.host}")["dvswitch_url"],
                    subnet_id,
                    self.pool_id,
                    kwargs.get("vpc_id"),
                ),
                headers=request_headers,
                verify=False,
            )
            return {"result": res.status_code == 200, "message": res.json()}
        except Exception as e:
            logger.exception("delete subnets: {}".format(subnet_id))
            return {"result": False, "message": str(e)}

    # ------------------***** route_table/ route_entry *****-------------------
    def list_route_tables(self, route_table_name=None, **kwargs):
        """查询路由表"""
        cur_page = kwargs.pop("cur_page", 1)
        page_size = kwargs.pop("page_size", 10)
        if route_table_name:
            res = requests.post(
                url="{}/{}/{}".format(get_resource_uri(self.basic_url)["route_table_url"], cur_page, page_size),
                headers=self.cw_headers,
                json={"name": route_table_name},
                verify=False,
            )
        else:
            res = requests.get(
                url=f"https://sc.{self.host}/silvan/rest/v1.0/routes", headers=self.cw_headers, verify=False
            )
        if res.status_code < 300:
            data_dict = res.json()
            route_table_list = data_dict.get("data", [])
            if route_table_list:
                route_table_list = [self.route_table_format(cur_route_table) for cur_route_table in route_table_list]
                return {"result": True, "data": route_table_list}
            else:
                return {"result": True, "data": [self.route_table_format(data_dict.get("result"))]}
        else:
            return {"result": False, "message": "查询路由表失败"}

    def list_route_entry(self, ids, **kwargs):
        """查询路由策略"""
        if ids:
            url_par = "{}/{}".format(get_resource_uri(self.basic_url)["route_entry_url"], ids[0])
        else:
            url_par = get_resource_uri(self.basic_url)["route_entry_url"]
        res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
        return self._handle_list_result(res, "route_entry", "list_route_entry")

    def create_route_entry(self, **kwargs):
        """新建路由策略"""
        list_required_params = ["destination", "nexthop", "type", "vpc_id"]
        check_required_params(list_required_params, kwargs)
        url_par = get_resource_uri(self.basic_url)["route_entry_url"]
        res = requests.post(url=url_par, headers=self.cw_headers, json=kwargs, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()["router"]}
        return {"result": False, "message": "create_route_entry failed"}

    def delete_route_entry(self, route_id, **kwargs):
        """删除路由策略"""
        url_par = "{}/{}".format(get_resource_uri(self.basic_url)["route_entry_url"], route_id)
        res = requests.delete(url=url_par, headers=self.cw_headers, verify=False)
        return self._handle_result(res, "delete_route_entry")

    # ------------------***** 弹性公网IP *****-------------
    def list_eips(self, ids=None, **kwargs):
        """查询弹性公网"""
        url_par = f"https://vpc.hnxc-region-1.{self.host}/v2.0/floatingips"
        if ids:
            url_par = f"{url_par}/{ids[0]}"
        res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
        return self._handle_list_result(res, "floatingips", "list_eips")

    def create_eip(self, **kwargs):
        """创建弹性公网, 订单接口"""
        list_required_params = ["product_id", "tenancy", "publicip", "bandwidth", "count", "display"]
        check_required_params(list_required_params, kwargs)
        params = {
            "regionId": self.region,
            "publicip": kwargs.get("publicip"),
            "tenant_id": self.project_id,
            "bandwidth": kwargs.get("bandwidth"),
            "count": kwargs.get("count"),
            "display": kwargs.get("display"),
        }
        body = {
            "subscriptions": [
                {
                    "operate_type": "apply",
                    "project_id": self.project_id,
                    "product_id": kwargs.get("product_id"),
                    "region_id": self.region,
                    "tenancy": int(kwargs.get("tenancy")),
                    "service_type": "eip",
                    "params": json.dumps(params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(self.basic_url)["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "创建弹性公网失败"}

    def release_eip(self, eip_id, **kwargs):
        """释放弹性公网, 订单接口"""
        list_required_params = ["display"]
        check_required_params(list_required_params, kwargs)
        params = {
            "regionId": self.region,
            "publicIpId": eip_id,
            "tenant_id": self.project_id,
            "ids": {"id": eip_id, "service_type": "eip"},
            "display": kwargs.get("display"),
        }
        body = {
            "subscriptions": [
                {
                    "operate_type": "delete",
                    "project_id": self.project_id,
                    "region_id": self.region,
                    "service_type": "eip",
                    "params": json.dumps(params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(self.basic_url)["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            return {"result": True, "data": json.loads(res.text)}
        else:
            return {"result": False, "message": "删除弹性公网失败"}

    def associate_address(self, **kwargs):
        """云服务器创建并解绑弹性公网"""
        url_par = get_resource_uri(self.basic_url)["eip_url"]
        post_params = {
            "floatingip": {
                "floating_network_id": kwargs.get("floating_network_id"),
                "port_id": kwargs.get("port_id"),
            }
        }
        res = requests.post(url=url_par, headers=self.cw_headers, json=post_params, verify=False)
        return self._handle_result(res, "associate_address")

    def disassociate_address(self, floatingip_id, **kwargs):
        """云服务器解绑弹性公网"""
        url_par = "{}/{}".format(get_resource_uri(self.basic_url)["eip_url"], floatingip_id)
        res = requests.put(url=url_par, headers=self.cw_headers, verify=False)
        return self._handle_result(res, "disassociate_address")

    # ------------------***** 负载均衡 *****---------------
    def list_load_balancers(self, ids=None, **kwargs):
        """查询负载均衡"""
        url_par = get_resource_uri(f"https://vpc.hnxc-region-1.{self.host}")["load_balancer_url"]
        if ids:
            url_par = "{}/{}".format(url_par, ids[0])
        res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
        if res.status_code < 300:
            data_dict = res.json()
            load_balancer_list = data_dict.get("loadbalancers", [])
            if load_balancer_list:
                result_list = [self.load_balancer_format(cur_load_balancer) for cur_load_balancer in load_balancer_list]
                return {"result": True, "data": result_list}
            else:
                return {"result": True, "data": [self.load_balancer_format(data_dict)]}
        else:
            return {"result": False, "message": "查询负载均衡列表失败！"}

    def create_load_balancers(self, **kwargs):
        """新建负载均衡， 订单接口"""
        list_required_params = ["product_id", "tenancy", "loadbalancer", "count", "display"]
        check_required_params(list_required_params, kwargs)
        params = {
            "loadbalancer": kwargs.get("loadbalancer"),
            "count": kwargs.get("count"),
            "display": kwargs.get("display"),
        }
        list_options_params = ["publicip", "bandwidth"]
        params = set_optional_params(list_options_params, kwargs, params)
        body = {
            "subscriptions": [
                {
                    "region_id": self.region,
                    "service_type": "elb",
                    "project_id": self.project_id,
                    "product_id": kwargs.get("product_id"),
                    "operate_type": "apply",
                    "tenancy": int(kwargs.get("tenancy")),
                    "params": json.dumps(params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(self.basic_url)["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            order_id = res.json()["purchases"][0]["subscription_id"]
            return self.handle_order_result(order_id)
        else:
            return {"result": False, "message": "新建负载均衡失败"}

    def delete_load_balancer(self, lb_id, **kwargs):
        """删除负载均衡, 订单接口"""
        list_required_params = ["display"]
        check_required_params(list_required_params, kwargs)
        params = {
            "ids": {"id": lb_id, "service_type": "elb"},
            "display": kwargs.get("display"),
        }
        body = {
            "subscriptions": [
                {
                    "service_type": "elb",
                    "operate_type": "delete",
                    "project_id": self.project_id,
                    "region_id": self.region,
                    "params": json.dumps(params),
                }
            ]
        }
        res = requests.post(
            url=get_resource_uri(self.basic_url)["order"], headers=self.cw_headers, json=body, verify=False
        )
        if res.status_code < 300:
            return {"result": True, "data": json.loads(res.text)}
        else:
            return {"result": False, "message": "删除弹性公网失败"}

    def create_load_balancer_listen(self, **kwargs):
        """添加监听(四种协议)"""
        list_required_params = ["loadbalancer_id", "protocol"]
        check_required_params(list_required_params, kwargs)
        project_id = self.project_id
        body = {"listener": {"tenant_id": self.project_id}}
        set_params = [
            "admin_state_up",
            "connection_limit",
            "default_pool_id",
            "default_tls_container_ref",
            "description",
            "http2_enable",
            "loadbalancer_id",
            "name",
            "protocol",
            "protocol_port",
            "sni_container_refs",
        ]
        set_optional_params(set_params, kwargs, body["listener"])
        res = requests.post(
            url=get_resource_uri(self.basic_url, project_id)["listener_url"],
            headers=self.cw_headers,
            json=body,
            verify=False,
        )
        if res.status_code < 300:
            return {"result": True, "data": res.json()["listener"]["id"]}
        return {"result": False, "message": "create_load_balancer_listen failed"}

    def list_load_balancer_listen(self, ids, **kwargs):
        """查询监听"""
        tenant_id = self.project_id
        url_par = "{}/v2.0/lbaas/listeners".format(self.basic_url)
        if ids:
            url_par = "{}/{}".format(url_par, ids[0])
        res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
        if res.status_code < 300:
            data_dict = res.json()
            load_balancer_listen_list = data_dict.get("listeners", [])
            if load_balancer_listen_list:
                result_list = []
                for cur in load_balancer_listen_list:
                    load_balancer_id = cur.get("id")
                    backend_servers = self.list_backend_servers(load_balancer_id=load_balancer_id, tenant_id=tenant_id)
                    if backend_servers.get("result"):
                        cur["backend_servers"] = backend_servers["data"]
                    result = self.load_balancer_listen_format(cur)
                    result_list.append(result)
                return {"result": True, "data": load_balancer_listen_list}
            else:
                cur = data_dict.get("listener")
                load_balancer_id = cur.get("id")
                backend_servers = self.list_backend_servers(load_balancer_id=load_balancer_id, tenant_id=tenant_id)
                if backend_servers.get("result"):
                    cur["backend_servers"] = backend_servers["data"]
                result = self.load_balancer_listen_format(cur)
                return {"result": True, "data": result}
        else:
            return {"result": False, "message": "查询监听失败"}

    def modify_load_balancer_listen(self, **kwargs):
        """修改监听(四种协议)"""
        listeners_id = kwargs.get("listeners_id")
        url_par = f"{self.basic_url}/v2.0/lbaas/listeners/{listeners_id}"
        body = {"listener": {}}
        set_params = ["connection_limit", "description", "name"]
        set_optional_params(set_params, kwargs, body["listener"])
        res = requests.put(url=url_par, headers=self.cw_headers, json=body, verify=False)
        return self._handle_result(res, "modify_load_balancer_listen")

    def delete_load_balancer_listen(self, **kwargs):
        """删除监听"""
        listener_id = kwargs.get("listener_id")
        url_par = f"{self.basic_url}/v2.0/lbaas/listeners/{listener_id}"
        res = requests.delete(url=url_par, headers=self.cw_headers, verify=False)
        return self._handle_result(res, "delete_load_balancer_listen")

    def list_rules(self, ids=None, **kwargs):
        """查询转发策略"""
        url_par = f"{self.basic_url}/v2.0/lbaas/l7policies"
        if ids:
            url_par = f"{url_par}/{ids[0]}"
        res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
        return self._handle_list_result(res, "rule", "list_rules")

    def create_rule(self, **kwargs):
        """添加转发策略"""
        url_par = f"{self.basic_url}/v2.0/lbaas/l7policies"
        list_required_params = ["action", "listener_id", "redirect_pool_id"]
        check_required_params(list_required_params, kwargs)
        body = {"l7policy": {"tenant_id": self.project_id}}
        set_params = [
            "action",
            "admin_state_up",
            "description",
            "listener_id",
            "name",
            "position",
            "redirect_pool_id",
            "redirect_listener_id",
            "redirect_url",
        ]
        set_optional_params(set_params, kwargs, body["l7policy"])
        res = requests.put(url=url_par, headers=self.cw_headers, json=body, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()["l7policy"]["id"]}
        return {"result": False, "message": "create_rule failed"}

    def delete_rule(self, rule_id, **kwargs):
        """删除转发策略"""
        url_par = f"{self.basic_url}/v2.0/lbaas/l7policies/{rule_id}"
        res = requests.delete(url=url_par, headers=self.cw_headers, verify=False)
        return self._handle_result(res, "delete_rule")

    # ------------------***** backend_server *****---------------
    def list_backend_servers(self, ids=None, **kwargs):
        """查询后端服务器"""
        load_balancer_id = kwargs.get("load_balancer_id")
        url_par = f"{self.basic_url}/nsx/v1/{self.project_id}/query/pools/{load_balancer_id}/list"
        res = requests.get(url=url_par, headers=self.cw_headers)
        if res.status_code == 200:
            data_dict = res.json()
            result_list = data_dict.get("pools", [])
            result_list = [self.backend_servers_format(cur) for cur in result_list]
            return {"result": True, "data": result_list}
        else:
            return {"result": False, "message": "查询后端服务器失败"}

    def add_backend_servers(self, **kwargs):
        """添加后端服务器"""
        pool_id = kwargs.get("pool_id")
        url_par = f"{self.basic_url}/v2.0/lbaas/pools/{pool_id}/members"
        list_required_params = ["address", "protocol_port", "subnet_cidr_id"]
        check_required_params(list_required_params, kwargs)
        body = {"member": {"tenant_id": self.project_id}}
        set_params = ["address", "admin_state_up", "name", "protocol_port", "subnet_cidr_id", "weight"]
        set_optional_params(set_params, kwargs, body["member"])
        res = requests.post(url=url_par, headers=self.cw_headers, json=body, verify=False)
        if res.status_code < 300:
            return {"result": True, "data": res.json()["member"]["id"]}
        return {"result": False, "message": "add_backend_servers failed"}

    def delete_backend_servers(self, bs_id, **kwargs):
        """删除后端服务器"""
        url_par = f"{self.basic_url}/nsx/v1/{self.project_id}/delete/pools/{bs_id}"
        res = requests.get(url=url_par, headers=self.cw_headers)
        return self._handle_result(res, "delete_backend_servers")

    def describe_health_status(self, ids=None, **kwargs):
        """查询后端服务器的健康状态"""
        url_par = f"{self.basic_url}/v2.0/lbaas/healthmonitors"
        if ids:
            url_par = f"{url_par}/{ids[0]}"
        res = requests.get(url=url_par, headers=self.cw_headers)
        return self._handle_result(res, "describe_health_status")

    # ***********************对象存储obs****************************************
    def _create_obs_client(self):
        """
        初始化OBS客户端（ObsClient）
        :param server: eg：https://your-endpoint
        :return:
        """
        account_object = AccountConfig.objects.filter(account=self.account, cloud_type="FusionCompute").first()
        if not account_object.icon:
            ak, sk = "P4Z0HVFFO9GQTXPHPDLB", "DahzWavDVgdh0ZlBhOy6ZBVnvkfKzcC5bGnp3gOO"
        else:
            ak, sk = account_object.icon.split("/")
        server = f"https://obsv3.{self.region}.{self.host}:443"
        obs_client = ObsClient(access_key_id=ak, secret_access_key=sk, server=server)
        return obs_client

    def create_bucket(self, **kwargs):
        """创建存储桶"""
        bucket_name = kwargs.get("bucket_name", uuid.uuid1().hex)
        obs_client = self._create_obs_client()
        resp = obs_client.createBucket(bucket_name)
        obs_client.close()
        return self._handle_result(resp, "create_bucket")

    def list_buckets(self, **kwargs):
        """获取Bucket列表信息"""
        obs_client = self._create_obs_client()
        resp = obs_client.listBuckets(True)
        ali_result = []
        if resp.status > 300:
            logger.exception("调用获取桶存储接口失败{}".format(resp.errorMessage))
            return {"result": False, "message": resp.errorMessage}
        bucket_list = resp.body.buckets
        for bucket_item in bucket_list:
            name = bucket_item.name
            obj_resp = obs_client.listObjects(name)
            if obj_resp.status > 300:
                return {"result": False, "message": resp.errorMessage}
            obj_list = obj_resp.body.contents
            size = 0
            for obj in obj_list:
                size += obj.size
            size = round(size / 1024 / 1024, 2)
            ali_result.append(self.format_bucket(bucket_item, size=size, obj_list=obj_list))
        obs_client.close()
        return {"result": True, "data": ali_result}

    def delete_bucket(self, bucket_name, **kwargs):
        """删除某个存储空间（Bucket）"""
        obs_client = self._create_obs_client()
        resp = obs_client.deleteBucket(bucket_name)
        if resp.status < 300:
            return {"result": True}
        logger.exception(f"delete bucket {bucket_name} fail")
        obs_client.close()
        return {"result": False, "message": resp.errorMessage}

    def put_object(self, **kwargs):
        """上传文件"""
        bucket_name = kwargs.get("bucket_name")
        obs_client = self._create_obs_client()
        if "file_path" not in kwargs:
            return {"result": False, "message": "need param local_path"}
        file_path = kwargs.get("file_path")
        if file_path[-1] == "/":
            kwargs.pop("content")
        resp = obs_client.putContent(bucket_name, file_path, kwargs.get("content"))
        if resp.status_code < 300:
            return {"result": True}
        logger.exception(f" put_object {file_path} fail")
        obs_client.close()
        return {"result": False, "message": resp.errorMessage}

    def load_object(self, **kwargs):
        """下载文件"""
        local_path = kwargs.get("local_path")
        object_name = kwargs.get("object_name")
        bucket_name = kwargs.get("bucket_name")
        obs_client = self._create_obs_client()
        resp = obs_client.getObject(bucket_name, object_name, local_path)
        if resp.status_code < 300:
            return {"result": True}
        logger.exception(f" load_object {object_name} fail")
        obs_client.close()
        return {"result": False, "message": resp.errorMessage}

    def delete_object(self, **kwargs):
        """删除文件"""
        object_name = kwargs.get("object_name")
        bucket_name = kwargs.get("bucket_name")
        obs_client = self._create_obs_client()
        resp = obs_client.deleteObject(bucket_name, object_name)
        if resp.status_code < 300:
            return {"result": True}
        logger.exception(f" delete_object {object_name} fail")
        obs_client.close()
        return {"result": False, "message": resp.errorMessage}

    def list_bucket_object(self, **kwargs):
        """获取存储桶下的所有object"""
        bucket_name = kwargs.get("bucket_name")
        file_path = kwargs.get("file_path", "")
        obs_client = self._create_obs_client()
        resp = obs_client.listObjects(bucket_name, prefix=file_path, delimiter="/")
        if resp.status_code > 300:
            return {"result": False, "message": resp.errorMessage}
        object_list = resp.body.contents
        ali_result = [item.key for item in object_list]
        return {"result": True, "data": ali_result}

    def list_dv_swtich(self, **kwargs):
        """获取分布式交换机"""
        url_par = f"https://sc.{self.host}/rest/orchestration/v3.0/fcvpc/dvswitchs?cloud_infra_id={self.pool_id}"
        try:
            get_res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
            if get_res.status_code < 300:
                data_dict = get_res.json()
                dv_switch_list = data_dict.get("dvSwitchs", [])
                return {"result": True, "data": dv_switch_list}
            else:
                return {"result": False, "message": get_res.json()}
        except Exception as e:
            return {"result": False, "message": str(e)}

    def list_datastores(self, **kwargs):
        """获取存储列表"""
        url_par = f"https://sc.{self.host}/rest/orchestration/v3.0/fcevs/datastores?cloud_infra_id={self.pool_id}"
        try:
            get_res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
            if get_res.status_code < 300:
                data_dict = get_res.json()
                datastore_list = data_dict.get("datastores", [])
                return {"result": True, "data": datastore_list}
            else:
                return {"result": False, "message": get_res.json()}
        except Exception as e:
            return {"result": False, "message": str(e)}

    def list_clusters(self, **kwargs):  # noqa
        url_par = (
            f"https://sc.{self.host}/rest/orchestration/v3.0/fcserviceaccess/clusters" f"?cloud_infra_id={self.pool_id}"
        )
        try:
            get_res = requests.get(url=url_par, headers=self.cw_headers, verify=False)
            if get_res.status_code < 300:
                data_dict = get_res.json()
                datastore_list = data_dict.get("clusters", [])
                return {"result": True, "data": datastore_list}
            else:
                return {"result": False, "message": get_res.json()}
        except Exception as e:
            return {"result": False, "message": str(e)}

    # ------------------***** 文件存储 *****---------------

    # ------------------***** format *****---------------
    @staticmethod
    def vm_format(vm_obj):
        """Format VM Object"""
        # handle disk
        system_disk_list = []
        data_disk_list = []
        for cur_disk in vm_obj.get("volumes", []):
            data_dict = {
                "resource_id": cur_disk.get("id"),
                "resource_name": cur_disk.get("name"),
                "cloud_type": "FusionCompute",
                "is_attached": True,
                "device_type": FusionComputeDiskType[cur_disk["type"]],
                "status": cur_disk.get("status"),
                "platform_type": "vmware_vc",
                "disk_type": "系统盘" if cur_disk.get("is_system_volume") else "数据盘",
                "disk_size": cur_disk.get("size"),
            }
            if cur_disk.get("is_system_volume"):
                system_disk_list.append(data_dict)
            else:
                data_disk_list.append(data_dict)
        inner_ip_list = []
        security_group_list = []

        for index, cur_nic in enumerate(vm_obj.get("nics", [])):
            inner_ip_dict = {
                "resource_id": cur_nic.get("id") or cur_nic.get("ip"),
                "resource_name": cur_nic.get("name") or cur_nic.get("ip"),
                "ip": cur_nic.get("ip"),
                "id": cur_nic.get("id") or index,
                "is_used": 0,
            }
            sg_info = cur_nic.get("sg_info", [])
            for cur_security_group in sg_info:
                security_group_list.append(cur_security_group.get("sg_id"))
                inner_ip_dict["security_group_id"] = cur_security_group.get("sg_id")
                inner_ip_dict["is_used"] = 1  # 表示该网卡被绑定安全组
            inner_ip_list.append(inner_ip_dict)
        vm_spec_info = vm_obj.get("vm_spec_info")
        status_map = {
            "running": "RUNNING",
            "stopped": "STOP",
            "stopping": "STOP",
            "creating": "BUILD",
            "unknown": "ERROR",
        }
        return VM(
            uuid=vm_obj.get("vm_id"),
            resource_id=vm_obj.get("id"),
            resource_name=vm_obj.get("name"),
            cloud_type="FusionCompute",
            vcpus=vm_spec_info.get("cpu_count"),
            memory=vm_spec_info.get("memory_count"),
            os_name=vm_obj.get("os_type"),
            status=status_map.get(vm_obj.get("status"), vm_obj.get("status")),
            inner_ip=inner_ip_list,
            security_group=security_group_list,
            system_disk=system_disk_list,
            data_disk=data_disk_list,
            project=vm_obj.get("project_id"),
            zone=vm_obj.get("available_zone_name"),
            region=vm_obj.get("region_id"),
            expired_time=vm_obj.get("tenancy"),
            create_time=vm_obj.get("create_time"),
            desc=vm_obj.get("description") or "",
            vpc=vm_obj.get("nics")[0].get("vpc_id") if vm_obj.get("nics") else "",
            subnet=vm_obj.get("nics")[0].get("network_id") if vm_obj.get("nics") else "",
        ).to_dict()

    @staticmethod
    def image_format(cur_image):
        status_map = {"public": "PUBLIC"}
        return Image(
            resource_id=cur_image.get("id"),
            resource_name=cur_image.get("name"),
            status="AVAILABLE",
            arch=cur_image.get("arch"),
            image_type=status_map.get(cur_image.get("type"), cur_image.get("type")),
            os_type=cur_image.get("os_type"),
            desc=cur_image.get("description"),
            size=cur_image.get("memory_info").get("quantity") if isinstance(cur_image.get("memory_info"), dict) else 0,
            cloud_type="FusionCompute",
            os_name=cur_image.get("os_version").replace("bit", "位").replace("Kylin", "麒麟"),
            os_name_en=cur_image.get("os_version").replace("bit", "位"),
            platform=cur_image.get("os_type"),
            extra={
                "cpu_info": cur_image.get("cpu_info"),
                "memory_info": cur_image.get("memory_info"),
                "os_option": cur_image.get("os_option"),
                "diskdetail": cur_image.get("diskdetail"),
            },
        ).to_dict()

    def snapshot_format(self, snapshot_obj, server_id):
        """Format snapshot Object"""
        return Snapshot(
            resource_id=snapshot_obj.get("id"),
            resource_name=snapshot_obj.get("name"),
            disk_type=snapshot_obj.get("type"),
            disk_size=snapshot_obj.get("memorySize"),
            desc=snapshot_obj.get("description", "") or "",
            create_time=snapshot_obj.get("createTime"),
            status="NORMAL" if snapshot_obj.get("status") == "ready" else snapshot_obj.get("status"),
            cloud_type="FusionCompute",
            server_id=server_id,
            project=self.project_id,
            extra={
                "volSnapshots": snapshot_obj.get("volSnapshots"),
                "coreNum": snapshot_obj.get("coreNum"),
                "volumeSizeSum": snapshot_obj.get("volumeSizeSum"),
                "childSnapshots": snapshot_obj.get("childSnapshots"),
            },
        ).to_dict()

    @staticmethod
    def disk_format(disk_obj):
        """Format Disk Object"""
        attchment = disk_obj.get("attachments")[0] if disk_obj.get("attachments") else {}
        status_map = {"INUSE": "ATTACHED", "USE": "UNATTACHED", "LOSE": "回收中"}
        return Disk(
            resource_id=disk_obj.get("id"),
            resource_name=disk_obj.get("name"),
            disk_size=disk_obj.get("size"),
            status=status_map.get(disk_obj.get("status"), disk_obj.get("status")),
            category=disk_obj.get("media_type"),
            create_time=disk_obj.get("created_at"),
            expired_time=disk_obj.get("expired_at"),
            is_attached=attchment != {},
            server_id=attchment.get("server_id") or "",
            project=disk_obj.get("project_id"),
            cloud_type="FusionCompute",
            extra={"volumeId": disk_obj.get("volumeId")},
        ).to_dict()

    @staticmethod
    def security_group_format(security_group_obj):
        """Format security group Object"""
        return SecurityGroup(
            resource_id=security_group_obj.get("id"),
            resource_name=security_group_obj.get("sgName"),
            # project=security_group_obj.get("project_id"),
            create_time=security_group_obj.get("create_at") or "",
            desc=security_group_obj.get("sgDesc", "") or "",
            cloud_type="FusionCompute",
            extra={
                "rules": security_group_obj.get("rules"),
                "vmNum": security_group_obj.get("vmNum"),
                "vmList": security_group_obj.get("vmList"),
                "sgId": security_group_obj.get("sgId"),
            },
        ).to_dict()

    @staticmethod
    def sgr_format(sgr_obj):
        """Format security_group_rule object"""
        if not sgr_obj.get("direction") is None:
            direction = "INGRESS" if sgr_obj.get("direction") in ["0", 0] else "EGRESS"
        else:
            direction = "ALL"
        return SecurityGroupRule(
            resource_id=sgr_obj.get("rules_id"),
            dest_cidr=sgr_obj.get("ip_ranges"),
            port_range=f'{sgr_obj.get("from_port")}/{sgr_obj.get("to_port")}',
            desc=sgr_obj.get("description"),
            protocol=sgr_obj.get("ip_protocol"),
            security_group=sgr_obj.get("security_group_id"),
            cloud_type="FusionCompute",
            direction=direction,
        ).to_dict()

    @staticmethod
    def vpc_format(vpc_obj):
        """Format VPC Object"""
        return VPC(
            resource_id=vpc_obj.get("vpc_id"),
            resource_name=vpc_obj.get("name"),
            desc=vpc_obj.get("description", "") or "",
            create_time=vpc_obj.get("create_time"),
            project=vpc_obj.get("project_id"),
            cloud_type="FusionCompute",
            region=vpc_obj.get("region_id"),
            cidr_v6=vpc_obj.get("cidr_v6", "") or "",
        ).to_dict()

    @staticmethod
    def subnet_format(subnet_obj):
        status = "AVAILABLE" if subnet_obj.get("status") == "ACTIVE" else "ERROR"
        cidr = subnet_obj.get("ipv4_subnet").get("subnet_id") if isinstance(subnet_obj.get("ipv4_subnet"), dict) else ""
        cidr_v6 = (
            subnet_obj.get("ipv6_subnet").get("subnet_id") if isinstance(subnet_obj.get("ipv6_subnet"), dict) else ""
        )
        dns = ""
        return Subnet(
            status=status,
            resource_id=subnet_obj.get("id"),
            resource_name=subnet_obj.get("name"),
            desc=subnet_obj.get("description", "") or "",
            cloud_type="FusionCompute",
            cidr=cidr,
            cidr_v6=cidr_v6,
            dns=dns,
            zone=subnet_obj.get("region_id", "") or "",
            create_time=subnet_obj.get("create_time"),
            project=subnet_obj.get("project_id"),
            vpc=subnet_obj.get("vpc_id"),
            extra={"vlan_id": subnet_obj.get("vlan_id"), "neutron_subnet_id": subnet_obj.get("dvs_urn")},
        ).to_dict()

    @staticmethod
    def time_control(time_data):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_data / 1000))

    def route_table_format(self, cur_obj):
        return RouteTable(
            resource_id=cur_obj.get("id"),
            create_time=self.time_control(cur_obj.get("createTime")) if cur_obj.get("createTime") else "",
            # resource_name="未命名",
            cloud_type="FusionCompute",
            extra={
                "protocols": cur_obj.get("protocols"),
                "service": cur_obj.get("service"),
                "methods": cur_obj.get("methods"),
                "hosts": cur_obj.get("hosts"),
                "updateTime": cur_obj.get("updateTime"),
            },
        ).to_dict()

    @staticmethod
    def route_entry_format(obj):
        return RouteEntry(
            resource_id=obj.get("id"),
            next_hops=obj.get("nexthop"),
            cloud_type="FusionCompute",
        ).to_dict()

    @staticmethod
    def floatingips_format(obj):
        """弹性公网IP格式化"""
        status_map = {
            "ACTIVE": "BIND",
            "DOWN": "UNBIND",
            "ERROR": "UNKNOWN",
        }
        return Eip(
            resource_id=obj.get("id"),
            status=status_map.get(obj.get("status"), obj.get("status")),
            ip_addr=obj.get("floating_ip_address"),
            private_ip_addr=obj.get("fixed_ip_address"),
            create_time=obj.get("created_at")[:19].replace("T", " "),
            bandwidth=0,
            project=obj.get("project_id"),
            is_attached=True if obj.get("port_id") else False,
            cloud_type="FusionCompute",
            extra={
                "router_id": obj.get("router_id"),
                "tenant_id": obj.get("tenant_id"),
                "qos_policy_id": obj.get("qos_policy_id"),
                "port_id": obj.get("port_id"),
                "updated_at": obj.get("updated_at"),
            },
        ).to_dict()

    @staticmethod
    def load_balancer_format(obj):
        return LoadBalancer(
            desc=obj.get("description"),
            resource_id=obj.get("id"),
            resource_name=obj.get("name"),
            # project=obj.get("tenant_id"),
            status=True if obj.get("operating_status") == "ONLINE" else False,
            create_time=obj.get("created_at")[:19].replace("T", " "),
            status_time=obj.get("updated_at")[:19].replace("T", " "),
            vips=[obj.get("vip_address")],
            cloud_type="FusionCompute",
            extra={
                "tenant_id": obj.get("tenant_id"),
                "vip_subnet_id": obj.get("vip_subnet_id"),
                "vip_port_id": obj.get("vip_port_id"),
                "provisioning_status": obj.get("provisioning_status"),
                "pools": obj.get("pools"),
            },
        ).to_dict()

    @staticmethod
    def load_balancer_listen_format(obj):
        return LoadBalancerListener(
            status=obj.get("admin_state_up"),
            desc=obj.get("description"),
            resource_id=obj.get("id"),
            resource_name=obj.get("name"),
            load_balancer="".join(obj.get("loadbalancers")),
            backend_version=obj.get("protocol"),
            backend_port=obj.get("protocol_port"),
            backend_servers=obj.get("backend_servers"),
            cloud_type="FusionCompute",
        ).to_dict()

    @staticmethod
    def rule_format(obj):
        return RelayRule(
            resource_id=obj.get("id"),
            resource_name=obj.get("name"),
            desc=obj.get("description"),
            url=obj.get("redirect_url"),
            cloud_type="FusionCompute",
        ).to_dict()

    @staticmethod
    def backend_servers_format(obj):
        return {"Type": "ecs", "Weight": 0, "ServerId": obj.get("id")}

    @staticmethod
    def format_bucket(item, size, obj_list):
        return Bucket(
            resource_id=item.name,
            resource_name=item.name,
            region=item.location,
            extra={"size": size, "obj_list": obj_list},
            create_time=item.create_date,
            cloud_type="FusionCompute",
        ).to_dict()

    @staticmethod
    def region_format(region_obj):
        return Region(
            resource_id=region_obj.get("id"),
            resource_name=region_obj.get("name"),
            cloud_type="FusionCompute",
            extra={
                "created": region_obj.get("created"),
                "lastModified": region_obj.get("lastModified"),
                "locale": region_obj.get("locale"),
                "active": region_obj.get("active"),
                "domainType": region_obj.get("domainType"),
                "type": region_obj.get("type"),
            },
        ).to_dict()

    @staticmethod
    def zone_format(zone_obj):
        return Zone(
            resource_id=zone_obj.get("az_id"),
            resource_name=zone_obj.get("name"),
            cloud_type="FusionCompute",
            status=zone_obj.get("status"),
            region=zone_obj.get("region", "hnxc-region-1"),
            extra={
                "az_res_id": zone_obj.get("az_res_id"),
                "type": zone_obj.get("type"),
                "cloud_infra_id": zone_obj.get("cloud_infra_id"),
                "has_clusters": zone_obj.get("has_clusters"),
                "extend_param": zone_obj.get("extend_param"),
            },
        ).to_dict()

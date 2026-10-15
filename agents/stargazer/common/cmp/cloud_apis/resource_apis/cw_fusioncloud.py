# -*- coding: UTF-8 -*-
import json
import uuid

import IPy
import requests
from obs import ObsClient

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.cloud_constant import CloudPlatform
from common.cmp.cloud_apis.cloud_object.base import VM, Disk, Domain, Image, InstanceType, Project, Region, Subnet, Zone
from common.cmp.cloud_apis.constant import CloudResourceType, CloudType, SubnetStatus
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.cloud_apis.resource_apis.resource_format.openstack.openstack_format_utils import (
    handle_image_status,
    handle_vm_status,
    handle_volume_status,
)
from common.cmp.cloud_apis.resource_apis.utils import fail, success
from common.cmp.utils import set_dir_size
from core.logger import logger

https_port = "443"
endpoint = "jx.hsip.public.cn"


class CwFusionCloud(object):
    """
    通过该类创建FusionCloud的Client实例，调用FusionCloudapi接口
    """

    def __init__(self, username, password, region, host="", **kwargs):
        """
         初始化方法，创建Client实例。在创建Client实例时，您需要获取Region ID、AccessKey ID和AccessKey Secret
        :param secret_id:
        :param secret_key:
        :param region_id:
        :param kwargs:
        """
        self.username = username
        self.password = password
        self.kwargs = kwargs
        self.host = host
        self.region = region
        self.https_port = kwargs.get("https_port", https_port)
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "project_id" not in kwargs:
            self.project_id = ""
        else:
            self.project_id = kwargs.pop("project_id")
        # if "endpoint" not in kwargs:
        if not kwargs.get("endpoint"):
            self.endpoint = region + "." + endpoint
        else:
            self.endpoint = region + "." + kwargs.pop("endpoint")
        self.version = kwargs.get("version") or "8.0.3"
        if "8.0.3" == self.version:
            self.token = self._log_on_new()
        else:
            self.token = self._log_on("https://{}.{}/v3/auth/tokens".format("iam-apigateway-proxy", self.host))

    def __getattr__(self, item):
        """
        private方法，返回对应的东风云接口类
        :param item:
        :return:
        """
        if self.version == "6.3":
            return FusionCloud(
                name=item,
                project_id=self.project_id,
                host=self.host,
                region=self.region,
                username=self.username,
                password=self.password,
                https_port=self.https_port,
                endpoint=self.endpoint,
                token=self.token,
            )
        elif self.version == "8.0.3":
            return FusionCloudNew(
                name=item,
                project_id=self.project_id,
                host=self.host,
                region=self.region,
                username=self.username,
                password=self.password,
                https_port=self.https_port,
                endpoint=self.endpoint,
                token=self.token,
            )
        else:
            raise ValueError("无可用版本")

    def _log_on(self, auth_url):
        """
        登录验证，获取token
        """
        data = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {"name": self.username, "password": self.password, "domain": {"name": self.username}}
                    },
                },
                "scope": {"project": {"id": self.project_id}},
            }
        }
        headers = {"Content-Type": "application/json"}
        token = ""
        try:
            result = requests.post(auth_url, headers=headers, data=json.dumps(data), verify=False)
        except Exception as e:
            logger.exception(e)
            return ""
        if result.status_code == 201 and "X-Subject-Token" in result.headers:
            token = result.headers["X-Subject-Token"]
        return token

    def _log_on_new(self):
        """8.0.3 获取 token"""
        url = "https://{}.{}/v3/auth/tokens".format("iam-apigateway-proxy", self.host)
        json_params = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        # domain里的name与username不一样, 但是没有该属性, 且一般客户会使用一样的username, 故domain直接用了username
                        "user": {"domain": {"name": self.username}, "name": self.username, "password": self.password}
                    },
                },
                "scope": {"project": {"id": self.project_id, "domain": {"name": self.username}}},
            }
        }
        auth_token = ""
        headers = {"Content-Type": "application/json"}
        try:
            resp = requests.post(url=url, headers=headers, json=json_params, verify=False)
        except Exception as e:
            logger.exception(e)
            return ""
        if resp.status_code == 201:
            auth_token = resp.headers.get("X-Subject-Token", "")
        else:
            # logger.exception(eval(resp.content)["errorDes"])
            logger.exception("获取Token失败")
        return auth_token


class FusionCloud(PrivateCloudManage):
    """
    FusionCloud接口类
    """

    def __init__(self, name, project_id, host, https_port, endpoint, region, username, password, token):
        """
        初始化方法
        """
        self.project_id = project_id
        self.host = host
        self.https_port = https_port
        self.endpoint = endpoint
        self.name = name
        self.region = region
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
        return fail("没有该功能！")

    def get_connection_result(self):
        """
        检查连接是否成功
        """
        if self.token:
            return success("连接成功")
        else:
            return fail("连接失败")

    def list_regions(self, resource_id="", **kwargs):
        """
        获取区域列表
        """
        if resource_id:
            return fail("暂无法获取此类资源详情")
        url = "https://iam-apigateway-proxy.{}/v3/regions".format(self.host)
        return request_get_list(url, self.cw_headers, "region")

    def list_zones(self, resource_id="", **kwargs):
        """
        获取可用区列表
        """
        if resource_id:
            return fail("暂无法获取此类资源详情")
        url = "https://ecs.{}/v2/{}/os-availability-zone".format(self.endpoint, self.project_id)
        headers = self.cw_headers
        headers["X-Project-Id"] = self.project_id
        try:
            result = requests.get(url, verify=False, headers=headers)
        except Exception as e:
            logger.exception(e)
            return fail("可用区列表获取失败")
        data = []
        if result.status_code == 200:
            content = json.loads(result.content)
            for i in content.get("availabilityZoneInfo", []):
                data.append(
                    get_format_method(
                        CloudPlatform.FusionCloud,
                        CloudResourceType.ZONE.value,
                        project_id=self.project_id,
                        region_id=self.region,
                    )(i, **kwargs)
                )
            return success(data)
        else:
            message = result.content
            return fail(message)

    def list_projects(self, resource_id="", **kwargs):
        """
        获取项目列表
        """
        if resource_id:
            return fail("暂无法获取此类资源详情")
        url = "https://{}:{}/v3/auth/projects".format(self.host, self.https_port)
        return request_get_list(url, self.cw_headers, CloudResourceType.PROJECT.value)

    def list_domains(self, resource_id="", **kwargs):
        if resource_id:
            return fail("暂无法获取此类资源详情")
        url = "https://{}:{}/v3/auth/domains".format(self.host, self.https_port)
        return request_get_list(url, self.cw_headers, "domain", project_id=self.project_id, region=self.region)

    def list_instance_types(self, resource_id="", **kwargs):
        """
        获取规格列表
        """
        if resource_id:
            return fail("暂无法获取此类资源详情")
        url = "https://ecs.{}/v2/{}/flavors".format(self.endpoint, self.project_id)
        return request_get_list(url, self.cw_headers, "flavor", project_id=self.project_id, region=self.region)

    def list_vms(self, ids="", **kwargs):
        """
        获取虚拟机列表
        """
        if ids:
            return self.get_vm_detail(ids[0])
        url = "https://ecs.{}/v2/{}/servers/detail".format(self.endpoint, self.project_id)
        headers = self.cw_headers
        headers["X-Project-Id"] = self.project_id
        return request_get_list(url, headers, "server", project_id=self.project_id, region=self.region)

    def get_vm_detail(self, vm_id):
        url = "https://ecs.{}/v2/{}/servers/{}".format(self.endpoint, self.project_id, vm_id)
        headers = self.cw_headers
        headers["X-Project-Id"] = self.project_id
        return request_get(url, headers, "server", project_id=self.project_id, region=self.region)

    @classmethod
    def _set_vm_params(cls, body, **kwargs):
        server = body["server"]
        system_disk = server["block_device_mapping_v2"][0]
        if "password" in kwargs:
            server["metadata"] = {"admin_pass": kwargs.get("password")}
        if "private_ip" in kwargs:
            server["networks"]["fixed_ip"] = kwargs["private_ip"]
        if "security_groups" in kwargs:
            server["security_groups"] = kwargs.get("security_groups")
        if "image_id" in kwargs:
            server["imageRef"] = kwargs.get("image_id")
        if "system_disk_id" in kwargs:
            system_disk["uuid"] = kwargs.get("system_disk_id")
        if "data_disk_ids" in kwargs:
            if kwargs.get("data_disk_ids") and type(kwargs.get("data_disk_ids")) == list:
                for i in kwargs.get("data_disk_ids"):
                    server["block_device_mapping_v2"].append(
                        {
                            "uuid": i,
                            "source_type": "volume",
                            "destination_type": "volume",
                            "delete_on_termination": kwargs.get("delete_on_termination", True),  # 删除vm时，是否删除卷
                            "boot_index": -1,  # 启动标识，“0”代表启动盘，“-1“代表非启动盘
                        }
                    )
        return body

    def create_vm(self, **kwargs):
        """
        创建虚拟机，在东风云环境中仅支持卷创建，在其他环境中需重新调试接口
        return：{
                    "result": True
                    "data": {
                        "server": {
                            "security_groups":[{"name": ""}],
                            "id": "",
                            "adminPasss": ""
                            "OS-DCF:diskConfig": "MANUAL"  # diskConfig方式。MANUAL，镜像空间不会扩展。AUTO，
                            系统盘镜像空间会自动扩展为与flavor大小一致。
                            "links": "弹性云服务器URI自描述信息"
                        }
                    }
                }
        """
        url = "https://ecs.{}/v2/{}/servers".format(self.endpoint, self.project_id)
        body = {
            "server": {
                "availability_zone": kwargs.get("zone"),
                "flavorRef": kwargs.get("flavor_id"),
                "name": kwargs.get("name"),
                "networks": [
                    {
                        "uuid": kwargs.get("vpc_id"),
                    }
                ],
                "block_device_mapping_v2": [
                    {
                        "source_type": "volume",
                        "destination_type": "volume",
                        "delete_on_termination": True,  # 删除弹性云服务器时，是否删除卷
                        "boot_index": 0,  # 启动标识，“0”代表启动盘，“-1“代表非启动盘
                    }
                ],
                "min_count": int(kwargs.get("min_count", 1)),
                "max_count": int(kwargs.get("max_count", kwargs.get("min_count", 1))),
            }
        }
        body = self._set_vm_params(body, **kwargs)
        return request_post(url, self.cw_headers, **body)

    def start_vm(self, vm_id, *args, **kwargs):
        """
        开机
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {"os-start": {}}
        return request_post(url, self.cw_headers, **body)

    # 重启偶尔无效，云平台不响应，在对接其他fusioncloud环境时，需重新测试
    def restart_vm(self, vm_id, *args, **kwargs):
        """
        重启
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {"reboot": {"type": "SOFT"}}  # 普通重启；HARD：强制重启
        return request_post(url, self.cw_headers, **body)

    def stop_vm(self, vm_id, *args, **kwargs):
        """
        关机
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {"os-stop": {"type": "SOFT"}}  # 普通关机；HARD：强制关机
        return request_post(url, self.cw_headers, **body)

    def destroy_vm(self, vm_id):
        """
        删除虚拟机
        """
        url = "https://ecs.{}/v2/{}/servers/{}".format(self.endpoint, self.project_id, vm_id)
        return request_delete(url, self.cw_headers)

    def resize_vm(self, vm_id, **kwargs):
        """
        变更单台云服务器规格。更改规格时云服务器磁盘不能变小。有变更接口，但请求返回权限错误
        "forbidden":{"message":"Policy doesn\'t allow the action to be
        performed.","code":"403"}），平台上无变更功能.目前在cmp上应用但无法保证功能正确性，需根据具体环境调试
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {
            "os-resize": {
                "flavorRef": kwargs.get("flavor_id"),
                # "dedicated_host_id": kwargs.get("dedicated_host_id")
            }
        }
        return request_post(url, self.cw_headers, **body)

    def live_resize_vm(self, vm_id, **kwargs):
        """
        在线变更单台云服务器规格。更改规格时云服务器磁盘不能变小。
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {
            "live-resize": {
                "flavorRef": kwargs.get("flavor_id"),
                # "dedicated_host_id": kwargs.get("dedicated_host_id")
            }
        }
        return request_post(url, self.cw_headers, **body)

    def confirm_resize(self, vm_id):
        """
        确认单台云服务器规格调整
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {"confirmResize": None}
        return request_post(url, self.cw_headers, **body)

    def revert_resize(self, vm_id):
        """
        回退云服务器规格变更。
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {"revertResize": None}
        return request_post(url, self.cw_headers, **body)

    def instance_security_group_add(self, vm_id, **kwargs):
        """
        为弹性云服务器添加一个安全组。
        添加多个安全组时，建议最多为弹性云服务器添加5个安全组
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {"addSecurityGroup": {"name": kwargs.get("security_group_id")}}
        return request_post(url, self.cw_headers, **body)

    def instance_security_group_del(self, vm_id, **kwargs):
        """
        移除弹性云服务器中的安全组。
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {"removeSecurityGroup": {"name": kwargs.get("security_group_id")}}
        return request_post(url, self.cw_headers, **body)

    # 查询云硬盘列表
    def list_disks(self, ids="", **kwargs):
        """
        获取磁盘列表
        """
        if ids:
            return self.get_disk_detail(ids[0])
        url = "https://evs.{}/v2/{}/volumes/detail".format(self.endpoint, self.project_id)
        return request_get_list(url, self.cw_headers, "volume", project_id=self.project_id, region=self.region)

    def get_disk_detail(self, disk_id):
        """
        获取磁盘详情
        """
        url = "https://evs.{}/v2/{}/volumes/{}".format(self.endpoint, self.project_id, disk_id)
        return request_get(url, self.cw_headers, "volume", project_id=self.project_id, region=self.region)

    def list_disk_types(self):
        """
        获取磁盘类型列表
        """
        url = "https://evs.{}/v2/{}/types".format(self.endpoint, self.project_id)
        return request_get_list(url, self.cw_headers, "volume_type", project_id=self.project_id, region=self.region)

    def create_disk(self, **kwargs):
        """
        创建云盘
        从镜像创建云硬盘时，云硬盘大小不能小于镜像大小。
        从快照创建云硬盘时，云硬盘大小不能小于快照大小, 快照创建云硬盘时，volume_type字段必须和快照源云硬盘保持一致
        从源硬盘创建云硬盘时，云硬盘大小不能小于源硬盘大小。
        return：{
                    "result": True
                    "data": {
                        "volume": {
                            "id":"",
                            ...
                        }  # 返回一个磁盘详情
                    }
                }
        """
        url = "https://evs.{}/v2/{}/volumes".format(self.endpoint, self.project_id)
        body = {
            "volume": {
                "name": kwargs.get("name", "未命名"),
                "size": int(kwargs.get("size", 1)),
                "availability_zone": kwargs.get("zone"),
                "multiattach": kwargs.get("multiattach", False),  # 共享云硬盘标志位。true为共享盘，false为普通云硬盘。
                "volume_type": kwargs.get("volume_type"),
            }
        }
        list_optional_params = ["imageRef", "snapshot_id", "source_volid"]  # source_volid 源云硬盘ID
        body["volume"] = request_optional_params(list_optional_params, kwargs, body.get("volume"))
        return request_post(url, self.cw_headers, **body)

    def delete_disk(self, disk_id, *args, **kwargs):
        """
        删除云盘(块存储)
        """
        url = "https://evs.{}/v2/{}/volumes/{}".format(self.endpoint, self.project_id, disk_id)
        return request_delete(url, self.cw_headers)

    def resize_disk(self, **kwargs):
        """
        磁盘扩容、不能缩小
        """
        url = "https://evs.{}/v2/{}/volumes/{}/action".format(self.endpoint, self.project_id, kwargs.get("disk_id"))
        body = {"os-extend": {"new_size": kwargs.get("new_size")}}
        return request_post(url, self.cw_headers, **body)

    def attach_disk(self, **kwargs):
        """
        云硬盘挂载
        """
        url = "https://ecs.{}/v2/{}/servers/{}/os-volume_attachments".format(
            self.endpoint, self.project_id, kwargs.get("vm_id")
        )
        body = {
            "volumeAttachment": {
                "volumeId": kwargs.get("disk_id"),
                "device": kwargs.get("device", "/dev/vdc"),  # 挂载点
            }
        }
        return request_post(url, self.cw_headers, **body)

    def detach_disk(self, **kwargs):
        """
        云硬盘卸载
        """
        url = "https://ecs.{}/v2/{}/servers/{}/os-volume_attachments/{}".format(
            self.endpoint, self.project_id, kwargs.get("vm_id"), kwargs.get("disk_id")
        )
        if "delete_flag" in kwargs:  # 在线强制卸载磁盘标志位。默认为0，为1时代表强制卸载。
            url = "{}?delete_flag={}".format(url, int(kwargs.get("delete_flag")))
        return request_delete(url, self.cw_headers)

    def list_images(self, resource_id="", **kwargs):
        """
        获取镜像列表
        """
        if resource_id:
            return fail("暂无法获取此类资源详情")
        url = "https://ims.{}/v2/cloudimages".format(self.endpoint)
        return request_get_list(
            url, self.cw_headers, CloudResourceType.IMAGE.value, project_id=self.project_id, region=self.region
        )

    def list_snapshots(self, resource_id="", **kwargs):
        """
        获取云盘快照列表
        """
        if resource_id:
            return fail("暂无法获取此类资源详情")
        url = "https://evs.{}/v2/{}/snapshots/detail".format(self.endpoint, self.project_id)
        return request_get_list(
            url, self.cw_headers, CloudResourceType.SNAPSHOT.value, project_id=self.project_id, region=self.region
        )

    def snapshot_recovery(self, **kwargs):
        """
        磁盘快照回滚,必要在快照和磁盘都处于可用状态才能回滚，无测试数据，未测试
        """
        url = "https://evs.{}/v2/{}/os-vendor-snapshots/{}/rollback".format(
            self.endpoint, self.project_id, kwargs.get("snapshot_id")
        )
        body = {"rollback": {"volume_id": kwargs.get("disk_id")}}
        if "name" in kwargs:
            body["rollback"]["name"] = kwargs["name"]
        return request_post(url, self.cw_headers, **body)

    def delete_snapshot(self, snapshot_id, *args, **kwargs):
        """
        删除云盘快照
        """
        url = "https://evs.{}/v2/{}/snapshots/{}".format(self.endpoint, self.project_id, snapshot_id)
        return request_delete(url, self.cw_headers)

    # 与东风生产环境实际vpc不一致，在东风中router代表vpc,子网由一个network加上一个subnet组成
    def list_vpcs(self, resource_id="", **kwargs):
        """
        获取网络列表
        """
        if resource_id:
            return self.get_vpc_detail(resource_id)
        url = "https://vpc.{}/v2.0/networks".format(self.endpoint)
        return request_get_list(url, self.cw_headers, "vpc", project_id=self.project_id, region=self.region)

    def get_vpc_detail(self, vpc_id):
        """
        获取vpc详情
        """
        url = "https://vpc.{}/v2.0/networks/{}".format(self.endpoint, vpc_id)
        return request_get(url, self.cw_headers, "vpc", project_id=self.project_id, region=self.region)

    def delete_vpc(self, vpc_id, *args, **kwargs):
        """
        删除vpc
        """
        url = "https://vpc.{}/v2.0/networks/{}".format(self.endpoint, vpc_id)
        return request_delete(url, self.cw_headers)

    def create_vpc(self, **kwargs):
        """
        创建vpc,一个network仅支持关联一个 subnet。
        在东风云中，一个network加上一个subnet组成一个子网，一个router为一个vpc
        """
        url = "https://vpc.{}/v2.0/networks".format(self.endpoint)
        body = {
            "network": {
                "name": kwargs.get("name", "未命名"),
                "admin_state_up": True,
            }
        }
        list_optional_params = [
            "router:external",
            "shared",
            "provider:physical_network",
            "provider:network_type",
            "availability_zones",
            "description",
        ]
        body = request_optional_params(list_optional_params, kwargs, body)
        return request_post(url, self.cw_headers, **body)

    def update_vpc(self, **kwargs):
        """
        更新vpc
        """
        url = "https://vpc.{}/v2.0/networks/{}".format(self.endpoint, kwargs.get("router_id"))
        body = {
            "router": {
                "name": kwargs.get("name"),
            }
        }
        return request_put(url, self.cw_headers, **body)

    # 查询子网列表
    def list_subnets(self, resource_id="", **kwargs):
        """
        获取子网列表信息
        """
        if resource_id:
            return self.get_subnet_detail(resource_id)
        url = "https://vpc.{}/v2.0/subnets".format(self.endpoint)
        return request_get_list(
            url, self.cw_headers, CloudResourceType.SUBNET.value, project_id=self.project_id, region=self.region
        )

    def get_subnet_detail(self, subnet_id):
        """
        获取子网详情
        """
        url = "https://vpc.{}/v2.0/subnets/{}".format(self.endpoint, subnet_id)
        return request_get(
            url, self.cw_headers, CloudResourceType.SUBNET.value, project_id=self.project_id, region=self.region
        )

    def delete_subnet(self, subnet_id, *args, **kwargs):
        """
        删除子网
        """
        url = "https://vpc.{}/v2.0/subnets/{}".format(self.endpoint, subnet_id)
        return request_delete(url, self.cw_headers)

    def create_subnet(self, **kwargs):
        """
        创建子网
        """
        url = "https://vpc.{}/v2.0/subnets".format(self.endpoint)
        if not (kwargs.get("start_ip", "") or kwargs.get("end_ip", "")) and kwargs.get("cidr"):
            cidr = kwargs.get("cidr").split("/")
            ip = cidr[0].split(".")
            ip[-1] = "2"
            kwargs["start_ip"] = ".".join(ip)
            ip[-1] = "254"
            kwargs["end_ip"] = ".".join(ip)
        body = {
            "subnet": {
                "name": kwargs.get("name"),
                "enable_dhcp": kwargs.get("enable_dhcp", True),
                "network_id": kwargs.get("network_id"),
                "tenant_id": self.project_id,
                "dns_nameservers": kwargs.get("dns_list", []),  # dns服务器列表
                "allocation_pools": [{"start": kwargs.get("start_ip", ""), "end": kwargs.get("end_ip", "")}],  # 可用IP池
                "ip_version": kwargs.get("ip_version", 4),
                "gateway_ip": kwargs.get("gateway_ip"),
                "cidr": kwargs.get("cidr"),
            }
        }
        return request_post(url, self.cw_headers, **body)

    def update_subnet(self, **kwargs):
        """
        更新子网
        """
        url = "https://vpc.{}/v2.0/subnets/{}".format(self.endpoint, kwargs.get("subnet_id"))
        body = {
            "subnet": {
                "name": kwargs.get("name"),
                # "dns_nameservers": kwargs.get("dns_list"),  # dns服务器列表
                # "gateway_ip": kwargs.get("gateway_ip"),
                # "cidr": kwargs.get("cidr"),
                # "allocation_pools": [  # 可用IP池
                #     {
                #         "start": kwargs.get("start_ip"),
                #         "end": kwargs.get("end_ip")
                #     }
                # ]
            }
        }
        return request_put(url, self.cw_headers, **body)

    # fusioncloud安全组与虚拟机关联字段为name，且无法确认唯一性，先假定name具备唯一性，当某虚拟机有一个名称x的安全组时，
    # 无法在添加其他名称为x的安全组，查询虚拟机安全组时，会显示全部名称为x的安全组
    def list_security_groups(self, security_group_id=None, **kwargs):
        """
        获取安全组列表信息
        """
        if security_group_id:
            return self.get_security_group_detail(security_group_id)
        url = "https://vpc.{}/v2.0/security-groups".format(self.endpoint)
        return request_get_list(
            url, self.cw_headers, CloudResourceType.SECURITY_GROUP.value, project_id=self.project_id, region=self.region
        )

    def get_security_group_detail(self, security_group_id):
        """
        获取安全组详情
        """
        url = "https://vpc.{}/v2.0/security-groups/{}".format(self.endpoint, security_group_id)
        return request_get(
            url, self.cw_headers, CloudResourceType.SECURITY_GROUP.value, project_id=self.project_id, region=self.region
        )

    def delete_security_group(self, security_group_id):
        """
        删除安全组
        """
        url = "https://vpc.{}/v2.0/security-groups/{}".format(self.endpoint, security_group_id)
        return request_delete(url, self.cw_headers)

    def create_security_group(self, **kwargs):
        """
        创建安全组
        """
        url = "https://vpc.{}/v2.0/security-groups".format(self.endpoint)
        body = {"security_group": {"name": kwargs.get("name")}}
        res = request_post(url, self.cw_headers, **body)
        if res["result"]:
            res["data"] = res["data"]["security_group"].get("id")
        return res

    def update_security_group(self, **kwargs):
        """
        更新安全组
        """
        url = "https://vpc.{}/v2.0/security-groups/{}".format(self.endpoint, kwargs.get("security_group_id"))
        body = {"security_group": {"name": kwargs.get("name")}}
        return request_put(url, self.cw_headers, **body)

    def list_security_group_rules(self, resource_id="", **kwargs):
        """
        获取安全组规则列表
        """
        if resource_id:
            return self.get_security_group_rule_detail(resource_id)
        url = "https://vpc.{}/v2.0/security-group-rules".format(self.endpoint)
        list_params = [
            "security_group_id",
            "remote_group_id",
            "direction",
            "remote_ip_prefix",
            "protocol",
            "port_range_max",
            "port_range_min",
            "ethertype",
            "tenant_id",
        ]
        mark = "?"
        for i in kwargs.keys():
            if i in list_params:
                url = "{}{}{}={}".format(url, mark, i, kwargs.get(i))
                mark = "&"
        return request_get_list(
            url,
            self.cw_headers,
            CloudResourceType.SECURITY_GROUP_RULE.value,
            project_id=self.project_id,
            region=self.region,
        )

    def get_security_group_rule_detail(self, security_group_rule_id):
        """
        获取安全组规则详情
        """
        url = "https://vpc.{}/v2.0/security-group-rules/{}".format(self.endpoint, security_group_rule_id)
        return request_get(
            url,
            self.cw_headers,
            CloudResourceType.SECURITY_GROUP_RULE.value,
            project_id=self.project_id,
            region=self.region,
        )

    def create_security_group_rule(self, **kwargs):
        """
        创建安全组规则
        """
        url = "https://vpc.{}/v2.0/security-group-rules".format(self.endpoint)
        body = {
            "security_group_rule": {
                "security_group_id": kwargs.get("security_group_id"),
                "direction": kwargs.get("direction"),
                "protocol": kwargs.get("protocol", None),
                "remote_ip_prefix": kwargs.get("remote_ip_prefix", None),
                "port_range_min": kwargs.get("port_range_min", None),
                "port_range_max": kwargs.get("port_range_max", None),
            }
        }
        try:
            result = requests.post(url, verify=False, headers=self.cw_headers, data=json.dumps(body))
        except Exception as e:
            logger.exception(e)
            message = str(e)
            if str(e).startswith("Security group rule already exists"):
                message = "规则已存在！"
            failed_ip = kwargs["remote_ip_prefix"]
            return {"result": False, "message": message, "failed_ip": failed_ip}
        if result.status_code < 300:
            return success(result.content)
        else:
            message = result.content
            failed_ip = kwargs["remote_ip_prefix"]
            return {"result": False, "message": message, "failed_ip": failed_ip}

    def delete_security_group_rule(self, security_group_rule_id):
        url = "https://vpc.{}/v2.0/security-group-rules/{}".format(self.endpoint, security_group_rule_id)
        return request_delete(url, self.cw_headers)

    def list_eips(self, resource_id="", **kwargs):
        """
        获取浮动ip列表
        """
        if resource_id:
            return self.get_eip_detail(resource_id)
        url = "https://vpc.{}/v2.0/floatingips".format(self.endpoint)
        return request_get_list(
            url, self.cw_headers, CloudResourceType.EIP.value, project_id=self.project_id, region=self.region
        )

    def get_eip_detail(self, eip_id):
        """
        获取浮动ip详情
        """
        url = "https://vpc.{}/v2.0/floatingips/{}".format(self.endpoint, eip_id)
        return request_get(
            url, self.cw_headers, CloudResourceType.EIP.value, project_id=self.project_id, region=self.region
        )

    def release_eip(self, eip_id):
        """
        删除浮动ip
        """
        url = "https://vpc.{}/v2.0/floatingips/{}".format(self.endpoint, eip_id)
        return request_delete(url, self.cw_headers)

    def create_eip(self, **kwargs):
        """
        创建浮动ip
        """
        url = "https://vpc.{}/v2.0/floatingips".format(self.endpoint)
        body = {
            "floatingip": {
                "floating_network_id": kwargs.get("floating_network_id"),
                "port_id": kwargs.get("port_id"),
            }
        }
        list_optional_params = [
            "router:external",
            "shared",
            "provider:physical_network",
            "provider:network_type",
            "availability_zones",
            "description",
        ]
        body = request_optional_params(list_optional_params, kwargs, body)
        return request_post(url, self.cw_headers, **body)

    def update_eip(self, **kwargs):
        """
        更新浮动ip
        """
        url = "https://vpc.{}/v2.0/floatingips/{}".format(self.endpoint, kwargs.get("eip_id"))
        body = {
            "floatingip": {
                "port_id": kwargs.get("port_id"),
                "fixed_ip_address": kwargs.get("fixed_ip_address"),
            }
        }
        return request_put(url, self.cw_headers, **body)

    def get_monitor_data(self):
        return fail("无法获取数据")

    def get_load_monitor_data(self, **kwargs):
        return fail("无法获取数据")


class FusionCloudNew(FusionCloud):
    def list_regions(self, resource_id="", **kwargs):
        """
        获取区域列表
        """
        if resource_id:
            return fail("暂无法获取此类资源详情")
        url = "https://iam-apigateway-proxy.{}/v3/regions".format(self.host)
        return request_get_list(url, self.cw_headers, "region")

    def list_projects(self, resource_id="", **kwargs):
        """
        获取项目列表
        """
        if resource_id:
            return fail("暂无法获取此类资源详情")
        url = "https://{}.{}/v3/auth/projects".format("iam-apigateway-proxy", self.host)
        return request_get_list(url, self.cw_headers, CloudResourceType.PROJECT.value)

    def list_instance_types(self, resource_id="", **kwargs):
        """
        获取规格列表
        :param resource_id:
        :param kwargs:
        :return:
        """
        url = "https://ecs.{}/v2/{}/flavors".format(self.endpoint, self.project_id)
        if resource_id:
            url = f"{url}/{resource_id}"
            return request_get(url, self.cw_headers, "flavor", project_id=self.project_id, region=self.region)
        return request_get_list(url, self.cw_headers, "flavor", project_id=self.project_id, region=self.region)

    def list_available_flavor(self, **kwargs):
        """获取可用规格列表"""
        url = f"https://ecs.{self.endpoint}/v1/{self.project_id}/cloudservers/flavors"
        return request_get_without_format(url, self.cw_headers, "flavors")

    def list_available_disk(self, flavor_id):
        """获取可用磁盘类型"""
        url_par = (
            f"https://ccs.{self.endpoint}/v1.0/resource-tags?resource_type=volume_type&availability_zone={flavor_id}"
        )
        return request_get_without_format(url_par, self.cw_headers, "resources")

    def list_vms(self, ids=None, **kwargs):
        """
        获取虚拟机列表
        :param ids:
        :param kwargs:
        :return:
        """
        url = f"https://ecs.{self.endpoint}/v2.1/{self.project_id}/servers/detail"
        if ids:
            # fusion创建没有返回id, 只能以name做搜索
            url += "?name={}".format(ids[0])
        return request_get_list(url, self.cw_headers, "server", project_id=self.project_id, region=self.region)

    def get_vm_spec(self, vm_id):
        """获取虚拟机详情"""
        url_par = f"https://ecs.{self.endpoint}/v1/{self.project_id}/cloudservers/{vm_id}"
        return request_get(url_par, self.cw_headers, "server", project_id=self.project_id, region=self.region)

    def create_vm(self, **kwargs):
        """创建虚拟机"""
        url_par = f"https://ecs.{self.endpoint}/v1.1/{self.project_id}/cloudservers"
        # must_par = ['imageRef', "flavorRef", "name", "vpcid", "nics", "root_volume", "availability_zone", "power_on"]
        # check_must_parameters(must_par, **kwargs)
        # body = {"server": {}}
        # body['server'].update(kwargs)
        # return request_post(url_par, self.cw_headers, **body)
        return request_post(url_par, self.cw_headers, **kwargs)

    def resize_vm(self, vm_id, **kwargs):
        """
        变更单台云服务器规格。更改规格时云服务器磁盘不能变小。有变更接口，但请求返回权限错误
        "forbidden":{"message":"Policy doesn\'t allow the action to be
        performed.","code":"403"}），平台上无变更功能.目前在cmp上应用但无法保证功能正确性，需根据具体环境调试
        """
        url = "https://ecs.{}/v2/{}/servers/{}/action".format(self.endpoint, self.project_id, vm_id)
        body = {"resize": {"flavorRef": kwargs.get("flavor_id"), "dedicated_host_id": kwargs.get("dedicated_host_id")}}
        return request_post(url, self.cw_headers, **body)

    def live_resize_vm(self, vm_id, **kwargs):
        """
        在线变更单台云服务器规格。更改规格时云服务器磁盘不能变小。
        :param vm_id:
        :param kwargs:
        :return:
        """
        url = f"https://ecs.{self.endpoint}/v1/{self.project_id}/cloudservers/{vm_id}/live-resize"
        body = {
            "live-resize": {"flavorRef": kwargs.get("flavor_id"), "dedicated_host_id": kwargs.get("dedicated_host_id")}
        }
        return request_post(url, self.cw_headers, **body)

    def list_disks(self, ids=None, **kwargs):
        """
        获取磁盘列表
        """

        url = "https://evs.{}/v2/{}/volumes/detail".format(self.endpoint, self.project_id)
        if ids:
            url += "?name={}".format(ids[0])
        optional_par = [
            "availability_zone",
            "changes-since",
            "limit",
            "marker",
            "metadata",
            "name",
            "offset",
            "server_id",
            "snapshot_metadata",
            "sort_dir",
            "sort_key",
            "status",
            "with_snapshot",
        ]
        query_url = request_optional_params_url(optional_par, **kwargs)
        if query_url:
            url = f"{url}?{query_url}"
        return request_get_list(url, self.cw_headers, "volume", project_id=self.project_id, region=self.region)

    def create_disk(self, **kwargs):
        """
        创建云盘
        :param kwargs:
        :return:
        """
        url = "https://evs.{}/v2/{}/volumes".format(self.endpoint, self.project_id)
        optional_par = [
            "availability_zone",
            "consistencygroup_id",
            "description",
            "imageRef",
            "metadata",
            "size",
            "source_volid",
            "multiattach",
            "name",
            "scheduler_hints",
            "snapshot_id",
            "source_replica",
            "volume_type",
        ]
        body = {"volume": {}}
        request_optional_params(optional_par, kwargs, body.get("volume"))
        res = request_post(url, self.cw_headers, **body)
        if res["result"]:
            return {"result": True, "data": res["data"]["volume"]["name"]}
        else:
            return {"result": False, "message": res["message"]}

    def list_images(self, ids=None, **kwargs):
        """
        根据不同条件查询镜像列表信息
        :param ids:
        :param kwargs:
        :return:
        """
        url = "https://ims.{}/v2/cloudimages".format(self.endpoint)
        if ids:
            url += "?id={}".format(ids[0])
        headers = self.cw_headers
        headers["X-Project-Id"] = self.project_id
        return request_get_list(
            url, headers, CloudResourceType.IMAGE.value, project_id=self.project_id, region=self.region
        )

    def list_snapshots(self, ids=None, **kwargs):
        """
        获取云盘快照列表
        """
        url = "https://evs.{}/v2/{}/snapshots/detail?0=0".format(self.endpoint, self.project_id)
        if ids:
            url += "&name={}".format(ids[0])
        optional_par = ["limit", "name", "offset", "status", "volume_id"]
        query_url = request_optional_params_url(optional_par, **kwargs)
        if query_url:
            url = f"{url}&{query_url}"
        return request_get_list(
            url, self.cw_headers, CloudResourceType.SNAPSHOT.value, project_id=self.project_id, region=self.region
        )

    def create_image(self, **kwargs):
        """
        创建镜像
        name:镜像名称
        instance_id:虚拟机示例ID
        """
        url = f"https://ims.{self.region}.{self.host}/v1/cloudimages/wholeimages/action"
        body = {"name": kwargs.get("name"), "instance_id": kwargs.get("instance_id")}
        return request_post(url, self.cw_headers, **body)

    def delete_image(self, **kwargs):
        url_par = "https://ims.{}/v2/images/{}".format(self.endpoint, kwargs["image_id"])
        return request_delete(url_par, self.cw_headers)

    def list_vpcs(self, ids=None, **kwargs):
        """
        获取网络列表
        """
        url = "https://vpc.{}/v1/{}/vpcs".format(self.endpoint, self.project_id)
        if ids:
            url += "?id={}".format(ids[0])
        return request_get_list(url, self.cw_headers, "vpc", project_id=self.project_id, region=self.region)

    def update_vpc(self, vpc_id, **kwargs):
        """
        更新vpc
        """
        url = "https://vpc.{}/v1/{}/vpcs/{}".format(self.endpoint, self.project_id, vpc_id)
        body = {"vpc": {}}
        list_optional_params = ["name", "external_gateway_info", "ntp", "ntp_v6", "tags"]
        body = request_optional_params(list_optional_params, kwargs, body)
        return request_put(url, self.cw_headers, **body)

    def get_vpc_sepc(self, vpc_id):
        """获取vpc详情"""
        url_par = f"https://vpc.{self.endpoint}/v1/{self.project_id}/vpcs/{vpc_id}"
        return request_get(url_par, self.cw_headers, "vpc")

    def create_vpc(self, **kwargs):
        """创建VPC"""
        url_par = f"https://vpc.{self.endpoint}/v1/{self.project_id}/vpcs"
        return request_post(url_par, self.cw_headers, **kwargs)

    def delete_vpc(self, vpc_id, *args, **kwargs):
        """删除vpc"""
        url = f"https://vpc.{self.endpoint}/v2.0/routers/{vpc_id}"
        return request_delete(url, self.cw_headers)

    def get_subnet_detail(self, subnet_id):
        """
        获取子网详情
        """
        url = "https://vpc.{}/v1/{}/subnets/{}".format(self.endpoint, self.project_id, subnet_id)
        return request_get(
            url,
            self.cw_headers,
            CloudResourceType.SUBNET.value,
            project_id=self.project_id,
            region=self.region,
            version="8.0",
        )

    def delete_subnet(self, subnet_id, vpc_id):
        """删除子网"""
        url_par = f"https://vpc.{self.endpoint}/v1/{self.project_id}/vpcs/{vpc_id}/subnets/{subnet_id}"
        return request_delete(url_par, self.cw_headers)

    def list_subnets(self, ids=None, **kwargs):
        """
        获取子网列表信息
        """
        url = "https://vpc.{}/v1/{}/subnets".format(self.endpoint, self.project_id)
        if ids:
            url += "?vpc_id={}".format(ids[0])
        return request_get_list(
            url, self.cw_headers, CloudResourceType.SUBNET.value, project_id=self.project_id, region=self.region
        )

    def create_subnet(self, **kwargs):
        """创建子网"""
        url_par = f"https://vpc.{self.endpoint}/v1/{self.project_id}/subnets"
        res = request_post(url_par, self.cw_headers, **kwargs)
        return res

    def list_routers(self, ids=None):
        """查询vpc路由列表"""
        if ids:
            return fail("暂无法获取此类资源详情")
        url_par = f"https://vpc.{self.endpoint}/v2.0/routers"
        try:
            result = requests.get(url_par, verify=False, headers=self.cw_headers)
        except Exception as e:
            logger.exception(e)
            return fail("请求异常")
        data = []
        if result.status_code < 300:
            content = json.loads(result.content)
            for i in content.get("routers", []):
                for j in i["routes"]:
                    i["route_info"] = j
                    data.append(
                        get_format_method(
                            CloudPlatform.FusionCloud, "router", project_id=self.project_id, region_id=self.region
                        )(i, **{"project_id": self.project_id, "region_id": self.region})
                    )
            return success(data)
        else:
            logger.error(result.content)
            return fail("获取{}资源列表错误".format("router"))

        # return request_get_list(url_par, self.cw_headers, 'router', project_id=self.project_id, region=self.region)

    def get_router_spec(self, router_id):
        """查询vpc路由"""
        url_par = f"https://vpc.{self.endpoint}/v2.0/routers/{router_id}"
        return request_get(url_par, self.cw_headers, "router", project_id=self.project_id, region=self.region)

    def operation_router(self, vpc_id, **kwargs):
        """创建，删除，修改vpc的路由表"""
        url_par = f"https://vpc.{self.endpoint}/v1/{self.project_id}/vpcs/{vpc_id}"
        return request_put(url_par, self.cw_headers, **kwargs)

    def list_security_groups(self, ids=None, **kwargs):
        """
        获取安全组列表信息
        """
        url = "https://vpc.{}/v2.0/security-groups".format(self.endpoint)
        if ids:
            url += "?id={}".format(ids[0])
        return request_get_list(
            url, self.cw_headers, CloudResourceType.SECURITY_GROUP.value, project_id=self.project_id, region=self.region
        )

    def update_security_group(self, **kwargs):
        """
        更新安全组
        """
        url = "https://vpc.{}/v2.0/security-groups/{}".format(self.endpoint, kwargs.get("security_group_id"))
        body = {"security_group": {"name": kwargs.get("name"), "description": kwargs.get("description")}}
        return request_put(url, self.cw_headers, **body)

    def list_security_group_rules(self, security_group_id=None, **kwargs):
        """
        获取安全组规则列表
        """
        url = "https://vpc.{}/v2.0/security-group-rules".format(self.endpoint)
        if security_group_id:
            url += "?security_group_id={}".format(security_group_id)
        return request_get_list(
            url,
            self.cw_headers,
            CloudResourceType.SECURITY_GROUP_RULE.value,
            project_id=self.project_id,
            region=self.region,
        )

    def create_security_group_rule(self, **kwargs):
        """
        创建安全组规则
        """
        must_par = ["security_group_id", "direction"]
        check_must_parameters(must_par, **kwargs)
        url = "https://vpc.{}/v2.0/security-group-rules".format(self.endpoint)
        body = {
            "security_group_rule": {
                "direction": kwargs.get("direction"),
                "security_group_id": kwargs.get("security_group_id"),
                # "remote_group_id": kwargs.get("remote_group_id", None),
                "description": kwargs.get("description", ""),
                "protocol": kwargs.get("protocol", None),
                # "ethertype": kwargs.get("ethertype", None),
                "remote_ip_prefix": kwargs.get("remote_ip_prefix", None),
                "port_range_min": kwargs.get("port_range_min", None),
                "port_range_max": kwargs.get("port_range_max", None),
            }
        }
        try:
            result = requests.post(url, verify=False, headers=self.cw_headers, data=json.dumps(body))
        except Exception as e:
            logger.exception(e)
            message = str(e)
            if str(e).startswith("Security group rule already exists"):
                message = "规则已存在！"
            failed_ip = kwargs["remote_ip_prefix"]
            return {"result": False, "message": message, "failed_ip": failed_ip}
        else:
            if result.status_code < 300:
                result_dict = json.loads(result.content)
                resource_id = result_dict["security_group_rule"]["id"]
                return success(resource_id)
            else:
                message = result.content
                failed_ip = kwargs["remote_ip_prefix"]
                return {"result": False, "message": message, "failed_ip": failed_ip}

    def list_eips(self, ids=None, **kwargs):
        """
        获取浮动ip列表
        """
        url = "https://vpc.{}/v2.0/floatingips".format(self.endpoint)
        if ids:
            url += "?id={}".format(ids[0])
        return request_get_list(url, self.cw_headers, "floatingip", project_id=self.project_id, region=self.region)

    def update_eip(self, **kwargs):
        """
        更新浮动ip
        """
        must_par = ["port_id"]
        check_must_parameters(must_par, **kwargs)
        url = "https://vpc.{}/v2.0/floatingips/{}".format(self.endpoint, kwargs.get("eip_id"))
        body = {
            "floatingip": {
                "port_id": kwargs.get("port_id"),
                "fixed_ip_address": kwargs.get("fixed_ip_address"),
            }
        }
        return request_put(url, self.cw_headers, **body)

    def release_eip(self, eip_id):
        """删除弹性公网"""
        url_par = f"https://vpc.{self.endpoint}/v2.0/floatingips/{eip_id}"
        return request_delete(url_par, self.cw_headers)

    def associate_address(self, **kwargs):
        """绑定弹性公网"""
        interface_data = self.list_os_interface(kwargs["instance_id"])
        if not interface_data.get("data"):
            return {"result": False, "message": "虚拟机网卡未找到"}
        port_id = interface_data["data"][0]["port_id"]
        body = {"floatingip": {"port_id": port_id}}

        url = "https://vpc.{}/v2.0/floatingips/{}".format(self.endpoint, kwargs["eip_id"])
        return request_put(url, self.cw_headers, **body)

    def disassociate_address(self, **kwargs):
        """解绑弹性公网"""
        body = {"floatingip": {"port_id": None}}

        url = "https://vpc.{}/v2.0/floatingips/{}".format(self.endpoint, kwargs["eip_id"])
        return request_put(url, self.cw_headers, **body)

    def list_os_interface(self, instance_id):
        url = "https://ecs.{}/v2/{}/servers/{}/os-interface".format(self.endpoint, self.project_id, instance_id)
        return request_get_without_format(url, self.cw_headers, "interfaceAttachments")

    def destroy_vm(self, vm_id):
        """删除虚拟机"""
        url = "https://ecs.{}/v1/{}/cloudservers/delete".format(self.endpoint, self.project_id)
        body = {"servers": [{"id": vm_id}]}
        return request_post(url, self.cw_headers, **body)

    def list_flavors(self):
        """
        获取可用规格
        :return:
        """
        url = "https://ecs.{}/v1/{}/cloudservers/flavors".format(self.endpoint, self.project_id)
        return request_get_without_format(url, self.cw_headers, "flavors")

    def list_resize_flavors(self, **kwargs):
        """
        获取可用规格
        :return:
        """
        url = "https://ecs.{}/v1/{}/cloudservers/resize_flavors?source_flavor_id={}".format(
            self.endpoint, self.project_id, kwargs.get("source_flavor_id")
        )
        return request_get_without_format(url, self.cw_headers, "flavors")

    def list_networks(self):
        url = "https://vpc.{}/v2.0/networks".format(self.endpoint)
        return request_get_without_format(url, self.cw_headers, "networks")

    def list_subnets_by_network(self, **kwargs):
        url = "https://vpc.{}/v2.0/subnets?network_id={}".format(self.endpoint, kwargs.get("network_id"))
        return request_get_without_format(url, self.cw_headers, "subnets")

    def list_publicips(self):
        url = "https://vpc.{}/v1/{}/publicips".format(self.endpoint, self.project_id)
        return request_get_without_format(url, self.cw_headers, "publicips")

    def list_bandwidths(self):
        url = "https://vpc.{}/v2.0/{}/bandwidths".format(self.endpoint, self.project_id)
        return request_get_without_format(url, self.cw_headers, "bandwidths")

    def modify_vm_spec(self, **kwargs):
        """虚拟机升降配"""
        url = "https://{}/rest/subscription/v3.0/subscriptions".format(self.endpoint)
        order_params = {
            "ids": [{"ids": kwargs.get("resource_id"), "name": kwargs.get("resource_name"), "service_type": "ecs"}],
            "resize": {"flavorRef": kwargs["flavor_id"]},
        }
        params = {
            "subscriptions": [
                {
                    "service_type": "ecs",
                    "region_id": self.region,
                    "operate_type": "modify",
                    "project_id": self.project_id,
                    "params": json.dumps(order_params),
                }
            ]
        }
        res = request_post(url, self.cw_headers, **params)
        return {"result": True, "data": res["data"]["purchases"][0]["subscription_id"]}

    def renew_vm(self, **kwargs):
        url = "https://sc.{}/rest/subscription/v3.0/subscriptions".format(self.host)
        order_params = {
            "ids": [
                {
                    "id": kwargs.get("resource_id"),
                    "name": kwargs.get("resource_name"),
                    "service_type": "ecs",
                    "tenancy": kwargs.get("renew_time"),
                }
            ]
        }

        params = {
            "subscriptions": [
                {
                    "service_type": "ecs",
                    "operate_type": "delay",
                    "project_id": self.project_id,
                    "region_id": self.region,
                    "tenancy": kwargs["renew_time"],
                    "params": json.dumps(order_params),
                }
            ]
        }
        res = request_post(url, self.cw_headers, **params)
        return {"result": True, "data": res["data"]["purchases"][0]["subscription_id"]}

    def list_load_balancers(self, ids=None, **kwargs):
        """查询负载均衡"""
        url = "https://vpc.{}/v2.0/lbaas/loadbalancers".format(self.endpoint)
        if ids:
            url += "?id={}".format(ids[0])
        return request_get_list(url, self.cw_headers, "loadbalancer", project_id=self.project_id, region=self.region)

    def list_backend_servers_group(self, ids=None):
        """查询后端服务器组列表"""
        url_par = f"https://vpc.{self.endpoint}/v2.0/lbaas/pools"
        if ids:
            return fail("暂无法获取此类资源详情")
        return request_get_list(url_par, self.cw_headers, "pool")

    def list_backend_servers(self, servers_group_id, ids=None):
        """查询后端服务器列表"""
        url_par = f"https://vpc.{self.endpoint}/v2.0/lbaas/pools/{servers_group_id}/members"
        if ids:
            return fail("暂无法获取此类资源详情")
        return request_get_without_format(url_par, self.cw_headers, "members")

    def add_backend_server(self, servers_group_id, **kwargs):
        kwargs["tenant_id"] = self.project_id
        """向服务器组添加后端服务器"""
        url_par = f"https://vpc.{self.endpoint}/v2.0/lbaas/pools/{servers_group_id}/members"
        must_par = ["address", "protocol_port", "subnet_id"]
        check_must_parameters(must_par, **kwargs)
        body = {"member": kwargs}
        return request_post(url_par, self.cw_headers, **body)

    def remove_backend_server(self, servers_group_id, backend_server_id):
        """移除服务器组中的后端服务器"""
        url_par = f"https://vpc.{self.endpoint}/v2.0/lbaas/pools/{servers_group_id}/members/{backend_server_id}"
        return request_delete(url_par, self.cw_headers)

    def list_rules(self, **kwargs):
        """查询转发策略"""
        url = "https://vpc.{}/v2.0/lbaas/l7policies".format(self.endpoint)
        if kwargs.get("rule_ids"):
            url += "?id={}".format(kwargs["rule_ids"])

        return request_get_list(
            url,
            self.cw_headers,
            "l7policie",
            project_id=self.project_id,
            region=self.region,
            load_balancer=kwargs["load_balancer"],
            listener_ids=kwargs["listener_ids"],
        )

    def create_rules(self, **kwargs):
        """创建转发策略"""
        url = "https://vpc.{}/v2.0/lbaas/l7policies".format(self.endpoint)
        return request_post(url, self.cw_headers, **kwargs)

    def delete_rules(self, **kwargs):
        """删除转发策略"""
        if kwargs.get("rule_ids"):
            rule_id = kwargs["rule_ids"][0]
            url = "https://vpc.{}/v2.0/lbaas/l7policies/{}".format(self.endpoint, rule_id)
            return request_delete(url, self.cw_headers)

    def create_load_balancer(self, **kwargs):
        """创建负载均衡"""
        url_par = f"https://{self.endpoint}/v2.0/lbaas/loadbalancers"
        must_par = ["vip_subnet_id"]
        check_must_parameters(must_par, **kwargs)
        body = {"loadbalancer": {}}
        list_optional_params = [
            "name",
            "description",
            "admin_state_up",
            "provider",
            "tenant_id",
            "vip_address",
            "vip_subnet_id",
            "flavor_id",
            "created_at",
            "updated_at",
        ]
        request_optional_params(list_optional_params, kwargs, body["loadbalancer"])
        res = request_post(url_par, self.cw_headers, **body)
        return {"result": True, "data": res["data"]["loadbalancer"]["id"]}

    def delete_load_balancer(self, lb_id):
        """删除负载均衡"""
        url_par = f"https://vpc.{self.endpoint}/v2.0/lbaas/loadbalancers/{lb_id}"
        return request_delete(url_par, self.cw_headers)

    def list_listeners(self, ids=None, **kwargs):
        """查询负载均衡监听"""
        if ids:
            return self.get_listener_spec(ids[0])
        url_par = f"https://vpc.{self.endpoint}/v2.0/lbaas/listeners"
        return request_get_list(
            url_par, self.cw_headers, CloudResourceType.LISTENER.value, project_id=self.project_id, region=self.region
        )

    def get_listener_spec(self, listener_id):
        """查询负载均衡监听详情"""
        url_par = f"https://vpc.{self.endpoint}/v2.0/lbaas/listeners/{listener_id}"
        return request_get(url_par, self.cw_headers, CloudResourceType.LISTENER.value)

    def delete_listener(self, listener_id):
        """删除负载均衡监听"""
        url_par = f"https://vpc.{self.endpoint}/v2.0/lbaas/listeners/{listener_id}"
        return request_delete(url_par, self.cw_headers)

    def create_eip(self, **kwargs):
        """创建弹性公网"""
        body = {
            "publicip": {"type": kwargs["eip_info"]["external_network"]},
            "bandwidth": {
                "name": kwargs["eip_info"]["bandwidth_name"],
                "size": kwargs["eip_info"]["bandwidth_size"],
                "share_type": "PER",
            },
        }
        url = "https://vpc.{}/v1/{}/publicips".format(self.endpoint, self.project_id)
        res = request_post(url, self.cw_headers, **body)
        return {"result": True, "data": res["data"]["publicip"]["id"]}

    def list_external_networks(self):
        url = "https://vpc.{}/v1/{}/external_networks?vpc_networks_type=Internet".format(self.endpoint, self.project_id)
        return request_get_without_format(url, self.cw_headers, "vpc_external_networks")

    def instance_security_group_action(self, **kwargs):
        """给实例绑定/解绑安全组"""
        net_card_id = kwargs.get("net_card_id")
        body = {"port": {"security_groups": kwargs.get("security_groups", [])}}
        url_par = f"https://vpc.{self.endpoint}/v2.0/ports/{net_card_id}"
        return request_put(url_par, self.cw_headers, **body)

    def create_snapshot(self, **kwargs):
        """创建云盘快照"""
        url = "https://evs.{}/v2/{}/snapshots".format(self.endpoint, self.project_id)
        body = {
            "snapshot": {
                "name": kwargs.get("snapshot_name"),
                "description": kwargs.get("description", ""),
                "volume_id": kwargs.get("resource_id"),
                "force": False,
            }
        }
        res = request_post(url, self.cw_headers, **body)
        return {"result": True, "data": res["data"]["snapshot"]["name"]}

    # ***********************对象存储obs****************************************
    def _create_obs_client(self):
        """
        初始化OBS客户端（ObsClient）
        :return:
        """
        ak, sk = "1OTGLTDTWU8FLTWYYIKH", "VfBptw9yA0oyCff3ikMxfdTwceNaeTWtCITTdfnb"
        server = f"https://obsv3.{self.region}.{self.host}:443"
        obs_client = ObsClient(access_key_id=ak, secret_access_key=sk, server=server)
        return obs_client

    def create_bucket(self, **kwargs):
        """创建存储桶"""
        try:
            bucket_name = kwargs.get("bucket_name", uuid.uuid1().hex)
            obs_client = self._create_obs_client()
            resp = obs_client.createBucket(bucket_name)
            obs_client.close()
            if resp.status < 300:
                return {"result": True, "data": "OK"}
            return {"result": False, "message": "create_bucket failed"}
        except Exception as e:
            return {"result": False, "message": str(e)}

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
            try:
                name = bucket_item.name
                obj_resp = obs_client.listObjects(name)
                if obj_resp.status > 300:
                    return {"result": False, "message": resp.errorMessage}
                obj_list = obj_resp.body.contents
                size = 0
                for obj in obj_list:
                    size += obj.size
                size = round(size / 1024 / 1024, 2)
                ali_result.append(
                    get_format_method(CloudPlatform.FusionCloud, "bucket")(bucket_item, size=size, obj_list=obj_list)
                )
            except Exception:
                continue
        obs_client.close()
        return {"result": True, "data": ali_result}

    def list_bucket_file(self, bucket_name, location):
        """获取存储桶下的所有object"""
        format_func = get_format_method(CloudPlatform.FusionCloud, "bucket_file")
        obs_client = self._create_obs_client()
        resp = obs_client.listObjects(bucketName=bucket_name)
        if resp.status > 300:
            logger.exception("调用获取桶存储文件接口失败{}".format(resp.errorMessage))
            return {"result": False, "message": resp.errorMessage}

        object_lists = resp.body.contents
        for item in object_lists:
            if item.key.endswith("/"):
                item["type"] = "DIR"
                item["parent"] = "/".join(item.key.split("/")[:-2]) if "/" in item.key.strip("/") else "/"
                item["name"] = item.key.split("/")[-2]
            else:
                item["type"] = "FILE"
                item["parent"] = "/".join(item.key.split("/")[:-1]) if "/" in item.key else "/"
                item["name"] = item.key.split("/")[-1]
        top_dir_list = [item for item in object_lists if item["parent"] == "/" and item["type"] == "DIR"]
        for top_dir in top_dir_list:
            set_dir_size(top_dir, object_lists, "fusioncloud")

        ali_result = [format_func(item, bucket=bucket_name, location=location) for item in object_lists]
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


# ***********************Common****************************************


resource_type_dict = {
    "network": CloudResourceType.VPC.value,
    "volume": CloudResourceType.DISK.value,
    "volume_type": "volume_type",
    "flavor": CloudResourceType.INSTANCE_TYPE.value,
    "l7policie": "rule",
    "loadbalancer": "load_balancer",
    "floatingip": "eip",
    "listener": CloudResourceType.LISTENER.value,
    "server": CloudResourceType.SERVER.value,
    "pool": "pool",
    "member": "member",
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
                    CloudPlatform.FusionCloud,
                    resource_type,
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region", ""),
                )(i, **kwargs)
            )
        return success(data)
    else:
        logger.error(result.content)
        return fail("获取{}资源列表错误".format(resource_type))


def request_get(url, headers, resource_type, **kwargs):
    """
    get请求格式方法
    """
    format_type = resource_type
    try:
        result = requests.get(url, verify=False, headers=headers)
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    if result.status_code < 300:
        content = json.loads(result.content)
        if resource_type in resource_type_dict:
            format_type = resource_type_dict[resource_type]
        data = get_format_method(
            CloudPlatform.FusionCloud, format_type, project_id=kwargs.get("project_id"), region_id=kwargs.get("region")
        )(content.get(resource_type, {}), **kwargs)
        return success([data])
    else:
        logger.error(result.content)
        return fail("获取{}资源详情错误".format(resource_type))


def request_get_without_format(url, headers, resource_type, **kwargs):
    try:
        result = requests.get(url, verify=False, headers=headers)
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    if result.status_code < 300:
        content = json.loads(result.content)
        return success(content.get(resource_type, []))
    else:
        logger.error(result.content)
        return fail("获取{}资源详情错误".format(resource_type))


def request_post(url, headers, **kwargs):
    try:
        result = requests.post(url, verify=False, headers=headers, data=json.dumps(kwargs))
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
        content = ""
        if result.content:
            content = json.loads(result.content)
        logger.error(result.content)
        if "is not a valid IP for the specified subnet" in content.get("NeutronError").get("message"):
            return fail("实例IP不在子网网段内")
        return fail("操作失败")


def request_put(url, headers, **kwargs):
    try:
        result = requests.put(url, verify=False, headers=headers, data=json.dumps(kwargs))
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    if result.status_code < 300:
        return success()
    else:
        logger.error(result.content)
        return fail("操作失败")


def request_delete(url, headers):
    try:
        result = requests.delete(url, verify=False, headers=headers)
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    if result.status_code < 300:
        return success()
    else:
        if not result.content:
            return fail("操作失败")
        content = json.loads(result.content)
        logger.error(content)
        return fail(content.get("message"))


def request_optional_params(param_list, kwargs, body):
    for param in param_list:
        if param in kwargs:
            body[param] = kwargs[param]

    return body


def request_optional_params_url(optional_par, **kwargs):
    """处理路径参数"""
    par_list = [f"{key}={kwargs[key]}" for key in optional_par if key in kwargs]
    return "&".join(par_list)


def check_must_parameters(par_list, **kwargs):
    """检验必传参数"""
    for key in par_list:
        if key not in kwargs:
            raise ValueError(f"need parameter {key}")


class FormatResource:
    """
    资源数据格式化类
    """

    def __init__(self):
        pass

    @staticmethod
    def format_domain(object_json, **kwargs):
        return Domain(
            id=object_json.get("id", ""),
            name=object_json.get("name", ""),
            platform_type=CloudType.FUSIONCLOUD.value,
            enabled=object_json.get("enabled", True),
            description=object_json.get("description", ""),
            extra={},
        ).to_dict()

    @staticmethod
    def format_project(object_json, **kwargs):
        return Project(
            id=object_json.get("id", ""),
            name=object_json.get("name", ""),
            platform_type=CloudType.FUSIONCLOUD.value,
            enabled=object_json.get("enabled", True),
            description=object_json.get("description", ""),
            extra={},
        ).to_dict()

    @staticmethod
    def format_region(object_json, **kwargs):
        return Region(
            id=object_json.get("id", ""),
            name=object_json.get("locales").get("zh-cn"),
            platform_type=CloudType.FUSIONCLOUD.value,
            extra={
                "cloud_infras": object_json.get("cloud_infras", ""),
                "description": object_json.get("description", ""),
                "parent_region_id": object_json.get("parent_region_id", ""),
            },
        ).to_dict()

    @staticmethod
    def format_zone(object_json, **kwargs):
        return Zone(
            id=object_json.get("zoneName"),
            name=object_json.get("zoneName"),
            platform_type=CloudType.FUSIONCLOUD.value,
            extra={},
        ).to_dict()

    @staticmethod
    def format_flavor(object_json, **kwargs):
        return InstanceType(
            resource_id=object_json.get("id", ""),
            resource_name=object_json.get("name", ""),
            # platform_type=CloudType.FUSIONCLOUD.value,
            region=kwargs.get("region", ""),
            extra={},
        ).to_dict()

    @staticmethod
    def format_server(object_json, **kwargs):
        flavor_obj = None
        if object_json.get("flavor"):
            flavor_obj = {"id": object_json.get("flavor").get("id")}
        image_obj = None
        if object_json.get("image"):
            image_obj = {"id": object_json.get("image").get("id")}

        nic_list = []
        inner_ip_list = []
        out_ip_list = []
        for k, v in object_json.get("addresses").items():
            nic_obj = {"name": k}
            for n in v:
                nic_obj.update(
                    {
                        "type": n["OS-EXT-IPS:type"],
                        "version": n["version"],
                        "ip": n["addr"],
                        "mac": n["OS-EXT-IPS-MAC:mac_addr"],
                    }
                )
                if n["OS-EXT-IPS:type"] == "fixed":
                    inner_ip_list.append(n["addr"])
                else:
                    out_ip_list.append(n["floating"])
            nic_list.append(nic_obj)
        mem = 0
        vcpus = 0
        vm_config = object_json.get("metadata").get("cascaded.instance_extrainfo").split(",")
        for i in vm_config:
            detail = i.split(":")
            if detail[0] == "current_mem":
                mem = int(detail[1])
            if detail[0] == "current_cpu":
                vcpus = int(detail[1])
        return VM(
            id=object_json.get("id", ""),
            name=object_json.get("name", ""),
            status=handle_vm_status(object_json.get("status", "")),
            platform_type=CloudType.FUSIONCLOUD.value,
            vcpus=vcpus,
            mem=mem,
            uuid=object_json.get("id", ""),
            flavor_info=flavor_obj,
            image_info=image_obj,
            inner_ip=inner_ip_list,
            public_ip=out_ip_list,
            nic_info=nic_list,
            disk_info=object_json.get("os-extended-volumes:volumes_attached", []),
            created_time=object_json.get("created")[:19].replace("T", " "),
            updated_time=object_json.get("updated")[:19].replace("T", " "),
            security_group_info=object_json.get("security_groups"),
            region_info={"id": kwargs.get("region")},
            region_id=kwargs.get("region"),
            zone_id=object_json.get("OS-EXT-AZ:availability_zone", ""),
            zone_info={"id": object_json.get("OS-EXT-AZ:availability_zone", "")},
            project_info={"id": kwargs.get("project_id")},
            extra={},
        ).to_dict()

    @staticmethod
    def format_image(object_json, **kwargs):
        return Image(
            id=object_json.get("id", ""),
            name=object_json.get("name", ""),
            platform_type=CloudType.FUSIONCLOUD.value,
            image_size=str(round(object_json.get("size", 0) / 1073741824, 2)),
            status=handle_image_status(object_json.get("status", "")),
            image_platform=object_json.get("__os_version", ""),
            image_type="私有",
            tags=object_json.get("tags", []),
            description=object_json.get("describe", ""),
            created_time=object_json.get("created_at", ""),
            updated_time=object_json.get("updated_at", ""),
            os_arch="",
            os_bit=object_json.get("__os_bit", ""),
            os_type=object_json.get("__os_type", ""),
            project_info={"id": kwargs.get("project_id")},
            zone_info={},
            visibility="",
            region_info={"id": kwargs.get("region")},
            extra={},
        ).to_dict()

    @staticmethod
    def format_subnet(object_json, **kwargs):
        return Subnet(
            id=object_json.get("id", ""),
            name=object_json.get("name", ""),
            platform_type=CloudType.FUSIONCLOUD.value,
            vpc_id=object_json.get("network_id", ""),
            status=SubnetStatus.AVAILABLE.value,
            network_addr=object_json.get("cidr", ""),
            available_ip_address_count=len(IPy.IP(object_json.get("cidr", ""))),
            gateway_ip=object_json.get("gateway_ip", ""),
            dns_list=object_json.get("dns_nameservers", ""),
            created_time=object_json.get("created_at", ""),
            updated_time=object_json.get("updated_at", ""),
            description=object_json.get("description", ""),
            region_info={"id": kwargs.get("region")},
            project_info={"id": kwargs.get("project_id")},
            zone_info={},
            extra={},
        ).to_dict()

    @staticmethod
    def format_volume(object_json, **kwargs):
        is_attached = False
        server_id = ""
        disk_type = "数据盘"
        if object_json.get("bootable") == "true":
            disk_type = "系统盘"
        attachments = object_json.get("attachments")
        if len(attachments) > 0:
            is_attached = True
            server_id = attachments[0].get("server_id")
        return Disk(
            id=object_json.get("id", ""),
            name=object_json.get("name", ""),
            platform_type=CloudType.FUSIONCLOUD.value,
            disk_size=object_json.get("size", ""),
            device_type=object_json.get("volume_type", ""),  # 无法获取到中文的接口
            is_attached=is_attached,
            status=handle_volume_status(object_json.get("status", "")),
            disk_type=disk_type,
            encrypted=object_json.get("encrypted"),
            snapshot_info=[],
            description=object_json.get("description", ""),
            tags=[],
            disk_format="",
            charge_type="",
            end_time="",
            server_id=server_id,
            project_info={"id": kwargs.get("project_id")},
            region_info={"id": kwargs.get("region")},
            zone_id=object_json.get("availability_zone", ""),
            zone_name=object_json.get("availability_zone", ""),
            created_time=object_json.get("created_at")[:19].replace("T", " "),
            updated_time=object_json.get("updated_at")[:19].replace("T", " "),
            extra={},
        ).to_dict()

    @staticmethod
    def format_volume_type(object_json, **kwargs):
        return {
            "extra_specs": {
                "volume_backend_name": object_json.get("volume_backend_name"),
                "availability-zone": object_json.get("availability-zone"),
            },
            "name": object_json.get("name", "未命名"),
            "qos_specs_id": object_json.get("qos_specs_id", ""),
            "id": object_json.get("id"),
            "is_public": object_json.get("is_public", True),
            "description": object_json.get("description", ""),
        }

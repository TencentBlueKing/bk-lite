# -*- coding: UTF-8 -*-
import base64
import datetime
import hmac
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from hashlib import sha256

import requests

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.constant import CloudResourceType, CloudType
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.cloud_apis.resource_apis.utils import fail, success
from core.logger import logger



class CwQingCloudPrivate(object):
    """
    通过该类创建QingCloud的Client实例，调用QingCloudapi接口
    """

    def __init__(self, username, password, region, host="", zone="", **kwargs):
        """
         初始化方法，创建Client实例。在创建Client实例时，您需要获取Region ID、AccessKey ID和AccessKey Secret
        :param secret_id:
        :param secret_key:
        :param region_id:
        :param kwargs:
        """
        self.access_key_id = username
        self.secret_access_key = password
        self.host = host
        self.port = kwargs.pop("port", None)
        self.region = region
        self.zone = zone
        self.signature_method = "HmacSHA256"  # 签名所用哈希算法，目前支持 HmacSHA256 和 HmacSHA1
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "version" not in kwargs:
            self.version = "1"

    def __getattr__(self, item):
        """
        private方法，返回对应的接口类
        """
        return QingCloudPrivate(
            name=item,
            host=self.host,
            access_key_id=self.access_key_id,
            secret_access_key=self.secret_access_key,
            region=self.region,
            zone=self.zone,
        )


class QingCloudPrivate(PrivateCloudManage):
    """
    QingCloud接口类
    """

    def __init__(self, name, host, access_key_id, secret_access_key, region, zone):
        """
        初始化方法
        """
        self.protocol = "http"
        self.host = host
        self.name = name
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self.zone = zone
        self.cloud_type = CloudType.QINGCLOUDPRIVATE.value
        self.resource_type_dict = {
            "network": CloudResourceType.VPC.value,
            "volume": CloudResourceType.DISK.value,
            "server": CloudResourceType.VM.value,
            "security_group": CloudResourceType.SECURITY_GROUP.value,
            "subnet": CloudResourceType.SUBNET.value,
            "security_group_rules": CloudResourceType.SECURITY_GROUP_RULE.value,
            "MySQL": CloudResourceType.MARIADB.value,
            "Redis": CloudResourceType.REDIS.value,
            "load_balancer": CloudResourceType.LOAD_BALANCER.value,
            "load_balancer_listener": CloudResourceType.LISTENER.value,
            "region": CloudResourceType.REGION.value,
            "zone": CloudResourceType.ZONE.value,
            "image": CloudResourceType.IMAGE.value,
        }
        self.resource_type_set = {
            "network": "router_set",
            "volume": "volume_set",
            "server": "instance_set",
            "security_group": "security_group_set",
            "subnet": "vxnet_set",
            "security_group_rules": "security_group_rule_set",
            "MySQL": "rdb_set",
            "Redis": "cache_set",
            "load_balancer": "loadbalancer_set",
            "load_balancer_listener": "loadbalancer_listener_set",
            "region": "zone_set",
            "zone": "zone_set",
            "image": "image_set",
        }

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(**kwargs)

    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        connection_result = self.list_regions()
        return {"result": connection_result["result"]}

    def list_regions(self, *args, **kwargs):
        action = "DescribeZones"
        result = self.getVhost(action, "region", **kwargs)
        return result

    def list_zones(self, *args, **kwargs):
        action = "DescribeZones"
        result = self.getVhost(action, "zone", **kwargs)
        return result

    def create_vm(self, **kwargs):
        # kwargs为参数
        action = "RunInstances"
        return self.operate_resource(action, **kwargs)

    def list_vms(self, ids=None, *args, **kwargs):
        if ids:
            for idx, instance_id in enumerate(ids):
                kwargs[f"instances.{idx+1}"] = instance_id
        action = "DescribeInstances"
        result = self.getVhost(action, "server", **kwargs)
        return result

    def list_images(self, id=None, **kwargs):
        kwargs["provider"] = "system"
        action = "DescribeImages"
        result = self.getVhost(action, "image", **kwargs)
        return result

    def list_disks(self, *args, **kwargs):
        action = "DescribeVolumes"
        result = self.getVhost(action, "volume", **kwargs)
        return result

    def list_vpcs(self, *args, **kwargs):
        action = "DescribeRouters"
        result = self.getVhost(action, "network", **kwargs)
        return result

    def list_subnets(self, *args, **kwargs):
        action = "DescribeVxnets"
        result = self.getVhost(action, "subnet", **kwargs)
        return result

    def list_security_groups(self, *args, **kwargs):
        action = "DescribeSecurityGroups"
        result = self.getVhost(action, "security_group", **kwargs)
        return result

    def list_security_group_rules(self, *args, **kwargs):
        action = "DescribeSecurityGroupRules"
        result = self.getVhost(action, "security_group_rules", **kwargs)
        return result

    def list_mysql(self, *args, **kwargs):
        action = "DescribeRDBs"
        result = self.getVhost(action, "MySQL", **kwargs)
        return result

    def list_redis(self, *args, **kwargs):
        action = "DescribeCaches"
        result = self.getVhost(action, "Redis", **kwargs)
        return result

    def list_load_balancers(self, *args, **kwargs):
        action = "DescribeLoadBalancers"
        result = self.getVhost(action, "load_balancer", **kwargs)
        return result

    def list_listeners(self, *args, **kwargs):
        action = "DescribeLoadBalancerListeners"
        result = self.getVhost(action, "load_balancer_listener", **kwargs)
        return result

    # *************************** tool *****************************

    def postResust(self, iassurl):
        res = requests.get(url=iassurl, verify=False)
        return res.json()

    def operate_resource(self, action, **kwargs):
        iaas_url = self.signature_url(action, **kwargs)
        try:
            result = self.postResust(iaas_url)
        except Exception as e:
            logger.exception(e)
            return fail("请求异常")
        if result["ret_code"] == 0:
            return success(result)
        else:
            logger.error(result.get("message"))
            return fail(f"调用接口{action}失败: {result.get('message')}")

    def getVhost(self, action, resource_type, **kwargs):
        page = 1
        format_type = self.resource_type_dict.get(resource_type, resource_type)
        resource_set = self.resource_type_set.get(resource_type, f"{resource_type}_set")
        data = []
        kwargs["limit"] = 50
        kwargs["offset"] = 50 * (page - 1)
        iaas_url = self.signature_url(action, **kwargs)
        result = self.postResust(iaas_url)
        if result["ret_code"] == 0:
            total_count = result.get("total_count", 0)
            count = len(result.get(resource_set, []))
            data.extend(result.get(resource_set, []))
        else:
            logger.error(f"调用{action}失败：{result}")
            total_count = 0
            count = 0
        # 分页查询
        while count < total_count:
            page += 1
            kwargs["offset"] = 50 * (page - 1)
            iaas_url = self.signature_url(action, **kwargs)
            result = self.postResust(iaas_url)
            if result["ret_code"] == 0:
                count += len(result.get(resource_set, []))
                data.extend(result.get(resource_set, []))
            else:
                logger.error(f"调用{action}分页失败：page：{page}，error:{result}")
                break
        format_method = get_format_method(self.cloud_type, format_type, region_id=self.region)
        resource_id_set = set()
        return_data = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            i_data = format_method(i, **kwargs)
            if i_data.get("resource_id") in resource_id_set:
                continue
            return_data.append(i_data)
            resource_id_set.add(i_data.get("resource_id"))
        return success(return_data)

    @staticmethod
    def sort_value(old_dict):
        items = sorted(old_dict.items())
        new_dict = OrderedDict()
        for item in items:
            new_dict[item[0]] = old_dict[item[0]]
        return new_dict

    def signature_url(self, action, **kwargs):
        od = OrderedDict()
        od["access_key_id"] = self.access_key_id
        od["action"] = action
        od["signature_method"] = "HmacSHA256"
        od["signature_version"] = 1
        time_stamp = datetime.datetime.utcnow()
        time_stamp = datetime.datetime.strftime(time_stamp, "%Y-%m-%dT%H:%M:%SZ")
        od["time_stamp"] = time_stamp
        od["version"] = 1
        if self.region:
            od["zone"] = self.region
        for k, v in kwargs.items():
            od[k] = v
        od = self.sort_value(od)
        data = urllib.parse.urlencode(od)
        string_to_sign = "GET" + "\n" + "/iaas/" + "\n" + data
        h = hmac.new(self.secret_access_key.encode(), digestmod=sha256)
        h.update(string_to_sign.encode())
        sign = base64.b64encode(h.digest()).strip()
        signature = urllib.parse.quote_plus(sign)
        iaas_url = f"{self.protocol}://{self.host}/iaas/" + "?" + data + "&signature=" + signature
        return iaas_url

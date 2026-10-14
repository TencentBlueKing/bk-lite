# -*- coding: UTF-8 -*-
import copy
import datetime
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import oss2
import pytz
from alibabacloud_alb20200616 import models as alb_20200616_models
from alibabacloud_alb20200616.client import Client as Alb20200616Client
from alibabacloud_alidns20150109 import models as alidns_20150109_models
from alibabacloud_alidns20150109.client import Client as Alidns20150109Client
from alibabacloud_alikafka20190916 import models as alikafka_20190916_models
from alibabacloud_alikafka20190916.client import Client as alikafka20190916Client
from alibabacloud_cas20200407 import models as cas_20200407_models
from alibabacloud_cas20200407.client import Client as Cas20200407Client
from alibabacloud_cdn20180510 import models as cdn_20180510_models
from alibabacloud_cdn20180510.client import Client as Cdn20180510Client
from alibabacloud_cs20151215 import models as cs20151215_models
from alibabacloud_cs20151215.client import Client as CS20151215Client
from alibabacloud_dds20151201 import models as dds_20151201_models
from alibabacloud_dds20151201.client import Client as Dds20151201Client
from alibabacloud_domain20180129 import models as domain_20180129_models
from alibabacloud_domain20180129.client import Client as Domain20180129Client
from alibabacloud_mse20190531 import models as mse20190531_models
from alibabacloud_mse20190531.client import Client as mse20190531Client
from alibabacloud_nas20170626 import models as nas20170626_models
from alibabacloud_nas20170626.client import Client as NAS20170626Client
from alibabacloud_oss20190517 import models as oss_20190517_models
from alibabacloud_oss20190517.client import Client as Oss20190517Client
from alibabacloud_r_kvstore20150101 import models as r_kvstore_20150101_models
from alibabacloud_r_kvstore20150101.client import Client as R_kvstore20150101Client
from alibabacloud_rds20140815 import models as rds_20140815_models
from alibabacloud_rds20140815.client import Client as Rds20140815Client
from alibabacloud_slb20140515 import models as slb_20140515_models
from alibabacloud_slb20140515.client import Client as Slb20140515Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_vpc20160428 import models as vpc_20160428_models
from alibabacloud_vpc20160428.client import Client as Vpc20160428Client  # noqa
from alibabacloud_waf_openapi20211001 import models as waf_openapi_20211001_models
from alibabacloud_waf_openapi20211001.client import Client as WafOpenapi20211001Client
from aliyunsdkbssopenapi.request.v20171214 import QueryAccountBalanceRequest
from aliyunsdkcms.request.v20190101 import DescribeMetricListRequest
from aliyunsdkcore import client
from aliyunsdkcore.request import CommonRequest
from aliyunsdkdds.request.v20151201.DescribeAvailableResourceRequest import (
    DescribeAvailableResourceRequest as dds_avail_resource,
)
from aliyunsdkecs.request.v20140526 import (
    ApplyAutoSnapshotPolicyRequest,
    AttachDiskRequest,
    AuthorizeSecurityGroupEgressRequest,
    AuthorizeSecurityGroupRequest,
    CancelAutoSnapshotPolicyRequest,
    CreateDiskRequest,
    CreateImageRequest,
    CreateSecurityGroupRequest,
    CreateSnapshotGroupRequest,
    CreateSnapshotRequest,
    DeleteDiskRequest,
    DeleteImageRequest,
    DeleteInstanceRequest,
    DeleteSecurityGroupRequest,
    DeleteSnapshotRequest,
    DescribeAutoSnapshotPolicyExRequest,
    DescribeAvailableResourceRequest,
    DescribeDisksRequest,
    DescribeImagesRequest,
    DescribeInstancesRequest,
    DescribeInstanceTypeFamiliesRequest,
    DescribeInstanceTypesRequest,
    DescribeInstanceVncUrlRequest,
    DescribePriceRequest,
    DescribeRegionsRequest,
    DescribeResourcesModificationRequest,
    DescribeSecurityGroupAttributeRequest,
    DescribeSecurityGroupsRequest,
    DescribeSnapshotsRequest,
    DescribeZonesRequest,
    DetachDiskRequest,
    JoinSecurityGroupRequest,
    LeaveSecurityGroupRequest,
    ListTagResourcesRequest,
    ModifyInstanceAttributeRequest,
    ModifyInstanceSpecRequest,
    ModifyPrepayInstanceSpecRequest,
    ModifySecurityGroupAttributeRequest,
    ModifySecurityGroupEgressRuleRequest,
    ModifySecurityGroupRuleRequest,
    ReActivateInstancesRequest,
    RebootInstanceRequest,
    RenewInstanceRequest,
    ResetDiskRequest,
    ResizeDiskRequest,
    RevokeSecurityGroupEgressRequest,
    RevokeSecurityGroupRequest,
    RunInstancesRequest,
    StartInstanceRequest,
    StopInstanceRequest,
    TagResourcesRequest,
    UntagResourcesRequest,
)
from aliyunsdknas.request.v20170626 import CreateFileSystemRequest, DeleteFileSystemRequest, DescribeFileSystemsRequest
from aliyunsdkr_kvstore.request.v20150101.DescribeAvailableResourceRequest import (
    DescribeAvailableResourceRequest as kvs_avail_resource,
)
from aliyunsdkslb.request.v20140515 import DescribeHealthStatusRequest, DescribeServerCertificatesRequest
from aliyunsdkvpc.request.v20160428 import (  # DescribeEipAddressesRequest,
    AllocateEipAddressRequest,
    AssociateEipAddressRequest,
    AssociateRouteTableRequest,
    CreateRouteTableRequest,
    CreateVpcRequest,
    CreateVSwitchRequest,
    DeleteRouteEntryRequest,
    DeleteRouteTableRequest,
    DeleteVpcRequest,
    DeleteVSwitchRequest,
    DescribeRouteEntryListRequest,
    DescribeRouteTableListRequest,
    DescribeVpcsRequest,
    DescribeVSwitchesRequest,
    ModifyEipAddressAttributeRequest,
    ReleaseEipAddressRequest,
    UnassociateEipAddressRequest,
    UnassociateRouteTableRequest,
)
from six.moves import range
from Tea.core import TeaCore

from common.cmp.cloud_apis.cloud_object.base import Bucket
from common.cmp.cloud_apis.constant import CloudType
from common.cmp.cloud_apis.resource_apis.aliyun_dict import disk_category_dict, object_storage_type_dict
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.utils import (
from core.logger import logger

    convert_param_to_list,
    format_ali_bill_charge_mode,
    format_public_cloud_resource_type,
    generate_serial_number,
    set_dir_size,
)


RESOURCE_MAP = {
    "region": ("Regions", "Region"),
    "zone": ["Zones", "Zone"],
    "instance_type_family": ["InstanceTypeFamilies", "InstanceTypeFamily"],
    "instance_type": ["InstanceTypes", "InstanceType"],
    "vm": ["Instances", "Instance"],
    "tag": ["TagResources", "TagResource"],
    "snapshot": ["Snapshots", "Snapshot"],
    "image": ["Images", "Image"],
    "disk": ["Disks", "Disk"],
    "subnet": ["VSwitches", "VSwitch"],
    "vpc": ["Vpcs", "Vpc"],
    "eip": ["EipAddresses", "EipAddress"],
    "security_group": ["SecurityGroups", "SecurityGroup"],
    "security_group_rule": ["Permissions", "Permission"],
    "route_table": ["RouterTableList", "RouterTableListType"],
    "route_entry": ["RouteEntrys", "RouteEntry"],
    "auto_snapshot_policy": ["AutoSnapshotPolicies", "AutoSnapshotPolicy"],
    "load_balancer": ["LoadBalancers", "LoadBalancer"],
    "listener": ["Listeners", "Listener"],
    "vserver_groups": ["VServerGroups", "VServerGroup"],
    "server_certificate": ["ServerCertificates", "ServerCertificate"],
    "file_system": ["FileSystems", "FileSystem"],
    "rule": ["Rules", "Rule"],
    "domain": ["Domains", "Domain"],
}


def local_to_utc(local_time_str, local_tz="Asia/Shanghai", fmt="%Y-%m-%d %H:%M:%S", utc_fmt="%Y-%m-%dT%H:%M:%SZ"):
    # 将字符串形式的时间转换为datetime对象
    local_time = datetime.datetime.strptime(local_time_str, fmt)

    # 将本地时间转换为UTC时间
    local_tz = pytz.timezone(local_tz)
    local_time = local_tz.localize(local_time)
    utc_time = local_time.astimezone(pytz.UTC)

    # 将UTC时间转换为字符串形式
    utc_time_str = utc_time.strftime(utc_fmt)

    return utc_time_str


def utc_to_local(utc_time_str, local_tz="Asia/Shanghai", fmt="%Y-%m-%d %H:%M:%S", utc_fmt="%Y-%m-%dT%H:%M:%SZ"):
    # 将字符串形式的UTC时间转换为datetime对象
    utc_time = datetime.datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ")

    # 将UTC时间转换为本地时间
    utc_time = pytz.UTC.localize(utc_time)
    local_time = utc_time.astimezone(pytz.timezone(local_tz))

    # 将本地时间转换为字符串形式
    local_time_str = local_time.strftime("%Y-%m-%d %H:%M:%S")

    return local_time_str


def dts_to_ts(dts_str, fmt="%Y-%m-%d %H:%M:%S"):
    """datetime把时间字符串转换为时间戳"""
    dts = datetime.datetime.strptime(dts_str, fmt)
    ts = int(time.mktime(dts.timetuple()))
    return ts


def utc_to_ts(utc_time_str, local_tz="Asia/Shanghai", fmt="%Y-%m-%d %H:%M:%S", utc_fmt="%Y-%m-%dT%H:%M:%SZ"):
    """UTC时间字符串转换为时间戳"""
    return dts_to_ts(utc_to_local(utc_time_str, local_tz, fmt, utc_fmt), fmt)


def patch_oss_models():
    def patch_from_map(self, m: dict = None):
        m = m or dict()
        self.buckets = []
        if m.get("Buckets", {}).get("Bucket") is not None:
            for k in m.get("Buckets", {}).get("Bucket"):
                temp_model = oss_20190517_models.Bucket()
                self.buckets.append(temp_model.from_map(k))
        if m.get("Owner") is not None:
            temp_model = oss_20190517_models.Owner()
            self.owner = temp_model.from_map(m["Owner"])
        return self

    old_bucket_init = oss_20190517_models.BucketInfoBucket.__init__
    old_bucket_from_map = oss_20190517_models.BucketInfoBucket.from_map
    old_bucket_to_map = oss_20190517_models.BucketInfoBucket.to_map

    def bucket_info_init(self, *args, **kwargs):
        old_bucket_init(self, *args, **kwargs)
        self.block_public_access = kwargs.get("BlockPublicAccess")

    def bucket_info_from_map(self, m: dict = None):
        m = m or dict()
        self = old_bucket_from_map(self, m)
        if m.get("BlockPublicAccess") is not None:
            self.block_public_access = m.get("BlockPublicAccess")
        return self

    def bucket_info_to_map(self):
        result = old_bucket_to_map(self)
        if self.block_public_access is not None:
            result["BlockPublicAccess"] = self.block_public_access
        return result

    oss_20190517_models.ListBucketsResponseBody.from_map = patch_from_map
    oss_20190517_models.BucketInfoBucket.__init__ = bucket_info_init
    oss_20190517_models.BucketInfoBucket.from_map = bucket_info_from_map
    oss_20190517_models.BucketInfoBucket.to_map = bucket_info_to_map


patch_oss_models()


class CwAliyun(object):
    """
    阿里云组件类,通过该类创建阿里云的Client实例，调用阿里云api接口
    """

    def __init__(self, access_key, access_secret, region_id, host="", **kwargs):
        """
        初始化方法，创建Client实例。在创建Client实例时，您需要获取Region ID、AccessKey ID和AccessKey Secret
        :param access_key:
        :param access_secret:
        :param region_id:
        :param kwargs:
        """
        self.AccessKey = access_key
        self.AccessSecret = access_secret
        self.RegionId = "cn-hangzhou" if not region_id else region_id
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.client = client.AcsClient(
            self.AccessKey, self.AccessSecret, self.RegionId, timeout=30, connect_timeout=30, max_retry_time=3
        )
        self.auth = oss2.Auth(self.AccessKey, self.AccessSecret)
        self.auth_config = open_api_models.Config(access_key_id=self.AccessKey, access_key_secret=self.AccessSecret)

    def __getattr__(self, item):
        """
        private方法，返回对应的阿里云接口类
        :param item:
        :return:
        """
        return Aliyun(
            aliyun_client=self.client, name=item, region=self.RegionId, auth=self.auth, auth_config=self.auth_config
        )


class Aliyun(object):
    """
    阿里云接口类。使用阿里云开发者工具套件（SDK），并进行封装，访问阿里云服务
    """

    def __init__(self, aliyun_client, name, region, auth, auth_config):
        """
        初始化方法
        :param aliyun_client:
        :param name:
        :param region:
        """
        self.client = aliyun_client
        self.name = name
        self.RegionId = region
        self.auth = auth
        self.cloud_type = CloudType.ALIYUN.value
        self.auth_config = auth_config
        domain_config = copy.deepcopy(auth_config)
        domain_config.endpoint = "domain.aliyuncs.com"
        self.domain_client = Domain20180129Client(domain_config)
        dns_config = copy.deepcopy(auth_config)
        dns_config.endpoint = f"alidns.{region}.aliyuncs.com"
        self.dns_client = Alidns20150109Client(dns_config)
        cdn_config = copy.deepcopy(auth_config)
        cdn_config.endpoint = "cdn.aliyuncs.com"
        self.cdn_client = Cdn20180510Client(cdn_config)
        waf_config = copy.deepcopy(auth_config)
        waf_config.endpoint = f"wafopenapi.{region}.aliyuncs.com"
        self.waf_client = WafOpenapi20211001Client(waf_config)
        cas_config = copy.deepcopy(auth_config)
        cas_config.endpoint = "cas.aliyuncs.com"
        self.cas_client = Cas20200407Client(cas_config)
        rds_config = copy.deepcopy(auth_config)
        rds_config.endpoint = "rds.aliyuncs.com"
        self.rds_client = Rds20140815Client(rds_config)
        kvs_config = copy.deepcopy(auth_config)
        kvs_config.endpoint = "r-kvstore.aliyuncs.com"
        self.kvs_client = R_kvstore20150101Client(kvs_config)
        oss_config = copy.deepcopy(auth_config)
        oss_config.endpoint = f"oss-{region}.aliyuncs.com"
        self.oss_client = Oss20190517Client(oss_config)
        dds_config = copy.deepcopy(auth_config)
        dds_config.endpoint = "mongodb.aliyuncs.com"
        self.dds_client = Dds20151201Client(dds_config)
        kafka_config = copy.deepcopy(auth_config)
        kafka_config.endpoint = f"alikafka.{region}.aliyuncs.com"
        self.kafka_client = alikafka20190916Client(kafka_config)
        slb_config = copy.deepcopy(auth_config)
        slb_config.endpoint = f"slb.{region}.aliyuncs.com"
        self.slb_client = Slb20140515Client(slb_config)
        cs_config = copy.deepcopy(auth_config)
        cs_config.endpoint = f"cs.{region}.aliyuncs.com"
        self.cs_client = CS20151215Client(cs_config)
        vpc_config = copy.deepcopy(auth_config)
        vpc_config.endpoint = "vpc.aliyuncs.com"
        self.vpc_client = Vpc20160428Client(vpc_config)
        mse_config = copy.deepcopy(auth_config)
        mse_config.endpoint = f"mse.{region}.aliyuncs.com"
        self.mse_client = mse20190531Client(mse_config)
        alb_config = copy.deepcopy(auth_config)
        alb_config.endpoint = f"alb.{region}.aliyuncs.com"
        self.alb_client = Alb20200616Client(alb_config)
        nas_config = copy.deepcopy(auth_config)
        nas_config.endpoint = f"nas.{region}.aliyuncs.com"
        self.nas_client = NAS20170626Client(nas_config)

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    # ***********************  common公用方法  ******************************************
    def _get_result(self, request, flag=False):
        """
        发送云接口访问请求，并可获取返回值
        :param request:
        :param flag: 类型：Boolean。描述：为True时获取返回参数，为False时无返回参数。
        :return:
        """
        request.set_accept_format("json")
        if flag:
            ali_request = self.client.do_action_with_exception(request)
            ali_result = json.loads(ali_request)
            return ali_result
        else:
            self.client.do_action_with_exception(request)

    def _add_required_params(self, request, params_dict):
        """
        通过add_query_param付费设置参数
        :param request:
        :param params_dict:  (dict): k是参数名，v是参数值
        :return:
        """
        return add_required_params(request, params_dict)

    def _get_result_c(self, request, flag=False):
        """CommonRequest类request，发送云接口访问请求，并可获取返回值"""
        if flag:
            ali_request = self.client.do_action(request)
            ali_result = json.loads(ali_request)
            return ali_result
        else:
            self.client.do_action(request)

    def _handle_list_request(self, resource, request):
        """
        请求资源列表公用方法
        Args:
            resource (str): 资源名  region|zone
            request (request): 阿里云sdk生成的reques
        Returns:

        """
        try:
            ali_result = self._get_result(request, True)
        except Exception as e:
            logger.exception("获取阿里云{}调用接口失败{}".format(resource, e))
            return {"result": False, "message": str(e)}

        data = self._format_resource_result(resource, ali_result)
        return {"result": True, "data": data}

    def _handle_list_request_with_page(self, resource, request):
        """
        获取有分页的资源数据
        Args:
            resource (str):
            request (client of sdk):
        Returns:

        """
        page_number = 1
        page_size = 50
        try:
            request.set_PageSize(page_size)
            request.set_PageNumber(page_number)
            ali_response = self._get_result(request, True)
            total_count = ali_response.get("TotalCount", 0)
            page = total_count // 50 if total_count % 50 == 0 else total_count // 50 + 1
            key1, key2 = RESOURCE_MAP[resource]
            for i in range(page):
                request.set_PageNumber(str(i + 2))
                ali_res = self._get_result(request, True)
                ali_response[key1][key2].extend(ali_res[key1][key2])
        except Exception as e:
            logger.exception("获取阿里云资源{}调用接口失败{}".format(resource, e))
            return {"result": False, "message": str(e)}
        data = self._format_resource_result(resource, ali_response)
        return {"result": True, "data": data}

    def _handle_list_request_with_page_c(self, resource, request):
        """CommonRequest 获取有分页的资源数据"""
        page_number = 1
        page_size = 50
        try:
            request = self._add_required_params(request, {"PageNumber": page_number, "PageSize": page_size})
            ali_response = self._get_result_c(request, True)
            total_count = ali_response.get("TotalCount", 0)
            page = (total_count + page_size - 1) // page_size
            key1, key2 = RESOURCE_MAP[resource]
            for i in range(page):
                request = self._add_required_params(request, {"PageNumber": str(i + 2)})
                ali_res = self._get_result_c(request, True)
                ali_response[key1][key2].extend(ali_res[key1][key2])
        except Exception as e:
            logger.exception("获取阿里云资源{}调用接口失败{}".format(resource, e))
            return {"result": False, "message": str(e)}
        data = self._format_resource_result(resource, ali_response)
        return {"result": True, "data": data}

    def _handle_list_request_with_next_token(self, resource, request, **kwargs):
        """
        获取有分页的资源数据,根据NextToke获得下一页数据.
        :return:
        """
        list_optional_params = kwargs["list_optional_params"]
        key1, key2 = RESOURCE_MAP[resource]
        request = set_optional_params(request, list_optional_params, kwargs)
        ali_result = self._get_result(request, True)
        ali_result_flag = ali_result
        while ali_result_flag.get("NextToken", None):
            kwargs["NextToken"] = ali_result_flag["NextToken"]
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result_flag = self.client.do_action_with_exception(request)
            ali_result_flag = json.loads(ali_result_flag)
            ali_result[key1][key2].extend(ali_result_flag[key1][key2])
        data = self._format_resource_result(resource, ali_result)
        return {"result": True, "data": data}

    def __handle_list_request_with_next_token_c(self, resource, request):
        """CommonRequest获取有分页的资源数据,根据NextToke获得下一页数据."""
        ali_result = self._get_result_c(request, True)
        if not ali_result.get("TotalCount"):
            return {"result": True, "data": []}
        key1, key2 = RESOURCE_MAP[resource]
        if isinstance(ali_result[key1], list):
            ali_result[key1] = {key2: ali_result[key1]}
        ali_result_flag = ali_result
        while ali_result_flag.get("NextToken", None):
            request = add_required_params(request, {"NextToken": ali_result_flag["NextToken"]})
            ali_res = self._get_result_c(request, True)
            if isinstance(ali_result[key1], list):
                ali_result[key1][key2].extend(ali_res[key1])
            else:
                ali_res[key1] = {key2: ali_res[key1]}
                ali_result[key1][key2].extend(ali_res[key1][key2])
            ali_result_flag = ali_res
        data = self._format_resource_result(resource, ali_result)
        return {"result": True, "data": data}

    def _format_resource_result(self, resource_type, data, **kwargs):
        """
        格式化获取到的资源结果
        Args:
            resource_type (str): 资源类型名 如 region
            data (list or object): 待格式化的数据，

        Returns:

        """
        key1, key2 = RESOURCE_MAP[resource_type]
        data = data[key1][key2]
        if not data:
            return []
        kwargs.update({"region_id": self.RegionId})
        format_method = get_format_method(self.cloud_type, resource_type, **kwargs)
        if isinstance(data, list):
            return [format_method(i, **kwargs) for i in data if i]
        return [format_method(data)]

    def _set_price_params(self, **kwargs):
        """
        设置价格参数
        :param kwargs:
        :return:
        """
        request = DescribePriceRequest.DescribePriceRequest()
        request.add_query_param("RegionId", self.RegionId)
        if kwargs.get("Amount"):
            request.set_Amount(kwargs["Amount"])
        if kwargs.get("ImageId"):
            request.set_ImageId(kwargs["ImageId"])
        if kwargs.get("InstanceType"):
            request.set_InstanceType(kwargs["InstanceType"])
        if kwargs.get("ResourceType"):
            request.set_ResourceType(kwargs["ResourceType"])
        if kwargs.get("PriceUnit"):
            request.set_PriceUnit(kwargs["PriceUnit"])
        if kwargs.get("Period"):
            request.set_Period(kwargs["Period"])
        if kwargs.get("sys_category"):
            request.set_SystemDiskCategory(kwargs["sys_category"])
        if kwargs.get("sys_size"):
            request.set_SystemDiskSize(kwargs["sys_size"])
        if kwargs.get("datadisk"):
            for index, i in enumerate(kwargs["datadisk"]):
                if index < 4:
                    getattr(request, "set_DataDisk" + str(index + 1) + "Category")(i["data_category"])
                    getattr(request, "set_DataDisk" + str(index + 1) + "Size")(i["data_size"])
        request.set_accept_format("json")
        return request

    def _get_source_devices(self, **kwargs):
        """
        查询一块或多块您已经创建的块存储
        :param kwargs:
        :return:
        """
        request = DescribeDisksRequest.DescribeDisksRequest()
        return self._handle_list_request_with_page("disk", request)

    #  ********************************主机管理**********************************
    def list_regions(self, ids=None):
        """
        获取阿里云地域信息
        : ids (list): id列表
        :return:
        """
        request = DescribeRegionsRequest.DescribeRegionsRequest()
        return self._handle_list_request("region", request)

    def list_zones(self, ids=None, **kwargs):
        """
        获取阿里云可用区信息
        :param ids: (list of str) id列表
        :param kwargs:
        :return:
        """
        request = DescribeZonesRequest.DescribeZonesRequest()
        return self._handle_list_request("zone", request)

    def get_connection_result(self):
        """
        根据能否获取地域信息判断是否连接成功
        :return:
        """
        connection_result = self.list_regions()
        return {"result": connection_result["result"]}

    # TODO 和接口list_instance_type_families重复。暂时不清楚作用，后续确定用途后需要修改
    def get_spec_type(self, **kwargs):
        """
        获取实例规格类型
        :param kwargs:
        :return:
        """
        request = DescribeInstanceTypeFamiliesRequest.DescribeInstanceTypeFamiliesRequest()
        request.set_accept_format("json")
        ali_response = self.client.do_action_with_exception(request)
        ali_result = json.loads(ali_response)
        return_data = []
        type_list = []
        for i in ali_result["InstanceTypeFamilies"]["InstanceTypeFamily"]:
            if i["InstanceTypeFamilyId"] not in type_list:
                return_data.append({"id": i["InstanceTypeFamilyId"], "name": i["InstanceTypeFamilyId"]})
                type_list.append(i["InstanceTypeFamilyId"])
        return {"result": True, "data": return_data}

    # TODO 和接口list_instance_types重复 后续确认作用后修改
    def get_spec_list(self, **kwargs):
        """
        获取实例规格列表
        :param kwargs:
        :return:
        """
        request = DescribeInstanceTypesRequest.DescribeInstanceTypesRequest()
        request.set_InstanceTypeFamily(kwargs["spec"])
        request.set_accept_format("json")
        ali_response = self.client.do_action_with_exception(request)
        ali_result = json.loads(ali_response)
        res_data = []
        for i in ali_result["InstanceTypes"]["InstanceType"]:
            i["id"] = i["text"] = i["InstanceTypeId"]
            i["InstanceType"] = i["id"]
            i["CPU"] = i["CpuCoreCount"]
            i["Memory"] = i["MemorySize"]
            res_data.append(i)
        return {"result": True, "data": res_data}

    def list_instance_type_families(self, ids=None, **kwargs):
        """
        查询云服务器ECS提供的实例规格族列表 不对应本地数据库
            SDk：
            仅返回InstanceTypeFamilyId  Generation 如
                {
                    "InstanceTypeFamilyId": "ecs.g6",
                    "Generation": "ecs-5"
                },
        :param ids: (list of str) 实例规格族系列信息 例如 ecs5
        :param kwargs:
        :return:
        """
        request = DescribeInstanceTypeFamiliesRequest.DescribeInstanceTypeFamiliesRequest()
        # 可以根据系列信息查询指定系列下的规格族列表 这里先简写只查第一个
        if ids:
            request.set_Generation(ids[0])
        res = self._handle_list_request("instance_type_family", request)
        if not res["result"]:
            return res
        # 去重
        return_data = []
        exist_type_set = set()
        for i in res["data"]:
            if i["resource_id"] not in exist_type_set:
                return_data.append(i)
                exist_type_set.add(i["resource_id"])
        return {"result": True, "data": return_data}

    def list_instance_types(self, ids=None, **kwargs):
        """
        查询云服务器ECS提供的所有实例规格的信息 可根据实例规格名  实例规格族名查询
        Args:
            ids (list of str): 实例规格名
            **kwargs ():
                InstanceTypeFamily (str): 实例规格族名

        Returns:

        """
        request = DescribeInstanceTypesRequest.DescribeInstanceTypesRequest()
        if "instance_type_family" in kwargs:
            # TODO 不确定传空是否可行 稍后测试
            request.set_InstanceTypeFamily(kwargs["instance_type_family"])
        return self._handle_list_request("instance_type", request)

    # TODO 价格模型使用 后续修改
    def get_storage_list(self, **kwargs):
        """
        获取存储信息列表
        :param kwargs:
        :return:
        """
        try:
            storage_list = [
                {"name": "普通云盘", "type": "cloud"},
                {"name": "高效云盘", "type": "cloud_efficiency"},
                {"name": "SSD云盘", "type": "cloud_ssd"},
            ]
            res_list = []
            for i in storage_list:
                kwargs["ResourceType"] = "disk"
                kwargs["datadisk"] = [{"data_category": i["type"], "data_size": 100}]
                request = self._set_price_params(**kwargs)
                ali_response = self.client.do_action_with_exception(request)
                ali_result = json.loads(ali_response)
                price = ali_result["PriceInfo"]["Price"]["TradePrice"]
                res_list.append({"price": round(float(price) * 24 * 30 / 100, 4), "name": i["name"], "type": i["type"]})
            return {"result": True, "data": res_list}
        except Exception as e:
            logger.exception("get_storage_list error")
            return {"result": False, "message": str(e)}

    # TODO 价格模型使用 后续修改
    def get_spec_price(self, **kwargs):
        """
        获取实例规格对应价格
        :param kwargs:
        :return:
        """
        try:
            kwargs["ResourceType"] = "instance"
            kwargs["Period"] = 1
            kwargs["PriceUnit"] = "Month"
            kwargs["InstanceType"] = kwargs["spec"]
            request = self._set_price_params(**kwargs)
            ali_response = self.client.do_action_with_exception(request)
            ali_result = json.loads(ali_response)
            price = ali_result["PriceInfo"]["Price"]["TradePrice"]
            return {"result": True, "data": price}
        except Exception as e:
            logger.exception("get_spec_price error")
            return {"result": False, "message": str(e)}

    def list_vms(self, ids=None, **kwargs):
        """
        获取一台或多台实例的详细信息
        Args:
            ids (list of str): 实例id列表
            **kwargs (): 其他筛选条件

        Returns:

        """
        request = DescribeInstancesRequest.DescribeInstancesRequest()
        # kwargs["PageNumber"] = 1
        # kwargs["PageSize"] = 50
        # todo 这里需要对应改前端传递参数
        if ids:
            ids = convert_param_to_list(ids)
            request.set_InstanceIds(json.dumps(ids))
        kwargs["request"] = request
        request = self._set_vm_info_params(**kwargs)
        return self._handle_list_request_with_page("vm", request)

    @classmethod
    def _set_vm_info_params(cls, **kwargs):
        """
        设置实例信息参数
        :param kwargs:
        :return:
        """
        if kwargs.get("request"):
            request = kwargs["request"]
        else:
            request = DescribeInstancesRequest.DescribeInstancesRequest()
        list_optional_params = [
            "VpcId",
            "VSwitchId",
            "VSwitchId",
            "InstanceType",
            "InstanceTypeFamily",
            "InstanceNetworkType",
            "PrivateIpAddresses",
            "ZoneId",
            "PublicIpAddresses",
            "InnerIpAddresses",
            "InstanceChargeType",
            "SecurityGroupId",
            "InternetChargeType",
            "InstanceName",
            "ImageId",
            "Tag.1.Key",
            "Tag.1.Value",
            "Tag.2.Key",
            "Tag.2.Value",
            "Status",
            "PageNumber",
            "PageSize",
        ]
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_accept_format("json")
        return request

    @classmethod
    def _set_create_vm_params(cls, **kwargs):
        """
        设置实例创建参数
        :param kwargs:
        :return:
        """
        request = RunInstancesRequest.RunInstancesRequest()
        request.set_ImageId(kwargs.get("ImageId"))
        request.set_InstanceType(kwargs.get("InstanceType"))
        request.set_SecurityGroupId(kwargs.get("SecurityGroupId"))
        request.set_VSwitchId(kwargs.get("VSwitchId"))
        list_optional_params = [
            "ZoneId",
            "InstanceName",
            "Description",
            "InternetChargeType",
            "InternetMaxBandwidthIn",
            "InternetMaxBandwidthOut",
            "HostName",
            "UniqueSuffix",
            "Password",
            "PasswordInherit",
            "SystemDiskCategory",
            "SystemDiskSize",
            "SystemDiskDiskName",
            "SystemDiskDescription",
            "SystemDiskPerformanceLevel",
            "DataDisks",
            "IoOptimized",
            "UserData",
            "KeyPairName",
            "RamRoleName",
            "Amount",
            "MinAmount",
            "AutoReleaseTime",
            "SpotStrategy",
            "SpotDuration",
            "SpotPriceLimit",
            "SpotInterruptionBehavior",
            "SecurityEnhancementStrategy",
            "Tags",
            "HpcClusterId",
            "DryRun",
            "DedicatedHostId",
            "LaunchTemplateId",
            "LaunchTemplateVersion",
            "ResourceGroupId",
            "Period",
            "PeriodUnit",
            "AutoRenew",
            "InstanceChargeType",
            "DeploymentSetId",
            "PrivateIpAddress",
            "CreditSpecification",
            "DeletionProtection",
            "Affinity",
            "Tenancy",
            "StorageSetId",
            "StorageSetPartitionNumber",
            "HttpEndpoint",
            "HttpTokens",
            "ClientToken",
            "LaunchTemplateName",
            "AutoRenewPeriod",
        ]
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_accept_format("json")
        return request

    def create_vm(self, **kwargs):
        """
        创建实例
        :param kwargs:参数，其中镜像ID，规格，安全组为必须
                      ImageId：镜像ID,类型：string。必选
                      ImageFamily：镜像族系名称，类型：string。
                      InstanceType：实例的资源规格。类型：string。必选
                      SecurityGroupId：指定新创建实例所属于的安全组ID。类型：string。必选
                      SecurityGroupIds：将实例同时加入多个安全组。类型：RepeatList。
                      VSwitchId：虚拟交换机ID。类型：string。必选
                      InstanceName：实例名称。类型：string。
                      Description：实例的描述。类型：string。
                      InternetMaxBandwidthIn：公网入带宽最大值，单位为Mbit/s。类型：Integer。
                      InternetMaxBandwidthOut：公网出带宽最大值，单位为Mbit/s。类型：Integer。
                      HostName：实例主机名称。类型：string。
                      UniqueSuffix：是否为HostName和InstanceName添加有序后缀。类型：Boolean
                      Password：实例的密码。类型：string。
                      PasswordInherit：是否使用镜像预设的密码。类型：Boolean。
                      ZoneId：实例所属的可用区ID。类型：string。
                      InternetChargeType：网络计费类型。取值范围：PayByBandwidth：按固定带宽计费；
                                                                PayByTraffic（默认）：按使用流量计费。类型：string。
                      SystemDiskSize：系统盘大小，单位为GiB。取值范围：20~500。类型：String。
                      SystemDiskCategory：系统盘的云盘种类。取值范围：cloud_efficiency：高效云盘
                                                                     cloud_ssd：SSD云盘
                                                                     cloud_essd：ESSD云盘
                                                                     cloud：普通云盘
                      SystemDiskDiskName：系统盘名称。类型：String。
                      SystemDiskDescription：系统盘的描述。类型：String。
                      SystemDiskPerformanceLevel：创建ESSD云盘作为系统盘使用时，设置云盘的性能等级。
                                                    取值范围：PL1（默认）：单盘最高随机读写IOPS 5万
                                                             PL2：单盘最高随机读写IOPS 10万
                                                             PL3：单盘最高随机读写IOPS 100万。类型：String。
                      SystemDiskAutoSnapshotPolicyId：系统盘采用的自动快照策略ID。类型：String。
                      DataDisks.N.Size：第n个数据盘的容量大小，N的取值范围为1~16，内存单位为GiB。类型：Integer。
                      DataDisks.N.SnapshotId：创建数据盘N使用的快照。类型：String。
                      DataDisks.N.Category：数据盘N的云盘种类。取值范围：cloud_efficiency：高效云盘
                                                                      cloud_ssd：SSD云盘
                                                                      ephemeral_ssd：本地SSD盘
                                                                      cloud_essd：ESSD云盘
                                                                      cloud：普通云盘。类型：String。
                      DataDisks.N.Encrypted：数据盘N是否加密。类型：String。
                      DataDisks.N.KMSKeyId：数据盘对应的KMS密钥ID。类型：String。
                      DataDisks.N.DiskName：数据盘名称。类型：String。
                      DataDisks.N.Description：数据盘的描述。类型：String。
                      DataDisks.N.Device：数据盘的挂载点。类型：String。
                      DataDisks.N.DeleteWithInstance：表示数据盘是否随实例释放。默认值：true。类型：Boolean。
                      DataDisks.N.PerformanceLevel：创建ESSD云盘作为数据盘使用时，设置云盘的性能等级。类型：String。
                      DataDisks.N.AutoSnapshotPolicyId：数据盘采用的自动快照策略ID。类型：String。
                      IoOptimized：是否为I/O优化实例。类型：String。
                      NetworkInterface.N.PrimaryIpAddress：添加一张辅助弹性网卡并设置主IP地址。类型：String。
                                                           默认值：从网卡所属的交换机网段中随机选择一个IP地址。
                      NetworkInterface.N.VSwitchId：辅助弹性网卡所属的虚拟交换机ID。类型：String。
                      NetworkInterface.N.SecurityGroupId：辅助弹性网卡所属的安全组ID。类型：String。默认值：实例所属的安全组。
                      NetworkInterface.N.SecurityGroupIds.N：将辅助弹性网卡同时加入多个安全组。类型：RepeatList。
                      NetworkInterface.N.NetworkInterfaceName：辅助弹性网卡名称。类型：String。
                      NetworkInterface.N.Description：辅助弹性网卡的描述。类型：String。
                      UserData：实例自定义数据。类型：String。
                      KeyPairName：密钥对名称。类型：String。
                      RamRoleName：实例RAM角色名称。类型：String。
                      Amount：指定创建ECS实例的数量。类型：Integer。
                      MinAmount：指定ECS实例最小购买数量。取值范围：1~100。类型：Integer。
                      AutoReleaseTime：按量付费实例的自动释放时间。类型：String。
                      SpotStrategy：按量实例的抢占策略。类型：String。
                      SpotDuration：抢占式实例的保留时长，单位为小时。类型：Integer。
                      SpotPriceLimit：设置实例的每小时最高价格。类型：Float。
                      SpotInterruptionBehavior：抢占实例中断模式。类型：String。
                      SecurityEnhancementStrategy：是否开启安全加固。取值范围：Active：启用安全加固，只对公共镜像生效。
                                                                Deactive：不启用安全加固，对所有镜像类型生效。类型：String。
                      ClientToken：保证请求幂等性。类型：String。
                      Tag.N.Key：实例、云盘和主网卡的标签键。类型：String。
                      Tag.N.Value:实例、云盘和主网卡的标签值。类型：String。
                      HpcClusterId：实例所属的EHPC集群ID。类型：String。
                      DryRun：是否只预检此次请求。取值范围：true：发送检查请求，不会创建实例。
                                                        false（默认）：发送正常请求，通过检查后直接创建实例。类型：Boolean。
                      DedicatedHostId：是否在专有宿主机上创建ECS实例。类型：String。
                      LaunchTemplateId：启动模板ID。类型：String。
                      LaunchTemplateName：启动模板名称。类型：String。
                      LaunchTemplateVersion：启动模板版本。类型：String。
                      ResourceGroupId：实例所在的企业资源组ID。类型：String。
                      Period：购买资源的时长。类型：Integer。
                      PeriodUnit：包年包月计费方式的时长单位。取值范围：Week；Month（默认）。类型：String。
                      AutoRenew：是否要自动续费。类型：Boolean。
                      AutoRenewPeriod：单次自动续费的续费时长。类型：Integer。
                      InstanceChargeType：实例的付费方式。取值范围：PrePaid：包年包月；
                                                                PostPaid（默认）：按量付费；类型：String。
                      DeploymentSetId：部署集ID。类型：String。
                      PrivateIpAddress：实例私网IP地址。类型：String。
                      CreditSpecification：修改突发性能实例的运行模式。类型：String。
                      Ipv6Address：为主网卡指定一个IPv6地址。类型：RepeatList。
                      Ipv6AddressCount：为主网卡指定随机生成的IPv6地址数量。类型：Integer。
                      DeletionProtection：实例释放保护属性，指定是否支持通过控制台或API释放实例。类型：Boolean。
                      Affinity：专有宿主机实例是否与专有宿主机关联。取值范围：default：实例不与专有宿主机关联。
                                                                    host：实例与专有宿主机关联。类型：String。
                      Tenancy：是否在专有宿主机上创建实例。取值范围：default：创建非专有宿主机实例。
                                                            host：创建专有宿主机实例。类型：String。
                      StorageSetId：存储集ID。类型：String。
                      StorageSetPartitionNumber：存储集中的最大分区数量。类型：Integer。
                      CpuOptions.Core：CPU核心数。该参数不支持自定义设置，只能采用默认值。类型：Integer。
                      CpuOptions.ThreadsPerCore：CPU线程数。类型：Integer。
                      CpuOptions.Numa：CPU Numa节点数。类型：String。
                      HttpEndpoint：是否启用实例元数据的访问通道。取值范围：enabled：
                                                                启用；disabled：禁用。默认值：enabled。类型：String。
                      HttpTokens：访问实例元数据时是否强制使用加固模式（IMDSv2）。取值范围：optional：不强制使用。
                                                                                required：强制使用。类型：String。
        :return:实例ID
        """
        try:
            if "ImageId" not in kwargs:
                return {"result": False, "message": "need param ImageId"}
            if "InstanceType" not in kwargs:
                return {"result": False, "message": "need param InstanceType"}
            if "SecurityGroupId" not in kwargs:
                return {"result": False, "message": "need param SecurityGroupId"}
            request = self._set_create_vm_params(**kwargs)
            ali_response = self.client.do_action_with_exception(request)
            ali_result = json.loads(ali_response)
            return {"result": True, "data": ali_result["InstanceIdSets"]["InstanceIdSet"]}
        except Exception as e:
            logger.exception("create_vm")
            return {"result": False, "message": str(e)}

    def reset_instances_password(self, **kwargs):
        """
            修改一台ECS实例的部分信息，包括实例密码、名称、描述、主机名
            查询ECS实例信息时，如果返回数据中包含{"OperationLocks": {"LockReason" : "security"}}，则禁止一切操作。
            调用该接口完成以下操作时，您需要注意：
            修改主机名（HostName）：重启实例后，修改生效，且必须是在ECS控制台重启或者调用API RebootInstance重启，新主机名
        才能生效。在操作系统内部重启不能生效。
            重置密码（Password）：
                实例状态不能为启动中（Starting）。
                重启实例后，重置生效，且必须是在ECS控制台重启或者调用API RebootInstance重启，新密码才能生效。在操作系统内部
            重启不能生效。
            修改自定义数据（UserData）：
                实例状态必须为已停止（Stopped）
                实例必须满足自定义数据使用限制。详情请参见生成实例自定义数据。
            更换实例安全组（SecurityGroupIds.N）：
                支持切换安全组类型。
                当ECS实例跨类型切换安全组时，您需要充分了解两种安全组规则的配置区别，避免影响实例网络。
                不支持经典网络类型实例。
            :param kwargs:
                        InstanceId：类型:String。必选。描述：实例id。
                        Password：类型：String。描述：实例的密码。支持长度为8至30个字符，必须同时包含大小写英文字母、数字和特殊符号中的三类字符。
                        HostName：类型：String。描述：操作系统的主机名。修改主机名后，请调用RebootInstance使修改生效。
                        InstanceName：类型：String。描述：实例名称。长度为2~128个英文或中文字符。必须以大小字母或中文开头，
                    不能以http://和https://开头。可以包含数字、半角冒号（:）、下划线（_）或者连字符（-）。
                        Description：类型：String。描述：实例描述。长度为2~256个英文或中文字符，不能以http://和https://开头。默认值：无。
            :return:
        """
        try:
            request = ModifyInstanceAttributeRequest.ModifyInstanceAttributeRequest()
            request.set_InstanceId(kwargs["InstanceId"])
            # 修改密码、主机名、实例名称和描述
            # list_optional_params = ["Password", "HostName", "InstanceName", "Description"]
            # 只修改密码
            list_optional_params = ["Password"]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("reset_instances_password:" + kwargs["InstanceId"])
            return {"result": False, "message": str(e)}

    def start_vm(self, vm_id):
        """
        启动实例
        :param vm_id:实例ID
        """
        try:
            request = StartInstanceRequest.StartInstanceRequest()
            request.set_InstanceId(vm_id)
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("start_vm(instance_id):" + vm_id)
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def stop_vm(self, vm_id, **kwargs):
        """
        停止实例
        :param vm_id:实例ID
        :param is_force: 强制关机
        """
        try:
            is_force = kwargs.get("is_force", "false")
            request = StopInstanceRequest.StopInstanceRequest()
            request.set_InstanceId(vm_id)
            request.set_ForceStop(is_force)
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("stop_vm(instance_id):" + vm_id)
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def restart_vm(self, vm_id, **kwargs):
        """
        实例处于运行中（Running）状态时,重启实例
        :param vm_id:实例ID
        :param is_force: 强制关机
        """
        try:
            is_force = kwargs.get("is_force", "false")
            request = RebootInstanceRequest.RebootInstanceRequest()
            request.set_InstanceId(vm_id)
            request.set_ForceStop(is_force)
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("restart_vm(instance_id):" + vm_id)
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def reactivate_vm(self, vm_id):
        """
        重新启动一台已过期或欠费回收中的按量付费ECS实例
        :param vm_id：类型：String。必选。描述：实例ID。
        :return:
        """
        try:
            request = ReActivateInstancesRequest.ReActivateInstancesRequest()
            request.set_InstanceId(vm_id)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("reactivate_vm:" + vm_id)
            return {"result": False, "message": str(e)}

    def renew_vm(self, vm_id, period):
        """
        实例续费
        :param vm_id: 实例ID
        :param period:包年包月续费时长
        """
        try:
            request = RenewInstanceRequest.RenewInstanceRequest()
            request.set_InstanceId(vm_id)
            request.set_Period(period)
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("renew_vm(instance_id):" + vm_id)
            return {"result": False, "message": str(e)}

    def modify_vm(self, **kwargs):
        """
        调整一台按量付费ECS实例的实例规格和公网带宽大小。
        :param kwargs: aliyun ModifyInstanceSpecRequest api param, see https://help.aliyun.com/
            InstanceId (str): 实例id  (required)
            InstanceType (str): 新规格id  (required)
        """
        try:
            request = ModifyInstanceSpecRequest.ModifyInstanceSpecRequest()
            request.set_InstanceId(kwargs["InstanceId"])
            request.set_InstanceType(kwargs["InstanceType"])
            if kwargs.get("InternetMaxBandwidthOut", None):
                request.set_InternetMaxBandwidthOut(kwargs["InternetMaxBandwidthOut"])
            if kwargs.get("InternetMaxBandwidthIn", None):
                request.set_InternetMaxBandwidthIn(kwargs["InternetMaxBandwidthIn"])
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_vm():" + kwargs["InstanceId"])
            return {"result": False, "message": str(e)}

    def modify_prepay_vm(self, **kwargs):
        """
        升级或者降低一台包年包月ECS实例的实例规格，新实例规格将会覆盖实例的整个生命周期
        调用该接口时，您需要注意：
            已过期实例无法修改实例规格，您可以续费后重新操作。
            降低实例规格时，您需要注意：
                实例必须处于已停止（Stopped）状态。
                您必须指定操作类型，即OperatorType=downgrade。
                每台实例降低配置次数不能超过三次，即价格差退款不会超过三次。降低配置包括降低实例规格、降低带宽配置、
            包年包月云盘转换为按量付费云盘等操作。
                降低前后的实例规格价格差退款会退还到您的原付费方式中，已使用的代金券不退回。
            本接口属于异步操作，等待约5~10秒后配置变更完成。随后，您必须调用API或者在控制台重启一次实例，否则规格变更不
        会生效，重启操作系统无效。
                若实例处于已停止状态，仅需启动实例，无需重启。
                若实例设置了RebootWhenFinished=true，则无需单独重启。
        :param kwargs:
                    InstanceId：类型：String。必选。描述：实例id。
                    InstanceType:类型：String。必选。描述：需要变配的目标实例规格。必选。
                    OperatorType:类型：String。描述。操作类型。取值范围：
                                            upgrade（默认）：升级实例规格。请确保您的账户支付方式余额充足。
                                            downgrade：降配实例规格。当InstanceType设置的实例规格低于当前实例规格时，
                                            您必须设置OperatorType=downgrade。
        :return:data:
                   ali_result["OrderId"]:生成的订单ID
        """
        try:
            request = ModifyPrepayInstanceSpecRequest.ModifyPrepayInstanceSpecRequest()
            request.set_InstanceId(kwargs["InstanceId"])
            request.set_InstanceType(kwargs["InstanceType"])
            if "OperatorType" in kwargs:
                request.set_OperatorType(kwargs["OperatorType"])
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["OrderId"]}
        except Exception as e:
            logger.exception("modify_vm_change_type:" + kwargs["InstanceId"])
            return {"result": False, "message": str(e)}

    def destroy_vm(self, vm_id):
        """
        释放实例
        :param vm_id:实例ID
        """
        try:
            request = DeleteInstanceRequest.DeleteInstanceRequest()
            request.set_InstanceId(vm_id)
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete vm failed(instance_id): " + vm_id)
            return {"result": False, "message": str(e)}

    def remote_connect_vm(self, **kwargs):
        """
        查询实例的Web管理终端地址
        :param kwargs:aliyun DescribeInstanceVncUrlRequest api param, see https://help.aliyun.com/
        :return: 远程控制台url
        """
        try:
            vm_id = kwargs["vm_id"]
            is_windows = kwargs.get("is_windows", "true")
            request = DescribeInstanceVncUrlRequest.DescribeInstanceVncUrlRequest()
            request.set_InstanceId(vm_id)
            request.set_accept_format("json")
            ali_response = self.client.do_action_with_exception(request)
            ali_result = json.loads(ali_response)
            vnc_url = ali_result["VncUrl"]
            url = (
                "https://g.alicdn.com/aliyun/ecs-console-vnc2/0.0.5/index.html?vncUrl={0}&instanceId={"
                "1}&isWindows={2}".format(vnc_url, vm_id, is_windows)
            )
            return {"result": True, "data": url}
        except Exception as e:
            logger.exception("remote_vm(instance_id):" + kwargs["vm_id"])
            return {"result": False, "message": str(e)}

    @classmethod
    def _set_available_vm_params(cls, **kwargs):
        """
        查询升级和降配实例规格或者系统盘时，某一可用区的可用资源信息
        :param kwargs:
        :return:
        """
        if "ResourceId" in kwargs:
            request = DescribeResourcesModificationRequest.DescribeResourcesModificationRequest()
            request.set_DestinationResource(kwargs["DestinationResource"])
            request.set_ResourceId(kwargs["ResourceId"])
        else:
            request = DescribeAvailableResourceRequest.DescribeAvailableResourceRequest()
            request.set_DestinationResource("InstanceType")
            if kwargs.get("ZoneId", None):
                request.set_ZoneId(kwargs["ZoneId"])
        request.set_Cores(kwargs["Cores"])
        request.set_Memory(kwargs["Memory"])
        request.set_accept_format("json")
        return request

    def get_available_flavor(self, **kwargs):
        """
        查询升级和降配实例规格时，某一可用区的可用实例规格信息
        :param kwargs: aliyun DescribeResourcesModificationRequest api param, see https://help.aliyun.com/
        :return: 实例规格id
        """
        try:
            kwargs["Cores"] = int(kwargs["config"][0])
            kwargs["Memory"] = float(kwargs["config"][1])
            request = self._set_available_vm_params(**kwargs)
            ali_response = self.client.do_action_with_exception(request)
            ali_result = json.loads(ali_response)
            data = ""
            if "Code" not in ali_result:
                available_resource = ali_result["AvailableZones"]["AvailableZone"][0]["AvailableResources"][
                    "AvailableResource"
                ]
                if available_resource:
                    supported_resource = available_resource[0]["SupportedResources"]["SupportedResource"]
                    t5_vm = ""
                    for i in supported_resource:
                        if "t5" not in i["Value"]:
                            data = i["Value"]
                            break
                        else:
                            t5_vm = i["Value"]
                    if t5_vm and not data:
                        data = t5_vm
                return {"result": True, "data": data}
        except Exception as e:
            logger.exception("get_available_flavor")
            return {"result": False, "message": str(e)}

    def get_available_specifications(self, **kwargs):
        """
        查询升级和降配实例规格时，某一可用区的可用实例规格信息
        :param kwargs:
        :return: 实例规格id
        """
        try:
            request = DescribeResourcesModificationRequest.DescribeResourcesModificationRequest()
            request.set_accept_format("json")
            request.set_ResourceId(kwargs.get("resource_id", ""))
            request.set_DestinationResource("InstanceType")
            response = self.client.do_action_with_exception(request)
            return response
        except Exception:
            return {}

    def list_domains(self, **kwargs):
        """
        查询域名列表
        :param kwargs:
        :return:
        """
        try:
            all_domain_list = []
            scroll_domain_list_request = domain_20180129_models.ScrollDomainListRequest()
            runtime = util_models.RuntimeOptions()
            while True:
                resp = self.domain_client.scroll_domain_list_with_options(scroll_domain_list_request, runtime)

                result = TeaCore.to_map(resp.body)
                domain = result.get("Data", {}).get("Domain", [])
                if domain:
                    all_domain_list.extend(domain)
                total_count = result.get("TotalItemNum", 0)
                if total_count == 0:
                    break
                scroll_id = result.get("ScrollId", {})
                scroll_domain_list_request.scroll_id = scroll_id
            return {"result": True, "data": all_domain_list}
        except Exception as e:
            logger.exception("list_domains error")
            return {"result": False, "message": repr(e)}

    def get_domain_parsing(self, domain_name, **kwargs):
        describe_domain_records_request = alidns_20150109_models.DescribeDomainRecordsRequest()
        describe_domain_records_request.domain_name = domain_name
        describe_domain_records_request.page_number = 1
        describe_domain_records_request.page_size = 50
        runtime = util_models.RuntimeOptions()
        domain_records = []
        try:
            while True:
                resp = self.dns_client.describe_domain_records_with_options(describe_domain_records_request, runtime)
                # 处理分页
                result = TeaCore.to_map(resp.body)
                domain_record = result.get("DomainRecords", {}).get("Record", [])
                if domain_record:
                    domain_records.extend(domain_record)
                if not domain_record:
                    break
                describe_domain_records_request.page_number += 1
            return domain_records
        except Exception as e:
            logger.exception("get_domain_parsing error")
            raise e

    def list_parsings(self, domains=None, **kwargs):
        """
        查询解析记录列表
        """
        if not domains:
            domains = self.list_domains()
            if not domains.get("result"):
                return {"result": False, "message": domains.get("message")}
            domains = domains.get("data", [])
        parsings = []
        for domain in domains:
            domain_name = domain.get("DomainName", "")
            domain_id = domain.get("InstanceId", "")
            try:
                domain_parsings = self.get_domain_parsing(domain_name)
                for domain_parsing in domain_parsings:
                    domain_parsing["DomainId"] = domain_id
                    domain_parsing["Remark"] = domain_parsing.get("Remark", "")
                parsings.extend(domain_parsings)
            except Exception:
                logger.exception("get_domain_parsing error")
                return {"result": False, "message": "get_domain_parsing error"}

        return {"result": True, "data": parsings}

    def list_cdn(self):
        """
        查询CDN域名列表
        """
        describe_cdn_service_request = cdn_20180510_models.DescribeCdnServiceRequest()
        runtime = util_models.RuntimeOptions()
        try:
            resp = self.cdn_client.describe_cdn_service_with_options(describe_cdn_service_request, runtime)
            result = TeaCore.to_map(resp.body)
            result = [result]
            return {"result": True, "data": result}
        except Exception as e:
            logger.exception("list_cdn error")
            return {"result": False, "message": repr(e)}

    def list_waf(self, **kwargs):
        describe_instance_info_request = waf_openapi_20211001_models.DescribeInstanceRequest()
        describe_instance_info_request.region_id = self.RegionId
        runtime = util_models.RuntimeOptions()
        try:
            resp = self.waf_client.describe_instance_with_options(describe_instance_info_request, runtime)
            result = TeaCore.to_map(resp.body)
            if result and result.get("InstanceId", None):
                result = [result]
                return {"result": True, "data": result}
            return {"result": True, "data": []}
        except Exception as e:
            logger.exception("list_waf error")
            return {"result": False, "message": repr(e)}

    def list_cas(self, **kwargs):
        list_user_certificate_order_request = cas_20200407_models.ListUserCertificateOrderRequest()
        runtime = util_models.RuntimeOptions()
        # 分页查询
        list_user_certificate_order_request.current_page = 1
        list_user_certificate_order_request.show_size = 50
        list_user_certificate_order_request.order_type = "CERT"

        try:
            cas = []
            while True:
                resp = self.cas_client.list_user_certificate_order_with_options(
                    list_user_certificate_order_request, runtime
                )
                result = TeaCore.to_map(resp.body)
                page_cas = result.get("CertificateOrderList", [])
                if not page_cas:
                    break
                cas.extend(page_cas)
                time.sleep(1)
                list_user_certificate_order_request.current_page += 1

            return {"result": True, "data": cas}
        except Exception as e:
            logger.exception("list_cas error")
            return {"result": False, "message": repr(e)}

    def list_buckets(self, **kwargs):
        """
        查询OSS存储桶列表
        """
        list_buckets_request = oss_20190517_models.ListBucketsRequest()
        list_buckets_header = oss_20190517_models.ListBucketsHeaders()
        runtime = util_models.RuntimeOptions()
        list_buckets_request.max_keys = 1000

        try:
            resp = self.oss_client.list_buckets_with_options(list_buckets_request, list_buckets_header, runtime)
            result = TeaCore.to_map(resp.body)
            buckets = result.get("buckets", [])
            for bucket in buckets:
                # 获取bucket详情
                bucket_name = bucket.get("Name")
                resp = self.oss_client.get_bucket_info_with_options(bucket_name, {}, runtime)
                result = TeaCore.to_map(resp.body)
                bucket.update(result.get("Bucket", {}))
            return {"result": True, "data": buckets}
        except Exception as e:
            logger.exception("list_buckets error")
            return {"result": False, "message": repr(e)}

    def list_rds(self, **kwargs):
        """
        查询RDS实例列表(mysql)
        """
        describe_db_instances_request = rds_20140815_models.DescribeDBInstancesRequest()
        runtime = util_models.RuntimeOptions()
        engine = kwargs.get("engine")
        if engine:
            describe_db_instances_request.engine = engine
        describe_db_instances_request.region_id = self.RegionId
        describe_db_instances_request.page_number = 1
        describe_db_instances_request.page_size = 100
        describe_db_instances_request.instance_level = 1
        rds_instances = []
        try:
            while True:
                resp = self.rds_client.describe_dbinstances_with_options(describe_db_instances_request, runtime)
                result = TeaCore.to_map(resp.body)
                db_instances = result.get("Items", {}).get("DBInstance", [])
                if not db_instances:
                    break
                rds_instances.extend(db_instances)
                describe_db_instances_request.page_number += 1
            return {"result": True, "data": rds_instances}
        except Exception as e:
            logger.exception("list_rds error")
            return {"result": False, "message": repr(e)}

    def list_redis(self):
        """
        查询redis实例列表
        """
        describe_instances_request = r_kvstore_20150101_models.DescribeInstancesRequest()
        runtime = util_models.RuntimeOptions()
        describe_instances_request.region_id = self.RegionId
        describe_instances_request.page_number = 1
        describe_instances_request.page_size = 100
        redis_instances = []
        try:
            while True:
                resp = self.kvs_client.describe_instances_with_options(describe_instances_request, runtime)
                result = TeaCore.to_map(resp.body)
                instances = result.get("Instances", {}).get("KVStoreInstance", [])
                if not instances:
                    break
                redis_instances.extend(instances)
                describe_instances_request.page_number += 1
            return {"result": True, "data": redis_instances}
        except Exception as e:
            logger.exception("list_redis error")
            return {"result": False, "message": repr(e)}

    def list_mongodb(self):
        """
        查询mongodb实例列表
        """

        describe_db_instances_request = dds_20151201_models.DescribeDBInstancesRequest()
        runtime = util_models.RuntimeOptions()
        describe_db_instances_request.region_id = self.RegionId

        describe_db_instances_request.engine = "MongoDB"
        """sharding：分片集群实例。
replicate：默认值，副本集实例和单节点实例。
serverless"""
        db_instance_types = ["sharding", "replicate", "serverless"]
        mongodb_instances = []
        try:
            for inst_type in db_instance_types:
                describe_db_instances_request.dbinstance_type = inst_type
                describe_db_instances_request.page_number = 1
                describe_db_instances_request.page_size = 100
                while True:
                    resp = self.dds_client.describe_dbinstances_with_options(describe_db_instances_request, runtime)
                    result = TeaCore.to_map(resp.body)
                    instances = result.get("DBInstances", {}).get("DBInstance", [])
                    if not instances:
                        break
                    mongodb_instances.extend(instances)
                    describe_db_instances_request.page_number += 1
            return {"result": True, "data": mongodb_instances}
        except Exception as e:
            logger.exception("list_mongodb error")
            return {"result": False, "message": repr(e)}

    def list_kafka(self):
        """
        查询kafka实例列表
        """
        get_instance_list_request = alikafka_20190916_models.GetInstanceListRequest()
        runtime = util_models.RuntimeOptions()
        get_instance_list_request.region_id = self.RegionId
        try:
            resp = self.kafka_client.get_instance_list_with_options(get_instance_list_request, runtime)
            result = TeaCore.to_map(resp.body)
            kafka_instances = result.get("InstanceList", {}).get("InstanceVO", [])
            return {"result": True, "data": kafka_instances}
        except Exception as e:
            logger.exception("list_kafka error")
            return {"result": False, "message": repr(e)}

    def list_kafka_consumer_group(self, **kwargs):
        """
        查询kafka consumer group列表
        """
        kafka_instances = kwargs.get("kafka_instances", [])
        if not kafka_instances:
            kafka_instances = self.list_kafka()
        if kafka_instances.get("result"):
            kafka_instances = kafka_instances.get("data", [])
        if not kafka_instances:
            return {"result": True, "data": []}
        get_consumer_group_list_request = alikafka_20190916_models.GetConsumerListRequest()
        runtime = util_models.RuntimeOptions()
        kafka_consumer_groups = []
        try:
            for kafka_instance in kafka_instances:
                get_consumer_group_list_request.instance_id = kafka_instance.get("InstanceId")
                get_consumer_group_list_request.region_id = self.RegionId
                get_consumer_group_list_request.current_page = 1
                get_consumer_group_list_request.page_size = 100
                while True:
                    resp = self.kafka_client.get_consumer_list_with_options(get_consumer_group_list_request, runtime)
                    result = TeaCore.to_map(resp.body)
                    consumer_groups = result.get("ConsumerList", {}).get("ConsumerVO", [])
                    if not consumer_groups:
                        break
                    kafka_consumer_groups.extend(consumer_groups)
                    get_consumer_group_list_request.current_page += 1
            return {"result": True, "data": kafka_consumer_groups}
        except Exception as e:
            logger.exception("list_kafka_consumer_group error")
            return {"result": False, "message": repr(e)}

    def get_kafka_topic_subscribe_status(self, instance_id, topic):
        """
        查询kafka topic订阅状态
        """
        get_topic_subscribe_status_request = alikafka_20190916_models.GetTopicSubscribeStatusRequest()
        runtime = util_models.RuntimeOptions()
        get_topic_subscribe_status_request.instance_id = instance_id
        get_topic_subscribe_status_request.region_id = self.RegionId
        get_topic_subscribe_status_request.topic = topic
        try:
            resp = self.kafka_client.get_topic_subscribe_status_with_options(
                get_topic_subscribe_status_request, runtime
            )
            result = TeaCore.to_map(resp.body)
            consumer_groups = result.get("TopicSubscribeStatus", {}).get("ConsumerGroups", [])

            return {"result": True, "data": {topic: consumer_groups}}
        except Exception as e:
            logger.exception("get_kafka_topic_subscribe_status error")
            return {"result": False, "message": repr(e)}

    def list_kafka_topic(self, **kwargs):
        """
        查询kafka topic列表
        """
        kafka_instances = kwargs.get("kafka_instances", [])
        if not kafka_instances:
            kafka_instances = self.list_kafka()
        if kafka_instances.get("result"):
            kafka_instances = kafka_instances.get("data", [])
        if not kafka_instances:
            return {"result": True, "data": []}
        kafka_topics = []
        get_topic_list_request = alikafka_20190916_models.GetTopicListRequest()
        runtime = util_models.RuntimeOptions()
        try:
            for kafka_instance in kafka_instances:
                get_topic_list_request.instance_id = kafka_instance.get("InstanceId")
                get_topic_list_request.region_id = self.RegionId
                get_topic_list_request.current_page = 1
                get_topic_list_request.page_size = 100
                while True:
                    resp = self.kafka_client.get_topic_list_with_options(get_topic_list_request, runtime)
                    result = TeaCore.to_map(resp.body)
                    topics = result.get("TopicList", {}).get("TopicVO", [])
                    total = result.get("Total")
                    if not topics:
                        break
                    kafka_topics.extend(topics)
                    if total <= get_topic_list_request.current_page * get_topic_list_request.page_size:
                        break
                    get_topic_list_request.current_page += 1
            # 开启多线程查询topic订阅状态
            pool = ThreadPoolExecutor(max_workers=10)
            futures = []
            for kafka_topic in kafka_topics:
                instance_id = kafka_topic.get("InstanceId")
                topic = kafka_topic.get("Topic")
                futures.append(pool.submit(self.get_kafka_topic_subscribe_status, instance_id, topic))
            topic_group_map = {}
            for future in as_completed(futures):
                result = future.result()
                if result.get("result"):
                    topic_group_map.update(result.get("data"))
            for kafka_topic in kafka_topics:
                topic = kafka_topic.get("Topic")
                kafka_topic["ConsumerGroups"] = topic_group_map.get(topic, [])
            return {"result": True, "data": kafka_topics}
        except Exception as e:
            logger.exception("list_kafka_topic error")
            return {"result": False, "message": repr(e)}

    def list_clb(self, **kwargs):
        """
        查询SLB实例列表
        """
        describe_load_balancers_request = slb_20140515_models.DescribeLoadBalancersRequest()
        runtime = util_models.RuntimeOptions()
        describe_load_balancers_request.region_id = self.RegionId
        describe_load_balancers_request.page_number = 1
        describe_load_balancers_request.page_size = 100
        clb_instances = []
        try:
            while True:
                resp = self.slb_client.describe_load_balancers_with_options(describe_load_balancers_request, runtime)
                result = TeaCore.to_map(resp.body)
                instances = result.get("LoadBalancers", {}).get("LoadBalancer", [])
                if not instances:
                    break
                clb_instances.extend(instances)
                total = result.get("TotalCount", 0)
                if total <= describe_load_balancers_request.page_number * describe_load_balancers_request.page_size:
                    break
                describe_load_balancers_request.page_number += 1
            return {"result": True, "data": clb_instances}
        except Exception as e:
            logger.exception("list_slb error")
            return {"result": False, "message": repr(e)}

    def list_k8s_clusters(self):
        """
        查询k8s集群列表
        """
        describe_clusters_request = cs20151215_models.DescribeClustersV1Request()
        runtime = util_models.RuntimeOptions()
        describe_clusters_request.region_id = self.RegionId
        describe_clusters_request.page_number = 1
        describe_clusters_request.page_size = 100
        k8s_clusters = []
        try:
            while True:
                resp = self.cs_client.describe_clusters_v1with_options(describe_clusters_request, {}, runtime)
                result = TeaCore.to_map(resp.body)
                clusters = result.get("clusters", [])
                if not clusters:
                    break
                k8s_clusters.extend(clusters)
                total = result.get("page_info").get("total", 0)
                if total <= describe_clusters_request.page_number * describe_clusters_request.page_size:
                    break
                describe_clusters_request.page_number += 1
            return {"result": True, "data": k8s_clusters}
        except Exception as e:
            logger.exception("list_k8s_clusters error")
            return {"result": False, "message": repr(e)}

    def list_eips(self):
        """
        查询EIP列表
        """
        describe_eip_addresses_request = vpc_20160428_models.DescribeEipAddressesRequest()
        runtime = util_models.RuntimeOptions()
        describe_eip_addresses_request.region_id = self.RegionId
        describe_eip_addresses_request.page_number = 1
        describe_eip_addresses_request.page_size = 100
        eips = []
        try:
            while True:
                resp = self.vpc_client.describe_eip_addresses_with_options(describe_eip_addresses_request, runtime)
                result = TeaCore.to_map(resp.body)
                eip_addresses = result.get("EipAddresses", {}).get("EipAddress", [])
                if not eip_addresses:
                    break
                eips.extend(eip_addresses)
                total = result.get("TotalCount", 0)
                if total <= describe_eip_addresses_request.page_number * describe_eip_addresses_request.page_size:
                    break
                describe_eip_addresses_request.page_number += 1
            return {"result": True, "data": eips}
        except Exception as e:
            logger.exception("list_eips error")
            return {"result": False, "message": repr(e)}

    def list_mse_clusters(self):
        """
        查询mse集群列表
        """
        list_clusters_request = mse20190531_models.ListClustersRequest()
        runtime = util_models.RuntimeOptions()
        list_clusters_request.region_id = self.RegionId
        list_clusters_request.page_num = 1
        list_clusters_request.page_size = 100
        mse_clusters = []
        try:
            while True:
                resp = self.mse_client.list_clusters_with_options(list_clusters_request, runtime)
                result = TeaCore.to_map(resp.body)
                clusters = result.get("Data", [])
                if not clusters:
                    break
                mse_clusters.extend(clusters)
                total = result.get("TotalCount", 0)
                if total <= list_clusters_request.page_num * list_clusters_request.page_size:
                    break
                list_clusters_request.page_num += 1
            return {"result": True, "data": mse_clusters}
        except Exception as e:
            logger.exception("list_mse_clusters error")
            return {"result": False, "message": repr(e)}

    def list_mse_namespaces(self, **kwargs):
        mse_clusters = kwargs.get("mse_clusters", [])
        if not mse_clusters:
            mse_clusters = self.list_mse_clusters()
        if mse_clusters.get("result"):
            mse_clusters = mse_clusters.get("data", [])
        else:
            return {"result": False, "message": mse_clusters.get("message")}
        if not mse_clusters:
            return {"result": True, "data": []}
        mse_namespaces = []
        try:
            for mse_cluster in mse_clusters:
                list_mse_namespace_request = mse20190531_models.ListEngineNamespacesRequest()
                runtime = util_models.RuntimeOptions()
                list_mse_namespace_request.instance_id = mse_cluster.get("InstanceId")

                resp = self.mse_client.list_engine_namespaces_with_options(list_mse_namespace_request, runtime)
                result = TeaCore.to_map(resp.body)
                namespaces = result.get("Data", [])
                if not namespaces:
                    break
                for namespace in namespaces:
                    namespace["ClusterId"] = mse_cluster.get("InstanceId")
                mse_namespaces.extend(namespaces)

            return {"result": True, "data": mse_namespaces}
        except Exception as e:
            logger.exception("list_mse_namespace error")
            return {"result": False, "message": repr(e)}

    def list_mse_service(self, **kwargs):
        mse_namespaces = kwargs.get("mse_namespaces", [])
        if not mse_namespaces:
            mse_namespaces = self.list_mse_namespaces()
        if mse_namespaces.get("result"):
            mse_namespaces = mse_namespaces.get("data", [])
        else:
            return {"result": False, "message": mse_namespaces.get("message")}
        if not mse_namespaces:
            return {"result": True, "data": []}
        mse_services = []
        try:
            for mse_namespace in mse_namespaces:
                list_mse_service_request = mse20190531_models.ListAnsServicesRequest()
                runtime = util_models.RuntimeOptions()
                list_mse_service_request.instance_id = mse_namespace.get("ClusterId", "")
                list_mse_service_request.namespace_id = mse_namespace.get("Namespace", "")
                list_mse_service_request.page_num = 1
                list_mse_service_request.page_size = 100
                while True:
                    resp = self.mse_client.list_ans_services_with_options(list_mse_service_request, runtime)
                    result = TeaCore.to_map(resp.body)
                    services = result.get("Data", [])
                    if not services:
                        break
                    for service in services:
                        service["ClusterId"] = mse_namespace.get("ClusterId")
                        service["Namespace"] = mse_namespace.get("Namespace")
                    mse_services.extend(services)
                    total = result.get("TotalCount", 0)
                    if total <= list_mse_service_request.page_num * list_mse_service_request.page_size:
                        break
                    list_mse_service_request.page_num += 1
            return {"result": True, "data": mse_services}
        except Exception as e:
            logger.exception("list_mse_service error")
            return {"result": False, "message": repr(e)}

    def list_mse_inst(self, **kwargs):
        mse_services = kwargs.get("mse_services", [])
        if not mse_services:
            mse_services = self.list_mse_service()
        if mse_services.get("result"):
            mse_services = mse_services.get("data", [])
        else:
            return {"result": False, "message": mse_services.get("message")}
        if not mse_services:
            return {"result": True, "data": []}
        mse_insts = []
        try:

            for mse_service in mse_services:
                list_mse_inst_request = mse20190531_models.ListAnsInstancesRequest()
                runtime = util_models.RuntimeOptions()
                list_mse_inst_request.service_name = mse_service.get("Name")
                list_mse_inst_request.instance_id = mse_service.get("ClusterId")
                list_mse_inst_request.namespace_id = mse_service.get("Namespace")
                list_mse_inst_request.page_num = 1
                list_mse_inst_request.page_size = 100
                while True:
                    resp = self.mse_client.list_ans_instances_with_options(list_mse_inst_request, runtime)
                    result = TeaCore.to_map(resp.body)
                    insts = result.get("Data", [])
                    if not insts:
                        break
                    for inst in insts:
                        # 用于标记关联
                        inst["ServiceNameRel"] = mse_service.get("Name")
                        inst["ClusterId"] = mse_service.get("ClusterId")
                        inst["Namespace"] = mse_service.get("Namespace")
                    mse_insts.extend(insts)
                    total = result.get("TotalCount", 0)
                    if total <= list_mse_inst_request.page_num * list_mse_inst_request.page_size:
                        break
                    list_mse_inst_request.page_num += 1
            return {"result": True, "data": mse_insts}
        except Exception as e:
            logger.exception("list_mse_inst error")
            return {"result": False, "message": repr(e)}

    def list_albs(self, **kwargs):
        """查询alb实例列表"""
        list_load_balancers_request = alb_20200616_models.ListLoadBalancersRequest()
        runtime = util_models.RuntimeOptions()
        list_load_balancers_request.region_id = self.RegionId
        list_load_balancers_request.page_number = 1
        list_load_balancers_request.page_size = 100
        alb_instances = []
        try:
            while True:
                resp = self.alb_client.list_load_balancers_with_options(list_load_balancers_request, runtime)
                result = TeaCore.to_map(resp.body)
                instances = result.get("LoadBalancers", {})
                if not instances:
                    break
                for i in instances:
                    i.update(region_id=self.RegionId)
                alb_instances.extend(instances)
                total = result.get("TotalCount", 0)
                if total <= list_load_balancers_request.page_number * list_load_balancers_request.page_size:
                    break
                list_load_balancers_request.page_number += 1
            return {"result": True, "data": alb_instances}
        except Exception as e:
            logger.exception("list_alb error")
            return {"result": False, "message": repr(e)}

    def list_nas(self, **kwargs):
        """查询查询文件系统信息"""
        describe_file_systems_request = nas20170626_models.DescribeFileSystemsRequest()
        runtime = util_models.RuntimeOptions()
        describe_file_systems_request.region_id = self.RegionId
        describe_file_systems_request.page_number = 1
        describe_file_systems_request.page_size = 100
        nas_instances = []
        try:
            while True:
                resp = self.nas_client.describe_file_systems_with_options(describe_file_systems_request, runtime)
                result = TeaCore.to_map(resp.body)
                instances = result.get("FileSystems", {}).get("FileSystem", [])
                if not instances:
                    break
                nas_instances.extend(instances)
                total = result.get("TotalCount", 0)
                if total <= describe_file_systems_request.page_number * describe_file_systems_request.page_size:
                    break
                describe_file_systems_request.page_number += 1
            return {"result": True, "data": nas_instances}
        except Exception as e:
            logger.exception("list_nas error")
            return {"result": False, "message": repr(e)}

    def list_all_resources(self, **kwargs):
        def handle_resource(resource_func, resource_name):
            result = resource_func()
            if result.get("result"):
                return {resource_name: result.get("data", [])}
            return {}

        data = {}
        kafka_result = self.list_kafka()
        mse_clusters_result = self.list_mse_clusters()
        mse_namespaces_result = self.list_mse_namespaces(mse_clusters=mse_clusters_result)
        mse_service_result = self.list_mse_service(mse_namespaces=mse_namespaces_result)

        resources = [
            (self.list_vms, "aliyun_ecs"),
            (self.list_domains, "aliyun_domain"),
            (self.list_parsings, "aliyun_parsing"),
            (self.list_cdn, "aliyun_cdn"),
            (self.list_waf, "aliyun_firewall"),
            (self.list_cas, "aliyun_ssl"),
            (self.list_buckets, "aliyun_bucket"),
            (lambda: self.list_rds(engine="Mysql"), "aliyun_mysql"),
            (lambda: self.list_rds(engine="PostgreSQL"), "aliyun_pgsql"),
            (self.list_redis, "aliyun_redis"),
            (self.list_mongodb, "aliyun_mongodb"),
            (lambda: kafka_result, "aliyun_kafka_inst"),
            (lambda: self.list_kafka_consumer_group(kafka_instances=kafka_result), "aliyun_kafka_group"),
            (lambda: self.list_kafka_topic(kafka_instances=kafka_result), "aliyun_kafka_topic"),
            (self.list_clb, "aliyun_clb"),
            (self.list_k8s_clusters, "aliyun_k8s_cluster"),
            (self.list_eips, "aliyun_eip"),
            (lambda: mse_clusters_result, "aliyun_mse_cluster"),
            (lambda: mse_service_result, "aliyun_mse_service"),
            (lambda: self.list_mse_inst(mse_services=mse_service_result), "aliyun_mse_inst"),
            (self.list_albs, "aliyun_alb"),
            (self.list_nas, "aliyun_nas"),
        ]

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_resource = {
                executor.submit(handle_resource, resource_func, resource_name): resource_name
                for resource_func, resource_name in resources
            }
            for future in as_completed(future_to_resource):
                result = future.result()
                if result:
                    data.update(result)

        return {"result": True, "data": data}

    def monitor_data(self, **kwargs):
        """
        获取监控信息列表
        :param kwargs:aliyun DescribeMetricListRequest api param, see https://help.aliyun.com/
        :return:监控信息
        """
        try:
            request = self._set_monitor_data_params(**kwargs)
            ali_response = self.client.do_action_with_exception(request)
            ali_result = json.loads(ali_response)
            monitor_list = []
            if not (ali_result.get("Datapoints"), []):
                logger.error("ali_result: {}".format(ali_result))
            monitor_list.extend(json.loads(ali_result.get("Datapoints")))

            while ali_result.get("NextToken", None):
                kwargs["NextToken"] = ali_result["NextToken"]
                request = self._set_monitor_data_params(**kwargs)
                ali_response = self.client.do_action_with_exception(request)
                ali_result = json.loads(ali_response)
                monitor_list.extend(json.loads(ali_result.get("Datapoints", "")))
            return {"result": True, "data": monitor_list}
        except Exception as e:
            logger.exception("monitor_data")
            return {"result": False, "data": [], "message": str(e)}

    @classmethod
    def _set_monitor_data_params(cls, **kwargs):
        """
        设置监控数据参数
        :param kwargs:
        :return:
        """
        request = DescribeMetricListRequest.DescribeMetricListRequest()
        list_required_params = ["Namespace", "MetricName", "Dimensions", "StartTime"]
        request = set_required_params(request, list_required_params, kwargs)
        list_optional_params = ["Period", "EndTime", "NextToken", "Length"]
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_accept_format("json")
        return request

    def get_monitor_data(self, **kwargs):
        """
        获取监控信息详情
        :param kwargs:
        :return:
        """
        now_time = (datetime.datetime.now() + datetime.timedelta(minutes=-50)).strftime("%Y-%m-%d %H:%M:%S")
        hour_time = (datetime.datetime.now() + datetime.timedelta(minutes=-60)).strftime("%Y-%m-%d %H:%M:%S")
        data = {}
        res = {}
        data["Namespace"] = "acs_ecs_dashboard"
        data["Length"] = 1000
        data["Period"] = kwargs.get("Period", "300")  # 时间间隔为5分钟
        data["StartTime"] = kwargs.get("StartTime", hour_time)
        data["EndTime"] = kwargs.get("EndTime", now_time)
        resource_id = kwargs.get("resourceId", "")
        resource_id_list = resource_id.split(",")
        try:
            get_vm_list_count = 0
            while get_vm_list_count < 5:
                virtual_machine_list = self._get_vm_list()
                if isinstance(virtual_machine_list, list):
                    break
                time.sleep(2)
                get_vm_list_count += 1
            vm_list_all = [x for x in resource_id_list if x in set(virtual_machine_list)]
            vm_lists = []
            for i in range(len(vm_list_all) // 40 + 1):
                vm_lists.append(vm_list_all[i * 40 : (i + 1) * 40])
            for vm_list in vm_lists:
                dimensions = []
                for i in vm_list:
                    dimensions.append({"instanceId": i})
                    res[i] = {"cpu_data": [], "memory_data": [], "disk_data": []}
                data["Dimensions"] = json.dumps(dimensions)
                data["MetricName"] = "cpu_user"
                cpu_result = self.monitor_data(**data)["data"]
                data["MetricName"] = "memory_usedutilization"
                memory_result = self.monitor_data(**data)["data"]
                data["MetricName"] = "diskusage_utilization"
                disk_result = self.monitor_data(**data)["data"]
                for i in cpu_result:
                    vm_id = i["instanceId"]
                    timestamp = i["timestamp"] / 1000
                    rate = "%.2f" % (i["Average"])
                    res[vm_id]["cpu_data"].append([timestamp, float(rate)])
                for i in memory_result:
                    vm_id = i["instanceId"]
                    timestamp = i["timestamp"] / 1000
                    rate = "%.2f" % (i["Average"])
                    res[vm_id]["memory_data"].append([timestamp, float(rate)])
                for i in disk_result:
                    vm_id = i["instanceId"]
                    timestamp = i["timestamp"] / 1000
                    rate = "%.2f" % (i["Average"])
                    res[vm_id]["disk_data"].append([timestamp, float(rate)])
            res["result"] = True
            return res
        except Exception as e:
            logger.exception("get_monitor_data")
            logger.error("get {} monitor data error".format(resource_id))
            return {"result": False, "message": str(e)}

    def get_load_monitor_data(self, **kwargs):
        """
        获取监控信息详情
        :param kwargs:
        :return:
        """
        start_time = str(kwargs.get("StartTime", datetime.datetime.now() + datetime.timedelta(minutes=-60)))
        end_time = str(kwargs.get("EndTime", datetime.datetime.now() + datetime.timedelta(minutes=-50)))

        data = {}
        res = {}
        data["Namespace"] = "acs_ecs_dashboard"
        data["Length"] = 1000
        data["Period"] = kwargs.get("Period", "300")  # 时间间隔为5分钟
        data["StartTime"] = kwargs.get("StartTime", start_time)
        data["EndTime"] = kwargs.get("EndTime", end_time)
        resource_id_list = list(set(kwargs["resourceId"]))
        try:
            get_vm_list_count = 0
            while get_vm_list_count < 5:
                virtual_machine_list = self._get_vm_list()
                if isinstance(virtual_machine_list, list):
                    break
                time.sleep(2)
                get_vm_list_count += 1
            vm_list_all = [x for x in resource_id_list if x in set(virtual_machine_list)]
            vm_lists = []
            for i in range(len(vm_list_all) // 40 + 1):
                vm_lists.append(vm_list_all[i * 40 : (i + 1) * 40])
            for vm_list in vm_lists:
                dimensions = []
                for i in vm_list:
                    dimensions.append({"instanceId": i})
                    res[i] = {"cpu_data": [], "memory_data": [], "load_data": []}
                data["Dimensions"] = json.dumps(dimensions)
                #  指标维度
                data["MetricName"] = "cpu_user"
                cpu_result = self.monitor_data(**data)["data"]
                data["MetricName"] = "memory_usedutilization"
                memory_result = self.monitor_data(**data)["data"]
                data["MetricName"] = "load_5m"
                load_result = self.monitor_data(**data)["data"]
                for i in cpu_result:
                    vm_id = i["instanceId"]
                    rate = round(i["Average"], 3)
                    res[vm_id]["cpu_data"].append(float(rate))
                for i in memory_result:
                    vm_id = i["instanceId"]
                    rate = round(i["Average"], 3)
                    res[vm_id]["memory_data"].append(float(rate))
                for i in load_result:
                    vm_id = i["instanceId"]
                    rate = round(i["Average"], 3)
                    res[vm_id]["load_data"].append(float(rate))
            return {"result": True, "data": res}
        except Exception as e:
            logger.exception("get_monitor_data {}".format(resource_id_list))
            return {"result": False, "message": str(e)}

    obj_map = {
        "aliyun_ecs": {
            "namespace": "acs_ecs_dashboard",
            "metrics": ["cpu_user", "memory_usedutilization", "diskusage_utilization"],
        },
        "aliyun_cdn": {
            "namespace": "acs_cdn_dashboard",
            "metrics": [
                "BpsDataPerInterval",
                "TrafficDataPerInterval",
                "SrcBpsDataPerInterval",
                "SrcTrafficDataPerInterval",
                "QpsDataInterval",
                "HitRateInterval",
            ],
            "metric_sdk": {
                "BpsDataPerInterval": {
                    "request": "DescribeDomainBpsDataRequest",
                    "function": "describe_domain_bps_data_with_options",
                },
                "TrafficDataPerInterval": {
                    "request": "DescribeDomainTrafficDataRequest",
                    "function": "describe_domain_traffic_data_with_options",
                },
                "SrcBpsDataPerInterval": {
                    "request": "DescribeDomainSrcBpsDataRequest",
                    "function": "describe_domain_src_bps_data_with_options",
                },
                "SrcTrafficDataPerInterval": {
                    "request": "DescribeDomainSrcTrafficDataRequest",
                    "function": "describe_domain_src_traffic_data_with_options",
                },
                "QpsDataInterval": {
                    "request": "DescribeDomainQpsDataRequest",
                    "function": "describe_domain_qps_data_with_options",
                },
                "HitRateInterval": {
                    "request": "DescribeDomainHitRateDataRequest",
                    "function": "describe_domain_hit_rate_data_with_options",
                },
            },
        },
        "aliyun_firewall": {
            "namespace": "acs_waf_dashboard",
            "metrics": [
                "TotalRequestCount",
                "InBytes",
                "OutBytes",
                "WafReportSum",
                "BlacklistReportsSum",
                "AntiscanReportsSum",
                "CcCustomReportsSum",
                "RegionBlockReportsSum",
                "AntibotReportSum",
                "AntiScanBlockSum",
                "AntibotBlockSum",
                "WafBlockSum",
                "BlacklistBlockSum",
                "CcCustomBlockSum",
                "QPSCount",
            ],
            "metric_sdk": {
                "TotalRequestCount": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "Count",
                },
                "InBytes": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "InBytes",
                },
                "OutBytes": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "OutBytes",
                },
                "WafReportSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "WafReportSum",
                },
                "BlacklistReportsSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "BlacklistReportsSum",
                },
                "AntiscanReportsSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "AntiscanReportsSum",
                },
                "CcCustomReportsSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "CcCustomReportsSum",
                },
                "RegionBlockReportsSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "RegionBlockReportsSum",
                },
                "AntibotReportSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "AntibotReportSum",
                },
                "AntiScanBlockSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "AntiScanBlockSum",
                },
                "AntibotBlockSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "AntibotBlockSum",
                },
                "WafBlockSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "WafBlockSum",
                },
                "BlacklistBlockSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "BlacklistBlockSum",
                },
                "CcCustomBlockSum": {
                    "request": "DescribeFlowChartRequest",
                    "function": "describe_flow_chart_with_options",
                    "response_key": "CcCustomBlockSum",
                },
                "QPSCount": {
                    "request": "DescribePeakTrendRequest",
                    "function": "describe_peak_trend_with_options",
                    "response_key": "Count",
                },
            },
        },
        "aliyun_bucket": {
            "namespace": "acs_oss_dashboard",
            "metrics": [
                "Storage",
                "ObjectCount",
                "Availability",
                "RequestValidRate",
                "TotalRequestCount",
                "ValidRequestCount",
                "InternetSend",
                "InternetRecv",
                "IntranetSend",
                "IntranetRecv",
                "CdnSend",
                "CdnRecv",
                "SyncSend",
                "SyncRecv",
            ],
            "metric_attr_map": {
                "Storage": "storage_size_in_bytes",
                "ObjectCount": "object_count",
            },
        },
        "aliyun_mysql": {
            "namespace": "acs_rds_dashboard",
            "metrics": [
                "mysql.mem_usage",
                "mysql.cpu_usage",
                "ins_size",
                "mysql.disk_usage",
                "mysql.iops_usage",
                "mysql.iops",
                "mysql.bytes_sent",
                "mysql.bytes_received",
                "qps",
                "tps",
                "mysql.total_session",
                "mysql.active_session",
                "mysql.insert_select",
                "mysql.insert_ps",
                "mysql.select_ps",
                "mysql.replace_select",
                "mysql.update_ps",
                "mysql.delete_ps",
                "mysql.replace_ps",
                "Created_tmp_disk_tables_ps",
                "mysql.threads_connected",
                "mysql.threads_running",
                "mysql.select_scan",
                "mysql.innodb_data_fsyncs",
                "mysql.innodb_data_read",
                "mysql.innodb_data_written",
                "mysql.innodb_buffer_pool_reads_requests",
                "mysql.innodb_buffer_pool_write_requests",
                "mysql.innodb_bp_usage_pct",
                "mysql.innodb_bp_hit",
                "mysql.innodb_bp_dirty_pct",
                "mysql.innodb_log_writes",
                "mysql.innodb_log_writes_request",
                "mysql.innodb_os_log_fsyncs",
                "mysql.inno_rows_deleted",
                "mysql.inno_rows_read",
                "mysql.inno_rows_inserted",
                "mysql.inno_log_writes",
                "mysql.inno_rows_updated",
                "mysql.innodb_buffer_pool_pages_flushed",
                "innodb_row_lock_waits",
                "Innodb_row_lock_time",
                "innodb_row_lock_time_avg",
                "mysql.MyISAM_key_reads",
                "mysql.MyISAM_key_read_requests",
                "mysql.MyISAM_key_writes",
                "mysql.MyISAM_key_write_requests",
                "mysql.MyISAM_key_usage_ratio",
                "mysql.MyISAM_key_write_hit_ratio",
                "mysql.MyISAM_key_read_hit_ratio",
                "mysql.slave_sql_running",
                "mysql.slave_io_running",
                "mysql.slave_lag",
            ],
            "metric_groups": {
                "MySQL_MemCpuUsage": {"memusage": "mysql.mem_usage", "cpuusage": "mysql.cpu_usage"},
                "MySQL_DetailedSpaceUsage": {"ins_size": "ins_size"},
                "DiskUsage": {"disk_usage": "mysql.disk_usage"},
                "IOPSUsage": {"iops_usage": "mysql.iops_usage"},
                "MySQL_IOPS": {"io": "mysql.iops"},
                "MySQL_NetworkTraffic": {"sent_k": "mysql.bytes_sent", "recv_k": "mysql.bytes_received"},
                "MySQL_QPSTPS": {"QPS": "qps", "TPS": "tps"},
                "MySQL_Sessions": {"total_session": "mysql.total_session", "active_session": "mysql.active_session"},
                "MySQL_COMDML": {
                    "com_insert_select": "mysql.insert_select",
                    "com_insert": "mysql.insert_ps",
                    "com_select": "mysql.select_ps",
                    "com_replace_select": "mysql.replace_select",
                    "com_update": "mysql.update_ps",
                    "com_delete": "mysql.delete_ps",
                    "com_replace": "mysql.replace_ps",
                },
                "MySQL_TempDiskTableCreates": {"tb_tmp_disk": "Created_tmp_disk_tables_ps"},
                "MySQL_ThreadStatus": {
                    "threads_connected": "mysql.threads_connected",
                    "threads_running": "mysql.threads_running",
                },
                "MySQL_SelectScan": {"select_scan": "mysql.select_scan"},
                "Mysql_DataFSyncs": {"innodb_data_fsyncs": "mysql.innodb_data_fsyncs"},
                "MySQL_InnoDBDataReadWriten": {
                    "inno_data_read": "mysql.innodb_data_read",
                    "inno_data_written": "mysql.innodb_data_written",
                },
                "MySQL_InnoDBLogRequests": {
                    "ibuf_request_r": "mysql.innodb_buffer_pool_reads_requests",
                    "ibuf_request_w": "mysql.innodb_buffer_pool_write_requests",
                },
                "MySQL_InnoDBBufferRatio": {
                    "ibuf_use_ratio": "mysql.innodb_bp_usage_pct",
                    "ibuf_read_hit": "mysql.innodb_bp_hit",
                    "ibuf_dirty_ratio": "mysql.innodb_bp_dirty_pct",
                },
                "MySQL_InnoDBLogWrites": {
                    "Innodb_log_writes": "mysql.innodb_log_writes",
                    "Innodb_log_write_requests": "mysql.innodb_log_writes_request",
                    "Innodb_os_log_fsyncs": "mysql.innodb_os_log_fsyncs",
                },
                "MySQL_RowDML": {
                    "inno_row_delete": "mysql.inno_rows_deleted",
                    "inno_row_readed": "mysql.inno_rows_read",
                    "inno_row_insert": "mysql.inno_rows_inserted",
                    "Inno_log_writes": "mysql.inno_log_writes",
                    "inno_row_update": "mysql.inno_rows_updated",
                },
                "Mysql_BufferPool": {"innodb_buffer_pool_pages_flushed": "mysql.innodb_buffer_pool_pages_flushed"},
                "MySQL_ROW_LOCK": {
                    "innodb_row_lock_waits": "innodb_row_lock_waits",
                    "innodb_row_lock_time": "Innodb_row_lock_time",
                    "innodb_row_lock_time_avg": "innodb_row_lock_time_avg",
                },
                "MySQL_MyISAMKeyReadWrites": {
                    "myisam_keyr": "mysql.MyISAM_key_reads",
                    "myisam_keyr_r": "mysql.MyISAM_key_read_requests",
                    "myisam_keyw": "mysql.MyISAM_key_writes",
                    "myisam_keyr_w": "mysql.MyISAM_key_write_requests",
                },
                "MySQL_MyISAMKeyBufferRatio": {
                    "Key_usage_ratio": "mysql.MyISAM_key_usage_ratio",
                    "Key_read_hit_ratio": "mysql.MyISAM_key_write_hit_ratio",
                    "Key_write_hit_ratio": "mysql.MyISAM_key_read_hit_ratio",
                },
                "MySQL_ReplicationThread": {
                    "sqlthread": "mysql.slave_sql_running",
                    "iothread": "mysql.slave_io_running",
                },
                "MySQL_ReplicationDelay": {"replication-lag": "mysql.slave_lag"},
            },
        },
        "aliyun_pgsql": {
            "namespace": "acs_rds_dashboard",
            "metrics": [
                "cpu_usage",
                "mem_usage",
                "disk_usage",
                "disk_used",
                "iops",
                "r_s",
                "w_s",
                "network_io",
                "network_in_io",
                "network_out_io",
                "total_session",
                "idle_in_transaction",
                "active_session",
                "waiting_connection",
                "tps",
                "deadlocks",
                "xact_rollback",
                "xact_commit",
            ],
            "metric_groups": {
                "CpuUsage": {"cpu_usage": "cpu_usage"},
                "MemoryUsage": {"mem_usage": "mem_usage"},
                "DiskUsage": {"disk_usage": "disk_usage"},
                "PgSQL_DetailedSpaceUsage": {"data_size": "disk_used"},
                # "PgSQL_SpaceUsage": {"space": "disk_used"},
                # "PgSQL_IOPS": {"data_iops": "iops"},
                "PgSQLConnections": {
                    "mean_total_session": "total_session",
                    "mean_idle_connection": "idle_in_transaction",
                    "mean_active_session": "active_session",
                    "mean_waiting_connection": "waiting_connection",
                },
                "PgSQLQPSTPS": {
                    "mean_tps": "tps",
                    "mean_commits_delta": "xact_commit",
                    "mean_deadlocks_delta": "deadlocks",
                    "mean_rollbacks_delta": "xact_rollback",
                },
                "PgSQLLocalIOSTAT": {
                    "mean_local_iops": "iops",
                    "mean_local_iops_read": "r_s",
                    "mean_local_iops_write": "w_s",
                },
                "PgSQLNetIOSTAT": {
                    "mean_network_io": "network_io",
                    "mean_network_in_io": "network_in_io",
                    "mean_network_out_io": "network_out_io",
                },
                "PostgreSQL_Network": {
                    "network_io": "network_io",
                    "network_in_io": "network_in_io",
                    "network_out_io": "network_out_io",
                },
                "PostgreSQL_Sessions": {
                    "total_session": "total_session",
                    "idle_in_transaction": "idle_in_transaction",
                    "active_session": "active_session",
                    "waiting_connection": "waiting_connection",
                },
                "PostgreSQL_TPS": {
                    "tps": "tps",
                    "deadlocks": "deadlocks",
                    "xact_rollback": "xact_rollback",
                    "xact_commit": "xact_commit",
                },
            },
        },
        "aliyun_redis": {
            "namespace": "acs_kvstore_dashboard",
            "metrics": [
                "CpuUsage",
                "MemoryUsage",
                "UsedMemory",
                "TotalQps",
                "GetQps",
                "PutQps",
                "ConnectionUsage",
                "UsedConnection",
                "OutFlow",
                "IntranetOutRatio",
                "InFlow",
                "IntranetInRatio",
                "Redis_Avg_Rt_Monitor_AvgRt",
                "Redis_Basic_Monitor_Keys",
                "Hit_rate",
                "Hit_hit",
                "Hit_miss",
            ],
            "metric_groups": {
                "CpuUsage": {"CpuUsage": "CpuUsage"},
                "MemoryUsage": {"memoryUsage": "MemoryUsage"},
                "UsedMemory": {"UsedMemory": "UsedMemory"},
                "UsedQPS": {"TotalQps": "TotalQps", "GetQps": "GetQps", "PutQps": "PutQps"},
                "UsedConnection": {"ConnectionUsage": "ConnectionUsage", "UsedConnection": "UsedConnection"},
                "IntranetOut": {"OutFlow": "OutFlow"},
                "IntranetOutRatio": {"intranetOutRatio": "IntranetOutRatio"},
                "IntranetIn": {"InFlow": "InFlow"},
                "IntranetInRatio": {"intranetInRatio": "IntranetInRatio"},
                "Redis_Avg_Rt_Monitor": {"AvgRt": "Redis_Avg_Rt_Monitor_AvgRt"},
                "Redis_Basic_Monitor": {"Keys": "Redis_Basic_Monitor_Keys"},
                "Hit_Rate_Monitor": {"hit_rate": "Hit_rate", "hit": "Hit_hit", "miss": "Hit_miss"},
            },
        },
        "aliyun_mongodb": {
            "namespace": "acs_kvstore_dashboard",
            "metrics": [
                "cpu_usage",
                "mem_usage",
                "data_iops",
                "iops_usage",
                "ins_size",
                "disk_usage",
                "insert_qps",
                "network_in",
                "network_out",
                "repl_lag",
                "avg_rt",
                "conn_usage",
                "current_conn",
            ],
            "metric_groups": {
                "CpuUsage": {"cpu_usage": "cpu_usage"},
                "MemoryUsage": {"mem_usage": "mem_usage"},
                "MongoDB_IOPS": {"data_iops": "data_iops"},
                "IOPSUsage": {"iops_usage": "iops_usage"},
                "MongoDB_DetailedSpaceUsage": {"ins_size": "ins_size"},
                "DiskUsage": {"disk_usage": "disk_usage"},
                "MongoDB_Opcounters": {"insert": "insert_qps"},
                "MongoDB_Network": {"bytes_in": "network_in", "bytes_out": "network_out"},
                "MongoDB_Repl_Lag": {"repl_lag": "repl_lag"},
                "MongoDB_RT": {"avg_rt": "avg_rt"},
                "ConnectionUsage": {"conn_usage": "conn_usage"},
                "MongoDB_TotalConns": {"current_conn": "current_conn"},
            },
        },
        "aliyun_kafka_inst": {
            "namespace": "acs_kafka",
            "metrics": [
                "instance_message_num_input",
                "instance_message_num_output",
                "instance_reqs_output",
                "instance_disk_capacity",
            ],
        },
        "aliyun_eip": {
            "namespace": "acs_vpc_eip",
            "metrics": [
                "net_tx.rate",
                "net_rx.rate",
                "net_out.rate_percentage",
                "net_in.rate_percentage",
                "net_txPkgs.rate",
                "net_rxPkgs.rate",
                "out_ratelimit_drop_speed",
                "in_ratelimit_drop_speed",
            ],
        },
    }

    def get_cdn_metric_value(self, metric, start_time, end_time, interval, **kwargs):
        value = None
        try:
            metric_request = self.obj_map["aliyun_cdn"]["metric_sdk"][metric]["request"]
            metric_function = self.obj_map["aliyun_cdn"]["metric_sdk"][metric]["function"]
            request = getattr(cdn_20180510_models, metric_request)()
            request.start_time = local_to_utc(start_time)
            request.end_time = local_to_utc(end_time)
            request.interval = interval
            runtime = util_models.RuntimeOptions()
            resp = getattr(self.cdn_client, metric_function)(request, runtime)
            result = TeaCore.to_map(resp.body)
            data_module = result.get(metric, {}).get("DataModule", [])
            if data_module:
                value = data_module[-1].get("Value")
        except Exception:
            logger.exception("get_cdn_monitor_data")
        return value

    def get_firewall_metric_value(self, instance_id, metric, start_time, end_time, interval, **kwargs):
        value = None
        try:
            metric_request = self.obj_map["aliyun_firewall"]["metric_sdk"][metric]["request"]
            metric_function = self.obj_map["aliyun_firewall"]["metric_sdk"][metric]["function"]
            metric_response_key = self.obj_map["aliyun_firewall"]["metric_sdk"][metric]["response_key"]

            request = getattr(waf_openapi_20211001_models, metric_request)()
            request.start_timestamp = int(datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp())
            request.end_timestamp = int(datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp())
            request.instance_id = instance_id
            request.interval = interval
            runtime = util_models.RuntimeOptions()
            resp = getattr(self.waf_client, metric_function)(request, runtime)
            result = TeaCore.to_map(resp.body)
            flow_chart = result.get("FlowChart", [])
            if flow_chart:
                value = flow_chart[-1].get(metric_response_key)
        except Exception:
            logger.exception("get_cdn_monitor_data")
        return value

    def get_bucket_stat(self, bucket_name, buckets=None, **kwargs):
        """
        查询OSS存储桶统计信息
        """
        if not buckets:
            bucket_result = self.list_buckets()
            if bucket_result.get("result", False):
                buckets = bucket_result.get("data", [])
            buckets = {bucket.get("Name"): bucket for bucket in buckets}
        if not buckets:
            return {"result": False, "message": "未获取到存储桶信息"}
        region = buckets.get(bucket_name, {}).get("Location")
        try:
            bucket = oss2.Bucket(self.auth, f"http://{region}.aliyuncs.com", bucket_name)
            # 获取存储空间的统计信息。
            result = bucket.get_bucket_stat()
            if result.status == 200:
                return result.__dict__
            logger.warning("get_bucket_stat error")
            return {}
        except Exception:
            logger.exception("get_bucket_stat error")
            return {}

    def get_bucket_stat_metric_value(self, metric_stat_key, **kwargs):
        bucket_stat = kwargs.get("bucket_stat", {})
        if not bucket_stat:
            return
        if metric_stat_key:
            value = bucket_stat.get(metric_stat_key)
            return value

    def get_mysql_metric_data(self, instance_id, metric_groups, start_time, end_time, interval, **kwargs):
        """
        DescribeDBInstancePerformance
        """
        request = rds_20140815_models.DescribeDBInstancePerformanceRequest()
        request.dbinstance_id = instance_id
        # 时间只到分钟级,把秒去掉,还保留UTC
        request.start_time = local_to_utc(start_time, utc_fmt="%Y-%m-%dT%H:%MZ")
        request.end_time = local_to_utc(end_time, utc_fmt="%Y-%m-%dT%H:%MZ")
        request.key = ",".join(metric_groups)
        runtime = util_models.RuntimeOptions()
        metric_data = []
        try:
            resp = self.rds_client.describe_dbinstance_performance_with_options(request, runtime)
            result = TeaCore.to_map(resp.body)
            pks = result.get("PerformanceKeys", {}).get("PerformanceKey", [])
            for pk in pks:
                key = pk.get("Key")
                value_format = pk.get("ValueFormat")
                metric_keys = value_format.split("&")
                values = pk.get("Values", {}).get("PerformanceValue", [])
                value = (values and values[-1]) or {}
                key_value = value.get("Value")
                timestamp = value.get("Date")
                if key_value is None:
                    continue
                value_list = key_value.split("&")
                for index, metric_value in enumerate(value_list):
                    metric_dict = dict(
                        key=key,
                        metric=metric_keys[index],
                        value=round(float(metric_value), 3),
                        timestamp=utc_to_ts(timestamp, utc_fmt="%Y-%m-%dT%H:%M:%SZ") * 1000,
                    )
                    metric_data.append(metric_dict)
            return metric_data
        except Exception:
            logger.exception(f"get_mysql_metric_data metric_data:{metric_data}")
            return metric_data

    def get_redis_monitor_data(self, instance_id, metric_groups, start_time, end_time, interval, **kwargs):
        """
        DescribeHistoryMonitorValues
        """
        # 把指标分成5个一批
        metric_data = []

        def get_interval(interval):
            if interval == 300:
                return "05m"
            return "01m"

        request = r_kvstore_20150101_models.DescribeHistoryMonitorValuesRequest()
        request.instance_id = instance_id
        request.start_time = local_to_utc(start_time)
        request.end_time = local_to_utc(end_time)
        request.interval_for_history = get_interval(interval)
        runtime = util_models.RuntimeOptions()

        try:
            for _metric_group in metric_groups:
                request.monitor_keys = _metric_group
                resp = self.kvs_client.describe_history_monitor_values_with_options(request, runtime)
                result = TeaCore.to_map(resp.body)
                mh = result.get("MonitorHistory", "{}")
                monitor_result = json.loads(mh)
                for utc_str, metric_value in monitor_result.items():
                    for metric, value in metric_value.items():
                        if value is None:
                            continue
                        metric_dict = dict(
                            key=_metric_group,
                            timestamp=utc_to_ts(utc_str) * 1000,
                            metric=metric,
                            value=round(float(value), 3),
                        )
                        metric_data.append(metric_dict)
            return metric_data
        except Exception:
            logger.exception(f"get_redis_monitor_data metric_data:{metric_data}")
            return metric_data

    def get_mongodb_metric_data(self, instance_id, metric_groups, start_time, end_time, interval, **kwargs):
        """
        DescribeDBInstancePerformance
        """
        request = dds_20151201_models.DescribeDBInstancePerformanceRequest()
        request.dbinstance_id = instance_id
        # 时间只到分钟级,把秒去掉,还保留UTC
        request.start_time = local_to_utc(start_time, utc_fmt="%Y-%m-%dT%H:%MZ")
        request.end_time = local_to_utc(end_time, utc_fmt="%Y-%m-%dT%H:%MZ")
        request.key = ",".join(metric_groups)
        runtime = util_models.RuntimeOptions()
        metric_data = []
        try:
            resp = self.dds_client.describe_dbinstance_performance_with_options(request, runtime)
            result = TeaCore.to_map(resp.body)
            pks = result.get("PerformanceKeys", {}).get("PerformanceKey", [])
            for pk in pks:
                key = pk.get("Key")
                value_format = pk.get("ValueFormat")
                metric_keys = value_format.split("&")
                values = pk.get("PerformanceValues", {}).get("PerformanceValue", [])
                value = (values and values[-1]) or {}
                key_value = value.get("Value")
                timestamp = value.get("Date")
                if key_value is None:
                    continue
                value_list = key_value.split("&")
                for index, metric_value in enumerate(value_list):
                    metric_dict = dict(
                        key=key,
                        metric=metric_keys[index],
                        value=round(float(metric_value), 3),
                        timestamp=utc_to_ts(timestamp, utc_fmt="%Y-%m-%dT%H:%M:%SZ") * 1000,
                    )
                    metric_data.append(metric_dict)
            return metric_data
        except Exception:
            logger.exception(f"get_mongodb_metric_data metric_data:{metric_data}")
            return metric_data

    def get_weops_monitor_data(self, **kwargs):
        """
        获取监控信息详情(weops专属)
        :param kwargs:
        :return:
        """
        start_time = str(kwargs.get("StartTime", datetime.datetime.now() + datetime.timedelta(minutes=-60)))
        end_time = str(kwargs.get("EndTime", datetime.datetime.now() + datetime.timedelta(minutes=-50)))

        data = {}
        res = {}
        data["Length"] = 1000
        data["Period"] = kwargs.get("Period", "300")  # 时间间隔为5分钟
        data["StartTime"] = kwargs.get("StartTime", start_time)
        data["EndTime"] = kwargs.get("EndTime", end_time)
        # 字符串时间前移1分钟,并再转成字符串
        data["StartTime"] = str(
            datetime.datetime.strptime(data["StartTime"], "%Y-%m-%d %H:%M:%S") + datetime.timedelta(minutes=-1)
        )
        data["EndTime"] = str(
            datetime.datetime.strptime(data["EndTime"], "%Y-%m-%d %H:%M:%S") + datetime.timedelta(minutes=-1)
        )
        resource_id_list = list(set(kwargs["resourceId"].split(",")))
        resources = kwargs.get("context", {}).get("resources", [])
        if not resources:
            return {"result": False, "message": "未获取到实例信息"}
        bk_obj_id = resources[0]["bk_obj_id"]
        default_metric = self.obj_map.get(bk_obj_id, {}).get("metrics", [])
        metrics = kwargs.get("Metrics", default_metric) or default_metric
        try:
            timestamp = int(datetime.datetime.strptime(data["EndTime"], "%Y-%m-%d %H:%M:%S").timestamp() * 1000)

            if bk_obj_id == "aliyun_cdn":
                for metric in metrics:
                    metric_value = self.get_cdn_metric_value(
                        metric, data["StartTime"], data["EndTime"], data["Period"], **kwargs
                    )
                    if metric_value is None:
                        continue
                    res.setdefault(resource_id_list[0], {}).setdefault(metric, []).append([timestamp, metric_value])
                return {"result": True, "data": res}
            elif bk_obj_id == "aliyun_firewall":
                for metric in metrics:
                    for resource_id in resource_id_list:
                        metric_value = self.get_firewall_metric_value(
                            resource_id, metric, data["StartTime"], data["EndTime"], data["Period"], **kwargs
                        )
                        if metric_value is None:
                            continue
                        res.setdefault(resource_id, {}).setdefault(metric, []).append([timestamp, metric_value])
                return {"result": True, "data": res}
            elif bk_obj_id == "aliyun_bucket":
                for resource_id in resource_id_list:
                    bucket_stat = self.get_bucket_stat(resource_id)
                    if not bucket_stat:
                        continue
                    for metric in metrics:
                        metric_stat_key = self.obj_map.get(bk_obj_id, {}).get("metric_attr_map", {}).get(metric)
                        if not metric_stat_key:
                            continue
                        metric_value = self.get_bucket_stat_metric_value(
                            metric_stat_key, bucket_stat=bucket_stat, **kwargs
                        )
                        if metric_value is None:
                            continue
                        res.setdefault(resource_id, {}).setdefault(metric, []).append([timestamp, metric_value])
                for i in self.obj_map.get(bk_obj_id, {}).get("metric_attr_map", {}).keys():
                    if i in metrics:
                        metrics.remove(i)
            elif bk_obj_id in ["aliyun_mysql", "aliyun_pgsql"]:
                for resource_id in resource_id_list:
                    metrics_group = self.obj_map.get(bk_obj_id, {}).get("metric_groups", {})
                    rds_metrics = self.get_mysql_metric_data(
                        resource_id,
                        metrics_group.keys(),
                        data["StartTime"],
                        data["EndTime"],
                        data["Period"],
                    )
                    if not rds_metrics:
                        continue
                    for metric in rds_metrics:
                        metric_name = metrics_group.get(metric["key"], {}).get(metric["metric"], "")
                        if metric_name in metrics:
                            res.setdefault(resource_id, {}).setdefault(metric_name, []).append(
                                [metric["timestamp"], metric["value"]]
                            )
                return {"result": True, "data": res}
            elif bk_obj_id == "aliyun_redis":
                for resource_id in resource_id_list:
                    metrics_group = self.obj_map.get(bk_obj_id, {}).get("metric_groups", {})
                    redis_metric = self.get_redis_monitor_data(
                        resource_id,
                        metrics_group,
                        data["StartTime"],
                        data["EndTime"],
                        data["Period"],
                    )
                    if not redis_metric:
                        continue
                    for metric in redis_metric:
                        metric_name = metrics_group.get(metric["key"], {}).get(metric["metric"], "")
                        if metric_name in metrics:
                            res.setdefault(resource_id, {}).setdefault(metric_name, []).append(
                                [metric["timestamp"], metric["value"]]
                            )
                return {"result": True, "data": res}
            elif bk_obj_id == "aliyun_mongodb":
                for resource_id in resource_id_list:
                    metrics_group = self.obj_map.get(bk_obj_id, {}).get("metric_groups", {})
                    mongodb_metrics = self.get_mongodb_metric_data(
                        resource_id,
                        metrics_group.keys(),
                        data["StartTime"],
                        data["EndTime"],
                        data["Period"],
                    )
                    if not mongodb_metrics:
                        continue
                    for metric in mongodb_metrics:
                        metric_name = metrics_group.get(metric["key"], {}).get(metric["metric"], "")
                        if metric_name in metrics:
                            res.setdefault(resource_id, {}).setdefault(metric_name, []).append(
                                [metric["timestamp"], metric["value"]]
                            )
                return {"result": True, "data": res}
            data["Namespace"] = self.obj_map.get(bk_obj_id, {}).get("namespace", "")
            vm_list_all = resource_id_list
            vm_lists = []
            for i in range(len(vm_list_all) // 40 + 1):
                vm_lists.append(vm_list_all[i * 40 : (i + 1) * 40])
            for vm_list in vm_lists:

                dimensions = []
                for i in vm_list:
                    if bk_obj_id == "aliyun_bucket":
                        dimensions.append({"BucketName": i})
                    else:
                        dimensions.append({"instanceId": i})
                data["Dimensions"] = json.dumps(dimensions)
                #  指标维度
                for metric in metrics:

                    data["MetricName"] = metric
                    result = self.monitor_data(**data)["data"]
                    for i in result:
                        vm_id = i.get("instanceId") or i.get("BucketName")  # 兼容bucket的返回
                        timestamp = i["timestamp"]
                        if "Average" in i:
                            value = i["Average"]
                        elif "Value" in i:
                            value = i["Value"]
                        elif "Maximum" in i:
                            value = i["Maximum"]
                        else:
                            continue
                        if value is None:
                            continue
                        rate = round(float(value), 3)
                        if vm_id not in resource_id_list:
                            continue
                        res.setdefault(vm_id, {}).setdefault(metric, []).append([timestamp, rate])
            return {"result": True, "data": res}

        except Exception as e:
            logger.exception("get_monitor_data {}".format(resource_id_list))
            return {"result": False, "message": str(e)}

    def _get_vm_list(self, **kwargs):
        """
        获取实例列表
        :param kwargs:
        :return:
        """
        try:
            kwargs["PageNumber"] = "1"
            kwargs["PageSize"] = 50
            request = self._set_vm_info_params(**kwargs)
            ali_response = self.client.do_action_with_exception(request)
            ali_result = json.loads(ali_response)
            ins_list = []
            total_count = ali_result["TotalCount"]
            ins_list.extend(ali_result["Instances"]["Instance"])
            page = total_count // 50 if total_count // 50 == 0 else total_count // 50 + 1
            for i in range(page):
                kwargs["PageNumber"] = str(i + 2)
                request = self._set_vm_info_params(**kwargs)
                ali_response = self.client.do_action_with_exception(request)
                ali_result = json.loads(ali_response)
                ins_list.extend(ali_result["Instances"]["Instance"])
            vm_list = []
            for i in ins_list:
                vm_list.append(i["InstanceId"])
            return vm_list
        except Exception as e:
            logger.exception("_get_vm_list")
            return {"result": False, "message": str(e)}

    def instance_security_group_action(self, **kwargs):
        """
        给实例绑定/解绑安全组
        :param kwargs:
            InstanceId: vm id
            SecurityGroupIds: list 安全组id集合
        :type kwargs:
        :return:
        :rtype:
        """
        try:
            request = ModifyInstanceAttributeRequest.ModifyInstanceAttributeRequest()
            list_optional_params = ["InstanceId", "SecurityGroupIds"]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request, True)
            return {"result": True}
        except Exception as e:
            logger.exception("vm_add_security_group")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    #  -------------------标签--------------------------

    def tag_resources(self, **kwargs):
        """
        为指定的ECS资源列表统一创建并绑定标签
        :param kwargs:
                    ResourceId.N：类型：RepeatList。必选。描述：资源ID，N的取值范围为1~50。示例：["id1", "id2", ...]
                    ResourceType：类型：String。必选。描述：资源类型定义。取值范围：instance：ECS实例、disk：磁盘、
                snapshot：快照、image：镜像、securitygroup：安全组、volume：存储卷、eni：弹性网卡、ddh：专有宿主机、
                keypair：SSH密钥对、launchtemplate：启动模板
                    Tag.N.Key：类型：String。描述：资源的标签键。N的取值范围：1~20。一旦传入该值，则不允许为空字符串。
                最多支持128个字符，不能以aliyun和acs:开头，不能包含http://或者https://。
                    Tag.N.Value：类型：String。描述：资源的标签值。N的取值范围：1~20。一旦传入该值，可以为空字符串。
                最多支持128个字符，不能以acs:开头，不能包含http://或者https://。
                注：参数Tag中至少有一对标签,示例：[{key:value},..]
        :return:
        """
        try:
            request = TagResourcesRequest.TagResourcesRequest()
            list_required_params = ["ResourceIds", "ResourceType", "Tag"]
            request = set_required_params(request, list_required_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("tag_resources：" + kwargs["ResourceType"] + ":" + kwargs["ResourceIds"])
            return {"result": False, "message": str(e)}

    def list_resource_tags(self, **kwargs):
        """
        查询一个或多个ECS资源已经绑定的标签列表。
        请求中至少指定一个参数：ResourceId.N、Tag.N（Tag.N.Key与Tag.N.Value）或者TagFilter.N，以确定查询对象。
        同时指定下列参数时，返回结果中仅包含同时满足这两个条件的ECS资源。
            Tag.N和ResourceId.N
            TagFilter.N和ResourceId.N
        :param kwargs:
                    ResourceType：类型：String。必选。描述：资源类型定义。取值范围：instance：ECS实例、disk：磁盘、
                snapshot：快照、image：镜像、securitygroup：安全组、volume：存储卷、eni：弹性网卡、ddh：专有宿主机、
                keypair：SSH密钥对、launchtemplate：启动模板
                    TagFilter.N.TagKey：类型：String。必选。描述：模糊查找ECS资源时使用的标签键。标签键长度的取值范围：1~128。
                N的取值范围：1~5
                TagFilter.N用于模糊查找绑定了指定标签的ECS资源，由一个键和一个或多个值组成。模糊查询可能会有2秒延时，
                仅支持模糊过滤后资源数小于等于5000的情况。
                    TagFilter.N.TagValues.N：类型：RepeatList。描述：模糊查找ECS资源时使用的标签值。标签值长度的取值范围：1~128。
                N的取值范围：1~5
                    NextToken：类型：String。描述：下一个查询开始Token。
                    ResourceId.N：类型：RepeatList。描述：ECS资源ID。N的取值范围：1~50.示例：["id1", "id2", ...]
                    Tag.N.Key：类型：String。描述：精确查找ECS资源时使用的标签键。标签键长度的取值范围：1~128。
                N的取值范围：1~20。Tag.N用于精确查找绑定了指定标签的ECS资源，由一个键值对组成
                    Tag.N.Value：类型：String。描述：精确查找ECS资源时使用的标签值。标签值长度的取值范围：1~128。
                N的取值范围：1~20
                注：Tag示例：[{key: value}, ...]。TagFilter示例：[{key: ["v1", "v2", ...]}, ...].
        :return：
                 示例：{"result": True,
                        "data":[
                                {
                                    "ResourceId": "i-wz9dp2j44sqyukygtaqb",
                                    "TagKey": "1",
                                    "ResourceType": "instance",
                                    "TagValue": ""
                                },
                                {
                                    "ResourceId": "i-wz97jccanlw7pf0vc5k0",
                                    "TagKey": "test",
                                    "ResourceType": "instance",
                                    "TagValue": "1111"
                                }
                            ]
                        }
        """
        request = ListTagResourcesRequest.ListTagResourcesRequest()
        list_optional_params = ["Tags", "ResourceIds", "ResourceIds", "TagFilters"]
        try:
            request.set_ResourceType(kwargs["ResourceType"])
            request = set_optional_params(request, list_optional_params, kwargs)
        except Exception as e:
            logger.exception("list_tag_resource")
            return {"result": False, "message": str(e)}
        return self._handle_list_request("tag", request)

    def untie_tag_resources(self, **kwargs):
        """
        为指定的ECS资源列表统一解绑标签。解绑后，如果该标签没有绑定其他任何资源，会被自动删除。
        :param kwargs:
                     ResourceId.N：类型：RepeatList。必选。描述：ECS资源ID。N的取值范围：1~50.示例：["id1", "id2", ...]
                     ResourceType：类型：String。必选。描述：资源类型定义。取值范围：instance：ECS实例、disk：磁盘、
                snapshot：快照、image：镜像、securitygroup：安全组、volume：存储卷、eni：弹性网卡、ddh：专有宿主机、
                keypair：SSH密钥对、launchtemplate：启动模板。
                    TagKey：类型：RepeatList。描述：标签键。
                    All：类型：Boolean。描述：是否解绑资源上全部的标签。当请求中未设置TagKey.N时，该参数才有效。取值范围：
                True、False，默认值：false。
        :return:
        """
        try:
            request = UntagResourcesRequest.UntagResourcesRequest()
            request.set_ResourceIds(kwargs["ResourceIds"])
            request.set_ResourceType(kwargs["ResourceType"])
            if "TagKeys" in kwargs:
                request.set_TagKeys(kwargs["TagKeys"])
            elif "All" in kwargs:
                request.set_All(kwargs["All"])
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("untie_tag_resources")
            return {"result": False, "message": str(e)}

    #  -----------------快照---------------------------------
    def create_snapshot(self, **kwargs):
        """
        为一块云盘创建一份快照。
        :param kwargs:
                    DiskId：类型：String。描述：云盘ID。
                    SnapshotName：类型：String。描述：快照的显示名称。长度为2~128个英文或中文字符。必须以大小字母或
                中文开头，不能以http://和https://开头。可以包含数字、半角冒号（:）、下划线（_）或者连字符（-）。为防止和
                自动快照的名称冲突，不能以auto开头。
                    Description：类型：String。描述：快照的描述。长度为2~256个英文或中文字符，不能以http://和
                https://开头。默认值：空。
                    RetentionDays：类型：Integer。描述：设置快照的保留时间，单位为天。保留时间到期后快照会被自动释放，
                取值范围：1~65536。默认值：空，表示快照不会被自动释放。
                    Category：类型：String。描述：快照类型。取值范围：Standard：普通快照、Flash：本地快照
                    ClientToken：类型：String。描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值
                唯一。ClientToken只支持ASCII字符，且不能超过64个字符。更多详情，请参见如何保证幂等性。
                    Tag.N.Key：类型：String。描述：快照的标签键。N的取值范围：1~20。一旦传入该值，则不允许为空字符串。
                最多支持128个字符，不能以aliyun和acs:开头，不能包含http://或者https://。
                    Tag.N.Value：类型：String。描述：快照的标签值。N的取值范围：1~20。一旦传入该值，可以为空字符串。
                最多支持128个字符，不能以acs:开头，不能包含http://或者https://。
        :return:data:ali_result["SnapshotId"]:快照id
        """
        try:
            request = CreateSnapshotRequest.CreateSnapshotRequest()
            request.set_DiskId(kwargs["DiskId"])
            list_optional_params = ["SnapshotName", "Description", "RetentionDays", "Category", "ClientToken", "Tags"]
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["SnapshotId"]}
        except Exception as e:
            logger.exception("create_snapshot")
            return {"result": False, "message": str(e)}

    def create_snapshot_group(self, **kwargs):
        """
        创建快照分组
        :param kwargs:
        InstanceId  String	否	实例ID。
        stantAccess  Boolean	否	是否开启快照极速可用
        InstantAccessRetentionDays int	否	设置快照极速可用的使用时间  单位：天，取值范围：1~65535 仅当InstantAccess=true时，该参数生效
        Name  String	否	ECS实例快照名称
        Description  String	否	描述
        ExcludeDiskId String []	否	实例中不需要创建快照的云盘ID
        DiskId  String []	否
        Tag list[] 否
        :return:
        """
        try:
            request = CreateSnapshotGroupRequest.CreateSnapshotGroupRequest()
            list_optional_params = [
                "InstanceId",
                "InstantAccess",
                "InstantAccessRetentionDays",
                "Name",
                "Description",
                "ExcludeDiskId",
                "DiskId",
                "Tags",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["SnapshotGroupId"]}
        except Exception as e:
            logger.exception("create_snapshot_group")
            return {"result": False, "message": str(e)}

    def delete_snapshot(self, snapshot_id, force=False):
        """
        删除指定的快照。如果需要取消正在创建的快照，也可以调用该接口删除快照，即取消创建快照任务。
        :param snapshot_id: 类型：String。必选。描述：快照 ID。
        :param force: 类型：Boolean。描述：是否强制删除有磁盘关联的快照。说明：删除后该磁盘无法重新初始化。
        :return:
        """
        try:
            request = DeleteSnapshotRequest.DeleteSnapshotRequest()
            request.set_SnapshotId(snapshot_id)
            request.set_Force(force)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete snapshot:" + snapshot_id)
            return {"result": False, "message": str(e)}

    @classmethod
    def _set_snapshot_info_params(cls, **kwargs):
        """
        设置快照信息参数
        :param kwargs:
        :return:
        """
        if kwargs.get("request"):
            request = kwargs["request"]
        else:
            request = DescribeInstancesRequest.DescribeInstancesRequest()
        list_optional_params = [
            "InstanceId",
            "DiskId",
            "SnapshotLinkId",
            "SnapshotIds",
            "Status",
            "Usage",
            "SourceDiskType",
            "ResourceGroupId",
            "KMSKeyId",
            "Filter.1.Key",
            "Filter.2.Key",
            "Filter.1.Value",
            "Filter.2.Value",
            "Tags",
            "Encrypted",
            "DryRun",
        ]  # 可选参数列表
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_accept_format("json")
        return request

    def list_snapshots(self, ids=None, **kwargs):
        """
        查询一台ECS实例或一块云盘所有的快照列表。
        InstanceId、DiskId和SnapshotIds不是必需的请求参数，但是可以构建过滤器逻辑，参数之间为逻辑与（And）关系。
        :param ids: 快照id
        :param kwargs:
                    InstanceId：类型：String。描述：指定的实例ID。
                    DiskId：类型：String。描述：指定的云盘设备ID。
                    SnapshotLinkId：类型：String。描述：快照链ID。
                    SnapshotIds：类型：String。描述：快照标识编码。取值可以由多个快照ID组成一个JSON数组，最多支持100个ID，
                ID之间用半角逗号（,）隔开。
                    PageNumber：类型：Integer。描述：快照列表的页码。起始值：1。默认值：1。
                    PageSize：类型：Integer。描述：分页查询时设置的每页行数。最大值：100。默认值：10。
                    SnapshotName：类型：String。描述：快照名称。
                    Status：类型：String。描述：快照状态。取值范围：progressing：正在创建的快照、accomplished：创建成功的快照
                failed：创建失败的快照、all（默认）：所有快照状态
                    Filter.1.Key：类型：String。描述：查询资源时的筛选键。取值必须为CreationStartTime。
                    Filter.2.Key：类型：String。描述：查询资源时的筛选键。取值必须为CreationEndTime。
                    Filter.1.Value：类型：String。描述：查询资源时的筛选值。取值必须为资源创建的开始时间（CreationStartTime）的取值。
                    Filter.2.Value：类型：String。描述：查询资源时的筛选值。取值必须为资源创建的结束时间（CreationEndTime）的取值。
                    Usage：类型：String。描述：快照是否被用作创建镜像或云盘。取值范围：image：使用快照创建了自定义镜像、
                disk：使用快照创建了云盘、image_disk：使用快照创建了数据盘和自定义镜像none：暂未使用
                    SourceDiskType：类型：String。描述：快照源云盘的云盘类型。取值范围：System：系统盘、Data：数据盘
                    Tag.N.Key：类型：String。描述：快照的标签键。N的取值范围：1~20。
                    Tag.N.Value：类型：String。描述：快照的标签值。N的取值范围：1~20。
                    Encrypted：类型：Boolean。描述：是否过滤加密快照。默认值：false。
                    ResourceGroupId：类型：String。描述：资源组ID。
                    DryRun：类型：Boolean。描述：是否只预检此次请求。
                    KMSKeyId：类型：String。描述：数据盘对应的KMS密钥ID。
        :return:
        """
        request = DescribeSnapshotsRequest.DescribeSnapshotsRequest()
        if ids:
            request.set_SnapshotIds(json.dumps(ids))
        kwargs["request"] = request
        request = self._set_snapshot_info_params(**kwargs)
        return self._handle_list_request_with_page("snapshot", request)

    def restore_snapshot(self, disk_id, snapshot_id):
        """
        使用磁盘的历史快照回滚至某一阶段的磁盘状态。
        调用该接口时，您需要注意：
            磁盘的状态必须为使用中（In_Use）的状态。
            磁盘挂载的实例的状态必须为已停止（Stopped)。
            指定的参数SnapshotId必须是由DiskId创建的历史快照。
        :param disk_id: 类型：String，必选。描述：指定的磁盘设备ID。
        :param snapshot_id: 类型：String，描述：需要恢复到某一磁盘阶段的历史快照ID。
        :return:
        """
        try:
            request = ResetDiskRequest.ResetDiskRequest()
            request.set_DiskId(disk_id)
            request.set_SnapshotId(snapshot_id)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("reset_disk: {}".format(disk_id))
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            if str(e).startswith("HTTP Status: 403 Error:IncorrectInstanceStatus"):
                message = "请先停止实例"
            return {"result": False, "message": message}

    def apply_auto_snapshot_policy(self, **kwargs):
        """
        为一块或者多块云盘应用自动快照策略。目标云盘已经应用了自动快照策略时，可以更换云盘当前自动快照策略。
        autoSnapshotPolicyId  String	是	目标自动快照策略ID
        diskIds  list[]	是	一块或多块云盘的ID。取值是JSON数组格式，云盘ID之间用半角逗号（,）隔开。
        :return:
        """
        try:
            required_list = ["autoSnapshotPolicyId", "diskIds"]
            checkout_required_parameters(required_list, kwargs)
            request = ApplyAutoSnapshotPolicyRequest.ApplyAutoSnapshotPolicyRequest()
            request.set_autoSnapshotPolicyId(kwargs.get("autoSnapshotPolicyId"))
            request.set_diskIds(kwargs.get("diskIds"))
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("apply auto snapshot policy failed")
            return {"result": False, "message": str(e)}

    def cancel_auto_snapshot_policy(self, **kwargs):
        """
        取消一块或者多块云盘的自动快照策略
        diskIds  String	是	目标云盘ID
        :return:
        """
        if "diskIds" not in kwargs:
            return {"result": False, "message": "need param diskIds"}
        request = CancelAutoSnapshotPolicyRequest.CancelAutoSnapshotPolicyRequest()
        request.set_diskIds(kwargs.get("diskIds"))
        ali_result = self._get_result(request, True)
        return {"result": True, "data": ali_result["RequestId"]}

    def list_auto_snapshot_policy(self, ids=None, **kwargs):
        """
        查询已创建的自动快照策略
        :param ids:  自动快照策略ID
        :param kwargs:
        :return:
        """
        if ids:
            kwargs["AutoSnapshotPolicyId"] = ids[0]
        request = DescribeAutoSnapshotPolicyExRequest.DescribeAutoSnapshotPolicyExRequest()
        list_optional_params = ["AutoSnapshotPolicyId", "PageNumber", "PageSize", "Tag"]
        request = set_optional_params(request, list_optional_params, kwargs)
        return self._handle_list_request_with_page("auto_snapshot_policy", request)

    # ------------------负载均衡------------------------------
    def create_load_balancer(self, **kwargs):
        """
        创建负载均衡实例
        :param kwargs:
            AddressType  String	否	负载均衡实例的网络类型
            InternetChargeType  String	否	公网类型实例的付费方式
            Bandwidth  Integer	否	监听的带宽峰值
            ClientToken  String	否
            LoadBalancerName  String	否	负载均衡实例的名称
            VpcId  String	否	负载均衡实例的所属的VPC ID
            VSwitchId  String	否	专有网络实例的所属的交换机ID
            MasterZoneId   String	否	负载均衡实例的主可用区ID
            SlaveZoneId  String	否	负载均衡实例的备可用区ID
            LoadBalancerSpec String	否	负载均衡实例的规格
            ResourceGroupId  String	否	企业资源组ID
            PayType  String	否	实例的计费类型
            PricingCycle  String	否	预付费公网实例的计费周期
            Duration  Integer	否	预付费公网实例的购买时长
            AutoPay  Boolean	否	是否是自动支付预付费公网实例的账单
            AddressIPVersion  String	否	负载均衡实例的IP版本，取值：ipv4或ipv6。
            Address  String	否	指定负载均衡实例的私网IP地址，该地址必须包含在交换机的目标网段下
            DeleteProtection  String	否	是否开启实例删除保护
            ModificationProtectionStatus  String	否 负载均衡修改保护状态
            ModificationProtectionReason  String	否	设置修改保护状态的原因
        :return:
        """
        try:
            request = CommonRequest()
            request.set_accept_format("json")
            request.set_domain("slb.{}.aliyuncs.com".format(self.RegionId))
            request.set_method("POST")
            request.set_protocol_type("https")
            request.set_version("2014-05-15")
            request.set_action_name("CreateLoadBalancer")
            params_dict = {"RegionId": self.RegionId}
            list_optional_params = [
                "AddressType",
                "InternetChargeType",
                "Bandwidth",
                "LoadBalancerName",
                "VpcId",
                "VSwitchId",
                "MasterZoneId",
                "SlaveZoneId",
                "LoadBalancerSpec",
                "ResourceGroupId",
                "PayType",
                "PricingCycle",
                "Duration",
                "AutoPay",
                "AddressIPVersion",
                "Address",
                "DeleteProtection",
                "ModificationProtectionStatus",
                "ModificationProtectionReason",
                "ClientToken",
            ]
            [params_dict.update({item: kwargs[item]}) for item in list_optional_params if item in kwargs]
            request = add_required_params(request, params_dict)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["LoadBalancerId"]}
        except Exception as e:
            logger.exception("create load balancer failed")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def delete_load_balancer(self, ins_id):
        """
        删除后付费的负载均衡实例/删除负载均衡
        :param kwargs:
            LoadBalancerId  String	是	负载均衡实例的ID。
        :return:
        """
        try:
            # if "LoadBalancerId" not in kwargs:
            #     return {"result": False, "message": "need param LoadBalancerId"}
            request = CommonRequest()
            request.set_accept_format("json")
            request.set_domain("slb.{}.aliyuncs.com".format(self.RegionId))
            request.set_method("POST")
            request.set_protocol_type("https")
            request.set_version("2014-05-15")
            request.set_action_name("DeleteLoadBalancer")
            params_dict = {"RegionId": self.RegionId, "LoadBalancerId": ins_id}
            request = add_required_params(request, params_dict)
            self.client.do_action(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete load balancer failed")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def list_load_balancers(self, ids=None, **kwargs):
        """
        查询已创建的负载均衡实例
        :param ids: 负载均衡id
        :param kwargs:
        :return:
        """
        try:
            if ids:
                kwargs["LoadBalancerId"] = ids[0]
            list_optional_params = [
                "ServerId",
                "AddressIPVersion",
                "LoadBalancerStatus",
                "LoadBalancerId",
                "LoadBalancerName",
                "ServerIntranetAddress",
                "AddressType",
                "InternetChargeType",
                "VpcId",
                "VSwitchId",
                "NetworkType",
                "Address",
                "MasterZoneId",
                "SlaveZoneId",
                "Tags",
                "PayType",
                "ResourceGroupId",
                "PageNumber",
                "PageSize",
            ]
            action_name = "DescribeLoadBalancers"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            result = self._handle_list_request_with_page_c("load_balancer", request)
            for index, items in enumerate(result["data"]):
                if items.get("resource_id"):
                    ret = self.get_load_balancer_detail(LoadBalancerId=items.get("resource_id"))
                    if not ret.get("result"):
                        continue
                    result["data"][index]["backend_servers"] = (
                        ret["data"]["BackendServers"].get("BackendServer")
                        if isinstance(ret["data"].get("BackendServers"), dict)
                        else []
                    )
                    if isinstance(ret["data"].get("ListenerPortsAndProtocal"), dict):
                        result["data"][index]["port"] = ret["data"]["ListenerPortsAndProtocal"].get(
                            "ListenerPortAndProtocal", []
                        )
            return result
        except Exception as e:
            logger.exception("list_load_balancer failed")
            return {"result": False, "message": str(e)}

    def get_load_balancer_detail(self, **kwargs):
        """
        查询指定负载均衡实例的详细信息
        :param kwargs:
        :return:
        """
        try:
            if "LoadBalancerId" not in kwargs:
                return {"result": False, "message": "need param LoadBalancerId"}
            list_optional_params = ["LoadBalancerId"]
            action_name = "DescribeLoadBalancerAttribute"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("list_load_balancer failed")
            return {"result": False, "message": str(e)}

    def list_server_certificates(self, ids=None, **kwargs):
        """
        查询指定地域的服务器证书列表
        :param ids: 服务器证书id
        :param kwargs:
        :return:
        """
        try:
            if ids:
                kwargs["ServerCertificateId"] = ids[0]
            request = DescribeServerCertificatesRequest.DescribeServerCertificatesRequest()
            list_optional_params = ["ServerCertificateId", "ResourceGroupId"]
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            data = self._format_resource_result("server_certificate", ali_result)
            return {"result": True, "data": data}
        except Exception as e:
            logger.exception("list_server_certificates failed")
            return {"result": False, "message": str(e)}

    def create_vserver_group(self, **kwargs):
        """
        添加后端服务器组并向指定的后端服务器组中添加后端服务器 / 虚拟服务器组新增
        :param kwargs:
        :return:
        """
        try:
            if "LoadBalancerId" not in kwargs:
                return {"result": False, "message": "need param LoadBalancerId"}
            list_optional_params = ["LoadBalancerId", "VServerGroupName", "BackendServers"]
            action_name = "CreateVServerGroup"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            if ali_result.get("Message"):
                raise Exception(ali_result["Message"])
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("create vserver group failed")
            return {"result": False, "message": str(e)}

    def delete_vserver_group(self, **kwargs):
        """
        删除服务器组
        :param kwargs:
        :return:
        """
        try:
            if "VServerGroupId" not in kwargs:
                return {"result": False, "message": "need param VServerGroupId"}
            list_optional_params = ["VServerGroupId"]
            action_name = "DeleteVServerGroup"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            if ali_result.get("Message"):
                raise Exception(ali_result["Message"])
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("delete vserver group failed")
            return {"result": False, "message": str(e)}

    def set_vserver_group(self, **kwargs):
        """
        修改虚拟服务器组的配置
        :param kwargs:
        :return:
        """
        try:
            if "VServerGroupId" not in kwargs:
                return {"result": False, "message": "need param VServerGroupId"}
            list_optional_params = ["VServerGroupId", "VServerGroupName", "BackendServers"]
            action_name = "SetVServerGroupAttribute"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            if ali_result.get("Message"):
                raise Exception(ali_result["Message"])
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("set vserver group failed")
            return {"result": False, "message": str(e)}

    def list_vserver_groups(self, load_balancer_id, **kwargs):
        """
        查询服务器组列表
        :param kwargs:
        :return:
        """
        try:
            if not load_balancer_id:
                return {"result": False, "message": "need param LoadBalancerId"}
            kwargs["LoadBalancerId"] = load_balancer_id
            kwargs["IncludeRule"] = True
            kwargs["IncludeListener"] = True
            list_optional_params = ["LoadBalancerId", "IncludeRule", "IncludeListener"]
            action_name = "DescribeVServerGroups"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            ali_res = self._get_result_c(request, True)
            data = self._format_resource_result("vserver_groups", ali_res)
            for index, item in enumerate(data):
                if item.get("resource_id"):
                    ret = self.get_vserver_group(VServerGroupId=item["resource_id"])
                    if ret["result"]:
                        item["backend_servers"] = ret["data"]["BackendServers"]["BackendServer"]
                        item["load_balancer"] = ret["data"].get("LoadBalancerId", "")
            return {"result": True, "data": data}
        except Exception as e:
            logger.exception("list_vserver_groups failed")
            return {"result": False, "message": str(e)}

    def get_vserver_group(self, **kwargs):
        """
        查询服务器组的详细信息
        :param kwargs:
        :return:
        """
        if "VServerGroupId" not in kwargs:
            return {"result": False, "message": "need param VServerGroupId"}
        list_optional_params = ["VServerGroupId"]
        action_name = "DescribeVServerGroupAttribute"
        request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
        response = self.client.do_action(request)
        ali_result = json.loads(response)
        return {"result": True, "data": ali_result}

    def add_vserver_group_backend_servers(self, **kwargs):
        """
        向指定的后端服务器组中添加后端服务器
        :param kwargs:
        :return:
        """
        try:
            required_list = ["VServerGroupId", "BackendServers"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = ["VServerGroupId", "BackendServers"]
            action_name = "AddVServerGroupBackendServers"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("add_vserver_group_backend_servers failed")
            return {"result": False, "message": str(e)}

    def delete_vserver_group_backend_servers(self, **kwargs):
        """
        删除指定的后端服务器组中的后端服务器
        :param kwargs:
        :return:
        """
        try:
            required_list = ["VServerGroupId", "BackendServers"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = ["VServerGroupId", "BackendServers"]
            action_name = "RemoveVServerGroupBackendServers"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("delete vserver group backend servers failed")
            return {"result": False, "message": str(e)}

    def modify_vserver_group_backend_servers(self, **kwargs):
        """
        替换服务器组中的后端服务器
        :param kwargs:
        :return:
        """
        try:
            required_list = ["VServerGroupId"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = ["VServerGroupId", "OldBackendServers", "NewBackendServers"]
            action_name = "ModifyVServerGroupBackendServers"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("modify_vserver_group_backend_servers failed")
            return {"result": False, "message": str(e)}

    def create_load_balancer_tcp_listen(self, **kwargs):
        """
        创建负载均衡TCP监听
        :param kwargs:
            LoadBalancerId  String	是	负载均衡实例的ID
            Bandwidth  Integer	是	监听的带宽峰值
            ListenerPort Integer	是	负载均衡实例前端使用的端口
            BackendServerPort Integer	否	负载均衡实例后端使用的端口
            XForwardedFor String	否	是否通过X-Forwarded-For获取客户端请求的真实IP
            Scheduler  String	否	调度算法
            StickySession  String	是	是否开启会话保持
            StickySessionType  String	否	Cookie的处理方式
            CookieTimeout  Integer	否	Cookie超时时间
            Cookie  String	否	服务器上配置的Cookie
            HealthCheck  String	是	是否开启健康检查
            HealthCheckMethod  String	否	监听HTTP类型健康检查的健康检查方法
            HealthCheckDomain  String	否	用于健康检查的域名
            HealthCheckURI  String	否	用于健康检查的URI。
            HealthyThreshold  Integer	否	健康检查连续成功多少次后，将后端服务器的健康检查状态由fail判定为success
            UnhealthyThreshold  Integer	否	健康检查连续失败多少次后，将后端服务器的健康检查状态由success判定为fail
            HealthCheckTimeout  Integer	否	接收来自运行状况检查的响应需要等待的时间。如果后端ECS在指定的时间内没有正确响应，则判定为健康检查失败
            HealthCheckConnectPort  Integer	否	健康检查使用的端口。
            HealthCheckInterval  Integer	否	健康检查的时间间隔
            HealthCheckHttpCode  String	否	健康检查正常的HTTP状态码，多个状态码用半角逗号（,）分割
            ServerCertificateId  String	否	 服务器证书的ID
            VServerGroupId  String	否	服务器组ID
            CACertificateId  String	否	CA证书ID
            XForwardedFor_SLBIP  String	否	是否通过SLB-IP头字段获取来访者的VIP（Virtual IP address）
            XForwardedFor_SLBID  String	否	是否通过SLB-ID头字段获取SLB实例ID
            XForwardedFor_proto  String	否	是否通过X-Forwarded-Proto头字段获取SLB的监听协议
            Gzip  String	否	是否开启Gzip压缩，对特定文件类型进行压缩
            AclId  String	否	监听绑定的访问策略组ID。
            AclType  String	否	访问控制类型
            AclStatus  String	否	是否开启访问控制功能
            Description  String	否	设置监听的描述信息
            IdleTimeout  Integer	否	指定连接空闲超时时间
            RequestTimeout  Integer	否	指定请求超时时间
            EnableHttp2  String	否	是否开启HTTP2特性
            TLSCipherPolicy  String	否	安全策略包含HTTPS可选的TLS协议版本和配套的加密算法套件
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "Bandwidth"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "Bandwidth",
                "ListenerPort",
                "BackendServerPort",
                "XForwardedFor",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckMethod",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckConnectPort",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "ServerCertificateId",
                "VServerGroupId",
                "CACertificateId",
                "XForwardedFor_SLBIP",
                "XForwardedFor_SLBID",
                "XForwardedFor_proto",
                "Gzip",
                "AclId",
                "AclStatus",
                "Description",
                "IdleTimeout",
                "RequestTimeout",
                "EnableHttp2",
                "TLSCipherPolicy",
            ]
            action_name = "CreateLoadBalancerTCPListener"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            if ali_result.get("Message"):
                raise Exception(ali_result["Message"])
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("create load balancer tcp listen failed")
            return {"result": False, "message": str(e)}

    def create_load_balancer_udp_listen(self, **kwargs):
        """
        创建负载均衡UDP监听
        :param kwargs:
            LoadBalancerId  String	是	负载均衡实例的ID。
            ListenerPort Integer	是	负载均衡实例前端使用的端口。
            BackendServerPort  Integer	否	负载均衡实例后端使用的端口
            Bandwidth  Integer	是	监听的带宽峰值
            Scheduler String	否	调度算法
            HealthyThreshold  Integer	否	健康检查连续成功多少次后，将后端服务器的健康检查状态由fail判定为success。
            UnhealthyThreshold Integer	否	健康检查连续失败多少次后，将后端服务器的健康检查状态由success判定为
            HealthCheckConnectTimeout  Integer	否	接收来自运行状况检查的响应需要等待的时间
            HealthCheckConnectPort  Integer	否	健康检查使用的端口。
            healthCheckInterval  Integer	否	健康检查的时间间隔。
            healthCheckReq  String	否	UDP监听健康检查的请求串，只允许包含字母、数字，最大长度限制为64个字符。
            healthCheckExp  String	否	UDP监听健康检查的响应串，只允许包含字母、数字，最大长度限制为64个字符。
            VServerGroupId  String	否	虚拟服务器组ID。
            MasterSlaveServerGroupId  String	否	主备服务器组ID。
            AclId  String	否	监听绑定的访问策略组ID。
            AclType String	否	访问控制类型：
            AclStatus String	否	是否开启访问控制功能。
            Description  String	否	设置监听的描述信息。
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "Bandwidth"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "ListenerPort",
                "BackendServerPort",
                "Bandwidth",
                "Scheduler",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckConnectTimeout",
                "HealthCheckConnectPort",
                "healthCheckInterval",
                "healthCheckReq",
                "healthCheckExp",
                "VServerGroupId",
                "MasterSlaveServerGroupId",
                "AclId",
                "AclType",
                "AclStatus",
                "Description",
            ]
            action_name = "CreateLoadBalancerUDPListener"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            if ali_result.get("Message"):
                raise Exception(ali_result["Message"])
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("create load balancer udp listen failed")
            return {"result": False, "message": str(e)}

    def create_load_balancer_http_listen(self, **kwargs):
        """
        创建负载均衡HTTP监听
        :param kwargs:
            LoadBalancerId String	是	负载均衡实例ID。
            Bandwidth  Integer	否	监听的带宽峰值
            ListenerPort  Integer	是	负载均衡实例前端使用的端口
            BackendServerPort  Integer	否	负载均衡实例后端使用的端口。
            XForwardedFor  String	否	是否开启通过X-Forwarded-For头字段获取来访者真实 IP
            Scheduler  String	否	调度算法
            StickySession  String	是	是否开启会话保持。
            StickySessionType  String	否	Cookie处理方式
            CookieTimeout  Integer	否	Cookie超时时间
            Cookie  String	否	服务器上配置的Cookie
            HealthCheck  String	是	是否开启健康检查。
            HealthCheckMethod  String	否	监听HTTP类型健康检查的健康检查方法。取值：head或get。
            HealthCheckDomain  String	否	用于健康检查的域名
            HealthCheckURI String	否	用于健康检查的URI。
            HealthyThreshold  Integer	否	健康检查连续成功多少次后，将后端服务器的健康检查状态由失败判定为成功
            UnhealthyThreshold  Integer	否	健康检查连续失败多少次后，将后端服务器的健康检查状态由成功判定为失败
            HealthCheckTimeout  Integer	否	接收来自运行状况检查的响应需要等待的时间。如果后端ECS在指定的时间内没有正确响应，则判定为健康检查失败
            HealthCheckConnectPort  Integer	否 健康检查的后端服务器的端口。
            HealthCheckInterval  Integer	否	健康检查的时间间隔。
            HealthCheckHttpCode  String	否	健康检查正常的HTTP状态码，多个状态码用逗号分隔
            VServerGroupId  String	否	虚拟服务器组ID。
            XForwardedFor_SLBIP  String	否	是否通过SLB-IP头字段获取客户端请求的VIP（Virtual IP address）
            XForwardedFor_SLBID  String	否	是否通过SLB-ID头字段获取负载均衡实例ID
            XForwardedFor_proto  String	否	是否通过X-Forwarded-Proto头字段获取负载均衡实例的监听协议、
            Gzip  String	否	是否开启Gzip压缩，对特定文件类型进行压缩。
            AclId  String	否	监听绑定的访问策略组ID。
            AclType String	否	访问控制类型：
            AclStatus String	否	是否开启访问控制功能。
            Description  String	否	设置监听的描述信息。
            ListenerForward  String	否	是否开启HTTP至HTTPS的转发
            ForwardPort  Integer	否	HTTP至HTTPS的监听转发端口。
            IdleTimeout  Integer	否	指定连接空闲超时时间
            RequestTimeout  Integer	否	指定请求超时时间
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "StickySession", "HealthCheck"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "Bandwidth",
                "ListenerPort",
                "BackendServerPort",
                "XForwardedFor",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckMethod",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckConnectPort",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "VServerGroupId",
                "XForwardedFor_SLBIP",
                "XForwardedFor_SLBID",
                "XForwardedFor_proto",
                "Gzip",
                "AclId",
                "AclType",
                "AclStatus",
                "Description",
                "ListenerForward",
                "ForwardPort",
                "IdleTimeout",
                "RequestTimeout",
            ]
            action_name = "CreateLoadBalancerHTTPListener"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            if ali_result.get("Message"):
                raise Exception(ali_result["Message"])
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("create load balancer http listen failed")
            return {"result": False, "message": str(e)}

    def create_load_balancer_https_listen(self, **kwargs):
        """
                创建负载均衡HTTPS监听
                :param kwargs:
                    LoadBalancerId String	是	负载均衡实例ID。
                    Bandwidth  Integer	是	监听的带宽峰值
                    ListenerPort  Integer	是	负载均衡实例前端使用的端口
                    BackendServerPort  Integer	否	负载均衡实例后端使用的端口。
                    XForwardedFor  String	否	是否开启通过X-Forwarded-For头字段获取来访者真实 IP
                    Scheduler  String	否	调度算法
                    StickySession  String	是	是否开启会话保持。
                    StickySessionType  String	否	Cookie处理方式
                    CookieTimeout  Integer	否	Cookie超时时间
                    Cookie  String	否	服务器上配置的Cookie
                    HealthCheck  String	是	是否开启健康检查。
                    HealthCheckMethod  String	否	监听HTTP类型健康检查的健康检查方法。取值：head或get。
                    HealthCheckDomain  String	否	用于健康检查的域名
                    HealthCheckURI String	否	用于健康检查的URI。
                    HealthyThreshold  Integer	否	健康检查连续成功多少次后，将后端服务器的健康检查状态由失败判定为成功
                    UnhealthyThreshold  Integer	否	健康检查连续失败多少次后，将后端服务器的健康检查状态由成功判定为失败
                    HealthCheckTimeout  Integer	否	接收来自运行状况检查的响应需要等待的时间。如果后端ECS在指定的时间内没有正确响应，则判定为健康检查失败
                    HealthCheckConnectPort  Integer	否 健康检查的后端服务器的端口。
                    HealthCheckInterval  Integer	否	健康检查的时间间隔。
                    HealthCheckHttpCode  String	否	健康检查正常的HTTP状态码，多个状态码用逗号分隔
                    ServerCertificateId String	否 服务器证书的ID。
                    VServerGroupId  String	否	虚拟服务器组ID。
                    CACertificateId  String	否 CA证书ID。
                    XForwardedFor_SLBIP  String	否	是否通过SLB-IP头字段获取客户端请求的VIP（Virtual IP address）
                    XForwardedFor_SLBID  String	否	是否通过SLB-ID头字段获取负载均衡实例ID
                    XForwardedFor_proto  String	否	是否通过X-Forwarded-Proto头字段获取负载均衡实例的监听协议、
                    Gzip  String	否	是否开启Gzip压缩，对特定文件类型进行压缩。
                    AclId  String	否	监听绑定的访问策略组ID。
                    AclType String	否	访问控制类型：
                    AclStatus String	否	是否开启访问控制功能。
                    Description  String	否	设置监听的描述信息。
        。
                    IdleTimeout  Integer	否	指定连接空闲超时时间
                    RequestTimeout  Integer	否	指定请求超时时间
                    EnableHttp2 String	否是否开启HTTP2特性。
                    TLSCipherPolicy  String	否	安全策略包含HTTPS可选的TLS协议版本和配套的加密算法套件。
                :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "StickySession", "HealthCheck", "Bandwidth"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "Bandwidth",
                "ListenerPort",
                "BackendServerPort",
                "XForwardedFor",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckMethod",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckConnectPort",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "ServerCertificateId",
                "VServerGroupId",
                "CACertificateId",
                "XForwardedFor_SLBIP",
                "XForwardedFor_SLBID",
                "XForwardedFor_proto",
                "Gzip",
                "AclId",
                "AclType",
                "AclStatus",
                "Description",
                "IdleTimeout",
                "RequestTimeout",
                "EnableHttp2",
                "TLSCipherPolicy",
            ]
            action_name = "CreateLoadBalancerHTTPSListener"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            if ali_result.get("Message"):
                raise Exception(ali_result["Message"])
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("create load balancer https listen failed")
            return {"result": False, "message": str(e)}

    def set_load_balancer_tcp_listener_attribute(self, **kwargs):
        """
        修改TCP监听的配置
        :param kwargs:
            LoadBalancerId  String	是	负载均衡实例的ID
            ListenerPort Integer	是	负载均衡实例前端使用的端口
            Bandwidth  Integer	否	监听的带宽峰值
            Scheduler  String	否	调度算法
            PersistenceTimeout Integer	否	会话保持的超时时间。取值：0~3600秒。默认值：0，表示关闭会话保持
            EstablishedTimeout Integer	否	连接超时时间。取值：10~900秒。
            HealthyThreshold  Integer	否	健康检查连续成功多少次后，将后端服务器的健康检查状态由fail判定为success
            UnhealthyThreshold  Integer	否	健康检查连续失败多少次后，将后端服务器的健康检查状态由success判定为fail
            HealthCheckTimeout  Integer	否	接收来自运行状况检查的响应需要等待的时间。如果后端ECS在指定的时间内没有正确响应，则判定为健康检查失败
            HealthCheckConnectPort  Integer	否	健康检查使用的端口。
            HealthCheckInterval  Integer	否	健康检查的时间间隔
            HealthCheckDomain  String	否	用于健康检查的域名。当TCP监听需要使用HTTP健康检查时可配置此参数，如不配置则按TCP健康检查
            HealthCheckURI  String	否	用于健康检查的URL
            HealthCheckHttpCode  String	否	健康检查正常的HTTP状态码，多个状态码用半角逗号（,）分割
            HealthCheckType  String	否	健康检查类型。取值：tcp或http
            SynProxy  String	否 是否开启负载均衡的攻击防护功能SynProxy
            VServerGroup String	否	是否使用虚拟服务器组。
            VServerGroupId  String	否	服务器组ID
            MasterSlaveServerGroupId  String	否	主备服务器组ID。
            MasterSlaveServerGroup  String	否	是否使用主备服务器组。
            AclId  String	否	监听绑定的访问策略组ID。
            AclType  String	否	访问控制类型
            AclStatus  String	否	是否开启访问控制功能
            Description  String	否	设置监听的描述信息
            ConnectionDrain  String	否	是否开启连接优雅中断
            ConnectionDrainTimeout  Integer	否	设置连接优雅中断超时时间。
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "Bandwidth",
                "ListenerPort",
                "Scheduler",
                "PersistenceTimeout",
                "HealthCheck",
                "HealthCheckMethod",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckType",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "HealthCheckConnectPort",
                "SynProxy",
                "VServerGroupId",
                "VServerGroup",
                "MasterSlaveServerGroupId",
                "MasterSlaveServerGroup",
                "AclId",
                "AclStatus",
                "EstablishedTimeout",
                "Description",
                "ConnectionDrain",
                "ConnectionDrainTimeout",
            ]
            action_name = "SetLoadBalancerTCPListenerAttribute"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("set load balancer tcp listener attribute failed")
            return {"result": False, "message": str(e)}

    def set_load_balancer_udp_listener_attribute(self, **kwargs):
        """
        修改UDP监听的配置
        :param kwargs: aliyun DescribeMetricListRequest api param, see https://help.aliyun.com/
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "ListenerPort",
                "Bandwidth",
                "Scheduler",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckConnectTimeout",
                "HealthCheckConnectPort",
                "HealthCheckInterval",
                "healthCheckReq",
                "healthCheckExp",
                "VServerGroup",
                "VServerGroupId",
                "MasterSlaveServerGroupId",
                "MasterSlaveServerGroup",
                "AclId",
                "AclType",
                "AclStatus",
                "Description",
            ]
            action_name = "SetLoadBalancerUDPListenerAttribute"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("set load balancer udp listener attribute failed")
            return {"result": False, "message": str(e)}

    def set_load_balancer_http_listener_attribute(self, **kwargs):
        """
        修改HTTP监听的配置
        :param kwargs: aliyun DescribeMetricListRequest api param, see https://help.aliyun.com/
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "ListenerPort",
                "Bandwidth",
                "XForwardedFor",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckMethod",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckConnectPort",
                "HealthCheckHttpCode",
                "VServerGroup",
                "VServerGroupId",
                "XForwardedFor_SLBIP",
                "XForwardedFor_SLBID",
                "XForwardedFor_proto",
                "Gzip",
                "AclId",
                "AclType",
                "AclStatus",
                "Description",
                "IdleTimeout",
                "RequestTimeout",
            ]
            action_name = "SetLoadBalancerHTTPListenerAttribute"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("set load balancer http listener attribute failed")
            return {"result": False, "message": str(e)}

    def set_load_balancer_https_listener_attribute(self, **kwargs):
        """
        修改HTTPS监听的配置
        :param kwargs: aliyun DescribeMetricListRequest api param, see https://help.aliyun.com/
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "Bandwidth",
                "ListenerPort",
                "EnableHttp2",
                "TLSCipherPolicy",
                "XForwardedFor",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckMethod",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "VServerGroup",
                "HealthCheckConnectPort",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "ServerCertificateId",
                "VServerGroupId",
                "CACertificateId",
                "XForwardedFor_SLBIP",
                "XForwardedFor_SLBID",
                "XForwardedFor_proto",
                "Gzip",
                "AclId",
                "AclType",
                "AclStatus",
                "Description",
                "IdleTimeout",
                "RequestTimeout",
            ]
            action_name = "SetLoadBalancerHTTPSListenerAttribute"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("set load balancer https listener attribute failed")
            return {"result": False, "message": str(e)}

    def create_rules(self, **kwargs):
        """
        为指定的HTTP或HTTPS监听添加转发规则
        :param kwargs:
            LoadBalancerId  String	是	负载均衡实例ID。
            ListenerPort  Integer	是	负载均衡实例前端使用的监听端口。
            ListenerProtocol  String	否	负载均衡实例前端使用的协议
            RuleList String	是	要添加的转发规则
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "RuleList"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = ["LoadBalancerId", "ListenerProtocol", "ListenerPort", "RuleList"]
            action_name = "CreateRules"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            if ali_result.get("Rules"):
                return {"result": True, "data": ali_result["Rules"]}
            return {"result": False, "message": ali_result["Message"]}
        except Exception as e:
            logger.exception("create rules failed")
            return {"result": False, "message": str(e)}

    def delete_rules(self, **kwargs):
        """
        删除转发规则
        :param kwargs:
            :param kwargs: aliyun DescribeMetricListRequest api param, see https://help.aliyun.com/
        :return:
        """
        try:
            if "RuleIds" not in kwargs:
                return {"result": False, "message": "need param RuleId"}
            list_optional_params = ["RuleIds"]
            action_name = "DeleteRules"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("delete rules failed")
            return {"result": False, "message": str(e)}

    def set_rules(self, **kwargs):
        """
        修改目标虚拟服务器组的转发规则
        :param kwargs:
            RuleId  String	是	转发规则ID。
            VServerGroupId  String	否	转发规则的目标服务器组ID。

        :return:
        """
        try:
            if "RuleId" not in kwargs:
                return {"result": False, "message": "need param RuleIds"}
            list_optional_params = [
                "RuleId",
                "VServerGroupId",
                "RuleName",
                "ListenerSync",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckConnectPort",
                "HealthCheckHttpCode",
            ]
            action_name = "SetRule"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("set rules failed")
            return {"result": False, "message": str(e)}

    def list_rules(self, **kwargs):
        """
        查询指定监听已配置的转发规则
        :param kwargs:
        :return:
        """
        required_list = ["LoadBalancerId", "ListenerPort"]
        checkout_required_parameters(required_list, kwargs)
        list_optional_params = ["LoadBalancerId", "ListenerProtocol", "ListenerPort"]
        action_name = "DescribeRules"
        request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
        ali_res = self._get_result_c(request, True)
        data = self._format_resource_result("rule", ali_res, **kwargs)
        for item in data:
            if item.get("RuleId"):
                ret = self.get_rule_attribute(RuleId=item["RuleId"])
                if ret["result"]:
                    item["LoadBalancerId"] = ret["data"].get("LoadBalancerId")
        return {"result": True, "data": data}

    def get_rule_attribute(self, **kwargs):
        """
        查询指定转发规则的配置详情
        :param kwargs:
        :return:
        """
        if "RuleId" in kwargs:
            return {"result": False, "message": "need param RuleIds"}
        list_optional_params = ["RuleId"]
        action_name = "DescribeRuleAttribute"
        request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
        response = self.client.do_action(request)
        ali_result = json.loads(response)
        return {"result": True, "data": ali_result}

    def start_listener(self, **kwargs):
        """
        启动监听
        :param kwargs:
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = ["LoadBalancerId", "ListenerPort", "ListenerProtocol"]
            action_name = "StartLoadBalancerListener"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("start_listener failed")
            return {"result": False, "message": str(e)}

    def stop_listener(self, **kwargs):
        """
        停止监听
        :param kwargs:
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = ["LoadBalancerId", "ListenerPort", "ListenerProtocol"]
            action_name = "StopLoadBalancerListener"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("stop_listener failed")
            return {"result": False, "message": str(e)}

    def delete_listener(self, **kwargs):
        """
        停止监听
        :param kwargs:
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = ["LoadBalancerId", "ListenerPort", "ListenerProtocol"]
            action_name = "DeleteLoadBalancerListener"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("delete_listener failed")
            return {"result": False, "message": str(e)}

    def list_listeners(self, **kwargs):
        """
        查询负载均衡监听列表详情
        :param kwargs:
            NextToken  String	否	用来标记当前开始读取的位置，置空表示从头开始。
            MaxResults  Integer	否	本次读取的最大数据记录数量。
            ListenerProtocol  String	否	负载均衡监听协议
            LoadBalancerId String []	否	负载均衡实例的ID列表，N最大值为10
        :return:
        """
        try:
            list_optional_params = ["NextToken", "MaxResults", "ListenerProtocol", "LoadBalancerId"]
            action_name = "DescribeLoadBalancerListeners"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            return self.__handle_list_request_with_next_token_c("listener", request)
        except Exception as e:
            logger.exception("start_listener failed")
            return {"result": False, "message": str(e)}

    def add_backend_servers(self, **kwargs):
        """
        添加后端服务器
        :param kwargs:
        :return:
        """
        try:
            if "LoadBalancerId" not in kwargs:
                return {"result": False, "message": "need param LoadBalancerId"}
            list_optional_params = ["LoadBalancerId", "BackendServers"]
            action_name = "AddBackendServers"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("add_backend_servers failed")
            return {"result": False, "message": str(e)}

    def delete_backend_servers(self, **kwargs):
        """
        添加后端服务器
        :param kwargs:
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "BackendServers"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = ["LoadBalancerId", "BackendServers"]
            action_name = "RemoveBackendServers"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("remove_backend_servers failed")
            return {"result": False, "message": str(e)}

    def modify_backend_servers(self, **kwargs):
        """
        设置后端服务器权重
        :param kwargs:
        :return:
        """
        try:
            if "LoadBalancerId" not in kwargs:
                return {"result": False, "message": "need param LoadBalancerId"}
            list_optional_params = ["LoadBalancerId", "BackendServers", "ListenerProtocol"]
            action_name = "SetBackendServers"
            request = self._set_common_request_params(action_name, list_optional_params, **kwargs)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("set_backend_servers failed")
            return {"result": False, "message": str(e)}

    def describe_health_status(self, **kwargs):
        """
        查询后端服务器的健康状态
        :param kwargs:
        :return:
        """
        try:
            if "LoadBalancerId" not in kwargs:
                return {"result": False, "message": "need param LoadBalancerId"}
            request = DescribeHealthStatusRequest.DescribeHealthStatusRequest()
            list_optional_params = ["LoadBalancerId", "ListenerPort", "ListenerProtocol"]
            request = set_optional_params(request, list_optional_params, kwargs)
            request.set_accept_format("json")
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["BackendServers"]}
        except Exception as e:
            logger.exception("describe_health_status failed")
            return {"result": False, "message": str(e)}

    def _set_common_request_params(self, action_name, list_optional_params, **kwargs):
        """
        设置CommonRequest类型request的参数
        :param kwargs:
        :return:
        """
        request = CommonRequest()
        request.set_accept_format("json")
        request.set_domain("slb.{}.aliyuncs.com".format(self.RegionId))
        request.set_method("POST")
        request.set_protocol_type("https")
        request.set_version("2014-05-15")
        request.set_action_name(action_name)
        params_dict = {"RegionId": self.RegionId}
        [params_dict.update({item: kwargs[item]}) for item in list_optional_params if item in kwargs]
        request = add_required_params(request, params_dict)
        return request

    # ------------------镜像------------------------------

    @classmethod
    def _set_template_info_params(cls, **kwargs):
        """
        设置镜像信息参数
        :param kwargs:
        :return:
        """
        request = kwargs.get("request", "")
        request = request or DescribeImagesRequest.DescribeImagesRequest()
        list_optional_params = [
            "Status",
            "Status",
            "ImageName",
            "ImageOwnerAlias",
            "Usage",
            "Tag.1.Key",
            "Tag.1.Value",
            "Tag.2.Key",
            "Tag.2.Value",
            "PageNumber",
            "PageSize",
        ]
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_accept_format("json")
        return request

    def create_image(self, **kwargs):
        """
        创建自定义镜像
        SnapshotId  String	否	根据指定的快照创建自定义镜像。
        InstanceId  String	否  实例ID。
        ImageName   String	否	镜像名称
        ImageFamily  String	否	镜像族系名称
        ImageVersion  String 否
        Description  String	否	镜像的描述信息
        Platform  String	否	指定数据盘快照做镜像的系统盘后，需要通过Platform确定系统盘的操作系统发行版
        Architecture String	否	指定数据盘快照做镜像的系统盘后，需要通过Architecture确定系统盘的系统架构
        ClientToken String	否	保证请求幂等性
        ResourceGroupId  String	否	自定义镜像所在的企业资源组ID。
        DiskDeviceMapping list []	否
        Tag list 否
        """
        try:
            request = CreateImageRequest.CreateImageRequest()
            list_optional_params = [
                "SnapshotId",
                "InstanceId",
                "ImageName",
                "ImageFamily",
                "ImageVersion",
                "Description",
                "Platform",
                "Architecture",
                "ClientToken",
                "ResourceGroupId",
                "DiskDeviceMapping",
                "Tag",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["ImageId"]}
        except Exception as e:
            logger.exception("create_images")
            return {"result": False, "message": str(e)}

    def list_images(self, ids=None, **kwargs):
        """
        获取镜像信息参数
        :param ids: ids (list of str): 镜像id列表
        :param kwargs:aliyun DescribeImagesRequest api param, see https://help.aliyun.com/
        :return:image列表
        """
        request = DescribeImagesRequest.DescribeImagesRequest()
        if ids:
            request.set_ImageId(json.dumps(ids))
        kwargs["request"] = request
        request = self._set_template_info_params(**kwargs)
        return self._handle_list_request_with_page("image", request)

    def delete_images(self, **kwargs):
        """
        销毁磁盘
        :param disk_id:
            aliyun DeleteDiskRequest api param, see https://help.aliyun.com/
        """
        try:
            request = DeleteImageRequest.DeleteImageRequest()
            request.set_ImageId(kwargs["image_id"])
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete image_id failed(ImageId):" + ",".join(kwargs["image_id"]))
            return {"result": False, "message": str(e)}

    #  *********************************存储管理*******************************************

    #  -----------------块存储-------------------------------
    @classmethod
    def _set_datastore_info_params(cls, request, **kwargs):
        """
        设置云盘信息参数
        :param kwargs:
        :return:
        """
        list_optional_params = [
            "Encrypted",
            "ZoneId",
            "DiskIds",
            "InstanceId",
            "DiskType",
            "Category",
            "Status",
            "SnapshotId",
            "DiskName",
            "Portable",
            "DeleteWithInstance",
            "DeleteAutoSnapshot",
            "EnableAutoSnapshot",
            "DiskChargeType",
            "Tag.1.Key",
            "Tag.1.Value",
            "Tag.2.Key",
            "Tag.2.Value",
            "PageNumber",
            "PageSize",
        ]
        request = set_optional_params(request, list_optional_params, kwargs)
        return request

    def list_disks(self, ids=None, **kwargs):
        """
        获取云盘列表
        :param ids:  ids (list of str): 磁盘id列表
        :param kwargs:aliyun DescribeDisksRequest api param, see https://help.aliyun.com/
        :return:云盘列表
        """
        request = DescribeDisksRequest.DescribeDisksRequest()
        if ids:
            request.set_DiskIds(json.dumps(ids))
        request = self._set_datastore_info_params(request, **kwargs)
        return self._handle_list_request_with_page("disk", request)

    @classmethod
    def _set_create_disk_params(cls, **kwargs):
        """设置阿里云磁盘创建参数
        下边二选一
            ZoneId：可用区id 付费类型是按需付费  (required)  现在只做按量付费即必有zone_id
            InstanceId (str): 关联实例id 和zoneId有且仅有1个，付费类型只能是包年包月 (required)
        DiskName: 名称 (optional)
        Size: 容量  (optional)
        DiskCategory: 数据盘种类 (optional)
        Description: 数据盘描述  (optional)

        """
        request = CreateDiskRequest.CreateDiskRequest()
        request.set_ZoneId(kwargs["ZoneId"])
        # request.set_InstanceId(kwargs["InstanceId"])
        list_optional_params = ["DiskCategory", "Size", "DiskName", "Encrypted", "Description"]
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_accept_format("json")
        return request

    def create_disk(self, **kwargs):
        """
        创建磁盘
        :param kwargs:aliyun CreateDiskRequest api param, see https://help.aliyun.com/
        :return:云盘id
        """
        try:
            request = self._set_create_disk_params(**kwargs)
            ali_response = self.client.do_action_with_exception(request)
            ali_result = json.loads(ali_response)
            return {"result": True, "data": ali_result["DiskId"]}
        except Exception as e:
            logger.exception("create_disk")
            return {"result": False, "message": str(e)}

    def attach_disk(self, **kwargs):
        """
        挂载磁盘
        :param kwargs:aliyun AttachDiskRequest api param, see https://help.aliyun.com/
        """
        try:
            request = AttachDiskRequest.AttachDiskRequest()
            request.set_InstanceId(kwargs["InstanceId"])
            request.set_DiskId(kwargs["DiskIds"])
            request.set_DeleteWithInstance("true")
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("attach_disk:InstanceId({}),DiskIds({})".format(kwargs["InstanceId"], kwargs["DiskIds"]))
            return {"result": False, "message": str(e)}

    def detach_disk(self, **kwargs):
        """
        卸载磁盘
        :param kwargs:aliyun DetachDiskRequest api param, see https://help.aliyun.com/
        """
        try:
            request = DetachDiskRequest.DetachDiskRequest()
            request.set_InstanceId(kwargs["InstanceId"])
            request.set_DiskId(kwargs["DiskIds"])
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("detach_disk:InstanceId({}),DiskIds({})".format(kwargs["InstanceId"], kwargs["DiskIds"]))
            return {"result": False, "message": str(e)}

    def delete_disk(self, disk_id):
        """
        销毁磁盘
        :param disk_id:
            aliyun DeleteDiskRequest api param, see https://help.aliyun.com/
        """
        try:
            request = DeleteDiskRequest.DeleteDiskRequest()
            request.set_DiskId(disk_id)
            request.set_accept_format("json")
            self.client.do_action_with_exception(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete disk failed(DiskIds):" + ",".join(disk_id))
            return {"result": False, "message": str(e)}

    def add_vm_disk(self, **kwargs):
        """
        绑定磁盘
        :param kwargs:
        :return:
        """
        try:
            disk_size = int(kwargs["config"][1])
            disk_type_raw = kwargs["config"][0]
            if disk_type_raw == "普通磁盘":
                disk_type = "cloud"
            elif disk_type_raw == "固态磁盘":
                disk_type = "cloud_ssd"
            else:
                disk_type = "cloud_efficiency"
            kwargs["Size"] = disk_size
            kwargs["DiskCategory"] = disk_type
            new_disk = self.create_disk(**kwargs)
            if new_disk["result"]:
                kwargs["DiskIds"] = new_disk["data"]
            else:
                return new_disk
            attach_result = self.attach_disk(**kwargs)
            if attach_result:
                return {"result": True}
            else:
                self.delete_disk(**kwargs)
                return {"result": False, "message": "实例不支持绑定该类型磁盘"}
        except Exception as e:
            logger.exception("add_vm_disk-InstanceId:" + kwargs["InstanceId"])
            return {"result": False, "message": str(e)}

    def resize_disk(self, **kwargs):
        """
            扩容一块云盘，支持扩容系统盘和数据盘。
            扩容前，请务必查询云盘采用的分区格式。如果是MBR格式，不支持扩容到2TiB以上，否则会造成数据丢失。对于MBR分区扩容，
        建议您重新创建并挂载一块数据盘，采用GPT分区格式后，再将已有数据拷贝至新的数据盘上。
            支持扩容的云盘类型包括普通云盘（cloud）、高效云盘（cloud_efficiency）、SSD云盘（cloud_ssd）和ESSD（cloud_essd）
        云盘。
            当云盘正在创建快照时，不允许扩容。
            云盘挂载的实例的状态必须为运行中（Running）或者已停止（Stopped）。
            扩容时，不会修改云盘分区和文件系统，您需要在扩容后自行分配存储空间。
            :param kwargs:
                        DiskId：类型：String。必选。描述：云盘ID。
                        NewSize：类型：Integer。必选。描述：希望扩容到的云盘容量大小。单位为GiB。取值范围：高效云盘
                    （cloud_efficiency）：20~32768、SSD云盘（cloud_ssd）：20~32768、ESSD云盘（cloud_essd）：20~32768、
                     普通云盘（cloud）：5~2000。指定的新云盘容量必须比原云盘容量大。
                        Type：类型：String。描述：扩容云盘的方式。取值范围：offline（默认）：离线扩容。扩容后，您必须在控制台重启实
                    例或者调用API RebootInstance使操作生效。online：在线扩容，无需重启实例即可完成扩容。云盘类型支持高效云盘、
                    SSD云盘和ESSD云盘。
                        ClientToken：类型：String。描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值
                    唯一。ClientToken只支持ASCII字符，且不能超过64个字符。
            :return:
        """
        try:
            request = ResizeDiskRequest.ResizeDiskRequest()
            request.set_DiskId(kwargs["DiskId"])
            request.set_NewSize(int(kwargs["NewSize"]))
            list_optional_params = ["Type", "ClientToken"]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("resize_disk")
            return {"result": False, "message": str(e)}

    # ---------------对象存储-----------------------

    # def list_buckets(self, **kwargs):
    #     """
    #     获取Bucket列表信息。
    #     :param kwargs:
    #                 Prefix：类型：String。描述：只罗列Bucket名为该前缀的Bucket，空串表示罗列所有的Bucket。
    #                 Marker：类型：分页标志。首次调用传空串，后续使用返回值中的next_marker。
    #                 Max-keys：类型：Integer。描述：每次调用最多返回的Bucket数目。
    #     :return: oss2.models.ListBucketsResult解码后的python对象
    #     :rtype: oss2.models.ListBucketsResult
    #     """
    #     bucket_type = ""
    #     format_func = get_format_method(self.cloud_type, "bucket")
    #     ali_result = []
    #     try:
    #         service = oss2.Service(self.auth, "http://oss-" + self.RegionId + ".aliyuncs.com")
    #         buckets = service.list_buckets().buckets
    #     except Exception as e:
    #         logger.exception("调用阿里云获取桶存储接口失败{}".format(e))
    #         return {"result": False, "message": e.message}
    #     for i in buckets:
    #         try:
    #             bucket = oss2.Bucket(self.auth, "http://" + i.location + ".aliyuncs.com", i.name)
    #             object_list = bucket.list_objects().object_list
    #         except Exception as e:
    #             logger.exception("调用阿里云获取桶存储接口失败{}".format(e))
    #             return {"result": False, "message": e.message}
    #         size = 0
    #         if object_list:
    #             bucket_type = object_list[0].storage_class
    #             for file in object_list:
    #                 size += file.size
    #             size = round(size / 1024 / 1024, 2)
    #         ali_result.append()
    #     return {"result": True, "data": ali_result}

    def put_bucket(self, **kwargs):
        """
        用于创建存储空间（Bucket）。
        :param kwargs:
                    BucketName：类型：String。必选。描述：存储空间名。只能包括小写字母、数字和短横线（-）。必须以小写字母
                或者数字开头和结尾。长度必须在 3–63 字节之间。存储空间的名称在 OSS 范围内必须是全局唯一的，一旦创建之后
                无法修改名称
                    Permission：类型：String。描述：指定Bucket访问权限。有效值：public-read-write、public-read、
                private。也可以是oss2.BUCKET_ACL_PRIVATE（推荐、缺省）、oss2.BUCKET_ACL_PUBLIC_READ或是
                oss2.BUCKET_ACL_PUBLIC_READ_WRITE。
        :return:
        """
        try:
            bucket = oss2.Bucket(self.auth, "http://oss-" + self.RegionId + ".aliyuncs.com", kwargs["BucketName"])
            permission = oss2.BUCKET_ACL_PRIVATE
            if "Permission" in kwargs:
                permission = kwargs["Permission"]
            bucket.create_bucket(permission)
            return {"result": True}
        except Exception as e:
            logger.exception("put_bucket")
            return {"result": False, "message": str(e)}

    def delete_bucket(self, name, location):
        """
        用于删除某个存储空间（Bucket）。
        :param kwargs:
                    BucketName：类型：String。必选。描述：存储空间名。只能包括小写字母、数字和短横线（-）。必须以小写字母
                或者数字开头和结尾。长度必须在 3–63 字节之间。存储空间的名称在 OSS 范围内必须是全局唯一的，一旦创建之后
                无法修改名称
        :return:
        """
        try:
            location = location or self.RegionId
            bucket = oss2.Bucket(self.auth, "http://oss-" + location + ".aliyuncs.com", name)
            bucket.delete_bucket()
            return {"result": True}
        except Exception as e:
            logger.exception("delete_bucket:" + name)
            return {"result": False, "message": str(e)}

    def get_bucket_info(self, **kwargs):
        """
        获取Bucket信息
        :param kwargs:
        :return:
        """
        try:
            bucket = oss2.Bucket(self.auth, "http://oss-" + self.RegionId + ".aliyuncs.com", kwargs["BucketName"])
            ali_result = Bucket(
                resource_id=bucket.bucket_name,
                resource_name=bucket.bucket_name,
                extra={
                    "auth": bucket.auth,
                    "endpoint": bucket.endpoint,
                    "session": bucket.session,
                    "app_name": bucket.app_name,
                    "enable_crc": bucket.enable_crc,
                },
            ).to_dict()
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("get_bucket_info:" + kwargs["BucketName"])
            return {"result": False, "message": str(e)}

    def put_object(self, location, **kwargs):
        """
        上传本地文件
        :param kwargs:
            file_path: str  是 本地文件地址
        :return:
        """
        try:
            if "file_path" not in kwargs:
                return {"result": False, "message": "need param local_path"}
            bucket = oss2.Bucket(self.auth, "http://oss-" + location + ".aliyuncs.com", kwargs["BucketName"])
            file_path = kwargs.get("file_path")
            if file_path[-1] == "/":
                kwargs.pop("content")
            bucket.put_object(file_path, kwargs.get("content", ""))
            return {"result": True}
        except Exception as e:
            logger.exception("put_object fail")
            return {"result": False, "message": str(e)}

    def load_object(self, location, **kwargs):
        """
        将指定的OSS文件下载到本地文件
        :param kwargs:
            local_path str 是 本地存储文件地址
            object_name str 是 下载文件名
        :return:
        """
        try:
            required_list = ["local_path", "object_name"]
            checkout_required_parameters(required_list, kwargs)
            bucket = oss2.Bucket(self.auth, "http://oss-" + location + ".aliyuncs.com", kwargs["BucketName"])
            # object_name = kwargs["object_name"].split("/")[-1]  \
            #     if "/" in kwargs["object_name"] else kwargs["object_name"]
            object_name = kwargs["object_name"]
            # local_file_path = os.path.join(kwargs["local_path"] + object_name.split("/")[-1])
            # bucket.get_object_to_file(kwargs["object_name"], object_name.split("/")[-1])
            object_stream = bucket.get_object(object_name)
            try:
                # 空文件会报错
                file_content = object_stream.read()
            except Exception:
                file_content = b""
            return {"result": True, "data": file_content}
        except Exception as e:
            logger.exception("get_object fail")
            return {"result": False, "message": str(e)}

    def delete_object(self, location, **kwargs):
        """
        删除文件
        :param kwargs:
            object_list 是 list  文件名列表 eg：['<yourObjectName-a>', '<yourObjectName-b>', '<yourObjectName-c>']
        :return:
        """
        try:
            if "object_list" not in kwargs:
                return {"result": False, "message": "need param object_list"}
            bucket = oss2.Bucket(self.auth, "http://oss-" + location + ".aliyuncs.com", kwargs["BucketName"])
            bucket.batch_delete_objects(kwargs["object_list"])
            return {"result": True}
        except Exception as e:
            logger.exception("delete_object fail")
            return {"result": False, "message": str(e)}

    def list_object(self, location, **kwargs):
        """
        查询
        :param kwargs:
        :return:
        """

        try:
            bucket = oss2.Bucket(self.auth, "http://oss-" + location + ".aliyuncs.com", kwargs["BucketName"])
            file_path = kwargs.get("file_path", "")
            object_list = bucket.list_objects(prefix=file_path, delimiter="/")
            ali_result = [item.key for item in object_list.object_list]
            ali_result.extend(object_list.prefix_list)
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("list_object fail")
            return {"result": False, "message": str(e)}

    def list_bucket_file(self, bucket_name, location):
        """获取存储桶下的所有object"""
        format_func = get_format_method(self.cloud_type, "bucket_file")
        try:
            bucket = oss2.Bucket(self.auth, "http://oss-" + location + ".aliyuncs.com", bucket_name)
            file_path = ""
            object_lists = bucket.list_objects(prefix=file_path).object_list
            for item in object_lists:
                if item.key.endswith("/"):
                    item.type = "DIR"
                    item.parent = "/".join(item.key.split("/")[:-2]) if "/" in item.key.strip("/") else ""
                    item.name = item.key.split("/")[-2]
                else:
                    item.type = "FILE"
                    item.parent = "/".join(item.key.split("/")[:-1]) if "/" in item.key else ""
                    item.name = item.key.split("/")[-1]
            top_dir_list = [item for item in object_lists if item.parent == "" and item.type == "DIR"]
            for top_dir in top_dir_list:
                set_dir_size(top_dir, object_lists)
            ali_result = [format_func(item, bucket=bucket_name, location=location) for item in object_lists]
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("list_object fail")
            return {"result": False, "message": str(e)}

    #  ---------------------文件系统---------------------------
    def create_file_system(self, **kwargs):
        """
        创建文件系统
        :param kwargs:aliyun DetachDiskRequest api param, see https://help.aliyun.com/
        :return:
        """
        required_list = ["StorageType", "ProtocolType"]
        checkout_required_parameters(required_list, kwargs)
        request = CreateFileSystemRequest.CreateFileSystemRequest()
        list_optional_params = [
            "FileSystemType",
            "ChargeType",
            "Duration",
            "Capacity",
            "Bandwidth",
            "StorageType",
            "ZoneId",
            "ProtocolType",
            "EncryptType",
            "SnapshotId",
            "VpcId",
            "VSwitchId",
            "ClientToken",
            "KmsKeyId",
            "DryRun",
            "Description",
        ]
        request = set_optional_params(request, list_optional_params, kwargs)
        ali_result = self._get_result(request, True)
        return {"result": True, "data": ali_result["FileSystemId"]}

    def delete_file_system(self, fs_id):
        """
        删除文件系统
        :param kwargs:aliyun DetachDiskRequest api param, see https://help.aliyun.com/
        :return:
        """
        try:
            request = DeleteFileSystemRequest.DeleteFileSystemRequest()
            request.set_FileSystemId(fs_id)
            # list_optional_params = ["FileSystemId"]
            # request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("delete_file_system fail")
            return {"result": False, "message": str(e)}

    def list_file_system(self, ids=None, **kwargs):
        """
        查询文件系统信息
        :param ids: 文件系统ID
        :param kwargs:
        :return:
        """
        if ids:
            kwargs["FileSystemId"] = ids[0]
        request = DescribeFileSystemsRequest.DescribeFileSystemsRequest()
        list_optional_params = ["FileSystemId", "FileSystemType", "VpcId", "PageSize", "PageNumber", "Tag"]
        request = set_optional_params(request, list_optional_params, kwargs)
        return self._handle_list_request_with_page("file_system", request)

    #  **************************************网络管理*******************************

    #  ---------------------VPC（专有网络）---------------------------

    def create_vpc(self, **kwargs):
        """
        创建一个专有网络（VPC）。
        调用该接口创建交换机时，请注意：
            每个VPC内的交换机数量不能超过24个。
            每个交换机网段的第1个和最后3个IP地址为系统保留地址。例如192.168.1.0/24的系统保留地址为192.168.1.0、
        192.168.1.253、192.168.1.254和192.168.1.255。
            交换机下的云产品实例数量不允许超过VPC剩余的可用云产品实例数量（15000减去当前云产品实例数量）。
            一个云产品实例只能属于一个交换机。
            交换机不支持组播和广播。
            交换机创建成功后，无法修改网段。
        :param kwargs:
                    CidrBlock：类型：String，描述：VPC的网段。您可以使用以下网段或其子集作为VPC的网段：172.16.0.0/12（默认值）、
                10.0.0.0/8、192.168.0.0/16
                    Ipv6CidrBlock：类型：String，描述：VPC的IPv6网段。
                    EnableIpv6：类型：Boolean，描述：是否开启IPv6网段，取值：false（默认值）：不开启、true：开启。
                    VpcName：类型：String，描述：VPC的名称。长度为2~128个字符，必须以字母或中文开头，可包含数字、点号（.）、
                下划线（_）和短横线（-），但不能以http://或https://开头。
                    Description：类型：String，描述：VPC的描述信息。长度为2~256个字符，必须以字母或中文开头，但不能以http://
                或https://开头。
                    ResourceGroupId：类型：String，描述：资源组ID。
                    DryRun：类型：Boolean，描述：是否只预检此次请求
                    UserCidr：类型：String，描述：用户网段，如需定义多个网段请使用半角逗号隔开，最多支持3个网段。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值唯一。
                ClientToken只支持ASCII字符，且不能超过64个字符。
        :return:
        """
        try:
            request = CreateVpcRequest.CreateVpcRequest()
            list_optional_params = [
                "CidrBlock",
                "Ipv6CidrBlock",
                "EnableIpv6",
                "VpcName",
                "Description",
                "ResourceGroupId",
                "UserCidr",
                "ClientToken",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["VpcId"]}
        except Exception as e:
            logger.exception("create_vpc")
            return {"result": False, "message": str(e)}

    def delete_vpc(self, vpc_id):
        """
        删除一个专有网络（VPC）。
        调用该接口删除VPC时，请注意：
            删除VPC之前，需要先释放或移走VPC内的所有资源，包括交换机、云产品实例、高可用虚拟IP等。
            只有处于Available状态的VPC才可以被删除。
        :param vpc_id：类型：String，必选。描述：要删除的VPC ID。
        :return:
        """
        try:
            request = DeleteVpcRequest.DeleteVpcRequest()
            request.set_VpcId(vpc_id)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete_vpc: {}".format(vpc_id))
            return {"result": False, "message": str(e)}

    def list_vpcs(self, ids=None, **kwargs):
        """
        获取专有网络信息
        :param ids: vpcId 列表
        :param kwargs:aliyun DescribeVpcsRequest api param, see https://help.aliyun.com/
        :return:VPC列表
        """
        request = DescribeVpcsRequest.DescribeVpcsRequest()
        if ids:
            request.set_VpcId(ids[0])
        kwargs["request"] = request
        request = self._set_vpc_info_params(**kwargs)
        return self._handle_list_request_with_page("vpc", request)

    @classmethod
    def _set_vpc_info_params(cls, **kwargs):
        """
        设置专有网路信息参数
        :param kwargs:
        :return:
        """
        request = kwargs.pop("request", "") or DescribeVpcsRequest.DescribeVpcsRequest()
        list_optional_params = ["VpcId", "VpcName", "IsDefault", "PageNumber", "PageSize"]
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_accept_format("json")
        return request

    #  -------------------VSwitch（交换机）------------------------------

    def create_subnet(self, **kwargs):
        """
        创建交换机。
        调用该接口创建交换机时，请注意：
            每个VPC内的交换机数量不能超过24个。
            每个交换机网段的第1个和最后3个IP地址为系统保留地址。例如192.168.1.0/24的系统保留地址为192.168.1.0、
        192.168.1.253、192.168.1.254和192.168.1.255。
            交换机下的云产品实例数量不允许超过VPC剩余的可用云产品实例数量（15000减去当前云产品实例数量）。
            一个云产品实例只能属于一个交换机。
            交换机不支持组播和广播。
            交换机创建成功后，无法修改网段。
        :param kwargs:
                    CidrBlock：类型：String，必选。描述：交换机的网段。交换机网段要求如下：交换机的网段的掩码长度范围为16~29位。
                交换机的网段必须从属于所在VPC的网段。交换机的网段不能与所在VPC中路由条目的目标网段相同，但可以是目标网段的子集。
                    VpcId：类型：String，必选。描述：要创建的交换机所属的VPC ID
                    ZoneId：类型：String，必选。描述：要创建的交换机所属的可用区ID。您可以通过调用DescribeZones接口获取可用区ID。
                    Ipv6CidrBlock：类型：Integer，描述：交换机IPv6网段的最后8比特位，取值：0~255。
                    Description：类型：String，描述：交换机的描述信息。描述长度为2~256个字符，必须以字母或中文开头，
                但不能以http://或https://开头。
                    VSwitchName：类型：String，描述：交换机的名称。名称长度为2~128个字符，必须以字母或中文开头，
                但不能以http://或https://开头。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值唯一。
                ClientToken只支持ASCII字符，且不能超过64个字符。更多详情，请参见如何保证幂等性。
                    OwnerAccount：类型：String，描述：RAM用户的账号登录名称。
        :return:data:ali_result["VSwitchId"]：创建的交换机的ID。
        """
        try:
            request = CreateVSwitchRequest.CreateVSwitchRequest()
            list_required_params = ["CidrBlock", "VpcId", "ZoneId"]
            list_optional_params = ["Ipv6CidrBlock", "Description", "VSwitchName", "ClientToken", "OwnerAccount"]
            request = set_required_params(request, list_required_params, kwargs)
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["VSwitchId"]}
        except Exception as e:
            logger.exception("create subnet failed")
            return {"result": False, "message": str(e)}

    def delete_subnet(self, subnet_id):
        """
        删除交换机。
        调用该接口删除交换机时，请注意：
            删除交换机之前，需要先删除交换机内的所有资源，包括ECS实例、SLB实例和RDS实例等。
            如果该交换机配置了SNAT条目、HAVIP等，确保已经删除了这些关联的资源。
            只有处于Available状态的交换机可以被删除。
            交换机所在的VPC正在创建/删除交换机或路由条目时，无法删除交换机。
        :param subnet_id：类型：String，必选。描述：要删除的交换机的ID。
        :return:
        """
        try:
            request = DeleteVSwitchRequest.DeleteVSwitchRequest()
            request.set_VSwitchId(subnet_id)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete subnets: {}".format(subnet_id))
            return {"result": False, "message": str(e)}

    def list_subnets(self, ids=None, **kwargs):
        """
        获取交换机信息
        :param ids: 子网id列表
        :param kwargs:aliyun DescribeVSwitchesRequest api param, see https://help.aliyun.com/
        :return:switch列表
        """
        request = DescribeVSwitchesRequest.DescribeVSwitchesRequest()
        if ids:
            request.set_VSwitchId(ids[0])
        kwargs["request"] = request
        request = self._set_switch_info_params(**kwargs)
        return self._handle_list_request_with_page("subnet", request)

    @classmethod
    def _set_switch_info_params(cls, **kwargs):
        """
        设置交换机信息参数
        :param kwargs:
        :return:
        """
        request = kwargs.pop("request", "") or DescribeVSwitchesRequest.DescribeVSwitchesRequest()
        list_optional_params = ["VpcId", "VSwitchId", "ZoneId", "PageNumber", "PageSize"]
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_accept_format("json")
        return request

    # -------------------RouteTable(路由表)------------------------------
    def list_route_tables(self, ids=None, **kwargs):
        """
        查询路由表
        :param ids: 路由表id列表
        :param kwargs:
        :return:
        """
        if ids:
            kwargs["RouteTableId"] = ids[0]
        request = DescribeRouteTableListRequest.DescribeRouteTableListRequest()
        kwargs["request"] = request
        request = self._set_route_table(**kwargs)
        return self._handle_list_request_with_page("route_table", request)

    @classmethod
    def _set_route_table(cls, **kwargs):
        """
        设置路由表参数
        :return:
        """
        request = kwargs.get("request", "")
        request = request or DescribeRouteTableListRequest.DescribeRouteTableListRequest()
        list_optional_params = [
            "RouterType",
            "RouterId",
            "VpcId",
            "RouteTableId",
            "RouteTableName",
            "PageNumber",
            "PageSize",
            "ResourceGroupId",
            "RegionId",
        ]
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_accept_format("json")
        return request

    def disassociate_route_table(self, **kwargs):
        """
        将路由表和交换机解绑
        :param kwargs:
        :return:
        """
        try:
            required_list = ["RouteTableId", "VSwitchId"]
            checkout_required_parameters(required_list, kwargs)
            request = UnassociateRouteTableRequest.UnassociateRouteTableRequest()
            list_optional_params = ["ClientToken"]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("disassociate route table failed")
            return {"result": False, "message": str(e)}

    def create_route_table(self, **kwargs):
        """
        创建自定义路由表
        :param kwargs:
            VpcId String	是	自定义路由表所属的VPC ID
            RouteTableName  String	否	路由表的名称
            Description  String	否	路由表的描述信息
            ClientToken String	否
        :return:
        """
        try:
            if "VpcId" not in kwargs:
                return {"result": False, "message": "need param VpcId"}
            request = CreateRouteTableRequest.CreateRouteTableRequest()
            list_optional_params = ["VpcId", "RouteTableName", "Description", "ClientToken"]
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["RouteTableId"]}
        except Exception as e:
            logger.exception("create route table failed")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def delete_route_table(self, route_table_id):
        """
        删除自定义路由表
        :param route_table_id:  String	是	路由表ID
        :return:
        """
        try:
            request = DeleteRouteTableRequest.DeleteRouteTableRequest()
            list_optional_params = ["RouteTableId"]
            request = set_optional_params(request, list_optional_params, {"RouteTableId": route_table_id})
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("delete route table failed")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def create_route_entry(self, **kwargs):
        """
        新建路由策略
        :param kwargs:
            RouteTableId  String	是	要创建自定义路由条目的路由表ID
            DestinationCidrBlock  String	是	自定义路由条目的目标网段
            NextHopId  String	是	自定义路由条目的下一跳实例的ID
            ClientToken  String	否
            RouteEntryName  String	否	要创建的自定义路由条目的名称
            Description  String	否	自定义路由条目的描述信息
            NextHopType  String	否	自定义路由条目的下一跳的类型
            NextHopList  list []	否
        :return:
        """
        try:
            required_list = ["RouteTableId", "DestinationCidrBlock", "NextHopId"]
            checkout_required_parameters(required_list, kwargs)
            request = CommonRequest()
            request.set_accept_format("json")
            request.set_domain("vpc.cn-guangzhou.aliyuncs.com")
            request.set_method("POST")
            request.set_protocol_type("https")
            request.set_version("2016-04-28")
            request.set_action_name("CreateRouteEntry")
            params_dict = {"RegionId": self.RegionId}
            list_optional_params = [
                "RouteTableId",
                "DestinationCidrBlock",
                "NextHopId",
                "RouteEntryName",
                "Description",
                "NextHopType",
                "NextHopList",
            ]
            [params_dict.update({item: kwargs[item]}) for item in list_optional_params if item in kwargs]
            request = add_required_params(request, params_dict)
            response = self.client.do_action(request)
            ali_result = json.loads(response)
            if ali_result.get("RouteEntryId"):
                return {"result": True, "data": ali_result["RouteEntryId"]}
            return {"result": False, "message": ali_result["Message"]}
        except Exception as e:
            logger.exception("create route entry failed")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def delete_route_entry(self, **kwagrgs):
        """
        删除路由策略
        :param kwagrgs:
            RouteTableId  String	是	路由条目所在的路由表的ID
            RouteEntryId  String	否	路由条目ID。
            DestinationCidrBlock  String	是	路由条目的目标网段，支持IPv4和IPv6网段。
            NextHopId  String	是	下一跳实例的ID
        :return:
        """
        try:
            request = DeleteRouteEntryRequest.DeleteRouteEntryRequest()
            list_optional_params = ["RouteTableId", "RouteEntryId", "DestinationCidrBlock", "NextHopId"]
            request = set_optional_params(request, list_optional_params, kwagrgs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("delete route entry failed")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def associate_route_table(self, **kwargs):
        """
        将创建的自定义路由表和同一VPC内的交换机绑定/新增关联子网
        :param kwargs:
            RouteTableId  String	是	要绑定到交换机的路由表的ID
            VSwitchId  String	是	要绑定路由表的交换机的ID。
            ClientToken  String	否
        :return:
        """
        try:
            required_list = ["autoSnapshotPolicyId", "diskIds"]
            checkout_required_parameters(required_list, kwargs)
            request = AssociateRouteTableRequest.AssociateRouteTableRequest()
            list_optional_params = ["ClientToken"]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("associate route table failed")
            return {"result": False, "message": str(e)}

    def list_route_entry(self, **kwargs):
        """
        查询路由条目列表
        :param kwargs:
            RouteTableId  String	是	要查询的路由表的ID
            RouteEntryId  String	否	要查询的路由条目的ID
            DestinationCidrBlock  String	否	路由条目的目标网段
            RouteEntryName  String	否	路由条目的名称
            IpVersion  String	否	IP协议的版本
            RouteEntryType  String	否	路由条目的类型
            NextHopId  String	否	下一跳实例ID
            NextHopType  String	否	下一跳类型
            MaxResult  Integer	否	分页大小，取值范围：20~100，默认为50。
            NextToken  String	否	下一个查询开始Token。
        :return:
        """
        try:
            if "RouteTableId" not in kwargs:
                return {"result": False, "message": "need param RouteTableId"}
            list_optional_params = [
                "RouteTableId",
                "RouteEntryId",
                "DestinationCidrBlock",
                "RouteEntryName",
                "IpVersion",
                "RouteEntryType",
                "NextHopId",
                "NextHopType",
                "MaxResult",
                "NextToken",
            ]
            request = DescribeRouteEntryListRequest.DescribeRouteEntryListRequest()
            kwargs["list_optional_params"] = list_optional_params
            return self._handle_list_request_with_next_token("route_entry", request, **kwargs)
        except Exception as e:
            logger.exception("describe_route_entry_list")
            return {"result": False, "data": [], "message": str(e)}

    #  ------------------弹性公网ip--------------------------------

    def create_eip(self, **kwargs):
        """
        申请弹性公网IP（EIP）。
        调用本接口后将在指定的地域内随机获取一个状态为Available的弹性公网IP。弹性公网IP在传输层目前只支持ICMP、
        TCP和UDP协议，不支持IGMP和SCTP等协议。
        :param kwargs:
                    ActivityId：类型：Long，描述：特殊活动ID，无需配置此参数。
                    AutoPay：类型：Boolean，描述：是否自动付费，取值：false：不开启自动付费，生成订单后需要到订单中心完成支付。
                true：开启自动付费，自动支付订单。当InstanceChargeType参数的值为PrePaid时，该参数必选；当InstanceChargeType
                参数的值为PostPaid时，该参数可不填。
                    Bandwidth：类型：String，描述：EIP的带宽峰值，取值范围：1~200，单位为Mbps。默认值为5。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值
                唯一。ClientToken只支持ASCII字符，且不能超过64个字符。
                    ISP：类型：String，描述：线路类型，默认值为BGP。如果是开通了单线带宽白名单的用户，ISP字段可以设置
                为ChinaTelecom（中国电信）、ChinaUnicom（中国联通）和ChinaMobile（中国移动）。如果是杭州金融云用户，
                该字段必填，取值：BGP_FinanceCloud。
                    InstanceChargeType：类型：String，描述：EIP的计费方式，取值：PrePaid：包年包月。
                PostPaid（默认值）：按量计费。当InstanceChargeType取值为PrePaid时，InternetChargeType必须取值
                PayByBandwidth；当InstanceChargeType取值为PostPaid时，InternetChargeType可取值PayByBandwidth
                或PayByTraffic。国际站仅支持配置为PostPaid（按量计费）。
                    InternetChargeType：类型：String，描述：EIP的计量方式，取值：PayByBandwidth（默认值）：按带宽计费。
                PayByTraffic：按流量计费。当InstanceChargeType取值为PrePaid时，InternetChargeType必须取值
                PayByBandwidth。当InstanceChargeType取值为PostPaid时，InternetChargeType可取值PayByBandwidth
                或PayByTraffic。
                    Netmode：类型：String，描述：网络类型，取值为public（公网）。
                    Period：类型：Integer，描述：购买时长。当PricingCycle取值Month时，Period取值范围为1~9。
                当PricingCycle取值Year时，Period取值范围为1~3.如果InstanceChargeType参数的值为PrePaid时，
                该参数必选，如果InstanceChargeType参数的值为PostPaid时，该参数不填。 国际站不支持配置该参数。
                    PricingCycle：类型：String，描述：包年包月的计费周期，取值：Month（默认值）：按月付费。Year：按年付费。
                当InstanceChargeType参数的值为PrePaid时，该参数必选；当InstanceChargeType参数的值为PostPaid时，该参数可不填。
                国际站不支持配置该参数。
                    ResourceGroupId：类型：String，描述：企业资源组ID。

         :kwargs (dict): {eip_info: {bandwidth_size: "", charge_type: "", period: "", charge_mode: ""}}
        :return:示例：{
                        "result": True,
                        "data":{
                                "AllocationId": "eip-25877c70x",
                                "EipAddress": "123.56.0.206",
                                "RequestId": "B6B9F518-60F8-4D81-9242-1207B356754D"
                            }
                        }
        """
        try:
            request = AllocateEipAddressRequest.AllocateEipAddressRequest()
            list_optional_params = [
                "ActivityId",
                "AutoPay",
                "Bandwidth",
                "ClientToken",
                "ISP",
                "InstanceChargeType",
                "InternetChargeType",
                "Netmode",
                "Period",
                "PricingCycle",
                "ResourceGroupId",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["AllocationId"]}
        except Exception as e:
            logger.exception("create_eip")
            return {"result": False, "message": str(e)}

    def associate_address(self, **kwargs):
        """
        将弹性公网IP（EIP）绑定到同地域的云产品实例上。
        在调用本接口时，请注意：
            EIP可绑定到同地域的专有网络ECS实例、专有网络的SLB实例、专有网络类型的辅助弹性网卡和NAT网关上。
        :param kwargs:
                    eip_id：类型：String，必选。描述：绑定云产品实例的EIP的ID。
                    instance_id：类型：String，必选。描述：要绑定EIP的实例ID。
                    InstanceType：类型：String，描述：要绑定EIP的实例的类型，取值：Nat：NAT网关。SlbInstance：负载均衡SLB。
                EcsInstance：云服务器ECS。NetworkInterface：辅助弹性网卡。
                    InstanceRegionId：类型：String，描述：要绑定EIP的实例所属地域的ID.仅在EIP加入到带宽共享性全球加速
                实例后，才需要填写该参数。
                    PrivateIpAddress：类型：String，描述：交换机网段内的一个IP地址。如果不输入该参数，系统根据VPC
                ID和交换机ID自动分配一个私网IP地址。
                    Mode：类型：String，描述：绑定模式，取值：NAT（默认值）：NAT模式（普通模式）。MULTI_BINDED：多EIP
                网卡可见模式。BINDED：EIP网卡可见模式。该参数暂不支持传入 BINDED，如需设置，请前往控制台设置EIP网卡
                可见模式。仅InstanceType配置为NetworkInterface时，才需要配置该参数。
        :return:
        """
        try:
            request = AssociateEipAddressRequest.AssociateEipAddressRequest()
            request.set_AllocationId(kwargs["eip_id"])
            request.set_InstanceId(kwargs["instance_id"])
            list_optional_params = ["InstanceType", "InstanceRegionId", "PrivateIpAddress", "Mode"]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("associate_address")
            return {"result": False, "message": str(e)}

    def disassociate_address(self, **kwargs):
        """
        将弹性公网IP（EIP）从绑定的云产品上解绑。
        :param kwargs:
                    AllocationId：类型：String，必选。描述：绑定云产品实例的EIP的ID。
                    Force：类型：Boolean，描述：当EIP绑定了NAT网关，且NAT网关添加了DNAT或SNAT条目时，是否强制解绑EIP，
                取值：false（默认值）：不强制解绑EIP。true：强制解绑EIP。
                    InstanceId：类型：String，描述：要解绑EIP的云产品实例的ID。
                    InstanceType：类型：String，描述：要解绑EIP的云产品类型，取值：EcsInstance（默认值）：专有网络类型的ECS实例。
                SlbInstance：专有网络类型的SLB实例。NetworkInterface：专有网络类型的辅助弹性网卡。Nat：NAT网关。HaVip：高可用虚拟IP。
                    PrivateIpAddress：类型：String，描述：要解绑EIP的ECS实例或ENI实例的私网IP地址。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数
                值唯一。ClientToken只支持ASCII字符，且不能超过64个字符。
        :return:
        """
        try:
            request = UnassociateEipAddressRequest.UnassociateEipAddressRequest()
            request.set_AllocationId(kwargs["eip_id"])
            list_optional_params = ["Force", "InstanceId", "InstanceType", "PrivateIpAddress", "ClientToken"]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("disassociate_address")
            return {"result": False, "message": str(e)}

    def modify_eip_band_width(self, **kwargs):
        """
        修改指定EIP的名称、描述信息和带宽峰值。
        :param kwargs:
                    eip_id：类型：String，必选。描述：要修改的EIP的ID。
                    Bandwidth：类型：String，描述：EIP的带宽峰值，取值：1~200，单位为Mbps。
                    Description：类型：String，描述：EIP的描述信息。长度为2~256个字符，必须以字母或中文开头，
                但不能以http://或https://开头。
                    Name：类型：String，描述：EIP的名称。长度为2~128个字符，必须以字母或中文开头，可包含数字、
                点号（.）、下划线（_）和短横线（-）。但不能以http://或https://开头。
        :return:
        """
        try:
            request = ModifyEipAddressAttributeRequest.ModifyEipAddressAttributeRequest()
            request.set_AllocationId(kwargs["eip_id"])
            if "bandwidth" in kwargs:
                request.set_Bandwidth(kwargs["bandwidth"])
            list_optional_params = ["Bandwidth", "Description", "Name"]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_eip_band_width")
            return {"result": False, "message": str(e)}

    def release_eip(self, eip_id):
        """
        释放指定的弹性公网IP（EIP）。
        释放EIP前，请确保满足以下条件：
            只有处于Available状态的EIP才可以被释放。
            仅按量计费类型的EIP支持释放，包年包月类型的EIP不支持释放。
        :param eip_id:
                   eip_id：类型：String，必选。描述：要释放的EIP的ID。
        :return:
        """
        try:
            request = ReleaseEipAddressRequest.ReleaseEipAddressRequest()
            request.set_AllocationId(eip_id)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("release_eip:" + eip_id)
            return {"result": False, "message": str(e)}

    @classmethod
    def _set_outnetip_info_params(cls, request, **kwargs):
        """
        设置外网信息参数
        :param kwargs:
        :return:
        """
        list_optional_params = [
            "Status",
            "AllocationId",
            "AssociatedInstanceType",
            "AssociatedInstanceId",
            "PageNumber",
            "PageSize",
        ]
        request = set_optional_params(request, list_optional_params, kwargs)
        return request

    # def list_eips(self, ids=None, **kwargs):
    #     """
    #     获取外网信息
    #     :param ids: eipId 列表
    #     :param kwargs:aliyun DescribeEipAddressesRequest api param, see https://help.aliyun.com/
    #     :return:eip列表
    #     """
    #     request = DescribeEipAddressesRequest.DescribeEipAddressesRequest()
    #     if ids:
    #         request.set_AllocationId(ids[0])
    #     request = self._set_outnetip_info_params(request, **kwargs)
    #     return self._handle_list_request_with_page("eip", request)

    #  ------------------安全组--------------------------
    @classmethod
    def _set_security_groups_info_params(cls, request, **kwargs):
        """
        设置安全组信息参数
        :param kwargs:
        :return:
        """
        list_optional_params = [
            "VpcId",
            "Tag.1.Key",
            "Tag.1.Value",
            "Tag.2.Key",
            "Tag.2.Value",
            "PageNumber",
            "PageSize",
            "SecurityGroupIds",
            "SecurityGroupName",
            "NetworkType",
            "SecurityGroupId",
            "ResourceGroupId",
        ]
        request = set_optional_params(request, list_optional_params, kwargs)
        return request

    def list_security_groups(self, ids=None, **kwargs):
        """
        获取安全组信息参数
        :param ids: 安全组id 列表
        :param kwargs:aliyun DescribeSecurityGroupsRequest api param, see https://help.aliyun.com/
        :return:安全组列表
        """
        request = DescribeSecurityGroupsRequest.DescribeSecurityGroupsRequest()
        if ids:
            request.set_SecurityGroupIds(json.dumps(ids))
        request = self._set_security_groups_info_params(request, **kwargs)
        return self._handle_list_request_with_page("security_group", request)

    def create_security_group(self, **kwargs):
        """
            新建一个安全组。新建的安全组，默认只允许安全组内的实例互相访问，安全组外的一切通信请求会被拒绝。若您想允许其他
        安全组实例的通信请求，或者来自互联网的访问请求，需要授权安全组权限（AuthorizeSecurityGroup）。
            调用该接口时，您需要注意：
                在一个阿里云地域下，您最多可以创建100个安全组。
                创建专有网络VPC类型的安全组时，您必须指定参数VpcId。
            :param kwargs:
                        VpcId：类型：String，描述：安全组所属VPC ID。
                        Description：类型：String，描述：安全组描述信息。长度为2~256个英文或中文字符，不能以http://和
                    https://开头。默认值：空。
                        ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该
                    参数值唯一。ClientToken只支持ASCII字符，且不能超过64个字符。
                        SecurityGroupName：类型：String，描述：安全组名称。长度为2~128个英文或中文字符。必须以大小字母或
                    中文开头，不能以 http://和https://开头。可以包含数字、半角冒号（:）、下划线（_）或者连字符（-）。默认值：空。
                        SecurityGroupType：类型：String，描述：安全组类型，分为普通安全组与企业安全组。取值范围：normal：普通安全组。
                    enterprise：企业安全组。
                        Tag.N.value：类型：String，描述：安全组的标签值。N的取值范围：1~20。一旦传入该值，则不允许为空字符串。
                    最多支持128个字符，不能以aliyun和acs:开头，不能包含http://或者https://。
                        Tag.N.key：类型：String，描述：安全组的标签键。N的取值范围：1~20。一旦传入该值，允许为空字符串。最多支持
                    128个字符，不能以acs:开头，不能包含http://或者https://。
                        ResourceGroupId：类型：String，描述：安全组所在的企业资源组ID。
            :return:data: ali_result["SecurityGroupId"]:安全组ID。
        """
        try:
            request = CreateSecurityGroupRequest.CreateSecurityGroupRequest()
            list_optional_params = [
                "VpcId",
                "Description",
                "ClientToken",
                "SecurityGroupName",
                "SecurityGroupType",
                "Tags",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["SecurityGroupId"]}
        except Exception as e:
            logger.exception("create_security_group")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def delete_security_group(self, security_group_id):
        """
        删除安全组之前，请确保安全组内不存在实例，并且没有其他安全组与该安全组有授权行为（DescribeSecurityGroupReferences），否则DeleteSecurityGroup请求失败。
        security_group_id
                     类型：String. 描述：安全组ID
        :return:data: ali_result["SecurityGroupId"]:安全组ID。
        """
        try:
            request = DeleteSecurityGroupRequest.DeleteSecurityGroupRequest()
            list_optional_params = ["SecurityGroupId"]
            request = set_optional_params(request, list_optional_params, {"SecurityGroupId": security_group_id})
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("delete security group failed")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def authorize_security_group(self, **kwargs):
        """
        增加一条入方向安全组规则。指定安全组入方向的访问权限，允许或者拒绝其他设备发送入方向流量到安全组里的实例。
        :param kwargs:
                    IpProtocol：类型：String，必选。描述：传输层协议。取值大小写敏感。取值范围：tcp、udp、icmp、gre、
                all：支持所有协议。此处icmp协议仅支持IPv4地址。
                    PortRange：类型：String，必选。描述：目的端安全组开放的传输层协议相关的端口范围。取值范围：TCP/UDP协
                议：取值范围1~65535。使用斜线（/）隔开起始端口和终止端口。正确示范：1/200；错误示范：200/1。ICMP协议：-1/-1。
                GRE协议：-1/-1。IpProtocol取值为all：-1/-1。
                    SecurityGroupId：类型：String，描述：目的端安全组ID。
                    SourceGroupId：类型：String，描述：需要设置访问权限的源端安全组ID。至少设置一项SourceGroupId或者
                SourceCidrIp参数。如果指定了SourceGroupId没有指定参数SourceCidrIp，则参数NicType取值只能为intranet。
                如果同时指定了SourceGroupId和SourceCidrIp，则默认以SourceCidrIp为准。
                    SourceGroupOwnerId：类型：Long，描述：跨账户设置安全组规则时，源端安全组所属的阿里云账户ID。如果
                SourceGroupOwnerId及SourceGroupOwnerAccount均未设置，则认为是设置您其他安全组的访问权限。如果您已经
                设置参数SourceCidrIp，则参数SourceGroupOwnerId无效。
                    SourceGroupOwnerAccount：类型：String，描述：跨账户设置安全组规则时，源端安全组所属的阿里云账户。
                如果SourceGroupOwnerAccount及SourceGroupOwnerId均未设置，则认为是设置您其他安全组的访问权限.如果已
                经设置参数SourceCidrIp，则参数SourceGroupOwnerAccount无效。
                    SourceCidrIp：类型：String，描述：源端IPv4 CIDR地址段。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6SourceCidrIp：类型：String，描述：源端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支持
                VPC类型ECS实例的IPv6地址。默认值：无。
                    SourcePortRange：类型：String，描述：源端安全组开放的传输层协议相关的端口范围。取值范围：TCP/UDP协
                议：取值范围为1~65535。使用斜线（/）隔开起始端口和终止端口。正确示范：1/200；错误示范：200/1。ICMP协
                议：-1/-1。GRE协议：-1/-1。all：-1/-1。
                    DestCidrIp：类型：String，描述：目的端IPv4 CIDR地址段。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6DestCidrIp：类型：String，描述：目的端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支
                持VPC类型ECS实例的IPv6地址。默认值：无。
                    Policy：类型：String，描述：设置访问权限。取值范围：accept（默认）：接受访问。drop：拒绝访问，不返回
                拒绝信息，表现为发起端请求超时或者无法建立连接的类似信息。
                    Priority：类型：String，描述：安全组规则优先级，数字越小，代表优先级越高。取值范围：1~100.默认值：1。
                    NicType：类型：String，描述：经典网络类型安全组规则的网卡类型。取值范围：internet：公网网卡。
                intranet：内网网卡。专有网络VPC类型安全组规则无需设置网卡类型，默认为intranet，只能为intranet。设置安全
                组之间互相访问时，即指定了DestGroupId且没有指定DestCidrIp，只能为intranet。默认值：internet。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值
                唯一。ClientToken只支持ASCII字符，且不能超过64个字符。更多详情，请参见如何保证幂等性。
                    Description：类型：String，描述：安全组规则的描述信息。长度为1~512个字符。
        :return:
        """
        try:
            request = AuthorizeSecurityGroupRequest.AuthorizeSecurityGroupRequest()
            list_required_params = ["IpProtocol", "SecurityGroupId", "PortRange", "SourceCidrIp", "Policy"]
            request = set_required_params(request, list_required_params, kwargs)
            list_optional_params = [
                "SourceGroupId",
                "SourceGroupOwnerId",
                "SourceGroupOwnerAccount",
                "SourceCidrIp",
                "Ipv6SourceCidrIp",
                "SourcePortRange",
                "DestCidrIp",
                "Ipv6DestCidrIp",
                "Policy",
                "Priority",
                "NicType",
                "ClientToken",
                "Description",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("authorize_security_group")
            logger.exception(kwargs)
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def authorize_security_group_egress(self, **kwargs):
        """
        增加一条安全组出方向规则。指定安全组出方向的访问权限，允许或者拒绝安全组里的实例发送出方向流量到其他设备。
        :param kwargs:
                    IpProtocol：类型：String，必选。描述：传输层协议。取值大小写敏感。取值范围：tcp、udp、icmp、gre、
                all：支持所有协议。此处icmp协议仅支持IPv4地址。
                    PortRange：类型：String，必选。描述：目的端安全组开放的传输层协议相关的端口范围。取值范围：TCP/UDP协
                议：取值范围1~65535。使用斜线（/）隔开起始端口和终止端口。正确示范：1/200；错误示范：200/1。ICMP协议：-1/-1。
                GRE协议：-1/-1。IpProtocol取值为all：-1/-1。
                    SecurityGroupId：类型：String，描述：源端安全组ID。
                    DestGroupId：类型：String，描述：跨账户设置安全组规则时，目的端安全组所属的阿里云账户ID。如果
                DestGroupOwnerId及DestGroupOwnerAccount均未设置，则认为是设置您其他安全组的访问权限。如果您已经设置
                参数DestCidrIp，则参数DestGroupOwnerId无效。
                    DestGroupOwnerId：类型：String，描述：跨账户设置安全组规则时，目的端安全组所属的阿里云账户ID。如果
                DestGroupOwnerId及DestGroupOwnerAccount均未设置，则认为是设置您其他安全组的访问权限。如果您已经设置参数
                DestCidrIp，则参数DestGroupOwnerId无效。
                    DestGroupOwnerAccount：类型：Long，描述：跨账户设置安全组规则时，目的端安全组所属的阿里云账户。如果
                DestGroupOwnerAccount及DestGroupOwnerId均未设置，则认为是设置您其他安全组的访问权限。如果已经设置参数
                DestCidrIp，则参数DestGroupOwnerAccount无效。
                    DestCidrIp：类型：String，描述：目的端IP地址范围。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6DestCidrIp：类型：String，描述：目的端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支持
                VPC类型ECS实例的IPv6地址。默认值：无。
                    SourceCidrIp：类型：String，描述：源端IP地址范围。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6SourceCidrIp：类型：String，描述：源端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支
                持VPC类型IP地址。默认值：无。
                    Policy：类型：String，描述：设置访问权限。取值范围：accept（默认）：接受访问。drop：拒绝访问，不返回
                拒绝信息。默认值：accept。
                    Priority：类型：String，描述：安全组规则优先级，数字越小，代表优先级越高。取值范围：1~100.默认值：1。
                    NicType：类型：String，描述：经典网络类型安全组规则的网卡类型。取值范围：internet：公网网卡。
                intranet：内网网卡。专有网络VPC类型安全组规则无需设置网卡类型，默认为intranet，只能为intranet。设置安全
                组之间互相访问时，即指定了DestGroupId且没有指定DestCidrIp，只能为intranet。默认值：internet。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值
                唯一。ClientToken只支持ASCII字符，且不能超过64个字符。更多详情，请参见如何保证幂等性。
                    Description：类型：String，描述：安全组规则的描述信息。长度为1~512个字符。
        :return:
        """
        try:
            request = AuthorizeSecurityGroupEgressRequest.AuthorizeSecurityGroupEgressRequest()
            list_required_params = ["IpProtocol", "SecurityGroupId", "PortRange", "DestCidrIp", "Policy"]
            request = set_required_params(request, list_required_params, kwargs)
            list_optional_params = [
                "DestGroupId",
                "DestGroupOwnerId",
                "DestGroupOwnerAccount",
                "DestCidrIp",
                "Ipv6DestCidrIp",
                "SourceCidrIp",
                "Ipv6SourceCidrIp",
                "SourcePortRange",
                "Policy",
                "Priority",
                "NicType",
                "ClientToken",
                "Description",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("authorize_security_group_egress")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def revoke_security_group(self, **kwargs):
        """
        删除一条安全组入方向规则，撤销安全组入方向的权限设置。
        :param kwargs:
                    IpProtocol：类型：String，必选。描述：传输层协议。取值大小写敏感。取值范围：tcp、udp、icmp、gre、
                all：支持所有协议。此处icmp协议仅支持IPv4地址。
                    PortRange：类型：String，必选。描述：目的端安全组开放的传输层协议相关的端口范围。取值范围：TCP/UDP协
                议：取值范围1~65535。使用斜线（/）隔开起始端口和终止端口。正确示范：1/200；错误示范：200/1。ICMP协议：-1/-1。
                GRE协议：-1/-1。IpProtocol取值为all：-1/-1。
                    SecurityGroupId：类型：String，描述：目的端安全组ID。
                    DestCidrIp：类型：String，描述：目的端IP地址范围。支持CIDR格式和IPv4格式的IP地址范围。
                默认值：0.0.0.0/0
                    Ipv6DestCidrIp：类型：String，描述：目的端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支
                持VPC类型的IP地址。默认值：无。
                    SourceGroupId：类型：String，描述：需要设置访问权限的源端安全组ID。至少设置一项SourceGroupId或者
                SourceCidrIp参数。如果指定了SourceGroupId没有指定参数SourceCidrIp，则参数NicType取值只能为intranet。
                如果同时指定了SourceGroupId和SourceCidrIp，则默认以SourceCidrIp为准。
                    SourceGroupOwnerId：类型：Long，描述：跨账户设置安全组规则时，源端安全组所属的阿里云账户ID。如果
                SourceGroupOwnerId及SourceGroupOwnerAccount均未设置，则认为是设置您其他安全组的访问权限。如果您已经
                设置参数SourceCidrIp，则参数SourceGroupOwnerId无效。
                    SourceGroupOwnerAccount：类型：String，描述：跨账户设置安全组规则时，源端安全组所属的阿里云账户。
                如果SourceGroupOwnerAccount及SourceGroupOwnerId均未设置，则认为是设置您其他安全组的访问权限.如果已
                经设置参数SourceCidrIp，则参数SourceGroupOwnerAccount无效。
                    SourceCidrIp：类型：String，描述：源端IP地址范围。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6SourceCidrIp：类型：String，描述：源端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支持
                VPC类型ECS实例的IPv6地址。默认值：无。
                    SourcePortRange：类型：String，描述：源端安全组开放的传输层协议相关的端口范围。取值范围：TCP/UDP协
                议：取值范围为1~65535。使用斜线（/）隔开起始端口和终止端口。正确示范：1/200；错误示范：200/1。ICMP协
                议：-1/-1。GRE协议：-1/-1。all：-1/-1。
                    Policy：类型：String，描述：设置访问权限。取值范围：accept（默认）：接受访问。drop：拒绝访问，不返回
                拒绝信息，表现为发起端请求超时或者无法建立连接的类似信息。
                    Priority：类型：String，描述：安全组规则优先级，数字越小，代表优先级越高。取值范围：1~100.默认值：1。
                    NicType：类型：String，描述：经典网络类型安全组规则的网卡类型。取值范围：internet：公网网卡。
                intranet：内网网卡。专有网络VPC类型安全组规则无需设置网卡类型，默认为intranet，只能为intranet。设置安全
                组之间互相访问时，即指定了DestGroupId且没有指定DestCidrIp，只能为intranet。默认值：internet。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值
                唯一。ClientToken只支持ASCII字符，且不能超过64个字符。更多详情，请参见如何保证幂等性。
                    Description：类型：String，描述：安全组规则的描述信息。长度为1~512个字符。
        :return:
        """
        try:
            request = RevokeSecurityGroupRequest.RevokeSecurityGroupRequest()
            list_required_params = ["IpProtocol", "SecurityGroupId", "PortRange"]
            request = set_required_params(request, list_required_params, kwargs)
            list_optional_params = [
                "DestCidrIp",
                "Ipv6DestCidrIp",
                "SourceGroupId",
                "SourceGroupOwnerId",
                "SourceGroupOwnerAccount",
                "SourceCidrIp",
                "Ipv6SourceCidrIp",
                "SourcePortRange",
                "Policy",
                "Priority",
                "NicType",
                "ClientToken",
                "Description",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("revoke_security_group")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def revoke_security_groupEgress(self, **kwargs):
        """
        删除一条安全组出方向规则。指定安全组出方向的访问权限，允许或者拒绝安全组里的实例发送出方向流量到其他设备。
        :param kwargs:
                    IpProtocol：类型：String，必选。描述：传输层协议。取值大小写敏感。取值范围：tcp、udp、icmp、gre、
                all：支持所有协议。此处icmp协议仅支持IPv4地址。
                    PortRange：类型：String，必选。描述：目的端安全组开放的传输层协议相关的端口范围。取值范围：TCP/UDP协
                议：取值范围1~65535。使用斜线（/）隔开起始端口和终止端口。正确示范：1/200；错误示范：200/1。ICMP协议：-1/-1。
                GRE协议：-1/-1。IpProtocol取值为all：-1/-1。
                    SecurityGroupId：类型：String，描述：源端安全组ID。
                    DestGroupId：类型：String，描述：跨账户设置安全组规则时，目的端安全组所属的阿里云账户ID。如果
                DestGroupOwnerId及DestGroupOwnerAccount均未设置，则认为是设置您其他安全组的访问权限。如果您已经设置
                参数DestCidrIp，则参数DestGroupOwnerId无效。
                    DestGroupOwnerId：类型：String，描述：跨账户设置安全组规则时，目的端安全组所属的阿里云账户ID。如果
                DestGroupOwnerId及DestGroupOwnerAccount均未设置，则认为是设置您其他安全组的访问权限。如果您已经设置参数
                DestCidrIp，则参数DestGroupOwnerId无效。
                    DestGroupOwnerAccount：类型：Long，描述：跨账户设置安全组规则时，目的端安全组所属的阿里云账户。如果
                DestGroupOwnerAccount及DestGroupOwnerId均未设置，则认为是设置您其他安全组的访问权限。如果已经设置参数
                DestCidrIp，则参数DestGroupOwnerAccount无效。
                    DestCidrIp：类型：String，描述：目的端IP地址范围。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6DestCidrIp：类型：String，描述：目的端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支持
                VPC类型ECS实例的IPv6地址。默认值：无。
                    SourceCidrIp：类型：String，描述：源端IP地址范围。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6SourceCidrIp：类型：String，描述：源端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支
                持VPC类型IP地址。默认值：无。
                    Policy：类型：String，描述：设置访问权限。取值范围：accept（默认）：接受访问。drop：拒绝访问，不返回
                拒绝信息。默认值：accept。
                    Priority：类型：String，描述：安全组规则优先级，数字越小，代表优先级越高。取值范围：1~100.默认值：1。
                    NicType：类型：String，描述：经典网络类型安全组规则的网卡类型。取值范围：internet：公网网卡。
                intranet：内网网卡。专有网络VPC类型安全组规则无需设置网卡类型，默认为intranet，只能为intranet。设置安全
                组之间互相访问时，即指定了DestGroupId且没有指定DestCidrIp，只能为intranet。默认值：internet。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值
                唯一。ClientToken只支持ASCII字符，且不能超过64个字符。更多详情，请参见如何保证幂等性。
                    Description：类型：String，描述：安全组规则的描述信息。长度为1~512个字符。
        :return:
        """
        try:
            request = RevokeSecurityGroupEgressRequest.RevokeSecurityGroupEgressRequest()
            list_required_params = ["IpProtocol", "SecurityGroupId", "PortRange"]
            request = set_required_params(request, list_required_params, kwargs)
            list_optional_params = [
                "DestGroupId",
                "DestGroupOwnerId",
                "DestGroupOwnerAccount",
                "DestCidrIp",
                "Ipv6DestCidrIp",
                "SourceCidrIp",
                "Ipv6SourceCidrIp",
                "SourcePortRange",
                "Policy",
                "Priority",
                "NicType",
                "ClientToken",
                "Description",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("revoke_security_groupEgress")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def list_security_group_rules(self, security_group_id, **kwargs):
        """
        查询一个安全组的安全组规则。
        security_group_id (str): 安全组id
        :param kwargs:
                    security_group_id：类型：String，必选。描述：安全组ID。
                    NicType：类型：String，描述：经典网络类型安全组规则的网卡类型。取值范围：internet：公网网卡。
                intranet：内网网卡。专有网络VPC类型安全组规则无需设置网卡类型，默认为intranet，只能为intranet。设置安全
                组之间互相访问时，即指定了DestGroupId且没有指定DestCidrIp，只能为intranet。默认值：internet。
                    Direction：类型：String，描述：安全组规则授权方向。取值范围：egress：安全组出方向.ingress：安全组入方向.
                all：不区分方向.默认值：all。
        :return:
        """
        request = DescribeSecurityGroupAttributeRequest.DescribeSecurityGroupAttributeRequest()
        if not security_group_id:
            return {"result": False, "message": "安全组id不能为空"}
        list_optional_params = ["NicType", "Direction"]
        request = set_optional_params(request, list_optional_params, kwargs)
        request.set_SecurityGroupId(security_group_id)

        try:
            ali_result = self._get_result(request, True)
        except Exception as e:
            logger.exception("获取阿里云{}调用接口失败{}".format("security_group_rule", e))
            return {"result": False, "message": str(e)}

        copy_ali_result = copy.deepcopy(ali_result)
        copy_ali_result.pop("Permissions")

        data = self._format_resource_result("security_group_rule", ali_result, **copy_ali_result)
        return {"result": True, "data": data}

        # return self._handle_list_request("security_group_rule", request)

    def modify_security_group_attribute(self, **kwargs):
        """
        修改一个安全组的名称或者描述。
        :param kwargs:
                    SecurityGroupId：类型：String。必选。描述：安全组ID。
                    SecurityGroupName：类型：String。描述：安全组名称。 长度为2~128个英文或中文字符。必须以大小字母或
                中文开头，不能以http://和https://开头。可以包含数字、半角冒号（:）、下划线（_）或者连字符（-）。默认值：空。
                    Description：类型：String，描述：安全组描述信息。长度为2~256个英文或中文字符，不能以http://和
                https://开头。默认值：空。
        :return:
        """
        try:
            request = ModifySecurityGroupAttributeRequest.ModifySecurityGroupAttributeRequest()
            request.set_SecurityGroupId(kwargs["SecurityGroupId"])
            list_optional_params = ["SecurityGroupName", "Description"]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_security_group_attribute")
            return {"result": False, "message": str(e)}

    def modify_security_group_rule(self, **kwargs):
        """
        修改安全组入方向规则的描述信息。该接口只能修改描述信息，如果您需要修改安全组规则的策略、端口范围、授权对象等信息，请在ECS管理控制台修改。
        :param kwargs:
                  IpProtocol：类型：String，必选。描述：传输层协议。取值大小写敏感。取值范围：tcp、udp、icmp、gre、
                all：支持所有协议。此处icmp协议仅支持IPv4地址。
                    PortRange：类型：String，必选。描述：目的端安全组开放的传输层协议相关的端口范围。取值范围：TCP/UDP协
                议：取值范围1~65535。使用斜线（/）隔开起始端口和终止端口。正确示范：1/200；错误示范：200/1。ICMP协议：-1/-1。
                GRE协议：-1/-1。IpProtocol取值为all：-1/-1。
                    SecurityGroupId：类型：String，描述：目的端安全组ID。
                    SourceGroupId：类型：String，描述：需要设置访问权限的源端安全组ID。至少设置一项SourceGroupId或者
                SourceCidrIp参数。如果指定了SourceGroupId没有指定参数SourceCidrIp，则参数NicType取值只能为intranet。
                如果同时指定了SourceGroupId和SourceCidrIp，则默认以SourceCidrIp为准。
                    SourceGroupOwnerId：类型：Long，描述：跨账户设置安全组规则时，源端安全组所属的阿里云账户ID。如果
                SourceGroupOwnerId及SourceGroupOwnerAccount均未设置，则认为是设置您其他安全组的访问权限。如果您已经
                设置参数SourceCidrIp，则参数SourceGroupOwnerId无效。
                    SourceGroupOwnerAccount：类型：String，描述：跨账户设置安全组规则时，源端安全组所属的阿里云账户。
                如果SourceGroupOwnerAccount及SourceGroupOwnerId均未设置，则认为是设置您其他安全组的访问权限.如果已
                经设置参数SourceCidrIp，则参数SourceGroupOwnerAccount无效。
                    SourceCidrIp：类型：String，描述：源端IPv4 CIDR地址段。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6SourceCidrIp：类型：String，描述：源端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支持
                VPC类型ECS实例的IPv6地址。默认值：无。
                    SourcePortRange：类型：String，描述：源端安全组开放的传输层协议相关的端口范围。取值范围：TCP/UDP协
                议：取值范围为1~65535。使用斜线（/）隔开起始端口和终止端口。正确示范：1/200；错误示范：200/1。ICMP协
                议：-1/-1。GRE协议：-1/-1。all：-1/-1。
                    DestCidrIp：类型：String，描述：目的端IPv4 CIDR地址段。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6DestCidrIp：类型：String，描述：目的端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支
                持VPC类型ECS实例的IPv6地址。默认值：无。
                    Policy：类型：String，描述：设置访问权限。取值范围：accept（默认）：接受访问。drop：拒绝访问，不返回
                拒绝信息，表现为发起端请求超时或者无法建立连接的类似信息。
                    Priority：类型：String，描述：安全组规则优先级，数字越小，代表优先级越高。取值范围：1~100.默认值：1。
                    NicType：类型：String，描述：经典网络类型安全组规则的网卡类型。取值范围：internet：公网网卡。
                intranet：内网网卡。专有网络VPC类型安全组规则无需设置网卡类型，默认为intranet，只能为intranet。设置安全
                组之间互相访问时，即指定了DestGroupId且没有指定DestCidrIp，只能为intranet。默认值：internet。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值
                唯一。ClientToken只支持ASCII字符，且不能超过64个字符。更多详情，请参见如何保证幂等性。
                    Description：类型：String，描述：安全组规则的描述信息。长度为1~512个字符。
        :return:
        """
        try:
            request = ModifySecurityGroupRuleRequest.ModifySecurityGroupRuleRequest()
            list_required_params = ["IpProtocol", "SecurityGroupId", "PortRange"]
            request = set_required_params(request, list_required_params, kwargs)
            list_optional_params = [
                "DestCidrIp",
                "Ipv6DestCidrIp",
                "SourceGroupId",
                "SourceGroupOwnerId",
                "SourceGroupOwnerAccount",
                "SourceCidrIp",
                "Ipv6SourceCidrIp",
                "SourcePortRange",
                "Policy",
                "Priority",
                "NicType",
                "ClientToken",
                "Description",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_security_group_rule")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def modify_security_group_egress_rule(self, **kwargs):
        """
        修改安全组出方向规则的描述信息。该接口只能修改描述信息，如果您需要修改安全组规则的策略、端口范围、授权对象等信息，
        请在ECS管理控制台修改。
        :param kwargs:
                    IpProtocol：类型：String，必选。描述：传输层协议。取值大小写敏感。取值范围：tcp、udp、icmp、gre、
                all：支持所有协议。此处icmp协议仅支持IPv4地址。
                    PortRange：类型：String，必选。描述：目的端安全组开放的传输层协议相关的端口范围。取值范围：TCP/UDP协
                议：取值范围1~65535。使用斜线（/）隔开起始端口和终止端口。正确示范：1/200；错误示范：200/1。ICMP协议：-1/-1。
                GRE协议：-1/-1。IpProtocol取值为all：-1/-1。
                    SecurityGroupId：类型：String，描述：源端安全组ID。
                    DestGroupId：类型：String，描述：跨账户设置安全组规则时，目的端安全组所属的阿里云账户ID。如果
                DestGroupOwnerId及DestGroupOwnerAccount均未设置，则认为是设置您其他安全组的访问权限。如果您已经设置
                参数DestCidrIp，则参数DestGroupOwnerId无效。
                    DestGroupOwnerId：类型：String，描述：跨账户设置安全组规则时，目的端安全组所属的阿里云账户ID。如果
                DestGroupOwnerId及DestGroupOwnerAccount均未设置，则认为是设置您其他安全组的访问权限。如果您已经设置参数
                DestCidrIp，则参数DestGroupOwnerId无效。
                    DestGroupOwnerAccount：类型：Long，描述：跨账户设置安全组规则时，目的端安全组所属的阿里云账户。如果
                DestGroupOwnerAccount及DestGroupOwnerId均未设置，则认为是设置您其他安全组的访问权限。如果已经设置参数
                DestCidrIp，则参数DestGroupOwnerAccount无效。
                    DestCidrIp：类型：String，描述：目的端IP地址范围。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6DestCidrIp：类型：String，描述：目的端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支持
                VPC类型ECS实例的IPv6地址。默认值：无。
                    SourceCidrIp：类型：String，描述：源端IP地址范围。支持CIDR格式和IPv4格式的IP地址范围。默认值：无。
                    Ipv6SourceCidrIp：类型：String，描述：源端IPv6 CIDR地址段。支持CIDR格式和IPv6格式的IP地址范围。仅支
                持VPC类型IP地址。默认值：无。
                    Policy：类型：String，描述：设置访问权限。取值范围：accept（默认）：接受访问。drop：拒绝访问，不返回
                拒绝信息。默认值：accept。
                    Priority：类型：String，描述：安全组规则优先级，数字越小，代表优先级越高。取值范围：1~100.默认值：1。
                    NicType：类型：String，描述：经典网络类型安全组规则的网卡类型。取值范围：internet：公网网卡。
                intranet：内网网卡。专有网络VPC类型安全组规则无需设置网卡类型，默认为intranet，只能为intranet。设置安全
                组之间互相访问时，即指定了DestGroupId且没有指定DestCidrIp，只能为intranet。默认值：internet。
                    ClientToken：类型：String，描述：保证请求幂等性。从您的客户端生成一个参数值，确保不同请求间该参数值
                唯一。ClientToken只支持ASCII字符，且不能超过64个字符。更多详情，请参见如何保证幂等性。
                    Description：类型：String，描述：安全组规则的描述信息。长度为1~512个字符。
        :return:
        """
        try:
            request = ModifySecurityGroupEgressRuleRequest.ModifySecurityGroupEgressRuleRequest()
            list_required_params = ["IpProtocol", "SecurityGroupId", "PortRange"]
            request = set_required_params(request, list_required_params, kwargs)
            list_optional_params = [
                "DestGroupId",
                "DestGroupOwnerId",
                "DestGroupOwnerAccount",
                "DestCidrIp",
                "Ipv6DestCidrIp",
                "SourceCidrIp",
                "Ipv6SourceCidrIp",
                "SourcePortRange",
                "Policy",
                "Priority",
                "NicType",
                "ClientToken",
                "Description",
            ]
            request = set_optional_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_security_group_egress_rule")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def associate_security_groups(self, **kwargs):
        """
        将一台ECS实例加入到指定的安全组。
        :param kwargs:
            InstanceId: string
            SecurityGroupId: string
        :type kwargs:
        :return:
        :rtype:
        """
        try:
            request = JoinSecurityGroupRequest.JoinSecurityGroupRequest()
            list_required_params = ["InstanceId", "SecurityGroupId"]
            request = set_required_params(request, list_required_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("associate_security_groups")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def disassociate_security_groups(self, **kwargs):
        """
        将一台ECS实例移出指定的安全组
        :param kwargs:
            InstanceId: string
            SecurityGroupId: string
        :type kwargs:
        :return:
        :rtype:
        """
        try:
            request = LeaveSecurityGroupRequest.LeaveSecurityGroupRequest()
            list_required_params = ["InstanceId", "SecurityGroupId"]
            request = set_required_params(request, list_required_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("disassociate_security_groups")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    # ********************************费用***********************************

    # @classmethod
    # def _set_realcost_params(cls, **kwargs):
    #     """
    #     设置真实费用参数
    #     :param kwargs:
    #     :return:
    #     """
    #     request = QueryInstanceBillRequest.QueryInstanceBillRequest()
    #     request.set_BillingCycle(kwargs["BillingCycle"])
    #     request.set_IsHideZeroCharge("true")
    #     if kwargs.get("ProductCode", None):
    #         request.set_ProductCode(kwargs["ProductCode"])
    #     if kwargs.get("ProductType", None):
    #         request.set_ProductType(kwargs["ProductType"])
    #     if kwargs.get("SubscriptionType", None):
    #         request.set_SubscriptionType(kwargs["SubscriptionType"])
    #     if kwargs.get("IsBillingItem", None):
    #         request.set_IsBillingItem(kwargs["IsBillingItem"])
    #     # if kwargs.get("IsHideZeroCharge", None):
    #     #     request.set_IsHideZeroCharge(kwargs["IsHideZeroCharge"])
    #     if kwargs.get("PageNum", None):
    #         request.set_PageNum(kwargs["PageNum"])
    #     if kwargs.get("PageSize", None):
    #         request.set_PageSize(kwargs["PageSize"])
    #     request.set_accept_format("json")
    #     return request
    #
    # def get_realcost(self, **kwargs):
    #     """
    #     获取真实费用参数
    #     :param kwargs:aliyun QueryInstanceBillRequest api param, see https://help.aliyun.com/
    #     :return:cost列表
    #     """
    #     try:
    #         kwargs["PageNum"] = "1"
    #         kwargs["PageSize"] = 50
    #         request = self._set_realcost_params(**kwargs)
    #         ali_response = self.client.do_action_with_exception(request)
    #         ali_result = json.loads(ali_response)
    #         data_list = []
    #         ins_list = []
    #         total_count = ali_result["Data"]["TotalCount"]
    #         data_list.extend(ali_result["Data"]["Items"]["Item"])
    #         page = total_count // 50 if total_count // 50 == 0 else total_count // 50 + 1
    #         for i in range(page):
    #             kwargs["PageNum"] = str(i + 2)
    #             request = self._set_realcost_params(**kwargs)
    #             ali_response = self.client.do_action_with_exception(request)
    #             ali_result = json.loads(ali_response)
    #             data_list.extend(ali_result["Data"]["Items"]["Item"])
    #         for item in data_list:
    #             if item["PretaxAmount"] > 0.0:
    #                 ins_list.append(
    #                     {
    #                         "resource_id": item.get("InstanceID"),
    #                         "resource_name": item.get("NickName"),
    #                         "resource_type": item.get("ProductType"),
    #                         "cost": item["PretaxAmount"],
    #                         "cost_time": kwargs["BillingCycle"],
    #                     }
    #                 )
    #         return {"result": True, "data": ins_list}
    #     except Exception as e:
    #         logger.exception("get_realcost")
    #         return {"result": False, "message": str(e)}

    # 阿里云接口更新，使用了新版的API接口代替
    # @classmethod
    def _set_realcost_params(self, **kwargs):
        """
        设置真实费用参数
        :param kwargs:
        :return:
        """
        request = CommonRequest()
        request.set_accept_format("json")
        request.set_domain("business.aliyuncs.com")
        request.set_method("POST")
        request.set_protocol_type("https")  # https | http
        request.set_version("2017-12-14")
        request.set_action_name("DescribeInstanceBill")
        params_dict = {
            "BillingCycle": kwargs["BillingCycle"],
            "IsHideZeroCharge": True,
        }
        if kwargs.get("ProductCode"):
            params_dict.update({"ProductCode": kwargs["ProductCode"]})
        if kwargs.get("ProductType"):
            params_dict.update({"ProductType": kwargs["ProductType"]})
        if kwargs.get("SubscriptionType"):
            params_dict.update({"SubscriptionType": kwargs["SubscriptionType"]})
        if kwargs.get("IsBillingItem"):
            params_dict.update({"IsBillingItem": kwargs["IsBillingItem"]})
        if kwargs.get("BillingDate"):
            params_dict.update({"BillingDate": kwargs["BillingDate"]})
            params_dict.update({"Granularity": "DAILY"})
            # request.set_BillingDate(kwargs["BillingDate"])
            # request.set_Granularity("DAILY")
        if kwargs.get("Granularity"):
            params_dict.update({"Granularity": kwargs["Granularity"]})
        # if kwargs.get("IsHideZeroCharge", None):
        #     request.set_IsHideZeroCharge(kwargs["IsHideZeroCharge"])
        if kwargs.get("NextToken"):
            params_dict.update({"NextToken": kwargs["NextToken"]})
        if kwargs.get("MaxResults"):
            params_dict.update({"MaxResults": kwargs["MaxResults"]})
        request = add_required_params(request, params_dict)
        response = self.client.do_action(request)
        res = json.loads(response)
        return res

        # request = DescribeInstanceBillRequest.DescribeInstanceBillRequest()
        # request.set_BillingCycle(kwargs["BillingCycle"])
        # request.set_IsHideZeroCharge(True)
        # if kwargs.get("ProductCode"):
        #     request.set_ProductCode(kwargs["ProductCode"])
        # if kwargs.get("ProductType"):
        #     request.set_ProductType(kwargs["ProductType"])
        # if kwargs.get("SubscriptionType"):
        #     request.set_SubscriptionType(kwargs["SubscriptionType"])
        # if kwargs.get("IsBillingItem"):
        #     request.set_IsBillingItem(kwargs["IsBillingItem"])
        # if kwargs.get("BillingDate"):
        #     request.set_BillingDate(kwargs["BillingDate"])
        #     request.set_Granularity("DAILY")
        # if kwargs.get("Granularity"):
        #     request.set_Granularity(kwargs["Granularity"])
        # # if kwargs.get("IsHideZeroCharge", None):
        # #     request.set_IsHideZeroCharge(kwargs["IsHideZeroCharge"])
        # if kwargs.get("NextToken"):
        #     request.set_NextToken(kwargs["NextToken"])
        # if kwargs.get("MaxResults"):
        #     request.set_MaxResults(kwargs["MaxResults"])
        # request.set_accept_format("json")
        # return request

    def get_realcost(self, **kwargs):
        """
        获取真实费用参数
        :param kwargs:aliyun QueryInstanceBillRequest api param, see https://help.aliyun.com/
        :return:cost列表
        """
        try:
            # kwargs["PageNum"] = "1"
            kwargs["MaxResults"] = 200  # 值默认200，最大取值300
            ali_result = self._set_realcost_params(**kwargs)
            # ali_response = self.client.do_action_with_exception(request)
            # ali_result = json.loads(ali_response)
            data_list = []
            ins_list = []
            # total_count = ali_result["Data"]["TotalCount"]
            data_list.extend(ali_result["Data"]["Items"])
            while ali_result["Data"].get("NextToken"):
                kwargs["NextToken"] = ali_result["Data"]["NextToken"]
                ali_result = self._set_realcost_params(**kwargs)
                # ali_response = self.client.do_action_with_exception(request)
                # ali_result = json.loads(ali_response)
                data_list.extend(ali_result["Data"]["Items"])
            # page = total_count // 50 if total_count // 50 == 0 else total_count // 50 + 1
            # for i in range(page):
            #     kwargs["PageNum"] = str(i + 2)
            #     request = self._set_realcost_params(**kwargs)
            #     ali_response = self.client.do_action_with_exception(request)
            #     ali_result = json.loads(ali_response)
            #     data_list.extend(ali_result["Data"]["Items"]["Item"])
            for item in data_list:
                # if item["PretaxAmount"] > 0.0:
                ins_list.append(
                    {
                        "serial_number": generate_serial_number(item["PretaxAmount"]),
                        "resource_id": item.get("InstanceID"),
                        "resource_name": item.get("NickName"),
                        "resource_type": format_public_cloud_resource_type("Aliyun", item.get("ProductName")) or "",
                        "mode": format_ali_bill_charge_mode(item.get("Item")),
                        # "product_name": item.get("ProductName"),
                        "product_detail": item["ProductDetail"],
                        "original_price": item.get("PretaxGrossAmount"),
                        "discount": item.get("InvoiceDiscount"),
                        "current_price": item["PretaxAmount"],
                        # "result_time_month": kwargs["BillingCycle"],
                        "result_time": item.get("BillingDate"),
                    }
                )
            return {"result": True, "data": ins_list}
        except Exception as e:
            logger.exception("get_realcost")
            return {"result": False, "message": str(e)}

    # def get_virtual_cost(self, **kwargs):
    #     """
    #     获取虚拟费用
    #     :param kwargs:
    #     :return:
    #     """
    #     try:
    #         zone_list = self.list_zones()["data"]
    #         kwargs["PageNumber"] = "1"
    #         kwargs["PageSize"] = 50
    #         return_data = []
    #         for z in zone_list:
    #             kwargs["ZoneId"] = z["resource_id"]
    #             request = self._set_vm_info_params(**kwargs)
    #             ali_response = self.client.do_action_with_exception(request)
    #             ali_result = json.loads(ali_response)
    #             ins_list = []
    #             total_count = ali_result["TotalCount"]
    #             ins_list.extend(ali_result["Instances"]["Instance"])
    #             page = total_count // 50 if total_count // 50 == 0 else total_count // 50 + 1
    #             for i in range(page):
    #                 kwargs["PageNumber"] = str(i + 2)
    #                 request = self._set_vm_info_params(**kwargs)
    #                 ali_response = self.client.do_action_with_exception(request)
    #                 ali_result = json.loads(ali_response)
    #                 ins_list.extend(ali_result["Instances"]["Instance"])
    #             _, spec_list = get_compute_price_module(
    #                 CloudPlatform.Aliyun, kwargs["account_name"], self.RegionId, z["resource_id"]
    #             )
    #             spec_set_list = [s[4] for s in spec_list]
    #             spec_price_list = [s[3] for s in spec_list]
    #             for i in ins_list:
    #                 try:
    #                     ins_spec = i["InstanceType"]
    #                     if ins_spec in spec_set_list:
    #                         price_vm = spec_price_list[spec_set_list.index(ins_spec)]
    #                     else:
    #                         price_vm = 0
    #                     devices_list = self._get_source_devices(**{"InstanceId": i["InstanceId"]})["data"]
    #                     price_disk = 0
    #                     for d in devices_list:
    #                         module, storage_list = get_storage_pricemodule(
    #                             CloudPlatform.Aliyun,
    #                             kwargs["account_name"],
    #                             self.RegionId, z["resource_id"], d["category"]
    #                         )
    #                         if module:
    #                             price_disk += storage_list[1] * d["disk_size"]
    #                         else:
    #                             price_disk += 0
    #                     return_data.append(
    #                         {
    #                             "resourceId": i["InstanceId"],
    #                             "name": i["HostName"],
    #                             "cpu": i["Cpu"],
    #                             "mem": round(i["Memory"] / 1024, 2),
    #                             "cost_all": round(float(price_vm), 2) + round(float(price_disk), 2),
    #                             "cost_vm": round(float(price_vm), 2),
    #                             "cost_disk": round(float(price_disk), 2),
    #                             "cost_net": 0.0,
    #                             "cost_time": datetime.datetime.now().strftime("%Y-%m-%d"),
    #                             "source_type": CloudResourceType.VM.value,
    #                         }
    #                     )
    #                 except Exception as e:
    #                     logger.exception(e)
    #                     logger.error("get {} price error".format(i["InstanceId"]))
    #                     continue
    #         return {"result": True, "data": return_data}
    #     except Exception as e:
    #         logger.exception("get_virtual_cost error")
    #         return {"result": False, "message": str(e)}

    def query_account_balance(self):
        """
        查询账户可用余额
        """
        request = QueryAccountBalanceRequest.QueryAccountBalanceRequest()
        format_func = get_format_method(self.cloud_type, "balance")
        ali_result = self._get_result(request, True)
        result = format_func(ali_result)
        return {"result": True, "data": result}

    # def query_account_transactions(self):
    #     """
    #     查询消费详情
    #     """
    #     try:
    #         from home_application.helpers.helpers import get_year_all_month
    #
    #         month_list = get_year_all_month()
    #         res_data = []
    #         for i in month_list:
    #             request = QueryBillRequest.QueryBillRequest()
    #             request.set_BillingCycle(i)
    #             request.set_IsHideZeroCharge(True)
    #             request.set_accept_format("json")
    #             ali_response = json.loads(self.client.do_action_with_exception(request))
    #             total_count = ali_response["Data"]["TotalCount"]
    #             request.set_PageSize(300)
    #             request.set_PageNum(1)
    #             res_data.extend(ali_response["Data"]["Items"]["Item"])
    #             pages = total_count // 300 if total_count % 300 == 0 else total_count // 300 + 1
    #             for i in range(pages):
    #                 request.set_PageNum(i + 2)
    #                 ali_response = json.loads(self.client.do_action_with_exception(request))
    #                 res_data.extend(ali_response["Data"]["Items"]["Item"])
    #         return {"result": True, "data": res_data}
    #     except Exception as e:
    #         logger.exception("query_account_transactions")
    #         return {"result": False, "message": str(e)}

    # ******************************************* 规格相关接口
    def get_vm_spec(self, cpu, memory):
        """
        查询云服务器ECS提供的所有实例规格的信息 可根据实例规格名  实例规格族名查询
        Args:
            memory (int): 内存
            cpu (int): cpu
        Returns:

        """
        request = DescribeInstanceTypesRequest.DescribeInstanceTypesRequest()
        res = self._get_result(request, True)
        res = [
            {"label": i["InstanceTypeId"], "value": i["InstanceTypeId"], "memory": memory, "cpu": cpu}
            for i in res["InstanceTypes"]["InstanceType"]
            if int(i["MemorySize"]) == memory and i["CpuCoreCount"] == cpu
        ]
        return {"result": True, "data": res}

    def get_available_instance_spec(self, zone, memory="", cpu=""):
        """
        获取计算资源规格。这里是 ecs。 可以用于获取计算资源和磁盘格式
        查询某一可用区的资源列表。 Zone InstanceType SystemDisk DataDisk Network ddh
        取值顺序：Zone > IoOptimized > InstanceType = Network = ddh > SystemDisk > DataDisk
        取值示例：
        若参数DestinationResource取值为DataDisk，则需要传入InstanceType参数或者指定ResourceType参数值为disk。
        若参数DestinationResource取值为SystemDisk，则必须要传入参数InstanceType。
        若参数DestinationResource取值为InstanceType，则必须传入参数IoOptimized和InstanceType。
        查询指定地域下所有可用区的ecs.g5.large库存供应情况：
            RegionId=cn-hangzhou &DestinationResource=InstanceType &IoOptimized=optimized &InstanceType=ecs.g5.large。
        查询指定地域下有ecs.g5.large库存供应的可用区列表：
            RegionId=cn-hangzhou &DestinationResource=Zone &IoOptimized=optimized &InstanceType=ecs.g5.large。
        Parameters
        ----------
        查询Zone：
        zone (str): 可用区id
        memory (int): 内存 GB
        cpu (int): cpu核数

        Returns
        -------

        """
        request = DescribeAvailableResourceRequest.DescribeAvailableResourceRequest()
        params = {"ZoneId": zone, "DestinationResource": "InstanceType", "Memory": memory, "Cores": cpu}
        request = set_required_params(request, ["ZoneId", "DestinationResource", "Memory", "Cores"], params)
        res = self._get_result(request, True)
        spec_list = [
            i["Value"]
            for i in res["AvailableZones"]["AvailableZone"][0]["AvailableResources"]["AvailableResource"][0][
                "SupportedResources"
            ]["SupportedResource"]
        ]
        return {"result": True, "data": [{"label": i, "value": i, "memory": memory, "cpu": cpu} for i in spec_list]}

    def get_disk_spec(self, zone, instance_type=""):
        """
        获取磁盘格式 获取数据盘或者系统盘。参数参照上面get_insatnce_spec
        ---------------------------
        zone (str): 所属可用区资源id
        insatnce_type (str): ecs的规格，查询可用系统盘格式时必传    (optional)
        ---------------------------
        Returns
        -------

        """
        request = DescribeAvailableResourceRequest.DescribeAvailableResourceRequest()
        param_list = ["ZoneId", "DestinationResource"]
        params = {"ZoneId": zone}
        if instance_type:
            param_list.append("InstanceType")
            params.update({"InstanceType": instance_type, "DestinationResource": "SystemDisk"})
        else:
            param_list.append("ResourceType")
            params.update({"ResourceType": "disk", "DestinationResource": "DataDisk"})
        request = set_required_params(request, param_list, params)
        res = self._get_result(request, True)
        try:
            disk_catagory = [
                i["Value"]
                for i in res["AvailableZones"]["AvailableZone"][0]["AvailableResources"]["AvailableResource"][0][
                    "SupportedResources"
                ]["SupportedResource"]
            ]
        except Exception as e:
            logger.exception("获取Aliyun磁盘格式失败:{}".format(e))
            return {"result": False, "message": "获取Aliyun磁盘格式失败"}
        return {"result": True, "data": [{"value": i, "label": disk_category_dict[i]} for i in disk_catagory]}

    def get_object_storage_spec(self):
        """
        获取对象存储类型
        Returns
        -------

        """
        return [{"value": k, "label": v} for k, v in object_storage_type_dict.items()]

    def get_mysql_spec(self, instance_charge_type="Postpaid", zone="", engine_version="5.7"):
        """
        获取指定地域的 RDS 规格信息
        Parameters
        ----------
        instance_charge_type (str): Postpaid | Prepaid  默认为Postpaid即按量付费
        zone (str): 可用区
        engine_version (str): mysql版本。 5.5 | 5.6 | 5.7 | 8.0

        Returns
        -------

        """
        request = CommonRequest()
        request.set_accept_format("json")
        request.set_domain("rds.aliyuncs.com")
        request.set_method("POST")
        request.set_protocol_type("https")  # https | http
        request.set_version("2014-08-15")
        request.set_action_name("DescribeAvailableResource")
        params_dict = {
            "InstanceChargeType": instance_charge_type,
            "RegionId": self.RegionId,
            "Engine": "MySQL",
            "EngineVersion": engine_version,
        }
        if zone:
            params_dict.update({"ZoneId": zone})
        request = add_required_params(request, params_dict)
        response = self.client.do_action(request)
        res = json.loads(response)
        # 阿里云返回的数据嵌套结构很深
        data = [
            {"label": spec["DBInstanceClass"], "value": spec["DBInstanceClass"]}
            for available_zone in res["AvailableZones"]["AvailableZone"]
            for resource in available_zone["SupportedEngines"]["SupportedEngine"]
            for catagory in resource["SupportedEngineVersions"]["SupportedEngineVersion"]
            for storage in catagory["SupportedCategorys"]["SupportedCategory"]
            for available_resource in storage["SupportedStorageTypes"]["SupportedStorageType"]
            for spec in available_resource["AvailableResources"]["AvailableResource"]
        ]
        return {"result": True, "data": data}

    def get_redis_spec(self, zone="", charge_type="PrePaid"):
        """
        获取redis规格
        Parameters
        ----------
        zone (str): 可用区资源id
        charge_type (str): 付费类型  PrePaid（包年包月） | PostPaid（按量计费）

        Returns
        -------

        """
        params_list = ["InstanceChargeType", "Engine"]
        params_dict = {"InstanceChargeType": charge_type, "Engine": "Redis"}
        if zone:
            params_list.append("ZoneId")
            params_dict.update({"ZoneId": zone})
        request = kvs_avail_resource()
        request = set_required_params(request, params_list, params_dict)
        res = self._get_result(request, True)
        data = [
            {
                "label": resource["InstanceClass"],
                "value": resource["InstanceClass"],
                "remark": resource["InstanceClassRemark"],
            }
            for available_zone in res["AvailableZones"]["AvailableZone"]
            for engine in available_zone["SupportedEngines"]["SupportedEngine"]
            for catagory in engine["SupportedEditionTypes"]["SupportedEditionType"]
            for series in catagory["SupportedSeriesTypes"]["SupportedSeriesType"]
            for engine_version in series["SupportedEngineVersions"]["SupportedEngineVersion"]
            for architecture in engine_version["SupportedArchitectureTypes"]["SupportedArchitectureType"]
            for shard in architecture["SupportedShardNumbers"]["SupportedShardNumber"]
            for node in shard["SupportedNodeTypes"]["SupportedNodeType"]
            for resource in node["AvailableResources"]["AvailableResource"]
        ]
        return {"result": True, "data": data}

    def get_mongodb_spec(self, zone="", charge_type="PrePaid"):
        """
        获取mongodb规格
        Parameters
        ----------
        zone (str)
        charge_type (str): 付费类型  PrePaid | PostPaid

        Returns
        -------

        """
        params_list = ["InstanceChargeType"]
        params_dict = {"InstanceChargeType": charge_type}
        if zone:
            params_list.append("ZoneId")
            params_dict.update({"ZoneId": zone})
        request = dds_avail_resource()
        request = set_required_params(request, params_list, params_dict)
        res = self._get_result(request, True)
        data = [
            {
                "label": resource["InstanceClass"],
                "value": resource["InstanceClass"],
                "remark": resource["InstanceClassRemark"],
                "dn_type": db_types["DbType"],
            }
            for db_types in res["SupportedDBTypes"]["SupportedDBType"]
            for avail_zone in db_types["AvailableZones"]["AvailableZone"]
            for engine_version in avail_zone["SupportedEngineVersions"]["SupportedEngineVersion"]
            for engine in engine_version["SupportedEngines"]["SupportedEngine"]
            for node_type in engine["SupportedNodeTypes"]["SupportedNodeType"]
            for resource in node_type["AvailableResources"]["AvailableResource"]
        ]
        return {"result": True, "data": data}


# ************************Common***********************************************


def set_optional_params(request, list_param, kwargs):
    """
    设置request的非必选请求参数
    :param request: 云接口对应请求实例
    :param list_param: 需设置的请求参数
    :param kwargs: 传入参数
    :return:
    """
    for _, v in enumerate(list_param):
        if v in kwargs:
            if isinstance(kwargs[v], int):
                getattr(request, "set_" + v)(int(kwargs[v]))
            elif isinstance(kwargs[v], int):
                getattr(request, "set_" + v)(int(kwargs[v]))
            else:
                getattr(request, "set_" + v)(kwargs[v])
    return request


def set_required_params(request, list_param, kwargs):
    """
    设置request的必选请求参数
    :param request: 云接口对应请求实例
    :param list_param: 需设置的请求参数
    :param kwargs: 传入参数
    :return:
    """
    for _, v in enumerate(list_param):
        if isinstance(kwargs[v], int):
            getattr(request, "set_" + v)(int(kwargs[v]))
        elif isinstance(kwargs[v], int):
            getattr(request, "set_" + v)(int(kwargs[v]))
        else:
            getattr(request, "set_" + v)(kwargs[v])
    return request


def add_required_params(request, params_dict):
    """
    通过add_query_param付费设置参数
    :param request:
    :param params_dict:  (dict): k是参数名，v是参数值
    :return:
    """
    for k, v in params_dict.items():
        request.add_query_param(k, v)
    return request


def checkout_required_parameters(required_list, kwargs):
    """
    检验必选的参数
    :param required_list: 必选的参数list
    :param kwargs: 参数集
    :return:
    """
    for item in required_list:
        if item not in kwargs:
            raise TypeError("need param {}".format(item))

# -- coding: utf-8 --
# @File: aliyun_info.py
# @Time: 2025/3/10 15:06
# @Author: windyzhao
import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import oss2
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
from aliyunsdkcore import client
from aliyunsdkcore.request import CommonRequest
from aliyunsdkecs.request.v20140526 import (
    ApplyAutoSnapshotPolicyRequest,
    CancelAutoSnapshotPolicyRequest,
    CreateDiskRequest,
    CreateImageRequest,
    DeleteImageRequest,
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
    ListTagResourcesRequest,
    ModifyInstanceAttributeRequest,
    ResetDiskRequest,
    TagResourcesRequest,
    UntagResourcesRequest,
)
from aliyunsdknas.request.v20170626 import DescribeFileSystemsRequest
from aliyunsdkslb.request.v20140515 import DescribeServerCertificatesRequest
from aliyunsdkvpc.request.v20160428 import (
    CreateVSwitchRequest,
    DeleteVSwitchRequest,
    DescribeRouteEntryListRequest,
    DescribeRouteTableListRequest,
    DescribeVpcsRequest,
    DescribeVSwitchesRequest,
)
from six.moves import range
from Tea.core import TeaCore

from common.cmp.cloud_apis.constant import CloudType
from common.cmp.cloud_apis.resource_apis.cw_aliyun import RESOURCE_MAP
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.utils import set_dir_size
from plugins.base_utils import utc_to_dts, ts_to_dts


def convert_param_to_list(param):
    """
    将传入的未定格式的参数转换成列表
    Args:
        param (all): 未确定类型参数

    Returns:

    """
    if not param and param != 0:
        return []
    if not isinstance(param, (str, list, int)):
        raise Exception("传入参数不为空时，类型仅支持str和list。请修改！")
    return param if isinstance(param, list) else [param]


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


class CwAliyun(object):
    """
    阿里云组件类,通过该类创建阿里云的Client实例，调用阿里云api接口
    """

    def __init__(self, params, **kwargs):
        """
        初始化方法，创建Client实例。在创建Client实例时，您需要获取Region ID、AccessKey ID和AccessKey Secret
        :param access_key:
        :param access_secret:
        :param region_id:
        :param kwargs:
        """
        self.AccessKey = params["access_key"]
        self.AccessSecret = params["access_secret"]
        self.RegionId = params.get("region_id", "cn-hangzhou")
        for k, v in kwargs.items():
            setattr(self, k, v)

        # 猴子补丁：为CredentialModel类添加缺失的provider_name属性
        from alibabacloud_credentials.models import CredentialModel
        if not hasattr(CredentialModel, "provider_name"):
            setattr(CredentialModel, "provider_name", None)

        # 如果get_credential方法也缺失，也添加这个方法
        if not hasattr(CredentialModel, "get_credential"):
            setattr(CredentialModel, "get_credential", lambda self: self)

        # 创建ACS客户端
        self.client = client.AcsClient(
            self.AccessKey, self.AccessSecret, self.RegionId, timeout=30, connect_timeout=30, max_retry_time=3
        )

        # 创建OSS认证对象
        self.auth = oss2.Auth(self.AccessKey, self.AccessSecret)

        # 创建配置 - 不使用credential对象，直接设置access_key_id和access_key_secret
        self.auth_config = open_api_models.Config(
            access_key_id=self.AccessKey,
            access_key_secret=self.AccessSecret
        )
        self.auth_config.region_id = self.RegionId

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
            print("获取阿里云{}调用接口失败{}".format(resource, e))
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
            print("获取阿里云资源{}调用接口失败{}".format(resource, e))
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
            print("获取阿里云资源{}调用接口失败{}".format(resource, e))
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
            print("get_storage_list error")
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
            print("get_spec_price error")
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
            print("remote_vm(instance_id):" + kwargs["vm_id"])
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
            print("get_available_flavor")
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
            print("list_domains error")
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
            print("get_domain_parsing error")
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
                print("get_domain_parsing error")
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
            print("list_cdn error")
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
            print("list_waf error")
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
            print("list_cas error")
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
            import traceback
            print("list_buckets error. error={}".format(traceback.format_exc()))
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
            import traceback
            print("list_rds error. error={}".format(traceback.format_exc()))
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
            import traceback
            print("list_redis error. error={}".format(traceback.format_exc()))
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
            import traceback
            print("list_mongodb error. error={}".format(traceback.format_exc()))
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
            print("list_kafka error. error={}".format(e))
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
            print("list_kafka_consumer_group error")
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
            print("get_kafka_topic_subscribe_status error")
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
            print("list_kafka_topic error")
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
            import traceback
            print("list_slb error. error={}".format(traceback.format_exc()))
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
            print("list_k8s_clusters error")
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
            print("list_eips error")
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
            print("list_mse_clusters error")
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
            print("list_mse_namespace error")
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
            print("list_mse_service error")
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
            print("list_mse_inst error")
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
            print("list_alb error")
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
            print("list_nas error")
            return {"result": False, "message": repr(e)}

    def list_all_resources(self, **kwargs):

        def handle_resource(resource_func, resource_name):
            try:
                result = resource_func()
                if result.get("result"):
                    return {resource_name: result.get("data", [])}
                else:
                    # 返回错误信息
                    error_msg = result.get("message", "unknown error")
                    return {resource_name: {"cmdb_collect_error": error_msg}}
            except Exception as e:
                import traceback
                return {resource_name: {"cmdb_collect_error": str(e) + "\n" + traceback.format_exc()}}

        try:
            kafka_result = self.list_kafka()
            # mse_clusters_result = self.list_mse_clusters()
            # mse_namespaces_result = self.list_mse_namespaces(mse_clusters=mse_clusters_result)
            # mse_service_result = self.list_mse_service(mse_namespaces=mse_namespaces_result)

            resources = [
                # (self.list_domains, "aliyun_domain"),
                # (self.list_parsings, "aliyun_parsing"),
                # (self.list_cdn, "aliyun_cdn"),
                # (self.list_waf, "aliyun_firewall"),
                # (self.list_cas, "aliyun_ssl"),
                (self.list_vms, "aliyun_ecs"),
                (self.list_buckets, "aliyun_bucket"),
                (lambda: self.list_rds(engine="Mysql"), "aliyun_mysql"),
                (lambda: self.list_rds(engine="PostgreSQL"), "aliyun_pgsql"),
                (self.list_redis, "aliyun_redis"),
                (self.list_mongodb, "aliyun_mongodb"),
                (lambda: kafka_result, "aliyun_kafka_inst"),
                (self.list_clb, "aliyun_clb"),

                # (lambda: self.list_kafka_consumer_group(kafka_instances=kafka_result), "aliyun_kafka_group"),
                # (lambda: self.list_kafka_topic(kafka_instances=kafka_result), "aliyun_kafka_topic"),
                # (self.list_k8s_clusters, "aliyun_k8s_cluster"),
                # (self.list_eips, "aliyun_eip"),
                # (lambda: mse_clusters_result, "aliyun_mse_cluster"),
                # (lambda: mse_service_result, "aliyun_mse_service"),
                # (lambda: self.list_mse_inst(mse_services=mse_service_result), "aliyun_mse_inst"),
                # (self.list_albs, "aliyun_alb"),
                # (self.list_nas, "aliyun_nas"),
            ]

            data = {}
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_resource = {
                    executor.submit(handle_resource, resource_func, resource_name): resource_name
                    for resource_func, resource_name in resources
                }
                for future in as_completed(future_to_resource):
                    result = future.result()
                    if result:
                        data.update(result)

            format_data = self.format_aliyun_data(data)
            result_data = {"result": format_data, "success": True}
        except Exception as err:
            import traceback
            from sanic.log import logger
            logger.error("aliyun_list_all_resources_error: {}".format(traceback.format_exc()))
            result_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return result_data

    # ===============
    @staticmethod
    def format_ecs_data(data_list):
        result = []
        for data in data_list:
            result.append(
                {
                    "resource_name": data["resource_name"],
                    "resource_id": data["resource_id"],
                    "ip_addr": data["inner_ip"][0] if data["inner_ip"] else "",
                    "public_ip": data["public_ip"][0] if data["public_ip"] else (
                        data["inner_ip"][0] if data["inner_ip"] else ""),
                    "region": data["region"],
                    "zone": data["zone"],
                    "vpc": data["vpc"],
                    "status": data["status"],
                    "instance_type": data["instance_type"],
                    "os_name": data["os_name"],
                    "vcpus": data["vcpus"],
                    "memory": data["memory"],
                    "charge_type": data["charge_type"],
                    "create_time": data["create_time"],
                    "expired_time": data["expired_time"],
                }
            )

        return result

    @staticmethod
    def format_bucket_data(data_list):
        result = []
        for data in data_list:
            result.append(
                {
                    "resource_name": data["Name"],
                    "resource_id": data["Name"],
                    "location": data["Location"],
                    "extranet_endpoint": f"{data['Name']}.{data['ExtranetEndpoint']}",
                    "intranet_endpoint": f"{data['Name']}.{data['IntranetEndpoint']}",
                    "storage_class": data["StorageClass"],
                    "cross_region_replication": data["CrossRegionReplication"],
                    "block_public_access": data["BlockPublicAccess"],
                    "creation_date": utc_to_dts(data["CreationDate"], utc_fmt='%Y-%m-%dT%H:%M:%S.%fZ'),
                }
            )

        return result

    @staticmethod
    def format_aliyun_mysql(data_list):
        result = []
        for data in data_list:
            zone_slave = ",".join([data[i] for i in data if i.startswith("ZoneIdSlave")])
            result.append({
                "resource_name": data.get("DBInstanceDescription"),
                "resource_id": data.get("DBInstanceId"),
                "region": data.get("RegionId"),
                "zone": data.get("ZoneId"),
                "zone_slave": zone_slave,
                "engine": data.get("Engine"),
                "version": data.get("EngineVersion"),
                "type": data.get("DBInstanceType"),
                "status": data.get("DBInstanceStatus"),
                "class": data.get("DBInstanceClass"),
                "storage_type": data.get("DBInstanceStorageType"),
                "network_type": data.get("InstanceNetworkType"),
                "connection_mode": data.get("ConnectionMode"),
                "lock_mode": data.get("LockMode"),
                "cpu": data.get("DBInstanceCPU"),
                "memory_mb": data.get("DBInstanceMemory"),
                "charge_type": data.get("ChargeType"),
                "create_time": utc_to_dts(data.get("CreateTime")),
                "expire_time": utc_to_dts(data.get("ExpireTime")),
            })
        return result

    @staticmethod
    def format_aliyun_pgsql(data_list):
        result = []
        for data in data_list:
            zone_slave = ",".join([data[i] for i in data if i.startswith("ZoneIdSlave")])
            result.append({
                "resource_name": data.get("DBInstanceDescription"),
                "resource_id": data.get("DBInstanceId"),
                "region": data.get("RegionId"),
                "zone": data.get("ZoneId"),
                "zone_slave": zone_slave,
                "engine": data.get("Engine"),
                "version": data.get("EngineVersion"),
                "type": data.get("DBInstanceType"),
                "status": data.get("DBInstanceStatus"),
                "class": data.get("DBInstanceClass"),
                "storage_type": data.get("DBInstanceStorageType"),
                "network_type": data.get("InstanceNetworkType"),
                "net_type": data.get("DBInstanceNetType"),
                "connection_mode": data.get("ConnectionMode"),
                "lock_mode": data.get("LockMode"),
                "cpu": data.get("DBInstanceCPU", ""),
                "memory_mb": data.get("DBInstanceMemory"),
                "charge_type": data.get("ChargeType", ""),
                "create_time": utc_to_dts(data.get("CreateTime")),
                "expire_time": utc_to_dts(data.get("ExpireTime")),
            })
        return result

    @staticmethod
    def format_aliyun_redis(data_list):
        result = []
        for data in data_list:
            result.append({
                "resource_name": data.get("InstanceName"),
                "resource_id": data.get("InstanceId"),
                "region": data["RegionId"],
                "zone": data["ZoneId"],
                "engine_version": data["EngineVersion"],
                "architecture_type": data["ArchitectureType"],
                "capacity": data["Capacity"],
                "network_type": data["NetworkType"],
                "connection_domain": data["ConnectionDomain"],
                "port": data["Port"],
                "bandwidth": data["Bandwidth"],
                "shard_count": data.get("ShardCount", ""),
                "qps": data["QPS"],
                "instance_class": data["InstanceClass"],
                "package_type": data["PackageType"],
                "charge_type": data["ChargeType"],
                "create_time": utc_to_dts(data.get("CreateTime")),
                "end_time": utc_to_dts(data.get("EndTime")),
            })
        return result

    @staticmethod
    def format_aliyun_mongodb(data_list):
        result = []
        for data in data_list:
            zone_slave = ",".join([data.get("SecondaryZoneId", "") or data.get("HiddenZoneId", "")])
            result.append({
                "resource_name": data.get("DBInstanceDescription"),
                "resource_id": data.get("DBInstanceId"),
                "region": data.get("RegionId"),
                "zone": data.get("ZoneId"),
                "zone_slave": zone_slave,
                "engine": data.get("Engine"),
                "version": data.get("EngineVersion"),
                "type": data.get("DBInstanceType"),
                "status": data.get("DBInstanceStatus"),
                "class": data.get("DBInstanceClass"),
                "storage_type": data.get("StorageType"),
                "storage_gb": data.get("DBInstanceStorage", ""),
                "lock_mode": data.get("LockMode", ""),
                "charge_type": data.get("ChargeType", ""),
                "create_time": utc_to_dts(data.get("CreateTime"), utc_fmt='%Y-%m-%dT%H:%MZ'),
                "expire_time": utc_to_dts(data.get("ExpireTime"), utc_fmt='%Y-%m-%dT%H:%MZ'),
            })
        return result

    @staticmethod
    def format_aliyun_kafka_inst(data_list):
        result = []
        for data in data_list:
            result.append({
                "resource_name": data.get("LoadBalancerName"),
                "resource_id": data.get("LoadBalancerId"),
                "region": data.get("RegionId"),
                "zone": data.get("ZoneId"),
                "vpc": data.get("VpcId"),
                "status": data.get("LoadBalancerStatus"),
                "class": data.get("LoadBalancerSpec"),
                "storage_gb": data.get("DiskSize", ""),
                "storage_type": data.get("DiskType", ""),
                "msg_retain": data.get("MsgRetain"),
                "topoc_num": data.get("TopicNumLimit", ""),
                "io_max_read": data.get("IoMaxRead", ""),
                "io_max_write": data.get("IoMaxWrite", ""),
                "charge_type": data.get("PaidType", ""),
                "create_time": ts_to_dts(data.get("CreateTime")),
            })
        return result

    @staticmethod
    def format_aliyun_clb(data_list):
        result = []
        for data in data_list:
            result.append({
                "resource_name": data.get("LoadBalancerName"),
                "resource_id": data.get("LoadBalancerId"),
                "region": data.get("RegionId"),
                "zone": data.get("MasterZoneId"),
                "zone_slave": data.get("SlaveZoneId"),
                "vpc": data.get("VpcId"),
                "ip_addr": data.get("Address"),
                "status": data.get("LoadBalancerStatus"),
                "class": data.get("LoadBalancerSpec"),
                "charge_type": data.get("PayType", ""),
                "create_time": utc_to_dts(data["CreateTime"], utc_fmt='%Y-%m-%dT%H:%MZ'),
            })
        return result

    @property
    def format_funcs(self):
        funcs = {
            "aliyun_ecs": self.format_ecs_data,
            "aliyun_bucket": self.format_bucket_data,
            "aliyun_mysql": self.format_aliyun_mysql,
            "aliyun_pgsql": self.format_aliyun_pgsql,
            "aliyun_mongodb": self.format_aliyun_mongodb,
            "aliyun_redis": self.format_aliyun_redis,
            "aliyun_clb": self.format_aliyun_clb,
            "aliyun_kafka_inst": self.format_aliyun_kafka_inst,
        }
        return funcs

    def format_aliyun_data(self, data_dict):
        result = {}
        for model_id, model_data in data_dict.items():
            # 检查是否是错误信息
            if isinstance(model_data, dict) and "cmdb_collect_error" in model_data:
                result[model_id] = [model_data]  # 保持格式一致，放在列表中
            else:
                func = self.format_funcs.get(model_id)
                if func:
                    result[model_id] = func(model_data)
                else:
                    # 如果没有对应的格式化函数，直接使用原数据
                    result[model_id] = model_data if isinstance(model_data, list) else [model_data]

        return result

    # =============================oss=========================

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
            print("get_bucket_stat error")
            return {}
        except Exception:
            print("get_bucket_stat error")
            return {}

    def get_bucket_stat_metric_value(self, metric_stat_key, **kwargs):
        bucket_stat = kwargs.get("bucket_stat", {})
        if not bucket_stat:
            return
        if metric_stat_key:
            value = bucket_stat.get(metric_stat_key)
            return value

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
            print("_get_vm_list")
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
            print("vm_add_security_group")
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
            print("tag_resources：" + kwargs["ResourceType"] + ":" + kwargs["ResourceIds"])
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
            print("list_tag_resource")
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
            print("untie_tag_resources")
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
            print("reset_disk: {}".format(disk_id))
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
            print("apply auto snapshot policy failed")
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
            print("list_load_balancer failed")
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
            print("list_load_balancer failed")
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
            print("list_server_certificates failed")
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
            print("list_vserver_groups failed")
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
            print("add_vserver_group_backend_servers failed")
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
            print("delete vserver group backend servers failed")
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
            print("modify_vserver_group_backend_servers failed")
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
            print("create load balancer tcp listen failed")
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
            print("start_listener failed")
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
            print("create_images")
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
            print("delete image_id failed(ImageId):" + ",".join(kwargs["image_id"]))
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
            print("list_object fail")
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
            print("list_object fail")
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
            print("create subnet failed")
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
            print("delete subnets: {}".format(subnet_id))
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
            print("describe_route_entry_list")
            return {"result": False, "data": [], "message": str(e)}

    #  ------------------弹性公网ip--------------------------------

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
            print("获取阿里云{}调用接口失败{}".format("security_group_rule", e))
            return {"result": False, "message": str(e)}

        copy_ali_result = copy.deepcopy(ali_result)
        copy_ali_result.pop("Permissions")

        data = self._format_resource_result("security_group_rule", ali_result, **copy_ali_result)
        return {"result": True, "data": data}

        # return self._handle_list_request("security_group_rule", request)

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

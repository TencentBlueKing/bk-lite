# -*- coding: utf-8 -*-
import datetime
import json
import time

from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_comm import format_region

from common.cmp.cloud_apis.base import PublicCloudManage
from common.cmp.cloud_apis.constant import CloudResourceType, CloudType
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.cloud_apis.resource_apis.resource_format.tce.tce_constant import (
    REDISTYPENAME,
    RedisType,
    tce_bucket_cn_dict,
    tce_disk_cn_dict,
)
from common.cmp.cloud_apis.resource_apis.tcecloud.bms.v20180813 import bms_client
from common.cmp.cloud_apis.resource_apis.tcecloud.bms.v20180813 import models as bms_models
from common.cmp.cloud_apis.resource_apis.tcecloud.cbs.v20170312 import cbs_client
from common.cmp.cloud_apis.resource_apis.tcecloud.cbs.v20170312 import models as cbs_models
from common.cmp.cloud_apis.resource_apis.tcecloud.cfs.v20190719 import cfs_client
from common.cmp.cloud_apis.resource_apis.tcecloud.cfs.v20190719 import models as cfs_models
from common.cmp.cloud_apis.resource_apis.tcecloud.ckafka.v20190819 import ckafka_client
from common.cmp.cloud_apis.resource_apis.tcecloud.ckafka.v20190819 import models as ckafka_models
from common.cmp.cloud_apis.resource_apis.tcecloud.clb.v20180317 import clb_client
from common.cmp.cloud_apis.resource_apis.tcecloud.clb.v20180317 import models as clb_models
from common.cmp.cloud_apis.resource_apis.tcecloud.common import credential
from common.cmp.cloud_apis.resource_apis.tcecloud.common.exception.tce_cloud_sdk_exception import TceCloudSDKException
from common.cmp.cloud_apis.resource_apis.tcecloud.common.profile.client_profile import ClientProfile
from common.cmp.cloud_apis.resource_apis.tcecloud.common.profile.http_profile import HttpProfile
from common.cmp.cloud_apis.resource_apis.tcecloud.csp.v20200107 import csp_client
from common.cmp.cloud_apis.resource_apis.tcecloud.csp.v20200107 import models as csp_models
from common.cmp.cloud_apis.resource_apis.tcecloud.cvm.v20170312 import models as cvm_models, cvm_client
from common.cmp.cloud_apis.resource_apis.tcecloud.dcdb.v20180411 import dcdb_client
from common.cmp.cloud_apis.resource_apis.tcecloud.dcdb.v20180411 import models as dcdb_models
from common.cmp.cloud_apis.resource_apis.tcecloud.mariadb.v20170312 import mariadb_client
from common.cmp.cloud_apis.resource_apis.tcecloud.mariadb.v20170312 import models as mariadb_models
from common.cmp.cloud_apis.resource_apis.tcecloud.mongodb.v20190725 import mongodb_client, models as mongodb_models
from common.cmp.cloud_apis.resource_apis.tcecloud.monitor.v20170312 import models as monitor_models, monitor_client
from common.cmp.cloud_apis.resource_apis.tcecloud.monitor.v20180724 import models as alarm_models, \
    monitor_client as alarm_client
from common.cmp.cloud_apis.resource_apis.tcecloud.redis.v20180412 import models as redis_models
from common.cmp.cloud_apis.resource_apis.tcecloud.redis.v20180412 import redis_client
from common.cmp.cloud_apis.resource_apis.tcecloud.tcr.v20190924 import models as tcr_models, tcr_client
from common.cmp.cloud_apis.resource_apis.tcecloud.tke.v20180525 import models as tke_models
from common.cmp.cloud_apis.resource_apis.tcecloud.tke.v20180525 import tke_client
from common.cmp.cloud_apis.resource_apis.tcecloud.vpc.v20170312 import models as vpc_models
from common.cmp.cloud_apis.resource_apis.tcecloud.vpc.v20170312 import vpc_client
from common.cmp.cloud_apis.resource_apis.utils import handle_time_str
from common.cmp.utils import convert_param_to_list, get_compute_price_module, get_storage_pricemodule
from core.logger import logger


TCE_COMPONENT = (
    "CVM",
    "CBS",
    "DCDB",
    "VPC",
    "CBS",
    "CFS",
    "CSP",
    "REDIS",
    "MONGODB",
    "CLB",
    "TKE",
    "MARIADB",
    "TCR",
    "BMS",
    "CKAFKA",
    "MONITOR",
    "ALARM",
)

CVM_ACTION = (
    "DescribeInstances",
    "RunInstances",
    "StartInstances",
    "StopInstances",
    "RebootInstances",
    "TerminateInstances",
    "ResetInstancesPassword",
    "ResetInstancesType",
    "DescribeRegions",
    "DescribeZones",
    "DescribeInstanceTypeConfigs",
    "DescribeInstanceFamilyConfigs",
    "DescribeImages",
    "DescribeZoneInstanceConfigInfos",
    "AssociateSecurityGroups",
    "DisassociateSecurityGroups",
    "InquiryPriceRunInstances",
)

VPC_ACTION = (
    "DescribeVpcs",
    "DeleteVpc",
    "DescribeSubnets",
    "DescribeSecurityGroups",
    "CreateSecurityGroup",
    "DeleteSecurityGroup",
    "DescribeSecurityGroupPolicies",
    "CreateSecurityGroupPolicies",
    "DeleteSecurityGroupPolicies",
    "AllocateAddresses",
    "CreateVpc",
    "CreateSubnet",
    "DescribeAvailableZone",
    "DeleteSubnet",
    "DescribeIp6Addresses",
    "DescribeAddresses",
    "ReleaseAddresses",
    "DisassociateAddress",
    "AssociateAddress",
    "ModifyAddressesBandwidth",
    "ModifySecurityGroupPolicies",
)

CBS_ACTION = (
    "DescribeDisks",
    "AttachDisks",
    "DetachDisks",
    "TerminateDisks",
    "DescribeDiskConfigQuota",
    "CreateDisks",
    "CreateSnapshot",
    "DeleteSnapshots",
    "DescribeSnapshots",
    "ApplySnapshot",
    "ResizeDisk",
    "InquiryPriceCreateDisks",
    "ModifyDiskAttributes",
)

CFS_ACTION = (
    "DescribeCfsFileSystems",
    "DescribeAvailableZoneInfo",
    "DescribeCfsPGroups",
    "DescribeMountTargets",
    "DeleteCfsFileSystem",
    "DescribeCfsFileSystemClients",
    "CreateCfsFileSystem",
    "UpdateCfsFileSystemSizeLimit" "DeleteMountTarget",
)

DCDB_ACTION = (
    "DescribeDCDBInstances",
    "CreateHourDCDBInstance",
    "DescribeDBLogFiles",
    "DestroyHourDCDBInstance",
    "DescribeDCDBShards",
    "DescribeAccounts",
    "CreateAccount",
    "DeleteAccount",
    "DescribeDBSlowLogs",
    "ResetAccountPassword",
    "DescribeDatabases",
    "DescribeDBParameters",
    "InitDCDBInstances",
    "IsolateHourDCDBInstance",
    "ActiveHourDCDBInstance",
    "DescribeShardSpec",
    "DescribeDBEngines",
    "DescribeDCDBSaleInfo",
    "ModifyDBParameters",
    "UpgradeHourDCDBInstance",
)

MARIADB_ACTION = (
    "DescribeDBInstances",
    "DescribeDBEngines",
    "DescribeAvailableExclusiveGroups",
    "IsolateHourDBInstance",
    "DestroyHourDBInstance",
    "CreateHourDBInstance",
    "DescribeDBInstanceSpecs",
    "DescribeSaleInfo",
    "DescribeProjectSecurityGroups",
    "UpgradeDBInstance",
    "UpgradeHourDBInstance",
)

CSP_ACTION = ("GetService", "PutBucket")

REDIS_ACTION = (
    "DescribeInstances",
    "CreateInstances",
    "DestroyPostpaidInstance",
    "ResetPassword",
    "ClearInstance",
    "DescribeProductInfo",
    "UpgradeInstance",
)

MONGODB_ACTION = (
    "DescribeDBInstances",
    "DescribeSpecInfo",
    "IsolateDBInstance",
    "CreateDBInstanceHour",
    "ModifyDBInstanceSpec",
)

CLB_ACTION = (
    "DescribeLoadBalancers",
    "CreateLoadBalancer",
    "DeleteLoadBalancer",
    "RegisterTargets",
    "DescribeLoadBalancerListeners",
    "DeleteLoadBalancerListeners",
    "DeleteRule",
    "ModifyDomain",
    "ModifyRule",
    "DeregisterInstancesFromLoadBalancer",
    "ModifyLoadBalancerBackends",
    "CreateLoadBalancerListeners",
    "DescribeLoadBalancerBackends",
    "ModifyLoadBalancerAttributes",
    "CreateForwardLBListenerRules",
)

TKE_ACTION = (
    "DescribeClusters",
    "DescribeImages",
    "DeleteClusterInstances",
    "DeleteCluster",
    "DescribeClusterServices",
    "CreateCluster",
    "DescribeClusterInstances",
    "DescribeInstances",
    "DescribeExistedInstances",
    "AddExistedInstances",
    "ModifyClusterAttribute",
    "DrainClusterNode",
    "CheckClusterCIDR",
    "DescribeQuota",
)

TCR_ACTION = ("DescribeRepositoryFilterPersonal",)

BMS_ACTION = (
    "DescribeInstances",
    "StartInstances",
    "StopInstances",
    "TerminateInstances",
    "DescribeFlavors",
    "RunInstances",
    "TerminateInstances",
    "GetInstancesByTaskId",
    "ModifyInstancesAttribute",
)

CKAFKA_ACTION = (
    "DescribeInstances",
    "DescribeInstanceDetail",
    "CreateTopic",
    "DescribeConsumerGroup",
    "CreateInstance",
    "DescribeCkafkaTypeConfigs",
    "ModifyInstanceAttributes",
    "DeleteInstance",
    "ModifyResourceTce",
)

MONITOR_ACTION = (
    "GetMonitorData",
    "DescribeBaseMetrics",
)

ALARM_ACTION = ("DescribeBasicAlarmList",)

TCE_COMPONENT_TUPLE = [(item, item.lower()) for item in TCE_COMPONENT]
CVM_ACTION_TUPLE = [(item, item) for item in CVM_ACTION]
VPC_ACTION_TUPLE = [(item, item) for item in VPC_ACTION]
CBS_ACTION_TUPLE = [(item, item) for item in CBS_ACTION]
CFS_ACTION_TUPLE = [(item, item) for item in CFS_ACTION]
DCDB_ACTION_TUPLE = [(item, item) for item in DCDB_ACTION]
MARIADB_ACTION_TUPLE = [(item, item) for item in MARIADB_ACTION]
CSP_ACTION_TUPLE = [(item, item) for item in CSP_ACTION]
REDIS_ACTION_TUPLE = [(item, item) for item in REDIS_ACTION]
MONGODB_ACTION_TUPLE = [(item, item) for item in MONGODB_ACTION]
CLB_ACTION_TUPLE = [(item, item) for item in CLB_ACTION]
TKE_ACTION_TUPLE = [(item, item) for item in TKE_ACTION]
TCR_ACTION_TUPLE = [(item, item) for item in TCR_ACTION]
BMS_ACTION_TUPLE = [(item, item) for item in BMS_ACTION]
CKAFKA_ACTION_TUPLE = [(item, item) for item in CKAFKA_ACTION]
MONITOR_ACTION_TUPLE = [(item, item) for item in MONITOR_ACTION]
ALARM_ACTION_TUPLE = [(item, item) for item in ALARM_ACTION]

ComponentCategory = type("TceComponentEnum", (object,), dict(TCE_COMPONENT_TUPLE))
CVMActionCategory = type("CvmActionEnum", (object,), dict(CVM_ACTION_TUPLE))
VPCActionCategory = type("VpcActionEnum", (object,), dict(VPC_ACTION_TUPLE))
CBSActionCategory = type("CbsActionEnum", (object,), dict(CBS_ACTION_TUPLE))
CFSActionCategory = type("CfsActionEnum", (object,), dict(CFS_ACTION_TUPLE))
DCDBActionCategory = type("DcdbActionEnum", (object,), dict(DCDB_ACTION_TUPLE))
MARIADBActionCategory = type("MariadbActionEnum", (object,), dict(MARIADB_ACTION_TUPLE))
CSPActionCategory = type("CspActionEnum", (object,), dict(CSP_ACTION_TUPLE))
RedisActionCategory = type("RedisActionEnum", (object,), dict(REDIS_ACTION_TUPLE))
MongoDBActionCategory = type("MongoDBActionEnum", (object,), dict(MONGODB_ACTION_TUPLE))
CLBActionCategory = type("ClbActionEnum", (object,), dict(CLB_ACTION_TUPLE))
TKEActionCategory = type("TkeActionEnum", (object,), dict(TKE_ACTION_TUPLE))
TCRActionCategory = type("TcrActionEnum", (object,), dict(TCR_ACTION_TUPLE))
BMSActionCategory = type("BMSActionEnum", (object,), dict(BMS_ACTION_TUPLE))
CKAFKAActionCategory = type("CKAFKAActionEnum", (object,), dict(CKAFKA_ACTION_TUPLE))
MONITORActionCategory = type("MONITORActionEnum", (object,), dict(MONITOR_ACTION_TUPLE))
ALARMActionCategory = type("ALARMACTIONEnum", (object,), dict(ALARM_ACTION_TUPLE))

resource_mapping = {
    "cvm": (ComponentCategory.CVM, CVMActionCategory.DescribeInstances, "InstanceSet"),
    "vpc": (ComponentCategory.VPC, VPCActionCategory.DescribeVpcs, "VpcSet"),
    "subnet": (ComponentCategory.VPC, VPCActionCategory.DescribeSubnets, "SubnetSet"),
    "security_group": (ComponentCategory.VPC, VPCActionCategory.DescribeSecurityGroups, "SecurityGroupSet"),
    "cbs": (ComponentCategory.CBS, CBSActionCategory.DescribeDisks, "DiskSet"),
    "image": (ComponentCategory.CVM, CVMActionCategory.DescribeImages, "ImageSet"),
    "cfs": (ComponentCategory.CFS, CFSActionCategory.DescribeCfsFileSystems, "FileSystems"),
    "dcdb": (ComponentCategory.DCDB, DCDBActionCategory.DescribeDCDBInstances, "Instances"),
    "mariadb": (ComponentCategory.MARIADB, MARIADBActionCategory.DescribeDBInstances, "Instances"),
    "mongodb": (ComponentCategory.MONGODB, MongoDBActionCategory.DescribeDBInstances, "InstanceDetails"),
    "redis": (ComponentCategory.REDIS, RedisActionCategory.DescribeInstances, "InstanceSet"),
    "clb": (ComponentCategory.CLB, CLBActionCategory.DescribeLoadBalancers, "LoadBalancerSet"),
    "tke": (ComponentCategory.TKE, TKEActionCategory.DescribeClusters, "Clusters"),
    "tke_ins": (ComponentCategory.TKE, TKEActionCategory.DescribeClusterInstances, "InstanceSet"),
    "dcdb_shard": (ComponentCategory.DCDB, DCDBActionCategory.DescribeDCDBShards, "Shards"),
    "instance_config": (ComponentCategory.CVM, CVMActionCategory.DescribeZoneInstanceConfigInfos, "ZoneInstanceConfig"),
    "eip": (ComponentCategory.VPC, VPCActionCategory.DescribeAddresses, "AddressSet"),
    "snapshot": (ComponentCategory.CBS, CBSActionCategory.DescribeSnapshots, "SnapshotSet"),
    "bms": (ComponentCategory.BMS, BMSActionCategory.DescribeInstances, "InstanceSet"),
    "bms_flavor": (ComponentCategory.BMS, BMSActionCategory.DescribeFlavors, "FlavorSet"),
    "ckafka": (ComponentCategory.CKAFKA, CKAFKAActionCategory.DescribeInstances, ["Result", "InstanceList"]),
    "ckafka_detail": (
        ComponentCategory.CKAFKA,
        CKAFKAActionCategory.DescribeInstanceDetail,
        ["Result", "InstanceList"],
    ),
    "ckafka_consumer": (ComponentCategory.CKAFKA, CKAFKAActionCategory.DescribeConsumerGroup, "Result"),
}

client_mapping = {
    "dcdb": (dcdb_client.DcdbClient, dcdb_models),
    "cvm": (cvm_client.CvmClient, cvm_models),
    "vpc": (vpc_client.VpcClient, vpc_models),
    "cbs": (cbs_client.CbsClient, cbs_models),
    "cfs": (cfs_client.CfsClient, cfs_models),
    "csp": (csp_client.CspClient, csp_models),
    "redis": (redis_client.RedisClient, redis_models),
    "mongodb": (mongodb_client.MongodbClient, mongodb_models),
    "clb": (clb_client.ClbClient, clb_models),
    "tke": (tke_client.TkeClient, tke_models),
    "mariadb": (mariadb_client.MariadbClient, mariadb_models),
    "tcr": (tcr_client.TcrClient, tcr_models),
    "bms": (bms_client.BmsClient, bms_models),
    "ckafka": (ckafka_client.CkafkaClient, ckafka_models),
    "monitor": (monitor_client.MonitorClient, monitor_models),
    "alarm": (alarm_client.MonitorClient, alarm_models),
}


class CwTCE:
    def __init__(self, secret_id, secret_key, region_id, host="", **kwargs):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region_id = region_id
        self.domain = host
        self.tce_ins = None
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.cred = credential.Credential(self.secret_id, self.secret_key)

    def __getattr__(self, method_name):
        if not self.tce_ins:
            self.tce_ins = TCE(
                cred=self.cred,
                method_name=method_name,
                region_id=self.region_id,
                domain=self.domain,
                secret_id=self.secret_id,
                secret_key=self.secret_key,
            )
            return self.tce_ins
        else:
            self.tce_ins.method_name = method_name
            return self.tce_ins


class TCE(PublicCloudManage):
    def __init__(self, cred, method_name, region_id, domain, secret_id=None, secret_key=None, version="api3"):
        self.cred = cred
        self.method_name = method_name
        self.region_id = region_id
        self.domain = domain
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.version = version
        self.cloud_type = CloudType.TCE.value

        # cache object
        self.region_cache = None
        self.zone_cache = None

    def __call__(self, *args, **kwargs):
        return getattr(self, self.method_name, self._non_function)(*args, **kwargs)

    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    @staticmethod
    def _get_client_profile(resource_type, version, domain):
        http_profile = HttpProfile()
        http_profile.endpoint = "{}.{}.{}".format(resource_type, version, domain)
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        return client_profile

    # ******************** tool func *********************
    def format_resource(self, resource_type, data, **kwargs):
        kwargs["region_id"] = self.region_id
        format_method = get_format_method(self.cloud_type, resource_type, **kwargs)
        if isinstance(data, list):
            return [format_method(cur_data, **kwargs) for cur_data in data]
        elif data is None:
            return None
        else:
            return format_method(data, **kwargs)

    def handle_call_request(self, component_name, client_method_name, params, request_method_name=None):
        component_obj = client_mapping[component_name]
        component_name = "monitor" if component_name == "alarm" else component_name
        client_profile = self._get_client_profile(component_name, self.version, self.domain)
        client_ins = component_obj[0](self.cred, self.region_id, client_profile)
        request_method_name = request_method_name or "%sRequest" % client_method_name
        request_ins = getattr(component_obj[1], request_method_name)()
        for key, value in params.items():
            setattr(request_ins, key, value)
        response_obj = getattr(client_ins, client_method_name)(request_ins)
        return response_obj

    def _resource_list(self, resource_type, filter_param=None, result_params=None):
        """
        Get all resource.
        :param resource_type
               type: str(required)
        :param filter_param
               type: dict(optional)
        """
        resource_list = []
        filter_param = filter_param or {}
        params = {"Limit": 50, "Offset": 0}
        params.update(filter_param)
        try:
            resp = self.handle_call_request(
                resource_mapping[resource_type][0], resource_mapping[resource_type][1], params
            )
        except TceCloudSDKException as e:
            logger.exception("get {} failed: {}".format(resource_type, e))
            return e.message, 0, False
        try:
            total_count = resp.TotalCount
        except AttributeError:
            total_count = resp.Result.TotalCount
        except Exception as e:
            logger.exception("请求资源{}失败，返回结果无法正常解析。错误信息：{}".format(resource_mapping[resource_type][0], str(e)))
            raise Exception("解析返回数据失败，请查看日志")
        if result_params:
            resource_list.extend(getattr(getattr(resp, result_params[0]), result_params[1]))
        else:
            resource_list.extend(getattr(resp, resource_mapping[resource_type][2]))
        if total_count > 50:
            max_page = int(total_count / 50) if total_count % 50 == 0 else int(total_count / 50) + 1

            for i in range(1, max_page):
                params["Offset"] = 50 * i
                try:
                    resp = self.handle_call_request(
                        resource_mapping[resource_type][0], resource_mapping[resource_type][1], params
                    )
                except TceCloudSDKException as e:
                    return e.message, 0, False
                resource_list.extend(getattr(resp, resource_mapping[resource_type][2]))

        return resource_list, total_count, True

    @property
    def cos_client(self):
        if not hasattr(self, "_cos_client"):
            self.create_cos_client()
        return self._cos_client

    @cos_client.setter
    def cos_client(self, value):
        self._cos_client = value

    def create_cos_client(self):
        endpoint = "{}.cos.{}".format(format_region(self.region_id), self.domain)
        config = CosConfig(Scheme="http", Secret_id=self.secret_id, Secret_key=self.secret_key, Endpoint=endpoint)
        self.cos_client = CosS3Client(config)

    # ********************* common **********************
    def list_projects(self, **kwargs):
        return {"result": True, "data": []}

    def list_regions(self):
        """
        Get regions.
        """
        if self.region_cache:
            return self.region_cache
        try:
            resp = self.handle_call_request(ComponentCategory.CVM, CVMActionCategory.DescribeRegions, {})
        except TceCloudSDKException as e:
            logger.exception("Get regions failed: %s" % e)
            return {"result": False, "message": e.message}
        total_count = resp.TotalCount
        data = self.format_resource("region", resp.RegionSet)
        self.region_cache = data
        return {"result": True, "data": data, "total": total_count}

    def list_zones(self, **kwargs):
        """
        Get zones.
        """
        if self.zone_cache:
            return self.zone_cache
        try:
            resp = self.handle_call_request(ComponentCategory.CVM, CVMActionCategory.DescribeZones, {})
        except TceCloudSDKException as e:
            logger.exception("Get zones failed: %s" % e)
            return {"result": False, "message": e.message}
        total_count = resp.TotalCount
        data = self.format_resource("zone", resp.ZoneSet)
        self.zone_cache = data
        return {"result": True, "data": data, "total": total_count}

    def get_connection_result(self):
        """
        Check connection status.
        """
        rs = self.list_regions()
        if rs["result"]:
            return {"result": True}
        else:
            return {"result": False}

    def list_instance_types(self, filters=None):
        """
        Get instance type configs.
        :param filters
               type: list of filter(optional)
               eg. [{
                   "name": "zone",
                   "values": ["yfm14-az1"]
               }]
        """
        params = {}
        if filters and isinstance(filters, list):
            filter_list = []
            for cur_filter in filters:
                if cur_filter.get("name") is not None and isinstance(cur_filter.get("values"), list):
                    filter_obj = cvm_models.Filter()
                    filter_obj.Name = cur_filter["name"]
                    filter_obj.Values = cur_filter["values"]
                    filter_list.append(filter_obj)
            params["Filters"] = filter_list
        try:
            resp = self.handle_call_request(
                ComponentCategory.CVM, CVMActionCategory.DescribeInstanceTypeConfigs, params
            )
        except TceCloudSDKException as e:
            logger.exception("get instance type configs failed: %s" % e)
            return {"result": False, "message": e.message}
        data = self.format_resource("instance_type", resp.InstanceTypeConfigSet)
        return {"result": True, "data": data}

    def list_instance_type_families(self):
        """
        Get flavor families. 规格族
        """
        try:
            resp = self.handle_call_request(ComponentCategory.CVM, CVMActionCategory.DescribeInstanceFamilyConfigs, {})
        except TceCloudSDKException as e:
            logger.exception("get flavor families failed: %s" % e)
            return {"result": False, "message": e.message}
        data = self.format_resource(
            "instance_type_family", resp.InstanceFamilyConfigSet, **{"region_id": self.region_id}
        )
        return {"result": True, "data": data}

    # todo 接口暂时无法调用，后期核对需求看是否需要 有很多额外参数，未测试完成
    def get_instance_price(self, **kwargs):
        """
        InquiryPriceRunInstances 获取实例价格
        Args:
            Placement (object): 位置信息对象，参照下方格式
            ImageId (str): 镜像id
            ... 其他需要测试补充

        Returns:

        """
        placement = cvm_models.Placement()
        placement.Zone = "yxm4"
        params = {"Placement": placement}
        try:
            resp = self.handle_call_request(ComponentCategory.CVM, CVMActionCategory.InquiryPriceRunInstances, params)
        except TceCloudSDKException as e:
            logger.exception("get flavor families failed: %s" % e)
            return {"result": False, "message": e.message}
        # data = self.format_resource("instance_type_family", resp.InstanceFamilyConfigSet,
        #                             **{"region_id": self.region_id})
        return {"result": True, "data": resp}

    # ********************* vm **********************
    def list_vms(self, ids=None, **kwargs):
        """
        Get vm(s).
        :param ids
               type: list of str or str
        """
        params = {}
        if ids:
            params["InstanceIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list("cvm", params)
        if status:
            return {
                "result": True,
                "data": self.format_resource("vm", resp_data),
                "total": total,
            }
        else:
            return {"result": False, "message": resp_data}

    def create_vm(self, **kwargs):
        """
        Create a vm.
        :param placement: vm position.
               type: dict(required)
               eg. {
                   "zone": "yfm14-az1",  # type: str(required)
                   "project_id": 0,      # type: int(required)
                   "host_ids": None      # type: List(optional)
               }
        :param image_id
               type: str(required)
        :param instance_charge_type
                type: str(optional)
                default: "POSTPAID_BY_HOUR"
        :param instance_type
               type: str(optional)
               default: "S1.SMALL1"
        :param system_disk
               type: dict(optional)
               eg. {
                   "disk_size": 50,  # type: int(required)
                   "disk_type: "CLOUD_SSD"  # type: str(required)
               }
        :param data_disks
               type: dict(optional)
               eg. [{
                   "disk_size: 50,  # type: int(required)
                   "disk_type: "CLOUD_SSD",  # type: str(required)
                   "delete_with_instance: True  # type: bool(optional) default: True
               }]
        :param virtual_private_cloud
               type: dict(optional)
               eg. {
                   "vpc_id": "vpc-6wc04fab",  # type: str(required)
                   "subnet_id": "subnet-9u0n10go",  #  type: str(required)
                   "as_vpc_gateway": False,  # type: bool(optional) default: False
                   "ipv6_address_count": 0  # type: int(optional) default: 0
               }
        :param internet_accessible
               type: dict(optional)
               eg. {
                   "internet_max_bandwith_out": 0,  # type: int(required)
                   "public_ip_assigned": False,  # type: bool(required)
                   "internet_charge_type": "TRAFFIC_POSTPAID_BY_HOUR"  # type: str(required)
               }
        :param instance_count
               type: int(optional)
               default: 1
        :param instance_name
               type: str(optional)
        :param login_settings
               attr:
                   password: instance password
                             type: str
                   key_ids: key ids
                            type: list of str
                   keep_image_login: keey origin image settings
                                     type: bool

               type: dict(optional)
               eg. {
                   "password": "passwordxx,"
               }
        :param security_group_ids
               type: list of str(optional)
        :param enhanced_service
               type: dict(optional)
               eg. {
                   "security_service": {
                       "enabled": true
                   },
                   "monitor_service": {
                       "enabled": true
                   }
               }
        :param hostname
               type: str(optional)
        :param user_data
               type: str(optional)
        :param disaster_recover_group_ids
               type: list of str(optional)
        :param tag_specification
               type: list of dict(optional)
               eg. [{
                   "resource_type": "instance",
                   "tags": [{
                       "key": "test",
                       "value": "demo"
                   }, {
                       "key": "test1",
                       "value": "demo1"
                  }]
               }]
        """
        result = self._valid_vm_params(**kwargs)
        if not result:
            return result
        placement = result.get("data")
        kwargs["placement"] = placement
        params = self._set_vm_params(**kwargs)
        try:
            resp = self.handle_call_request(ComponentCategory.CVM, CVMActionCategory.RunInstances, params)
        except TceCloudSDKException as e:
            logger.exception("create cvm failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.InstanceIdSet}

    def _valid_vm_params(self, **kwargs):
        """
        校验创建虚拟机参数
        Args:
            **kwargs ():

        Returns:

        """
        if kwargs.get("placement") and kwargs["placement"].get("zone"):
            placement = cvm_models.Placement()
            placement.Zone = kwargs["placement"]["zone"]
            if not kwargs["placement"].get("project_id") is None:
                placement.ProjectId = kwargs["placement"]["project_id"]
            if not kwargs["placement"].get("host_ids") is None:
                placement.HostIds = kwargs["placement"]["host_ids"]
            return {"result": True, "data": placement}
        else:
            return {"result": False, "message": u"缺少placement参数"}

    def _set_vm_params(self, placement, **kwargs):
        """
        设置创建虚拟机的参数
        Args:
            placement ():
            **kwargs ():

        Returns:

        """
        params = {
            "Placement": placement,
            "ImageId": kwargs["image_id"],
        }
        if kwargs.get("instance_type"):
            params["InstanceType"] = kwargs["instance_type"]

        if (
            kwargs.get("system_disk")
            and kwargs["system_disk"].get("disk_type")
            and kwargs["system_disk"].get("disk_size")
        ):
            system_disk = cvm_models.SystemDisk()
            system_disk.DiskType = kwargs["system_disk"]["disk_type"]
            system_disk.DiskSize = kwargs["system_disk"]["disk_size"]
            params["SystemDisk"] = system_disk
        if kwargs.get("data_disks") and isinstance(kwargs["data_disks"], list):
            data_disk_list = []
            for cur_obj in kwargs["data_disks"]:
                data_disk = cvm_models.DataDisk()
                data_disk.DiskSize = cur_obj.get("disk_size")
                data_disk.DiskType = cur_obj.get("disk_type")
                data_disk.DeleteWithInstance = cur_obj.get("delete_with_instance", True)
                data_disk_list.append(data_disk)
            params["DataDisks"] = data_disk_list
        if (
            kwargs.get("virtual_private_cloud")
            and kwargs["virtual_private_cloud"].get("vpc_id")
            and kwargs["virtual_private_cloud"].get("subnet_id")
        ):
            vpc = cvm_models.VirtualPrivateCloud()
            vpc.VpcId = kwargs["virtual_private_cloud"]["vpc_id"]
            vpc.SubnetId = kwargs["virtual_private_cloud"]["subnet_id"]
            vpc.AsVpcGateway = kwargs["virtual_private_cloud"].get("as_vpc_gateway", False)
            vpc.Ipv6AddressCount = kwargs["virtual_private_cloud"].get("ipv6_address_count")
            params["VirtualPrivateCloud"] = vpc
        if kwargs.get("internet_accessible"):
            internet_access = cvm_models.InternetAccessible()
            internet_access.InternetChargeType = kwargs["internet_accessible"].get(
                "internet_charge_type", "TRAFFIC_POSTPAID_BY_HOUR"
            )
            internet_access.InternetMaxBandwidthOut = kwargs["internet_accessible"].get("internet_max_bandwidth_out", 0)
            internet_access.PublicIpAssigned = kwargs["internet_accessible"].get("public_ip_assigned", False)
            params["InternetAccessible"] = internet_access
        if kwargs.get("instance_count"):
            params["InstanceCount"] = kwargs["instance_count"]
        if kwargs.get("instance_name"):
            params["InstanceName"] = kwargs["instance_name"]
        if kwargs.get("login_settings"):
            login_settings = cvm_models.LoginSettings()
            if kwargs["login_settings"].get("password"):
                login_settings.Password = kwargs["login_settings"]["password"]
            if kwargs["login_settings"].get("key_ids"):
                login_settings.KeyIds = kwargs["login_settings"]["key_ids"]
            if not kwargs["login_settings"].get("keep_image_login") is None:
                login_settings.KeepImageLogin = kwargs["login_settings"]["keep_image_login"]
            params["LoginSettings"] = login_settings
        if kwargs.get("security_group_ids") and isinstance(kwargs["security_group_ids"], list):
            params["SecurityGroupIds"] = kwargs["security_group_ids"]
        if kwargs.get("enhanced_service"):
            enhanced_service = cvm_models.EnhancedService()
            if kwargs["enhanced_service"].get("security_service"):
                run_security_service_enabled = cvm_models.RunSecurityServiceEnabled()
                run_security_service_enabled.Enabled = kwargs["enhanced_service"]["security_service"].get(
                    "enabled", False
                )
                enhanced_service.SecurityService = run_security_service_enabled
            if kwargs["enhanced_service"].get("monitor_service"):
                run_monitor_service_enabled = cvm_models.RunMonitorServiceEnabled()
                run_monitor_service_enabled.Enabled = kwargs["enhanced_service"]["monitor_service"].get(
                    "enabled", False
                )
                enhanced_service.MonitorService = run_monitor_service_enabled
            params["EnhancedService"] = enhanced_service
        if kwargs.get("hostname"):
            params["HostName"] = kwargs["hostname"]
        if kwargs.get("user_data"):
            params["UserData"] = kwargs["user_data"]
        if kwargs.get("disaster_recover_group_ids"):
            params["DisasterRecoverGroupIds"] = kwargs["disaster_recover_group_ids"]
        if kwargs.get("tag_specification") and isinstance(kwargs["tag_specification"], list):
            tag_obj_list = []
            for cur_tag_obj in kwargs["tag_specification"]:
                tag_obj = cvm_models.TagSpecification()
                tag_obj.ResourceType = cur_tag_obj.get("resource_type")
                tag_list = []
                if cur_tag_obj.get("tags") and isinstance(cur_tag_obj["tags"], list):
                    for temp in cur_tag_obj["tags"]:
                        tag = cvm_models.Tag()
                        tag.Key = temp.get("key")
                        tag.Value = temp.get("value")
                        tag_list.append(tag)
                tag_obj.Tags = tag_list
                tag_obj_list.append(tag_obj)

            params["TagSpecification"] = tag_obj_list
        return params

    def _vm_action(self, vm_id, action_name, **kwargs):
        """
         Vm(s) action.
        :param vm_id
               type: str or list of str(required)
        :param action_name
               type: str(required)
        """
        if isinstance(vm_id, list):
            instance_ids = vm_id
        elif isinstance(vm_id, str):
            instance_ids = [str(vm_id)]
        else:
            return {"result": False, "message": u"非法实例ID"}
        params = {"InstanceIds": instance_ids}
        if kwargs:
            params.update(kwargs)
        try:
            self.handle_call_request(ComponentCategory.CVM, action_name, params)
        except TceCloudSDKException as e:
            logger.exception("operate vm(s)[{}] failed: {}".format(vm_id, e))
            return {"result": False, "message": e.message}
        return {"result": True}

    def start_vm(self, vm_id):
        """
        Start vm(s).
        :param vm_id
               type: str or list of str(required)
        """
        return self._vm_action(vm_id, CVMActionCategory.StartInstances)

    def stop_vm(self, vm_id, is_force=None):
        """
        Stop vm(s).
        :param vm_id
               type: str or list of str(required)
        :param is_force
               type: bool(optional)
        """
        return self._vm_action(vm_id, CVMActionCategory.StopInstances, ForceStop=is_force)

    def restart_vm(self, vm_id, is_force=None):
        """
        Reboot vm(s).
        :param vm_id
               type: str or list of str(required)
        :param is_force
               type: bool(optional)
        """
        return self._vm_action(vm_id, CVMActionCategory.RebootInstances, ForceReboot=is_force)

    def destroy_vm(self, vm_id, release_address=None, dry_run=None):
        """
        Reboot vm(s).
        :param vm_id
               type: str or list of str(required)
        :param release_address
               type: bool(optional)
        :param dry_run
               type: bool(optional)
        """
        return self._vm_action(
            vm_id, CVMActionCategory.TerminateInstances, ReleaseAddress=release_address, DryRun=dry_run
        )

    def reset_instances_password(self, InstanceIds, Password, UserName=None, ForceStop=None):
        """
        Reset instance(s) password.
        :param InstanceIds
               type: str or list of str(required)
        :param Password
               type: str(required)
        :param UserName 待重置密码的实例操作系统用户名
               type: str(optional)
        :param ForceStop
               type: bool(required)
        """
        return self._vm_action(
            InstanceIds,
            CVMActionCategory.ResetInstancesPassword,
            UserName=UserName,
            Password=Password,
            ForceStop=ForceStop,
        )

    def modify_vm(self, vm_id, instance_type, force_stop=None):
        """
        Resize a vm.
         :param vm_id
               type: str or list of str(required)
        :param instance_type
               type: str(required)
        :param force_stop
               type: str(required)
        """
        return self._vm_action(
            vm_id, CVMActionCategory.ResetInstancesType, InstanceType=instance_type, ForceStop=force_stop
        )

    def list_zone_instance_configs(self, **kwargs):
        """
        获取可用区的机型信息
        Returns:

        """
        if kwargs:
            params = {"Filters": [{"Name": name, "Values": value} for name, value in kwargs.items()]}
        else:
            params = {}
        try:
            resp = self.handle_call_request(
                ComponentCategory.CVM, CVMActionCategory.DescribeZoneInstanceConfigInfos, params
            )
        except TceCloudSDKException as e:
            logger.exception("Get instance_config failed: %s" % e)
            return {"result": False, "message": e.message}
        data = self.format_resource("instance_config", resp.InstanceTypeQuotaSet)
        return {"result": True, "data": data}

    def _vm_security_group_action(self, action_name, **kwargs):
        """
        实例和安全组绑定
        Args:
            action_name (str): 方法名  如CVMActionCategory.AssociateSecurityGroups
            **kwargs ():
                SecurityGroupIds (list): 安全组id的列表
                InstanceIds (list): 实例id的列表

        Returns:

        """
        group_ids = kwargs.get("SecurityGroupIds")
        vm_ids = kwargs.get("InstanceIds")
        if not group_ids:
            return {"result": False, "message": u"安全组id不允许为空"}
        if not vm_ids:
            return {"result": False, "message": u"实例id不允许为空"}
        params = {
            "SecurityGroupIds": group_ids if isinstance(group_ids, list) else [group_ids],
            "InstanceIds": vm_ids if isinstance(vm_ids, list) else [vm_ids],
        }
        resp = self.handle_call_request(ComponentCategory.CVM, action_name, params)
        return resp

    def vm_associate_security_groups(self, **kwargs):
        """
        主机实例绑定安全组
        SDK参数：SecurityGroupIds (list); InstanceIds (list)
        Args:
            **kwargs ():
                SecurityGroupIds (list): 安全组id的列表
                InstanceIds (list): 实例id的列表
        Returns:

        """
        try:
            resp = self._vm_security_group_action(CVMActionCategory.AssociateSecurityGroups, **kwargs)
        except Exception as e:
            logger.exception(u"实例绑定安全组异常{},参数:{}".format(e, kwargs))
            return {"result": False, "message": str(e.message)}
        return {"result": True, "data": resp}

    def vm_disassociate_security_groups(self, **kwargs):
        """
        主机实例解绑安全组
        SDK参数：SecurityGroupIds (list); InstanceIds (list)
        Args:
            **kwargs ():
                SecurityGroupIds (list): 安全组id的列表
                InstanceIds (list): 实例id的列表

        Returns:

        """
        try:
            resp = self._vm_security_group_action(CVMActionCategory.DisassociateSecurityGroups, **kwargs)
        except Exception as e:
            logger.exception(u"实例解绑安全组异常{},参数:{}".format(e, kwargs))
            return {"result": False, "message": str(e.message)}
        return {"result": True, "data": resp}

    # --------------------------network-------------------------------------------
    # ---------------- vpc and subnet ----------------
    def get_vpc_avail_zones(self):
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, VPCActionCategory.DescribeAvailableZone, {})
        except TceCloudSDKException as e:
            logger.exception("get vpc available zone failed: %s" % e)
            return {"result": False, "message": e.message}

        data = [
            {
                "zone": zone.Zone,
                "zone_name": zone.ZoneName,
                "zone_id": zone.ZoneId,
                "zone_state": zone.ZoneState,
            }
            for zone in resp.ZoneSet
            if zone.ZoneState == "UNAVAILABLE"
        ]

        return {"result": True, "data": data, "total": resp.TotalCount}

    def create_vpc(self, **kwargs):
        """
        Create a vpc.
        :param vpc_name
               type: str(required)
        :param cidr_block
               type: str(required)
               values: 10.0.0.0/16 | 172.16.0.0/16 | 192.168.0.0/16
        :param enable_multicast
               type: bool(optional)
        :param dns_servers
               type: list(optional)
        :param domain_name
               type: str(optional)
        :param tags
               type: list(optional)
               eg: [{
                "key": "city",
                "value": "shanghai"
               }]
        """
        if isinstance(kwargs.get("tags"), list):
            vpc_tag_list = []
            for cur_tag in kwargs["tags"]:
                vpc_tag = vpc_models.Tag()
                vpc_tag.Key = cur_tag.get("key")
                vpc_tag.Value = cur_tag.get("value")
                vpc_tag_list.append(vpc_tag)
            kwargs["Tags"] = vpc_tag_list
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, VPCActionCategory.CreateVpc, kwargs)
        except TceCloudSDKException as e:
            logger.exception("create vpc failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.Vpc.VpcId}

    def list_vpcs(self, ids=None, *kwargs):
        """
        Get vpc list.
        :param ids
               type: list of str or str
        """
        params = {}
        if ids:
            params["VpcIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list("vpc", params)
        if status:
            return {"result": True, "data": self.format_resource("vpc", resp_data), "total": total}
        else:
            return {"result": False, "message": resp_data}

    def delete_vpc(self, vpc_id):
        """
        删除vpc
        SDK参数：VpcId (str)
        Args:
            vpc_id (str): id of vpc

        Returns:

        """
        return self._delete_network_resource("VpcId", VPCActionCategory.DeleteVpc, vpc_id, "VPC")

    def create_subnet(self, **kwargs):
        """
        Create a subnet.
        :param VpcId
               type: str(required)
        :param SubnetName
               type: str(required)
        :param CidrBlock
               type: list(required)
        :param Zone
               type: str(required)
        :param tags
               type: list(optional)
               eg: [{
                "key": "city",
                "value": "shanghai"
               }]
        """
        if not kwargs.get("VpcId"):
            return {"result": False, "message": u"VPC不能为空"}
        if not kwargs.get("SubnetName"):
            return {"result": False, "message": u"子网名称不能为空"}
        if not kwargs.get("Zone"):
            return {"result": False, "message": u"可用区不能为空"}
        if not kwargs.get("CidrBlock"):
            return {"result": False, "message": u"子网网段必须在VPC网段内，相同VPC内子网网段不能重叠"}
        params = {
            "VpcId": kwargs["VpcId"],
            "SubnetName": kwargs["SubnetName"],
            "CidrBlock": kwargs["CidrBlock"],
            "Zone": kwargs["Zone"],
        }
        if isinstance(kwargs.get("tags"), list):
            vpc_tag_list = []
            for cur_tag in kwargs["tags"]:
                vpc_tag = vpc_models.Tag()
                vpc_tag.Key = cur_tag.get("key")
                vpc_tag.Value = cur_tag.get("value")
                vpc_tag_list.append(vpc_tag)
            params["Tags"] = vpc_tag_list
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, VPCActionCategory.CreateSubnet, params)
        except TceCloudSDKException as e:
            logger.exception("create subnet failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.Subnet.SubnetId}

    def list_subnets(self, ids=None, **kwargs):
        """
        Get subnet list.
        :param ids
               type: list of str or str
        """
        if ids:
            kwargs["SubnetIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list("subnet", kwargs)
        if status:
            return {"result": True, "data": self.format_resource("subnet", resp_data), "total": total}
        else:
            logger.error(u"获取子网失败{}".format(kwargs))
            return {"result": False, "message": resp_data}

    def delete_subnet(self, **kwargs):
        """
        删除子网
        SDK: SubnetId (str)
        Args:
            subnet_id (str):

        Returns:

        """
        subnet_id = kwargs.get("subnet_id")
        return self._delete_network_resource("SubnetId", VPCActionCategory.DeleteSubnet, subnet_id, "子网")

    def _delete_network_resource(self, param_name, method_name, resource_id, resource_type):
        """
        删除网络资源
        Args:
            param_name (str): 参数名
            method_name (str): 方法名
            resource_id (str): 资源id
            resource_type (str): 资源类型

        Returns:

        """
        if not resource_id:
            return {"result": False, "message": u"{}对应id不能为空".format(resource_type)}
        params = {param_name: resource_id}
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, method_name, params)
        except Exception as e:
            logger.exception("删除{}失败。错误信息:{}, {}id: {}".format(resource_type, e, resource_type, resource_id))
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    # ----------------------- security_group -----------------
    def list_security_groups(self, ids=None, **kwargs):
        """
        Get security group list.
        :param SecurityGroupIds
               type: list of str or str
        """
        if ids:
            kwargs["SecurityGroupIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list("security_group", kwargs)
        if status:
            return {
                "result": True,
                "data": self.format_resource("security_group", resp_data, **{"region_id": self.region_id}),
                "total": total,
            }
        else:
            logger.error(u"同步安全组失败{}".format(kwargs))
            return {"result": False, "message": resp_data}

    def create_security_group(self, **kwargs):
        """
        创建安全组
        Args:
            **kwargs ():
                GroupName (str)： 安全组名、  (optional) 同项目不可重名，不可超过60个字符
                GroupDescription (str)： 安全组备注。  （optional） 不可超过100个字符
                ProjectId (str)： 项目id。默认0   （optional）
                Tags (list)： 标签。内部是dict   optional

        Returns:

        """
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, VPCActionCategory.CreateSecurityGroup, kwargs)
        except Exception as e:
            logger.exception(u"TCE创建安全组失败，参数：{}，错误信息：{}".format(kwargs, str(e)))
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.SecurityGroup.SecurityGroupId}

    def delete_security_group(self, group_id, **kwargs):
        """
        删除安全组
        Args:
            group_id (str)： 安全组id、  (required)

        Returns:

        """
        return self._delete_network_resource("SecurityGroupId", VPCActionCategory.DeleteSecurityGroup, group_id, "安全组")

    def list_security_group_rules(self, security_group_id, **kwargs):
        """
        获取安全组规则列表  SDK接口需要参数 SecurityGroupId   可获取到version
        Args:
            security_group_id: 安全组id
            **kwargs ():

        Returns:

        """
        if not security_group_id:
            return {"result": False, "message": "安全组id不能为空"}
        kwargs["SecurityGroupId"] = security_group_id
        try:
            resp = self.handle_call_request(
                ComponentCategory.VPC, VPCActionCategory.DescribeSecurityGroupPolicies, kwargs
            )
        except Exception as e:
            logger.exception(u"获取安全组{}规则失败{}".format(security_group_id, e))
            return {"result": False, "message": e.message}
        version = resp.SecurityGroupPolicySet.Version
        data = self.format_resource(
            "security_group_rule",
            resp.SecurityGroupPolicySet.Egress,
            **{"direction": "EGRESS", "version": version, "security_group_id": security_group_id}
        )
        data.extend(
            self.format_resource(
                "security_group_rule",
                resp.SecurityGroupPolicySet.Ingress,
                **{"direction": "INGRESS", "version": version, "security_group_id": security_group_id}
            )
        )
        return {"result": True, "data": data}

    def create_security_group_rule(self, **kwargs):
        """
        创建安全组规则   SDK接口参数：SecurityGroupId SecurityGroupPolicySet
        Args:
            **kwargs ():

        Returns:

        """
        if not kwargs.get("SecurityGroupId"):
            return {"result": False, "message": u"参数SecurityGroupId(安全组id)不能为空"}
        if not kwargs.get("SecurityGroupPolicySet"):
            return {"result": False, "message": u"参数SecurityGroupPolicySet(安全组规则)不能为空"}
        try:
            resp = self.handle_call_request(
                ComponentCategory.VPC, VPCActionCategory.CreateSecurityGroupPolicies, kwargs
            )
        except Exception as e:
            logger.exception(u"TCE创建安全组规则失败" + str(e))
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    def destroy_security_group_rule(self, **kwargs):
        """
        删除安全组规则 接口文档需要参数  SecurityGroupId version indexes direction
        Args:
            **kwargs ():

        Returns:

        """
        try:
            resp = self.handle_call_request(
                ComponentCategory.VPC, VPCActionCategory.DeleteSecurityGroupPolicies, kwargs
            )
        except Exception as e:
            logger.exception("TCE delete security_group_rule error" + str(e))
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    def modify_security_group_rule(self, **kwargs):
        """
        修改安全组规则
        ModifySecurityGroupPolicys:
        Args:
            **kwargs ():
                SecurityGroupId  (str):
                SecurityGroupPolicySet (dict):
        Returns:
        """
        try:
            resp = self.handle_call_request(
                ComponentCategory.VPC, VPCActionCategory.ModifySecurityGroupPolicies, kwargs
            )
        except Exception as e:
            logger.exception("TCE modify security_group_rule error" + str(e))
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    # ——----------------------------- eip --------------------
    def list_eips(self, ids=None, **kwargs):
        """
        获取EIP列表。TCE都是IP v6
        SDK名： DescribeAddresses
        SDK参数：AddressIds Filters Offset Limit
        kwargs:
            查询参数 预留位置
        Returns:

        """
        if ids:
            kwargs["AddressIds"] = convert_param_to_list(ids)
        eip_data, total, status = self._resource_list("eip", kwargs)
        if status:
            data = self.format_resource("eip", eip_data)
            return {"result": True, "data": data, "count": total}
        else:
            return {"result": False, "message": eip_data}

    def create_eip(self, **kwargs):
        """
        接口AllocateAddresses：
        创建弹性公网IP。
        :param kwargs:
                    AddressCount：类型：Integer。描述：EIP数量。默认值：1。 (required)
                    InternetServiceProvider：类型：String。描述：EIP线路类型。默认值：BGP。 (required)
                    InternetChargeType：类型：String。描述：EIP计费方式。    (required)
                            BANDWIDTH_PACKAGE | BANDWIDTH_POSTPAID_BY_HOUR | TRAFFIC_POSTPAID_BY_HOUR
                    InternetMaxBandwidthOut：类型：Integer。描述：EIP出带宽上限，单位：Mbps。 (required)
                    AddressType：类型：String。描述：EIP类型。默认值：EIP。
                    AnycastZone：类型：String。描述：Anycast发布域。
                    BandwidthPackageId：类型：String。描述：BGP带宽包唯一ID参数。
        :return:    data输出示例：
                    {
                      "Response": {
                        "AddressSet": [
                          "eip-m44ku5d2"
                        ],
                        "TaskId": "61531428",
                        "RequestId": "6EF60BEC-0242-43AF-BB20-270359FB54A7"
                      }
                    }
        """
        # params = {
        #     "AddressCount": kwargs["AddressCount"],
        #     "InternetServiceProvider": kwargs["InternetServiceProvider"],
        #     "AddressType": "EIP",
        #     "InternetMaxBandwidthOut": kwargs["InternetMaxBandwidthOut"],
        #     "InternetChargeType": kwargs["InternetChargeType"],
        # }
        charge_type_dict = {
            "POSTPAID_BY_HOUR": "TRAFFIC_POSTPAID_BY_HOUR",
        }
        params = {
            "AddressCount": kwargs.get("AddressCount"),
            "InternetServiceProvider": kwargs.get("InternetServiceProvider"),
            "AddressType": "EIP",
            "InternetMaxBandwidthOut": kwargs["bandwidth_size"],
            "InternetChargeType": charge_type_dict.get(kwargs["charge_type"]),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, VPCActionCategory.AllocateAddresses, params)
        except TceCloudSDKException as e:
            logger.exception("create eip failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.AddressSet[0]}

    def associate_address(self, **kwargs):
        """
        绑定eip
        接口AssociateAddress:
            AddressId (str): eip id
            InstanceId (str): 实例id
            NetworkInterfaceId (str): 要绑定的网卡id，指定这个必须指定内网ip     (optional)
            PrivateIpAddress (str) 要绑定的内网ip     (optional)
        Args:
            **kwargs ():

        Returns:

        """
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, VPCActionCategory.AssociateAddress, kwargs)
        except TceCloudSDKException as e:
            logger.exception("associate eip with vm failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    def disassociate_address(self, **kwargs):
        """
        解绑弹性公网IP（简称 EIP）
        接口：DisassociateAddressRequest
            AddressId （str）:    (required)
            KeepAddressIdBindWithEniPip (bool): (optional)
            ReallocateNormalPublicIp (bool): (optional)
            CascadeRelease (bool): (optional)
        :param kwargs:
                    AddressId：类型：String。必选。描述：标识 EIP 的唯一 ID。
                    ReallocateNormalPublicIp：类型：bool。描述：表示解绑 EIP 之后是否分配普通公网 IP。
        :return:
        """
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, VPCActionCategory.DisassociateAddress, kwargs)
        except TceCloudSDKException as e:
            logger.exception("disassociate eip with vm failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    def release_eip(self, eip_id):
        """
        释放eip
        ReleaseAddressesRequest:
            AddressIds (list of str)
        Args:
            eip_id (list of str):

        Returns:

        """
        params = {"AddressIds": eip_id if isinstance(eip_id, list) else [eip_id]}
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, VPCActionCategory.ReleaseAddresses, params)
        except TceCloudSDKException as e:
            logger.exception("release eip with vm failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    def modify_eip_band_width(self, **kwargs):
        """
        调整带宽
        ModifyAddressesBandwidthRequest:
        Args:
            **kwargs ():
                AddressIds (list of str):
                InternetMaxBandwidthOut (int)
        Returns:

        """
        try:
            resp = self.handle_call_request(ComponentCategory.VPC, VPCActionCategory.ModifyAddressesBandwidth, kwargs)
        except TceCloudSDKException as e:
            logger.exception(u"调整带宽: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    # ------------------- disk(CBS) ----------------------
    def list_disk_types(self, **kwargs):
        """
        Get disk type
        :param
            - disk_charge_type
              type: str(optional)
              value: POSTPAID_BY_HOUR | PREPAID
        """
        params = {"InquiryType": "INQUIRY_CBS_CONFIG"}
        if kwargs.get("disk_charge_type"):
            params["DiskChargeType"] = kwargs["disk_charge_type"]
        try:
            resp = self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.DescribeDiskConfigQuota, params)
        except TceCloudSDKException as e:
            logger.exception("get disk type failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    def get_storage_list(self, **kwargs):
        """
        获取磁盘价格
        DiskType (str): 云硬盘类型。取值范围：<br><li>普通云硬盘：CLOUD_BASIC<br><li>高性能云硬盘：CLOUD_PREMIUM<br><li>SSD云硬盘：CLOUD_SSD。
        DiskSize (int): 云盘大小，取值范围： 普通云硬盘:10GB ~ 4000G；高性能云硬盘:50GB ~ 4000GB；SSD云硬盘:100GB ~ 4000GB，步长均为10GB。
        DiskChargeType (str): 目前只有 PREPAID 预付费
        Returns:

        """
        storage_type = [
            {"name": "普通云硬盘", "type": "CLOUD_BASIC"},
            {"name": "高性能云硬盘", "type": "CLOUD_PREMIUM"},
            {"name": "SSD云硬盘", "type": "CLOUD_SSD"},
        ]
        storage_list = []
        for i in storage_type:
            params = {
                "DiskType": i["type"],
                "DiskSize": 100,
                "DiskChargeType": "PREPAID",
                "DiskChargePrepaid": {"Period": 1},
                "DiskCount": 1,
            }
            resp = self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.InquiryPriceCreateDisks, params)
            storage_list.append(
                {"price": float(resp.DiskPrice.DiscountPrice) / 100, "name": i["name"], "type": i["type"]}
            )
        return {"result": True, "data": storage_list}

    def list_disks(self, ids=None, **kwargs):
        """
        Get disk list.
        ids: 磁盘id列表
        :param ids:
        """
        if ids:
            kwargs["DiskIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list("cbs", kwargs)
        if status:
            return {"result": True, "data": self.format_resource("disk", resp_data), "total": total}
        else:
            return {"result": False, "message": resp_data}

    def create_disk(self, **kwargs):
        """
        Create a disk
        :param placement: disk postition
               type dict(required)
               eg. {
                   "zone": "yfm14-az1",
                   "project_id": 0
               }
        :param disk_type
               type: str(requried)
               value: CLOUD_BASIC(普通云硬盘10GB ~ 4000G) |
                      CLOUD_PREMIUM(高性能云硬盘50GB ~ 4000GB) |
                      CLOUD_SSD(SSD云硬盘100GB ~ 4000) (step 10GB)
        :param disk_charge_type
               type: str(optional)
               default: POSTPAID_BY_HOUR(目前仅支持按小时后付费)
               value: PREPAID(预付费) | POSTPAID_BY_HOUR(按小时后付费)
        :param disk_name
               type: str(optional)
        :param disk_count
               type: int(optional)
               default: 1
        :param disk_size
               type: str(required if don't pass snapshot_id)
        :param snapshot_id
               type: str(optional)
        :param encrypt
               type: str(optional)
               default: ENCRYPT
        :param tags
               type: list(optional)
               eg. [{
                       "key": "test",
                       "value": "demo"
                   }, {
                       "key": "test1",
                       "value": "demo1"
                  }]
        :param shareable
               type: bool(optional)
               default: False
        :param auto_snapshot_policy_id
               type: str(optional)
        :param disk_storage_pool_group
               type: str(optional)
        """
        placement = cbs_models.Placement()
        kwargs["DiskChargeType"] = "POSTPAID_BY_HOUR"
        if kwargs.get("Placement"):
            placement.Zone = kwargs["Placement"].get("zone")
            placement.ProjectId = kwargs["Placement"].get("ProjectId", 0)
        else:
            return {"result": False, "message": u"传入参数缺失placement"}
        if not kwargs.get("DiskType"):
            return {"result": False, "message": u"传入参数缺失disk_type"}
        if not (kwargs.get("DiskSize") or kwargs.get("snapshot_id")):
            return {"result": False, "message": u"传入参数缺失disk_size或snapshot_id"}

        kwargs["Placement"] = placement

        if kwargs.get("Tags") and isinstance(kwargs["Tags"], list):
            tag_list = []
            for cur_tag in kwargs["tags"]:
                tag_obj = cbs_models.Tag()
                tag_obj.Key = cur_tag.get("key")
                tag_obj.Value = cur_tag.get("value")
                tag_list.append(tag_obj)
            kwargs["Tags"] = tag_list
        try:
            resp = self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.CreateDisks, kwargs)
        except TceCloudSDKException as e:
            logger.exception("create disk(s) failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.DiskIdSet}

    def modify_disk_type(self, **kwargs):

        try:
            self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.ModifyDiskAttributes, kwargs)
        except TceCloudSDKException as e:
            logger.exception("modify disk type failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def attach_disk(self, **kwargs):
        """
        Attach disk(s) to a specific vm.
        :param DiskIds
               type: str(required)
        :param InstanceId
               type: str(required)
        """
        try:
            self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.AttachDisks, kwargs)
        except TceCloudSDKException as e:
            logger.exception("attach disk(s)[{}] failed: {}".format(kwargs.get("DiskIds", ""), e))
            return {"result": False, "message": e.message}
        return {"result": True}

    def detach_disk(self, vm_id, disk_id):
        """
        Detach disk(s) from a specific vm.
        :param vm_id: vm instance id.
        :param disk_id: disk id(s).
               type: str or list
        """
        params = {"DiskIds": disk_id if isinstance(disk_id, list) else [disk_id], "InstanceId": vm_id}
        try:
            self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.DetachDisks, params)
        except TceCloudSDKException as e:
            logger.exception("detach disk(s)[{}] failed: {}".format(disk_id, e))
            return {"result": False, "message": e.message}
        return {"result": True}

    def destroy_disk(self, **kwargs):
        """
        Delete disk(s).
        功能备注：退还云硬盘
        :param DiskIds
               type: str or list of str(required)
        """
        try:
            self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.TerminateDisks, kwargs)
        except TceCloudSDKException as e:
            logger.exception("delete disk(s)[{}] failed: {}".format(kwargs.get("DiskIds", ""), e))
            return {"result": False, "message": e.message}
        return {"result": True}

    def resize_disk(self, **kwargs):
        """
        扩容磁盘
        接口参数要求： DiskId(str): '', DiskSize(int): 扩容后的大小，普通:10GB~4000G；高性能:50GB~4000GB；SSD:100GB ~ 4000GB，
                            步长均为10GB
        Args:
            **kwargs ():
                DiskId (str):
                DiskSize (int):
        Returns:

        """
        if not kwargs.get("DiskId"):
            return {"result": False, "message": u"磁盘id不能为空"}
        if not kwargs.get("DiskSize"):
            return {"result": False, "message": u"磁盘新容量不能为空"}
        if not isinstance(kwargs.get("DiskSize"), int):
            return {"result": False, "message": u"磁盘新容量必须为整数"}
        try:
            resp = self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.ResizeDisk, kwargs)
        except Exception as e:
            logger.exception(u"扩容磁盘异常，参数：{},错误信息：{}".format(kwargs, e))
            return {"result": False, "message": str(e)}
        return {"result": True, "data": {"request_id": resp.RequestId}}

    # ---------------------------- monitor 监控 ------------------------------
    def _request_monitor_data(self, namespace, metric, dimension, period, start_time, end_time, statistic=None):
        """
        调用sdk获取监控数据
        接口：GetMonitorDataRequest
        API参数：具体参数取值可以去控制台F12查看
        ----------------------------------------------------------
        'Namespace': 'QCE/CVM',
        'MetricName': 'cpu_usage',
        'Dimensions': [{'unInstanceId': 'ins-mtc97c49'}],
        'Period': 300,
        'StartTime': '2021-06-10T15:14:07+08:00',
        'EndTime': '2021-06-10T15:19:07+08:00'
        ----------------------------------------------------------
        :param Namespace: 命名空间，每个云产品会有一个命名空间 qce/cvm
        :type Namespace: str
        :param MetricName: 指标名称  内存：mem_usage CPU：cpu_usage
        :type MetricName: str
        :param Dimensions: 实例对象的维度组合 ["unInstanceId": "ns-mtc97c49"]
        :type Dimensions: list of str
        :param Period: 监控统计周期。默认为取值为300，单位为s
        :type Period: int
        :param StartTime: 起始时间，如 2018-01-01 00:00:00    例：2021-06-10T13:57:18+08:00
        :type StartTime: str
        :param EndTime: 结束时间，默认为当前时间。 endTime不能小于startTime。  例2021-06-10T14:57:18+08:00
        :type EndTime: str
        :param Statistics: 统计类型
        :type Statistics: str
        -------------------------------------
        Returns  返回Points数据为指标值，根据传入的StartTime、EndTime和Period确定值。都是向下取整，每隔固定时间一次。
                例如 StartTime为13:57:28，
                Period为300时，第一次时间即Point第一个值对应的时间是 13:55:00.  (按5分钟取整，下一次取值时间 14:00:00)
                Period为60，第一个时间为 13:57:00 (1分钟一次，按时间全部取整。下一次取值 13:58:00)
                Period为10，第一次时间为 13:57:20 （10s一次，按10s向下取整。下一次取值 13:57:30）
        -------------------------------------
        {"MetricName": "cpu_usage",
         "StartTime": "2021-06-10 15:00:00",
        "EndTime": "2021-06-10 15:15:00",
        "Period": 300,
        "DataPoints": [{"Dimensions": {"unInstanceId": "ins-mtc97c49"},"Points": [null, 0.7, null, 0.8]}],
        "RequestId": "67b5c109-48db-4c21-a985-d1d16469d4d5"}
        -------

        """
        params = {
            "Namespace": namespace or "qce/cvm",
            "MetricName": metric,
            "Dimensions": dimension,
            # "Dimensions": convert_param_to_list(dimension),
            "Period": period,
            "StartTime": start_time,
            "EndTime": end_time,
            # "Statistics": statistic,
        }
        try:
            res = self.handle_call_request(ComponentCategory.MONITOR, MONITORActionCategory.GetMonitorData, params)
        except Exception as e:
            logger.exception("获取TCE监控数据异常。异常{}".format(e))
            return {"result": False, "message": str(e)}
        return {"result": True, "data": res}

    def describe_base_metrics(self, name_space, metric_name=None):
        """
        调用sdk获取基础指标详情
        接口：DescribeBaseMetrics
        ----------------------------------------------------------
        'Namespace': 'qce/cvm',
        'MetricName': 'cpu_usage',
        ----------------------------------------------------------
        :param Namespace: 命名空间，每个云产品会有一个命名空间 qce/cvm
        :type Namespace: str
        :param MetricName: 指标名称  内存：mem_usage CPU：cpu_usage
        :type MetricName: str
        -------------------------------------
        Returns
        -------------------------------------

        -------
        """
        params = {
            "Namespace": name_space or "qce/cvm",
            "MetricName": metric_name,
        }
        try:
            res = self.handle_call_request(ComponentCategory.MONITOR, MONITORActionCategory.DescribeBaseMetrics, params)
        except Exception as e:
            logger.exception("获取TCE监控数据异常。异常{}".format(e))
            return {"result": False, "message": str(e)}
        return {"result": True, "data": res}

    def get_monitor_data(self, **kwargs):
        """
        获取监控数据 处理参数和组合返回数据。用于外部调用
        Parameters
        ----------
        kwargs

        Returns
        -----------------
        {"ins1": {"cpu_data": [[timestamp1, 0.01], []]}}
        -------

        """
        resource_id = kwargs.get("resourceId", "")
        if not resource_id:
            return {"result": False, "message": "参数错误"}
        resource_id = resource_id.split(",")
        time_format = "%Y-%m-%dT%H:%M:%S+08:00"
        # 接口有问题，时间过长(可能与返回数据数量有关)，会报错['Dimensions * Points <= 1440']
        # start_time = kwargs.get("StartTime")
        start_time = (datetime.datetime.now() + datetime.timedelta(days=-1)).strftime("%Y-%m-%d %H:%M:%S")
        end_time = kwargs.get("EndTime")
        # start_time = ""
        # end_time = ""
        before_five_minutes_time = (datetime.datetime.now() + datetime.timedelta(minutes=-5)).strftime(time_format)
        before_ten_minutes_time = (datetime.datetime.now() + datetime.timedelta(minutes=-10)).strftime(time_format)
        start_time = (
            datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").strftime(time_format)
            if start_time
            else before_ten_minutes_time
        )
        end_time = (
            datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").strftime(time_format)
            if end_time
            else before_five_minutes_time
        )
        namespace = "qce/cvm"
        period = 300
        dimension = [{"unInstanceId": vm_id} for vm_id in convert_param_to_list(resource_id)]
        cpu_metric_name = "cpu_usage"
        memory_metric_name = "mem_usage"

        cpu_result = self._request_monitor_data(namespace, cpu_metric_name, dimension, period, start_time, end_time)
        cpu_monitor_data = cpu_result["data"] if cpu_result["result"] else []
        memory_result = self._request_monitor_data(
            namespace, memory_metric_name, dimension, period, start_time, end_time
        )
        mem_monitor_data = memory_result["data"] if memory_result["result"] else []

        all_cpu_data = self.format_monitor_data(cpu_monitor_data, "cpu")
        all_mem_data = self.format_monitor_data(mem_monitor_data, "memory")
        for k, v in all_cpu_data.items():
            all_mem_data.setdefault(k, v).update(v)
            all_mem_data[k].update({"dick_data": []})
        all_mem_data["result"] = True
        return all_mem_data

    def get_load_monitor_data(self, **kwargs):
        """
        获取监控数据 处理参数和组合返回数据。用于外部调用
        Parameters
        ----------
        kwargs

        Returns
        -----------------
        {"ins1": {"cpu_data": [[timestamp1, 0.01], []]}}
        -------

        """
        resource_id = kwargs["resourceId"]
        if not resource_id:
            return {"result": False, "message": "参数错误"}
        start_time = str(kwargs.get("StartTime", datetime.datetime.now() + datetime.timedelta(minutes=-10)))
        end_time = str(kwargs.get("EndTime", datetime.datetime.now() + datetime.timedelta(minutes=-5)))
        namespace = "qce/cvm"
        period = 300
        vm_lists = []
        for i in range(len(resource_id) // 10 + 1):
            vm_lists.append(resource_id[i * 10 : (i + 1) * 10])
        res = {}
        for vm_list in vm_lists:
            if not vm_list:
                continue
            dimension = [{"unInstanceId": vm_id} for vm_id in convert_param_to_list(vm_list)]
            cpu_metric_name = "cpu_usage"
            memory_metric_name = "mem_usage"
            load_metric_name = "cpu_loadavg"

            cpu_result = self._request_monitor_data(namespace, cpu_metric_name, dimension, period, start_time, end_time)
            cpu_monitor_data = cpu_result["data"] if cpu_result["result"] else []

            memory_result = self._request_monitor_data(
                namespace, memory_metric_name, dimension, period, start_time, end_time
            )
            mem_monitor_data = memory_result["data"] if memory_result["result"] else []

            load_result = self._request_monitor_data(
                namespace, load_metric_name, dimension, period, start_time, end_time
            )
            load_monitor_data = load_result["data"] if load_result["result"] else []

            all_cpu_data = self.format_monitor_data(cpu_monitor_data, "cpu")
            all_mem_data = self.format_monitor_data(mem_monitor_data, "memory")
            all_load_data = self.format_monitor_data(load_monitor_data, "load")
            for k, v in all_cpu_data.items():
                all_mem_data.setdefault(k, v).update(v)
            for k, v in all_load_data.items():
                all_mem_data.setdefault(k, v).update(v)
            for k, v in all_mem_data.items():
                res[k] = v

        return {"result": True, "data": res}

    def _get_monitor_timestamp_list(self, period, start, end):
        """
        根据period获取监控数据的时间戳列表
        Parameters
        ----------
        period (int): 调用监控数据的period参数，间隔时间
        start (str): 起始时间 2021-06-10 15:00:00 。这里是tce端监控数据的第一个时间点
        end (str): 结束时间 2021-06-10 15:05:00

        Returns
        -------
        (list of timestamp)
        """
        start = int(time.mktime(time.strptime(start, "%Y-%m-%d %H:%M:%S")))
        end = int(time.mktime(time.strptime(end, "%Y-%m-%d %H:%M:%S")))
        return [timestamp for timestamp in range(start, end + period, period)]

    def format_monitor_data(self, data, monitor_type):
        """
        格式化monitor数据
        Parameters
        ----------
        data (Object): 监控数据类型对象
        monitor_type (str): 监控数据类型 cpu mem等

        Returns
        -------

        """
        if not data:
            return {}
        return_data = {}
        timestamp_list = self._get_monitor_timestamp_list(data.Period, data.StartTime, data.EndTime)
        data_name = "{}_data".format(monitor_type)
        for monitor in data.DataPoints:
            vm_id = monitor.Dimensions["unInstanceId"]
            point_list = [round(i, 2) for i in monitor.Points if i]
            return_data[vm_id] = {data_name: list(zip(timestamp_list, point_list))}
        return return_data

    # ------------------------- 告警alarm ---------------------
    def get_alarm_data(self, **kwargs):
        """
        调用sdk获取监控数据
        接口：DescribeBasicAlarmList
        API参数：具体参数取值可以去控制台F12查看
        ----------------------------------------------------------
        :param Module: 接口模块名，当前取值monitor
        :type Module: str
        :param StartTime: 起始时间，默认一天前的时间戳
        :type StartTime: int
        :param EndTime: 结束时间，默认当前时间戳
        :type EndTime: int
        :param Limit: 分页参数，每页返回的数量，取值1~100，默认20
        :type Limit: int
        :param Offset: 分页参数，页偏移量，从0开始计数，默认0
        :type Offset: int
        :param OccurTimeOrder: 根据发生时间排序，取值ASC或DESC
        :type OccurTimeOrder: str
        :param ProjectIds: 根据项目ID过滤
        :type ProjectIds: list of int
        :param ViewNames: 根据策略类型过滤
        :type ViewNames: list of str
        :param AlarmStatus: 根据告警状态过滤
        :type AlarmStatus: list of int
        :param ObjLike: 根据告警对象过滤
        :type ObjLike: str
        :param InstanceGroupIds: 根据实例组ID过滤
        :type InstanceGroupIds: list of int
        -------------------------------------
        Returns 返回参数
        :param Alarms: 告警列表
        :type Alarms: list of DescribeBasicAlarmListAlarms
        :param Total: 总数
        :type Total: int
        :param RequestId: 唯一请求 ID，每次请求都会返回。定位问题时需要提供该次请求的 RequestId。
        :type RequestId: str
        -------------------------------------
        {"Response": {
            "Alarms": [
              {
                "AlarmStatus": "OK",
                "AlarmType": "内存使用量",
                "Content": "内存使用量 >  66666 MB",
                "Dimensions": "{\"unInstanceId\":\"ins-19a06nn8\"}",
                "Duration": 600,
                "FirstOccurTime": "2019-11-16T15:50:00+08:00",
                "GroupId": 1278966,
                "GroupName": "dddd",
                "Id": 30057956,
                "InstanceGroup": [
                  {
                    "InstanceGroupId": 562,
                    "InstanceGroupName": "barad_nws_cvm"
                  }
                ],
                "LastOccurTime": "2019-11-16T16:00:00+08:00",
                "MetricId": 24,
                "MetricName": "mem_used",
                "NotifyWay": [
                  "EMAIL",
                  "SMS"
                ],
                "ObjId": "a961c198-e0e2-4989-a3b6-7b155b35ff6f",
                "ObjName": "10.0.0.14(251008737 vm1)",
                "ProjectId": 0,
                "ProjectName": "默认项目",
                "Region": "gz",
                "Status": 1,
                "ViewName": "cvm_device",
                "Vpc": "1"
              }
        }   ]
        -------
        """
        params = {
            "Module": "monitor",
            "StartTime": kwargs.get("start_time", None),
            "EndTime": kwargs.get("end_time", None),
            "Limit": kwargs.get("limit", None),
            "Offset": kwargs.get("offset", None),
            "AlarmStatus": kwargs.get("status", [0]),
        }
        try:
            res = self.handle_call_request(ComponentCategory.ALARM, ALARMActionCategory.DescribeBasicAlarmList, params)
        except Exception as e:
            logger.exception("获取TCE告警数据异常: {}".format(e))
            return {"result": False, "message": str(e)}
        return {"result": True, "data": res}

    # -------------------------image ---------------------
    def list_images(self, ids=None, **kwargs):
        """
        Get image list.
        :param ids
               type: list of str
        """
        if ids:
            kwargs["ImageIds"] = ids
        resp_data, total, status = self._resource_list("image", kwargs)
        if status:
            return {"result": True, "data": self.format_resource("image", resp_data), "total": total}
        else:
            return {"result": False, "message": resp_data}

    # ----------------------------------- snapshot -------------------------
    def list_snapshots(self, ids=None, **kwargs):
        """
        获取快照列表
        SDK: DescribeSnapshotsRequest
        SDK参数： SnapshotIds (list) (optional)
        Args:
            ids (list): 快照id列表

        Returns:

        """
        kwargs["SnapshotIds"] = ids
        snapshot_data, total, status = self._resource_list("snapshot", kwargs)
        if status:
            return {
                "result": True,
                "data": self.format_resource("snapshot", snapshot_data),
                "count": total,
            }
        return {"result": False, "message": snapshot_data}

    def create_snapshot(self, **kwargs):
        """
        创建快照
        SDK: CreateSnapshotRequest
        Args:
            **kwargs ():
                DiskId (str): 磁盘id      (required)
                SnapshotName (str): 快照名     (optional)
        Returns:

        """
        if not kwargs.get("DiskId"):
            return {"result": False, "message": u"磁盘id不能为空"}
        try:
            resp = self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.CreateSnapshot, kwargs)
        except Exception as e:
            logger.exception(u"创建快照异常，{}，参数：{}".format(e, kwargs))
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    def delete_snapshot(self, ids, **kwargs):
        """
        创建快照
        SDK: DeleteSnapshotsRequest
        Args:
            ids (list of str): 待删除id列表
            **kwargs ():
                SnapshotIds (list): 快照id列表
        Returns:

        """
        if not ids:
            return {"result": False, "message": "快照id不能为空"}
        params = {}
        if not isinstance(ids, list):
            params["SnapshotIds"] = [ids]
        params.update(kwargs)
        try:
            resp = self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.DeleteSnapshots, params)
        except Exception as e:
            logger.exception(u"创建快照异常，{}，参数：{}".format(e, kwargs))
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp}

    def snapshot_recovery(self, disk_id, snapshot_id):
        """
        回滚快照
        :param disk_id: 快照原云硬盘ID
        :param snapshot_id: 描述：快照ID
        :return:
        """
        params = {"DiskId": disk_id, "SnapshotId": snapshot_id}
        try:
            resp = self.handle_call_request(ComponentCategory.CBS, CBSActionCategory.ApplySnapshot, params)
        except Exception as e:
            logger.exception(u"回滚快照异常，参数：{},错误信息：{}".format(params, e))
            return {"result": False, "message": str(e)}
        return {"result": True, "data": {"request_id": resp.RequestId}}

    # TODO 词不达意 后面废弃
    def get_local_storage_detail(self, **kwargs):
        return self.list_zones(**kwargs)

    # ------------------- file storage(CFS) ----------------------
    def list_file_systems(self, ids=None, **kwargs):
        """
        Get file systems.
        :param ids
               type: list
        """
        if ids:
            ids = convert_param_to_list(ids) if ids else []
            data, total = self._get_multi_file_system(ids)
            return {"result": True, "data": self.format_resource("file_system", data), "total": total}
        else:
            resp_data, total, status = self._resource_list(ComponentCategory.CFS)
            if status:
                return {
                    "result": True,
                    "data": self.format_resource("file_system", resp_data),
                    "total": total,
                }
            return {"result": False, "message": resp_data}

    def _get_multi_file_system(self, ids):
        """
        批量获取文件系统
        Args:
            ids (list of str):

        Returns:

        """
        data = []
        file_system_total = 0
        params = {}
        for i in ids:
            params["FileSystemId"] = i
            resp_data, total, status = self._resource_list(ComponentCategory.CFS, params)
            if status:
                data.extend(resp_data)
                file_system_total += total
        return data, file_system_total

    def create_file_system(self, **kwargs):
        """
        Create a file system.
        :param fs_name
               type: str(required)
        :param zone_id
               type: str(required)
        :param net_interface
               type: required(required)
               default: VPC
               value: VPC | BASIC
        :param pgroup_id:
               type: str(required)
        :param protocol:
               type: str(optional)
               default: NFS
               value: NFS | CIFS
        :param storage_type
               type: str(optional)
        :param vpc_id
               type: str(optional)
        :param subnet_id
               type: str(optional)
        """
        params = {
            "FsName": kwargs.get("fs_name"),
            "Zone": kwargs.get("zone"),
            # "ZoneId": "50010001",
            "NetInterface": kwargs.get("net_interface", "VPC"),
            "PGroupId": kwargs.get("pgroup_id"),
            "Protocol": kwargs.get("protocol", "NFS"),
            "StorageType": kwargs.get("storage_type", "SD"),
            "VpcId": kwargs.get("vpc"),
            "SubnetId": kwargs.get("subnet"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.CFS, CFSActionCategory.CreateCfsFileSystem, params)
        except TceCloudSDKException as e:
            logger.exception("create file system failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.FileSystemId}

    def delete_file_system(self, fs_id):
        """
        Delete File System.
        """
        params = {"FileSystemId": fs_id}
        try:
            self.handle_call_request(ComponentCategory.CFS, CFSActionCategory.DeleteCfsFileSystem, params)
        except TceCloudSDKException as e:
            logger.exception("delete file system failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def delete_mount_target(self, **kwargs):
        """
        DeleteMountTarget.
        """
        params = {"FileSystemId": kwargs.get("resource_id"), "MountTargetId": kwargs.get("mount_id")}
        try:
            self.handle_call_request(ComponentCategory.CFS, CFSActionCategory.DeleteMountTarget, params)
        except TceCloudSDKException as e:
            logger.exception("删除挂载点失败: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def get_file_system_avail_zones(self):
        """
        Get available zone info from file system.
        """
        try:
            resp = self.handle_call_request(ComponentCategory.CFS, CFSActionCategory.DescribeAvailableZoneInfo, {})
        except TceCloudSDKException as e:
            logger.exception("get file system available zones failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "region_name": region_info.RegionName,
                    "status": region_info.RegionStatus,
                    "region_cn_name": region_info.RegionCnName,
                    "zones": [
                        {
                            "zone_id": zone_info.Zone,
                            "zone_name": zone_info.ZoneEnName,
                            "zone_cn_name": zone_info.ZoneCnName,
                            "ZoneId": zone_info.ZoneId,
                            "types": [
                                {
                                    "type": type_info.Type,
                                    "protocols": [
                                        {"protocol": protocol_info.Protocol, "sale_status": protocol_info.SaleStatus}
                                        for protocol_info in type_info.Protocols
                                    ],
                                }
                                for type_info in zone_info.Types
                            ],
                        }
                        for zone_info in region_info.Zones
                    ],
                }
                for region_info in resp.RegionZones
            ],
        }

    def get_file_system_pgroups(self, international_flag=None):
        """
        Get file system permission group
        :param international_flag
               type: int
               value:
                    1: return data

        """
        params = {}
        if international_flag is not None:
            params["InternationalFlag"] = international_flag
        try:
            resp = self.handle_call_request(ComponentCategory.CFS, CFSActionCategory.DescribeCfsPGroups, params)
        except TceCloudSDKException as e:
            logger.exception("get file system permission groups failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "pg_id": cur_pg.PGroupId,
                    "name": cur_pg.Name,
                    "desc": cur_pg.DescInfo,
                    "date": cur_pg.CDate,
                    "bind_fs_num": cur_pg.BindCfsNum,
                }
                for cur_pg in resp.PGroupList
            ],
        }

    def get_fs_mount_targets(self, fs_id):
        """
        Get file system mount targets.
        功能备注：查询挂载点
        :param fs_id
               type: str(required)
        """
        params = {"FileSystemId": fs_id}
        try:
            resp = self.handle_call_request(ComponentCategory.CFS, CFSActionCategory.DescribeMountTargets, params)
        except TceCloudSDKException as e:
            logger.exception("get file system mount targets %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": {
                "mount_target_num": resp.NumberOfMountTargets,
                "mount_targets": [
                    {
                        "fs_id": cur_mount_target.FileSystemId,
                        "mount_target_id": cur_mount_target.MountTargetId,
                        "ip_address": cur_mount_target.IpAddress,
                        "mount_root_dir": cur_mount_target.FSID,
                        "mount_status": cur_mount_target.LifeCycleState,
                        "net_type": cur_mount_target.NetworkInterface,
                        "vpc_id": cur_mount_target.VpcId,
                        "vpc_name": cur_mount_target.VpcName,
                        "subnet_id": cur_mount_target.SubnetId,
                        "subnet_name": cur_mount_target.SubnetName,
                    }
                    for cur_mount_target in resp.MountTargets
                ],
            },
        }

    def get_fs_clients(self, fs_id):
        """
        Get file system clients.
        :param fs_id
               type: str(required)
        """
        params = {"FileSystemId": fs_id}
        try:
            fs_mount_targets = self.handle_call_request(
                ComponentCategory.CFS, CFSActionCategory.DescribeCfsFileSystemClients, params
            )
        except TceCloudSDKException as e:
            logger.exception("get file system clients %s" % e)
            return {"result": False, "message": e.message}
        return fs_mount_targets

    # ------------------- object storage ----------------------
    def list_buckets(self):
        params = {"CosRegion": self.region_id, "TmpSecretId": self.secret_id, "TmpSecretKey": self.secret_key}
        try:
            resp = self.handle_call_request(ComponentCategory.CSP, CSPActionCategory.GetService, params)
        except TceCloudSDKException as e:
            logger.exception("get buckets failed：%s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": self.format_resource("bucket", resp.Buckets),
            "total": len(resp.Buckets),
        }

    def create_private_bucket(self, **kwargs):
        """
        Create a private bucket
        :param bucket_name
               type: str(required)
        :param acl
               type: str(optional)
               value: 'private'|'public-read'|'public-read-write'
        """
        try:
            self.cos_client.create_bucket(Bucket=kwargs.get("bucket_name"), ACL=kwargs.get("acl"))
        except Exception as e:
            logger.exception("create private bucket failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def delete_private_bucket(self, bucket_name):
        """
        Delete a private bucket
        :param bucket_name
               type: str(required)
        """
        try:
            self.cos_client.delete_bucket(Bucket=bucket_name)
        except Exception as e:
            logger.exception("delete private bucket failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def list_private_bucket_objects(self, bucket_name, prefix=""):
        """
        list all objects from a specific private bucket
        :param bucket_name
               type: str(required)
        :param prefix
               type: str(optional)
        """
        try:
            resp = self.cos_client.list_objects(Bucket=bucket_name, Prefix=prefix)
        except Exception as e:
            logger.exception("list private bucket objects failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": {
                "name": resp["Name"],
                "max_keys": resp["MaxKeys"],
                "prefix": resp["Prefix"],
                "marker": resp["Marker"],
                "encoding_type": resp["EncodingType"],
                "is_truncated": resp["IsTruncated"],
                "contents": [
                    {
                        "last_modified": handle_time_str(content.get("LastModified")),
                        "e_tag": content.get("ETag"),
                        "storage_class": content["StorageClass"],
                        "key": content.get("Key"),
                        "owner": {
                            "display_name": content.get("Owner", {}).get("DisplayName"),
                            "id": content.get("Owner", {}).get("ID"),
                        },
                        "size": content.get("Size"),
                    }
                    for content in resp["Contents"]
                ]
                if resp.get("Contents")
                else [],
            }
            if resp
            else {},
        }

    # ---------------------- tdsql ----------------------------
    def list_tdsqls(self, ids=None, **kwargs):
        """
        保持命名统一
        :param ids:
        :param kwargs:
        :return:
        """
        return self.list_tdsql_instances(ids, **kwargs)

    def create_tdsql(self, **kwargs):
        """
        Create a tdsql instance.
        :param vpc_id: VPC网络ID，形如vpc-qquscup9。
               type: str(required)
        :param subnet_id: VPC网络子网ID，形如subnet-mfhkoln6。
               type: str(required)
        :param shard_memory: 分片内存大小，单位为GB。
               type: int(required)
        :param shard_storage: 分片磁盘大小，单位为GB。
               type: int(required)
        :param shard_node_count: 每个分片的节点个数，值为2或者3。2-一主一从；3-一主两从
               type: int(required)
        :param shard_count: 分片的个数。取值范围为[2, 64]，即最小分片个数为2，最大分片个数为64。
               type: int(required)
        :param zones: 实例可用区信息，只能填一个可用区或者两个可用区。
                      如果只填一个，那么主库和从库可用区一致；如果填两个，
                      那么前一个表示主库可用区，后一个表示从库可用区。
               type: list(required)
        :param db_version_id: 数据库版本。取值为10.0.10，10.1.9，5.7.17或者5.6.39。不填默认为5.7.17。
               type: str(optional)
               values: 10.0.10 | 10.1.9 | 5.7.1 | 5.6.39
               default: 5.7.17
        :param count: 购买数量
               type: int(optional)
        :param shard_cpu: 分片CPU(核)
               type: int(optional)
        :param instance_name: 实例名称
               type: str(optional)
        :param excluster_id: 资源池ID
               type: str(optional)
        """
        params = {
            "VpcId": kwargs.get("vpc"),
            "SubnetId": kwargs.get("subnet"),
            "ShardMemory": kwargs.get("shard_memory"),
            "ShardStorage": kwargs.get("shard_storage"),
            "ShardNodeCount": kwargs.get("shard_node_count"),
            "ShardCount": kwargs.get("shard_count"),
            "Zones": kwargs.get("zones"),
            "DbVersionId": kwargs.get("db_version_id"),
            "Count": kwargs.get("count", 1),
            "ShardCpu": kwargs.get("shard_cpu"),
            "InstanceName": kwargs.get("instance_name"),
            "ExclusterId": kwargs.get("excluster_id"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.CreateHourDCDBInstance, params)
        except TceCloudSDKException as e:
            logger.exception("create tdsql failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.InstanceIds}

    def list_db_params(self, ins_id):
        params = {"InstanceId": ins_id}
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeDBParameters, params)
        except TceCloudSDKException as e:
            logger.exception("get database params failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "default": param.Default,
                    "set_value": param.SetValue,
                    "param": param.Param,
                    "value": param.Value,
                    "constraint": {
                        "range": {
                            "max": param.Constraint.Range.Max,
                            "min": param.Constraint.Range.Min,
                        }
                        if param.Constraint.Range
                        else None,
                        "enum": param.Constraint.Enum,
                        "type": param.Constraint.Type,
                        "string": param.Constraint.String,
                    },
                }
                for param in resp.Params
            ]
            if resp.Params
            else [],
        }

    def modify_db_params(self, ins_id, **kwargs):
        params = {"InstanceId": ins_id, "Params": {"Param": kwargs["param"], "Value": kwargs["value"]}}
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.ModifyDBParameters, params)
        except TceCloudSDKException as e:
            logger.exception("modify db params failed: %s" % e)
            return {"result": False, "message": e.message}
        if resp.Result[0].Code:
            return {"result": False, "message": "修改tdsql参数失败"}
        return {"result": True}

    def init_db_ins(self, ins_id, db_params):
        """
        Init database.
        :param ins_id
               type: str
        :param db_params
               type: list
               eg. [{
                    "param": "auto_increment_increment",
                    "value": "2"
               }]
        """
        if isinstance(ins_id, list):
            ins_ids = ins_id
        else:
            ins_ids = [ins_id]
        if not isinstance(db_params, list):
            return {"result": False, "message": u"非法数据库参数类型[%s]" % str(db_params)}
        Params = []
        for db_param in db_params:
            if db_param.get("param") == "set":
                Params.append({"Param": "character_set_server", "Value": db_param.get("value")})
            elif db_param.get("param") == "case":
                Params.append({"Param": "lower_case_table_names", "Value": 0 if db_param.get("value") else 1})
            elif db_param.get("param") == "synchronize":
                Params.append({"Param": "sync_mode", "Value": 0 if db_param.get("value") == "async" else 2})
            else:
                Params.append({"Param": db_param.get("param"), "Value": db_param.get("value")})
        params = {
            "InstanceIds": ins_ids,
            "Params": Params,
        }
        try:
            self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.InitDCDBInstances, params)
        except TceCloudSDKException as e:
            logger.exception("init database failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def isolate_db_ins(self, ins_id):
        params = {"InstanceId": ins_id}
        try:
            self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.IsolateHourDCDBInstance, params)
        except TceCloudSDKException as e:
            logger.exception("isolate database failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def active_db_ins(self, ins_id):
        params = {"InstanceId": ins_id}
        try:
            self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.ActiveHourDCDBInstance, params)
        except TceCloudSDKException as e:
            logger.exception("active database failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def list_tdsql_instances(self, ids=None, **kwargs):
        """
        Get TDSQL list.
        :param ids:
               type: list of str or str
        """
        params = {}
        if ids:
            params["InstanceIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list(ComponentCategory.DCDB, params)
        if status:
            return {
                "result": True,
                "data": self.format_resource("dcdb", resp_data),
                "total": total,
            }
        else:
            return {"result": False, "message": resp_data}

    def delete_tdsql_instance(self, ins_id):
        """
        Delete TDSQL.
        """
        params = {"InstanceId": ins_id}
        try:
            self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DestroyHourDCDBInstance, params)
        except TceCloudSDKException as e:
            logger.exception("delete tdsql failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def list_tdsql_shards(self, ins_id):
        params = {"InstanceId": ins_id}
        resp_data, total, status = self._resource_list("dcdb_shard", params)
        if status:
            return {"result": True, "data": self.format_resource("dcdb_shard", resp_data), "total": total}
        else:
            return {"result": False, "message": resp_data}

    def list_tdsql_accounts(self, ins_id):
        params = {"InstanceId": ins_id}
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeAccounts, params)
        except TceCloudSDKException as e:
            logger.exception("get tdsql accounts failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "username": user.UserName,
                    "update_time": user.UpdateTime,
                    "desc": user.Description,
                    "host": user.Host,
                    "read_only": user.ReadOnly,
                    "delay_thresh": user.DelayThresh,
                    "created_time": user.CreateTime,
                }
                for user in resp.Users
            ]
            if resp.Users
            else [],
        }

    def create_tdsql_account(self, **kwargs):
        """
        Create a TDSQL account.
        :param ins_id
               type: str(required)
        :param username
               type: str(required)
        :param host
               type: str(required)
               desc: 可以登录的主机，与mysql 账号的 host 格式一致，可以支持通配符。
                     例如 %，10.%，10.20.%。
        :param password
               type: str(required)
        :param read_only
               type: int(optional)
               values: 0 | 1 | 2 | 3
               desc: 是否创建为只读账号
                     0：否，
                     1：该账号的sql请求优先选择备机执行，备机不可用时选择主机执行，
                     2：优先选择备机执行，备机不可用时操作失败，
                     3：只从备机读取。
        :param desc
               type: str(optional)
        :param delay_thresh
               type: int(optional)
               desc: 如果备机延迟超过本参数设置值，系统将认为备机发生故障
                     建议该参数值大于10。当ReadOnly选择1、2时该参数生效。
        """
        params = {
            "InstanceId": kwargs.get("ins_id"),
            "UserName": kwargs.get("username"),
            "Host": kwargs.get("host"),
            "Password": kwargs.get("password"),
            "ReadOnly": kwargs.get("read_only"),
            "Description": kwargs.get("desc"),
            "DelayThresh": kwargs.get("delay_thresh"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.CreateAccount, params)
        except TceCloudSDKException as e:
            logger.exception("create tdsql account failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": {
                "ins_id": resp.InstanceId,
                "username": resp.UserName,
                "host": resp.Host,
                "readonly": resp.ReadOnly,
            },
        }

    def delete_tdsql_account(self, ins_id, username, host):
        """
        Delete a TDSQL account.
        """
        params = {"InstanceId": ins_id, "UserName": username, "Host": host}
        try:
            self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DeleteAccount, params)
        except TceCloudSDKException as e:
            logger.exception("delete tdsql account failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def reset_tdsql_account_passwd(self, **kwargs):
        """
        Reset a TDSQL account password.
        :param ins_id
               type: str(required)
        :param username
               type: str(required)
        :param host
               type: str(required)
               desc: 可以登录的主机，与mysql 账号的 host 格式一致，可以支持通配符。
                     例如 %，10.%，10.20.%。
        :param password
               type: str(required)
        """
        params = {
            "InstanceId": kwargs.get("ins_id"),
            "UserName": kwargs.get("username"),
            "Host": kwargs.get("host"),
            "Password": kwargs.get("password"),
        }
        try:
            self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.ResetAccountPassword, params)
        except TceCloudSDKException as e:
            logger.exception("reset tdsql account password failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def list_tdsql_slow_log_files(self, ins_id, shard_ins_id, log_type=4):
        """
        Get a tdsql shard slow log file list.
        :param ins_id
               type: str(required)
        :param shard_ins_id
               type: str(required)
        :param log_type
               type: int(required)
               desc: 请求日志类型，取值只能为1、2、3或者4。
                     1-binlog，2-冷备，3-errlog，4-slowlog。
        """
        params = {"InstanceId": ins_id, "ShardId": shard_ins_id, "Type": log_type}
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeDBLogFiles, params)
        except TceCloudSDKException as e:
            logger.exception("get tdsql shard slow log files failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "last_modify_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file_obj.Mtime)),
                    "length": file_obj.Length,
                    "uri": file_obj.Uri,
                    "file_name": file_obj.FileName,
                }
                for file_obj in resp.Files
            ]
            if resp.Files
            else [],
        }

    def list_tdsql_slow_logs(self, **kwargs):
        """
        Get a tdsql shard slow log list.
        :param ins_id
               type: str(required)
        :param shard_ins_id
               type: str(required)
        :param offset
               type: int(required)
        :param limit
               type: int(required)
        :param start_time
               type: str(required)
               desc: 查询的起始时间，形如2016-07-23 14:55:20
        :param end_time
               type: str(optional)
               desc: 查询的结束时间，形如2016-08-22 14:55:20。如果不填，那么查询结束时间就是当前时间
        :param db
               type: str(optional)
        :param order_by
               type: str(optional)
               desc: 排序指标，取值为query_time_sum或者query_count。
                     不填默认按照query_time_sum排序
        :param order_by_type
               type: str(optional)
               desc: 排序类型，desc（降序）或者asc（升序）。不填默认desc排序
        :param slave
               type: int(optional)
               desc: 是否查询从机的慢查询，0-主机; 1-从机。不填默认查询主机慢查询
        """
        params = {
            "InstanceId": kwargs.get("ins_id"),
            "ShardId": kwargs.get("shard_ins_id"),
            "Offset": kwargs.get("offset"),
            "Limit": kwargs.get("limit"),
            "StartTime": kwargs.get("start_time"),
            "EndTime": kwargs.get("end_time"),
            "Db": kwargs.get("db"),
            "OrderBy": kwargs.get("order_by"),
            "OrderByType": kwargs.get("order_by_type"),
            "Slave": kwargs.get("slave"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeDBSlowLogs, params)
        except TceCloudSDKException as e:
            logger.exception("get tdsql shard slow log files failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "check_sum": data.CheckSum,
                    "db_name": data.Db,
                    "finger_print": data.FingerPrint,
                    "lock_time_avg": data.LockTimeAvg,
                    "lock_time_max": data.LockTimeMax,
                    "lock_time_min": data.LockTimeMin,
                    "lock_time_sum": data.LockTimeSum,
                    "query_count": data.QueryCount,
                    "query_time_avg": data.QueryTimeAvg,
                    "query_time_max": data.QueryTimeMax,
                    "query_time_min": data.QueryTimeMin,
                    "query_time_sum": data.QueryTimeSum,
                    "rows_examined_sum": data.RowsExaminedSum,
                    "rows_sent_sum": data.RowsSentSum,
                    "ts_max": data.TsMax,
                    "ts_min": data.TsMin,
                    "user": data.User,
                }
                for data in resp.Data
            ]
            if resp.Data
            else [],
            "total": resp.Total,
        }

    def list_tdsql_database(self, ins_id):
        params = {"InstanceId": ins_id}
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeDatabases, params)
        except TceCloudSDKException as e:
            logger.exception("get tdsql databases failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [{"db_name": database.DbName} for database in resp.Databases] if resp.Databases else [],
        }

    def list_shard_specs(self):
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeShardSpec, {})
        except TceCloudSDKException as e:
            logger.exception("get tdsql shard spec list failed: %s" % e)
            return {"result": False, "message": e.message}
        spec_data = resp.SpecConfig
        return {
            "result": True,
            "data": [
                {
                    "pid": spec.Pid,
                    "max_storage": spec.MaxStorage,
                    "suit_info": spec.SuitInfo,
                    "memory": spec.Memory,
                    "node_count": spec.NodeCount,
                    "qps": spec.Qps,
                    "min_storage": spec.MinStorage,
                    "cpu": spec.Cpu,
                }
                for spec_obj in spec_data
                for spec in spec_obj.SpecConfigInfos
            ]
            if spec_data
            else [],
        }

    def list_db_engines(self):
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeDBEngines, {})
        except TceCloudSDKException as e:
            logger.exception("get tdsql engine list failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "version": item_obj.Version,
                    "type": item_obj.Type,
                    "name": item_obj.Name,
                    "description": item_obj.Description,
                }
                for item_obj in resp.Items
            ]
            if resp.Items
            else [],
            "total": resp.TotalCount,
        }

    def list_shard(self, ins_id):
        """
        查询分片信息.
        :param ins_id
               type: str(required)
        """
        params = {"InstanceId": ins_id}
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeDCDBShards, params)
        except TceCloudSDKException as e:
            logger.exception("get tdsql node count failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": {
                "ins_id": resp.Totalcount,
                "shards": resp.Shards,
            },
        }

    def modify_tdsql_shard_spec(self, **kwargs):
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.UpgradeHourDCDBInstance, kwargs)
        except TceCloudSDKException as e:
            logger.exception("get tdsql node count failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": {"ins_id": resp.InstanceId}}

    # ---------------------- mariadb ----------------------------
    def list_mariadbs(self, ids=None, **kwargs):
        """
        仅为了保持统一
        :param ids:
        :param kwargs:
        :return:
        """
        return self.list_mariadb_instances(ids, **kwargs)

    def list_mariadb_instances(self, ids=None, **kwargs):
        """
        Get mariadb instance list.
        :param ids
               type: list of str or str
        """
        params = {}
        if ids:
            params["InstanceIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list(ComponentCategory.MARIADB, params)
        if status:
            return {
                "result": True,
                "data": self.format_resource("mariadb", resp_data),
                "total": total,
            }
        else:
            return {"result": False, "message": resp_data}

    def list_mariadb_engines(self):
        try:
            resp = self.handle_call_request(ComponentCategory.MARIADB, DCDBActionCategory.DescribeDBEngines, {})
        except TceCloudSDKException as e:
            logger.exception("get mariadb engine list failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "version": item_obj.Version,
                    "type": item_obj.Type,
                    "name": item_obj.Name,
                    "description": item_obj.Description,
                }
                for item_obj in resp.Items
            ]
            if resp.Items
            else [],
            "total": resp.TotalCount,
        }

    def upgrade_hour_mariadb_instance(self, **kwargs):
        try:
            self.handle_call_request(ComponentCategory.MARIADB, MARIADBActionCategory.UpgradeHourDBInstance, kwargs)
        except TceCloudSDKException as e:
            logger.exception("upgrade_hour_maria_db_instance failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def list_avail_exclusive_groups(self):
        try:
            resp = self.handle_call_request(
                ComponentCategory.MARIADB, MARIADBActionCategory.DescribeAvailableExclusiveGroups, {}
            )
        except TceCloudSDKException as e:
            logger.exception("list available exclusive groups failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [{"fence_id": item_obj.FenceId} for item_obj in resp.Items] if resp.Items else [],
            "total": resp.TotalCount,
        }

    def isolate_mariadb_instances(self, ins_id):
        """
        isolate MARIADB instance.
        """
        params = {"InstanceId": ins_id}
        try:
            self.handle_call_request(ComponentCategory.MARIADB, MARIADBActionCategory.IsolateHourDBInstance, params)
        except TceCloudSDKException as e:
            logger.exception("isolate mariadb instance failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def delete_mariadb_instance(self, ins_id):
        """
        Delete MARIADB instance.
        """
        params = {"InstanceId": ins_id}
        try:
            self.handle_call_request(ComponentCategory.MARIADB, MARIADBActionCategory.DestroyHourDBInstance, params)
        except TceCloudSDKException as e:
            logger.exception("delete mariadb instance failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def create_mariadb_instance(self, **kwargs):
        """
        Create a mariadb instance.
        :param zones: 实例可用区信息。只可填一个或者两个可用区。
                      如果只填一个，则主库和从库都在该可用区；如果填两个，
                      则主库在第一个可用区，从库在第二个可用区。
               type: list(required)
        :param node_count: 实例节点个数，为2或者3。2表示一主一从；3表示一主两从。
               type: int(required)
        :param vpc_id: VPC网络ID，形如vpc-qquscup9。
               type: str(required)
        :param subnet_id: VPC子网ID，形如subnet-mfhkoln6。
                          type: str(required)
        :param memory: 购买实例内存大小，单位为GB。
                       tyoe: str(required)
        :param storage: 购买实例磁盘大小，单位为GB。
                        type: str(required)
        :param count: 购买实例个数。如果不填，则默认购买一个实例。取值范围为1到10。
                      type: int(optional)
        :param db_version_id: 数据库版本，所填值为10.0.10，10.1.9，5.7.17或者5.6.39。不填的话，默认购买5.7.17版本实例。
                              type: str(optional)
        :param cpu: 购买的CPU大小，单位为核
                    type: int(optional)
        :param excluster_id: 独享集群id
                             type: str(optional)
        :param instance_name: 实例名称
                              type: str(optional)
        """
        params = {
            "Zones": kwargs.get("zones"),
            "NodeCount": kwargs.get("node_count"),
            "VpcId": kwargs.get("vpc_id"),
            "SubnetId": kwargs.get("subnet_id"),
            "Memory": kwargs.get("memory"),
            "Storage": kwargs.get("storage"),
            "Count": kwargs.get("count"),
            "DbVersionId": kwargs.get("db_version_id"),
            "Cpu": kwargs.get("cpu"),
            "ExclusterId": kwargs.get("excluster_id"),
            "InstanceName": kwargs.get("instance_name"),
        }
        try:
            resp = self.handle_call_request(
                ComponentCategory.MARIADB, MARIADBActionCategory.CreateHourDBInstance, params
            )
        except TceCloudSDKException as e:
            logger.exception("create mariadb failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.InstanceIds}

    def list_mariadb_specs(self):
        try:
            resp = self.handle_call_request(
                ComponentCategory.MARIADB, MARIADBActionCategory.DescribeDBInstanceSpecs, {}
            )
        except TceCloudSDKException as e:
            logger.exception("get mariadb spec failed: %s" % e)
            return {"result": False, "message": e.message}
        spec_data = resp.Specs
        return {
            "result": True,
            "data": [
                {
                    "pid": spec.Pid,
                    "machine": spec.Machine,
                    "max_storage": spec.MaxStorage,
                    "suit_info": spec.SuitInfo,
                    "memory": spec.Memory,
                    "node_count": spec.NodeCount,
                    "qps": spec.Qps,
                    "cpu": spec.Cpu,
                    "min_storage": spec.MinStorage,
                }
                for spec_obj in spec_data
                for spec in spec_obj.SpecInfos
            ]
            if spec_data
            else [],
        }

    # ---------------------- redis ----------------------------
    def list_rediss(self, ids=None, **kwargs):
        """
        仅为了保持资源同步方法名的统一
        :param ids:
        :param kwargs:
        :return:
        """
        return self.list_redis_instances(ids=None, **kwargs)

    def list_redis_instances(self, ids=None, **kwargs):
        """
        Get Redis list.
        :param ids
               type: list
        """
        if ids:
            ids = convert_param_to_list(ids) if ids else []
            data, total = self._get_multi_redis_instance(ids)
            return {"result": True, "data": self.format_resource("redis", data), "total": total}
        else:
            resp_data, total, status = self._resource_list(ComponentCategory.REDIS)
            if status:
                return {
                    "result": True,
                    "data": self.format_resource("redis", resp_data),
                    "total": total,
                }
            else:
                return {"result": False, "message": resp_data}

    def _get_multi_redis_instance(self, ids):
        """
        批量获取redis实例
        Args:
            ids (list of str):

        Returns:

        """
        data = []
        ins_total = 0
        params = {}
        for i in ids:
            params["InstanceId"] = i
            resp_data, total, status = self._resource_list(ComponentCategory.REDIS, params)
            if status:
                data.extend(resp_data)
                ins_total += total
        return data, ins_total

    def create_redis(self, **kwargs):
        """
        Create a redis instance.
        :param zone_id: 实例所属的可用区id
               type: str(required)
        :param type_id: 实例类型：2 – Redis2.8主从版，
                                3 – Redis3.2主从版(CKV主从版)，
                                4 – Redis3.2集群版(CKV集群版)，
                                5-Redis2.8单机版，
                                7 – Redis4.0集群版
               type: int(required)
        :param mem_size: 实例容量，单位MB， 取值大小以 查询售卖规格接口返回的规格为准
               type: int(required)
        :param goods_num: 实例数量，单次购买实例数量以 查询售卖规格接口返回的规格为准
               type: int(required)
        :param period: 购买时长，在创建包年包月实例的时候需要填写，按量计费实例填1即可，单位：月
               type: int(required)
               values: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 24 | 36
        :param password: 实例密码，密码规则：1.长度为8-16个字符；2:至少包含字母、数字和字符!@^*()中的两种
               type: str(required)
        :param billing_mode: 付费方式:0-按量计费，1-包年包月。
               type: int(required)
        :param vpc_id: 私有网络ID，如果不传则默认选择基础网络，请使用私有网络列表查询，如：vpc-sad23jfdfk
               type: str(optional)
        :param subnet_id: 基础网络下， subnetId无效； vpc子网下，取值以查询子网列表，如：subnet-fdj24n34j2
               type: str(optional)
        :param project_id: 项目id，取值以用户账户>用户账户相关接口查询>项目列表返回的projectId为准
                           type: int(optional)
        :param auto_renew: 自动续费标识。0 - 默认状态（手动续费）；1 - 自动续费；2 - 明确不自动续费
                           type: int(optional)
        :param sg_id_list: 安全组ID数组
                           type: list(optional)
        :param port: 用户自定义的端口 不填则默认为6379
               type: int(optional)
        :param redis_shard_num: 实例分片数量，Redis2.8主从版、CKV主从版和Redis2.8单机版不需要填写
               type: int(optional)
        :param redis_replicas_num: 实例副本数量，Redis2.8主从版、CKV主从版和Redis2.8单机版不需要填写
               type: int(optional)
        :param replicas_read_only: 是否支持副本只读，Redis2.8主从版、CKV主从版和Redis2.8单机版不需要填写
               type: int(optional)
        :param instance_name: 实例名称
               type: str(optional)
        """
        params = {
            "ZoneId": kwargs.get("zone"),
            "TypeId": kwargs.get("type_id"),
            "MemSize": kwargs.get("mem_size"),
            "GoodsNum": kwargs.get("goods_num"),
            "Period": kwargs.get("period"),
            "Password": kwargs.get("password"),
            "BillingMode": kwargs.get("billing_mode"),
            "VpcId": kwargs.get("vpc"),
            "SubnetId": kwargs.get("subnet"),
            "ProjectId": kwargs.get("project_id"),
            "AutoRenew": kwargs.get("auto_renew"),
            "SecurityGroupIdList": kwargs.get("sg_id_list"),
            "VPort": kwargs.get("port"),
            "RedisShardNum": kwargs.get("redis_shard_num"),
            "RedisReplicasNum": kwargs.get("redis_replicas_num"),
            "ReplicasReadonly": kwargs.get("replicas_read_only"),
            "InstanceName": kwargs.get("instance_name"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.REDIS, RedisActionCategory.CreateInstances, params)
        except TceCloudSDKException as e:
            logger.exception("create redis failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.DealId}

    def reset_redis_password(self, ins_id, password):
        """
        Reset Redis password.
        """
        params = {"InstanceId": ins_id, "Password": password}
        try:
            self.handle_call_request(ComponentCategory.REDIS, RedisActionCategory.ResetPassword, params)
        except TceCloudSDKException as e:
            logger.exception("reset redis password failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def clear_redis_instance(self, ins_id, password):
        """
        clear a specific Redis instance.
        """
        params = {"InstanceId": ins_id, "Password": password}
        try:
            self.handle_call_request(ComponentCategory.REDIS, RedisActionCategory.ClearInstance, params)
        except TceCloudSDKException as e:
            logger.exception("clear redis instance failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def delete_redis_instance(self, ins_id):
        """
        Delete a specific Redis instance.
        功能备注：按量计费实例销毁
        :param ins_id
                type: str(required)
        """
        params = {
            "InstanceId": ins_id,
        }
        try:
            self.handle_call_request(ComponentCategory.REDIS, RedisActionCategory.DestroyPostpaidInstance, params)
        except TceCloudSDKException as e:
            logger.exception("delete redis failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def upgrade_redis_instance(self, **kwargs):
        try:
            self.handle_call_request(ComponentCategory.REDIS, RedisActionCategory.UpgradeInstance, kwargs)
        except TceCloudSDKException as e:
            logger.exception("upgrade redis failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    # ------------------- load balancer -----------------------
    def list_load_balancers(self, ids=None):
        """
        Get Load Balancer list.
        :param ids
               type: list of str or str
        """
        params = {}
        if ids:
            params["LoadBalancerIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list(ComponentCategory.CLB, params)
        if status:
            return {
                "result": True,
                "data": self.format_resource("load_balancer", resp_data),
                "total": total,
            }
        else:
            return {"result": False, "message": resp_data}

    def delete_load_balancer(self, ins_id):
        """
        Delete load_balancer instance(s).
        """
        if isinstance(ins_id, list):
            ins_ids = ins_id
        else:
            ins_ids = [ins_id]
        params = {
            "LoadBalancerIds": ins_ids,
        }
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.DeleteLoadBalancer, params)
        except TceCloudSDKException as e:
            logger.exception("delete load balancer failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def list_lb_listener(self, ins_id):
        params = {
            "LoadBalancerId": ins_id,
        }
        try:
            resp = self.handle_call_request(
                ComponentCategory.CLB, CLBActionCategory.DescribeLoadBalancerListeners, params
            )
        except TceCloudSDKException as e:
            logger.exception("get load balancer listener failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": self.format_resource("clb_listener", resp.Listeners),
        }

    def register_targets_to_listener(self, ins_id, **kwargs):
        """
        绑定后端机器到监听器上.
        """
        params = {
            "LoadBalancerId": ins_id,
            "ListenerId": kwargs.get("listener_id"),
            "Targets": kwargs.get("targets"),
            "LocationId": kwargs.get("location_id"),
            "Domain": kwargs.get("domain"),
            "Url": kwargs.get("url"),
        }
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.RegisterTargets, params)
        except TceCloudSDKException as e:
            logger.exception("register targets to load balancer failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def create_load_balancer(self, **kwargs):
        """
        Create a load balancer instance.
        :param load_balancer_type: 负载均衡实例的网络类型：OPEN：公网属性， INTERNAL：内网属性。
               type: str(required)
               values: OPEN | INTERNAL
        :param forward: 负载均衡实例的类型。1：通用的负载均衡实例，目前只支持传入1
               type: int(optional)
               value: 1
        :param load_balancer_name: 负载均衡实例的名称，只在创建一个实例的时候才会生效。
                                   规则：1-50 个英文、汉字、数字、连接线“-”或下划线“_”。
               type: str(optional)
        :param vpc_id: 负载均衡后端目标设备所属的网络 ID，如vpc-12345678，可以通过 DescribeVpcEx 接口获取。
                       不传此参数则默认为基础网络（"0"）。
               type: str(optional)
        :param subnet_id: 在私有网络内购买内网负载均衡实例的情况下，必须指定子网 ID，内网负载均衡实例的 VIP 将从这个子网中产生。
               type: str(optional)
        :param project_id: 负载均衡实例所属的项目 ID，可以通过 DescribeProject 接口获取。不传此参数则视为默认项目。
               type: int(optional)
        :param address_ip_version: 仅适用于公网负载均衡。IP版本，可取值：IPV4、IPV6、IPv6FullChain，默认值 IPV4。
               type: str(optional)
               value: IPV4 | IPV6 | IPv6FullChain
        :param number: 创建负载均衡的个数，默认值 1。
               type: int(optional)
               default: 1
        :param master_zone_id: 仅适用于公网负载均衡。设置跨可用区容灾时的主可用区ID，例如 100001 或 ap-guangzhou-1
               type: str(optional)
        :param zone_id: 仅适用于公网负载均衡。可用区ID，指定可用区以创建负载均衡实例。如：ap-guangzhou-1
               type: str(optional)
        :param internet_accessible: 仅适用于公网负载均衡。负载均衡的网络计费模式。
               type: object(optional)
        :param vip_isp: 仅适用于公网负载均衡。CMCC &#124; CTCC &#124; CUCC，分别对应 移动 | 电信 | 联通。
                        如果不指定本参数，则默认使用BGP。
               type: str(optional)
        :param tags: 购买负载均衡同时，给负载均衡打上标签
               type: array(optional)
        """
        if kwargs.get("LoadBalancerType") == "OPEN":
            kwargs["AddressIPVersion"] = "IPV4"
        if kwargs.get("tags") and isinstance(kwargs["tags"], list):
            tag_list = []
            for cur_tag in kwargs["tags"]:
                tag_obj = clb_models.TagInfo()
                tag_obj.TagKey = cur_tag.get("key")
                tag_obj.TagValue = cur_tag.get("value")
                tag_list.append(tag_obj)
            kwargs["Tags"] = tag_list
        try:
            res = self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.CreateLoadBalancer, kwargs)
        except TceCloudSDKException as e:
            logger.exception("create load balancer failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": res.LoadBalancerIds}

    def create_load_balancer_listeners(self, **kwargs):
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "listeners.n.loadBalancerPort": kwargs.get("listeners_n_loadBalancerPort"),
            "listeners.n.instancePort": kwargs.get("listeners_n_instancePort "),
            "listeners.n.protocol": kwargs.get("listeners_n_protocol"),
            "listeners.n.listenerName": kwargs.get("listeners_n_listenerName"),
            "listeners.n.sessionExpire": kwargs.get("listeners_n_sessionExpire"),
            "listeners.n.healthSwitch": kwargs.get("listeners_n_healthSwitch"),
            "listeners.n.timeOut": kwargs.get("listeners_n_timeOut"),
            "listeners.n.intervalTime": kwargs.get("listeners_n_intervalTime"),
            "listeners.n.healthNum": kwargs.get("listeners_n_healthNum"),
            "listeners.n.unhealthNum": kwargs.get("listeners_n_unhealthNum"),
            "listeners.n.httpHash": kwargs.get("listeners_n_httpHash"),
            "listeners.n.scheduler": kwargs.get("listeners_n_scheduler"),
            "listeners.n.httpCode": kwargs.get("listeners_n_httpCode"),
            "listeners.n.httpCheckPath": kwargs.get("listeners_n_httpCheckPath"),
            "listeners.n.SSLMode": kwargs.get("listeners_n_SSLMode"),
            "listeners.n.certId": kwargs.get("listeners_n_certId"),
            "listeners.n.certCaId": kwargs.get("listeners_n_certCaId"),
            "listeners.n.certCaContent": kwargs.get("listeners_n_certCaContent"),
            "listeners.n.certCaName": kwargs.get("listeners_n_certCaName"),
            "listeners.n.certContent": kwargs.get("listeners_n_certContent"),
            "listeners.n.certKey": kwargs.get("listeners_n_certKey"),
            "listeners.n.certName": kwargs.get("listeners_n_certName"),
        }
        try:
            res = self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.CreateLoadBalancerListeners, params)
        except TceCloudSDKException as e:
            logger.exception("create load balancer listeners failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": res.listenerIds}

    def delete_load_balancer_listeners(self, **kwargs):
        """
        删除监听器.
        """
        params = {"loadBalancerId": kwargs.get("ins_id"), "listenerId": kwargs.get("listener_id")}
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.DeleteLoadBalancerListeners, params)
        except TceCloudSDKException as e:
            logger.exception("delete load balancer listener failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def modify_load_balancer_listener(self, **kwargs):
        """
        修改监听器属性.
        """
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "listenerId": kwargs.get("listener_id"),
            "listenerName": kwargs.get("listener_name"),
            "sessionExpire": kwargs.get("session_expire"),
            "healthSwitch ": kwargs.get("health_switch"),
            "timeOut ": kwargs.get("time_out"),
            "intervalTime ": kwargs.get("interval_time"),
            "healthNum": kwargs.get("health_num"),
            "unhealthNum": kwargs.get("unhealth_num"),
            "scheduler": kwargs.get("scheduler"),
            "httpHash": kwargs.get("http_hash"),
            "httpCode": kwargs.get("http_code"),
            "httpCheckPath": kwargs.get("http_check_path "),
            "SSLMode": kwargs.get("ssl_mode"),
            "certId": kwargs.get("cert_id"),
            "certCaId": kwargs.get("cert_ca_id"),
            "certCaContent": kwargs.get("cert_ca_content"),
            "certCaName": kwargs.get("cert_ca_name"),
            "certContent": kwargs.get("cert_content"),
            "certKey": kwargs.get("cert_key"),
            "certName": kwargs.get("cert_name"),
        }
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.ModifyLoadBalancerListener, params)
        except TceCloudSDKException as e:
            logger.exception("modify load balancer listener failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def register_instances_with_load_balancer(self, **kwargs):
        """
        修改监听器属性.
        """
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "backends.n.instanceId": kwargs.get("backends.n.instanceId"),
            "backends.n.weight": kwargs.get("backends.n.weight"),
        }
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.RegisterInstancesWithLoadBalancer, params)
        except TceCloudSDKException as e:
            logger.exception("register instances with load balancer failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def modify_load_balancer_backends(self, **kwargs):
        """
        修改负载均衡后端服务器权重.
        """
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "backends.n.instanceId": kwargs.get("backends_n_instanceId"),
            "backends.n.weight": kwargs.get("backends_n_weight"),
        }
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.ModifyLoadBalancerBackends, params)
        except TceCloudSDKException as e:
            logger.exception(" modify load balancer backends failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def deregister_instances_from_load_balancer(self, **kwargs):
        """
        解绑后端服务器.
        """
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "backends.n.instanceId": kwargs.get("backends_n_instanceId"),
        }
        try:
            self.handle_call_request(
                ComponentCategory.CLB, CLBActionCategory.DeregisterInstancesFromLoadBalancer, params
            )
        except TceCloudSDKException as e:
            logger.exception("deregister instances from load balancer failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def modify_load_balancer_attributes(self, **kwargs):
        """
        修改负载均衡属性信息.
        """
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "loadBalancerName": kwargs.get("load_balancer_name"),
            "domainPrefix": kwargs.get("domain_prefix"),
        }
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.ModifyLoadBalancerAttributes, params)
        except TceCloudSDKException as e:
            logger.exception("modify load balancer attributes failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def create_forward_load_balancer_seventh_layer_listeners(self, **kwargs):
        """
        创建应用型负载均衡七层监听器.
        """
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "listeners.n.loadBalancerPort": kwargs.get("listeners_n_loadBalancerPort"),
            "listeners.n.protocol": kwargs.get("listeners_n_protocol"),
            "listeners.n.listenerName": kwargs.get("listeners_n-listenerName"),
            "listeners.n.SSLMode": kwargs.get("listeners_n_SSLMode"),
            "listeners.n.certId": kwargs.get("listeners_n_certId "),
            "listeners.n.certCaId": kwargs.get("listeners_n_certCaId"),
            "listeners.n.certCaContent": kwargs.get("listeners_n_certCaContent "),
            "listeners.n.certCaName": kwargs.get("listeners_n_certCaName"),
            "listeners.n.certContent": kwargs.get("listeners_n_certContent"),
            "listeners.n.certKey": kwargs.get("listeners_n_certKey"),
            "listeners.n.certName": kwargs.get("listeners_n_certName"),
        }

        try:
            self.handle_call_request(
                ComponentCategory.CLB, CLBActionCategory.CreateForwardLBSeventhLayerListeners, params
            )
        except TceCloudSDKException as e:
            logger.exception("create forward load balancer seventh layer listeners failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def modify_forward_lb_rules_domain(self, **kwargs):
        """
        修改七层监听器下的域名.
        """
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "listenerId": kwargs.get("listener_id"),
            "locationIds.n": kwargs.get("locationIds_n"),
            "domain": kwargs.get("domain"),
            "newDomain": kwargs.get("new_domain"),
        }
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.ModifyForwardLBRulesDomain, params)
        except TceCloudSDKException as e:
            logger.exception("modify forward lb rules domain failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def modify_rule(self, **kwargs):
        """
        修改负载均衡七层监听器的转发规则.
        """
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "listenerId": kwargs.get("listener_id"),
            "LocationId ": kwargs.get("location_id"),
            "Url ": kwargs.get("url"),
            "HealthCheck ": kwargs.get("health_check"),
            "Scheduler": kwargs.get("scheduler"),
            "SessionExpireTime": kwargs.get("session_expire_time"),
            "ForwardType": kwargs.get("forward_type"),
            "RequestId": kwargs.get("request_id"),
        }
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.ModifyRule, params)
        except TceCloudSDKException as e:
            logger.exception("modify rules failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def delete_rule(self, **kwargs):
        """
        删除负载均衡七层监听器的转发规则.
        """
        params = {
            "loadBalancerId": kwargs.get("ins_id"),
            "listenerId": kwargs.get("listener_id"),
            "LocationIds": kwargs.get("location_ids"),
            "Url ": kwargs.get("url"),
            "Domain": kwargs.get("domain"),
            "RequestId": kwargs.get("request_id"),
        }
        try:
            self.handle_call_request(ComponentCategory.CLB, CLBActionCategory.DeleteRule, params)
        except TceCloudSDKException as e:
            logger.exception("delete rule failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    # ---------------------- tke ------------------------------

    def list_personal_repository(self, **kwargs):
        """
        List k8s personal repository.
        """
        query_params = {
            "RepoName": kwargs.get("name"),
            "Offset": kwargs.get("offset"),
            "Limit": kwargs.get("limit"),
            "Public": kwargs.get("public"),
            "Namespace": kwargs.get("namespace"),
        }
        try:
            resp = self.handle_call_request(
                ComponentCategory.TCR, TCRActionCategory.DescribeRepositoryFilterPersonal, query_params
            )
        except TceCloudSDKException as e:
            logger.exception("list personal repository failed: %s" % e)
            return {"result": False, "message": e.message}
        repo_info = resp.Data.RepoInfo
        return {
            "result": True,
            "data": [
                {
                    "id": cur_repo.RepoName,
                    "name": cur_repo.RepoName,
                    "repo_type": cur_repo.RepoType,
                    "platform_type": CloudType.TCE.value,
                    "tag_count": cur_repo.TagCount,
                    "public": cur_repo.Public,
                    "is_user_favor": cur_repo.IsUserFavor,
                    "is_qcloud_official": cur_repo.IsQcloudOfficial,
                    "favor_count": cur_repo.FavorCount,
                    "pull_count": cur_repo.PullCount,
                    "description": cur_repo.Description,
                    "created_time": cur_repo.CreationTime,
                    "update_time": cur_repo.UpdateTime,
                    "image_url": resp.Data.Server,
                }
                for cur_repo in repo_info
            ],
            "total": resp.Data.TotalCount,
        }

    def list_tke_images(self):
        """
        List k8s images.
        """
        try:
            resp = self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.DescribeImages, {})
        except TceCloudSDKException as e:
            logger.exception("get TKE image list failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "alias": image.Alias,
                    "os_customize_type": image.OsCustomizeType,
                    "os_name": image.OsName,
                }
                for image in resp.ImageInstanceSet
            ]
            if resp.ImageInstanceSet
            else [],
            "total": resp.TotalCount,
        }

    def list_tke_cluster_services(self, cluster_id, **kwargs):
        """
        List k8s cluster services.
        :param cluster_id: 集群ID
               type: str(required)
        :param namespace: 命名空间
               type: str(optional)
        :param all_namespace: 是否使用所有命名空间
               type: int(optional)
        """
        params = {
            "ClusterId": cluster_id,
            "Namespace": kwargs.get("namespace"),
            "AllNamespace": kwargs.get("all_namespace"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.DescribeClusterServices, params)
        except TceCloudSDKException as e:
            logger.exception("get TKE cluster service list failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "name": service.Name,
                    "status": service.Status,
                    "service_ip": service.ServiceIp,
                    "external_ip": service.ExternalIp,
                    "lb_id": service.LbId,
                    "lb_status": service.LbStatus,
                    "access_type": service.AccessType,
                    "desired_replicas": service.DesiredReplicas,
                    "currentReplicas": service.CurrentReplicas,
                    "created_at": service.CreatedAt,
                    "namespace": service.Namespace,
                }
                for service in resp.Services
            ]
            if resp.Services
            else [],
            "total": resp.TotalCount,
        }

    def list_tke_clusters(self, ids=None):
        """
        Get k8s cluster list.
        :param ids
               type: list of str or str
        """
        params = {}
        if ids:
            params["ClusterIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list(ComponentCategory.TKE, params)
        if status:
            return {
                "result": True,
                "data": self.format_resource("tke", resp_data),
                "total": total,
            }
        else:
            return {"result": False, "message": resp_data}

    def delete_tke_cluster_instance(self, **kwargs):
        """
        Delete k8s instance.
        :param cluster_id: 集群ID
               type: str(required)
        :param instance_ids: 主机InstanceId列表
               type: list(required)
        :param mode: 集群实例删除时的策略：
                        terminate（销毁实例，仅支持按量计费云主机实例）
                        retain （仅移除，保留实例）
                     type: str(optional)
        :param force_delete: 是否强制删除(当节点在初始化时，可以指定参数为TRUE)
               type: boolean(optional)
        """
        params = {
            "ClusterId": kwargs.get("cluster_id"),
            "InstanceIds": kwargs.get("instance_ids"),
            "InstanceDeleteMode": kwargs.get("mode"),
            "ForceDelete": kwargs.get("force_delete"),
        }
        try:
            self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.DeleteClusterInstances, params)
        except TceCloudSDKException as e:
            logger.exception("delete TKE cluster node failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def create_tke_cluster(self, **kwargs):
        """
        Create a k8s cluster.
        :param cluster_cidr_settings: 集群容器网络配置信息
               type: ClusterCIDRSettings(required)
               attrs:
                    - ClusterCIDR: 用于分配集群容器和服务 IP 的 CIDR，不得与 VPC CIDR 冲突，也不得与同 VPC 内其他集群 CIDR 冲突。
                                   且网段范围必须在内网网段内，例如:10.1.0.0/14, 192.168.0.1/18,172.16.0.0/16。
                    - IgnoreClusterCIDRConflict: 是否忽略 ClusterCIDR 冲突错误, 默认不忽略
                    - MaxNodePodNum: 集群中每个Node上最大的Pod数量。取值范围4～256。不为2的幂值时会向上取最接近的2的幂值。
                    - MaxClusterServiceNum: 集群最大的service数量。取值范围32～32768，不为2的幂值时会向上取最接近的2的幂值。
                    - ServiceCIDR: 用于分配集群服务 IP 的 CIDR，不得与 VPC CIDR 冲突，也不得与同 VPC 内其他集群 CIDR 冲突。
                                   且网段范围必须在内网网段内，例如:10.1.0.0/14, 192.168.0.1/18,172.16.0.0/16。
                    - EniSubnetIds: VPC-CNI网络模式下，弹性网卡的子网Id。
                    - ClaimExpiredSeconds: VPC-CNI网络模式下，弹性网卡IP的回收时间，取值范围[300,15768000)
        :param cluster_type: 集群类型，托管集群：MANAGED_CLUSTER，独立集群：INDEPENDENT_CLUSTER。
               type: str(required)
        :param run_instances_for_node: CVM创建透传参数，json化字符串格式，详见CVM创建实例接口。
                                        总机型(包括地域)数量不超过10个，相同机型(地域)购买多台机器可以通过设置
                                        参数中RunInstances中InstanceCount来实现。
               type: list of RunInstancesForNode(optional)
               attrs:
                    NodeRole: 节点角色，取值:MASTER_ETCD, WORKER。
                    RunInstancesPara: CVM创建透传参数，json化字符串格式，详见CVM创建实例接口，传入公共参数外的其他参数即可，
                                      其中ImageId会替换为TKE集群OS对应的镜像。
                    InstanceAdvancedSettingsOverrides: (array)
                        type: list of InstanceAdvancedSettings
                        attrs:
                            - MountTarget: 数据盘挂载点, 默认不挂载数据盘
                            - DockerGraphPath: dockerd --graph 指定值, 默认为 /var/lib/docker
                            - UserScript: base64 编码的用户脚本
                            - Unschedulable: 设置加入的节点是否参与调度，默认值为0，表示参与调度；非0表示不参与调度
                            - Labels: 节点Label数组(list)
                                attrs:
                                     - Name
                                     - Value
                            - DataDisks: 数据盘相关信息(list)
                                attrs:
                                    - DiskType: 云盘类型
                                    - FileSystem: 文件系统(ext3/ext4/xfs)
                                    - DiskSize: 云盘大小(G）
                                    - AutoFormatAndMount: 是否自动化格式盘并挂载
                                    - MountTarget: 挂载目录
                            - ExtraArgs: 节点相关的自定义参数信息
                                attrs:
                                    - Kubelet: kubelet自定义参数
        :param cluster_basic_settings: 集群的基本配置信息
               type: ClusterBasicSettings(optional)
               attrs:
                    - ClusterOs: 集群系统
                    - ClusterVersion: 集群版本,默认值为1.10.5
                    - ClusterName: 集群名称
                    - ClusterDescription: 集群描述
                    - VpcId: 私有网络ID，形如vpc-xxx。创建托管空集群时必传。
                    - ProjectId: 集群内新增资源所属项目ID。
                    - TagSpecification: 标签描述列表。通过指定该参数可以同时绑定标签到相应的资源实例，当前仅支持绑定标签到集群实例。
                        type: list
                        attrs:
                            - ResourceType: 标签绑定的资源类型，当前支持类型："cluster"
                            - Tags: 标签对列表
                                type: list
                                attrs:
                                    - Key: 标签键
                                    - Value: 标签值
                    - OsCustomizeType: 容器的镜像版本，"DOCKER_CUSTOMIZE"(容器定制版),"GENERAL"(普通版本，默认值)
                    - NeedWorkSecurityGroup: 是否开启节点的默认安全组(默认: 否，Aphla特性)
        :param cluster_advance_settings: 集群高级配置信息
               type: ClusterAdvancedSettings(optional)
               attrs:
                    - IPVS: 是否启用IPVS
                    - AsEnabled: 是否启用集群节点自动扩缩容(创建集群流程不支持开启此功能)
                    - ContainerRuntime: 集群使用的runtime类型，包括"docker"和"containerd"两种类型，默认为"docker"
                    - NodeNameType: 集群中节点NodeName类型
                    - ExtraArgs: 集群自定义参数
                    - NetworkType: 集群网络类型（包括GR(全局路由)和VPC-CNI两种模式，默认为GR。
                    - IsNonStaticIpMode: 集群VPC-CNI模式是否为非固定IP，默认: FALSE 固定IP。
        :param instance_advanced_settings: 节点高级配置信息
               type: InstanceAdvancedSettings(optional)
               attrs:
                    - MountTarget: 数据盘挂载点, 默认不挂载数据盘
                    - DockerGraphPath: dockerd --graph 指定值, 默认为 /var/lib/docker
                    - UserScript: base64 编码的用户脚本
                    - Unschedulable: 设置加入的节点是否参与调度，默认值为0，表示参与调度；非0表示不参与调度
                    - Labels: 节点Label数组
                    - DataDisks: 数据盘相关信息
                    - ExtraArgs: 节点相关的自定义参数信息
        :param existed_instances_for_node:  已存在实例的配置信息。所有实例必须在同一个VPC中，最大数量不超过100。
               type: list of ExistedInstancesForNode(optional)
               attrs:
                    - NodeRole: 节点角色，取值:MASTER_ETCD, WORKER。
                    - ExistedInstancesPara: 已存在实例的重装参数
                    - InstanceAdvancedSettingsOverride: 节点高级设置，会覆盖集群级别设置的InstanceAdvancedSettings
        :param instance_data_disk_mount_settings: CVM类型和其对应的数据盘挂载配置信息
               type: list of InstanceDataDiskMountSetting(optional)
               attrs:
                    - InstanceType: CVM实例类型
                    - DataDisks: 数据盘挂载信息
                    - Zone: CVM实例所属可用区
        """
        params = {
            "ClusterCIDRSettings": kwargs.get("cluster_cidr_settings"),
            "ClusterType": kwargs.get("cluster_type"),
            "RunInstancesForNode": kwargs.get("run_instances_for_node"),
            "ClusterBasicSettings": kwargs.get("cluster_basic_settings"),
            "ClusterAdvancedSettings": kwargs.get("cluster_advance_settings"),
            "InstanceAdvancedSettings": kwargs.get("instance_advanced_settings"),
            "ExistedInstancesForNode": kwargs.get("existed_instances_for_node"),
            "InstanceDataDiskMountSettings": kwargs.get("instance_data_disk_mount_settings"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.CreateCluster, params)
        except TceCloudSDKException as e:
            logger.exception("create TKE cluster failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.ClusterId}

    def delete_tke_cluster(self, cluster_id, mode="terminate"):
        """
        Delete a specific k8s cluster.
        :param cluster_id: 集群ID
               type: str(required)
        :param mode: 集群实例删除时的策略：
                        terminate（销毁实例，仅支持按量计费云主机实例）
                        retain （仅移除，保留实例）
                     type: str(required)
                     value: terminate | retain
        """
        params = {"ClusterId": cluster_id, "InstanceDeleteMode": mode}
        try:
            self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.DeleteCluster, params)
        except TceCloudSDKException as e:
            logger.exception("delete TKE cluster failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def modify_cluster_attribute(self, cluster_id, **kwargs):
        """
        修改集群属性  可以修改集群名称和描述
        ---------------------------------
        接口：ModifyClusterAttribute
        参数：
            :param ClusterId: 集群ID
            :type ClusterId: str
            :param ProjectId: 集群所属项目
            :type ProjectId: int
            :param ClusterName: 集群名称
            :type ClusterName: str
            :param ClusterDesc: 集群描述
            :type ClusterDesc: str
        ---------------------------------
        :param cluster_id:
        :param kwargs:
        :return:
        """
        params = {
            "ClusterId": cluster_id,
            "ProjectId": kwargs["project_id"],
            "ClusterName": kwargs.get("name", ""),
            "ClusterDesc": kwargs.get("desc", ""),
        }
        try:
            self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.ModifyClusterAttribute, params)
        except Exception as e:
            logger.exception("修改集群属性失败。异常信息：{}。参数：{}".format(e, params))
            return {"result": False, "message": str(e)}
        return {"result": True, "data": ""}

    def list_tke_cluster_instances(self, cluster_id, **kwargs):
        """
        List all instances from a specific cluster.
        --------------------------------------------
        DescribeClusterInstancesRequest
        --------------------------------------------
        cluster_id (list of str): 集群id

        kwargs:
        :param instance_ids: 需要获取的节点实例ID列表
               type: list(optional)
        :param instance_role: 节点角色, MASTER, WORKER, ETCD, MASTER_ETCD,ALL
               type: str(optional)
               default: WORKER
        """
        params = {
            "ClusterId": cluster_id,
            "InstanceIds": kwargs.get("instance_ids"),
            "InstanceRole": kwargs.get("instance_role"),
        }
        try:
            resp_data, total, status = self._resource_list("tke_ins", params)
        except TceCloudSDKException as e:
            logger.exception("list k8s cluster node list failed: %s" % e)
            return {"result": False, "message": e.message}
        if status:
            return {
                "result": True,
                "data": self.format_resource("tke_instance", resp_data, **{"cluster_id": cluster_id}),
                "total": total,
            }
        else:
            return {"result": False, "message": resp_data}

    def list_tke_existed_instance(self, cluster_id, **kwargs):
        """
        List all instances from a specific cluster.
        --------------------------------------------
        获取tke已存在实例。即tce上符合条件的全部实例。 包括已加入集群和未加入集群的
        接口：DescribeExistedInstances
        参数：
        :param ClusterId: 集群 ID，请填写查询集群列表 接口中返回的 ClusterId 字段（仅通过ClusterId获取需要过滤条件中的VPCID
                        节点状态比较时会使用该地域下所有集群中的节点进行比较。参数不支持同时指定InstanceIds和ClusterId。
        :type ClusterId: str
        :param InstanceIds: 按照一个或者多个实例ID查询。实例ID形如：ins-xxxxxxxx。（此参数的具体格式可参考API简介的id.N一节）。
                        每次请求的实例的上限为100。参数不支持同时指定InstanceIds和Filters。
        :type InstanceIds: list of str
        :param Filters: 过滤条件,字段和详见CVM查询实例如果设置了ClusterId，会附加集群的VPCID作为查询字段，
                        在此情况下如果在Filter中指定了"vpc-id"作为过滤字段，指定的VPCID必须与集群的VPCID相同。
        :type Filters: list of Filter
        :param VagueIpAddress: 实例IP进行过滤(同时支持内网IP和外网IP)
        :type VagueIpAddress: str
        :param VagueInstanceName: 实例名称进行过滤
        :type VagueInstanceName: str
        :param Offset: 偏移量，默认为0。关于Offset的更进一步介绍请参考 API 简介中的相关小节。
        :type Offset: int
        :param Limit: 返回数量，默认为20，最大值为100。关于Limit的更进一步介绍请参考 API 简介中的相关小节。
        :type Limit: int
        --------------------------------------------
        :param cluster_id: 集群ID
               type: str(optional)
        :param offset: 偏移量，默认为0
               type: int(optional)
               default: 0
        :param limit: 返回数量，默认为20，最大值为100
               type: int(optional)
               default: 20
        :param instance_ids: 按照一个或者多个实例ID查询
               type: list(optional)
        :param vague_instance_name: 实例名称进行过滤
               type: str(optional)
        :param vague_ip_addr: 实例IP进行过滤(同时支持内网IP和外网IP)
               type: str(optional)
        """
        params = {
            "ClusterId": cluster_id,
            "Offset": kwargs.get("offset"),
            "Limit": kwargs.get("limit"),
            "InstanceIds": kwargs.get("instance_ids"),
            "VagueInstanceName": kwargs.get("vague_instance_name"),
            "VagueIpAddress": kwargs.get("vague_ip_addr"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.DescribeExistedInstances, params)
        except TceCloudSDKException as e:
            logger.exception("list k8s exists instance list failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": [
                {
                    "usable": exist_ins.Usable,
                    "unusable_reason": exist_ins.UnusableReason,
                    "already_in_cluster": exist_ins.AlreadyInCluster,
                    "instance_id": exist_ins.InstanceId,
                    "instance_name": exist_ins.InstanceName,
                    "private_ip_addresses": exist_ins.PrivateIpAddresses,
                    "public_ip_addresses": exist_ins.PublicIpAddresses,
                    "created_time": handle_time_str(exist_ins.CreatedTime),
                    "instance_charge_type": exist_ins.InstanceChargeType,
                    "cpu": exist_ins.CPU,
                    "memory": exist_ins.Memory,
                    "os_name": exist_ins.OsName,
                    "instance_type": exist_ins.InstanceType,
                }
                for exist_ins in resp.ExistedInstanceSet
            ]
            if resp.ExistedInstanceSet
            else [],
            "total": resp.TotalCount,
        }

    def add_existed_ins_to_tke_cluster(self, **kwargs):
        """
        Add existed instance to cluster.
        :param cluster_id: 集群ID
               type: str(required)
        :param instance_ids: 实例列表
               type: list(required)
        :param instance_advanced_settings: 实例额外需要设置参数信息
               type: InstanceAdvancedSettings(optional)
               attrs:
                    MountTarget
                    DockerGraphPath
                    UserScript
                    Unschedulable
                    Labels: list
                        - Name
                        - Value
                    DataDisks: list
                        - DiskType
                        - FileSystem
                        - DiskSize
                        - AutoFormatAndMount
                        - MountTarget
                    ExtraArgs: object
                        - Kubelet
        :param enhance_service: 增强服务。通过该参数可以指定是否开启云安全、云监控等服务。
                                若不指定该参数，则默认开启云监控、云安全服务。
               type: EnhancedService(optional)
               attrs:
                    SecurityService: object
                        - Enabled
                    MonitorService: object
                        - Enabled
        :param login_settings: 节点登录信息（目前仅支持使用Password或者单个KeyIds
               type: LoginSettings(optional)
               attrs:
                    Password
                    KeyIds
                    KeepImageLogin
        :params security_group_ids: 实例所属安全组。(获取接口DescribeSecurityGroups）
                type: list(optional)
        :params hostname: 重装系统时，可以指定修改实例的HostName
                          (集群为HostName模式时，此参数必传，规则名称除不支持大写字符外与CVM创建实例接口HostName一致)
                type: str(optional)
        """
        params = {
            "ClusterId": kwargs.get("cluster_id"),
            "InstanceIds": kwargs.get("instance_ids"),
            "InstanceAdvancedSettings": kwargs.get("instance_advanced_settings"),
            "EnhancedService": kwargs.get("enhance_service"),
            "LoginSettings": kwargs.get("login_settings"),
            "SecurityGroupIds": kwargs.get("security_group_ids"),
            "HostName": kwargs.get("hostname"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.AddExistedInstances, params)
        except TceCloudSDKException as e:
            logger.exception("add existed instance to cluster service failed: %s" % e)
            return {"result": False, "message": e.message}
        return {
            "result": True,
            "data": {
                "success_instance_ids": resp.SuccInstanceIds,
                "failed_instance_ids": resp.FailedInstanceIds,
                "timeout_instance_ids": resp.TimeoutInstanceIds,
            },
        }

    def drain_cluster_node(self, cluster_id, instance_id, **kwargs):
        """
        驱逐集群节点
        ---------------------------------
        接口：DrainClusterNode
        参数：
            :param ClusterId: 集群ID
            :type ClusterId: str
            :param InstanceId: 实例ID
            :type InstanceId: str
            :param DryRun: 是否只是拉取列表
            :type DryRun: bool
        ---------------------------------
        :param cluster_id (str):
        :param instance_id (str):
        ---------------------------------
        :return:
        """
        params = {
            "ClusterId": cluster_id,
            "InstanceId": instance_id,
            "DryRun": kwargs.get("dry_run"),
        }
        try:
            self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.DrainClusterNode, params)
        except Exception as e:
            logger.exception("驱逐集群节点失败。异常信息：{}。参数：{}".format(e, params))
            return {"result": False, "message": str(e)}
        return {"result": True, "data": ""}

    def check_cluster_cidr(self, vpc, cidr):
        """
        检查cidr.   CheckClusterCIDR
        Parameters
        ----------
        vpc (str): 集群所属vpc的资源id
        cidr (str): 集群的cidr

        Returns
        -------

        """
        params = {
            "VpcId": vpc,
            "ClusterCIDR": cidr,
        }
        try:
            resp = self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.CheckClusterCIDR, params)
        except Exception as e:
            logger.exception("check cidr失败。异常信息：{}。参数：{}".format(e, params))
            return {"result": False, "message": str(e)}
        data = {
            "is_conflict": resp.IsConflict,
            "conflict_type": resp.ConflictType,
            "conflict_msg": resp.ConflictMsg,
        }
        return {"result": True, "data": data}

    def list_cluster_quota(self):
        """
        获取集群配额数据 DescribeQuota
        Parameters
        ----------
        Returns
        -------

        """
        try:
            resp = self.handle_call_request(ComponentCategory.TKE, TKEActionCategory.DescribeQuota, {})
        except Exception as e:
            logger.exception("获取配额数据失败。异常信息：{}。".format(e))
            return {"result": False, "message": str(e)}
        data = {
            "max_cluster_num": resp["data"].MaxClustersNum,
            "MaxNodesNum": resp["data"].MaxNodesNum,
        }
        return {"result": True, "data": data}

    # ********************* mongodb **********************
    def list_mongodbs(self, ids=None, **kwargs):
        """
        Get vm(s).
        :param ids
               type: list of str or str
        """
        params = {}
        if ids:
            params["InstanceIds"] = convert_param_to_list(ids)
        resp_data, total, status = self._resource_list("mongodb", params)
        if status:
            return {
                "result": True,
                "data": self.format_resource("mongodb", resp_data),
                "total": total,
            }
        else:
            return {"result": False, "message": resp_data}

    def list_mongodb_spec_info(self, **kwargs):
        """
        于查询实例的售卖规格。
        :param cluster_id: 集群ID
               type: str(optional)
        :param offset: 偏移量，默认为0
               type: int(optional)
               default: 0
        :param limit: 返回数量，默认为20，最大值为100
               type: int(optional)
               default: 20
        :param instance_ids: 按照一个或者多个实例ID查询
               type: list(optional)
        :param vague_instance_name: 实例名称进行过滤
               type: str(optional)
        :param vague_ip_addr: 实例IP进行过滤(同时支持内网IP和外网IP)
               type: str(optional)
        """
        params = {
            "Zone": kwargs.get("Zone"),
        }
        try:
            resp = self.handle_call_request(ComponentCategory.MONGODB, MongoDBActionCategory.DescribeSpecInfo, params)
        except TceCloudSDKException as e:
            logger.exception("list k8s exists instance list failed: %s" % e)
            return {"result": False, "message": e.message}
        return_data = []
        if resp:
            for i in resp.SpecInfoList[0].SpecItems:
                if i.ClusterType:
                    cluster_type = "SHARD"
                    cluster_type_name = "分片集群"
                else:
                    cluster_type = "REPLSET"
                    cluster_type_name = "副本集集群"
                obj = {
                    "spec_code": i.SpecCode,
                    "cluster_type": cluster_type,
                    "cluster_type_name": cluster_type_name,
                    "cpu": i.Cpu,
                    "memory": int(i.Memory / 1024),
                    "conns": i.Conns,
                    "min_replicate_set_num": i.MinReplicateSetNum,
                    "max_replicate_set_num": i.MaxReplicateSetNum,
                    "min_replicate_set_node_num": i.MinReplicateSetNodeNum,
                    "max_replicate_set_node_num": i.MaxReplicateSetNodeNum,
                    "min_node_num": i.MinNodeNum,
                    "max_node_num": i.MaxNodeNum,
                    "engine_name": i.EngineName,
                    "machine_type": i.MachineType,
                    "mongo_version_code": i.MongoVersionCode,
                    "mongo_version_value": i.MongoVersionValue,
                    "qps": i.Qps,
                    "version": i.Version,
                    "status": i.Status,
                }
                if i.Status and cluster_type == kwargs.get("cluster_type", cluster_type):
                    return_data.append(obj)
        return {"result": True, "data": return_data}

    def delete_mongodb_instance(self, ins_id):
        """
        Delete MongoDB.
        """
        params = {"InstanceId": ins_id}
        try:
            self.handle_call_request(ComponentCategory.MONGODB, MongoDBActionCategory.IsolateDBInstance, params)
        except TceCloudSDKException as e:
            logger.exception("delete tdsql failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def create_mongodb(self, **kwargs):
        """
        创建MongoDB数据库。
        """
        params = {
            "Memory": kwargs.get("shard_memory"),  # 实例内存大小，单位：GB
            "Volume": kwargs.get("shard_storage"),  # 实例硬盘容量大小，单位：GB!!不能低于250G
            "ReplicateSetNum": kwargs.get("shard_count"),  # 副本集个数，创建副本集实例时
            "NodeNum": kwargs.get("node_num"),  # 副本集内节点个数
            "MongoVersion": kwargs.get("mongo_version", "MONGO_36_WT"),  # 副本集内节点个数
            "MachineCode": kwargs.get("machine_num"),  # 机器类型，HIO：高IO型；HIO10G：高IO万兆
            "GoodsNum": 1,
            "Zone": kwargs.get("zones"),
            "ClusterType": kwargs.get("cluster_type"),
            "VpcId": kwargs.get("vpc"),
            "SubnetId": kwargs.get("subnet"),  # 私有网络下的子网ID，如果设置了 VpcId，则 SubnetId必填
            "Password": kwargs.get("password"),  # 实例密码
        }
        try:
            resp = self.handle_call_request(
                ComponentCategory.MONGODB, MongoDBActionCategory.CreateDBInstanceHour, params
            )
        except TceCloudSDKException as e:
            logger.exception("list k8s exists instance list failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": resp.InstanceIds}

    # ************************************************ 裸金属服务器 BMS
    def list_bmss(self, ids=None, **kwargs):
        return self.list_bms_instances(ids, **kwargs)

    def list_bms_instances(self, ids=None, **kwargs):
        """
        获取裸金属服务器列表
        接口：DescribeInstancesRequest
        ——————————————————————
        InstanceIds (list of str): 实例id列表。
        Filters (list of Filters): 筛选条件。和InstanceIds只能存在一个
        Offset (int): 偏移量。可以理解为page
        Limit (int): 返回数量。可以理解为size
        ——————————————————————
        :param ids:
        :param kwargs:
        :return:
        """
        if ids:
            ids = convert_param_to_list(ids)
            kwargs["InstanceIds"] = ids
        bms_data, total, status = self._resource_list("bms", kwargs)
        if status:
            return {
                "result": True,
                "data": self.format_resource("bms", bms_data),
                "count": total,
            }
        return {"result": False, "message": bms_data}

    def get_instance_by_task_id(self, task_ids):
        """
        根据任务id获取实例 sdk文档不齐全，无返回值
        :param task_ids:
        :return:
        """
        try:
            params = {"TaskIds": convert_param_to_list(task_ids)}
            res = self.handle_call_request(ComponentCategory.BMS, BMSActionCategory.GetInstancesByTaskId, params)
        except Exception as e:
            logger.exception("get instance by task_id failed. error_message: {}; params: {}".format(e, task_ids))
            return {"result": False, "message": str(e)}
        # todo 返回数据文档里只有一个RequestId，需要更新准确返回数据
        return {"result": True, "data": res}

    def _set_create_bms_params(self, params):
        """
        格式化创建bms实例的参数
        Parameters
        ----------
        params (dict): 详细内容参照 create_bms_instance

        Returns
        -------

        """
        placement = bms_models.Placement()
        placement.Zone = params.pop("zone")
        login_settings = bms_models.LoginSettings()
        login_settings.Password = params.pop("password")
        if params.get("band_width"):
            # 带宽大于0，如果没有额外设置，会默认开通公网IP
            internet = bms_models.InternetAccessible()
            internet.InternetMaxBandwidthOut = params.pop("band_width")
            params["InternetAccessible"] = internet

        params["Placement"] = placement
        params["LoginSettings"] = login_settings
        params["FlavorId"] = params.pop("flavor")
        params["OperatingSystemType"] = params.pop("os_type")
        params["OperatingSystem"] = params.pop("os")
        params["RaidType"] = params.pop("raid_type")
        params["InstanceCount"] = 1
        params["HostName"] = params.pop("host_name")
        params["InstanceName"] = params.pop("instance_name")
        return params

    def create_bms_instance(self, **kwargs):
        """
        创建bms实例
        接口：RunInstancesRequest
        参数：
        ——————————————————————————————————————————
        Placement (object of Placement):位置信息，Placement对象  (required)

        FlavorId (str): 套餐id  (required)
        OperatingSystemType (str): 系统类型 根据选择的flavor确定  (required)
        OperatingSystem (str): 系统发行版本号  (required)   根据flavor确定
        VirtualPrivateCloud (object of VirtualPrivateCloud): 网络信息，(optional)
        LoginSettings (object of LoginSettings): 登录设置，密码等
            Password (str): 登录密码，linux中8到16位，字母、数字和特殊符号必须有；
                            特殊符号取值[( ) ` ~ ! @ # $ % ^ & * - + = | { } [ ] : ; ' , . ? / ]；
                            windows系统中12~16位，至少包括大小写字母、数字三种以及特殊符号，非必传
        RaidType (str): raid类型 (required)   根据选择的flavor确定
        HostName (str): 主机名 2到15位，.和-不能在首尾
        ClientToken (str): 幂等性字符串
        InternetAccessible (object): 公网带宽信息。默认为0Mb
        InstanceCount (int): 实例数量
        InstanceName (str): 实例显示名称
        TagSpecification (object): 标签描述列表对象
        ——————————————————————————————————————————
        :param kwargs:
        :return:
        """
        params = self._set_create_bms_params(kwargs)
        try:
            res = self.handle_call_request(ComponentCategory.BMS, BMSActionCategory.RunInstances, params)
        except TceCloudSDKException as e:
            logger.exception("create bms failed: %s" % e)
            return {"result": False, "message": e.message}
        task_id = res.TaskId
        return self.get_instance_by_task_id(task_id)

    def start_bms_instance(self, ids=None, **kwargs):
        """
        启动裸金属服务器
        :param kwargs (dict):
            {InstanceIds: []}
        :return:
        """
        return self._operate_instance("Start", self._set_operate_instance_params(ids, kwargs))

    def stop_bms_instance(self, ids=None, **kwargs):
        """
        关闭裸金属实例
        :param kwargs:
        :return:
        """
        return self._operate_instance("Stop", self._set_operate_instance_params(ids, kwargs))

    def terminate_bms_instance(self, ids=None, **kwargs):
        """
        退还实例
        ------------
        接口：TerminateInstances
        参数：
            InstanceIds (list of str):
            ReleaseAddress (bool): 释放弹性公网IP
            DryRun (bool): 试运行
        :param kwargs:
        :return:
        """
        return self._operate_instance("Terminate", self._set_operate_instance_params(ids, kwargs))

    def modify_bms_instance(self, instance_id, name):
        """
        修改裸金属实例的名字
        Parameters
        ----------
        instance_id (str): 待修改的裸金属实例id
        name (str): 实例名

        Returns
        -------

        """
        params = {"InstanceIds": convert_param_to_list(instance_id), "InstanceName": name}
        try:
            self.handle_call_request(ComponentCategory.BMS, BMSActionCategory.ModifyInstancesAttribute, params)
        except Exception as e:
            logger.exception("modify bms instance failed: {}".format(e))
            return {"result": False, "message": e.message}
        return {"result": True, "data": ""}

    def _set_operate_instance_params(self, ids, params):
        """
        处理参数
        :param ids:
        :param params:
        :return:
        """
        if ids:
            ids = convert_param_to_list(ids)
            params.update({"InstanceIds": ids})
        return params

    def _operate_instance(self, action, params):
        """
        操作实例公共方法
        :param action:
        :param params:
        :return:
        """
        try:
            res = self.handle_call_request(
                ComponentCategory.BMS, getattr(BMSActionCategory, "{}Instances".format(action)), params
            )
        except Exception as e:
            logger.exception("{} bms instance failed: {}".format(action, e))
            return {"result": False, "message": e.message}
        return self.get_instance_by_task_id(res.TaskId)

    def list_bms_flavors(self, ids=None, **kwargs):
        """
        获取bms的规格
        :param ids (list of str): 实例规格id列表
        :return:
        """
        if ids:
            ids = convert_param_to_list(ids)
            kwargs["FlavorIds"] = ids
        bms_flavor_data, total, status = self._resource_list("bms_flavor", kwargs)
        if status:
            return {
                "result": True,
                "data": [
                    {
                        "flavor_id": i.FlavorId,
                        "flavor_name": i.FlavorName,
                        "raid_type": i.RaidType,
                        "os": i.OperatingSystem,
                        "cpu": i.Cpu,
                        "memory": i.Memory,
                        "system_disk": i.SystemDisk,
                        "net_speed": i.NetSpeed,
                        "create_time": i.CreatedTime,
                        "is_soldout": i.Soldout,
                    }
                    for i in bms_flavor_data
                ],
                "count": total,
            }
        return {"result": False, "message": bms_flavor_data}

    # **********************************************  kafka

    def list_ckafkas(self, ids=None, **kwargs):
        return self.list_ckafka_instance_detail(ids, **kwargs)

    def list_ckafka_instance(self, ids=None, **kwargs):
        """
        获取kafka实例列表
        -----------------------------
        DescribeInstancesRequest
        InstanceId (str): 按照实例id过滤
        SearchWord (str):按照实例名称过滤，支持模糊查询
        Status (list of int):0：创建中，1：运行中，2：删除中，不填默认返回全部
        -----------------------------
        :param ids:
        :param kwargs:
        :return:
        """
        if ids:
            ids = convert_param_to_list(ids)
            kwargs["InstanceIds"] = ids
        ckafka_data, total, status = self._resource_list("ckafka", kwargs, ["Result", "InstanceList"])
        if status:
            return {
                "result": True,
                "data": [
                    {
                        "resource_id": i.InstanceId,
                        "resource_name": i.InstanceName,
                        "status": i.Status,
                        "if_community": i.IfCommunity,
                    }
                    for i in ckafka_data
                ],
                "count": total,
            }
        return {"result": False, "message": ckafka_data}

    def list_ckafka_instance_detail(self, ids=None, **kwargs):
        """
        获取kafka实例详情
        -----------------------------
        DescribeInstancesRequest
        InstanceId (str): 按照实例id过滤
        SearchWord (str):按照实例名称过滤，支持模糊查询
        Status (list of int):0：创建中，1：运行中，2：删除中，不填默认返回全部
        -----------------------------
        :param ids:
        :param kwargs:
        :return:
        """
        data = []
        if not ids:
            # 取全部ckafka
            res = self.list_ckafka_instance()
            if not res["result"]:
                return {"result": False, "message": res["message"]}
            ids = [i["resource_id"] for i in res["data"]]

        ids = convert_param_to_list(ids)
        for i in ids:
            kwargs["InstanceId"] = i
            try:
                resp = self.handle_call_request(ComponentCategory.CKAFKA, "DescribeInstanceDetail", kwargs)
            except Exception as e:
                logger.exception("根据id：{}获取ckafka实例详情失败。错误信息:{}".format(i, str(e)))
            else:
                data.extend(self.format_resource("ckafka", resp.Result.InstanceList))
        return {"result": True, "data": data}

    def create_ckafka_instance(self, **kwargs):
        """
        创建ckafka实例
        接口：CreateInstanceRequest
        :param InstanceName: 实例名称，是一个不超过 64 个字符的字符串，必须以字母为首字符，剩余部分可以包含字母、数字和横划线(-)
        :type InstanceName: str
        :param BandWidth: 后付费实例带宽
        :type BandWidth: int
        :param Zone: 可用区
        :type Zone: str
        :param VpcId: vpcId，不填默认基础网络
        :type VpcId: str
        :param SubnetId: 子网id，vpc网络需要传该参数，基础网络可以不传
        :type SubnetId: str
        :param PayMode: 付费模式，0表示按需计费/后付费，1表示预付费
        :type PayMode: int
        :param MsgRetentionTime: 后付费实例日志的最长保留时间，单位分钟，默认为10080（7天），最大30天，
                                不填默认0，代表不开启日志保留时间回收策略
        :type MsgRetentionTime: int
        :param Period: 预付费购买时长，后付费类型不用传
        :type Period: str
        :param RenewFlag: 预付费自动续费标记，后付费类型不用传，0表示默认状态(用户未设置，即初始状态)，
                        1表示自动续费，2表示明确不自动续费(用户设置)
        :type RenewFlag: int
        :param VipType: 创建的实例的主路由的类型，4：支撑路由的实例；3：vpc路由的实例。
        :type VipType: int
        :param AccessType: 接入类型，0：PLAINTEXT；1：SASL_PLAINTEXT
        :type AccessType: int
        :param InstanceType: 实例规格，预付费购买必填，1：入门型 ，2： 标准型，3 ：进阶型，4 ：容量型，5： 高阶型1，6：高阶性2, 7：
                            高阶型3,8： 高阶型4， 9 ：独占型。
        :type InstanceType: int

        Parameters
        ----------
        kwargs

        Returns
        -------

        """
        try:
            res = self.handle_call_request(ComponentCategory.CKAFKA, CKAFKAActionCategory.CreateInstance, kwargs)
        except TceCloudSDKException as e:
            logger.exception("create ckafka failed: %s" % e)
            return {"result": False, "message": e.message}
        data = ""
        try:
            data = res.Result.Data.FlowId
        except Exception as e:
            logger.exception("创建ckafka实例后获取返回结果为None，{}".format(e))
        return {"result": True, "data": data}

    def create_topic(self, **kwargs):
        """
        创建topic
        -----------------------------
        CreateTopicRequest
        :param InstanceId: 实例Id
        :type InstanceId: str
        :param TopicName: 主题名称，是一个不超过 64 个字符的字符串，必须以字母为首字符，剩余部分可以包含字母、数字和横划线(-)
        :type TopicName: str
        :param PartitionNum: Partition个数，大于0
        :type PartitionNum: int
        :param ReplicaNum: 副本个数，不能多于 broker 数，最大为3
        :type ReplicaNum: int
        :param EnableWhiteList: ip白名单开关, 1:打开  0:关闭，默认不打开
        :type EnableWhiteList: int
        :param IpWhiteList: Ip白名单列表，配额限制，enableWhileList=1时必选
        :type IpWhiteList: list of str
        :param CleanUpPolicy: 清理日志策略，日志清理模式，默认为"delete"。
                            "delete"：日志按保存时间删除
                            "compact"：日志按 key 压缩
                            "compact, delete"：日志按 key 压缩且会按保存时间删除。
        :type CleanUpPolicy: str
        :param Note: 主题备注，是一个不超过 64 个字符的字符串，必须以字母为首字符，剩余部分可以包含字母、数字和横划线(-)
        :type Note: str
        :param MinInsyncReplicas: 默认为1
        :type MinInsyncReplicas: int
        :param UncleanLeaderElectionEnable: 是否允许未同步的副本选为leader，false:不允许，true:允许，默认不允许
        :type UncleanLeaderElectionEnable: int
        :param RetentionMs: 可消息选。保留时间，单位ms，当前最小值为60000ms
        :type RetentionMs: int
        :param SegmentMs: Segment分片滚动的时长，单位ms，当前最小为3600000ms
        :type SegmentMs: int
        -----------------------------
        :param ids:
        :param kwargs:
        :return:
        """
        try:
            res = self.handle_call_request(ComponentCategory.CKAFKA, CKAFKAActionCategory.CreateTopic, kwargs)
        except TceCloudSDKException as e:
            logger.exception("create ckafka topic failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True, "data": res.Result.TopicId}

    def list_ckafka_consumer_group(self, ids=None, **kwargs):
        """
        获取消费组
        -----------------------------
        DescribeConsumerGroupRequest
        :param InstanceId: ckafka实例id。
        :type InstanceId: str
        :param GroupName: 可选，用户需要查询的group名称。
        :type GroupName: str
        :param TopicName: 可选，用户需要查询的group中的对应的topic名称，如果指定了该参数，而group又未指定则忽略该参数。
        :type TopicName: str
        :param Limit: 本次返回个数限制
        :type Limit: int
        :param Offset: 偏移位置
        :type Offset: int
        -----------------------------
        :param ids:
        :param kwargs:
        :return:
        """
        data = []
        err_list = []
        if ids:
            ids = convert_param_to_list(ids)
            for i in ids:
                kwargs["InstanceId"] = i
                try:
                    resp = self.handle_call_request(ComponentCategory.CKAFKA, "DescribeConsumerGroup", kwargs)
                except Exception as e:
                    logger.exception("根据id：{}获取ckafka实例的消费组失败。错误信息:{}".format(i, str(e)))
                    err_list.append("根据id：{}获取ckafka实例的消费组失败。错误信息:{}".format(i, str(e)))
                else:
                    data.extend(resp.Result.GroupList)
        if err_list:
            return {"result": False, "message": "获取ckafka实例消费组失败，请查看日志"}
        return {"result": True, "data": data}

    def get_virtual_cost(self, **kwargs):
        """
        获取虚拟费用
        :param kwargs:
        :return:
        """
        try:
            zone_list = self.list_zones()["data"]
            return_data = []
            for z in zone_list:
                params = {"Filters": [{"Name": "zone", "Values": [z["resource_id"]]}]}
                ins_list, _, _ = self._resource_list("cvm", params)

                pricemodule, spec_list = get_compute_price_module(
                    "TCE", kwargs["account_name"], self.region_id, z["resource_id"]
                )
                spec_set_list = [s[4] for s in spec_list]
                spec_price_list = [s[3] for s in spec_list]
                for i in ins_list:
                    try:
                        price_disk = 0
                        i = json.loads(i.to_json_string())
                        ins_spec = i["InstanceType"]
                        if ins_spec in spec_set_list:
                            price_vm = spec_price_list[spec_set_list.index(ins_spec)]
                        else:
                            price_vm = 0
                        sys_disk = i["SystemDisk"]
                        data_disk = i.get("DataDisks") if i.get("DataDisks") else []
                        module, storage_list = get_storage_pricemodule(
                            "TCE", kwargs["account_name"], self.region_id, z["resource_id"], sys_disk["DiskType"]
                        )
                        if module:
                            price_disk += float("%.4f" % float(storage_list[2] / 30)) * sys_disk["DiskSize"]
                        else:
                            price_disk += 0
                        for d in data_disk:
                            module, storage_list = get_storage_pricemodule(
                                "TCE", kwargs["account_name"], self.region_id, z["resource_id"], d["DiskType"]
                            )
                            if module:
                                price_disk += float("%.4f" % float(storage_list[2] / 30)) * d["DiskSize"]
                            else:
                                price_disk += 0
                        return_data.append(
                            {
                                "resourceId": i["InstanceId"],
                                "name": i["InstanceName"],
                                "cpu": i["CPU"],
                                "mem": round(i["Memory"] / 1024, 2),
                                "cost_all": round((float(price_vm)), 2) + round((float(price_disk)), 2),
                                "cost_vm": round((float(price_vm)), 2),
                                "cost_disk": round((float(price_disk)), 2),
                                "cost_net": 0.0,
                                "cost_time": datetime.datetime.now().strftime("%Y-%m-%d"),
                                "source_type": CloudResourceType.VM.value,
                            }
                        )
                    except Exception:
                        logger.exception("get {} price error".format(i["InstanceId"]))
                        continue
            return {"result": True, "data": return_data}
        except Exception as e:
            logger.exception("get_virtual_cost")
            return {"result": False, "message": str(e)}

    def delete_ckafka_instance(self, ins_id):
        """
        DeleteInstance
        功能备注：删除ckafka实例
        :param ins_id
                type: str(required)
        """
        params = {
            "InstanceIds": [ins_id],
        }
        try:
            self.handle_call_request(ComponentCategory.CKAFKA, CKAFKAActionCategory.DeleteInstance, params)
        except TceCloudSDKException as e:
            logger.exception("delete redis failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    def modify_ckafka_instance(self, **kwargs):
        try:
            self.handle_call_request(ComponentCategory.CKAFKA, CKAFKAActionCategory.ModifyResourceTce, kwargs)
        except TceCloudSDKException as e:
            logger.exception("modify redis failed: %s" % e)
            return {"result": False, "message": e.message}
        return {"result": True}

    # ************************** 规格 ××××××××××××××××××××××××××××××××
    @staticmethod
    def get_disk_spec():
        """
        获取云硬盘规格 tce直接是枚举
        Returns
        -------

        """
        return {"result": True, "data": [{"label": v, "value": k} for k, v in tce_disk_cn_dict.items()]}

    @staticmethod
    def get_object_storage_spec():
        """
        获取tce对象存储规格  未找到，接口也无法调通
        Returns
        -------

        """
        return {"result": True, "data": [{"label": v, "value": k} for k, v in tce_bucket_cn_dict.items()]}

    def get_mysql_spec(self, region="", zone=""):
        """
        获取mysql可售卖类型  DescribeDBZoneConfig
        Returns
        -------

        """
        try:
            resp = self.handle_call_request(
                ComponentCategory.MARIADB, MARIADBActionCategory.DescribeDBInstanceSpecs, {}
            )
        except TceCloudSDKException as e:
            logger.exception("get mariadb spec failed: %s" % e)
            return {"result": False, "message": e.message}
        spec_data = resp.Specs
        data = [
            {
                "node_count": spec.NodeCount,
                "mem": spec.Memory,
                "cpu": spec.Cpu,
                "remark": spec.SuitInfo,
            }
            for spec_obj in spec_data
            for spec in spec_obj.SpecInfos
        ]
        return {"result": True, "data": data}

    def get_redis_spec(self, region="", zone=""):
        """
        获取redis规格  未找到接口
        Parameters
        ----------
        region
        zone

        Returns
        -------

        """
        try:
            resp = self.handle_call_request(ComponentCategory.REDIS, RedisActionCategory.DescribeProductInfo, {})
        except TceCloudSDKException as e:
            logger.exception("get redis spec failed: %s" % e)
            return {"result": False, "message": e.message}
        # shard_num, shard_size = set(), set()
        data = []
        for region_obj in resp.RegionSet:
            if region and region_obj.RegionId != region:
                continue
            for zone_obj in region_obj.ZoneSet:
                if zone and zone_obj.ZoneId != zone:
                    continue
                for spec in zone_obj.ProductSet:
                    data.append(
                        {
                            "type": spec.Type,
                            "type_name": REDISTYPENAME.get(RedisType(int(spec.Type)).name),
                            "shard_num": spec.ShardNum,
                            "shard_size": spec.ShardSize,
                            "replica_num": spec.ReplicaNum,
                            "enable_repica_readonly": spec.EnableRepicaReadOnly,
                            "engine": spec.Engine,
                            "pay_mode": spec.PayMode,
                            "version": spec.Version,
                        }
                    )
        #             shard_num.update(spec.ShardNum)
        #             shard_size.update(spec.ShardSize)
        # shard_num = [int(i) if "." not in i else float(i) for i in shard_num]
        # shard_size = [int(i) if "." not in i else float(i) for i in shard_size]
        # data = {"shard_num": sorted(shard_num), "shard_size": sorted(shard_size)}
        return {"result": True, "data": data}

    def get_mongodb_spec(self, zone=""):
        """
        获取mongodb规格 会根据账户的区域信息（self.mongodb_client初始化时指定的region），获取指定区域内
        Parameters
        ----------
        region
        zone

        Returns
        -------

        """
        try:
            resp = self.handle_call_request(ComponentCategory.MONGODB, MongoDBActionCategory.DescribeSpecInfo, {})
        except TceCloudSDKException as e:
            logger.exception("get redis spec failed: %s" % e)
            return {"result": False, "message": e.message}
        data = []
        for spec_info in json.loads(resp.to_json_string())["SpecInfoList"]:
            if not zone or (zone and spec_info["Zone"] == zone):
                data = [
                    {
                        "label": "{key}({version})".format(version=item["MongoVersionCode"], key=item["SpecCode"]),
                        "value": item["SpecCode"],
                        "cpu": item["Cpu"],
                        "mem": item["Memory"],
                    }
                    for item in spec_info["SpecItems"]
                ]
        return {"result": True, "data": data}

    def get_tdsql_spec(self):
        """
        获取tdsql规格
        Returns
        -------

        """
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeShardSpec, {})
        except TceCloudSDKException as e:
            logger.exception("get tce tdsql shard spec list failed: %s" % e)
            return {"result": False, "message": e.message}
        spec_data = resp.SpecConfig
        data = [
            {"node_count": spec.NodeCount, "remark": spec.SuitInfo, "cpu": spec.Cpu, "mem": spec.Memory}
            for spec_obj in spec_data
            for spec in spec_obj.SpecConfigInfos
        ]
        return {"result": True, "data": data}

    def describe_dcdb_sale_info(self):
        try:
            resp = self.handle_call_request(ComponentCategory.DCDB, DCDBActionCategory.DescribeDCDBSaleInfo, {})
        except TceCloudSDKException as e:
            logger.exception("get tce tdsql shard spec list failed: %s" % e)
            return {"result": False, "message": e.message}
        region_list = resp.RegionList
        data = [
            {
                "master_zone": {
                    "zone": shard_zone_choose_info.MasterZone.Zone,
                    "zone_name": shard_zone_choose_info.MasterZone.ZoneName,
                },
                "slave_zones": [
                    {"zone": slave_zone.Zone, "zone_name": slave_zone.ZoneName}
                    for slave_zone in shard_zone_choose_info.SlaveZones
                ],
                "region_id": region_info.Region,
                "region_name": region_info.RegionName,
            }
            for region_info in region_list
            for shard_zone_choose_info in region_info.AvailableChoice
        ]
        return {"result": True, "data": data}

    def describe_ckafka_type_configs(self):
        """
        获取ckafka产品规格
        Returns
        """
        try:
            resp = self.handle_call_request(
                ComponentCategory.CKAFKA, CKAFKAActionCategory.DescribeCkafkaTypeConfigs, {}
            )
        except TceCloudSDKException as e:
            logger.exception("describe_ckafka_type_configs failed: %s" % e)
            return {"result": False, "message": e.message}
        data = [
            {
                "bandwidth": config.Bandwidth,
                "desc": config.Desc,
                "disk_size": config.DiskSize,
                "maximum_instance_partition": config.MaximumInstancePartition,
                "maximum_instance_topic": config.MaximumInstanceTopic,
                "pid": config.Pid,
                "type": config.Type,
                "itsm": "{}/{}/{}/{}/{}/{}/{}".format(
                    config.Bandwidth,
                    config.Desc,
                    config.DiskSize,
                    config.MaximumInstancePartition,
                    config.MaximumInstanceTopic,
                    config.Pid,
                    config.Type,
                ),
            }
            for config in resp.Result.InstanceTypeConfigSet
        ]

        return {"result": True, "data": data}

    def describe_sale_info(self):
        """
        查询云数据库可售卖地域和可用区信息
        @return:
        """
        try:
            resp = self.handle_call_request(ComponentCategory.MARIADB, MARIADBActionCategory.DescribeSaleInfo, {})
        except TceCloudSDKException as e:
            logger.exception("describe_sale_info failed: %s" % e)
            return {"result": False, "message": e.message}
        data = [
            {
                "available_choice": [
                    {
                        "master_zone": {
                            "zone": choice.MasterZone.Zone,
                            "zone_id": choice.MasterZone.ZoneId,
                            "zone_name": choice.MasterZone.ZoneName,
                        },
                        "slave_zones": [
                            {
                                "zone": choice_slave_zone.Zone,
                                "zone_id": choice_slave_zone.ZoneId,
                                "zone_name": choice_slave_zone.ZoneName,
                            }
                            for choice_slave_zone in choice.SlaveZones
                        ],
                    }
                    for choice in region.AvailableChoice
                ],
                "region": region.Region,
                "region_id": region.RegionId,
                "region_name": region.RegionName,
                "zone_list": [
                    {
                        "zone": zone.Zone,
                        "zone_id": zone.ZoneId,
                        "zone_name": zone.ZoneName,
                    }
                    for zone in region.ZoneList
                ],
            }
            for region in resp.RegionList
        ]

        return {"result": True, "data": data}

    def get_project_security_groups(self, **kwargs):
        """
        查询项目安全组
        @return:
        """
        try:
            resp = self.handle_call_request(
                ComponentCategory.MARIADB, MARIADBActionCategory.DescribeProjectSecurityGroups, kwargs
            )
        except TceCloudSDKException as e:
            logger.exception("describe_sale_info failed: %s" % e)
            return {"result": False, "message": e.message}

        data = [
            {
                "project_id": group.ProjectId,
                "security_group_id": group.SecurityGroupId,
                "security_group_name": group.SecurityGroupName,
                "security_group_remark": group.SecurityGroupRemark,
                "inbound": [
                    {
                        "action": i.Action,
                        "address_module": i.AddressModule,
                        "cidr_ip": i.CidrIp,
                        "desc": i.Desc,
                        "id": i.Id,
                        "ip_protocol": i.IpProtocol,
                        "port_range": i.PortRange,
                        "service_module": i.ServiceModule,
                    }
                    for i in group.Inbound
                ],
                "outbound": [
                    {
                        "action": i.Action,
                        "address_module": i.AddressModule,
                        "cidr_ip": i.CidrIp,
                        "desc": i.Desc,
                        "id": i.Id,
                        "ip_protocol": i.IpProtocol,
                        "port_range": i.PortRange,
                        "service_module": i.ServiceModule,
                    }
                    for i in group.Outbound
                ],
            }
            for group in resp.Groups
        ]

        return {"result": True, "data": data}

    def update_cfs_file_system_size_limit(self, **kwargs):
        """
        更新文件系统存储容量限制
        """
        try:
            self.handle_call_request(ComponentCategory.CFS, CFSActionCategory.UpdateCfsFileSystemSizeLimit, kwargs)
        except TceCloudSDKException as e:
            logger.exception("update_cfs_file_system_size_limit failed: %s" % e)
            return {"result": False, "message": e.message}

        return {"result": True}

    def modify_ckafka_instance_attributes(self, **kwargs):
        """
        设置ckafka实例属性
        """
        try:
            self.handle_call_request(ComponentCategory.CKAFKA, CKAFKAActionCategory.ModifyInstanceAttributes, kwargs)
        except TceCloudSDKException as e:
            logger.exception("modify_ckafka_instance_attributes failed: %s" % e)
            return {"result": False, "message": e.message}

        return {"result": True}

    def upgrade_maria_db_instance(self, **kwargs):
        """
        更新mariadb实例
        """
        try:
            self.handle_call_request(ComponentCategory.MARIADB, MARIADBActionCategory.UpgradeDBInstance, kwargs)
        except TceCloudSDKException as e:
            logger.exception("upgrade_maria_db_instance failed: %s" % e)
            return {"result": False, "message": e.message}

        return {"result": True}

    def modify_mongodb_instance_spec(self, **kwargs):
        """
        调整云数据库mongodb实例配置
        """
        try:
            self.handle_call_request(ComponentCategory.MONGODB, MongoDBActionCategory.ModifyDBInstanceSpec, kwargs)
        except TceCloudSDKException as e:
            logger.exception("modify_mongodb_instance_spec failed: %s" % e)
            return {"result": False, "message": e.message}

        return {"result": True}

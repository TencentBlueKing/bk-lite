# -*- coding: UTF-8 -*-
import datetime
import json
import ssl

from qcloud_cos import CosConfig, CosS3Client
from QcloudApi.qcloudapi import QcloudApi
from six.moves import range
from tencentcloud.billing.v20180709 import billing_client
from tencentcloud.billing.v20180709 import models as billing_models
from tencentcloud.cbs.v20170312 import cbs_client
from tencentcloud.cbs.v20170312 import models as cbs_models
from tencentcloud.cdb.v20170320 import cdb_client
from tencentcloud.cdb.v20170320 import models as cdb_models
from tencentcloud.clb.v20180317 import clb_client
from tencentcloud.clb.v20180317 import models as clb_models
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.cvm.v20170312 import cvm_client
from tencentcloud.cvm.v20170312 import models as cvm_models
from tencentcloud.dcdb.v20180411 import dcdb_client
from tencentcloud.dcdb.v20180411 import models as dcdb_models
from tencentcloud.mongodb.v20190725 import models as mongodb_models
from tencentcloud.mongodb.v20190725 import mongodb_client
from tencentcloud.monitor.v20180724 import models as monitor_models
from tencentcloud.monitor.v20180724 import monitor_client
from tencentcloud.redis.v20180412 import models as redis_models
from tencentcloud.redis.v20180412 import redis_client
from tencentcloud.tag.v20180813 import models as tag_models
from tencentcloud.tag.v20180813 import tag_client
from tencentcloud.tdmq.v20200217 import models as tdmq_models
from tencentcloud.tdmq.v20200217 import tdmq_client
from tencentcloud.tke.v20180525 import models as tke_models
from tencentcloud.tke.v20180525 import tke_client
from tencentcloud.vpc.v20170312 import models as vpc_models
from tencentcloud.vpc.v20170312 import vpc_client

from common.cmp.cloud_apis.constant import CloudType
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.cloud_apis.resource_apis.resource_format.qcloud.qcloud_constant import (
    qcloud_bucket_cn_dict,
    qcloud_disk_cn_dict,
)
from common.cmp.cloud_apis.resource_apis.utils import handle_disk_category
from common.cmp.driver import logger
from common.cmp.utils import (
    convert_param_to_list,
    format_public_cloud_resource_type,
    generate_serial_number,
    set_dir_size_qcloud,
)

RESOURCE_HANDLE_DICT = {
    "region": {"request": "DescribeRegions", "resp": "RegionSet"},
    "zone": {"request": "DescribeZones", "resp": "ZoneSet"},
    "instance_type_family": {"request": "DescribeInstanceFamilyConfigs", "resp": "InstanceFamilyConfigSet"},
    "instance_type": {
        "request": "DescribeInstanceTypeConfigs",
        "resp": "InstanceTypeConfigSet",
    },
    "vm": {
        "request": "DescribeInstances",
        "resp": "InstanceSet",
    },
    "disk": {
        "request": "DescribeDisks",
        "resp": "DiskSet",
    },
    "image": {
        "request": "DescribeImages",
        "resp": "ImageSet",
    },
    "snapshot": {
        "request": "DescribeSnapshots",
        "resp": "SnapshotSet",
    },
    "auto_snapshot_policy": {
        "request": "DescribeAutoSnapshotPolicies",
        "resp": "AutoSnapshotPolicySet",
    },
    "vpc": {
        "request": "DescribeVpcs",
        "resp": "VpcSet",
    },
    "subnet": {
        "request": "DescribeSubnets",
        "resp": "SubnetSet",
    },
    "eip": {
        "request": "DescribeAddresses",
        "resp": "AddressSet",
    },
    "security_group": {
        "request": "DescribeSecurityGroups",
        "resp": "SecurityGroupSet",
    },
    "security_group_rule": {
        "request": "DescribeSecurityGroupPolicies",
        "resp": "SecurityGroupPolicySet",
    },
    "bucket": {
        "request": "DescribeInstanceTypeConfigs",
        "resp": "InstanceTypeConfigSet",
    },
    "balance": {
        "request": "DescribeAccountBalance",
        "resp": "null",
    },
    "transactions": {
        "request": "DescribeBillList",
        "resp": "TransactionList",
    },
    "tag": {
        "request": "DescribeResourceTags",
        "resp": "Rows",
    },
    "load_balancer": {
        "request": "DescribeLoadBalancers",
        "resp": "LoadBalancerSet",
    },
    "route_table": {
        "request": "DescribeRouteTables",
        "resp": "RouteTableSet",
    },
    "cdb_mysql": {
        "request": "DescribeDBInstances",
        "resp": "Items",
    },
    "rocketmq_cluster": {
        "request": "DescribeRocketMQClusters",
        "resp": "ClusterList",
    },
    "tke_serverless_cluster": {
        "request": "DescribeEKSClusters",
        "resp": "Clusters",
    },
}


class CwQcloud(object):
    """
    腾讯云组件类,通过该类创建腾讯云的Client实例，调用腾讯云api接口
    """

    def __init__(self, secret_id, secret_key, region_id, host="", **kwargs):
        """
         初始化方法，创建Client实例。在创建Client实例时，您需要获取Region ID、AccessKey ID和AccessKey Secret
        :param secret_id:
        :param secret_key:
        :param region_id:
        :param kwargs:
        """
        self.secretId = secret_id
        self.secretKey = secret_key
        self.region_id = "ap-guangzhou" if not region_id else region_id
        for k, v in kwargs.items():
            setattr(self, k, v)
        ssl._create_default_https_context = ssl._create_unverified_context
        self.cred = credential.Credential(self.secretId, self.secretKey)
        config = CosConfig(Region=self.region_id, SecretId=self.secretId, SecretKey=self.secretKey)
        self.cosS3_client = CosS3Client(config)

    def __getattr__(self, item):
        """
        private方法，返回对应的腾讯云接口类
        :param item:
        :return:
        """
        return Qcloud(cred=self.cred, name=item, region_id=self.region_id, cosS3_client=self.cosS3_client)


class Qcloud(object):
    """
    腾讯云接口类。使用腾讯云开发者工具套件（SDK），并进行封装，访问腾讯云服务
    """

    BK_OBJ_ID_NS_MAP = {
        "qcloud_cvm": "QCE/CVM",
        "qcloud_mysql": "QCE/CDB",
        "qcloud_rocketmq": "QCE/ROCKETMQ",
        "qcloud_serverless": "QCE/TKE2",
    }
    RENAME_METRIC = {
        "qcloud_cvm": {"CPUUsage": "CpuUseRate", "MemUsage": "MemoryUseRate", "CvmDiskUsage": "VolumeRate"}
    }
    RENAME_METRIC_REVERT = {
        "qcloud_cvm": {"CpuUseRate": "CPUUsage", "MemoryUseRate": "MemUsage", "VolumeRate": "CvmDiskUsage"}
    }
    BK_OBJ_ID_METRICS = {
        "qcloud_cvm": [
            "CPUUsage",
            "MemUsed",
            "MemUsage",
            "CvmDiskUsage",
            "LanOuttraffic",
            "LanIntraffic",
            "LanOutpkg",
            "LanInpkg",
            "WanOuttraffic",
            "WanIntraffic",
            "WanOutpkg",
            "WanInpkg",
            "Outratio",
        ],
        "qcloud_mysql": [
            "CpuUseRate",
            "MemoryUseRate",
            "MemoryUse",
            "VolumeRate",
            "RealCapacity",
            "Capacity",
            "IOPS",
            "IopsUseRate",
            "BytesSent",
            "BytesReceived",
            "MaxConnections",
            "ThreadsConnected",
            "ConnectionUseRate",
            "InnodbCacheHitRate",
            "InnodbCacheUseRate",
            "SlowQueries",
            "SelectCount",
            "CreatedTmpTables",
            "TableLocksWaited",
            "KeyCacheHitRate",
            "KeyCacheUseRate",
            "ThreadsCreated",
            "ThreadsRunning",
            "ThreadsCreated",
            "ThreadsRunning",
        ],
        "qcloud_rocketmq": [
            # "RopRateIn",
            # "RopRateOut",
            # "RopThroughputIn",
            # "RopThroughputOut",
            # "RopMsgBacklog",
            # "RopMsgAverageSize",
            # "RopInMessageTotal",
            # "RopGroupCount",
            "RocketmqTenantProduceMessageSize",
            "RocketmqTenantProducerTps",
            "RocketmqTenantConsumerMessageSize",
            "RocketmqTenantConsumerTps",
            "RocketmqTenantDiff",
            "RocketmqTenantNumberOfSendLimit",
            "RocketmqTenantNumberOfPullApiCalls",
            "RocketmqTenantNumberOfSendApiCalls",
        ],
        "qcloud_serverless": [
            "K8sClusterPodsUsedTotal",
            "K8sClusterEksCpuCoreUsed",
            "K8sClusterEksMemNoCacheBytes",
            "K8sClusterEksMemUsageBytes",
            "K8sClusterEksNetworkTransmitBytesBw",
        ],
    }

    def __init__(self, cred, name, region_id, cosS3_client):
        """
        初始化方法
        :param cred:
        :param name:
        :param region_id:
        """
        self.cred = cred
        self.name = name
        self.region_id = region_id
        self.cosS3_client = cosS3_client
        self.cloud_type = CloudType.QClOUD.value

        self.cvm_client = cvm_client.CvmClient(self.cred, self.region_id)
        self.monitor_client = monitor_client.MonitorClient(self.cred, self.region_id)
        self.billing_client = billing_client.BillingClient(self.cred, self.region_id)
        self.cbs_client = cbs_client.CbsClient(self.cred, self.region_id)
        self.vpc_client = vpc_client.VpcClient(self.cred, self.region_id)
        self.tag_client = tag_client.TagClient(self.cred, self.region_id)
        self.cdb_client = cdb_client.CdbClient(self.cred, self.region_id)
        self.tdmq_client = tdmq_client.TdmqClient(self.cred, self.region_id)
        self.tke_client = tke_client.TkeClient(self.cred, self.region_id)
        self.redis_client = redis_client.RedisClient(self.cred, self.region_id)
        self.mongodb_client = mongodb_client.MongodbClient(self.cred, self.region_id)
        self.dcdb_client = dcdb_client.DcdbClient(self.cred, self.region_id)
        self.clb_client = clb_client.ClbClient(self.cred, self.region_id)

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    # ************************* common
    def _handle_list_request(self, client_type, request, resource, is_page=False, format=True, **kwargs):
        """
        获取资源接口统一请求方法
        Args:
            client_type (str): client名，对应__init__方法里的定义
            request (): request
            resource (str): 资源名 region
            is_page (bool): 是否分页标记
            **kwargs (dict): 额外参数
        Returns:

        """
        if not hasattr(self, client_type):
            raise Exception("腾讯云请求数据{}时传入client{}错误，请检查".format(resource, client_type))

        client = getattr(self, client_type)
        try:
            if is_page:
                result = self.__get_page_result(client, request, resource)
            else:
                resp = getattr(client, RESOURCE_HANDLE_DICT[resource]["request"])(request)
                result = getattr(resp, RESOURCE_HANDLE_DICT[resource]["resp"], resp)
        except Exception as e:
            logger.exception("腾讯云调用获取{}资源接口失败。{}".format(resource, e))
            return {"result": False, "message": str(e)}
        if format:
            result = self.__parse_result(result, resource, **kwargs)
        else:
            result = [json.loads(i.to_json_string()) for i in result]
        return {"result": True, "data": result}

    def __parse_result(self, result, resource, **kwargs):
        """
        格式化资源数据
        Args:
            result (list or object):
            resource (str): 资源名 region
        Returns:

        """
        format_method = get_format_method(self.cloud_type, resource, region_id=self.region_id)
        if isinstance(result, list):
            return [format_method(i, **kwargs) for i in result]
        try:
            data = format_method(result, **kwargs)
        except Exception as e:
            logger.exception("格式化资源{}结果失败.{}".format(resource, e))
            return []
        return data

    @staticmethod
    def __get_page_result(client, request, resource):
        """
        获取分页数据
        Args:
            client (): client，对应__init__方法里的定义
            request (): request
            resource (str): 资源名 region

        Returns:

        """
        request.Limit = 50
        request.Offset = 0
        resp = getattr(client, RESOURCE_HANDLE_DICT[resource]["request"])(request)

        data = getattr(resp, RESOURCE_HANDLE_DICT[resource]["resp"])
        if hasattr(resp, "TotalCount"):
            total_count = resp.TotalCount
        elif hasattr(resp, "Total"):
            total_count = resp.Total
        else:
            # 无数据总条数 无法分页 直接返回当次结果
            return data
        page = total_count // 50 if total_count % 50 == 0 else total_count // 50 + 1
        for i in range(page):
            offset = (i + 1) * 50
            request.Offset = offset
            response = getattr(client, RESOURCE_HANDLE_DICT[resource]["request"])(request)
            data.extend(getattr(response, RESOURCE_HANDLE_DICT[resource]["resp"]))
        return data

    def list_regions(self):
        """
        获取腾讯云地域信息
        :return:
        """
        req = cvm_models.DescribeRegionsRequest()
        return self._handle_list_request("cvm_client", req, "region")

    def list_zones(self, **kwargs):
        """
        获取腾讯云可用区信息
        :return:
        """
        req = cvm_models.DescribeZonesRequest()
        return self._handle_list_request("cvm_client", req, "zone")

    def get_connection_result(self):
        """
         根据能否获取地域信息判断是否连接成功
        :return:
        """
        connection_result = self.list_zones()
        if connection_result["result"]:
            return {"result": True}
        else:
            return {"result": False}

    # todo 鉴别方法作用 是否去除，包括下边几个
    def get_spec_type(self, **kwargs):
        client = self.cvm_client
        model = cvm_models
        req = model.DescribeInstanceTypeConfigsRequest()
        filter = model.Filter()
        filter.Name = "zone"
        filter.Values = [kwargs["zone"]]
        req._Filters = [filter]
        resp = client.DescribeInstanceTypeConfigs(req)
        return_data = []
        type_list = []
        for i in resp.InstanceTypeConfigSet:
            if i.InstanceFamily not in type_list:
                return_data.append({"id": i.InstanceFamily, "name": i.InstanceFamily})
                type_list.append(i.InstanceFamily)
        return {"result": True, "data": return_data}

    # todo
    def get_spec_list(self, **kwargs):
        client = self.cvm_client
        model = cvm_models
        req = model.DescribeInstanceTypeConfigsRequest()
        params = {
            "_Filters": [
                {"Name": "zone", "Values": [kwargs["zone"]]},
                {"Name": "instance-family", "Values": [kwargs["spec"]]},
            ]
        }
        req.from_json_string(json.dumps(params))
        resp = client.DescribeInstanceTypeConfigs(req)
        return_data = []
        for i in resp.InstanceTypeConfigSet:
            i = json.loads(i.to_json_string())
            i["id"] = i["text"] = i["InstanceFamily"]
            return_data.append(i)
        return {"result": True, "data": return_data}

    def get_storage_list(self, **kwargs):
        """
        获取云硬盘价格列表 价格计量单位是  1块 1GB 1个月
        :param kwargs:
        :return:
        """
        storage_type = [
            {"name": "普通云硬盘", "type": "CLOUD_BASIC"},
            {"name": "高性能云硬盘", "type": "CLOUD_PREMIUM"},
            {"name": "SSD云硬盘", "type": "CLOUD_SSD"},
        ]
        client = self.cbs_client
        model = cbs_models
        req = model.InquiryPriceCreateDisksRequest()
        storage_list = []
        for i in storage_type:
            params = {
                "DiskType": i["type"],
                "DiskSize": 100,
                "DiskChargeType": "PREPAID",
                "DiskChargePrepaid": {"Period": 1},
                "DiskCount": 1,
            }
            req.from_json_string(json.dumps(params))
            resp = client.InquiryPriceCreateDisks(req)
            storage_list.append(
                {"price": float(resp.DiskPrice.DiscountPrice) / 100, "name": i["name"], "type": i["type"]}
            )
        return {"result": True, "data": storage_list}

    def get_storage_price(self, **kwargs):
        """
        根据磁盘类型、大小、付费类型获取存储价格， 暂未使用，用上边那个就可以
        Args:
            **kwargs ():
                disk_type (str): 取值参照QCloud硬盘类型枚举；  (required)
                disk_size (int): 硬盘容量   (required)
                paid_modal (str): 计费模式，取值参照QCloud计费模式枚举类    (required)
                period (int): 包年包月时长，包年包月时必填，其他不需要.    (required)
                disk_count (int): 硬盘数量.   默认值为1.  (optional)
        Returns:

        """
        client = self.cbs_client
        model = cbs_models
        req = model.InquiryPriceCreateDisksRequest()
        storage_list = []
        disk_type = kwargs.get("disk_type")
        disk_size = kwargs.get("disk_size")
        disk_count = kwargs.get("disk_count")
        params = {
            "DiskType": disk_type,
            "DiskSize": disk_size,
            "DiskCount": disk_count,
        }
        paid_modal = kwargs.get("paid_modal")
        if paid_modal == "PREPAID":
            dict(params, **{"DiskChargeType": paid_modal, "DiskChargePrepaid": {"Period": kwargs.get("period")}})
        else:
            dict(params, **{"DiskChargeType": paid_modal})
        req.from_json_string(json.dumps(params))
        resp = client.InquiryPriceCreateDisks(req)
        storage_list.append(
            {"price": resp.DiskPrice.DiscountPrice, "name": handle_disk_category(disk_type), "type": disk_type}
        )
        return {"result": True, "data": storage_list}

    def get_spec_price(self, **kwargs):
        """
        获取实例规格对应价格
        :param kwargs:
        :return:
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.DescribeImagesRequest()
            resp = client.DescribeImages(req)
            image_id = resp.ImageSet[0].ImageId
            params = {
                "InstanceChargeType": "PREPAID",
                "InstanceChargePrepaid": {"Period": 1},
                "Placement": {"Zone": kwargs["zone"]},
                "ImageId": image_id,
                "InstanceType": kwargs["spec"],
            }
            if kwargs.get("SystemDisk"):
                params["SystemDisk"] = kwargs["SystemDisk"]
            if kwargs.get("DataDisks"):
                params["DataDisks"] = kwargs["DataDisks"]
            req = model.InquiryPriceRunInstancesRequest()
            req.from_json_string(json.dumps(params))
            resp = client.InquiryPriceRunInstances(req)
            return {"result": True, "data": resp.Price.InstancePrice.DiscountPrice}
        except Exception as e:
            logger.exception("get_spec_price error")
            return {"result": False, "message": str(e)}

    @classmethod
    def get_project_list(cls, secret_id, secret_key, region_id):
        """
        获取项目列表
        :param secret_id:
        :param secret_key:
        :param region_id:
        :return:
        """
        config = {
            "Region": secret_id,
            "secretId": secret_key,
            "secretKey": region_id,
            "method": "post",
        }
        module = "monitor"
        service = QcloudApi(module, config)
        action = "DescribeProject"
        params = {"allList": 0}
        service.generateUrl(action, params)
        result = json.loads(service.call(action, params))
        return result

    #  ********************************主机管理**********************************

    # def get_flavor_families(self, **kwargs):
    #     """
    #     查询当前用户和地域所支持的机型族列表信息
    #     :param kwargs:
    #     :return:
    #     """
    #     client = self.cvm_client
    #     model = cvm_models
    #     req = model.DescribeInstanceFamilyConfigsRequest()
    #     resp = client.DescribeInstanceFamilyConfigs(req)
    #     return_data = []
    #     for i in resp.InstanceFamilyConfigSet:
    #         return_data.append(format_resp_data("FlavorFamily", i))
    #     return {"result": True, "data": return_data}
    #
    # def get_vm_flavors(self, **kwargs):
    #     """
    #     获取实例规格列表
    #     :param kwargs:
    #     :return:
    #     """
    #     client = self.cvm_client
    #     model = cvm_models
    #     req = model.DescribeInstanceTypeConfigsRequest()
    #     if "zone" in kwargs:
    #         zone = kwargs["zone"]
    #         if "spec" in kwargs:
    #             flavor = kwargs["spec"]
    #             params = {
    #                 "_Filters": [{"Name": "zone", "Values": [zone]}, {"Name": "instance-family", "Values": [flavor]}]
    #             }
    #             req.from_json_string(json.dumps(params))
    #     resp = client.DescribeInstanceTypeConfigs(req)
    #     return_data = []
    #     for i in resp.InstanceTypeConfigSet:
    #         return_data.append(format_resp_data("Flavor", i))
    #     return {"result": True, "data": return_data}
    def list_instance_type_families(self, **kwargs):
        """
        查询实例机型族信息
        SDK：DescribeInstanceFamilyConfigs
        Returns:

        """
        req = cvm_models.DescribeInstanceFamilyConfigsRequest()
        return self._handle_list_request("cvm_client", req, "instance_type_family")

    def list_instance_types(self, **kwargs):
        """
        获取实例规格列表
        Returns:

        """
        req = cvm_models.DescribeInstanceTypeConfigsRequest()
        return self._handle_list_request("cvm_client", req, "instance_type")

    def list_vms(self, ids=None, **kwargs):
        """
        获取实例信息
        :param kwargs: tcloud DescribeInstancesRequest api param, see https://cloud.tencent.com/document/api
        ids (list): 实例id列表
        :return: vm_list
        """
        req = cvm_models.DescribeInstancesRequest()
        if ids:
            req.InstanceIds = convert_param_to_list(ids)
        filters = cvm_models.Filter()
        for k, v in kwargs.items():
            filters.Name = k
            filters.Values = v
        if kwargs:
            req._Filters = [filters]
        return self._handle_list_request("cvm_client", req, "vm", True)

    @classmethod
    def _set_create_vm_params(cls, **kwargs):
        """
        设置实例创建参数
        :param kwargs:
        :return:
        """
        model = cvm_models
        req = model.RunInstancesRequest()
        placement = model.Placement()
        placement.Zone = kwargs.get("Placement").get("Zone")
        placement.ProjectId = kwargs.get("Placement").get("ProjectId", None)
        placement.HostIds = kwargs.get("Placement").get("HostIds", None)
        req.Placement = placement
        req.ImageId = kwargs["ImageId"]
        req.InstanceChargeType = kwargs.get("InstanceChargeType", None)
        if kwargs.get("InstanceChargePrepaid", None):
            charge_prepaid = model.InstanceChargePrepaid()
            charge_prepaid.Period = kwargs["InstanceChargePrepaid"].get("Period", None)
            charge_prepaid.RenewFlag = kwargs["InstanceChargePrepaid"].get("RenewFlag", None)
            req.InstanceChargePrepaid = charge_prepaid
        req.InstanceType = kwargs.get("InstanceType", None)
        if kwargs.get("SystemDisk", None):
            system_disk = model.SystemDisk()
            system_disk.DiskType = kwargs["SystemDisk"].get("DiskType", None)
            system_disk.DiskId = kwargs["SystemDisk"].get("DiskId", None)
            system_disk.DiskSize = kwargs["SystemDisk"].get("DiskSize", None)
            req.SystemDisk = system_disk
        if kwargs.get("DataDisks", None):
            data_disks = []
            data_disk = model.DataDisk()
            for i in kwargs["DataDisks"]:
                data_disk.DiskType = i.get("DiskType", None)
                data_disk.DiskId = i.get("DiskId", None)
                data_disk.DiskSize = i.get("DiskSize", None)
                data_disk.DeleteWithInstance = i.get("DeleteWithInstance", None)
                data_disk.SnapshotId = i.get("SnapshotId", None)
                data_disk.Encrypt = i.get("Encrypt", None)
                data_disks.append(data_disk)
            req.DataDisks = data_disks
        if kwargs.get("VirtualPrivateCloud", None):
            vir_private_cloud = model.VirtualPrivateCloud()
            vir_private_cloud.VpcId = kwargs["VirtualPrivateCloud"].get("VpcId", None)
            vir_private_cloud.SubnetId = kwargs["VirtualPrivateCloud"].get("SubnetId", None)
            vir_private_cloud.AsVpcGateway = kwargs["VirtualPrivateCloud"].get("AsVpcGateway", None)
            vir_private_cloud.PrivateIpAddresses = kwargs["VirtualPrivateCloud"].get("PrivateIpAddresses", None)
            req.VirtualPrivateCloud = vir_private_cloud
        if kwargs.get("InternetAccessible", None):
            inter_access = model.InternetAccessible()
            inter_access.InternetChargeType = kwargs["InternetAccessible"].get("InternetChargeType", None)
            inter_access.InternetMaxBandwidthOut = kwargs["InternetAccessible"].get("InternetMaxBandwidthOut", None)
            inter_access.PublicIpAssigned = kwargs["InternetAccessible"].get("PublicIpAssigned", None)
            inter_access.BandwidthPackageId = kwargs["InternetAccessible"].get("BandwidthPackageId", None)
            req.InternetAccessible = inter_access
        req.InstanceCount = kwargs.get("InstanceCount", 1)
        req.InstanceName = kwargs.get("InstanceName", None)
        if kwargs.get("LoginSettings", None):
            login_settings = model.LoginSettings()
            login_settings.Password = kwargs["LoginSettings"].get("Password", None)
            login_settings.KeyIds = kwargs["LoginSettings"].get("KeyIds", None)
            login_settings.KeepImageLogin = kwargs["LoginSettings"].get("KeepImageLogin", None)
            req.LoginSettings = login_settings
        req.SecurityGroupIds = kwargs.get("SecurityGroupIds", None)
        if kwargs.get("EnhancedService", None):
            enhanced_service = model.EnhancedService()
            enhanced_service.SecurityService = kwargs["EnhancedService"].get("SecurityService", None)
            enhanced_service.MonitorService = kwargs["EnhancedService"].get("MonitorService", None)
        req.ClientToken = kwargs.get("ClientToken", None)
        req.HostName = kwargs.get("HostName", None)
        if kwargs.get("ActionTimer", None):
            action_time = model.ActionTimer()
            action_time.TimerAction = kwargs["ActionTimer"].get("TimerAction")
            action_time.ActionTime = kwargs["ActionTimer"].get("ActionTime")
            if kwargs["ActionTimer"].get("Externals") is not None:
                externals = model.Externals()
                externals.ReleaseAddress = kwargs["ActionTimer"]["Externals"].get("extennals")
            req.ActionTimer = action_time
        req.DisasterRecoverGroupIds = kwargs.get("DisasterRecoverGroupIds", None)
        if kwargs.get("TagSpecification", None):
            tag_spec = model.TagSpecification()
            tag_spec.ResourceType = kwargs["TagSpecification"].get("ResourceType")
            if kwargs["TagSpecification"].get("Tags", None):
                tag = model.Tag()
                tags = []
                for t in kwargs["TagSpecification"]["Tags"]:
                    tag.Key = t.get("Key", None)
                    tag.Value = t.get("Value", None)
                    tags.append(tag)
            req.TagSpecification = tag_spec
        return req

    def create_vm(self, **kwargs):
        """
        创建实例
        :param kwargs: tcloud RunInstances api param, see https://cloud.tencent.com/document/api
                Placement:实例所在的位置。类型：`tencentcloud.cvm.v20170312.models.Placement`。必选
                ImageId:指定有效的镜像ID。类型：string。必选。
                InstanceChargeType：实例计费类型。类型：string。
                                     可选值：PREPAID：预付费，即包年包月
                                            POSTPAID_BY_HOUR：按小时后付费
                                            CDHPAID：独享子机（基于专用宿主机创建，宿主机部分的资源不收费）
                                            SPOTPAID：竞价付费
                                            默认值：POSTPAID_BY_HOUR。
                InstanceChargePrepaid：预付费模式，即包年包月相关参数设置。类型：`tencentcloud.cvm.v20170312.models.InstanceChargePrepaid`。
                InstanceType:实例机型。类型：string。
                SystemDisk：实例系统盘配置信息。类型：`tencentcloud.cvm.v20170312.models.SystemDisk`。
                DataDisks：实例数据盘配置信息。类型：Array of `tencentcloud.cvm.v20170312.models.DataDisks`。
                VirtualPrivateCloud：私有网络相关信息配置。类型：私有网络相关信息配置。
                InternetAccessible：公网带宽相关信息设置。类型：`tencentcloud.cvm.v20170312.models.InternetAccessible`。
                InstanceCount：购买实例数量。类型：int。
                InstanceName：实例显示名称。类型：string。
                LoginSettings：实例登录设置。类型：`tencentcloud.cvm.v20170312.models.LoginSettings`。
                SecurityGroupIds：实例所属安全组。类型：Array of String。
                EnhancedService：增强服务。类型：`tencentcloud.cvm.v20170312.models.EnhancedService`。
                ClientToken：用于保证请求幂等性的字符串。类型：String。
                HostName：云服务器的主机名。类型：String。
                ActionTimer：定时任务。类型：`tencentcloud.cvm.v20170312.models.ActionTimer`。
                DisasterRecoverGroupIds：置放群组id，类型：Array of String。
                TagSpecification：标签描述列表。类型：Array of `tencentcloud.cvm.v20170312.models.TagSpecification`。
                InstanceMarketOptions：实例的市场相关选项。类型：Array of `tencentcloud.cvm.v20170312.models.InstanceMarketOptions`。
                UserData：提供给实例使用的用户数据，需要以 base64 方式编码，支持的最大数据大小为 16KB。类型：String。
                DryRun：是否只预检此次请求。类型：Boolean。
                HpcClusterId：高性能计算集群ID。类型：String。
        :return: 虚拟机ID
        """
        try:
            client = self.cvm_client
            req = self._set_create_vm_params(**kwargs)
            resp = client.RunInstances(req)
            return {"result": True, "data": resp.InstanceIdSet}
        except TencentCloudSDKException as e:
            logger.exception("create_vm")
            return {"result": False, "message": e.message}

    def start_vm(self, vm_id):
        """
        启动实例
        :param vm_id: 虚拟机ID
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.StartInstancesRequest()
            req.InstanceIds = [vm_id]
            client.StartInstances(req)
            return {"result": True}
        except TencentCloudSDKException as e:
            logger.exception("start_vm(instance_id):" + vm_id)
            return {"result": False, "message": e.message}

    def stop_vm(self, vm_id, is_force="FALSE"):
        """
        停止实例
        :param vm_id: 虚拟机ID
        :param is_force: 强制关机
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.StopInstancesRequest()
            req.InstanceIds = [vm_id]
            req.ForceStop = is_force
            client.StopInstances(req)
            return {"result": True}
        except TencentCloudSDKException as e:
            logger.exception("stop_vm(instance_id):" + vm_id)
            return {"result": False, "message": e.message}

    def restart_vm(self, vm_id, is_force="FALSE"):
        """
        重启实例
        :param vm_id: 虚拟机ID
        :param is_force: 强制重启
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.RebootInstancesRequest()
            req.InstanceIds = [vm_id]
            req.ForceReboot = is_force
            client.RebootInstances(req)
            return {"result": True}
        except TencentCloudSDKException as e:
            logger.exception("restart_vm(instance_id):" + vm_id)
            return {"result": False, "message": e.message}

    def reset_instances_password(self, **kwargs):
        r"""
            将实例操作系统的密码重置为用户指定的密码。
            调用接口是注意：
            只修改管理员帐号的密码。实例的操作系统不同，管理员帐号也会不一样(Windows为Administrator，Ubuntu为ubuntu，
        其它系统为root)。
            重置处于运行中状态的实例，需要显式指定强制关机参数ForceStop。如果没有显式指定强制关机参数，则只有处于关机状态的
        实例才允许执行重置密码操作。
            支持批量操作。将多个实例操作系统的密码重置为相同的密码。每次请求批量实例的上限为100。
            :param kwargs:
                        InstanceIds：类型： Array Of String.。描述：一个或多个待操作的实例ID。
                        Password：类型：String。描述：实例登录密码。不同操作系统类型密码复杂度限制不一样，具体如下：
                    Linux实例密码必须8-30位，推荐使用12位以上密码，不能以“/”开头，至少包含以下字符中的三种不同字符，
                    字符种类：
                            小写字母：[a-z]
                            大写字母：[A-Z]
                            数字：0-9
                            特殊字符： ()\`~!@#$%^&\*-+=\_|{}[]:;'<>,.?/
                    Windows实例密码必须12~30位，不能以“/”开头且不包括用户名，至少包含以下字符中的三种不同字符：
                            小写字母：[a-z]
                            大写字母：[A-Z]
                            数字： 0-9
                            特殊字符：()\`~!@#$%^&\*-+=\_|{}[]:;' <>,.?/
                    如果实例即包含`Linux`实例又包含`Windows`实例，则密码复杂度限制按照`Windows`实例的限制。
                        UserName：类型：String。描述：待重置密码的实例操作系统的管理员账户。不得超过64个字符。
                        ForceStop：类型：Boolean。描述：是否对运行中的实例选择强制关机。建议对运行中的实例先手动关机，
                    然后再重置用户密码。取值范围：
                                                TRUE：表示在正常关机失败后进行强制关机
                                                FALSE：表示在正常关机失败后不进行强制关机
                    默认取值：FALSE。
            :return:
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.ResetInstancesPasswordRequest()
            # list_optional_params = ["InstanceIds", "Password", "UserName", "ForceStop"]
            list_optional_params = ["InstanceIds", "Password"]
            req = set_optional_params(req, list_optional_params, kwargs)
            client.ResetInstancesPassword(req)
            return {"result": True}
        except Exception as e:
            logger.exception("reset_instances_password")
            return {"result": False, "message": str(e)}

    def renew_vm(self, vm_id, period):
        """
        实例续费
        :param vm_id: 虚拟机ID
        :param period:包年包月续费时长
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.RenewInstancesRequest()
            req.InstanceIds = [vm_id]
            ins_charge = model.InstanceChargePrepaid()
            ins_charge.Period = period
            ins_charge.RenewFlag = None
            req.InstanceChargePrepaid = ins_charge
            client.RenewInstances(req)
            return {"result": True}
        except TencentCloudSDKException as e:
            logger.exception("renew_vm(instance_id):" + vm_id)
            return {"result": False, "message": e.message}

    def modify_vm(self, **kwargs):
        """
        调整实例配置
        :param kwargs: tcloud ResetInstances api param, see https://cloud.tencent.com/document/api
            InstanceId (list): 实例id列表. (required)
            InstanceType (str): 新的实例规格id. (required)
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.ResetInstancesTypeRequest()
            if isinstance(kwargs["InstanceId"], list):
                req.InstanceIds = kwargs["InstanceId"]
            else:
                req.InstanceIds = [kwargs["InstanceId"]]
            req.InstanceType = kwargs.get("InstanceType", "")
            client.ResetInstancesType(req)
            return {"result": True}
        except TencentCloudSDKException as e:
            logger.exception("modify_vm(instance_id):" + kwargs["InstanceId"])
            return {"result": False, "message": e.message}

    def destroy_vm(self, vm_id):
        """
        释放实例
        :param vm_id: 虚拟机ID
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.TerminateInstancesRequest()
            params = {"InstanceIds": [vm_id]}
            req.from_json_string(json.dumps(params))
            client.TerminateInstances(req)
            return {"result": True}
        except TencentCloudSDKException as e:
            logger.exception("destroy_vm(instance_id):" + vm_id)
            return {"result": False, "message": e.message}

    def remote_connect_vm(self, **kwargs):
        """
        查询实例的Web管理终端地址
        :param kwargs:tcloud DescribeInstanceVncUrlRequest api param, see https://cloud.tencent.com/document/api
        :return: 远程控制台url
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.DescribeInstanceVncUrlRequest()
            req.InstanceId = kwargs["vm_id"]
            resp = client.DescribeInstanceVncUrl(req)
            vnc_url = json.loads(resp.to_json_string())["InstanceVncUrl"]
            url = "https://img.qcloud.com/qcloud/app/active_vnc/index.html?InstanceVncUrl=" + vnc_url
            return {"result": True, "data": url}
        except Exception as e:
            logger.exception("remote_vm(instance_id):" + kwargs["vm_id"])
            return {"result": False, "message": str(e)}

    def reset_instances_internet_max_bandwidth(self, **kwargs):
        """
        调整实例公网带宽上限。
        :param kwargs:
                    InstanceIds：类型：list of str。必选。描述：一个或多个待操作的实例ID。
                    InternetAccessible：类型：class:`tencentcloud.cvm.v20170312.models.InternetAccessible`。必选。
                描述：公网出带宽配置。
                    StartTime：类型：String。描述：带宽生效的起始时间。格式：`YYYY-MM-DD`。
                    EndTime：类型：String。描述：带宽生效的终止时间。格式：`YYYY-MM-DD。
        :return:
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.ResetInstancesInternetMaxBandwidthRequest()
            list_optional_params = ["StartTime", "EndTime"]
            list_required_params = ["InstanceIds", "InternetAccessible"]
            req = set_required_params(req, list_required_params, kwargs)
            req = set_optional_params(req, list_optional_params, kwargs)
            client.ResetInstancesInternetMaxBandwidth(req)
            return {"result": True}
        except Exception as e:
            logger.exception("reset_instances_internet_max_bandwidth")
            return {"result": False, "message": str(e)}

    def get_available_flavor(self, **kwargs):
        """
        获取可用区机型配置信息
        :param kwargs: tcloud DescribeZoneInstanceConfigInfosRequest api param,
        see https://cloud.tencent.com/document/api
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.DescribeZoneInstanceConfigInfosRequest()
            config = kwargs["config"]
            kwargs["Cores"] = int(config[0])
            kwargs["Memory"] = float(config[1])
            params = json.dumps({"_Filters": [{"Name": "zone", "Values": [kwargs["ZoneId"]]}]})
            req.from_json_string(params)
            resp = client.DescribeZoneInstanceConfigInfos(req)
            result = json.loads(resp.to_json_string())
            data = ""
            if "Error" not in result:
                for i in result["InstanceTypeQuotaSet"]:
                    if i["Cpu"] == kwargs["Cores"] and i["Memory"] == kwargs["Memory"]:
                        data = i["InstanceType"]
            return {"result": True, "data": data}
        except TencentCloudSDKException as e:
            logger.exception("get_available_flavor")
            return {"result": False, "message": e.message}

    def modify_instances_vpc_attribute(self, **kwargs):
        """
        修改实例vpc属性，如私有网络ip。
        :param kwargs:
                    InstanceIds：类型：String。必选。待操作的实例ID数组。
                    VirtualPrivateCloud：类型：String。必选。私有网络相关信息配置。
                    ForceStop：类型：String。是否对运行中的实例选择强制关机。默认为TRUE。
        :return:
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.ModifyInstancesVpcAttributeRequest()
            list_optional_params = ["ForceStop"]
            list_required_params = ["InstanceIds", "VirtualPrivateCloud"]
            req = set_required_params(req, list_required_params, kwargs)
            req = set_optional_params(req, list_optional_params, kwargs)
            client.ModifyInstancesVpcAttribute(req)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_instances_vpc_attribute")
            return {"result": False, "message": str(e)}

    def monitor_data(self, namespace, metric_name, instances, period=300, start_time=None, end_time=None):
        """
        获取监控信息列表
        :param namespace:
        :param metric_name:
        :param instances:
        :param period:
        :param start_time:
        :param end_time:
        :return:
        """
        try:
            client = self.monitor_client
            model = monitor_models
            req = model.GetMonitorDataRequest()
            req.Instances = instances

            req.Namespace = namespace
            req.MetricName = metric_name
            req.Period = period
            req.StartTime = start_time
            req.EndTime = end_time
            resp = client.GetMonitorData(req)
            result_dic = json.loads(resp.to_json_string())
            if "Error" not in list(result_dic.keys()):
                data = result_dic["DataPoints"]
                return {"result": True, "data": data}
            else:
                return {"result": False, "message": result_dic["message"]}
        except Exception as e:
            logger.exception("monitor_data")
            return {"result": False, "message": str(e)}

    def describe_statistic_data(
        self, namespace, metrics, period=300, start_time=None, end_time=None, module="monitor", conditions=None
    ):
        req = monitor_models.DescribeStatisticDataRequest()
        params = {
            "Module": module,
            "Namespace": namespace,
            "MetricNames": metrics,
            "Conditions": conditions,
            "Period": period,
            "StartTime": start_time,
            "EndTime": end_time,
        }
        req.from_json_string(json.dumps(params))
        try:
            resp = self.monitor_client.DescribeStatisticData(req)
            result_dic = json.loads(resp.to_json_string())
            return {"result": True, "data": result_dic.get("Data")}
        except Exception as e:
            logger.exception(f"describe_statistic_data:{e}")
            return {"result": False, "message": str(e)}

    def get_monitor_data(self, **kwargs):
        """
        获取监控信息详情
        :param kwargs:
        :return:
        """
        try:
            now_time = (datetime.datetime.now() + datetime.timedelta(minutes=-5)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
            hour_time = (datetime.datetime.now() + datetime.timedelta(minutes=-10)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
            start_time = kwargs.get("StartTime", hour_time)
            start_time = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%S+08:00")
            end_time = kwargs.get("EndTime", now_time)
            end_time = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%S+08:00")
            namespace = "QCE/CVM"
            resource_id = kwargs.get("resourceId", "")
            vm_list_all = resource_id.split(",")
            res = {}
            vm_lists = []
            # 可能是一次只能拿20个实例的监控数据
            for i in range(len(vm_list_all) // 20 + 1):
                vm_lists.append(vm_list_all[i * 20 : (i + 1) * 20])
            for vm_list in vm_lists:
                instances = []
                for i in vm_list:
                    instances.append({"Dimensions": [{"Name": "InstanceId", "Value": i}]})
                    res[i] = {}
                cpu_metric_name = "CPUUsage"
                memory_metric_name = "MemUsage"
                cpu_result = self.monitor_data(
                    namespace, cpu_metric_name, instances, period=300, start_time=start_time, end_time=end_time
                )["data"]
                memory_result = self.monitor_data(
                    namespace, memory_metric_name, instances, period=300, start_time=start_time, end_time=end_time
                )["data"]
                disk_data = []
                for n in cpu_result:
                    cpu_data = []
                    vm_id = n["Dimensions"][0]["Value"]
                    for k, i in enumerate(n["Timestamps"]):
                        rate = "%.2f" % (n["Values"][k])
                        cpu_data.append([i, float(rate)])
                    res[vm_id]["cpu_data"] = cpu_data
                for n in memory_result:
                    memory_data = []
                    vm_id = n["Dimensions"][0]["Value"]
                    for k, i in enumerate(n["Timestamps"]):
                        rate = "%.2f" % (n["Values"][k])
                        memory_data.append([i, float(rate)])
                    res[vm_id]["memory_data"] = memory_data
                    res[vm_id]["disk_data"] = disk_data
            res["result"] = True
            return res
        except Exception as e:
            logger.exception("get_monitor_data")
            return {"result": False, "message": str(e)}

    def get_load_monitor_data(self, **kwargs):
        """
        获取监控信息详情
        :param kwargs:
        :return:
        """
        try:
            start_time = str(kwargs.get("StartTime", datetime.datetime.now() + datetime.timedelta(minutes=-10)))
            end_time = str(kwargs.get("EndTime", datetime.datetime.now() + datetime.timedelta(minutes=-5)))

            namespace = "QCE/CVM"
            vm_list_all = list(set(kwargs["resourceId"]))
            res = {}
            vm_lists = []

            # 一次最多拉取10个实例的监控数据  1台机器4小时最多48条数据
            for i in range(len(vm_list_all) // 10 + 1):
                vm_lists.append(vm_list_all[i * 10 : (i + 1) * 10])
            for vm_list in vm_lists:
                if not vm_list:
                    continue
                instances = []
                for i in vm_list:
                    instances.append({"Dimensions": [{"Name": "InstanceId", "Value": i}]})
                    res[i] = {}
                # 负载维度
                cpu_metric_name = "CPUUsage"
                memory_metric_name = "MemUsage"
                load_metric_name = "Cpuloadavg5m"

                cpu_result = self.monitor_data(
                    namespace, cpu_metric_name, instances, period=300, start_time=start_time, end_time=end_time
                )["data"]
                memory_result = self.monitor_data(
                    namespace, memory_metric_name, instances, period=300, start_time=start_time, end_time=end_time
                )["data"]
                load_result = self.monitor_data(
                    namespace, load_metric_name, instances, period=300, start_time=start_time, end_time=end_time
                )["data"]
                for n in cpu_result:
                    vm_id = n["Dimensions"][0]["Value"]
                    res[vm_id]["cpu_data"] = n["Values"]

                for n in memory_result:
                    vm_id = n["Dimensions"][0]["Value"]
                    res[vm_id]["memory_data"] = n["Values"]

                for n in load_result:
                    vm_id = n["Dimensions"][0]["Value"]
                    res[vm_id]["load_data"] = n["Values"]

                # disk_data = []
                # for n in cpu_result:
                #     cpu_data = []
                #     vm_id = n["Dimensions"][0]["Value"]
                #     for k, i in enumerate(n["Timestamps"]):
                #         rate = "%.2f" % (n["Values"][k])
                #         cpu_data.append([i, float(rate)])
                #     res[vm_id]["cpu_data"] = cpu_data
                # for n in memory_result:
                #     memory_data = []
                #     vm_id = n["Dimensions"][0]["Value"]
                #     for k, i in enumerate(n["Timestamps"]):
                #         rate = "%.2f" % (n["Values"][k])
                #         memory_data.append([i, float(rate)])
                #     res[vm_id]["memory_data"] = memory_data
                #     res[vm_id]["disk_data"] = disk_data
            return {"result": True, "data": res}

        except Exception as e:
            logger.exception("get_monitor_data")
            return {"result": False, "message": str(e)}

    def get_weops_monitor_data(self, **kwargs):
        """
        获取监控信息详情(weops专属)
        :param kwargs:
        :return:
        """
        try:
            now_time = (datetime.datetime.now() + datetime.timedelta(minutes=-5)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
            hour_time = (datetime.datetime.now() + datetime.timedelta(minutes=-10)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
            start_time = kwargs.get("StartTime", hour_time)
            start_time = (
                datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S") + datetime.timedelta(minutes=-1)
            ).strftime("%Y-%m-%dT%H:%M:%S+08:00")
            end_time = kwargs.get("EndTime", now_time)
            end_time = (
                datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S") + datetime.timedelta(minutes=-1)
            ).strftime("%Y-%m-%dT%H:%M:%S+08:00")

            period = kwargs.get("Period", 300)
            resource_id = kwargs.get("resourceId", "")
            obj_list_all = resource_id.split(",")
            if not obj_list_all:
                return {"result": False, "message": "缺少监控对象"}

            resources = kwargs.get("context", {}).get("resources", [])
            bk_obj_id = resources[0]["bk_obj_id"]
            namespace = self.BK_OBJ_ID_NS_MAP.get(bk_obj_id)
            default_metrics = self.BK_OBJ_ID_METRICS.get(bk_obj_id)
            metrics = kwargs.get("Metrics", default_metrics) or default_metrics
            if not metrics:
                return {"result": False, "message": "缺少监控指标"}
            res = {}
            obj_data = {}
            obj_lists = []
            # 可能是一次只能拿20个实例的监控数据
            for i in range(len(obj_list_all) // 20 + 1):
                obj_lists.append(obj_list_all[i * 20 : (i + 1) * 20])
            for obj_list in obj_lists:
                if namespace == "QCE/TKE2":
                    conditions = [{"Key": "tke_cluster_instance_id", "Operator": "in", "Value": obj_list}]
                    result = self.describe_statistic_data(
                        namespace, metrics, period, start_time, end_time, conditions=conditions
                    )
                    if not result["result"]:
                        continue
                    result = result.get("data", [])
                    for _result in result:
                        metric = _result["MetricName"]
                        points = _result["Points"]
                        for point in points:
                            obj_id = point["Dimensions"][0]["Value"]
                            ts_values = point["Values"]
                            for ts in ts_values:
                                metric_value = ts["Value"]
                                timestamp = ts["Timestamp"]
                                if metric_value is None:
                                    continue
                                obj_data.setdefault(obj_id, {}).setdefault(
                                    self.rename_metric_key(bk_obj_id, metric), []
                                ).append([timestamp, float(metric_value)])
                else:
                    instances = []
                    for i in obj_list:
                        instances.append({"Dimensions": [{"Name": "InstanceId", "Value": i}]})
                        obj_data[i] = {}
                    for metric in metrics:
                        new_metric = self.rename_metric_key(bk_obj_id, metric, revert=True)
                        result = self.monitor_data(
                            namespace, new_metric, instances, period=period, start_time=start_time, end_time=end_time
                        )
                        if not result["result"]:
                            continue
                        result = result["data"]
                        for n in result:
                            obj_id = n["Dimensions"][0]["Value"]
                            for k, i in enumerate(n["Timestamps"]):
                                rate = "%.2f" % (n["Values"][k])
                                obj_data[obj_id].setdefault(metric, []).append([i, float(rate)])
            res["data"] = obj_data
            res["result"] = True
            return res
        except Exception as e:
            logger.exception("get_weops_monitor_data")
            return {"result": False, "message": str(e)}

    def instance_security_group_action(self, **kwargs):
        """
        给实例绑定安全组
        :param kwargs:
            InstanceIds: 实例id集合 腾讯云接收list
            SecurityGroups: list 安全组id集合
        :type kwargs:
        :return:
        :rtype:
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.ModifyInstancesAttributeRequest()
            req.InstanceIds = kwargs.get("InstanceIds")
            req.SecurityGroups = kwargs.get("SecurityGroups")
            client.ModifyInstancesAttribute(req)
            return {"result": True}
        except TencentCloudSDKException as e:
            logger.exception("vm_add_security_group")
            return {"result": False, "message": e.message}

    # -----------------------标签--------------------------------

    def create_tag(self, **kwargs):
        """
        创建标签
        :param kwargs:
                    TagKey：类型：String。必选。描述：标签键
                    TagValue：类型：String。必选。描述：标签值
        :return:    data输出示例：
                    {
                      "Response": {
                        "RequestId": "3c140219-cfe9-470e-b241-907877d6fb03"
                      }
                    }
        """
        try:
            client = self.tag_client
            model = tag_models
            req = model.CreateTagRequest()
            req.TagKey = kwargs["TagKey"]
            req.TagValue = kwargs["TagValue"]
            client.CreateTag(req)
            return {"result": True}
        except Exception as e:
            logger.exception("create_tag")
            return {"result": False, "message": str(e)}

    def delete_tag(self, **kwargs):
        """
        删除标签
        :param kwargs:
                    TagKey：类型：String。必选。描述：标签键
                    TagValue：类型：String。必选。描述：标签值
        :return:
        """
        try:
            client = self.tag_client
            model = tag_models
            req = model.DeleteTagRequest()
            req.TagKey = kwargs["TagKey"]
            req.TagValue = kwargs["TagValue"]
            client.DeleteTag(req)
            return {"result": True}
        except Exception as e:
            logger.exception("delete_tag")
            return {"result": False, "message": str(e)}

    def update_resource_tag_value(self, **kwargs):
        """
        修改资源已关联的标签值（标签键不变）
        :param kwargs:
                    TagKey：类型：String。必选。描述：标签键
                    TagValue：类型：String。必选。描述：标签值
                    Resource：类型：String。必选。描述：资源的六段式描述。示例：Resource=qcs::cvm:ap-beijing:uin/1234567:instance/ins-123
        :return:    data输出示例：
                    {
                      "Response": {
                        "RequestId": "3c140219-cfe9-470e-b241-907877d6fb03"
                      }
                    }
        """
        try:
            client = self.tag_client
            model = tag_models
            req = model.UpdateResourceTagValueRequest()
            req.TagKey = kwargs["TagKey"]
            req.TagValue = kwargs["TagValue"]
            req.Resource = kwargs["Resource"]
            client.UpdateResourceTagValue(req)
            return {"result": True}
        except Exception as e:
            logger.exception("update_resource_tag_value")
            return {"result": False, "message": str(e)}

    def add_resource_tag(self, **kwargs):
        """
        给标签关联资源。
        :param kwargs:
                    TagKey：类型：String。必选。描述：标签键
                    TagValue：类型：String。必选。描述：标签值
                    Resource：类型：String。必选。描述：资源的六段式描述。示例：Resource=qcs::cvm:ap-beijing:uin/1234567:instance/ins-123
        :return:
        """
        try:
            client = self.tag_client
            model = tag_models
            req = model.AddResourceTagRequest()
            req.TagKey = kwargs["TagKey"]
            req.TagValue = kwargs["TagValue"]
            req.Resource = kwargs["Resource"]
            client.AddResourceTag(req)
            return {"result": True}
        except Exception as e:
            logger.exception("add_resource_tag")
            return {"result": False, "message": str(e)}

    def delete_resource_tag(self, **kwargs):
        """
        标签解绑资源
        :param kwargs:
                    TagKey：类型：String。必选。描述：标签键
                    Resource：类型：String。必选。描述：资源的六段式描述。示例：Resource=qcs::cvm:ap-beijing:uin/1234567:instance/ins-123
        :return:
        """
        try:
            client = self.tag_client
            model = tag_models
            req = model.DeleteResourceTagRequest()
            req.TagKey = kwargs["TagKey"]
            req.Resource = kwargs["Resource"]
            client.DeleteResourceTag(req)
            return {"result": True}
        except Exception as e:
            logger.exception("delete_resource_tag")
            return {"result": False, "message": str(e)}

    def list_resource_tags(self, **kwargs):
        """
        查看资源关联的标签
        :param kwargs:
                    ServiceType：类型：String。描述：业务类型
                    ResourcePrefix：类型：String。描述：资源前缀
                    ResourceIds：类型：list of str。描述：资源唯一标记
                    ResourceRegion：类型：String。描述：资源所在地域
                    Offset：类型：int。描述：数据偏移量，默认为 0, 必须为Limit参数的整数倍
                    Limit：类型：int。描述：每页大小，默认为 15
                    CosResourceId：类型：int。描述：是否是Cos的资源id
                    CreateUin：类型：int。描述：创建者uin
        :return:    data输出示例：
                    {
                      "Response": {
                        "TotalCount": 1,
                        "Offset": 0,
                        "Limit": 15,
                        "Rows": [
                          {
                            "ServiceType": "cvm",
                            "TagKey": "instance",
                            "TagKeyMd5": "abced",
                            "TagValue": "ins-asdfsadf",
                            "TagValueMd5": "abced",
                            "ResourceId": "ins-asdfsadf"
                          }
                        ],
                        "RequestId": "5024400f-ae5c-4080-b3ca-f45bf9dae21a"
                      }
                    }
        """
        request = tag_models.DescribeResourceTagsRequest()
        list_optional_params = [
            "ServiceType",
            "ResourcePrefix",
            "ResourceIds",
            "ResourceRegion",
            "Offset",
            "Limit",
            "CosResourceId",
            "CreateUin",
        ]
        request = set_optional_params(request, list_optional_params, kwargs)
        return self._handle_list_request("tag_client", request, "tag", True)

    # ------------------------镜像---------------------------------

    def create_image(self, **kwargs):
        """
        将实例的系统盘制作为新镜像，创建后的镜像可以用于创建实例。
        :param kwargs:
                    ImageName：类型：String。必选。描述：镜像名称
                    InstanceId：类型：String。描述：需要制作镜像的实例ID
                    ImageDescription：类型：String。描述：镜像描述
                    ForcePoweroff：类型：String。描述：软关机失败时是否执行强制关机以制作镜像。取值范围：TRUE：表示关机
                之后制作镜像。FALSE：表示开机状态制作镜像。
                    Sysprep：类型：String。描述：创建Windows镜像时是否启用Sysprep
                    Reboot：类型：String。描述：实例处于运行中时，是否允许关机执行制作镜像任务。
                    DataDiskIds：类型：list of str。描述：实例需要制作镜像的数据盘Id
                    DryRun：类型：bool。描述：检测请求的合法性，但不会对操作的资源产生任何影响
        :return:    data输出示例：
                    {
                      "Response": {
                        "ImageId": "img-0yc6rie8",
                        "RequestId": "71e69b56-32be-4412-ab45-49eded6a87be"
                      }
                    }
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.CreateImageRequest()
            list_optional_params = [
                "InstanceId",
                "ImageDescription",
                "ForcePoweroff",
                "Sysprep",
                "Reboot",
                "DataDiskIds",
                "DryRun",
            ]
            req.ImageName = kwargs["ImageName"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.CreateImage(req)
            qcloud_result = json.loads(resp.to_json_string())
            return {"result": True, "data": qcloud_result["ImageId"]}
        except Exception as e:
            logger.exception("create_image")
            return {"result": False, "message": str(e)}

    def delete_images(self, **kwargs):
        """
        删除镜像
        :param kwargs:
                    ImageIds：类型：String。必选。描述：准备删除的镜像Id列表
        :return:
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.DeleteImagesRequest()
            req.ImageIds = kwargs["ImageIds"]
            client.DeleteImages(req)
            return {"result": True}
        except Exception as e:
            logger.exception("delete_images：" + kwargs["ImageIds"])
            return {"result": False, "message": str(e)}

    def _set_template_info_params(cls, **kwargs):
        """
         设置镜像信息参数
        :param kwargs:
        :return:
        """
        model = cvm_models
        req = model.DescribeImagesRequest()
        req.ImageIds = kwargs.get("ImageIds", None)
        req.InstanceType = kwargs.get("InstanceType", None)
        filters = model.Filter()
        for k, v in kwargs.items():
            filters.Name = k
            filters.Values = v
        # req._Filters = [{"Name": "image-type", "Values": ["PRIVATE_IMAGE", "SHARED_IMAGE"]}]
        req.Limit = 50
        req.Offset = 0
        return req

    def list_images(self, ids=None, **kwargs):
        """
        查看镜像列表
        :param kwargs:tcloud DescribeImages api param, see https://cloud.tencent.com/document/api
        :return: image列表
        """
        request = self._set_template_info_params(**kwargs)
        if ids:
            request.ImageIds = convert_param_to_list(ids)
        return self._handle_list_request("cvm_client", request, "image", True)

    #  *****************************存储***************************************

    # ---------------------云硬盘--------------------------
    @classmethod
    def _set_datastore_info_params(cls, **kwargs):
        """
        设置数据存储信息参数
        :param kwargs:
        :return:
        """
        model = cbs_models
        req = model.DescribeDisksRequest()
        req.DiskIds = kwargs.pop("DiskIds", None)
        req.Order = kwargs.pop("Order", None)
        req.OrderField = kwargs.pop("OrderField", None)
        req.ReturnBindAutoSnapshotPolicy = kwargs.pop("ReturnBindAutoSnapshotPolicy", None)
        filters = model.Filter()
        for k, v in kwargs.items():
            filters.Name = k
            filters.Values = v
        req._Filters = [filters]
        req.Offset = 0
        req.Limit = 50
        return req

    def list_disks(self, ids=None, **kwargs):
        """
        获取云盘列表
        :param kwargs: tcloud DescribeDisksRequest api param, see https://cloud.tencent.com/document/api
        """
        request = self._set_datastore_info_params(**kwargs)
        if ids:
            request.DiskIds = convert_param_to_list(ids)
        return self._handle_list_request("cbs_client", request, "disk", True)

    def create_disk(self, **kwargs):
        """
        创建云硬盘
        :param kwargs:tcloud CreateDiskRequest api param, see https://cloud.tencent.com/document/api
        :return:云盘id
        """
        try:
            client = self.cbs_client
            model = cbs_models
            req = model.CreateDisksRequest()
            req.DiskType = kwargs["DiskType"]
            req.DiskSize = kwargs["DiskSize"]
            # req.DiskChargeType = "POSTPAID_BY_HOUR"
            req.DiskChargeType = kwargs["PaidModal"]
            if req.DiskChargeType == "PREPAID":
                req.DiskChargePrepaid = {"Period": kwargs["Period"]}
            else:
                req.DiskChargeType = "POSTPAID_BY_HOUR"
            req.Placement = {"Zone": kwargs["ZoneId"]}
            list_optional_params = ["DiskName", "DiskCount", "SnapshotId", "Encrypt"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.CreateDisks(req)
            return {"result": True, "data": resp.DiskIdSet}
        except TencentCloudSDKException as e:
            logger.exception("create_disk")
            return {"result": False, "message": e.message}

    def attach_disk(self, **kwargs):
        """
        挂载云硬盘
        :param kwargs:tcloud AttachDisksRequest api param, see https://cloud.tencent.com/document/api
        """
        try:
            client = self.cbs_client
            model = cbs_models
            req = model.AttachDisksRequest()
            req.InstanceId = kwargs["InstanceId"]
            req.DiskIds = kwargs["DiskIds"]
            req.DeleteWithInstance = True
            client.AttachDisks(req)
            return {"result": True}
        except TencentCloudSDKException as e:
            logger.exception("attach_disk:InstanceId({}),DiskIds({})".format(kwargs["InstanceId"], kwargs["DiskIds"]))
            return {"result": False, "message": e.message}

    def detach_disk(self, **kwargs):
        """
        解挂云硬盘。
        :param kwargs:
                    DiskIds：类型：list of str。必选。描述：将要解挂的云硬盘ID
        :return:
        """
        try:
            client = self.cbs_client
            model = cbs_models
            req = model.DetachDisksRequest()
            req.DiskIds = kwargs["DiskIds"]
            client.DetachDisks(req)
            return {"result": True}
        except Exception as e:
            logger.exception("detach_disks:" + kwargs["DiskIds"])
            return {"result": False, "message": str(e)}

    def delete_disk(self, disk_ids):
        """
        退还云硬盘
        :param disk_ids: tcloud TerminateDisksRequest api param, see https://cloud.tencent.com/document/api
        """
        try:
            client = self.cbs_client
            model = cbs_models
            req = model.TerminateDisksRequest()
            req.DiskIds = disk_ids
            client.TerminateDisks(req)
            return {"result": True}
        except TencentCloudSDKException as e:
            logger.exception("destroy disk(DiskIds): {}".format(disk_ids))
            return {"result": False, "message": e.message}

    def add_vm_disk(self, **kwargs):
        """
         绑定磁盘
        :param kwargs:
        :return:
        """
        try:
            disk_type_raw = kwargs["config"][0]
            if disk_type_raw == "普通磁盘":
                disk_type = "CLOUD_BASIC"
            elif disk_type_raw == "固态磁盘":
                disk_type = "CLOUD_SSD"
            else:
                disk_type = "CLOUD_PREMIUM"
            kwargs["DiskType"] = disk_type
            kwargs["DiskSize"] = int(kwargs["config"][1])
            new_disk = self.create_disk(**kwargs)
            if new_disk["result"]:
                kwargs["DiskIds"] = new_disk["data"]
            else:
                return new_disk
            attach_result = self.attach_disk(**kwargs)
            if attach_result:
                return {"result": True}
            else:
                self.delete_disk(kwargs["DiskIds"])
                return {"result": False, "message": "主机不支持绑定改类型磁盘"}
        except Exception as e:
            logger.exception("add_vm_disk")
            return {"result": False, "message": str(e)}

    def resize_instance_disks(self, **kwargs):
        """
            扩容实例的数据盘。
            目前只支持扩容非弹性数据盘（DescribeDisks接口返回值中的Portable为false表示非弹性），且数据盘类型
        为：CLOUD_BASIC、CLOUD_PREMIUM、CLOUD_SSD和CDH实例的LOCAL_BASIC、LOCAL_SSD类型数据盘。
            对于包年包月实例，使用该接口会涉及扣费，请确保账户余额充足。
            目前只支持扩容一块数据盘。
            :param kwargs:
                        InstanceId：类型：String。必选。描述：待操作的实例ID。
                        DataDisks：类型：Array of DataDisk。必选。描述：待扩容的数据盘配置信息。
                        ForceStop：类型：String。描述：是否对运行中的实例选择强制关机
            :return:
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.ResizeInstanceDisksRequest()
            req.InstanceId = kwargs["InstanceId"]
            req.DataDisks = kwargs["DataDisks"]
            if "ForceStop" in kwargs:
                req.ForceStop = kwargs["ForceStop"]
            client.ResizeInstanceDisks(req)
            return {"result": True}
        except Exception as e:
            logger.exception("resize_instance_disks:" + kwargs["InstanceId"])
            return {"result": False, "message": str(e)}

    def resize_disk(self, **kwargs):
        """
        接口请求域名： cbs.tencentcloudapi.com
        本接口（ResizeDisk）用于扩容云硬盘。
        只支持扩容弹性云盘。云硬盘类型可以通过DescribeDisks接口查询，见输出参数中Portable字段解释。
        随云主机创建的云硬盘需通过ResizeInstanceDisks接口扩容。随主机一起购买的云硬盘也可以用这个（20201012测试）
        本接口为异步接口，接口成功返回时，云盘并未立即扩容到指定大小，可通过接口DescribeDisks来查询对应云盘的状态，
        如果云盘的状态为“EXPANDING”，表示正在扩容中。
        Args:
            **kwargs ():
                DiskId (str): 云硬盘id
                DiskSize (int): 云硬盘扩容后的大小。必须大于当前云硬盘大小

        Returns (dict):
            {result: bool}

        """
        try:
            client = self.cbs_client
            model = cbs_models
            req = model.ResizeDiskRequest()
            req.DiskId = kwargs["DiskId"]
            req.DiskSize = kwargs["DiskSize"]
            client.ResizeDisk(req)
            return {"result": True}
        except Exception as e:
            logger.exception("resize_disk:" + kwargs["DiskId"])
            return {"result": False, "message": str(e)}

    #  ----------------快照-------------------------

    def restore_snapshot(self, disk_id, snapshot_id):
        """
        回滚快照
        :param disk_id: 类型：String。必选。描述：快照原云硬盘ID
        :param snapshot_id: 类型：String。必选。描述：快照ID
        :return:
        """
        try:
            client = self.cbs_client
            model = cbs_models
            req = model.ApplySnapshotRequest()
            req.SnapshotId = snapshot_id
            req.DiskId = disk_id
            client.ApplySnapshot(req)
            return {"result": True}
        except Exception as e:
            logger.exception("apply_snapshot: {}".format(snapshot_id))
            return {"result": False, "message": str(e)}

    def create_snapshot(self, **kwargs):
        """
        创建快照
        :param kwargs:
        -------------------
        * SnapshotName：the name of snapshot.(optional)
                        type: str
        * DiskId：the id of disk.(required)
                  type: str
        ---------------------
        :return:
        """
        try:
            client = self.cbs_client
            models = cbs_models
            req = models.CreateSnapshotRequest()
            req.DiskId = kwargs["DiskId"]
            req.SnapshotName = kwargs["SnapshotName"]

            resp = client.CreateSnapshot(req)
            return {"result": True, "data": resp.SnapshotId}
        except Exception as e:
            logger.exception("create_snapshot:" + kwargs["DiskId"])
            return {"result": False, "message": str(e)}

    def list_snapshots(self, ids=None, **kwargs):
        """
        查询快照详情列表
        :param kwargs:
                    SnapshotIds：类型：list of str。描述：要查询快照的ID列表。参数不支持同时指定`SnapshotIds`和`_Filters`。
                    _Filters：类型：list of Filter。描述：过滤条件。参数不支持同时指定`SnapshotIds`和`_Filters`。
                    Offset：类型：int。描述：偏移量，默认为0。
                    Limit：类型：int。描述：返回数量，默认为20，最大值为100。
                    Order：类型：String。描述：输出云盘列表的排列顺序。取值范围：<br><li>ASC：升序排列<br><li>DESC：降序排列。
                    OrderField：类型：String。描述：快照列表排序的依据字段。取值范围：<br><li>CREATE_TIME：依据快照的
                创建时间排序<br>默认按创建时间排序。
        :return:   data输出示例：
                        {
                          "Response": {
                            "TotalCount": 2,
                            "RequestId": "4ab150b9-538d-48fb-8821-7fa185f1d07c",
                            "SnapshotSet": [
                              {
                                "Placement": {
                                  "ProjectId": 0,
                                  "Zone": "ap-guangzhou-2"
                                },
                                "CopyFromRemote": false,
                                "IsPermanent": false,
                                "DiskUsage": "DATA_DISK",
                                "DeadlineTime": "2019-07-15 00:00:00",
                                "Percent": 100,
                                "SnapshotId": "snap-lfo71d1x",
                                "ShareReference": 0,
                                "SnapshotType": "PRIVATE_SNAPSHOT",
                                "DiskSize": 10,
                                "DiskId": "disk-aq3k1jn0",
                                "SnapshotName": "auto_disk-aq3k1jn0_20190708_00",
                                "Images": [],
                                "CopyingToRegions": [],
                                "Encrypt": false,
                                "CreateTime": "2019-07-08 00:03:13",
                                "ImageCount": 0,
                                "SnapshotState": "NORMAL"
                              },
                              {
                                "Placement": {
                                  "ProjectId": 0,
                                  "Zone": "ap-guangzhou-2"
                                },
                                "CopyFromRemote": false,
                                "IsPermanent": false,
                                "DiskUsage": "DATA_DISK",
                                "DeadlineTime": "2019-07-15 00:00:00",
                                "Percent": 100,
                                "SnapshotId": "snap-jt5npvml",
                                "ShareReference": 0,
                                "SnapshotType": "PRIVATE_SNAPSHOT",
                                "DiskSize": 10,
                                "DiskId": "disk-38hlz2p0",
                                "SnapshotName": "auto_disk-38hlz2p0_20190708_00",
                                "Images": [],
                                "CopyingToRegions": [],
                                "Encrypt": false,
                                "CreateTime": "2019-07-08 00:03:10",
                                "ImageCount": 0,
                                "SnapshotState": "NORMAL"
                              }
                            ]
                          }
                        }
        """
        request = cbs_models.DescribeSnapshotsRequest()
        if ids:
            request.SnapshotIds = convert_param_to_list(ids)
        list_optional_params = ["SnapshotIds", "_Filters", "Offset", "Limit", "Order", "OrderField"]
        request = set_optional_params(request, list_optional_params, kwargs)
        return self._handle_list_request("cbs_client", request, "snapshot", True)

    def delete_snapshot(self, snapshot_ids):
        """
        删除快照
        :param snapshot_ids: 类型：list of str。必选。描述：要删除的快照ID列表.
        :return:
        """
        try:
            client = self.cbs_client
            model = cbs_models
            req = model.DeleteSnapshotsRequest()
            req.SnapshotIds = snapshot_ids
            client.DeleteSnapshots(req)
            return {"result": True}
        except Exception as e:
            logger.exception("delete_snapshots: {}".format(snapshot_ids))
            return {"result": False, "message": str(e)}

    def list_auto_snapshot_policy(self, ids=None, **kwargs):
        """查询已创建的自动快照策略"""
        request = cbs_models.DescribeAutoSnapshotPoliciesRequest()
        if ids:
            request.AutoSnapshotPolicyIds = convert_param_to_list(ids)
        list_optional_params = ["AutoSnapshotPolicyIds", "_Filters", "Offset", "Limit", "Order", "OrderField"]
        request = set_optional_params(request, list_optional_params, kwargs)
        return self._handle_list_request("cbs_client", request, "auto_snapshot_policy", True)

    def create_auto_snapshot_policy(self, **kwargs):
        """创建定期快照策略"""
        try:
            required_list = ["Policy"]
            checkout_required_parameters(required_list, kwargs)
            client = self.cbs_client
            req = cbs_models.CreateAutoSnapshotPolicyRequest()
            list_optional_params = [
                "Policy",
                "AutoSnapshotPolicyName",
                "IsActivated",
                "IsPermanent",
                "RetentionDays",
                "DryRun",
            ]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.CreateAutoSnapshotPolicy(req)
            return {"result": True, "data": resp.AutoSnapshotPolicyId}
        except Exception as e:
            logger.exception("fail create_auto_snapshot_policy:")
            return {"result": False, "message": str(e)}

    def delete_auto_snapshot_policy(self, ids, **kwargs):
        """批量删除定期快照策略"""
        try:
            auto_snapshot_policy_ids = ids if isinstance(ids, list) else [ids]
            client = self.cbs_client
            req = cbs_models.DeleteAutoSnapshotPoliciesRequest()
            req.AutoSnapshotPolicyIds = auto_snapshot_policy_ids
            resp = client.DeleteAutoSnapshotPolicies(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail delete_auto_snapshot_policy:")
            return {"result": False, "message": str(e)}

    def apply_auto_snapshot_policy(self, **kwargs):
        """绑定定期快照策略"""
        try:
            client = self.cbs_client
            required_list = ["AutoSnapshotPolicyId", "DiskIds"]
            checkout_required_parameters(required_list, kwargs)
            req = cbs_models.BindAutoSnapshotPolicyRequest()
            req = set_optional_params(req, required_list, kwargs)
            resp = client.BindAutoSnapshotPolicy(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail apply_auto_snapshot_policy:" + kwargs["AutoSnapshotPolicyId"])
            return {"result": False, "message": str(e)}

    def cancel_auto_snapshot_policy(self, **kwargs):
        """解绑定期快照策略"""
        try:
            client = self.cbs_client
            req = cbs_models.UnbindAutoSnapshotPolicyRequest()
            required_list = ["AutoSnapshotPolicyId", "DiskIds"]
            checkout_required_parameters(required_list, kwargs)
            req = set_optional_params(req, required_list, kwargs)
            resp = client.UnbindAutoSnapshotPolicy(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail cancel_auto_snapshot_policy:" + kwargs["AutoSnapshotPolicyId"])
            return {"result": False, "message": str(e)}

    #  ---------------------对象存储------------------------

    def list_buckets(self):
        """
        查询存储桶列表
        :param kwargs:
        :return:
        """
        data = []
        try:
            client = self.cosS3_client
            resp = client.list_buckets()
        except Exception as e:
            logger.exception("list_buckets")
            return {"result": False, "message": str(e)}
        if not resp.get("Buckets"):
            return {"result": True, "data": data}
        qcloud_result = resp["Buckets"]["Bucket"]
        format_method = get_format_method(self.cloud_type, "bucket")
        for i in qcloud_result:
            # 仅显示同区域存储桶  非同区域存储桶无法获取桶类型。即下方接口调用会报错
            if i["Location"] != self.region_id:
                continue
            list_objects = client.list_objects_versions(i.get("Name", "")).get("Version")
            bucket_type = list_objects[0].get("StorageClass") if list_objects else ""
            size = 0
            for file in list_objects:
                size += float(file["Size"])
            size = round(size / 1024 / 1024, 2)
            data.append(format_method(i, bucket_type=bucket_type, size=size))
        return {"result": True, "data": data}

    def create_bucket(self, name):
        """
        创建存储桶
        :param name:存储桶名称.
        :return:
        """
        try:
            client = self.cosS3_client
            client.create_bucket(name=name)
            return {"result": True}
        except Exception as e:
            logger.exception("create_bucket")
            return {"result": False, "message": str(e)}

    def delete_bucket(self, name):
        """
        删除一个bucket，bucket必须为空
        :param name:存储桶名称.
        :return:
        """
        try:
            client = self.cosS3_client
            client.delete_bucket(name=name)
            return {"result": True}
        except Exception as e:
            logger.exception("delete_bucket")
            return {"result": False, "message": str(e)}

    def list_bucket_file(self, bucket_name, location):
        """
        查询存储桶对象
        :param kwargs:
        :return:
        """
        data = []
        try:
            client = self.cosS3_client
            file_path = ""
            resp = client.list_objects(Bucket=bucket_name, Prefix=file_path)
        except Exception as e:
            logger.exception("list_bucket_file")
            return {"result": False, "message": str(e)}
        if not resp.get("Contents"):
            return {"result": True, "data": data}
        qcloud_result = resp["Contents"]
        format_method = get_format_method(self.cloud_type, "bucket_file")
        for item in qcloud_result:
            if item["Key"].endswith("/"):
                item["type"] = "DIR"
                item["parent"] = "/".join(item["Key"].split("/")[:-2]) if "/" in item["Key"].strip("/") else ""
                item["name"] = item["Key"].split("/")[-2]
            else:
                item["type"] = "FILE"
                item["parent"] = "/".join(item["Key"].split("/")[:-1]) if "/" in item["Key"] else ""
                item["name"] = item["Key"].split("/")[-1]
        top_dir_list = [item for item in qcloud_result if item["parent"] == "" and item["type"] == "DIR"]
        for top_dir in top_dir_list:
            set_dir_size_qcloud(top_dir, qcloud_result)
        ali_result = [format_method(item, bucket=bucket_name, location=location) for item in qcloud_result]
        return {"result": True, "data": ali_result}

    # ********************************网络****************************

    # ---------------------VPC------------------------
    def create_vpc(self, **kwargs):
        """
        创建VPC
        :param kwargs:
                VpcName：类型：String。必选。描述：vpc名称，最大长度不能超过60个字节。
                CidrBlock：类型：String。必选。描述：vpc的cidr，只能为10.0.0.0/16，172.16.0.0/12，192.168.0.0/16这三个内网网段内。
                EnableMulticast：类型：String。描述：是否开启组播。true: 开启, false: 不开启。
                DnsServers：类型：list of str。描述：DNS地址，最多支持4个
                DomainName：类型：String。描述：域名
                Tags：类型：list of Tag。描述：指定绑定的标签列表，例如：[{"Key": "city", "Value": "shanghai"}]
        :return:        data输出示例：
                        {
                          "Response": {
                            "RequestId": "354f4ac3-8546-4516-8c8a-69e3ab73aa8a",
                            "Vpc": {
                              "VpcId": "vpc-4tboefn3",
                              "VpcName": "TestVPC",
                              "EnableMulticast": false,
                              "CidrBlock": "10.8.0.0/16",
                              "TagSet": [
                                {
                                  "Key": "city",
                                  "Value": "shanghai"
                                }
                              ]
                            }
                          }
                        }
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.CreateVpcRequest()
            req.VpcName = kwargs["VpcName"]
            req.CidrBlock = kwargs["CidrBlock"]
            list_optional_params = ["EnableMulticast", "DnsServers", "DomainName", "Tags"]
            req = set_optional_params(req, list_optional_params, kwargs)
            data = client.CreateVpc(req).Vpc.VpcId
            return {"result": True, "data": data}
        except Exception as e:
            logger.exception("create_vpc")
            return {"result": False, "message": str(e)}

    def delete_vpc(self, vpc_id):
        """
            删除私有网络。
            删除前请确保 VPC 内已经没有相关资源，例如云服务器、云数据库、NoSQL、VPN网关、专线网关、负载均衡、对等连接、
        与之互通的基础网络设备等。
            :param vpc_id:  VPC实例ID。
            :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.DeleteVpcRequest()
            req.VpcId = vpc_id
            client.DeleteVpc(req)
            return {"result": True}
        except Exception as e:
            logger.exception("delete_vpc")
            return {"result": False, "message": str(e)}

    def list_vpcs(self, ids=None, **kwargs):
        """
        查看VPC列表
        :param kwargs:tcloud DescribeVpcsRequest api param, see https://cloud.tencent.com/document/api
        """
        request = vpc_models.DescribeVpcsRequest()
        if ids:
            request.VpcIds = convert_param_to_list(ids)
        filters = vpc_models.Filter()
        for k, v in kwargs.items():
            if k == "host_id":
                v = convert_param_to_list(v)
            filters.Name = k
            filters.Values = v
        request._Filters = [filters]
        return self._handle_list_request("vpc_client", request, "vpc", True)

    # ---------------------路由表------------------------
    def list_route_tables(self, ids=None, **kwargs):
        """查询路由列表"""
        if ids:
            kwargs["RouteTableIds"] = ids
        req = vpc_models.DescribeRouteTablesRequest()
        list_optional_params = ["_Filters", "RouteTableIds", "Offset", "Limit"]
        request = set_optional_params(req, list_optional_params, kwargs)
        return self._handle_list_request("vpc_client", request, "route_table", True)

    def create_route_table(self, **kwargs):
        """创建路由表"""
        try:
            required_list = ["VpcId", "RouteTableName"]
            checkout_required_parameters(required_list, kwargs)
            client = self.vpc_client
            req = vpc_models.CreateRouteTableRequest()
            list_optional_params = ["VpcId", "RouteTableName", "Tags"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.CreateRouteTable(req)
            return {"result": True, "data": resp.RouteTable.RouteTableId}
        except Exception as e:
            logger.exception("fail create_route_table")
            return {"result": False, "message": str(e)}

    def delete_route_table(self, rt_id):
        """删除路由表"""
        try:
            client = self.vpc_client
            req = vpc_models.DeleteRouteTableRequest()
            req.LoadBalancerIds = rt_id
            resp = client.DeleteRouteTable(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail delete_route_table")
            return {"result": False, "message": str(e)}

    def modify_route_table(self, **kwargs):
        """修改路由表属性"""
        try:
            required_list = ["RouteTableId", "RouteTableName"]
            checkout_required_parameters(required_list, kwargs)
            client = self.vpc_client
            req = vpc_models.ModifyRouteTableAttributeRequest()
            list_optional_params = required_list
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.ModifyRouteTableAttribute(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail modify_route_table")
            return {"result": False, "message": str(e)}

    # ---------------------路由表策略------------------------
    def list_route_entry(self, **kwargs):
        """查询路由策略列表"""
        try:
            if "RouteTableIds" not in kwargs:
                kwargs["RouteTableIds"] = [kwargs.get("RouteTableId")] if kwargs.get("RouteTableId") else []
            client = self.vpc_client
            req = vpc_models.DescribeRouteTablesRequest()
            list_optional_params = ["RouteTableIds", "_Filters", "Offset", "Limit"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.DescribeRouteTables(req)
            data = self.__parse_result(resp.RouteTableSet[0].RouteSet, "route_entry", **kwargs)
            # data = self.__parse_result(resp.RouteTableSet, "route_entry", **kwargs)
            return {"result": True, "data": data}
        except Exception as e:
            logger.exception("fail list_route_table_entry")
            return {"result": False, "message": str(e)}

    def create_route_table_entry(self, **kwargs):
        """创建路由策略"""
        try:
            required_list = ["RouteTableId"]
            checkout_required_parameters(required_list, kwargs)
            client = self.vpc_client
            req = vpc_models.CreateRoutesRequest()
            list_optional_params = ["RouteTableId", "Routes"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.CreateRoutes(req)
            data = resp.RouteTableSet.RouteSet[0].RouteItemId
            if kwargs.get("RouteItemId"):
                route_item_id = kwargs.get("RouteItemId")
                data = [item for item in data if item.resource_id == route_item_id]
            return {"result": True, "data": data}
        except Exception as e:
            logger.exception("fail create_route_table_entry")
            return {"result": False, "message": str(e)}

    def delete_route_table_entry(self, rt_id, routes, **kwargs):
        """删除路由策略"""
        try:
            client = self.vpc_client
            req = vpc_models.DeleteRoutesRequest()
            req.RouteTableId = rt_id
            req.Routes = routes if isinstance(routes, list) else [routes]
            resp = client.DeleteRoutes(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail delete_route_table")
            return {"result": False, "message": str(e)}

    # -------------------子网---------------------
    def create_subnet(self, **kwargs):
        """
            创建子网。子网创建成功后，子网网段不能修改。子网网段必须在VPC网段内，可以和VPC网段相同（VPC有且只有一个子网时），
        建议子网网段在VPC网段内，预留网段给其他子网使用。
            :param kwargs:
                        VpcId：类型：String。必选。描述：待操作的VPC实例ID。可通过DescribeVpcs接口返回值中的VpcId获取。
                        SubnetName：类型：String。必选。描述：子网名称，最大长度不能超过60个字节。
                        CidrBlock：类型：String。必选。描述：子网网段，子网网段必须在VPC网段内，相同VPC内子网网段不能重叠。
                        Zone：类型：String。必选。描述：子网所在的可用区ID，不同子网选择不同可用区可以做跨可用区灾备。
            :return:    data输出示例：
                        {
                          "Response": {
                            "RequestID": "354f4ac3-8546-4516-8c8a-69e3ab73aa8a",
                            "Subnet": {
                              "VpcId": "vpc-m3ul053f",
                              "IsDefault": false,
                              "SubnetName": "TestSubnet",
                              "Zone": "ap-guangzhou-1",
                              "SubnetId": "subnet-2qhl25io",
                              "CidrBlock": "10.8.255.0/24",
                              "TotalIpAddressCount": 253,
                              "AvailableIpAddressCount": 253,
                              "TagSet": [
                                {
                                  "Key": "city",
                                  "Value": "shanghai"
                                }
                              ]
                            }
                          }
                        }
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.CreateSubnetRequest()
            list_required_params = ["VpcId", "SubnetName", "CidrBlock", "Zone"]
            set_required_params(req, list_required_params, kwargs)
            data = client.CreateSubnet(req).Subnet.SubnetId
            return {"result": True, "data": data}
        except Exception as e:
            logger.exception("create_subnet")
            return {"result": False, "message": str(e)}

    def delete_subnet(self, **kwargs):
        """
        删除子网。删除子网前，请清理该子网下所有资源，包括云服务器、负载均衡、云数据、noSql、弹性网卡等资源。
        :param kwargs:
                    subnet_id：类型：String。必选。描述：子网实例ID。可通过DescribeSubnets接口返回值中的SubnetId获取。
        :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.DeleteSubnetRequest()
            req.SubnetId = kwargs["subnet_id"]
            client.DeleteSubnet(req)
            return {"result": True}
        except Exception as e:
            logger.exception("delete_subnet:" + kwargs["subnet_id"])
            return {"result": False, "message": str(e)}

    def list_subnets(self, ids=None, **kwargs):
        """
        获取交换机信息
        :param kwargs:tcloud DescribeSubnetsRequest api param, see https://cloud.tencent.com/document/api
        """
        request = vpc_models.DescribeSubnetsRequest()
        if ids:
            request.SubnetIds = convert_param_to_list(ids)
        filters = vpc_models.Filter()
        for k, v in kwargs.items():
            filters.Name = k
            filters.Values = v
        request._Filters = [filters]
        return self._handle_list_request("vpc_client", request, "subnet", True)

    # ------------------弹性公网---------------------

    def create_eip(self, **kwargs):
        """
        创建弹性公网IP。 腾讯云目前仅支持POSTPAID_BY_HOUR一种计费模式 调接口时不传递参数
        :param kwargs:
                    AddressCount：类型：Integer。描述：EIP数量。默认值：1。
                    InternetServiceProvider：类型：String。描述：EIP线路类型。默认值：BGP。
                    InternetChargeType：类型：String。描述：EIP计费方式。
                    InternetMaxBandwidthOut：类型：Integer。描述：EIP出带宽上限，单位：Mbps。
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
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.AllocateAddressesRequest()
            list_optional_params = [
                "AddressCount",
                "InternetServiceProvider",
                "InternetChargeType",
                "InternetMaxBandwidthOut",
                "AddressType",
                "AnycastZone",
                "BandwidthPackageId",
            ]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.AllocateAddresses(req)
            return {"result": True, "data": resp.AddressSet[0]}
        except Exception as e:
            logger.exception("create_eip")
            return {"result": False, "message": str(e)}

    def associate_address(self, **kwargs):
        """
        将弹性公网IP（简称 EIP）绑定到实例或弹性网卡的指定内网 IP 上。
        :param kwargs:
                    AddressId：类型：String。必选。描述：标识 EIP 的唯一 ID。EIP 唯一 ID 形如：`eip-11112222`。
                    InstanceId：类型：String。描述：要绑定的实例 ID。
                    NetworkInterfaceId：类型：String。描述：要绑定的弹性网卡 ID。
                    PrivateIpAddress：类型：String。描述：要绑定的内网 IP。
        :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.AssociateAddressRequest()
            req.AddressId = kwargs["eip_id"]
            if "instance_id" in kwargs:
                req.InstanceId = kwargs["instance_id"]
            list_optional_params = ["InstanceId", "NetworkInterfaceId", "PrivateIpAddress"]
            req = set_optional_params(req, list_optional_params, kwargs)
            client.AssociateAddress(req)
            return {"result": True}
        except Exception as e:
            logger.exception("associate_address")
            return {"result": False, "message": str(e)}

    def disassociate_address(self, **kwargs):
        """
        解绑弹性公网IP（简称 EIP）
        :param kwargs:
                    AddressId：类型：String。必选。描述：标识 EIP 的唯一 ID。
                    ReallocateNormalPublicIp：类型：bool。描述：表示解绑 EIP 之后是否分配普通公网 IP。
        :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.DisassociateAddressRequest()
            req.AddressId = kwargs["eip_id"]
            if "ReallocateNormalPublicIp" in kwargs:
                req.ReallocateNormalPublicIp = kwargs["ReallocateNormalPublicIp"]
            client.DisassociateAddress(req)
            return {"result": True}
        except Exception as e:
            logger.exception("disassociate_address：" + kwargs["eip_id"])
            return {"result": False, "message": str(e)}

    def release_eip(self, eip_id):
        """
        释放弹性公网IP
        :param eip_id:
                   eip_id：类型： str。必选。描述：标识 EIP 的唯一 ID 列表。
        :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.ReleaseAddressesRequest()
            id_list = [eip_id]
            req.AddressIds = id_list
            client.ReleaseAddresses(req)
            return {"result": True}
        except Exception as e:
            logger.exception("release_eip")
            return {"result": False, "message": str(e)}

    def list_eips(self, ids=None, **kwargs):
        """
        获取外网信息
        :param kwargs:tcloud DescribeAddressesRequest api param, see https://cloud.tencent.com/document/api
        """
        request = vpc_models.DescribeAddressesRequest()
        if ids:
            request.AddressIds = convert_param_to_list(ids)
        filters = vpc_models.Filter()
        for k, v in kwargs.items():
            filters.Name = k
            filters.Values = v
        request._Filters = [filters]
        return self._handle_list_request("vpc_client", request, "eip", True)

    def modify_eip_band_width(self, **kwargs):
        """
        调整弹性公网ip带宽
         :param kwargs:
               eip_id: str , 弹性公网id
               bandwidth: str , 调整带宽目标值
        """
        try:
            instance_id = self.get_eip_info(eip_id=kwargs.get("eip_id"))["data"][0]["band_instance_id"]
            client = self.cvm_client
            model = cvm_models
            req = model.ResetInstancesInternetMaxBandwidthRequest()
            req.InstanceIds = [instance_id]
            internetAccessible = model.InternetAccessible()
            internetAccessible.InternetMaxBandwidthOut = int(kwargs["bandwidth"])
            req.InternetAccessible = internetAccessible
            client.ResetInstancesInternetMaxBandwidth(req)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_eip_band_width")
            return {"result": False, "message": e.message}

    # --------------安全组----------------------

    def list_security_groups(self, ids=None, **kwargs):
        """
        查看安全组
        :param kwargs: tcloud DescribeSecurityGroupsRequest api param, see https://cloud.tencent.com/document/api
        """
        request = vpc_models.DescribeSecurityGroupsRequest()
        if ids:
            request.SecurityGroupIds = convert_param_to_list(ids)
        filters = vpc_models.Filter()
        for k, v in kwargs.items():
            filters.Name = k
            filters.Values = v
        request._Filters = [filters]
        return self._handle_list_request("vpc_client", request, "security_group", True)

    def create_security_group(self, **kwargs):
        """
        创建安全组
        :param kwargs:
             GroupName：类型：String。必选。描述：安全组名称
             GroupDescription: 类型：String。必选。描述：安全组描述
        :type kwargs:
        :return:
        :rtype:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.CreateSecurityGroupRequest()
            req.GroupName = kwargs["GroupName"]
            req.GroupDescription = kwargs["GroupDescription"]
            res = client.CreateSecurityGroup(req)
            qcloud_result = json.loads(res.to_json_string())
            return {"result": True, "data": qcloud_result["SecurityGroup"]["SecurityGroupId"]}
        except Exception as e:
            logger.exception("create_security_group")
            return {"result": False, "message": str(e)}

    def delete_security_group(self, security_group_id):
        """
        删除安全组
        security_group_id:
             类型：String。必选。描述：安全组id
        :type kwargs:
        :return: result: True, "data": {"RequestId":""}
        :rtype:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.DeleteSecurityGroupRequest()
            req.SecurityGroupId = security_group_id
            res = client.DeleteSecurityGroup(req)
            qcloud_result = json.loads(res.to_json_string())
            return {"result": True, "data": qcloud_result}
        except Exception as e:
            logger.exception("create_security_group")
            return {"result": False, "message": str(e)}

    def associate_security_groups(self, **kwargs):
        """
        绑定安全组到指定实例。
        :param kwargs:
                    SecurityGroupIds：类型：list of str。必选。要绑定的`安全组ID`，类似sg-efil73jd，只支持绑定单个安全组。
                    InstanceIds：类型：list of str。必选。被绑定的`实例ID`，类似ins-lesecurk，支持指定多个实例。
        :return:
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.AssociateSecurityGroupsRequest()
            req.SecurityGroupIds = kwargs["SecurityGroupIds"]
            req.InstanceIds = kwargs["InstanceIds"]
            client.AssociateSecurityGroups(req)
            return {"result": True}
        except Exception as e:
            logger.exception("associate_security_groups")
            return {"result": False, "message": str(e)}

    def disassociate_security_groups(self, **kwargs):
        """
        解绑实例的指定安全组。
        :param kwargs:
                    SecurityGroupIds：类型：list of str。必选。要解绑的`安全组ID`，类似sg-efil73jd，只支持解绑单个安全组。
                    InstanceIds：类型：list of str。必选。被解绑的`实例ID`，类似ins-lesecurk，支持指定多个实例。
        :return:
        """
        try:
            client = self.cvm_client
            model = cvm_models
            req = model.DisassociateSecurityGroupsRequest()
            req.SecurityGroupIds = kwargs["SecurityGroupIds"]
            req.InstanceIds = kwargs["InstanceIds"]
            client.DisassociateSecurityGroups(req)
            return {"result": True}
        except Exception as e:
            logger.exception("disassociate_security_groups")
            return {"result": False, "message": str(e)}

    def modify_security_group_attribute(self, **kwargs):
        """
        修改安全组属性
        :param kwargs:
                    SecurityGroupId：类型：String。必选。描述：安全组实例ID
                    GroupName：类型：String。描述：安全组名称，可任意命名，但不得超过60个字符。
                    GroupDescription：类型：String。描述：安全组备注，最多100个字符。
        :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.ModifySecurityGroupAttributeRequest()
            req.SecurityGroupId = kwargs["SecurityGroupId"]
            list_optional_params = ["GroupName", "GroupName"]
            req = set_optional_params(req, list_optional_params, kwargs)
            client.ModifySecurityGroupAttribute(req)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_security_group_attribute")
            return {"result": False, "message": str(e)}

    def list_security_group_rules(self, security_group_id, **kwargs):
        """
                查询安全组规则
        `       security_group_id：类型：str。必选。描述：安全组实例ID
                :return:  data输出示例：
                            {
                              "Response": {
                                "SecurityGroupPolicySet": {
                                  "Ingress": [
                                    {
                                      "PolicyIndex": 0,
                                      "Direction": "INGRESS",
                                      "ServiceTemplate": {
                                        "ServiceId": "ppm-f5n1f8da"
                                      },
                                      "AddressTemplate": {
                                        "AddressGroupId": "ipmg-2uw6ujo6"
                                      },
                                      "Action": "ACCEPT",
                                      "ModifyTime": "2017-03-12 10:00:00",
                                      "PolicyDescription": "ModifyPolicies"
                                    },
                                    {
                                      "PolicyIndex": 1,
                                      "Direction": "INGRESS",
                                      "ServiceTemplate": {
                                        "ServiceId": "ppm-f5n1f8da"
                                      },
                                      "AddressTemplate": {
                                        "AddressGroupId": "ipmg-2uw6ujo6"
                                      },
                                      "Action": "ACCEPT",
                                      "ModifyTime": "2017-03-12 10:00:00",
                                      "PolicyDescription": "2"
                                    }
                                  ],
                                  "Egress": [
                                    {
                                      "PolicyIndex": 0,
                                      "Direction": "EGRESS",
                                      "ServiceTemplate": {
                                        "ServiceId": "ppm-f5n1f8da"
                                      },
                                      "AddressTemplate": {
                                        "AddressGroupId": "ipmg-2uw6ujo6"
                                      },
                                      "Action": "ACCEPT",
                                      "ModifyTime": "2017-03-12 10:00:00",
                                      "PolicyDescription": "E1"
                                    }
                                  ],
                                  "Version": 60
                                },
                                "RequestId": "74883e1b-5901-46de-ae1e-d6e2cf591c5b"
                              }
                            }
        """
        if not security_group_id:
            return {"result": False, "message": "安全组id不能为空"}
        client = self.vpc_client
        request = vpc_models.DescribeSecurityGroupPoliciesRequest()
        request.SecurityGroupId = security_group_id
        data = []
        format_method = get_format_method(self.cloud_type, "security_group_rule")
        try:
            resp = client.DescribeSecurityGroupPolicies(request)
        except Exception as e:
            logger.exception("get_security_group_rule")
            return {"result": False, "message": str(e)}
        data.extend(
            [
                format_method(i, direction="Egress", security_group_id=security_group_id)
                for i in resp.SecurityGroupPolicySet.Egress
            ]
        )
        data.extend(
            [
                format_method(j, direction="Ingress", security_group_id=security_group_id)
                for j in resp.SecurityGroupPolicySet.Ingress
            ]
        )
        return {"result": True, "data": data}

    def create_security_group_rules(self, **kwargs):
        """
        安全组添加规则
        :param kwargs:
                    SecurityGroupId：类型：String。必选。描述：安全组实例ID
                    SecurityGroupPolicySet：类型：class:`tencentcloud.vpc.v20170312.models.SecurityGroupPolicySet`。必选。
                描述：安全组规则集合。
        :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.CreateSecurityGroupPoliciesRequest()
            req.SecurityGroupId = kwargs["SecurityGroupId"]
            req.SecurityGroupPolicySet = kwargs["SecurityGroupPolicySet"]
            client.CreateSecurityGroupPolicies(req)
            return {"result": True}
        except Exception as e:
            logger.exception("create_security_group_rules")
            return {"result": False, "message": str(e)}

    def delete_security_group_rule(self, **kwargs):
        """
        删除安全组规则
        :param kwargs:
                    SecurityGroupId：类型：String。必选。描述：安全组实例ID
                    SecurityGroupPolicySet：类型：class:`tencentcloud.vpc.v20170312.models.SecurityGroupPolicySet`。必选。
                    此处传安全组具体信息或者直接传安全组具体索引  1和2任意一个即可，
                    1、{"Port": rule["port_range"], "Action": rule["action"], "CidrBlock": rule["access_ipaddr"],
                    "Protocol": rule["protocol"], {"Port": rule["port_range"], "Action": rule["action"],
                     "CidrBlock": rule["access_ipaddr"], "Protocol": rule["protocol"],
                    2、{"PolicyIndex": rule["rule_id"]}
                描述：安全组规则集合。
        :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.DeleteSecurityGroupPoliciesRequest()
            req.SecurityGroupId = kwargs["SecurityGroupId"]
            req.SecurityGroupPolicySet = kwargs["SecurityGroupPolicySet"]
            client.DeleteSecurityGroupPolicies(req)
            return {"result": True}
        except Exception as e:
            logger.exception("destroy security group rules failed.")
            return {"result": False, "message": str(e)}

    def modify_security_group_policies(self, **kwargs):
        """
        重置安全组出站和入站规则
        :param kwargs:
                    SecurityGroupId：类型：String。必选。描述：安全组实例ID
                    SecurityGroupPolicySet：类型：class:`tencentcloud.vpc.v20170312.models.SecurityGroupPolicySet`。必选。
                描述：安全组规则集合。
        :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.ModifySecurityGroupPoliciesRequest()
            req.SecurityGroupId = kwargs["SecurityGroupId"]
            req.SecurityGroupPolicySet = kwargs["SecurityGroupPolicySet"]
            client.ModifySecurityGroupPolicies(req)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_security_group_policies")
            return {"result": False, "message": str(e)}

    def replace_security_group_policy(self, **kwargs):
        """
        替换单条安全组路由规则
        :param kwargs:
                    SecurityGroupId：类型：String。必选。描述：安全组实例ID
                    SecurityGroupPolicySet：类型：class:`tencentcloud.vpc.v20170312.models.SecurityGroupPolicySet`。必选。
                描述：安全组规则集合。
        :return:
        """
        try:
            client = self.vpc_client
            model = vpc_models
            req = model.ReplaceSecurityGroupPolicyRequest()
            req.SecurityGroupId = kwargs["SecurityGroupId"]
            req.SecurityGroupPolicySet = kwargs["SecurityGroupPolicySet"]
            client.ReplaceSecurityGroupPolicy(req)
            return {"result": True}
        except Exception as e:
            logger.exception("replace_security_group_policy")
            return {"result": False, "message": str(e)}

    # *************************负载均衡*******************************
    def create_load_balancer(self, **kwargs):
        """创建负载均衡"""
        try:
            required_list = ["LoadBalancerType"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.CreateLoadBalancerRequest()
            list_optional_params = [
                "LoadBalancerType",
                "Forward",
                "LoadBalancerName",
                "VpcId",
                "SubnetId",
                "ProjectId",
                "AddressIPVersion",
                "Number",
                "MasterZoneId",
                "ZoneId",
                "VipIsp",
                "Vip",
                "BandwidthPackageId",
            ]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.CreateLoadBalancer(req)
            return {"result": True, "data": resp.LoadBalancerIds[0]}
        except Exception as e:
            logger.exception("fail create_load_balancer")
            return {"result": False, "message": str(e)}

    def delete_load_balancer(self, lb_ids):
        """删除负载均衡"""
        try:
            client = self.clb_client
            req = clb_models.DeleteLoadBalancerRequest()
            req.LoadBalancerIds = lb_ids if isinstance(lb_ids, list) else [lb_ids]
            resp = client.DeleteLoadBalancer(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail delete_load_balancer")
            return {"result": False, "message": str(e)}

    def modify_load_balancers(self, **kwargs):
        """修改负载均衡实例的属性"""
        try:
            required_list = ["LoadBalancerId"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.ModifyLoadBalancerAttributesRequest()
            list_optional_params = [
                "LoadBalancerId",
                "LoadBalancerName",
                "TargetRegionInfo",
                "InternetChargeInfo",
                "LoadBalancerPassToTarget",
                "SnatPro",
                "DeleteProtect",
            ]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.ModifyLoadBalancerAttributes(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("")
            return {"result": False, "message": str(e)}

    def list_load_balancers(self, ids=None, **kwargs):
        """查询负载均衡列表"""
        if ids:
            kwargs["LoadBalancerIds"] = ids
        req = clb_models.DescribeLoadBalancersRequest()
        list_optional_params = [
            "LoadBalancerIds",
            "LoadBalancerType",
            "Forward",
            "LoadBalancerName",
            "Domain",
            "OrderBy",
            "OrderType",
            "SearchKey",
            "ProjectId",
            "WithRs",
            "VpcId",
            "SecurityGroup",
            "MasterZone",
            "_Filters",
            "Offset",
            "Limit",
        ]
        request = set_optional_params(req, list_optional_params, kwargs)
        return self._handle_list_request("clb_client", request, "load_balancer", True)

    def list_backend_server(self, **kwargs):
        """查询负载均衡绑定的后端服务列表"""
        required_list = ["LoadBalancerId"]
        checkout_required_parameters(required_list, kwargs)
        client = self.clb_client
        req = clb_models.DescribeTargetsRequest()
        list_optional_params = ["LoadBalancerId", "ListenerIds", "Protocol", "Port"]
        request = set_optional_params(req, list_optional_params, kwargs)  # noqa
        resp = client.DescribeTargets(req)  # noqa
        # todo 后端服务器如何与负载均衡绑定

    def associate_backend_server(self, **kwargs):
        """绑定后端机器到监听器上"""
        try:
            required_list = ["LoadBalancerId", "ListenerId", "Targets"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.RegisterTargetsRequest()
            list_optional_params = ["LoadBalancerId", "ListenerId", "Targets", "LocationId", "Domain", "Url"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.RegisterTargets(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail associate_backend_server")
            return {"result": False, "message": str(e)}

    def disassociate_backend_server(self, **kwargs):
        """从负载均衡监听器上解绑后端服务"""
        try:
            required_list = ["LoadBalancerId", "ListenerId", "Targets"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.DeregisterTargetsRequest()
            list_optional_params = ["LoadBalancerId", "ListenerId", "Targets", "LocationId", "Domain", "Url"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.DeregisterTargets(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail disassociate_backend_server")
            return {"result": False, "message": str(e)}

    def list_listeners(self, **kwargs):
        """查询负载均衡的监听器列表"""
        try:
            required_list = ["LoadBalancerId"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.DescribeListenersRequest()
            list_optional_params = ["LoadBalancerId", "ListenerIds", "Protocol", "Port"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.DescribeListeners(req)
            data = self.__parse_result(resp.Listeners, "listener", **kwargs)
            return {"result": True, "data": data}
        except Exception as e:
            logger.exception("fail list_listeners")
            return {"result": False, "message": str(e)}

    def create_listener(self, **kwargs):
        """批量创建负载均衡监听器"""
        try:
            required_list = ["LoadBalancerId", "Ports", "Protocol"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.CreateListenerRequest()
            list_optional_params = [
                "LoadBalancerId",
                "Ports",
                "Protocol",
                "ListenerNames",
                "HealthCheck",
                "Certificate",
                "SessionExpireTime",
                "Scheduler",
                "SniSwitch",
                "TargetType",
                "SessionType",
                "KeepaliveEnable",
                "EndPort",
                "DeregisterTargetRst",
            ]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.CreateListener(req)
            return {"result": True, "data": resp.ListenerIds}
        except Exception as e:
            logger.exception("fail create_listener")
            return {"result": False, "message": str(e)}

    def delete_listener(self, **kwargs):
        """批量删除负载均衡多个监听器"""
        try:
            required_list = ["LoadBalancerId"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.DeleteLoadBalancerListenersRequest()
            list_optional_params = ["LoadBalancerId", "ListenerIds"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.DeleteLoadBalancerListeners(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail delete_listener")
            return {"result": False, "message": str(e)}

    def modify_listener(self, **kwargs):
        """修改负载均衡监听器属性"""
        try:
            required_list = ["LoadBalancerId", "ListenerId"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.ModifyListenerRequest()
            list_optional_params = [
                "LoadBalancerId",
                "ListenerId",
                "ListenerName",
                "SessionExpireTime",
                "HealthCheck",
                "Certificate",
                "Scheduler",
                "SniSwitch",
                "KeepaliveEnable",
                "DeregisterTargetRst",
                "SessionType",
            ]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.ModifyListener(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail modify_listener")
            return {"result": False, "message": str(e)}

    def list_rules(self, **kwargs):
        """查询转发规则列表"""
        try:
            required_list = ["LoadBalancerId", "ListenerIds"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.DescribeListenersRequest()
            list_optional_params = ["LoadBalancerId", "ListenerIds", "Protocol", "Port"]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.DescribeListeners(req)
            data = self.__parse_result(resp.Listeners.Rules, "rule", **kwargs)
            if kwargs.get("LocationIds"):
                location_ids = kwargs.get("LocationIds")
                data = [item for item in data if item.resource_id in location_ids]
            return {"result": True, "data": data}
        except Exception as e:
            logger.exception("fail list_listeners")
            return {"result": False, "message": str(e)}

    def create_rule(self, **kwargs):
        """创建转发规则"""
        try:
            required_list = ["LoadBalancerId", "ListenerId", "Rules"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.CreateRuleRequest()
            list_optional_params = required_list
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.CreateRule(req)
            return {"result": True, "data": resp.LocationIds}
        except Exception as e:
            logger.exception("fail create_rule")
            return {"result": False, "message": str(e)}

    def modify_rule(self, **kwargs):
        """更新转发规则"""
        try:
            required_list = ["LoadBalancerId", "ListenerId", "LocationId"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.ModifyRuleRequest()
            list_optional_params = [
                "LoadBalancerId",
                "ListenerId",
                "LocationId",
                "Url",
                "HealthCheck",
                "Scheduler",
                "SessionExpireTime",
                "ForwardType",
                "TrpcCallee",
                "TrpcFunc",
            ]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.ModifyRule(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("fail modify_rule")
            return {"result": False, "message": str(e)}

    def modify_rule_domain(self, **kwargs):
        """修改负载均衡七层监听器转发规则的域名级别属性"""
        try:
            required_list = ["LoadBalancerId", "ListenerId", "Domain"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.ModifyDomainAttributesRequest()
            list_optional_params = [
                "LoadBalancerId",
                "ListenerId",
                "Domain",
                "NewDomain",
                "Certificate",
                "Http2",
                "DefaultServer",
                "NewDefaultServerDomain",
            ]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.ModifyDomainAttributes(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("")
            return {"result": False, "message": str(e)}

    def delete_rule(self, **kwargs):
        """删除转发规则"""
        try:
            required_list = ["LoadBalancerId", "ListenerId"]
            checkout_required_parameters(required_list, kwargs)
            client = self.clb_client
            req = clb_models.DeleteRuleRequest()
            list_optional_params = [
                "LoadBalancerId",
                "ListenerId",
                "LocationIds",
                "Domain",
                "Url",
                "NewDefaultServerDomain",
            ]
            req = set_optional_params(req, list_optional_params, kwargs)
            resp = client.DeleteRule(req)
            return {"result": True, "data": resp.RequestId}
        except Exception as e:
            logger.exception("")
            return {"result": False, "message": str(e)}

    # *************************费用*******************************
    # def get_realcost(self, **kwargs):
    #     """
    #     获取真实费用参数
    #     :param kwargs:tcloud DescribeBillResourceSummaryRequest api param, see https://cloud.tencent.com/document/api
    #     :return:cost列表
    #     """
    #     try:
    #         client = self.billing_client
    #         model = billing_models
    #         req = model.DescribeBillResourceSummaryRequest()
    #         req.Month = kwargs["BillingCycle"]
    #         req.PeriodType = "byPayTime"
    #         req.Limit = 1000
    #         req.Offset = 0
    #         resp = client.DescribeBillResourceSummary(req)
    #         result_dic = json.loads(resp.to_json_string())
    #         data = []
    #         ins_list = []
    #         if "Error" not in list(result_dic.keys()):
    #             while result_dic["ResourceSummarySet"]:
    #                 data.extend(result_dic["ResourceSummarySet"])
    #                 total = len(result_dic["ResourceSummarySet"])
    #                 if total >= 1000:
    #                     req.Offset += 1000
    #                     resp = client.DescribeBillResourceSummary(req)
    #                     result_dic = json.loads(resp.to_json_string())
    #                 else:
    #                     break
    #             for item in data:
    #                 if float(item["CashPayAmount"]) > 0.0:
    #                     ins_list.append(
    #                         {
    #                             "resource_id": item.get("ResourceId"),
    #                             "resource_name": item.get("ResourceName"),
    #                             "resource_type": item.get("ProductCodeName"),
    #                             "cost": item["CashPayAmount"],
    #                             "cost_time": kwargs["BillingCycle"],
    #                         }
    #                     )
    #             return {"result": True, "data": ins_list}
    #         else:
    #             return {"result": False, "message": result_dic["message"]}
    #     except Exception as e:
    #         logger.exception("monitor_data")
    #         return {"result": False, "message": str(e)}

    def get_realcost(self, **kwargs):
        """
        查看账单明细数据
        :param kwargs:tcloud DescribeBillDetail api param, see https://cloud.tencent.com/document/api
        :return:cost列表
        """
        try:
            client = self.billing_client
            model = billing_models
            req = model.DescribeBillDetailRequest()
            req.Month = kwargs["BillingCycle"]
            # kwargs["BillingDate"] = "2021-03-15"
            req.BeginTime = kwargs["BillingDate"] + " 00:00:00"
            req.EndTime = kwargs["BillingDate"] + " 23:59:59"
            req.PeriodType = "byPayTime"
            req.Limit = 100  # 最大100
            req.Offset = 0
            resp = client.DescribeBillDetail(req)
            result_dic = json.loads(resp.to_json_string())
            data = []
            ins_list = []
            if "Error" not in list(result_dic.keys()):
                while result_dic["DetailSet"]:
                    data.extend(result_dic["DetailSet"])
                    total = len(result_dic["DetailSet"])
                    if total >= 100:
                        req.Offset += 100
                        resp = client.DescribeBillDetail(req)
                        result_dic = json.loads(resp.to_json_string())
                    else:
                        break
                for item in data:
                    original_price = 0
                    current_price = 0

                    for component in item["ComponentSet"]:
                        original_price += float(component["Cost"])
                        current_price += float(component["CashPayAmount"])

                    if float(current_price) > 0.0:
                        ins_list.append(
                            {
                                "serial_number": generate_serial_number(current_price),
                                "resource_id": item.get("ResourceId"),
                                "resource_name": item.get("ResourceName"),
                                # "resource_type": item.get("ProductCodeName"),
                                "resource_type": format_public_cloud_resource_type(
                                    CloudType.QClOUD.value, item.get("BusinessCodeName")
                                )
                                or item.get("ProductCodeName"),
                                "product_detail": item.get("BusinessCodeName"),
                                "mode": item.get("PayModeName"),
                                "original_price": original_price,
                                "discount": current_price - original_price,
                                "current_price": current_price,
                                "result_time": kwargs["BillingDate"],
                            }
                        )
                return {"result": True, "data": ins_list}
            else:
                return {"result": False, "message": result_dic["message"]}
        except Exception as e:
            logger.exception("monitor_data")
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
    #             client = self.cvm_client
    #             req = cvm_models.DescribeInstancesRequest()
    #             params = {"_Filters": [{"Name": "zone", "Values": [z["resource_id"]]}]}
    #             req.from_json_string(json.dumps(params))
    #             resp = client.DescribeInstances(req)
    #             ins_list = []
    #             total_count = resp.TotalCount
    #             ins_list.extend(resp.InstanceSet)
    #             page = total_count // 20 if total_count // 20 == 0 else total_count // 20 + 1
    #             for i in range(page):
    #                 offset = (i + 1) * 20
    #                 req.Offset = offset
    #                 ins_list.extend(client.DescribeInstances(req).InstanceSet)
    #             _, spec_list = get_compute_price_module(
    #                 CloudType.QClOUD.value, kwargs["account_name"], self.region_id, z["resource_id"]
    #             )
    #             spec_set_list = [s[4] for s in spec_list]
    #             spec_price_list = [s[3] for s in spec_list]
    #             for i in ins_list:
    #                 try:
    #                     price_disk = 0
    #                     i = json.loads(i.to_json_string())
    #                     ins_spec = i["InstanceType"]
    #                     if ins_spec in spec_set_list:
    #                         price_vm = spec_price_list[spec_set_list.index(ins_spec)]
    #                     else:
    #                         price_vm = 0
    #                     sys_disk = i["SystemDisk"]
    #                     data_disk = i.get("DataDisks") if i.get("DataDisks") else []
    #                     module, storage_list = get_storage_pricemodule(
    #                         CloudType.QClOUD.value, kwargs["account_name"], self.region_id, z["resource_id"],
    #                         sys_disk["DiskType"]
    #                     )
    #                     if module:
    #                         price_disk += storage_list[1] * sys_disk["DiskSize"]
    #                     else:
    #                         price_disk += 0
    #                     for d in data_disk:
    #                         module, storage_list = get_storage_pricemodule(
    #                             CloudType.QClOUD.value, kwargs["account_name"], self.region_id, z["resource_id"],
    #                             d["DiskType"]
    #                         )
    #                         if module:
    #                             price_disk += storage_list[1] * d["DiskSize"]
    #                         else:
    #                             price_disk += 0
    #                     return_data.append(
    #                         {
    #                             "resourceId": i["InstanceId"],
    #                             "name": i["InstanceName"],
    #                             "cpu": i["CPU"],
    #                             "mem": round(i["Memory"] / 1024, 2),
    #                             "cost_all": round((float(price_vm)), 2) + round((float(price_disk)), 2),
    #                             "cost_vm": round((float(price_vm)), 2),
    #                             "cost_disk": round((float(price_disk)), 2),
    #                             "cost_net": 0.0,
    #                             "cost_time": datetime.datetime.now().strftime("%Y-%m-%d"),
    #                             "source_type": CloudResourceType.VM.value,
    #                         }
    #                     )
    #                 except Exception:
    #                     logger.exception("get {} price error".format(i["InstanceId"]))
    #                     continue
    #         return {"result": True, "data": return_data}
    #     except Exception as e:
    #         logger.exception("get_virtual_cost")
    #         return {"result": False, "message": str(e)}

    def query_account_balance(self):
        """
        查询账户可用余额
        """
        request = billing_models.DescribeAccountBalanceRequest()
        return self._handle_list_request("billing_client", request, "balance")

    def query_account_transactions(self):
        """
        查询消费详情
        """
        model = billing_models
        req = model.DescribeBillListRequest()
        req.StartTime = (datetime.datetime.now() + datetime.timedelta(days=-366)).strftime("%Y-%m-%d %H:%M:%S")
        req.EndTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self._handle_list_request("billing_client", req, "transactions", True)

    # ************************** 规格 ××××××××××××××××××××××××××××××××
    def get_vm_spec(self, cpu, mem):
        pass

    @staticmethod
    def get_disk_spec(zone):
        """
        获取云硬盘规格 腾讯云直接是枚举
        Returns
        -------

        """
        return {"result": True, "data": [{"label": v, "value": k} for k, v in qcloud_disk_cn_dict.items()]}

    @staticmethod
    def get_object_storage_spec():
        """
        获取腾讯云对象存储规格
        Returns
        -------

        """
        return {"result": True, "data": [{"label": v, "value": k} for k, v in qcloud_bucket_cn_dict.items()]}

    def get_mysql_spec(self, region="", zone=""):
        """
        获取mysql可售卖类型  DescribeDBZoneConfig
        Returns
        -------

        """
        if zone and not region:
            raise Exception("参数zone有值时，参数region也必须传值")
        req = cdb_models.DescribeDBZoneConfigRequest()
        resp = self.cdb_client.DescribeDBZoneConfig(req)
        items, data = [], []
        for item in json.loads(resp.to_json_string())["Items"]:
            if not region:
                items.extend(item["ZonesConf"])
                continue
            if item["Region"] == region:
                items.extend(item["ZonesConf"])

        zone_items = []
        for zone_item in items:
            if not zone:
                zone_items.extend([i for sell in zone_item["SellType"] for i in sell["Configs"]])
                continue
            if zone_item["Zone"] == zone:
                zone_items.extend([i for sell in zone_item["SellType"] for i in sell["Configs"]])

        # 无规格标识，看控制台创建页面也是直接选cpu和memory
        data = [
            {
                "label": "{}核{}MB".format(i["Cpu"], i["Memory"]),
                "value": {"cpu": i["Cpu"], "mem": i["Memory"]},
                "remark": "{}{}{}".format(i["Device"], i["Type"], i["Info"]),
            }
            for i in zone_items
        ]
        return {"result": True, "data": data}

    def get_redis_spec(self, region="", zone=""):
        """
        获取redis规格
        Parameters
        ----------
        region
        zone

        Returns
        -------

        """
        if zone and not region:
            raise Exception("参数zone有值时，参数region也必须传值")
        req = redis_models.DescribeProductInfoRequest()
        resp = self.redis_client.DescribeProductInfo(req)
        items, data = [], []
        for item in json.loads(resp.to_json_string())["RegionSet"]:
            if not region:
                items.extend(item["ZoneSet"])
                continue
            if item["Region"] == region:
                items.extend(item["ZoneSet"])

        shard_size = set()
        shard_num = set()
        for zone_item in items:
            if not zone:
                shard_size.update([i for sell in zone_item["ProductSet"] for i in sell["ShardSize"]])
                shard_num.update([i for sell in zone_item["ProductSet"] for i in sell["ShardNum"]])
                continue
            if zone_item["Zone"] == zone:
                shard_size.update([i for sell in zone_item["ProductSet"] for i in sell["ShardSize"]])
                shard_num.update([i for sell in zone_item["ProductSet"] for i in sell["ShardNum"]])

        shard_num = [int(i) if "." not in i else float(i) for i in shard_num]
        shard_size = [int(i) if "." not in i else float(i) for i in shard_size]
        data = {"shard_size": sorted(shard_size), "shard_num": sorted(shard_num)}
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
        req = mongodb_models.DescribeSpecInfoRequest()
        resp = self.mongodb_client.DescribeSpecInfo(req)
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
        req = dcdb_models.DescribeShardSpecRequest()
        resp = self.dcdb_client.DescribeShardSpec(req)
        data = [
            {"mem": spec["Memory"], "cpu": spec["Cpu"], "node_count": spec["NodeCount"], "remark": spec["SuitInfo"]}
            for spec_config in json.loads(resp.to_json_string())["SpecConfig"]
            for spec in spec_config["SpecConfigInfos"]
        ]

        return {"result": True, "data": data}

    # ------------------------------------weops专属------------------------------------------------
    def list_cdb_mysql(self, ids=None, **kwargs):
        """
        获取云数据库mysql
        """
        req = cdb_models.DescribeDBInstancesRequest()
        if ids:
            req.InstanceIds = convert_param_to_list(ids)
        return self._handle_list_request("cdb_client", req, "cdb_mysql", True, format=False)

    def list_rocketmq_cluster(self, ids=None, **kwargs):
        """
        获取RocketMQ集群列表
        """
        req = tdmq_models.DescribeRocketMQClustersRequest()
        if ids:
            req.InstanceIds = convert_param_to_list(ids)
        return self._handle_list_request("tdmq_client", req, "rocketmq_cluster", True, format=False)

    def list_tke_serverless_cluster(self, ids=None, **kwargs):
        """
        获取tke serverless集群列表
        """
        req = tke_models.DescribeEKSClustersRequest()
        if ids:
            req.InstanceIds = convert_param_to_list(ids)
        return self._handle_list_request("tke_client", req, "tke_serverless_cluster", True, format=False)

    def rename_metric_key(self, bk_obj_id, raw_key, revert=False):
        _map = self.RENAME_METRIC
        if revert:
            _map = self.RENAME_METRIC_REVERT
        return _map.get(bk_obj_id, {}).get(raw_key) or raw_key

    def list_all_resources(self, **kwargs):
        cvm_rsp = self.list_vms(**kwargs)
        cdb_mysql_rsp = self.list_cdb_mysql(**kwargs)
        rocketmq_cluster_rsp = self.list_rocketmq_cluster(**kwargs)
        tke_serverless_cluster_rsp = self.list_tke_serverless_cluster(**kwargs)
        cvm = []
        cdb = []
        rocketmq = []
        serverless = []
        if cvm_rsp["result"]:
            cvm = cvm_rsp["data"]
        if cdb_mysql_rsp["result"]:
            cdb = cdb_mysql_rsp["data"]
        if rocketmq_cluster_rsp["result"]:
            rocketmq = rocketmq_cluster_rsp["data"]
        if tke_serverless_cluster_rsp["result"]:
            serverless = tke_serverless_cluster_rsp["data"]
        all_data = {
            "qcloud_cvm": cvm,
            "qcloud_mysql": cdb,
            "qcloud_rocketmq": rocketmq,
            "qcloud_serverless": serverless,
        }
        return {"result": True, "data": all_data}


# ***********************Common****************************************


def set_optional_params(request, list, kwargs):
    """
    设置request的非必选请求参数
    :param request:云接口对应请求实例
    :param list:需设置的请求参数
    :param kwargs:传入参数
    :return:
    """
    for _, v in enumerate(list):
        if v in kwargs:
            set_params(request, v, kwargs)
    return request


def set_required_params(request, list, kwargs):
    """
    设置request的必选请求参数
    :param request:云接口对应请求实例
    :param list:需设置的请求参数
    :param kwargs:传入参数
    :return:
    """
    for _, v in enumerate(list):
        set_params(request, v, kwargs)
    return request


def set_params(request, v, kwargs):
    """
     按照不同类型设置request的请求参数
    :param request:
    :param v:
    :param kwargs:
    :return:
    """
    if type(kwargs[v]) == int:
        setattr(request, v, (int(kwargs[v])))
    elif type(kwargs[v]) == int:
        setattr(request, v, (int(kwargs[v])))
    else:
        setattr(request, v, kwargs[v])


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

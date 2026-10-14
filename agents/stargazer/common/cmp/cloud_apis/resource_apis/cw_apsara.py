import json

import oss2

from common.cmp.cloud_apis.constant import CloudType
from common.cmp.cloud_apis.resource_apis.aliyun_dict import disk_category_dict
from common.cmp.cloud_apis.resource_apis.aliyunsdkasapi.AsapiRequest import AsapiRequest
from common.cmp.cloud_apis.resource_apis.aliyunsdkasapi.ASClient import ASClient
from common.cmp.cloud_apis.resource_apis.cw_aliyun import Aliyun, checkout_required_parameters
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.utils import convert_param_to_list
from core.logger import logger



class CwApsara:
    """
    阿里云组件类,通过该类创建阿里云的Client实例，调用阿里云api接口
    """

    def __init__(self, access_key, access_secret, region_id, host="", endpoint="", **kwargs):
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
        # self.endpoint = endpoint
        self.endpoint = host
        self.version = kwargs.pop("version", "")
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.client = ASClient(self.AccessKey, self.AccessSecret, self.RegionId)
        self.auth = oss2.Auth(self.AccessKey, self.AccessSecret)

    def __getattr__(self, item):
        """
        private方法，返回对应的阿里云接口类
        :param item:
        :return:
        """
        return Apsara(self.client, item, self.RegionId, self.auth, self.endpoint, self.version)


class Apsara(Aliyun):
    def __init__(self, aliyun_client, name, region, auth, endpoint, version):
        """
        初始化方法
        :param aliyun_client:
        :param name:
        :param region:
        """
        super().__init__(aliyun_client, name, region, auth)
        self.cloud_type = CloudType.APSARA.value
        self.endpoint = endpoint
        self.version = version

    # ***********************  common公用方法  ******************************************
    def _get_result(self, request, flag=False):
        """
        发送云接口访问请求，并可获取返回值
        :param request:
        :param flag: 类型：Boolean。描述：为True时获取返回参数，为False时无返回参数。
        :return:
        """
        self.client.sign_with_asapi = 1
        ali_request = self.client.do_action_with_exception(request)
        ali_result = json.loads(ali_request)
        if ali_result.get("asapiErrorCode", "200") != "200":
            raise Exception(ali_result.get("asapiErrorMessage", "操作失败，请重试"))
        if flag:
            return ali_result

    def _get_result_c(self, request, flag=False):
        return self._get_result(request, flag)

    def _add_required_params(self, request, params_dict):
        for k, v in params_dict.items():
            request.add_body_params(k, v)
        return request

    def _handle_list_request_with_page(self, resource, request):
        return self._handle_list_request_with_page_c(resource, request)

    def _get_request(self, product, version, action_name, asapi_gateway):
        request = AsapiRequest(product, version=version, action_name=action_name, asapi_gateway=asapi_gateway)
        request.set_method("POST")
        return request

    def _get_ecs_request(self, action_name):
        return self._get_request("ecs", version="2014-05-26", action_name=action_name, asapi_gateway=self.endpoint)

    def _get_slb_request(self, action_name):
        # 负载均衡的版本可能跟其他产品不一样
        return self._get_request("slb", version="2014-05-15", action_name=action_name, asapi_gateway=self.endpoint)

    def _get_vpc_request(self, action_name):
        return self._get_request("vpc", version="2016-04-28", action_name=action_name, asapi_gateway=self.endpoint)

    def _set_common_request_params(self, action_name, list_optional_params, **kwargs):
        """
        设置CommonRequest类型request的参数
        :param kwargs:
        :return:
        """
        request = self._get_slb_request(action_name)
        request = set_request_params(request, list_optional_params, kwargs)
        self.client.sign_with_asapi = 1
        return request

    # def get_connection_result(self):
    #     """
    #     根据能否获取地域信息判断是否连接成功
    #     :return:
    #     """
    #     # connection_result = self.list_regions()
    #     return {"result": True}
    #  ********************************主机管理**********************************
    def list_regions(self, ids=None):
        """
        获取阿里云地域信息
        : ids (list): id列表
        :return:
        """
        request = self._get_ecs_request("DescribeRegions")
        return self._handle_list_request("region", request)

    def list_zones(self, ids=None, **kwargs):
        """
        获取阿里云可用区信息
        :param ids: (list of str) id列表
        :param kwargs:
        :return:
        """
        request = self._get_ecs_request("DescribeZones")
        return self._handle_list_request("zone", request)

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
        request = self._get_ecs_request("DescribeInstanceTypeFamilies")
        # 可以根据系列信息查询指定系列下的规格族列表 这里先简写只查第一个
        if ids:
            request.add_body_params("Generation", ids[0])
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
        request = self._get_ecs_request("DescribeInstanceTypes")
        if "instance_type_family" in kwargs:
            request.add_body_params("InstanceTypeFamily", kwargs["instance_type_family"])
        return self._handle_list_request("instance_type", request)

    def list_vms(self, ids=None, **kwargs):
        """
        获取一台或多台实例的详细信息
        Args:
            ids (list of str): 实例id列表
            **kwargs (): 其他筛选条件

        Returns:

        """
        request = self._get_ecs_request("DescribeInstances")
        # todo 这里需要对应改前端传递参数??
        if ids:
            ids = convert_param_to_list(ids)
            request.add_body_params("InstanceIds", json.dumps(ids))
        kwargs["request"] = request
        request = self._set_vm_info_params(**kwargs)
        return self._handle_list_request_with_page("vm", request)

    def _set_vm_info_params(self, **kwargs):
        """
        设置实例信息参数
        :param kwargs:
        :return:
        """
        if kwargs.get("request"):
            request = kwargs["request"]
        else:
            request = self._get_ecs_request("DescribeInstances")
        list_optional_params = [
            "VpcId",
            "VSwitchId",
            "ZoneId",
            "InstanceNetworkType",
            "SecurityGroupId",
            "PageNumber",
            "PageSize",
            "InnerIpAddresses",
            "PrivateIpAddresses",
            "PublicIpAddresses",
            "EipAddresses",
            "InstanceName",
            "ImageId",
            "Status",
            "LockReason",
            "IoOptimized",
            "InstanceType",
            "InstanceTypeFamily",
            "KeyPairName",
            "ResourceGroupId",
            "HpcClusterId",
            "RdmaIpAddresses",
            "DryRun",
            "HttpEndpoint",
            "HttpTokens",
        ]
        request = set_request_params(request, list_optional_params, kwargs)
        request = set_kv_params(request, "Tag", kwargs)
        return request

    def _set_create_vm_params(self, **kwargs):
        """
        设置实例创建参数
        :param kwargs:
        :return:
        """
        request = self._get_ecs_request("RunInstances")
        request.add_body_params("ImageId", kwargs.get("ImageId"))
        request.add_body_params("InstanceType", kwargs.get("InstanceType"))
        request.add_body_params("SecurityGroupId", kwargs.get("SecurityGroupId"))
        request.add_body_params("VSwitchId", kwargs.get("VSwitchId"))
        list_optional_params = [
            "InstanceName",
            "Description",
            "InternetChargeType",
            "InternetMaxBandwidthIn",
            "InternetMaxBandwidthOut",
            "HostName",
            "UniqueSuffix",
            "Password",
            "PasswordInherit",
            "ZoneId",
            "SystemDisk.Size",
            "SystemDisk.Category",
            "SystemDisk.DiskName",
            "SystemDisk.Description",
            "SystemDisk.PerformanceLevel",
            "DataDisks",
            "IoOptimized",
            "UserData",
            "KeyPairName",
            "RamRoleName",
            "Amount",
            "MinAmount",
            "AutoReleaseTime",
            "SpotPriceLimit",
            "SecurityEnhancementStrategy",
            "ClientToken",
            "Tags",
            "HpcClusterId",
            "DryRun",
            "DedicatedHostId",
            "LaunchTemplateId",
            "LaunchTemplateName",
            "LaunchTemplateVersion",
            "ResourceGroupId",
            "DeploymentSetId",
            "PrivateIpAddress",
            "CreditSpecification",
            "Ipv6AddressCount",
            "DeletionProtection",
            "Affinity",
            "Tenancy",
            "StorageSetId",
            "StorageSetPartitionNumber",
            "CpuOptions.Core",
            "CpuOptions.ThreadsPerCore",
            "CpuOptions.Numa",
        ]
        request = set_request_params(request, list_optional_params, kwargs)
        return request

    def create_vm(self, **kwargs):

        try:
            required_list = ["ImageId", "InstanceType", "SecurityGroupId", "SecurityGroupId"]
            checkout_required_parameters(required_list, kwargs)
            request = self._set_create_vm_params(**kwargs)
            ali_response = self.client.do_action_with_exception(request)
            ali_result = json.loads(ali_response)
            return {"result": True, "data": ali_result["InstanceIdSets"]["InstanceIdSet"]}
        except Exception as e:
            logger.exception("create_vm")
            return {"result": False, "message": str(e)}

    def reset_instances_password(self, **kwargs):
        try:
            request = self._get_ecs_request("ModifyInstanceAttribute")
            request.add_body_params("InstanceId", kwargs["InstanceId"])
            # 只修改密码
            list_optional_params = ["Password"]
            request = set_request_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("reset_instances_password:" + kwargs["InstanceId"])
            return {"result": False, "message": str(e)}

    def start_vm(self, vm_id, **kwargs):
        """
        启动实例
        :param vm_id:实例ID
        """
        try:
            request = self._get_ecs_request("StartInstance")
            request.add_body_params("InstanceId", vm_id)
            list_optional_params = ["InitLocalDisk", "DryRun"]
            request = set_request_params(request, list_optional_params, kwargs)
            self.client.do_request(request)
            return {"result": True}
        except Exception as e:
            logger.exception("start_vm(instance_id):" + vm_id)
            return {"result": False, "message": str(e)}

    def stop_vm(self, vm_id, **kwargs):
        """
        停止实例
        :param vm_id:实例ID
        :param is_force: 强制关机
        """
        try:
            # is_force = kwargs.get("is_force", False)
            request = self._get_ecs_request("StopInstance")
            request.add_body_params("InstanceId", vm_id)
            # request.add_body_params("ForceStop", is_force)
            list_optional_params = ["ConfirmStop", "DryRun"]
            request = set_request_params(request, list_optional_params, kwargs)
            self.client.do_request(request)
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
            request = self._get_ecs_request("RebootInstance")
            request.add_body_params("InstanceId", vm_id)
            request.add_body_params("ForceStop", is_force)
            list_optional_params = ["DryRun"]
            request = set_request_params(request, list_optional_params, kwargs)
            self.client.do_request(request)
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
        # todo 没有接口 ecs ReActivateInstances

    def renew_vm(self, vm_id, period):
        """
        实例续费
        :param vm_id: 实例ID
        :param period:包年包月续费时长
        """
        # todo 没有接口 ecs RenewInstance

    def modify_vm(self, **kwargs):
        """
        调整一台按量付费ECS实例的实例规格和公网带宽大小。
        :param kwargs:
            InstanceId (str): 实例id  (required)
            InstanceType (str): 新规格id  (required)
        """
        try:
            request = self._get_ecs_request("ModifyInstanceSpec")
            request.add_body_params("InstanceId", kwargs["InstanceId"])
            request.add_body_params("InstanceType", kwargs["InstanceType"])
            list_optional_params = ["InstanceType", "InternetMaxBandwidthOut", "InternetMaxBandwidthIn"]
            request = set_request_params(request, list_optional_params, kwargs)
            self.client.do_request(request)
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
        # todo 没有接口 ecs ModifyPrepayInstanceSpec

    def destroy_vm(self, vm_id, **kwargs):
        """
        释放实例
        :param vm_id:实例ID
        """
        try:
            request = self._get_ecs_request("DeleteInstance")
            request.add_body_params("InstanceId", vm_id)
            list_optional_params = ["Force"]
            request = set_request_params(request, list_optional_params, kwargs)
            self.client.do_request(request)
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
        # todo 没有接口 ecs DescribeInstanceVncUrl

    def _set_available_vm_params(self, **kwargs):
        """
        查询升级和降配实例规格或者系统盘时，某一可用区的可用资源信息
        :param kwargs:
        :return:
        """
        request = self._get_ecs_request("DescribeAvailableResource")
        request.add_body_params("DestinationResource", kwargs["DestinationResource"])
        list_optional_params = [
            "ZoneId",
            "IoOptimized",
            "DedicatedHostId",
            "InstanceType",
            "SystemDiskCategory",
            "DataDiskCategory",
            "NetworkCategory",
            "Cores",
            "Memory",
            "ResourceType",
        ]
        request = set_request_params(request, list_optional_params, kwargs)
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
            ali_result = self._get_result(request, True)
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
            request = self._get_ecs_request("DescribeResourcesModification")
            request.add_body_params("ResourceId", kwargs.get("resource_id", ""))
            request.add_body_params("DestinationResource", kwargs["DestinationResource"])
            list_optional_params = ["MigrateAcrossZone", "InstanceType", "Cores", "Memory"]
            request = set_request_params(request, list_optional_params, kwargs)
            response = self._get_result(request, True)
            return response
        except Exception as e:
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
            request = self._get_ecs_request("ModifyInstanceAttribute")
            request.add_body_params("InstanceId", kwargs["InstanceId"])
            list_optional_params = ["SecurityGroupIds"]
            request = set_request_params(request, list_optional_params, kwargs)
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
        try:
            request = self._get_ecs_request("TagResources")
            resource_ids = kwargs.pop("ResourceIds")
            for idx, resource_id in enumerate(resource_ids):
                request.add_body_params("ResourceId." + str(idx + 1), resource_id)
            if "Tags" in kwargs:
                tags = kwargs.pop("Tags")
                for idx, tag in enumerate(tags):
                    request.add_body_params("Tag." + str(idx + 1) + ".Key", tag["Key"])
                    request.add_body_params("Tag." + str(idx + 1) + ".Value", tag["Value"])
            request.add_body_params("ResourceType", kwargs["ResourceType"])
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("tag_resources：" + kwargs["ResourceType"] + ":" + kwargs["ResourceIds"])
            return {"result": False, "message": str(e)}

    def list_resource_tags(self, **kwargs):
        request = self._get_ecs_request("ListTagResources")
        request.add_body_params("ResourceType", kwargs["ResourceType"])
        if "ResourceIds" in kwargs:
            resource_ids = kwargs.pop("ResourceIds")
            for idx, resource_id in enumerate(resource_ids):
                request.add_body_params("ResourceType." + str(idx + 1), resource_id)
        if "Tags" in kwargs and "TagFilters" not in kwargs:
            tags = kwargs.pop("Tags")
            for idx, tag in enumerate(tags):
                request.add_body_params("Tag." + str(idx + 1) + ".Key", tag["Key"])
                request.add_body_params("Tag." + str(idx + 1) + ".Value", tag["Value"])
        if "TagFilters" in kwargs:
            tag_filters = kwargs.pop("TagFilters")
            for idx, tag_filter in enumerate(tag_filters):
                request.add_body_params("Tag." + str(idx + 1) + ".TagKey", tag_filter["TagKey"])
                request.add_body_params("Tag." + str(idx + 1) + ".TagValues", tag_filter["TagValues"])
        list_optional_params = ["NextToken"]
        request = set_request_params(request, list_optional_params, kwargs)
        return self._handle_list_request("tag", request)

    def untie_tag_resources(self, **kwargs):
        request = self._get_ecs_request("UntagResources")
        request.add_body_params("ResourceType", kwargs["ResourceType"])
        resource_ids = kwargs.pop("ResourceIds")
        try:
            for idx, resource_id in enumerate(resource_ids):
                request.add_body_params("ResourceType." + str(idx + 1), resource_id)
            if "Tags" in kwargs:
                tags = kwargs.pop("Tags")
                for idx, tag in enumerate(tags):
                    request.add_body_params("TagKey." + str(idx + 1), tag["Key"])
            else:
                request.add_body_params("All", kwargs["All"])
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("untie_tag_resources")
            return {"result": False, "message": str(e)}

    #  -----------------快照---------------------------------

    def create_snapshot(self, **kwargs):
        """创建快照"""
        try:
            request = self._get_ecs_request("CreateSnapshot")
            request.add_body_params("DiskId", kwargs["DiskId"])
            request = set_kv_params(request, "Tag", kwargs)
            list_optional_params = ["SnapshotName", "Description", "RetentionDays", "Category", "ClientToken"]
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["SnapshotId"]}
        except Exception as e:
            logger.exception("create_snapshot")
            return {"result": False, "message": str(e)}

    def create_snapshot_group(self, **kwargs):
        """
        创建快照分组
        """
        # todo 没有接口 ecs CreateSnapshotGroup

    def delete_snapshot(self, snapshot_id, force=False):
        """删除快照"""
        try:
            request = self._get_ecs_request("DeleteSnapshot")
            request.add_body_params("SnapshotId", snapshot_id)
            request.add_body_params("Force", force)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete snapshot:" + snapshot_id)
            return {"result": False, "message": str(e)}

    def _set_snapshot_info_params(self, **kwargs):
        """
        设置快照信息参数
        :param kwargs:
        :return:
        """
        if kwargs.get("request"):
            request = kwargs["request"]
        else:
            request = self._get_ecs_request("DescribeSnapshots")
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
        request = set_request_params(request, list_optional_params, kwargs)
        return request

    def list_snapshots(self, ids=None, **kwargs):
        """获取快照列表"""
        request = self._get_ecs_request("DescribeSnapshots")
        if ids:
            request.add_body_params("SnapshotIds", json.dumps(ids))
        kwargs["request"] = request
        request = self._set_snapshot_info_params(**kwargs)
        return self._handle_list_request_with_page("snapshot", request)

    def restore_snapshot(self, disk_id, snapshot_id, **kwargs):
        try:
            request = self._get_ecs_request("ResetDisk")
            request.add_body_params("DiskId", disk_id)
            request.add_body_params("SnapshotId", snapshot_id)
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
        """为一块或者多块云盘应用自动快照策略。"""
        try:
            required_list = ["autoSnapshotPolicyId", "diskIds"]
            checkout_required_parameters(required_list, kwargs)
            request = self._get_ecs_request("ApplyAutoSnapshotPolicy")
            request.add_body_params("autoSnapshotPolicyId", kwargs.get("autoSnapshotPolicyId"))
            request.add_body_params("diskIds", kwargs.get("diskIds"))
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
        request = self._get_ecs_request("CancelAutoSnapshotPolicy")
        request.add_body_params("diskIds", kwargs.get("diskIds"))
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
        request = self._get_ecs_request("DescribeAutoSnapshotPolicyEx")
        request = set_kv_params(request, "Tag", kwargs)
        list_optional_params = ["AutoSnapshotPolicyId", "PageNumber", "PageSize"]
        request = set_request_params(request, list_optional_params, kwargs)
        return self._handle_list_request_with_page("auto_snapshot_policy", request)

    def copy_snapshots(self, **kwargs):
        """将一份普通快照从一个地域复制到另一个地域"""
        try:
            request = self._get_ecs_request("CopySnapshot")
            required_list = [
                "SnapshotId",
                "DestinationRegionId",
                "DestinationSnapshotName",
                "DestinationSnapshotDescription",
            ]
            checkout_required_parameters(required_list, kwargs)
            request = set_kv_params(request, "Tag", kwargs)
            list_request_params = [
                "SnapshotId",
                "DestinationRegionId",
                "DestinationSnapshotName",
                "DestinationSnapshotDescription",
                "RetentionDays",
            ]  # 可选参数列表
            request = set_request_params(request, list_request_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["SnapshotId"]}
        except Exception as e:
            logger.exception("copy snapshot error")
            return {"result": False, "message": str(e)}

    # ------------------负载均衡------------------------------
    def create_load_balancer(self, **kwargs):
        """创建负载均衡实例"""
        try:
            request = self._get_slb_request("CreateLoadBalancer")
            list_optional_params = ["LoadBalancerName", "AddressType", "VSwitchId", "ClientToken"]
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
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
            request = self._get_slb_request("DeleteLoadBalancer")
            request.add_body_params("LoadBalancerId", ins_id)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete load balancer failed")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def list_load_balancers(self, ids=None, **kwargs):
        try:
            if ids:
                kwargs["LoadBalancerId"] = ids[0]
            list_optional_params = [
                "LoadBalancerId",
                "LoadBalancerName",
                "AddressType",
                "NetworkType",
                "VpcId",
                "VSwitchId",
                "Address",
                "ServerIntranetAddress",
                "ServerId",
                "MasterZoneId",
                "SlaveZoneId",
                "Tags",
            ]
            request = self._get_slb_request("DescribeLoadBalancers")
            request = set_request_params(request, list_optional_params, kwargs)
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
            request = self._get_slb_request("DescribeLoadBalancerAttribute")
            request.add_body_params("LoadBalancerId", kwargs["LoadBalancerId"])
            ali_result = self._get_result(request, True)
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
            request = self._get_slb_request("DescribeServerCertificates")
            if "ServerCertificateId" in kwargs:
                request.add_body_params("ServerCertificateId", kwargs["ServerCertificateId"])
            return self._handle_list_request("server_certificate", request)
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
            request = self._get_slb_request("CreateVServerGroup")
            list_optional_params = ["LoadBalancerId", "VServerGroupName", "BackendServers"]
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
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
            request = self._get_slb_request("DeleteVServerGroup")
            request.add_body_params("VServerGroupId", kwargs["VServerGroupId"])
            ali_result = self._get_result(request, True)
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
            if "LoadBalancerId" not in kwargs:
                return {"result": False, "message": "need param VServerGroupId"}
            list_optional_params = ["LoadBalancerId", "VServerGroupName", "BackendServers"]
            request = self._get_slb_request("SetVServerGroupAttribute")
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request)
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("set vserver group failed")
            return {"result": False, "message": str(e)}

    # todo 接口跟公有云接口差异比较大,待确认
    def list_vserver_groups(self, load_balancer_id, **kwargs):
        """查询服务器组列表"""
        try:
            if not load_balancer_id:
                return {"result": False, "message": "need param LoadBalancerId"}
            request = self._get_slb_request("DescribeVServerGroups")
            request.add_body_params("LoadBalancerId", load_balancer_id)
            data = self._handle_list_request("vserver_groups", request)
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

    # todo 接口跟公有云接口差异比较大,待确认
    def get_vserver_group(self, **kwargs):
        """
        查询服务器组的详细信息
        :param kwargs:
        :return:
        """
        list_optional_params = ["LoadBalancerId", "ListenerPort"]
        request = self._get_slb_request("DescribeVServerGroupAttribute")
        request = set_request_params(request, list_optional_params, kwargs)
        ali_result = self._get_result(request, True)
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
            request = self._get_slb_request("AddVServerGroupBackendServers")
            request = set_request_params(request, required_list, kwargs)
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
            request = self._get_slb_request("RemoveVServerGroupBackendServers")
            request = set_request_params(request, required_list, kwargs)
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
            required_list = ["VServerGroupId", "OldBackendServers", "NewBackendServers"]
            checkout_required_parameters(required_list, kwargs)
            request = self._get_slb_request("ModifyVServerGroupBackendServers")
            request = set_request_params(request, required_list, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result}
        except Exception as e:
            logger.exception("modify_vserver_group_backend_servers failed")
            return {"result": False, "message": str(e)}

    def create_load_balancer_tcp_listen(self, **kwargs):
        """
        创建负载均衡TCP监听
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "Bandwidth"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "ListenerPort",
                "BackendServerPort",
                "VServerGroupId",
                "MasterSlaveServerGroupId",
                "Bandwidth",
                "Scheduler",
                "PersistenceTimeout",
                "EstablishedTimeout",
                "HealthCheckType",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthCheckConnectPort",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
            ]
            request = self._get_slb_request("CreateLoadBalancerTCPListener")
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)

            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("create load balancer tcp listen failed")
            return {"result": False, "message": str(e)}

    def create_load_balancer_udp_listen(self, **kwargs):
        """
        创建负载均衡UDP监听
        :param kwargs:
            LoadBalancerId	String	是	负载均衡实例ID。
            ListenerPort	Integer	是	负载均衡实例前端使用的端口，取值：1-65535
            BackendServerPort	Integer	是	负载均衡实例后端使用的端口。取值：1-65535
            VServerGroupId	String	否	服务器组ID。
            MasterSlaveServerGroupId	String	否	主备服务器组ID。
            Bandwidth	Integer	是	监听的带宽峰值，
            Scheduler	String	否	调度算法。
            HealthCheckConnectPort	Integer	否	健康检查使用的端口。取值：1-65535
            HealthyThreshold	Integer	否	健康检查连续成功多少次后，将后端服务器的健康检查状态由fail判定为success。取值：2-10
            UnhealthyThreshold	Integer	否	健康检查连续失败多少次后，将后端服务器的健康检查状态由success判定为fail。取值：2-10
            HealthCheckTimeout	Integer	否	接收来自运行状况检查的响应需要等待的时间。
            HealthCheckInterval	Integer	否	健康检查的时间间隔。取值：1-50（秒）
            HealthCheckHttpCode	String	否	健康检查正常的HTTP状态码，多个状态码用逗号分隔。
            HealthCheckReq	String	否	UDP监听健康检查的请求串，只允许包含字母、数字字符，最大长度限制为500字符。
            HealthCheckExp	String	否	UDP监听健康检查的响应串，只允许包含字母、数字字符，最大长度限制为500字符。
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "Bandwidth"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "ListenerPort",
                "BackendServerPort",
                "VServerGroupId",
                "MasterSlaveServerGroupId",
                "Bandwidth",
                "Scheduler",
                "HealthCheckConnectPort",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "HealthCheckReq",
                "HealthCheckExp",
            ]
            request = self._get_slb_request("CreateLoadBalancerUDPListener")
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
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
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "Bandwidth", "StickySession", "HealthCheck"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "Bandwidth",
                "ListenerPort",
                "BackendServerPort",
                "XForwardedFor",
                "VServerGroupId",
                "XForwardedFor_SLBIP",
                "XForwardedFor_SLBID",
                "XForwardedFor_proto",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckMethod",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthCheckConnectPort",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "Gzip",
            ]
            request = self._get_slb_request("CreateLoadBalancerHTTPListener")
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("create load balancer udp listen failed")
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
        :return:
        """
        try:
            required_list = [
                "LoadBalancerId",
                "ListenerPort",
                "ServerCertificateId",
                "StickySession",
                "HealthCheck",
                "Bandwidth",
            ]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "Bandwidth",
                "ListenerPort",
                "BackendServerPort",
                "VServerGroupId",
                "ServerCertificateId",
                "CACertificateId",
                "XForwardedFor",
                "XForwardedFor_SLBIP",
                "XForwardedFor_SLBID",
                "XForwardedFor_proto",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthCheckConnectPort",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "Gzip",
            ]
            request = self._get_slb_request("CreateLoadBalancerHTTPSListener")
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["RequestId"]}
        except Exception as e:
            logger.exception("create load balancer https listen failed")
            return {"result": False, "message": str(e)}

    def set_load_balancer_tcp_listener_attribute(self, **kwargs):
        """
        修改TCP监听的配置
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "Bandwidth"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "ListenerPort",
                "BackendServerPort",
                "VServerGroupId",
                "MasterSlaveServerGroupId",
                "Bandwidth",
                "Scheduler",
                "PersistenceTimeout",
                "EstablishedTimeout",
                "HealthCheckType",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthCheckConnectPort",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
            ]
            request = self._get_slb_request("SetLoadBalancerTCPListenerAttribute")
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
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
            required_list = ["LoadBalancerId", "ListenerPort", "Bandwidth"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "ListenerPort",
                "BackendServerPort",
                "VServerGroupId",
                "MasterSlaveServerGroupId",
                "Bandwidth",
                "Scheduler",
                "HealthCheckConnectPort",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "HealthCheckReq",
                "HealthCheckExp",
            ]
            request = self._get_slb_request("SetLoadBalancerUDPListenerAttribute")
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
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
            required_list = ["LoadBalancerId", "ListenerPort", "Bandwidth", "StickySession", "HealthCheck"]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "ListenerPort",
                "BackendServerPort",
                "VServerGroupId",
                "Bandwidth",
                "XForwardedFor",
                "XForwardedFor_SLBIP",
                "XForwardedFor_SLBID",
                "XForwardedFor_proto",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthCheckConnectPort",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "Gzip",
            ]
            request = self._get_slb_request("SetLoadBalancerHTTPListenerAttribute")
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
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
            required_list = [
                "LoadBalancerId",
                "ListenerPort",
                "ServerCertificateId",
                "Bandwidth",
                "StickySession",
                "HealthCheck",
            ]
            checkout_required_parameters(required_list, kwargs)
            list_optional_params = [
                "LoadBalancerId",
                "ListenerPort",
                "BackendServerPort",
                "VServerGroupId",
                "ServerCertificateId",
                "CACertificateId",
                "Bandwidth",
                "XForwardedFor",
                "XForwardedFor_SLBIP",
                "XForwardedFor_SLBID",
                "XForwardedFor_proto",
                "Scheduler",
                "StickySession",
                "StickySessionType",
                "CookieTimeout",
                "Cookie",
                "HealthCheck",
                "HealthCheckDomain",
                "HealthCheckURI",
                "HealthCheckConnectPort",
                "HealthyThreshold",
                "UnhealthyThreshold",
                "HealthCheckTimeout",
                "HealthCheckInterval",
                "HealthCheckHttpCode",
                "Gzip",
            ]
            request = self._get_slb_request("SetLoadBalancerHTTPSListenerAttribute")
            request = set_request_params(request, list_optional_params, kwargs)
            ali_result = self._get_result(request, True)
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
            Rules String	是	要添加的转发规则,公有云参数名为为RuleList
        :return:
        """
        try:
            required_list = ["LoadBalancerId", "ListenerPort", "RuleList"]
            checkout_required_parameters(required_list, kwargs)
            kwargs["Rules"] = kwargs.pop("RuleList")  # 操作类传过来的是RuleList,接口接受的是Rules
            request = self._set_common_request_params("CreateRules", required_list, **kwargs)
            ali_result = self._get_result(request, True)
            if ali_result.get("Rules"):
                return {"result": True, "data": ali_result["Rules"]}
            return {"result": False, "message": ali_result["Message"]}
        except Exception as e:
            logger.exception("create rules failed")
            return {"result": False, "message": str(e)}

    def list_listeners(self, **kwargs):
        """查询负载均衡监听列表详情"""
        # todo 没有接口 slb DescribeLoadBalancerListeners

    # ------------------镜像------------------------------

    def _set_template_info_params(self, **kwargs):
        """
        设置镜像信息参数
        :param kwargs:
        :return:
        """
        request = kwargs.get("request", "") or self._get_ecs_request("CreateImage")
        list_optional_params = [
            "Status",
            "ImageId",
            "SnapshotId",
            "ImageName",
            "ImageOwnerAlias",
            "InstanceType",
            "IsSupportIoOptimized",
            "IsSupportCloudinit",
            "OSType",
            "Architecture",
            "PageNumber",
            "PageSize",
            "Usage",
            "DryRun",
            "ActionType",
            "ResourceGroupId",
        ]
        request = set_request_params(request, list_optional_params, kwargs)
        request = set_kv_params(request, "Tag", kwargs)
        request = set_kv_params(request, "Filter", kwargs)
        return request

    def create_image(self, **kwargs):
        """
        创建自定义镜像
        SnapshotId  String	否	根据指定的快照创建自定义镜像。
        InstanceId  String	否  实例ID。
        ImageName   String	否	镜像名称
        Description  String	否	镜像的描述信息
        Platform  String	否	指定数据盘快照做镜像的系统盘后，需要通过Platform确定系统盘的操作系统发行版
        ClientToken String	否	保证请求幂等性
        ResourceGroupId  String	否	自定义镜像所在的企业资源组ID。
        DiskDeviceMapping list []	否
        Tag list 否
        """
        try:
            request = self._get_ecs_request("CreateImage")
            list_optional_params = [
                "SnapshotId",
                "InstanceId",
                "ImageName",
                "Description",
                "Platform",
                "Architecture",
                "ClientToken",
                "ResourceGroupId",
            ]
            request = set_request_params(request, list_optional_params, kwargs)
            request = set_kv_params(request, "Tag", kwargs)
            request = set_request_disk_device_mappings(request, kwargs)
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
        request = self._get_ecs_request("DescribeImages")
        if ids:
            request.add_body_params("ImageId", ids)
        kwargs["request"] = request
        request = self._set_template_info_params(**kwargs)
        return self._handle_list_request_with_page("image", request)

    def delete_images(self, **kwargs):
        """
        销毁磁盘
        """
        try:
            if "image_id" not in kwargs:
                return {"result": False, "message": "need param image_id"}
            request = self._get_ecs_request("DeleteImage")
            request.add_body_params("ImageId", kwargs["image_id"])
            request.add_body_params("Force", kwargs.get("Force", False))
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete image_id failed(ImageId):" + ",".join(kwargs["image_id"]))
            return {"result": False, "message": str(e)}

    #  *********************************存储管理*******************************************

    #  -----------------块存储-------------------------------

    def _set_datastore_info_params(self, request, **kwargs):
        """
        设置云盘信息参数
        :param kwargs:
        :return:
        """
        list_optional_params = [
            "ZoneId",
            "InstanceId",
            "DiskType",
            "Category",
            "Status",
            "SnapshotId",
            "Portable",
            "DeleteWithInstance",
            "DeleteAutoSnapshot",
            "PageNumber",
            "PageSize",
            "DiskName",
            "AutoSnapshotPolicyId",
            "EnableAutomatedSnapshotPolicy",
            "ResourceGroupId",
            "EnableShared",
            "DryRun",
            "KMSKeyId",
        ]
        request = set_request_params(request, list_optional_params, kwargs)
        request = set_kv_params(request, "Tag", kwargs)
        return request

    def list_disks(self, ids=None, **kwargs):
        """
        获取云盘列表
        :param ids:  ids (list of str): 磁盘id列表
        :param kwargs:aliyun DescribeDisksRequest api param, see https://help.aliyun.com/
        :return:云盘列表
        """
        request = self._get_ecs_request("DescribeDisks")
        if ids:
            request.add_body_params("DiskIds", json.dumps(ids))
        request = self._set_datastore_info_params(request, **kwargs)
        return self._handle_list_request_with_page("disk", request)

    def _set_create_disk_params(self, **kwargs):
        """设置阿里云磁盘创建参数
        下边二选一
            ZoneId：可用区id 付费类型是按需付费  (required)  现在只做按量付费即必有zone_id
            InstanceId (str): 关联实例id 和zoneId有且仅有1个，付费类型只能是包年包月 (required)
        DiskName: 名称 (optional)
        Size: 容量  (optional)
        DiskCategory: 数据盘种类 (optional)
        Description: 数据盘描述  (optional)

        """
        request = self._get_ecs_request("CreateDisk")
        request.add_body_params("ZoneId", kwargs["ZoneId"])
        list_optional_params = ["DiskCategory", "Size", "DiskName", "Encrypted", "Description"]
        request = set_request_params(request, list_optional_params, kwargs)
        return request

    def create_disk(self, **kwargs):
        """
        创建磁盘
        :param kwargs:aliyun CreateDiskRequest api param, see https://help.aliyun.com/
        :return:云盘id
        """
        try:
            request = self._set_create_disk_params(**kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["DiskId"]}
        except Exception as e:
            logger.exception("create_disk")
            return {"result": False, "message": str(e)}

    def attach_disk(self, **kwargs):
        """
        挂载磁盘
        """
        try:
            required_list = ["DiskIds", "InstanceId"]
            checkout_required_parameters(required_list, kwargs)
            kwargs["DiskId"] = kwargs.pop("DiskIds")
            list_request_params = ["DiskId", "InstanceId", "DeleteWithInstance", "Bootable", "Password", "KeyPairName"]
            request = self._get_ecs_request("AttachDisk")
            request = set_request_params(request, list_request_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("attach_disk:InstanceId({}),DiskIds({})".format(kwargs["InstanceId"], kwargs["DiskId"]))
            return {"result": False, "message": str(e)}

    def detach_disk(self, **kwargs):
        """
        卸载磁盘
        :param kwargs:aliyun DetachDiskRequest api param, see https://help.aliyun.com/
        """
        try:
            required_list = ["DiskIds", "InstanceId"]
            checkout_required_parameters(required_list, kwargs)
            kwargs["DiskId"] = kwargs.pop("DiskIds")
            list_request_params = ["DiskId", "InstanceId", "DeleteWithInstance"]
            request = self._get_ecs_request("DetachDisk")
            request = set_request_params(request, list_request_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("detach_disk:InstanceId({}),DiskIds({})".format(kwargs["InstanceId"], kwargs["DiskId"]))
            return {"result": False, "message": str(e)}

    def delete_disk(self, disk_id, **kwargs):
        """
        销毁磁盘
        :param disk_id:
            aliyun DeleteDiskRequest api param, see https://help.aliyun.com/
        """
        try:
            request = self._get_ecs_request("DeleteDisk")
            request.add_body_params("DiskId", disk_id)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("delete disk failed(DiskIds):" + ",".join(disk_id))
            return {"result": False, "message": str(e)}

    def resize_disk(self, **kwargs):
        """
        扩容一块云盘，支持扩容系统盘和数据盘。
        """
        try:
            request = self._get_ecs_request("ResizeDisk")
            request.add_body_params("DiskId", kwargs["DiskId"])
            request.add_body_params("NewSize", int(kwargs["NewSize"]))
            list_optional_params = ["Type", "ClientToken"]
            request = set_request_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("resize_disk")
            return {"result": False, "message": str(e)}

    # ---------------对象存储-----------------------
    def list_buckets(self, **kwargs):
        """
        获取Bucket列表信息。
        :param kwargs:
                    Prefix：类型：String。描述：只罗列Bucket名为该前缀的Bucket，空串表示罗列所有的Bucket。
                    Marker：类型：分页标志。首次调用传空串，后续使用返回值中的next_marker。
                    Max-keys：类型：Integer。描述：每次调用最多返回的Bucket数目。
        :return: oss2.models.ListBucketsResult解码后的python对象
        :rtype: oss2.models.ListBucketsResult
        """
        bucket_type = ""
        format_func = get_format_method(self.cloud_type, "bucket")
        ali_result = []
        try:
            service = oss2.Service(self.auth, self.endpoint)
            buckets = service.list_buckets().buckets
        except Exception as e:
            logger.exception("调用阿里云飞天获取桶存储接口失败{}".format(e))
            return {"result": False, "message": e.message}
        for i in buckets:
            try:
                bucket = oss2.Bucket(self.auth, self.endpoint, i.name)
                object_list = bucket.list_objects().object_list
            except Exception as e:
                logger.exception("调用阿里云飞天获取桶存储接口失败{}".format(e))
                return {"result": False, "message": e.message}
            size = 0
            if object_list:
                bucket_type = object_list[0].storage_class
                for file in object_list:
                    size += file.size
                size = round(size / 1024 / 1024, 2)
            ali_result.append(format_func(i, bucket_type=bucket_type, size=size))
        return {"result": True, "data": ali_result}

    def create_bucket(self, **kwargs):
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
            bucket = oss2.Bucket(self.auth, self.endpoint, kwargs["BucketName"])
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
            bucket = oss2.Bucket(self.auth, self.endpoint, name)
            bucket.delete_bucket()
            return {"result": True}
        except Exception as e:
            logger.exception("delete_bucket:" + name)
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
        request = self._get_request("nas", self.version, "CreateFileSystem", self.endpoint)
        list_optional_params = ["StorageType", "ProtocolType", "Description", "VolumeSize"]
        request = set_request_params(request, list_optional_params, kwargs)
        ali_result = self._get_result(request, True)
        return {"result": True, "data": ali_result["FileSystemId"]}

    def delete_file_system(self, fs_id):
        """
        删除文件系统
        :param kwargs:aliyun DetachDiskRequest api param, see https://help.aliyun.com/
        :return:
        """
        try:
            request = self._get_request("nas", self.version, "DeleteFileSystem", self.endpoint)
            request.add_body_params("FileSystemId", fs_id)
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
        request = self._get_request("nas", self.version, "DescribeFileSystems", self.endpoint)
        list_optional_params = ["FileSystemId", "PageSize", "PageNumber"]
        request = set_request_params(request, list_optional_params, kwargs)
        return self._handle_list_request_with_page("file_system", request)

    #  **************************************网络管理*******************************

    #  ---------------------VPC（专有网络）---------------------------

    def create_vpc(self, **kwargs):
        """
        创建一个专有网络（VPC）。
        """
        try:
            request = self._get_vpc_request("CreateVpc")
            list_optional_params = ["CidrBlock", "VpcName", "Description", "ResourceGroupId", "UserCidr", "ClientToken"]
            request = set_request_params(request, list_optional_params, kwargs)
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
            request = self._get_vpc_request("DeleteVpc")
            request.add_body_params("VpcId", vpc_id)
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
        request = self._get_vpc_request("DescribeVpcs")
        if ids:
            request.add_body_params("VpcId", ids[0])
        list_optional_params = ["VpcId", "IsDefault", "PageNumber", "PageSize"]
        request = set_request_params(request, list_optional_params, kwargs)
        return self._handle_list_request_with_page("vpc", request)

    #  -------------------VSwitch（交换机）------------------------------

    def create_subnet(self, **kwargs):
        """
        创建交换机。
        """
        try:
            request = self._get_vpc_request("CreateVSwitch")
            list_required_params = ["ZoneId", "CidrBlock", "VpcId"]
            checkout_required_parameters(list_required_params, kwargs)
            list_request_params = list_required_params.extend(["VSwitchName", "Description", "ClientToken"])
            request = set_request_params(request, list_request_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["VSwitchId"]}
        except Exception as e:
            logger.exception("create_subnet")
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
            request = self._get_vpc_request("DeleteVSwitch")
            request.add_body_params("VSwitchId", subnet_id)
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
        request = self._get_vpc_request("DescribeVSwitches")
        if ids:
            request.add_body_params("VSwitchId", ids[0])
        list_optional_params = ["VpcId", "ZoneId", "PageNumber", "PageSize", "IsDefault"]
        request = set_request_params(request, list_optional_params, kwargs)
        return self._handle_list_request_with_page("subnet", request)

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
        request = self._get_vpc_request("DescribeRouteTables")
        list_optional_params = ["RouterType", "RouterId", "VRouterId", "RouteTableId", "PageNumber", "PageSize"]
        request = set_request_params(request, list_optional_params, kwargs)
        return self._handle_list_request_with_page("route_table", request)

    def disassociate_route_table(self, **kwargs):
        """
        将路由表和交换机解绑
        :param kwargs:
        :return:
        """
        # todo 没有接口vpc UnassociateRouteTable

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
        # todo 没有接口vpc CreateRouteTable

    def delete_route_table(self, route_table_id):
        """
        删除自定义路由表
        :param route_table_id:  String	是	路由表ID
        :return:
        """
        # todo 没有接口vpc DeleteRouteTable

    def create_route_entry(self, **kwargs):
        """
        新建路由策略
        :param kwargs:
            RouteTableId  String	是	要创建自定义路由条目的路由表ID
            DestinationCidrBlock  String	是	自定义路由条目的目标网段
            NextHopId  String	是	自定义路由条目的下一跳实例的ID
            ClientToken  String	否
            NextHopType  String	否	自定义路由条目的下一跳的类型
            NextHopList  list []	否
        :return:
        """
        try:
            required_list = ["RouteTableId", "DestinationCidrBlock"]
            checkout_required_parameters(required_list, kwargs)
            request = self._get_vpc_request("CreateRouteEntry")
            list_request_params = required_list.extend(["NextHopType", "NextHopId", "ClientToken", "NextHopList"])
            request = set_request_params(request, list_request_params, kwargs)
            ali_result = self._get_result(request, True)
            return {"result": True, "data": ali_result["RouteEntryId"]}
        except Exception as e:
            logger.exception("create route entry failed")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def delete_route_entry(self, **kwargs):
        """
        删除路由策略
        :param kwargs:
            RouteTableId  String	是	路由条目所在的路由表的ID
            NextHopList  String	否	路由条目的下一跳列表。在删除ECMP路由条目时，指定该参数。
            DestinationCidrBlock  String	是	路由条目的目标网段，支持IPv4和IPv6网段。
            NextHopId  String	是	下一跳实例的ID
        :return:
        """
        try:
            request = self._get_vpc_request("DeleteRouteEntry")
            required_list = ["RouteTableId", "DestinationCidrBlock"]
            checkout_required_parameters(required_list, kwargs)
            list_request_params = ["RouteTableId", "DestinationCidrBlock", "NextHopId", "NextHopList"]
            request = set_request_params(request, list_request_params, kwargs)
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
        """
        # todo 没有接口 vpc AssociateRouteTable

    def list_route_entry(self, **kwargs):
        """
        查询路由条目列表
        """
        # todo 没有接口 vpc DescribeRouteEntryList

    #  ------------------弹性公网ip--------------------------------

    def create_eip(self, **kwargs):
        """
        申请弹性公网IP（EIP）。
        """
        try:
            request = self._get_vpc_request("AllocateEipAddress")
            list_optional_params = ["Bandwidth", "ClientToken"]
            request = set_request_params(request, list_optional_params, kwargs)
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
        :return:
        """
        try:
            request = self._get_vpc_request("AssociateEipAddress")
            request.add_body_params("AllocationId", kwargs["eip_id"])
            request.add_body_params("InstanceId", kwargs["instance_id"])
            if "InstanceType" in kwargs:
                request.add_query_param("InstanceType", kwargs["InstanceType"])
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("associate_address")
            return {"result": False, "message": str(e)}

    def disassociate_address(self, **kwargs):
        """
        将弹性公网IP（EIP）从绑定的云产品上解绑。
        :param kwargs:
            eip_id：类型：String，必选。描述：绑定云产品实例的EIP的ID。
            instance_id：类型：String，必选，描述：要解绑EIP的云产品实例的ID。
            InstanceType：类型：String，描述：要解绑EIP的云产品类型，取值：EcsInstance（默认值）：专有网络类型的ECS实例。
        :return:
        """
        try:
            request = self._get_vpc_request("UnassociateEipAddress")
            request.add_body_params("AllocationId", kwargs["eip_id"])
            request.add_body_params("InstanceId", kwargs["instance_id"])
            list_optional_params = ["InstanceType"]
            request = set_request_params(request, list_optional_params, kwargs)
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
            request = self._get_vpc_request("ModifyEipAddressAttribute")
            request.add_body_params("AllocationId", kwargs["eip_id"])
            if "bandwidth" in kwargs:
                request.add_body_params("Bandwidth", kwargs["bandwidth"])
            list_optional_params = ["Bandwidth", "Description", "Name"]
            request = set_request_params(request, list_optional_params, kwargs)
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
            request = self._get_vpc_request("ReleaseEipAddress")
            request.add_body_params("AllocationId", eip_id)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("release_eip:" + eip_id)
            return {"result": False, "message": str(e)}

    def list_eips(self, ids=None, **kwargs):
        """
        获取外网信息
        :param ids: eipId 列表
        :param kwargs:aliyun DescribeEipAddressesRequest api param, see https://help.aliyun.com/
        :return:eip列表
        """
        request = self._get_vpc_request("DescribeEipAddresses")
        if ids:
            request.add_body_params("AllocationId", ids[0])
        list_optional_params = ["Status", "AssociatedInstanceType", "AssociatedInstanceId", "PageNumber", "PageSize"]
        request = set_request_params(request, list_optional_params, kwargs)
        return self._handle_list_request_with_page("eip", request)

    #  ------------------安全组--------------------------

    def list_security_groups(self, ids=None, **kwargs):

        """
        获取安全组信息参数
        :param ids: 安全组id 列表
        :param kwargs:aliyun DescribeSecurityGroupsRequest api param, see https://help.aliyun.com/
        :return:安全组列表
        """
        request = self._get_ecs_request("DescribeSecurityGroups")
        if ids:
            request.add_body_params("SecurityGroupIds", json.dumps(ids))
        list_optional_params = [
            "VpcId",
            "PageNumber",
            "PageSize",
            "SecurityGroupIds",
            "ResourceGroupId",
            "SecurityGroupName",
            "NetworkType",
            "SecurityGroupId",
            "DryRun",
        ]
        request = set_request_params(request, list_optional_params, kwargs)
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
            request = self._get_ecs_request("CreateSecurityGroup")
            request = set_kv_params(request, "Tag", kwargs)
            list_optional_params = [
                "VpcId",
                "Description",
                "ClientToken",
                "SecurityGroupName",
                "SecurityGroupType",
                "ResourceGroupId",
            ]
            request = set_request_params(request, list_optional_params, kwargs)
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
        删除安全组
        """
        try:
            request = self._get_ecs_request("DeleteSecurityGroup")
            request.add_body_params("SecurityGroupId", security_group_id)
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
        """
        try:
            request = self._get_ecs_request("AuthorizeSecurityGroup")
            required_list = ["IpProtocol", "SecurityGroupId", "PortRange"]
            checkout_required_parameters(required_list, kwargs)
            list_request_params = [
                "IpProtocol",
                "SecurityGroupId",
                "PortRange",
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
            request = set_request_params(request, list_request_params, kwargs)
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
        """
        try:
            request = self._get_ecs_request("AuthorizeSecurityGroupEgress")
            required_list = ["IpProtocol", "SecurityGroupId", "PortRange"]
            checkout_required_parameters(required_list, kwargs)
            list_request_params = [
                "IpProtocol",
                "SecurityGroupId",
                "PortRange",
                "DestGroupId",
                "SourceGroupOwnerId",
                "SourceGroupOwnerAccount",
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
            request = set_request_params(request, list_request_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("authorize_security_group")
            logger.exception(kwargs)
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    def revoke_security_group(self, **kwargs):
        """
        删除一条安全组入方向规则，撤销安全组入方向的权限设置。
        """
        try:
            request = self._get_ecs_request("RevokeSecurityGroup")
            required_list = ["IpProtocol", "PortRange", "SecurityGroupId"]
            checkout_required_parameters(required_list, kwargs)
            list_request_params = [
                "IpProtocol",
                "SecurityGroupId",
                "PortRange",
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
            request = set_request_params(request, list_request_params, kwargs)
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
        """
        # todo 没有接口 ecs	RevokeSecurityGroupEgress

    def list_security_group_rules(self, security_group_id, **kwargs):
        """
        查询一个安全组的安全组规则。
        """
        request = self._get_ecs_request("DescribeSecurityGroupAttribute")
        if not security_group_id:
            return {"result": False, "message": "安全组id不能为空"}
        list_optional_params = ["NicType", "Direction"]
        request = set_request_params(request, list_optional_params, kwargs)
        request.add_body_params("SecurityGroupId", security_group_id)
        try:
            ali_result = self._get_result(request, True)
        except Exception as e:
            logger.exception("获取阿里云{}调用接口失败{}".format("security_group_rule", e))
            return {"result": False, "message": str(e)}
        data = self._format_resource_result("security_group_rule", ali_result, **ali_result)
        return {"result": True, "data": data}

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
            request = self._get_ecs_request("ModifySecurityGroupAttribute")
            request.add_body_params("SecurityGroupId", kwargs["SecurityGroupId"])
            list_optional_params = ["SecurityGroupName", "Description"]
            request = set_request_params(request, list_optional_params, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("modify_security_group_attribute")
            return {"result": False, "message": str(e)}

    def modify_security_group_rule(self, **kwargs):
        """
        修改安全组入方向规则的描述信息。该接口只能修改描述信息，如果您需要修改安全组规则的策略、端口范围、授权对象等信息，请在ECS管理控制台修改。
        """
        try:
            request = self._get_ecs_request("ModifySecurityGroupRule")
            required_list = ["IpProtocol", "PortRange", "SecurityGroupId"]
            checkout_required_parameters(required_list, kwargs)
            list_request_params = [
                "IpProtocol",
                "SecurityGroupId",
                "PortRange",
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
            request = set_request_params(request, list_request_params, kwargs)
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
        修改安全组出方向规则的描述信息。该接口只能修改描述信息，如果您需要修改安全组规则的策略、端口范围、授权对象等信息，请在ECS管理控制台修改。
        """
        try:
            request = self._get_ecs_request("ModifySecurityGroupEgressRule")
            required_list = ["IpProtocol", "PortRange", "SecurityGroupId"]
            checkout_required_parameters(required_list, kwargs)
            list_request_params = [
                "IpProtocol",
                "SecurityGroupId",
                "PortRange",
                "DestGroupId",
                "SourceGroupOwnerId",
                "SourceGroupOwnerAccount",
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
            request = set_request_params(request, list_request_params, kwargs)
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
            request = self._get_ecs_request("JoinSecurityGroup")
            required_list = ["InstanceId", "SecurityGroupId"]
            checkout_required_parameters(required_list, kwargs)
            request = set_request_params(request, required_list, kwargs)
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
            request = self._get_ecs_request("LeaveSecurityGroup")
            required_list = ["InstanceId", "SecurityGroupId"]
            checkout_required_parameters(required_list, kwargs)
            request = set_request_params(request, required_list, kwargs)
            self._get_result(request)
            return {"result": True}
        except Exception as e:
            logger.exception("disassociate_security_groups")
            message = str(e)
            if str(e).startswith("SDK.HttpError"):
                message = "连接云服务器失败，请稍后再试！"
            return {"result": False, "message": message}

    # ********************************费用***********************************
    # todo 没有计费相关接口
    def get_storage_list(self, **kwargs):
        """
        获取存储信息列表
        :param kwargs:
        :return:
        """
        storage_list = [
            {"price": 0, "name": "普通云盘", "type": "cloud"},
            {"price": 0, "name": "高效云盘", "type": "cloud_efficiency"},
            {"price": 0, "name": "SSD云盘", "type": "cloud_ssd"},
            {"price": 0, "name": "ESSD云盘", "type": "cloud_essd"},
        ]
        return {"result": True, "data": storage_list}

    # ******************************************* 规格相关接口
    def get_vm_spec(self, cpu, memory, **kwargs):
        """
        查询云服务器ECS提供的所有实例规格的信息 可根据实例规格名  实例规格族名查询
        Args:
            memory (int): 内存
            cpu (int): cpu
        Returns:

        """
        request = self._get_ecs_request("DescribeInstanceTypes")
        if "InstanceTypeFamily" in kwargs:
            request.add_body_params("InstanceTypeFamily", kwargs["InstanceTypeFamily"])
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
        request = self._get_ecs_request("DescribeAvailableResource")
        params = {"ZoneId": zone, "DestinationResource": "InstanceType", "Memory": memory, "Cores": cpu}
        request = set_request_params(request, ["ZoneId", "DestinationResource", "Memory", "Cores"], params)
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
        request = self._get_ecs_request("DescribeAvailableResource")
        param_list = ["ZoneId", "DestinationResource"]
        params = {"ZoneId": zone}
        if instance_type:
            param_list.append("InstanceType")
            params.update({"InstanceType": instance_type, "DestinationResource": "SystemDisk"})
        else:
            param_list.append("ResourceType")
            params.update({"ResourceType": "disk", "DestinationResource": "DataDisk"})
        request = set_request_params(request, param_list, params)
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
        # todo rds找不到DescribeAvailableResource

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
        # todo 找不到DescribeAvailableResource

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
        # todo 找不到DescribeAvailableResource

    def get_spec_price(self, **kwargs):
        return {"result": True, "data": 0}


def set_request_params(request, optional_params, kwargs):
    """
    设置request的非必选请求参数
    :param request: 云接口对应请求实例
    :param optional_params: 需设置的请求参数
    :param kwargs: 传入参数
    :return:
    """
    for _, v in enumerate(optional_params):
        if v in kwargs:
            request.add_body_params(v, kwargs[v])
    return request


def set_kv_params(request, name, kwargs):
    if name in kwargs:
        params = kwargs.get(name)
        for idx, param in enumerate(params):
            if param.get("Key") is not None:
                request.add_body_params(name + "." + str(idx + 1) + ".Key", param["Key"])
            if param.get("Value") is not None:
                request.add_body_params(name + "." + str(idx + 1) + ".Value", param["Value"])

    return request


def set_request_disk_device_mappings(request, kwargs):
    if "DiskDeviceMappings" in kwargs:
        disk_device_mappings = kwargs.get("DiskDeviceMappings")
        for depth1 in range(len(disk_device_mappings)):
            if disk_device_mappings[depth1].get("SnapshotId") is not None:
                request.add_query_param(
                    "DiskDeviceMapping." + str(depth1 + 1) + ".SnapshotId",
                    disk_device_mappings[depth1].get("SnapshotId"),
                )
            if disk_device_mappings[depth1].get("Size") is not None:
                request.add_query_param(
                    "DiskDeviceMapping." + str(depth1 + 1) + ".Size", disk_device_mappings[depth1].get("Size")
                )
            if disk_device_mappings[depth1].get("DiskType") is not None:
                request.add_query_param(
                    "DiskDeviceMapping." + str(depth1 + 1) + ".DiskType", disk_device_mappings[depth1].get("DiskType")
                )
            if disk_device_mappings[depth1].get("Device") is not None:
                request.add_query_param(
                    "DiskDeviceMapping." + str(depth1 + 1) + ".Device", disk_device_mappings[depth1].get("Device")
                )
    return request

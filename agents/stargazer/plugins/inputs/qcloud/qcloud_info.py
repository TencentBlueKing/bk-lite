# -*- coding: utf-8 -*-
# @File：qcloud_info.py.py
# @Time：2025/6/16 15:14
# @Author：bennie
import asyncio
import json
import time
from functools import cached_property
from typing import Dict, List

from plugins.constants import (
    cfs_status_map,
    cfs_storage_type_map,
    clb_isp_map,
    clb_net_type_map,
    clb_status_map,
    client_version_map,
    cmq_status_map,
    cmq_topic_filter_type_map,
    cmq_topic_status_map,
    domain_status_map,
    eip_isp_map,
    eip_pay_type_map,
    eip_res_type_map,
    eip_status_map,
    eip_type_map,
    mongodb_inst_type_map,
    mongodb_pay_type_map,
    mongodb_status_map,
    mysql_pay_type_map,
    mysql_status_map,
    pgsql_pay_type_map,
    pgsql_status_map,
    product_available_region_list_map,
    pulsar_pay_type_map,
    pulsar_status_map,
    redis_region_map,
    redis_status_map,
    redis_sub_status_map,
    redis_type_map,
)
from plugins.inputs.qcloud.region_scope import resolve_collection_regions
from qcloud_cos import CosConfig, CosS3Client
from sanic.log import logger
from tencentcloud.common import credential
from tencentcloud.common.common_client import CommonClient
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

_QCLOUD_PAGE_SIZE = 100
_QCLOUD_PAGE_SAFETY_CAP = 10000


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _join_values(values):
    return ",".join(str(item) for item in (values or []) if item)


def _bool_text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value in (None, ""):
        return ""
    return str(value)


def _as_int(value):
    if value in (None, ""):
        return 0
    return int(value)


def _network_type(instance):
    prop = instance.get("Property")
    if isinstance(prop, str):
        text = prop.strip()
        if not text:
            return ""
        try:
            prop = json.loads(text)
        except json.JSONDecodeError:
            return ""
    if isinstance(prop, dict):
        return prop.get("NetworkType") or ""
    return ""


def _tag_pairs(tags):
    pairs = []
    if isinstance(tags, dict):
        tags = [tags]
    if not isinstance(tags, list):
        return pairs
    for item in tags:
        if not isinstance(item, dict):
            continue
        nested = item.get("Tags")
        if isinstance(nested, list):
            pairs.extend(_tag_pairs(nested))
            continue
        if "Key" in item:
            key = item.get("Key")
            value = item.get("Value")
        elif "TagKey" in item:
            key = item.get("TagKey")
            value = item.get("TagValue")
        else:
            continue
        if key in (None, ""):
            continue
        pairs.append(f"{key}:{'' if value is None else value}")
    return pairs


def _serialize_qcloud_tags(tags):
    """把 TagSet / TagSpecification 收成 key:value 串，空标签留空。"""
    return ",".join(_tag_pairs(tags))


def _join_named(items, key):
    values = []
    for item in items or []:
        value = item.get(key) if isinstance(item, dict) else item
        if value not in (None, ""):
            values.append(str(value))
    return ",".join(values)


def _warn_qcloud_skip(action, region, error, cluster_id=""):
    logger.warning(
        "event=qcloud_collect_skipped action=%s region=%s cluster_id=%s failed_stage=%s error_type=%s",
        action,
        region,
        cluster_id,
        action,
        type(error).__name__,
    )


class TencentClientProxy(object):
    """
    腾讯云客户端代理类（非网络代理）
    """

    def __init__(self, credential: credential.Credential, region: str, profile: ClientProfile):
        self.credential = credential
        self.region = region
        self.profile = profile

    def get_client(self, service_name, version=None):
        if version is None:
            version = client_version_map.get(service_name)
            assert version is not None, "version is not supported"
        assert service_name in client_version_map, "service_name is not supported"
        return CommonClient(service_name, version, self.credential, self.region, self.profile)

    def __getattr__(self, item):
        # 支持client_xxmethod格式的直接调用
        if "_" in item:
            parts = item.split("_", 1)
            if len(parts) == 2:
                service_name, method_name = parts
                client = self.get_client(service_name)
                return getattr(client, method_name)
        # 支持client.xxmethod的链式调用
        return self.get_client(item)


def _first_cloud_secret(params: dict, *keys):
    for key in keys:
        value = params.get(key)
        if value not in (None, ""):
            return value
    return None


class TencentCloudManager:
    def __init__(self, params: dict):
        # 需要提供有全面只读权限的云账号，并允许进行编程访问
        self.params = params
        self.secret_id = _first_cloud_secret(params, "secret_id", "accessKey", "access_key")
        self.secret_key = _first_cloud_secret(params, "secret_key", "accessSecret", "access_secret")
        self.timeout = 60  # 请求超时硬编码；表单 timeout 由框架作单对象预算
        ssl = params.get("ssl", "false")
        self.protocol = "https" if str(ssl).strip().lower() == "true" else "http"

        # 🆕 支持自定义endpoint（私有云场景）
        # 从host参数读取endpoint，如: cvm.private-cloud.example.com
        self.custom_endpoint = params.get("host")
        self.collection_task_id = params.get("collection_task_id")
        self.region_id = str(params.get("region_id") or "").strip()

    def _call_cmq_with_retry(self, region: str, action: str, params: Dict | None = None) -> Dict:
        params = params or {}
        max_retries = 3
        retryable_error_codes = {
            "InternalError",
            "RequestLimitExceeded",
            "RequestTimeout",
        }
        retryable_error_keywords = (
            "timed out",
            "timeout",
            "connection reset",
            "temporarily unavailable",
        )

        for attempt in range(max_retries):
            try:
                return self.get_tencent_client(region=region).cmq.call_json(action, params)
            except TencentCloudSDKException as err:
                if err.code not in retryable_error_codes or attempt == max_retries - 1:
                    raise
                wait_seconds = 2**attempt
                logger.warning(
                    "Retry qcloud cmq action=%s region=%s after sdk error " "code=%s requestId=%s attempt=%s/%s",
                    action,
                    region,
                    err.code,
                    getattr(err, "requestId", None),
                    attempt + 1,
                    max_retries,
                )
                time.sleep(wait_seconds)
            except Exception as err:
                error_message = str(err).lower()
                if attempt == max_retries - 1 or not any(keyword in error_message for keyword in retryable_error_keywords):
                    raise
                wait_seconds = 2**attempt
                logger.warning(f"Retry qcloud cmq action={action} region={region} after transient error, attempt={attempt + 1}/{max_retries}: {err}")
                time.sleep(wait_seconds)

        raise RuntimeError(f"Unexpected retry loop exit for qcloud cmq action={action} region={region}")

    def get_tencent_client(self, region="ap-guangzhou") -> TencentClientProxy:
        """
        params:
            region: 地域
        return: TencentClientProxy
        """
        httpProfile = HttpProfile()
        httpProfile.protocol = self.protocol
        httpProfile.reqTimeout = self.timeout

        # 🆕 如果有自定义endpoint，优先使用
        if self.custom_endpoint:
            httpProfile.endpoint = self.custom_endpoint

        client_profile = ClientProfile()
        client_profile.httpProfile = httpProfile
        cred = self.get_credentials()
        return TencentClientProxy(credential=cred, region=region, profile=client_profile)

    def get_tencent_cos_client(self, region):
        return CosS3Client(CosConfig(SecretId=self.secret_id, SecretKey=self.secret_key, Region=region))

    def get_credentials(self) -> credential.Credential:
        return credential.Credential(self.secret_id, self.secret_key)

    def list_regions(self) -> List[Dict]:
        """获取腾讯云区域信息"""
        return self.get_tencent_client(region="").cvm.call_json("DescribeRegions", {}).get("Response", {}).get("RegionSet", [])

    def get_qcloud_zones(self, region) -> List[Dict]:
        """获取腾讯云可用区信息"""
        try:
            return self.get_tencent_client(region=region).cvm.call_json("DescribeZones", {}).get("Response", {}).get("ZoneSet") or []
        except TencentCloudSDKException as err:
            if err.code == "UnsupportedRegion":
                logger.warning("Skip qcloud zone collection for unsupported region: %s", region)
                return []
            raise

    def _iter_paged_resources(self, region, service, action, list_key, extra_params=None, page_size=_QCLOUD_PAGE_SIZE):
        offset = 0
        extra_params = extra_params or {}
        while offset < _QCLOUD_PAGE_SAFETY_CAP:
            params = dict(extra_params)
            params["Limit"] = page_size
            params["Offset"] = offset
            try:
                payload = getattr(self.get_tencent_client(region=region), service).call_json(action, params)
            except TencentCloudSDKException as err:
                if err.code == "UnsupportedRegion":
                    logger.warning("Skip qcloud %s collection for unsupported region: %s", action, region)
                    return
                raise
            items = (payload.get("Response") or {}).get(list_key) or []
            if not items:
                return
            yield from items
            if len(items) < page_size:
                return
            offset += page_size

    @cached_property
    def available_region_list(self):
        if self.region_id:
            return resolve_collection_regions(self.region_id, [])
        return resolve_collection_regions("", self.list_regions())

    @cached_property
    def zone_id_zone_map(self) -> Dict:
        """获取腾讯云可用区信息"""
        result = {}
        for region in self.available_region_list:
            for zone in self.get_qcloud_zones(region):
                result[zone.get("ZoneId")] = zone.get("Zone")
        return result

    def get_qcloud_cvm(self) -> List[Dict]:
        """获取所有区域的CVM的资源名、资源ID、内网IP、公网IP、地域、可用区、VPC、状态、规格、操作系统名称、vCPU数、内存容量(MB)、付费类型
        doc: https://cloud.tencent.com/document/api/213/15753#Instance
        """
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "cvm", "DescribeInstances", "InstanceSet"):
                result.append(
                    {
                        "resource_name": instance.get("InstanceName"),
                        "resource_id": instance.get("InstanceId"),
                        "ip_addr": _join_values(instance.get("PrivateIpAddresses")),
                        "public_ip": _join_values(instance.get("PublicIpAddresses")),
                        "region": region,
                        "zone": _as_dict(instance.get("Placement")).get("Zone"),
                        "vpc": _as_dict(instance.get("VirtualPrivateCloud")).get("VpcId"),
                        "status": instance.get("InstanceState"),
                        "instance_type": instance.get("InstanceType"),
                        "os_name": instance.get("OsName"),
                        "vcpus": instance.get("CPU"),
                        "memory_mb": instance.get("Memory", 0) * 1024,
                        "charge_type": instance.get("InstanceChargeType"),
                    }
                )
        return result

    def get_qcloud_rocketmq(self) -> List[Dict]:
        """资源名、资源ID、地域、可用区、状态、Topic 总数量、已用Topic 数量、集群 TPS 数量、命名空间数量、Group 数量"""
        result = []
        for region in self.available_region_list:
            for cluster in self._iter_paged_resources(region, "tdmq", "DescribeRocketMQClusters", "ClusterList"):
                info = _as_dict(cluster.get("Info"))
                config = _as_dict(cluster.get("Config"))
                result.append(
                    {
                        "resource_name": info.get("ClusterName"),
                        "resource_id": info.get("ClusterId"),
                        "region": region,
                        "zone": self.zone_id_zone_map.get(info.get("ZoneId")),
                        "status": cluster.get("Status"),
                        "topic_num": config.get("MaxTopicNum"),
                        "used_topic_num": config.get("UsedTopicNum"),
                        "tpsper_name_space": config.get("MaxTpsLimit"),
                        "name_space_num": config.get("MaxNamespaceNum"),
                        "used_name_space_num": config.get("UsedNamespaceNum"),
                        "group_num": config.get("MaxGroupNum"),
                        "used_group_num": config.get("UsedGroupNum"),
                    }
                )
        return result

    def get_qcloud_mysql(self):
        """资源名、资源ID、IP、地域、可用区、状态、硬盘大小(GB)、内存容量(MB)、付费类型"""
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "cdb", "DescribeDBInstances", "Items"):
                result.append(
                    {
                        "resource_name": instance.get("InstanceName"),
                        "resource_id": instance.get("InstanceId"),
                        "ip_addr": instance.get("Vip"),
                        "region": region,
                        "zone": instance.get("Zone"),
                        "status": mysql_status_map.get(instance.get("Status"), "未知"),
                        "volume": instance.get("Volume"),
                        "memory_mb": instance.get("Memory"),
                        "charge_type": mysql_pay_type_map.get(instance.get("PayType"), "未知"),
                    }
                )
        return result

    def get_qcloud_redis_product_conf(self, region="ap-guangzhou"):
        """获取售卖的Redis产品信息,
        参数region即使指定具体地域，也返回所有地域的售卖信息。
        """
        product_info = self.get_tencent_client(region=region).redis.call_json("DescribeProductInfo", {})
        return product_info.get("Response", {}).get("RegionSet", [])

    def get_qcloud_redis(self):
        """资源名、资源ID、IP、VPC、地域、可用区、端口号、外网地址、实例状态、读写状态、
        产品版本、兼容版本、架构版本、内存容量(MB)、分片大小、分片数量、副本数量、最大连接数、最大网络吞吐(Mb/s)
        """

        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "redis", "DescribeInstances", "InstanceSet"):
                result.append(
                    {
                        "resource_name": instance.get("InstanceName"),
                        "resource_id": instance.get("InstanceId"),
                        "ip_addr": instance.get("WanIp"),
                        "vpc": instance.get("VpcId"),
                        "region": redis_region_map.get(instance.get("RegionId")),
                        "zone": self.zone_id_zone_map.get(instance.get("ZoneId")),
                        "port": instance.get("Port"),
                        "wan_address": instance.get("WanAddress"),
                        "status": redis_status_map.get(instance.get("Status"), "未知"),
                        "sub_status": redis_sub_status_map.get(instance.get("SubStatus"), "未知"),
                        "engine": instance.get("Engine"),
                        "version": instance.get("CurrentRedisVersion"),
                        "type": redis_type_map.get(instance.get("Type")),
                        "memory_mb": instance.get("Size"),
                        "shard_size": instance.get("RedisShardSize"),
                        "shard_num": instance.get("RedisShardNum"),
                        "replicas_num": instance.get("RedisReplicasNum"),
                        "client_limit": instance.get("ClientLimit"),
                        "net_limit": instance.get("NetLimit"),
                        "charge_type": instance.get("BillingMode"),
                    }
                )
        return result

    def get_qcloud_mongodb(self):
        """资源名、资源ID、IP、标签、项目ID、VPC、地域、可用区、端口号、实例状态、实例类型、配置类型、版本与引擎、实例CPU核数、
        实例内存规格(MB)、实例磁盘容量(MB)、实例从节点数、Mongod节点CPU核数、Mongod节点内存规格(MB)、Mongod节点数、付费类型"""
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "mongodb", "DescribeDBInstances", "InstanceDetails"):
                result.append(
                    {
                        "resource_name": instance.get("InstanceName"),
                        "resource_id": instance.get("InstanceId"),
                        "ip_addr": instance.get("Vip"),
                        "tag": instance.get("Tags"),
                        "project_id": instance.get("ProjectId"),
                        "vpc": instance.get("VpcId"),
                        "region": instance.get("Region"),
                        "zone": instance.get("Zone"),
                        "port": instance.get("Vport"),
                        "status": mongodb_status_map.get(instance.get("Status"), "未知"),
                        "cluster_type": mongodb_inst_type_map.get(instance.get("InstanceType"), "未知"),
                        "machine_type": instance.get("MachineType"),
                        "version": instance.get("MongoVersion"),
                        "cpu": instance.get("CpuNum"),
                        "memory_mb": instance.get("Memory"),
                        "volume_mb": instance.get("Volume"),
                        "secondary_num": instance.get("SecondaryNum"),
                        "mongos_cpu": instance.get("MongosCpuNum"),
                        "mongos_memory_mb": instance.get("MongosMemory"),
                        "mongos_node_num": instance.get("MongosNodeNum"),
                        "charge_type": mongodb_pay_type_map.get(instance.get("PayMode"), "未知"),
                    }
                )
        return result

    def get_qcloud_pgsql(self):
        """
        资源名、资源ID、标签、项目ID、VPC、地域、可用区、实例状态、字符集、数据库引擎、架构、数据库版本、内核版本、
        实例CPU核数、实例内存规格(MB)、实例磁盘容量(MB)、付费类型
        """
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "postgres", "DescribeDBInstances", "DBInstanceSet"):
                memory = instance.get("DBInstanceMemory") or 0
                volume = instance.get("DBInstanceStorage") or 0
                result.append(
                    {
                        "resource_name": instance.get("DBInstanceName"),
                        "resource_id": instance.get("DBInstanceId"),
                        "tag": instance.get("TagList"),
                        "project_id": instance.get("ProjectId"),
                        "vpc": instance.get("VpcId"),
                        "region": instance.get("Region"),
                        "zone": instance.get("Zone"),
                        "status": pgsql_status_map.get(instance.get("DBInstanceStatus"), "未知"),
                        "charset": instance.get("DBCharset"),
                        "engine": instance.get("DBEngine"),
                        "mode": instance.get("DBInstanceType"),
                        "version": instance.get("DBVersion"),
                        "kernel_version": instance.get("DBKernelVersion"),
                        "cpu": instance.get("DBInstanceCpu"),
                        "memory_mb": memory * 1024,
                        "volume_mb": volume * 1024,
                        "charge_type": pgsql_pay_type_map.get(instance.get("PayType"), "未知"),
                    }
                )
        return result

    def get_qcloud_pulsar_cluster(self):
        """资源名、资源ID、标签、项目ID、地域、状态、版本、内网接入地址、公网接入地址、最大命名空间数、最大Topic数、
        最大QPS、最大消息保留时间(s)、最大存储容量(MB)、最长消息延迟(s)、付费类型"""
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "tdmq", "DescribeClusters", "Instances"):
                result.append(
                    {
                        "resource_name": instance.get("ClusterName"),
                        "resource_id": instance.get("ClusterId"),
                        "tag": instance.get("Tags"),
                        "project_id": instance.get("ProjectId"),
                        "region": region,
                        "status": pulsar_status_map.get(instance.get("Status"), "未知"),
                        "version": instance.get("Version"),
                        "vpc_endpoint": instance.get("VpcEndPoint"),
                        "public_endpoint": instance.get("PublicEndPoint"),
                        "max_namespace_num": instance.get("MaxNamespaceNum"),
                        "max_topic_num": instance.get("MaxTopicNum"),
                        "max_qps": instance.get("MaxQps"),
                        "max_retention_s": instance.get("MessageRetentionTime"),
                        "max_storage_mb": instance.get("MaxStorageCapacity"),
                        "max_delay_s": instance.get("MaxMessageDelayInSeconds"),
                        "charge_type": pulsar_pay_type_map.get(instance.get("PayMode"), "未知"),
                    }
                )
        return result

    def get_qcloud_cmq(self):
        """资源名、资源ID、标签、地域、状态、消息最大未确认时间(s)、消息接收长轮询等待时间(s)、取出消息隐藏时长(s)、消息最大长度(B)、QPS限制"""
        result = []
        for region in product_available_region_list_map.get("cmq", []):
            try:
                cmq_info = self._call_cmq_with_retry(region=region, action="DescribeQueueDetail")
            except TencentCloudSDKException as err:
                logger.warning(
                    f"Skip qcloud cmq collection action=DescribeQueueDetail region={region} "
                    f"code={err.code} requestId={getattr(err, 'requestId', None)} message={err.message}"
                )
                continue
            except Exception as err:
                logger.warning(f"Skip qcloud cmq collection action=DescribeQueueDetail region={region} " f"after transient retries exhausted: {err}")
                continue
            instances = cmq_info.get("Response", {}).get("QueueSet", [])
            result.extend(
                [
                    {
                        "resource_name": instance.get("QueueName"),
                        "resource_id": instance.get("QueueId"),
                        "tag": instance.get("Tags"),
                        "region": region,
                        "status": cmq_status_map.get(instance.get("Migrate"), "未知"),
                        "max_delay_s": instance.get("msgRetentionSeconds"),  # 消息最大未确认时间(s)
                        "polling_wait_s": instance.get("PollingWaitSeconds"),  # 消息接收长轮询等待时间(s)
                        "visibility_timeout_s": instance.get("visibilityTimeout"),  # 取出消息隐藏时长(s)
                        "max_message_b": instance.get("maxMsgSize"),  # 消息最大长度(B)
                        "qps": instance.get("Qps"),  # QPS限制
                    }
                    for instance in instances
                ]
            )
        return result

    def get_qcloud_cmq_topic(self):
        """资源名、资源ID、标签、地域、状态、消息生命周期、消息最大长度(B)、消息过滤类型、QPS限制"""
        result = []
        for region in product_available_region_list_map.get("cmq", []):
            try:
                topic_info = self._call_cmq_with_retry(region=region, action="DescribeTopicDetail")
            except TencentCloudSDKException as err:
                logger.warning(
                    f"Skip qcloud cmq topic collection action=DescribeTopicDetail region={region} "
                    f"code={err.code} requestId={getattr(err, 'requestId', None)} message={err.message}"
                )
                continue
            except Exception as err:
                logger.warning(
                    f"Skip qcloud cmq topic collection action=DescribeTopicDetail region={region} " f"after transient retries exhausted: {err}"
                )
                continue
            instances = topic_info.get("Response", {}).get("TopicSet", [])
            result.extend(
                [
                    {
                        "resource_name": instance.get("TopicName"),
                        "resource_id": instance.get("TopicId"),
                        "tag": instance.get("Tags"),
                        "region": region,
                        "status": cmq_topic_status_map.get(instance.get("Migrate"), "未知"),
                        "max_retention_s": instance.get("MsgRetentionSeconds"),  # 消息生命周期
                        "max_message_b": instance.get("MaxMsgSize"),  # 消息最大长度(B)
                        "filter_type": cmq_topic_filter_type_map.get(instance.get("FilterType"), "未知"),  # 消息过滤类型
                        "qps": instance.get("Qps"),  # QPS限制
                    }
                    for instance in instances
                ]
            )
        return result

    def get_qcloud_clb(self):
        """资源名、资源ID、标签、项目ID、安全组ID、VPC、地域、主可用区、备可用区、状态、域名、VIP、网络类型、运营商、付费类型"""
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "clb", "DescribeLoadBalancers", "LoadBalancerSet"):
                backup_zones = [_as_dict(zone).get("Zone") for zone in (instance.get("BackupZoneSet") or [])]
                result.append(
                    {
                        "resource_name": instance.get("LoadBalancerName"),
                        "resource_id": instance.get("LoadBalancerId"),
                        "tag": instance.get("Tags"),
                        "project_id": instance.get("ProjectId"),
                        "security_group_id": instance.get("SecurityGroup"),
                        "vpc": instance.get("VpcId"),
                        "region": region,
                        "master_zone": _as_dict(instance.get("MasterZone")).get("Zone"),
                        "backup_zone": _join_values(backup_zones),
                        "status": clb_status_map.get(instance.get("Status"), "未知"),
                        "domain": instance.get("Domain"),
                        "ip_addr": _join_values(instance.get("LoadBalancerVips")),
                        "type": clb_net_type_map.get(instance.get("LoadBalancerType"), "未知"),
                        "isp": clb_isp_map.get(instance.get("VipIsp"), "未知"),
                        "charge_type": instance.get("ChargeType"),
                    }
                )
        return result

    def get_qcloud_eip(self):
        """资源名、资源ID、标签、地域、状态、类型、公网IP地址、绑定资源类型、绑定资源ID、线路类型、付费类型"""
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "vpc", "DescribeAddresses", "AddressSet"):
                result.append(
                    {
                        "resource_name": instance.get("AddressName") or "未命名",
                        "resource_id": instance.get("AddressId"),
                        "tag": instance.get("TagSet"),
                        "region": region,
                        "status": eip_status_map.get(instance.get("AddressStatus"), "未知"),
                        "type": eip_type_map.get(instance.get("AddressType"), "未知"),
                        "ip_addr": instance.get("AddressIp"),
                        "instance_type": eip_res_type_map.get(instance.get("InstanceType"), "未知"),
                        "instance_id": instance.get("InstanceId"),
                        "isp": eip_isp_map.get(instance.get("InternetServiceProvider"), "未知"),
                        "charge_type": eip_pay_type_map.get(instance.get("InternetChargeType"), "未知"),
                    }
                )
        return result

    def get_qcloud_tke_cluster(self) -> List[Dict]:
        """TKE 集群。DescribeClusters → ClusterId。"""
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "tke", "DescribeClusters", "Clusters"):
                network = _as_dict(instance.get("ClusterNetworkSettings"))
                result.append(
                    {
                        "resource_name": instance.get("ClusterName"),
                        "resource_id": instance.get("ClusterId"),
                        "region": region,
                        "status": instance.get("ClusterStatus"),
                        "cluster_type": instance.get("ClusterType"),
                        "version": instance.get("ClusterVersion"),
                        "vpc": network.get("VpcId"),
                        "cluster_cidr": network.get("ClusterCIDR"),
                        "service_cidr": network.get("ServiceCIDR"),
                        "network_type": _network_type(instance),
                        "node_num": _as_int(instance.get("ClusterNodeNum")),
                        "master_node_num": _as_int(instance.get("ClusterMaterNodeNum")),
                        "runtime": instance.get("ContainerRuntime"),
                        "runtime_version": instance.get("RuntimeVersion"),
                        "os_name": instance.get("ClusterOs"),
                        "project_id": instance.get("ProjectId"),
                        "cluster_level": instance.get("ClusterLevel"),
                        "ha": _bool_text(instance.get("IsHighAvailability")),
                        "create_time": instance.get("CreatedTime"),
                        "deletion_protection": _bool_text(instance.get("DeletionProtection")),
                        "tag": _serialize_qcloud_tags(instance.get("TagSpecification")),
                    }
                )
        return result

    def _collect_tke_cluster_nodes(self, region, cluster_id) -> List[Dict]:
        nodes = []
        for instance in self._iter_paged_resources(
            region,
            "tke",
            "DescribeClusterInstances",
            "InstanceSet",
            extra_params={"ClusterId": cluster_id},
        ):
            resource_id = instance.get("InstanceId") or ""
            nodes.append(
                {
                    "resource_name": resource_id or instance.get("LanIP") or "",
                    "resource_id": resource_id,
                    "region": region,
                    "cluster_id": cluster_id,
                    "ip_addr": instance.get("LanIP"),
                    "instance_role": instance.get("InstanceRole"),
                    "status": instance.get("InstanceState"),
                    "node_pool_id": instance.get("NodePoolId") or "",
                    "create_time": instance.get("CreatedTime"),
                    "tag": "",
                }
            )
        return nodes

    def get_qcloud_tke_node(self) -> List[Dict]:
        """先列集群，再按 ClusterId 拉节点。单个集群失败只跳过该集群。"""
        result = []
        regions = list(self.available_region_list)
        listed_ok = not regions
        clusters_seen = 0
        instance_failures = 0
        for region in regions:
            try:
                clusters = list(self._iter_paged_resources(region, "tke", "DescribeClusters", "Clusters"))
            except Exception as err:
                _warn_qcloud_skip("DescribeClusters", region, err)
                continue
            listed_ok = True
            for cluster in clusters:
                cluster_id = str(_as_dict(cluster).get("ClusterId") or "").strip()
                if not cluster_id:
                    continue
                clusters_seen += 1
                try:
                    result.extend(self._collect_tke_cluster_nodes(region, cluster_id))
                except Exception as err:
                    instance_failures += 1
                    _warn_qcloud_skip("DescribeClusterInstances", region, err, cluster_id)
        if regions and not listed_ok:
            raise RuntimeError("qcloud tke node collection failed for all regions")
        if clusters_seen and instance_failures == clusters_seen and not result:
            raise RuntimeError("qcloud tke node collection failed for all clusters")
        return result

    def get_qcloud_vpn_gateway(self) -> List[Dict]:
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "vpc", "DescribeVpnGateways", "VpnGatewaySet"):
                result.append(
                    {
                        "resource_name": instance.get("VpnGatewayName"),
                        "resource_id": instance.get("VpnGatewayId"),
                        "region": region,
                        "zone": instance.get("Zone"),
                        "vpc": instance.get("VpcId"),
                        "status": instance.get("State"),
                        "type": instance.get("Type"),
                        "ip_addr": instance.get("PublicIpAddress"),
                        "bandwidth_mbps": _as_int(instance.get("InternetMaxBandwidthOut")),
                        "charge_type": instance.get("InstanceChargeType"),
                        "create_time": instance.get("CreatedTime"),
                        "expired_time": instance.get("ExpiredTime"),
                        "renew_flag": instance.get("RenewFlag"),
                        "version": instance.get("Version"),
                        "max_connection": _as_int(instance.get("MaxConnection")),
                        "tag": _serialize_qcloud_tags(instance.get("TagSet")),
                    }
                )
        return result

    def get_qcloud_customer_gateway(self) -> List[Dict]:
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "vpc", "DescribeCustomerGateways", "CustomerGatewaySet"):
                result.append(
                    {
                        "resource_name": instance.get("CustomerGatewayName"),
                        "resource_id": instance.get("CustomerGatewayId"),
                        "region": region,
                        "ip_addr": instance.get("IpAddress"),
                        "create_time": instance.get("CreatedTime"),
                        "tag": _serialize_qcloud_tags(instance.get("TagSet")),
                    }
                )
        return result

    def get_qcloud_vpn_connection(self) -> List[Dict]:
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "vpc", "DescribeVpnConnections", "VpnConnectionSet"):
                result.append(
                    {
                        "resource_name": instance.get("VpnConnectionName"),
                        "resource_id": instance.get("VpnConnectionId"),
                        "region": region,
                        "vpc": instance.get("VpcId"),
                        "vpn_gateway_id": instance.get("VpnGatewayId"),
                        "customer_gateway_id": instance.get("CustomerGatewayId"),
                        "status": instance.get("State"),
                        "net_status": instance.get("NetStatus"),
                        "vpn_proto": instance.get("VpnProto"),
                        "route_type": instance.get("RouteType"),
                        "create_time": instance.get("CreatedTime"),
                        "tag": _serialize_qcloud_tags(instance.get("TagSet")),
                    }
                )
        return result

    def get_qcloud_nat_gateway(self) -> List[Dict]:
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "vpc", "DescribeNatGateways", "NatGatewaySet"):
                addresses = instance.get("PublicIpAddressSet") or []
                result.append(
                    {
                        "resource_name": instance.get("NatGatewayName"),
                        "resource_id": instance.get("NatGatewayId"),
                        "region": region,
                        "zone": instance.get("Zone"),
                        "vpc": instance.get("VpcId"),
                        "subnet": instance.get("SubnetId"),
                        "status": instance.get("State"),
                        "network_state": instance.get("NetworkState"),
                        "bandwidth_mbps": _as_int(instance.get("InternetMaxBandwidthOut")),
                        "max_concurrent": _as_int(instance.get("MaxConcurrentConnection")),
                        "eip_ids": _join_named(addresses, "AddressId"),
                        "eip_addrs": _join_named(addresses, "PublicIpAddress"),
                        "product_version": instance.get("NatProductVersion"),
                        "restrict_state": instance.get("RestrictState"),
                        "create_time": instance.get("CreatedTime"),
                        "tag": _serialize_qcloud_tags(instance.get("TagSet")),
                    }
                )
        return result

    def get_qcloud_bucket(self):
        """资源名、资源ID、地域"""
        result = []
        for region in self.available_region_list:
            bucket_payload = self.get_tencent_cos_client(region=region).list_buckets().get("Buckets") or {}
            buckets = bucket_payload.get("Bucket") or []
            for bucket in buckets:
                result.append(
                    {
                        "resource_name": bucket.get("Name"),
                        "resource_id": bucket.get("Name"),
                        "region": bucket.get("Location"),
                    }
                )
        return result

    def get_qcloud_filesystem(self):
        """资源名、资源ID、标签、地域、可用区、状态、文件系统协议、存储类型、吞吐上限(MiB/s)、总容量(GiB)"""
        result = []
        for region in self.available_region_list:
            for instance in self._iter_paged_resources(region, "cfs", "DescribeCfsFileSystems", "FileSystems"):
                result.append(
                    {
                        "resource_name": instance.get("FsName"),
                        "resource_id": instance.get("FileSystemId"),
                        "tag": instance.get("Tags"),
                        "region": region,
                        "zone": instance.get("Zone"),
                        "status": cfs_status_map.get(instance.get("LifeCycleState"), "未知"),
                        "protocol": instance.get("Protocol"),
                        "type": cfs_storage_type_map.get(instance.get("StorageType"), "未知"),
                        "net_limit": instance.get("BandwidthLimit"),
                        "size_gib": instance.get("Capacity"),
                    }
                )
        return result

    def get_qcloud_domain(self):
        """资源名、资源ID、域名后缀、状态、到期时间"""
        domain_info = self.get_tencent_client("").domain.call_json("DescribeDomainNameList", {})
        return [
            {
                "resource_name": instance.get("DomainName"),
                "resource_id": instance.get("DomainId"),
                "tld": instance.get("CodeTld"),  # 域名后缀
                "status": domain_status_map.get(instance.get("BuyStatus"), "未知"),
                "expired_time": instance.get("ExpirationDate"),  # 到期时间
            }
            for instance in domain_info.get("DomainList", [])
        ]

    def exec_script(self):
        def handle_resource(resource_func, resource_name):
            try:
                return {resource_name: resource_func()}
            except Exception as err:
                logger.warning(f"Skip qcloud resource={resource_name} after collection error: {err}")
                return {resource_name: {"cmdb_collect_error": str(err)}}

        resources = [
            (self.get_qcloud_cvm, "qcloud_cvm"),
            (self.get_qcloud_rocketmq, "qcloud_rocketmq"),
            (self.get_qcloud_mysql, "qcloud_mysql"),
            (self.get_qcloud_redis, "qcloud_redis"),
            (self.get_qcloud_mongodb, "qcloud_mongodb"),
            (self.get_qcloud_pgsql, "qcloud_pgsql"),
            (self.get_qcloud_pulsar_cluster, "qcloud_pulsar_cluster"),
            (self.get_qcloud_cmq, "qcloud_cmq"),
            (self.get_qcloud_cmq_topic, "qcloud_cmq_topic"),
            (self.get_qcloud_clb, "qcloud_clb"),
            (self.get_qcloud_eip, "qcloud_eip"),
            (self.get_qcloud_tke_cluster, "qcloud_tke_cluster"),
            (self.get_qcloud_tke_node, "qcloud_tke_node"),
            (self.get_qcloud_vpn_gateway, "qcloud_vpn_gateway"),
            (self.get_qcloud_customer_gateway, "qcloud_customer_gateway"),
            (self.get_qcloud_vpn_connection, "qcloud_vpn_connection"),
            (self.get_qcloud_nat_gateway, "qcloud_nat_gateway"),
            (self.get_qcloud_bucket, "qcloud_bucket"),
            (self.get_qcloud_filesystem, "qcloud_filesystem"),
            (self.get_qcloud_domain, "qcloud_domain"),
        ]

        result = {}
        for resource_func, resource_name in resources:
            _data = handle_resource(resource_func, resource_name)
            result.update(_data)
        return result

    async def list_all_resources(self):
        return await asyncio.to_thread(self._list_all_resources_sync)

    def _list_all_resources_sync(self):
        try:
            result = self.exec_script()
            inst_data = {"result": result, "success": True}
        except Exception as err:
            logger.exception(
                "event=qcloud_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                self.custom_endpoint,
                self.collection_task_id,
                "list_all_resources",
                type(err).__name__,
            )
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return inst_data

    def test_connection(self):
        """
        Test connection to Tencent Cloud Api
        : return  True if connection is successful, False otherwise
        """
        try:
            self.list_regions()
            return True
        except Exception as err:
            logger.exception(
                "event=qcloud_test_connection_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                self.custom_endpoint,
                self.collection_task_id,
                "test_connection",
                type(err).__name__,
            )
            return False


if __name__ == "__main__":
    import os

    params = {
        "secret_id": os.getenv("qcloud_secret_id"),
        "secret_key": os.getenv("qcloud_secret_key"),
    }
    manager = TencentCloudManager(params)
    client = manager.get_tencent_client("")

    # print(manager.get_qcloud_cvm())
    # print(manager.get_qcloud_bucket())
    print(client.organization.call_json("DescribeOrganization", {}))

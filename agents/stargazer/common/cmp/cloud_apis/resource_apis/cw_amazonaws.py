# -*- coding: UTF-8 -*-
import collections
import copy
import datetime
import hashlib
import hmac
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import parse

import boto3
import requests
import xmltodict

from common.cmp.cloud_apis.base import PublicCloudManage
from common.cmp.cloud_apis.common import local_to_utc, utc_to_ts
from common.cmp.cloud_apis.constant import CloudResourceType, CloudType
from common.cmp.cloud_apis.resource_apis.resource_format.amazonaws.amazonaws_constant import (
    AmazonAwsAttachStatus,
    AmazonAwsVMStatus,
)
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.cloud_apis.resource_apis.utils import fail, success
from core.logger import logger

https_port = "443"


class CwAmazonAws(object):
    """
    通过该类创建AmazonAws的Client实例，
    """

    def __init__(self, access_key, secret_key, region_id, **kwargs):
        """
        初始化方法，创建实例
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.region_id = "us-east-1" if not region_id else region_id

    def __getattr__(self, item):
        """
        private方法，返回对应的接口类
        """
        return AmazonAws(
            name=item,
            region_id=self.region_id,
            access_key=self.access_key,
            secret_key=self.secret_key,
        )


class AmazonAws(PublicCloudManage):
    """
    AmazonAws接口类
    """

    def __init__(self, name, region_id, access_key, secret_key):
        """
        初始化方法
        """
        self.version = "2016-11-15"
        self.region_id = region_id
        self.name = name
        self.access_key = access_key
        self.secret_key = secret_key
        self.cloud_type = CloudType.AMAZONAWS.value
        self.kafka_client = boto3.client(
            "kafka",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_id,
        )
        self.cf_client = boto3.client(
            "cloudfront",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_id,
        )
        self.eks_client = boto3.client(
            "eks",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_id,
        )
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_id,
        )

        self.docdb_client = boto3.client(
            "docdb",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_id,
        )
        self.memdb_client = boto3.client(
            "memorydb",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_id,
        )

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        connection_result = self.list_regions()
        return {"result": connection_result["result"]}

    def list_regions(self, regions_name=None, next_token=None, **kwargs):
        service = "ec2"
        request_field = "RegionName"
        response_field = "regionInfo"
        resource_id_list = {"Version": self.version}
        action = "DescribeRegions"
        resource_id_list.update(kwargs)
        if regions_name:
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(regions_name):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
            )
        )

    def list_zones(self, zones_name=None, next_token=None, **kwargs):
        service = "ec2"
        request_field = "ZoneId"
        response_field = "availabilityZoneInfo"
        resource_id_list = {"Version": self.version}
        action = "DescribeAvailabilityZones"
        resource_id_list.update(kwargs)
        if zones_name:
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(zones_name):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
            )
        )

    # *********************** Vm *****************************************
    def list_vms(self, vms_id=None, next_token=None, _format=True, **kwargs):
        service = "ec2"
        request_field = "InstanceId"
        response_field = "reservationSet"
        resource_id_list = {"Version": self.version}
        action = "DescribeInstances"
        resource_id_list.update(kwargs)
        if vms_id:
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(vms_id):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
                _format=_format,
            )
        )

    def list_rds(self, next_token=None, _format=True, **kwargs):

        service = "rds"
        response_field = "DBInstances"
        resource_id_list = {"Version": "2014-10-31"}
        action = "DescribeDBInstances"

        rds_data = request_get_list(
            service,
            action,
            response_field,
            next_token,
            region_id=self.region_id,
            access_key=self.access_key,
            secret_key=self.secret_key,
            action_dict=resource_id_list,
            item_field="DBInstance",
            _format=_format,
        )
        if isinstance(rds_data, dict):
            return rds_data
        certificate_ca_map = {}
        certificates = self.list_certificates(_format=False)
        if certificates.get("result"):
            for certificate in certificates.get("data", []):
                certificate_name = certificate.get("CertificateIdentifier")
                certificate_ca_map[certificate_name] = certificate

        for rds in rds_data:
            rds["Certificate"] = certificate_ca_map.get(rds.get("CACertificateIdentifier", ""), OrderedDict())
        return success(rds_data)

    def list_msk_clusters(self, next_token=None, _format=True, **kwargs):
        try:
            resp = self.kafka_client.list_clusters()
            if resp.get("ClusterInfoList"):
                data = resp.get("ClusterInfoList")
                for i in data:
                    # 补充region_id
                    i["region_id"] = self.region_id
                return success(data)
            logger.info(f"list msk clusters failed, response: {resp}")
            return fail("list msk clusters failed")
        except Exception:
            logger.exception("list msk clusters failed")
            return fail("list msk clusters failed")

    def list_elasticaches(self, next_token=None, _format=True, **kwargs):
        service = "elasticache"
        response_field = "ReplicationGroups"
        resource_id_list = {"Version": "2015-02-02"}
        action = "DescribeReplicationGroups"

        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
                item_field="ReplicationGroup",
                _format=_format,
            )
        )

    def list_elasticaches_nodes(self, next_token=None, _format=True, **kwargs):
        service = "elasticache"
        response_field = "CacheClusters"
        resource_id_list = {"Version": "2015-02-02"}
        action = "DescribeCacheClusters"

        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
                item_field="CacheCluster",
                _format=_format,
            )
        )

    def list_certificates(self, next_token=None, _format=True, **kwargs):
        service = "rds"
        response_field = "Certificates"
        resource_id_list = {"Version": "2014-10-31"}
        action = "DescribeCertificates"

        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
                item_field="Certificate",
                _format=_format,
            )
        )

    def list_eks_clusters(self, next_token=None, _format=True, **kwargs):
        eks_clusters = []
        try:
            while True:
                resp = (
                    self.eks_client.list_clusters(NextToken=next_token)
                    if next_token
                    else self.eks_client.list_clusters()
                )
                if not resp.get("clusters"):
                    break
                items = resp.get("clusters")
                for item in items:
                    item_resp = self.eks_client.describe_cluster(name=item)
                    item_dict = {}
                    if item_resp.get("cluster"):
                        item_dict.update(region_id=self.region_id)
                        item_dict.update(item_resp.get("cluster"))
                    eks_clusters.append(item_dict)

                next_token = resp.get("NextToken")
                if not next_token:
                    break
            for i in eks_clusters:
                i["region_id"] = self.region_id
            return success(eks_clusters)
        except Exception:
            logger.exception("list eks clusters failed")
            return fail("list eks clusters failed")

    def list_cf_distributions(self, next_token=None, _format=True, **kwargs):
        cf_distributions = []
        try:
            # 分页获取
            while True:
                resp = (
                    self.cf_client.list_distributions(Marker=next_token)
                    if next_token
                    else self.cf_client.list_distributions()
                )
                if not resp.get("DistributionList"):
                    break
                items = resp.get("DistributionList").get("Items")
                for item in items:
                    item["region_id"] = self.region_id
                cf_distributions.extend(items)
                next_token = resp.get("DistributionList").get("NextMarker")
                if not next_token:
                    break
            return success(cf_distributions)
        except Exception:
            logger.exception("list cf distributions failed")
            return fail("list cf distributions failed")

    def list_elbs(self, next_token=None, _format=True, **kwargs):
        service = "elasticloadbalancing"
        response_field = "DescribeLoadBalancersResponse"
        resource_id_list = {"Version": "2015-12-01", "PageSize": 300}
        action = "DescribeLoadBalancers"

        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
                item_field="DescribeLoadBalancersResult.LoadBalancers.member",
                _format=_format,
            )
        )

    def list_s3_buckets(self, next_token=None, _format=True, timeout=5, **kwargs):
        """
        获取S3桶列表,添加超时,如果请求过长,之间返回异常
        """
        s3_buckets = []
        endpoint = self.s3_client._endpoint.host
        try:
            requests.get(endpoint, verify=False, timeout=timeout)
        except Exception as e:
            logger.exception(f"list s3 buckets failed, endpoint:{endpoint} error:{e}")
            return fail(f"list s3 buckets failed, endpoint:{endpoint} error:{e}")

        try:
            while True:
                resp = (
                    self.s3_client.list_buckets(ContinuationToken=next_token, MaxBuckets=300)
                    if next_token
                    else self.s3_client.list_buckets(timeout=10)
                )
                if not resp.get("Buckets"):
                    break
                items = resp.get("Buckets")
                for item in items:
                    item["region_id"] = self.region_id
                s3_buckets.extend(items)
                next_token = resp.get("ContinuationToken")
                if not next_token:
                    break
            return success(s3_buckets)
        except Exception:
            logger.exception("list s3 buckets failed")
            return fail("list s3 buckets failed")

    def list_docdb_clusters(self, next_token=None, _format=True, **kwargs):
        docdb_clusters = []
        try:
            # 分页获取
            while True:
                resp = (
                    self.docdb_client.describe_db_clusters(Marker=next_token)
                    if next_token
                    else self.docdb_client.describe_db_clusters()
                )
                if not resp.get("DBClusters"):
                    break
                items = resp.get("DBClusters")
                for item in items:
                    item["region_id"] = self.region_id
                docdb_clusters.extend(items)
                next_token = resp.get("Marker")
                if not next_token:
                    break
            return success(docdb_clusters)
        except Exception:
            logger.exception("list docdb clusters failed")
            return fail("list docdb clusters failed")

    def list_memdb_clusters(self, next_token=None, _format=True, **kwargs):
        memdb_clusters = []
        try:
            # 分页获取
            while True:
                resp = (
                    self.memdb_client.describe_clusters(Marker=next_token)
                    if next_token
                    else self.memdb_client.describe_clusters()
                )
                if not resp.get("Clusters"):
                    break
                items = resp.get("Clusters")
                for item in items:
                    item["region_id"] = self.region_id
                memdb_clusters.extend(items)
                next_token = resp.get("Marker")
                if not next_token:
                    break
            return success(memdb_clusters)
        except Exception:
            logger.exception("list memdb clusters failed")
            return fail("list memdb clusters failed")

    def list_all_resources(self, **kwargs):
        def handle_resource(resource_func, resource_name):
            result = resource_func()
            if result.get("result"):
                return {resource_name: result.get("data", [])}
            return {}

        data = {}
        resources = [
            (self.list_vms, "aws_ec2"),
            (lambda: self.list_rds(_format=False), "aws_rds"),
            (lambda: self.list_msk_clusters(_format=False), "aws_msk_cluster"),
            (lambda: self.list_elasticaches(_format=False), "aws_elasticache"),
            (lambda: self.list_eks_clusters(_format=False), "aws_eks_cluster"),
            (lambda: self.list_cf_distributions(_format=False), "aws_cf_distribution"),
            (lambda: self.list_elbs(_format=False), "aws_elb"),
            (lambda: self.list_s3_buckets(_format=False), "aws_s3_bucket"),
            (lambda: self.list_docdb_clusters(_format=False), "aws_docdb_cluster"),
            (lambda: self.list_memdb_clusters(_format=False), "aws_memdb_cluster"),
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

    obj_map = {
        "aws_ec2": {
            "metrics": ["CPUUtilization", "NetworkIn", "NetworkOut", "NetworkPacketsIn", "NetworkPacketsOut"],
            "namespace": "AWS/EC2",
            "dimension_key": "InstanceId",
        },
        "aws_rds": {
            "metrics": [
                "CPUUtilization",
                "DatabaseConnections",
                "DBLoad",
                "FreeStorageSpace",
                "EBSByteBalance",
                "EBSIOBalance",
                "FreeableMemory",
                "MaximumUsedTransactionIDs",
                "ReadLatency",
                "WriteLatency",
            ],
            "namespace": "AWS/RDS",
            "dimension_key": "DBInstanceIdentifier",
        },
        # "aws_msk_cluster": {
        #     "metrics": ["CpuUser", "KafkaDataLogsDiskUsed", "NetworkTxPackets", "NetworkRxPackets"],
        #     "namespace": "AWS/Kafka",
        #     "dimension_key": "Cluster Name"
        #
        # },
        # "aws_elasticache": {
        #     "metrics": [
        #         "DatabaseMemoryUsagePercentage",
        #         "CPUUtilization",
        #         "DatabaseCapacityUsagePercentage",
        #         "CacheHitRate",
        #         "FreeableMemory",
        #         "NetworkPacketsOut",
        #         "NetworkPacketsIn",
        #         "NetworkBytesIn",
        #         "NetworkBytesOut",
        #         "CurrConnections",
        #     ],
        #     "namespace": "AWS/ElastiCache",
        #     "dimension_key": "CacheClusterId",
        # },
    }

    def _get_monitor(
        self, namespace, dimensions, metric_name, start_time, end_time, period, inst_region=None, **kwargs
    ):
        """"""
        service = "monitoring"
        action = "GetMetricStatistics"
        start_time = local_to_utc(start_time)
        end_time = local_to_utc(end_time)
        params = {
            "Version": "2010-08-01",
            "Namespace": namespace,
            "MetricName": metric_name,
            "StartTime": start_time,
            "EndTime": end_time,
            "Period": period,
            "Statistics.member.1": "Average",
        }
        for index, dimension in enumerate(dimensions):
            params.update(
                {
                    f"Dimensions.member.{index + 1}.Name": dimension.get("Name"),
                    f"Dimensions.member.{index + 1}.Value": dimension.get("Value"),
                }
            )

        sorted_params = sorted(params.items(), key=lambda item: item[0])
        action = "{}&{}".format(action, parse.urlencode(flat_dict(dict(sorted_params))))
        return self.handle_action_request(service, action, inst_region=inst_region)

    # def get_msk_cluster_broker_id(self, cluster_arn):
    #     msk_cluster_broker_ids = []
    #     try:
    #         while True:
    #             resp = self.kafka_client.list_nodes(ClusterArn=cluster_arn)
    #             if not resp.get("NodeInfoList"):
    #                 break
    #             msk_cluster_broker_ids.extend(
    #                 [node.get("BrokerNodeInfo").get("BrokerId") for node in resp.get("NodeInfoList")])
    #             next_token = resp.get("NextToken")
    #             if not next_token:
    #                 break
    #             logger.info(f"list msk cluster brokers failed, response: {resp}")
    #         return msk_cluster_broker_ids
    #     except Exception:
    #         logger.exception("list msk cluster brokers failed")
    #         return []
    #
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
        resources = kwargs.get("context", {}).get("resources", [])

        if not resources:
            return {"result": False, "message": "未获取到实例信息"}
        bk_obj_id = resources[0]["bk_obj_id"]
        default_metric = self.obj_map.get(bk_obj_id, {}).get("metrics", [])
        metrics = kwargs.get("Metrics", default_metric) or default_metric
        # msk_brokers = {}
        # if bk_obj_id == "aws_msk_cluster":
        #     msks = self.list_msk_clusters(_format=False)
        #     if not msks.get("result"):
        #         return fail("get msk cluster failed")
        #     for msk in msks.get("data", []):
        #         cluster_arn = msk.get("ClusterArn")
        #         cluster_name = msk.get("ClusterName")
        #         brokers = self.get_msk_cluster_broker_id(cluster_arn)
        #         msk_brokers[cluster_name] = brokers
        namespace = self.obj_map.get(bk_obj_id, {}).get("namespace", "")
        metrics_params = []
        for metric in metrics:
            aws_metric = metric
            if metric in ["EBSByteBalance", "EBSIOBalance"]:
                aws_metric = metric + "%"
            for res_dict in resources:
                region = res_dict.get("extra", {}).get("region", "")
                dimensions = []
                resource_id = res_dict.get("resource_id", "")
                dimension_key = self.obj_map.get(bk_obj_id, {}).get("dimension_key", "")

                # if bk_obj_id == "aws_msk_cluster":
                #     brokers = msk_brokers.get(resource_id, [])
                #     for broker in brokers:
                #         dimension = [{"Name": dimension_key, "Value": resource_id},
                #                      {"Name": "Broker Id", "Value": str(broker)}]
                #         dimensions.append(dimension)
                # if bk_obj_id == "aws_elasticache":
                #     dimension = [
                #         {"Name": dimension_key, "Value": resource_id},
                #         {"Name": "CacheNodeId", "Value": "0001"},
                #     ]
                #     dimensions.append(dimension)
                # else:
                dimension = [{"Name": dimension_key, "Value": resource_id}]
                dimensions.append(dimension)
                for dimension in dimensions:
                    metrics_params.append(
                        {
                            "resource_id": resource_id,
                            "origin_metric": metric,
                            "namespace": namespace,
                            "dimensions": dimension,
                            "metric_name": aws_metric,
                            "start_time": data["StartTime"],
                            "end_time": data["EndTime"],
                            "period": data["Period"],
                            "inst_region": region,
                        }
                    )
        try:
            for metrics_param in metrics_params:
                metric_result = self._get_monitor(**metrics_param)
                resource_id = metrics_param.get("resource_id")
                metric = metrics_param.get("origin_metric")
                if not metric_result["Status"]:
                    continue
                content = metric_result["Content"]
                points = (
                    content.get("GetMetricStatisticsResponse", {})
                    .get("GetMetricStatisticsResult", {})
                    .get("Datapoints", {})
                )
                if not points:
                    continue
                points = points.get("member", [])
                points = points if isinstance(points, list) else [points]
                for point in points:
                    timestamp = utc_to_ts(point.get("Timestamp"))
                    value = point.get("Average")
                    if value is None:
                        continue
                    value = round(float(value), 2)
                    res.setdefault(resource_id, {}).setdefault(metric, []).append([timestamp, value])
            return success(res)
        except Exception as e:
            logger.exception("get monitor data failed")
            return fail("get monitor data failed:{}".format(str(e)))

    def create_vms(self, **kwargs):
        """
         创建实例
         request param kwargs:
            see https://docs.amazonaws.cn/AWSEC2/latest/APIReference/API_RunInstances.html

         BlockDeviceMapping.N  Type: Array of BlockDeviceMapping objects
            DeviceName  -The device name (for example, /dev/sdh or xvdh) Type: String.
            Ebs -used to automatically set up EBS volumes when the instance is launched.Type: EbsBlockDevice object
                DeleteOnTermination Type: Boolean
                Encrypted   Type: Boolean
                Iops    Type: Integer       required for some type volumes,read html
                KmsKeyId    Type: String
                OutpostArn  Type: String     only called by CreateImage.
                SnapshotId  Type: String
                Throughput  Type: Integer   Type: is valid only for gp3 volumes. range: 125-1000.
                VolumeSize  Type: Integer   volume type different,range different
                VolumeType  Type: String    String      standard | io1 | io2 | gp2 | sc1 | st1 | gp3
            NoDevice    Type: String
            VirtualName     Type: String
        CapacityReservationSpecification    Type: CapacityReservationSpecification object
            CapacityReservationPreference   Type: String    Valid Values: open | none  default:open
            CapacityReservationTarget   Type: CapacityReservationTarget object
                CapacityReservationId   Type: String
                CapacityReservationResourceGroupArn     Type: String
        ClientToken     Type: String
        CpuOptions      CpuOptionsRequest object
            CoreCount   Type: Integer
            ThreadsPerCore      Type: Integer
        CreditSpecification     Type: CreditSpecificationRequest object
            ->The credit option for CPU usage of a T2, T3, or T3a instance. Valid values are standard and unlimited.
            ->Default: standard (T2 instances) or unlimited (T3/T3a instances)
            ->For T3 instances with host tenancy, only standard is supported.
            CreditSpecificationRequest  Type: String    Required: Yes
        DisableApiStop     Type: Boolean
        DisableApiTermination   Type: Boolean   Default: false
        DryRun      Type: Boolean
        EbsOptimized    Type: Boolean   Default: false
        ElasticGpuSpecification.N   Type: Array of ElasticGpuSpecification objects
            Type    Type: String    Required: Yes
        ElasticInferenceAccelerator.N   Type: Array of ElasticInferenceAccelerator objects
            Count   Type: Integer   Default: 1  Valid Range: Minimum value of 1.
            Type    Required: Yes   valid:eia1.medium, eia1.large, eia1.xlarge, eia2.medium, eia2.large, and eia2.xlarge
        EnclaveOptions      Type: EnclaveOptionsRequest object
            Enabled     Type: Boolean  ->whether the instance is enabled for Amazon Nitro Enclaves.
        HibernationOptions  Type: HibernationOptionsRequest object
            Configured      Type: Boolean   Default: false
            ->can't enable hibernation and Amazon Nitro Enclaves on the same instance.
        IamInstanceProfile  Type: IamInstanceProfileSpecification object
            Arn     Type: String
            Name    Type: String
        ImageId    Type: String
        -> An AMI ID is required to launch an instance and must be specified here or in a launch template.
        InstanceInitiatedShutdownBehavior   Type: String    Default: stop   Valid Values: stop | terminate
        InstanceMarketOptions   Type: InstanceMarketOptionsRequest object
            MarketType      Type: String    Valid Values: spot
            SpotOptions     Type: SpotMarketOptions object
                InstanceInterruptionBehavior   Type: String   default:terminate     hibernate | stop | terminate
                MaxPrice    Type: String    default is the On-Demand price.
                SpotInstanceType    Type: String    Valid Values: one-time | persistent
                ->For RunInstances, persistent Spot Instance requests are only supported
                ->when the instance interruption behavior is either hibernate or stop.
                ValidUntil  Type: Timestamp     Supported only for persistent requests.
        InstanceType    Type: String    Default: m1.small
        Ipv6Address.N   Type: Array of InstanceIpv6Address objects
            Ipv6Address     Type:
        Ipv6AddressCount    Type: Integer
        KernelId    Type: String
        KeyName     Type: String
        LaunchTemplate      Type: LaunchTemplateSpecification object
            LaunchTemplateId    Type: String
            LaunchTemplateName  Type: String
            Version     Type: String
        LicenseSpecification.N      Type: Array of LicenseConfigurationRequest objects
            LicenseConfigurationArn     Type: String
        MaintenanceOptions      Type: InstanceMaintenanceOptionsRequest object
            AutoRecovery    Type: String
        MaxCount    Type: Integer   Required: Yes
        MetadataOptions     Type: InstanceMetadataOptionsRequest object
            HttpEndpoint    Type: String    Default: enabled    Valid Values: disabled | enabled
            HttpProtocolIpv6    Type: String    Valid Values: disabled | enabled
            HttpPutResponseHopLimit     Type: Integer   Default: 1  Possible values: Integers from 1 to 64
            HttpTokens      Type: String    Default: optional   Valid Values: optional | required
            InstanceMetadataTags    Type: String    Default: disabled   Valid Values: disabled | enabled
        MinCount    Type: Integer   Required: Yes
        Monitoring  Type: RunInstancesMonitoringEnabled object
            Enabled     Type: Boolean   Required: Yes
        NetworkInterface.N      Type: Array of InstanceNetworkInterfaceSpecification objects
            AssociateCarrierIpAddress   Type: Boolean
            AssociatePublicIpAddress    Type: Boolean
            DeleteOnTermination         Type: Boolean
            Description                 Type: String
            DeviceIndex                 Type: Integer
            InterfaceType               Type: String    Valid values: interface | efa
            Ipv4Prefixes                Type: Array of Ipv4PrefixSpecificationRequest objects
            ->You cannot use this option if you use the Ipv4PrefixCount option.
                Ipv4Prefix              Type: String
            Ipv4PrefixCount             Type: Integer
            Ipv6AddressCount            Type: Integer
            Ipv6Addresses               Type: Array of InstanceIpv6Address objects
                Ipv6Address             Type: String
            Ipv6Prefixes                Type: Array of Ipv6PrefixSpecificationRequest objects
            Ipv6PrefixCount             Type: Integer
            NetworkCardIndex            Type: Integer
            NetworkInterfaceId          Type: String
            PrivateIpAddress            Type: String
            -> cannot specify this option if you're launching more than one instance in a RunInstances request.
            PrivateIpAddresses          Type: Array of PrivateIpAddressSpecification objects
            -> cannot specify this option if you're launching more than one instance in a RunInstances request.
                Primary     Type: Boolean   -> Only one IPv4 address can be designated as primary.
                PrivateIpAddress    Type: String
            SecondaryPrivateIpAddressCount      Type: Integer
            ->cannot specify this option if you're launching more than one instance in a RunInstances request.
            Groups      Type: Array of strings
            SubnetId    Type: String
        Placement   Type: Placement object
            Affinity    Type: String
            AvailabilityZone    Type: String
            GroupName      Type: String
            HostId      Type: String
            HostResourceGroupArn    Type: String
            PartitionNumber     Type: Integer
            SpreadDomain        Type: String    Reserved for future use.
            Tenancy            Type: String     Valid Values: default | dedicated | host
        PrivateDnsNameOptions   Type: PrivateDnsNameOptionsRequest object
            EnableResourceNameDnsAAAARecord     Type: Boolean
            EnableResourceNameDnsARecord        Type: Boolean
            HostnameType                        Type: String    Valid Values: ip-name | resource-name
        PrivateIpAddress    Type: String
        ->cannot specify this option and the network interfaces option in the same request.
        RamdiskId       Type: String
        SecurityGroup.N     Type: Array of strings  Default: Amazon EC2 uses the default security group.
        SecurityGroupId.N   Type: Array of strings
        SubnetId            Type: String
        TagSpecification.N      Type: Array of TagSpecifictitation objects
            ResourceType    Type: String
            Tags            Type: Array of Tag objects
        UserData             Type: String
        """
        if "MaxCount" not in kwargs or not kwargs["MaxCount"]:
            return fail("need param MaxCount")
        if "MinCount" not in kwargs or not kwargs["MinCount"]:
            return fail("need param MinCount")
        if "ImageId" not in kwargs or not kwargs["ImageId"]:
            return fail("need param ImageId")
        service = "ec2"
        response_field = "instancesSet"
        params_list = self._set_create_vm_params(**kwargs)
        params_list["Version"] = self.version
        sorted_dict_asc = sorted(params_list.items(), key=lambda item: item[0])
        action = "RunInstances&{}".format(parse.urlencode(flat_dict(dict(sorted_dict_asc))))
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, response_field)
            return_msg = {}
            object_item = content.get("item", [])
            if type(object_item) is not list:
                object_item = [object_item]
            for instance_index, instance in enumerate(object_item):
                if instance["instanceId"]:
                    return_msg.update({instance_index: True})
                else:
                    return_msg.update({instance_index: False})
            success(return_msg)
        else:
            logger.error("RunInstances response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def _set_create_vm_params(self, **kwargs):
        params_dic = {
            "MaxCount": kwargs["MaxCount"],
            "MinCount": kwargs["MinCount"],
            "ImageId": kwargs["ImageId"],
        }
        # creat_vm optional params
        params_list = [
            "BlockDeviceMapping",
            "CapacityReservationSpecification",
            "ClientToken",
            "CpuOptions",
            "CreditSpecification",
            "DisableApiStop",
            "DisableApiTermination",
            "EbsOptimized",
            "ElasticGpuSpecification",
            "ElasticInferenceAccelerator",
            "EnclaveOptions",
            "HibernationOptions",
            "IamInstanceProfile",
            "InstanceInitiatedShutdownBehavior",
            "InstanceMarketOptions",
            "InstanceType",
            "Ipv6Address",
            "Ipv6AddressCount",
            "KernelId",
            "KeyName",
            "LaunchTemplate",
            "LicenseSpecification",
            "MaintenanceOptions",
            "MetadataOptions",
            "Monitoring",
            "NetworkInterface",
            "Placement",
            "PrivateDnsNameOptions",
            "PrivateIpAddress",
            "RamdiskId",
            "SecurityGroup",
            "SecurityGroupId",
            "SubnetId",
            "TagSpecification",
            "UserData",
        ]
        return set_optional_param(params_list, params_dic, **kwargs)

    def delete_vms(self, vms_id, **kwargs):
        request_field = "InstanceId"
        response_field = "instancesSet"
        service = "ec2"
        resource_id_list = {"Version": self.version, request_field: {}}
        for index, resource_id in enumerate(vms_id):
            resource_id_list[request_field].update({index + 1: resource_id})
        sorted_dict_asc = sorted(resource_id_list.items(), key=lambda item: item[0])
        action = "TerminateInstances&{}".format(parse.urlencode(flat_dict(dict(sorted_dict_asc))))
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, response_field)
            return_msg = {}
            object_item = content.get("item", [])
            if type(object_item) is not list:
                object_item = [object_item]
            for instance in object_item:
                if instance["currentState"]["name"] is AmazonAwsVMStatus.SHUTTING_DOWN or AmazonAwsVMStatus.TERMINATED:
                    return_msg.update({instance["instanceId"]: True})
                else:
                    logger.error("delete failed,vm id({})".format(instance["instanceId"]))
                    return_msg.update({instance["instanceId"]: False})
            return success(return_msg)
        else:
            logger.error("TerminateInstances response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def start_vms(self, vms_id, **kwargs):
        request_field = "InstanceId"
        response_field = "instancesSet"
        service = "ec2"
        resource_id_list = {"Version": self.version, request_field: {}}
        for index, resource_id in enumerate(vms_id):
            resource_id_list[request_field].update({index + 1: resource_id})
        sorted_dict_asc = sorted(resource_id_list.items(), key=lambda item: item[0])
        action = "StartInstances&{}".format(parse.urlencode(flat_dict(dict(sorted_dict_asc))))
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, response_field)
            return_msg = {}
            object_item = content.get("item", [])
            if type(object_item) is not list:
                object_item = [object_item]
            for instance in object_item:
                if instance["currentState"]["name"] is AmazonAwsVMStatus.PENDING or AmazonAwsVMStatus.RUNNING:
                    return_msg.update({instance["instanceId"]: True})
                else:
                    logger.error("start failed,vm id({})".format(instance["instanceId"]))
                    return_msg.update({instance["instanceId"]: False})
            return success(return_msg)
        else:
            logger.error("StartInstances response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def stop_vms(self, vms_id, force="false", hibernate="false", **kwargs):
        request_field = "InstanceId"
        response_field = "instancesSet"
        service = "ec2"
        if not vms_id:
            return fail("need param vms_id")
        resource_id_list = {"Force": force, "Hibernate": hibernate, "Version": self.version, request_field: {}}
        for index, resource_id in enumerate(vms_id):
            resource_id_list[request_field].update({index + 1: resource_id})
        sorted_dict_asc = sorted(resource_id_list.items(), key=lambda item: item[0])
        action = "StopInstances&{}".format(parse.urlencode(flat_dict(dict(sorted_dict_asc))))
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, response_field)
            return_msg = {}
            object_item = content.get("item", [])
            if type(object_item) is not list:
                object_item = [object_item]
            for instance in object_item:
                if instance["currentState"]["name"] is AmazonAwsVMStatus.STOPPED or AmazonAwsVMStatus.STOPPING:
                    return_msg.update({instance["instanceId"]: True})
                else:
                    logger.error("stop failed,vm id({})".format(instance["instanceId"]))
                    return_msg.update({instance["instanceId"]: False})
            return success(return_msg)
        else:
            logger.error("StopInstances response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    # ***********************Disk*****************************************
    def list_disks(self, disks_id=None, next_token=None, **kwargs):
        service = "ec2"
        request_field = "VolumeId"
        response_field = "volumeSet"
        resource_id_list = {"Version": self.version}
        action = "DescribeVolumes"
        resource_id_list.update(kwargs)
        if disks_id:
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(disks_id):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
            )
        )

    def create_disk(self, *args, **kwargs):
        """
         创建磁盘卷
            see https://docs.amazonaws.cn/AWSEC2/latest/APIReference/API_CreateVolume.html
        request param kwargs:

        AvailabilityZone    Type: String    Required: Yes
        ClientToken         Type: String
        DryRun              Type: Boolean
        Encrypted           Type: Boolean
        Iops                Type: Integer   This parameter is required for io1 and io2 volumes
        KmsKeyId            Type: String
        MultiAttachEnabled  Type: Boolean
        OutpostArn          Type: String
        Size                Type: Integer
        SnapshotId          Type: String
        TagSpecification.N  Type: Array of TagSpecification objects
            ResourceType    Type: String
            Tags            Type: Array of Tag objects
        Throughput          Type: Integer        is valid only for gp3 volumes. range:125-1000
        VolumeType          Type: String  Default: gp2  Valid Values: standard | io1 | io2 | gp2 | sc1 | st1 | gp3

        """
        if "AvailabilityZone" not in kwargs or not kwargs["AvailabilityZone"]:
            return fail("need param AvailabilityZone")
        if not (kwargs.get("Size") or kwargs.get("SnapShotId")):
            return fail("need either a snapshot ID or a volume Size")
        service = "ec2"
        params_list = self._set_create_disk_params(**kwargs)
        params_list["Version"] = self.version
        sorted_dict_asc = sorted(params_list.items(), key=lambda item: item[0])
        action = "CreateVolume&{}".format(parse.urlencode(flat_dict(dict(sorted_dict_asc))))
        parse_content = self.handle_action_request(service, action)
        if parse_content:
            content = find_key_from_dict(parse_content, "volumeId")
            return success(content) if content else fail()
        else:
            logger.error("CreateVolume response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def _set_create_disk_params(self, **kwargs):
        params_dic = {
            "AvailabilityZone": kwargs["AvailabilityZone"],
        }
        # creat_disk optional params
        params_list = [
            "ClientToken",
            "Encrypted",
            "Iops",
            "KmsKeyId",
            "SnapshotId",
            "Size",
            "MultiAttachEnabled",
            "OutpostArn",
            "TagSpecification",
            "Throughput",
            "VolumeType",
        ]
        return set_optional_param(params_list, params_dic, **kwargs)

    def delete_disk(self, disk_id, **kwargs):
        action = "DeleteVolume&Version={}&VolumeId={}".format(self.version, disk_id)
        service = "ec2"
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, "return")
            return success() if content == "true" else fail()
        else:
            logger.error("DeleteVolume response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def attach_disk(self, disk_id, **kwargs):
        disk_info = {
            "Device": kwargs["Device"],
            "InstanceId": kwargs["InstanceId"],
            "Version": self.version,
            "VolumeId": disk_id,
        }
        service = "ec2"
        action = "AttachVolume&{}".format(parse.urlencode(flat_dict(disk_info)))
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, "status")
            if content is AmazonAwsAttachStatus.ATTACHED or AmazonAwsAttachStatus.ATTACHING:
                return success()
            else:
                logger.error("attach disk failed")
                return fail()
        else:
            logger.error("AttachVolume response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def detach_disk(self, disk_id, **kwargs):
        disk_info = {
            "Device": kwargs["Device"],
            "Force": "false" if "Force" not in kwargs else kwargs["Force"],
            "InstanceId": kwargs["InstanceId"],
            "Version": self.version,
            "VolumeId": disk_id,
        }
        service = "ec2"
        action = "DetachVolume&{}".format(parse.urlencode(flat_dict(disk_info)))
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, "status")
            if content is AmazonAwsAttachStatus.DETACHED or AmazonAwsAttachStatus.DETACHING:
                return success()
            else:
                logger.error("detach disk failed")
                return fail()
        else:
            logger.error("DetachVolume response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    # ***********************Vpc*****************************************
    def list_vpcs(self, vpcs_id=None, next_token=None, **kwargs):
        service = "ec2"
        request_field = "VpcId"
        response_field = "vpcSet"
        resource_id_list = {"Version": self.version}
        action = "DescribeVpcs"
        resource_id_list.update(kwargs)
        if vpcs_id:
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(vpcs_id):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
            )
        )

    def create_vpc(self, *args, **kwargs):
        """
         创建vpc
            see https://docs.amazonaws.cn/AWSEC2/latest/APIReference/API_CreateVpc.html
        request param kwargs:

        AmazonProvidedIpv6CidrBlock     Type: Boolean
        CidrBlock   Type: String
        DryRun      Type: Boolean
        InstanceTenancy     Type: String    Default: default    Valid Values: default | dedicated | host
        Ipv4IpamPoolId      Type: String
        Ipv4NetmaskLength   Type: Integer
        Ipv6CidrBlock       Type: String    must also specify Ipv6Pool in the request.
        Ipv6CidrBlockNetworkBorderGroup     Type: String
        ->must set AmazonProvidedIpv6CidrBlock to true to use this parameter.
        Ipv6IpamPoolId      Type: String
        Ipv6NetmaskLength   Type: Integer
        Ipv6Pool            Type: String
        TagSpecification.N  Type: Array of TagSpecification objects
            ResourceType    Type: String
            Tags            Type: Array of Tag objects
        """
        if not (kwargs.get("CidrBlock") or kwargs.get("Ipv4IpamPoolId")):
            return fail("need either a CidrBlock or a Ipv4IpamPoolId ")
        service = "ec2"
        params_list = self._set_create_vpc_params(**kwargs)
        params_list["Version"] = self.version
        sorted_dict_asc = sorted(params_list.items(), key=lambda item: item[0])
        action = "CreateVpc&{}".format(parse.urlencode(flat_dict(dict(sorted_dict_asc))))
        parse_content = self.handle_action_request(service, action)
        if parse_content:
            content = find_key_from_dict(parse_content, "vpcId")
            return success(content) if content else fail()
        else:
            logger.error("CreateVpc response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def _set_create_vpc_params(self, **kwargs):
        params_dic = {}
        # creat_vpc optional params
        params_list = [
            "AmazonProvidedIpv6CidrBlock",
            "CidrBlock",
            "InstanceTenancy",
            "Ipv4IpamPoolId",
            "Ipv4NetmaskLength",
            "Ipv6CidrBlock",
            "Ipv6CidrBlockNetworkBorderGroup",
            "Ipv6IpamPoolId",
            "Ipv6NetmaskLength",
            "Ipv6Pool",
            "TagSpecification",
        ]
        return set_optional_param(params_list, params_dic, **kwargs)

    def delete_vpc(self, vpc_id, **kwargs):
        action = "DeleteVpc&Version={}&VpcId={}".format(self.version, vpc_id)
        service = "ec2"
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, "return")
            return success() if content == "true" else fail()
        else:
            logger.error("DeleteVpc response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    # ***********************Subnet****************************************
    def list_subnets(self, subnets_id=None, next_token=None, **kwargs):
        service = "ec2"
        request_field = "SubnetId"
        response_field = "subnetSet"
        resource_id_list = {"Version": self.version}
        action = "DescribeSubnets"
        resource_id_list.update(kwargs)
        if subnets_id:
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(subnets_id):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
            )
        )

    def create_subnet(self, *args, **kwargs):
        """
         创建subnet
            see https://docs.amazonaws.cn/AWSEC2/latest/APIReference/API_CreateSubnet.html
        request param kwargs:

        AvailabilityZone    Type: String
        AvailabilityZoneId  Type: String
        CidrBlock           Type: String         is not supported for an IPv6 only subnet.
        DryRun              Type: Boolean
        Ipv6CidrBlock       Type: String        is required for an IPv6 only subnet.
        Ipv6Native          Type: Boolean
        OutpostArn          Type: String
        TagSpecification.N  Type: Array of TagSpecification objects
        VpcId               Type: String    Required: Yes
        """
        if "VpcId" not in kwargs or not kwargs["VpcId"]:
            return fail("need VpcId")
        if not (kwargs.get("CidrBlock") or kwargs.get("ipv6CidrBlock")):
            return fail("need either a CidrBlock or a ipv6CidrBlock")
        service = "ec2"
        params_list = self._set_create_subnet_params(**kwargs)
        params_list["Version"] = self.version
        sorted_dict_asc = sorted(params_list.items(), key=lambda item: item[0])
        action = "CreateSubnet&{}".format(parse.urlencode(flat_dict(dict(sorted_dict_asc))))
        parse_content = self.handle_action_request(service, action)
        if parse_content:
            content = find_key_from_dict(parse_content, "subnetId")
            return success(content) if content else fail()
        else:
            logger.error("CreateSubnet response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def _set_create_subnet_params(self, **kwargs):
        params_dic = {"VpcId": kwargs["VpcId"]}
        # creat_subnet optional params
        params_list = [
            "AvailabilityZone",
            "AvailabilityZoneId",
            "CidrBlock",
            "Ipv6CidrBlock",
            "Ipv6Native",
            "OutpostArn",
            "TagSpecification",
        ]
        return set_optional_param(params_list, params_dic, **kwargs)

    def delete_subnet(self, subnet_id, **kwargs):

        action = "DeleteSubnet&SubnetId={}&Version={}".format(subnet_id, self.version)
        service = "ec2"
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, "return")
            return success() if content == "true" else fail()
        else:
            logger.error("DeleteSubnet response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    # ***********************Security_group****************************************
    def list_security_groups(self, security_groups_id=None, next_token=None, **kwargs):
        service = "ec2"
        request_field = "GroupId"
        response_field = "securityGroupInfo"
        action = "DescribeSecurityGroups"
        resource_id_list = {"Version": self.version}
        resource_id_list.update(kwargs)
        if security_groups_id:
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(security_groups_id):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
            )
        )

    def create_security_group(self, **kwargs):
        """
         创建安全组
            see https://docs.amazonaws.cn/AWSEC2/latest/APIReference/API_CreateSecurityGroup.html
        request param kwargs:

        DryRun  Type: Boolean
        GroupDescription    Type: String    Required: Yes
        GroupName       Type: String    Required: Yes
        TagSpecification.N  Type: Array of TagSpecification objects
        VpcId       Type: String    Required for EC2-VPC.
        """
        if "GroupName" not in kwargs or not kwargs["GroupName"]:
            return fail("need GroupName")
        if "GroupDescription" not in kwargs or not kwargs["GroupDescription"]:
            return fail("need GroupDescription")
        service = "ec2"
        params_list = self._set_create_security_group_params(**kwargs)
        params_list["Version"] = self.version
        sorted_dict_asc = sorted(params_list.items(), key=lambda item: item[0])
        action = "CreateSecurityGroup&{}".format(parse.urlencode(flat_dict(dict(sorted_dict_asc))))
        parse_content = self.handle_action_request(service, action)
        if parse_content:
            content = find_key_from_dict(parse_content, "groupId")
            return success(content) if content else fail()
        else:
            logger.error("CreateSecurityGroup response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def _set_create_security_group_params(self, **kwargs):
        params_dic = {
            "GroupName": kwargs["GroupName"],
            "GroupDescription": kwargs["GroupDescription"],
        }
        # creat_security_group optional params
        params_list = ["VpcId", "TagSpecification"]
        return set_optional_param(params_list, params_dic, **kwargs)

    def delete_security_group(self, security_group_id, **kwargs):
        action = "DeleteSecurityGroup&GroupId={}&Version={}".format(security_group_id, self.version)
        service = "ec2"
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, "return")
            return success() if content == "true" else fail()
        else:
            logger.error("DeleteSecurityGroup response Failure")

    def list_security_group_rules(self, security_group_id=None, next_token=None, **kwargs):
        service = "ec2"
        request_field = "SecurityGroupRuleId"
        response_field = "securityGroupRuleSet"
        action = "DescribeSecurityGroupRules"
        resource_id_list = {"Version": self.version}
        resource_id_list.update(kwargs)
        if isinstance(security_group_id, list):
            security_group_id = [security_group_id]
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(security_group_id):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
            )
        )

    # ***********************Snap_shots****************************************
    def list_snapshots(self, snapshots_id=None, next_token=None, **kwargs):
        """
        NextToken   Type: String
        Owner.N     Type: Array of strings
        RestorableBy.N      Type: Array of strings
        SnapshotId.N        Type: Array of strings
        """
        service = "ec2"
        request_field = "SnapshotId"
        response_field = "snapshotSet"
        action = "DescribeSnapshots"
        resource_id_list = {"Version": self.version, "Owner.1": "self"}
        resource_id_list.update(kwargs)
        if snapshots_id:
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(snapshots_id):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
            )
        )

    def create_snapshot(self, **kwargs):
        """
        Description     Type: String
        OutpostArn      Type: String
        TagSpecification.N      Type: Array of TagSpecification objects
        VolumeId       Type: String
        """
        if "VolumeId" not in kwargs or not kwargs["VolumeId"]:
            return fail("need VolumeId")
        service = "ec2"
        params_list = self._set_create_snapshot_params(**kwargs)
        params_list["Version"] = self.version
        sorted_dict_asc = sorted(params_list.items(), key=lambda item: item[0])
        action = "CreateSnapshot&{}".format(parse.urlencode(flat_dict(dict(sorted_dict_asc))))
        parse_content = self.handle_action_request(service, action)
        if parse_content:
            content = find_key_from_dict(parse_content, "snapshotId")
            return success(content) if content else fail()
        else:
            logger.error("CreateSnapshot response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def _set_create_snapshot_params(self, **kwargs):
        params_dic = {
            "VolumeId": kwargs["VolumeId"],
        }
        # create_snapshot optional params
        params_list = ["Description", "OutpostArn", "TagSpecification"]
        return set_optional_param(params_list, params_dic, **kwargs)

    def delete_snapshot(self, snapshot_id, **kwargs):
        action = "DeleteSnapshot&SnapshotId={}&Version={}".format(snapshot_id, self.version)
        service = "ec2"
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, "return")
            return success() if content == "true" else fail()
        else:
            logger.error("DeleteSnapshot response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    # ***********************Images****************************************

    def list_images(self, images_id=None, next_token=None, **kwargs):
        """
        NextToken   Type: String
        Owner.N     Type: Array of strings
        RestorableBy.N      Type: Array of strings
        SnapshotId.N        Type: Array of strings
        """
        service = "ec2"
        request_field = "ImageId"
        response_field = "imagesSet"
        action = "DescribeImages"
        resource_id_list = {"Version": self.version, "Owner.1": "self"}
        resource_id_list.update(kwargs)
        if images_id:
            resource_id_list[request_field] = {}
            for index, resource_id in enumerate(images_id):
                resource_id_list[request_field].update({index + 1: resource_id})
        return success(
            request_get_list(
                service,
                action,
                response_field,
                next_token,
                region_id=self.region_id,
                access_key=self.access_key,
                secret_key=self.secret_key,
                action_dict=resource_id_list,
            )
        )

    def delete_image(self, image_id, **kwargs):

        action = "DeregisterImage&ImageId={}&Version={}".format(image_id, self.version)
        service = "ec2"
        parse_content = self.handle_action_request(service, action)
        if parse_content["Status"]:
            content = find_key_from_dict(parse_content, "return")
            return success() if content == "true" else fail()
        else:
            logger.error("DeregisterImage response Failure")
            return fail(",".join(list(parse_content["Content"]["Error"].values())))

    def handle_action_request(self, service, action, inst_region=None):
        url = aws_signature(service, inst_region or self.region_id, self.access_key, self.secret_key, action)
        try:
            result = requests.get(url, verify=False)
        except Exception as e:
            logger.exception(e)
            return {"Status": False, "Content": str(e)}
        if result.status_code < 300:
            parse_content = xmltodict.parse(result.content)
            return {"Status": True, "Content": parse_content}
        else:
            logger.error("response code error")
            return {"Status": False, "Content": xmltodict.parse(result.content)["Response"]["Errors"]}


# ***********************Common****************************************
def set_optional_param(params_list, params_dic, **kwargs):
    for i in params_list:
        if i in kwargs:
            params_dic[i] = kwargs[i]
    return params_dic


def request_get_list(service, action, resource_type, next_token, item_field="item", _format=True, **kwargs):
    """
    list 请求格式方法
    """
    action_dict = kwargs["action_dict"]
    if next_token:
        action_dict["NextToken"] = next_token
    sorted_dict_asc = sorted(action_dict.items(), key=lambda item: item[0])
    url_action = "{}&{}".format(action, parse.urlencode(flat_dict(dict(sorted_dict_asc))))
    url = aws_signature(
        service=service,
        region=kwargs.get("region_id"),
        access_key=kwargs.get("access_key"),
        secret_key=kwargs.get("secret_key"),
        action=url_action,
    )
    try:
        result = requests.get(url, verify=False)
    except Exception as e:
        logger.exception(e)
        return fail("请求异常")
    data = []
    if result.status_code < 300:
        parse_content = xmltodict.parse(result.content)
        next_token = find_key_from_dict(parse_content, "nextToken")
        if next_token:
            data.extend(
                request_get_list(
                    service,
                    action,
                    resource_type,
                    next_token,
                    region_id=kwargs.get("region_id"),
                    access_key=kwargs.get("access_key"),
                    secret_key=kwargs.get("secret_key"),
                    action_dict=kwargs.get("action_dict"),
                    _format=_format,
                )
            )
        content = find_key_from_dict(parse_content, resource_type)
        if content is None:
            return data
        item_field = item_field.split(".")
        for i in item_field:
            content = content.get(i, {})
            if content is None:
                return []
        object_item = content
        if type(object_item) is not list:
            object_item = [object_item]
        for i in object_item:
            # 兼容vm有多层嵌套item,需要展平
            if action != "DescribeInstances" or not isinstance(i.get("instancesSet", {}).get("item", []), list):
                flat_items = [i]
            else:
                flat_items = []

                origin_item = i.get("instancesSet", {}).get("item", [])

                for k in origin_item:
                    copy_i = copy.deepcopy(i)
                    copy_i.update(instancesSet=OrderedDict(item=k))
                    flat_items.append(copy_i)

            for j in flat_items:
                if resource_type in resource_type_dict:
                    resource_type = resource_type_dict[resource_type]
                j.update(region_id=kwargs.get("region_id", ""))
                data.append(
                    get_format_method(CloudType.AMAZONAWS.value, resource_type, region_id=kwargs.get("region_id", ""))(
                        j, **kwargs
                    )
                    if _format
                    else j
                )

        return data
    else:
        logger.error(result.content)
        return fail("获取{}资源列表错误".format(resource_type))


resource_type_dict = {
    "vpcSet": CloudResourceType.VPC.value,
    "volumeSet": CloudResourceType.DISK.value,
    "subnetSet": CloudResourceType.SUBNET.value,
    "reservationSet": CloudResourceType.VM.value,
    "securityGroupInfo": CloudResourceType.SECURITY_GROUP.value,
    "securityGroupRuleSet": CloudResourceType.SECURITY_GROUP_RULE.value,
    "snapshotSet": CloudResourceType.SNAPSHOT.value,
    "imagesSet": CloudResourceType.IMAGE.value,
    "availabilityZoneInfo": CloudResourceType.ZONE.value,
    "regionInfo": CloudResourceType.REGION.value,
    "DescribeDbInstancesResult": CloudResourceType.RDS.value,
    "DescribeCacheClustersResult": CloudResourceType.CACHE_CLUSTER.value,
    "DescribeCertificatesResult": CloudResourceType.CERTIFICATE.value,
    "DescribeLoadBalancersResult": CloudResourceType.LOAD_BALANCER.value,
}


def find_key_from_dict(dictData, target):  # 查找多维字典中唯一的键的值
    queue = [dictData]
    while len(queue) > 0:
        data = queue.pop()
        for key, value in data.items():
            if key == target:
                return value
            elif type(value) == dict or type(value) == collections.OrderedDict:
                queue.append(value)
    return None


# 多维字典转get参数
# {'a': 1, 'b': 2, 'c': {'d': 1, 'e': 2, 'f': {'z': 0, 'g': 'pqw'}}}
# -> a=1&b=2&c.d=1&c.e=2&c.f.z=0&c.f.g=pqw
def flat_key(layer):
    if len(layer) == 1:
        return layer[0]
    else:
        _list = [".{}".format(k) for k in layer[1:]]
        return layer[0] + "".join(_list)


def flat_dict(_dict):
    if not isinstance(_dict, dict):
        raise TypeError("argument must be a dict, not {}".format(type(_dict)))
    if not _dict:
        return None

    def __flat_dict(pre_layer, value):
        result = {}
        for k, v in value.items():
            layer = pre_layer[:]
            layer.append(k)
            if isinstance(v, dict):
                result.update(__flat_dict(layer, v))
            else:
                result[flat_key(layer)] = v
        return result

    return __flat_dict([], _dict)


#  *********************************签名部分*******************************************


def aws_signature(service, region, access_key, secret_key, action):
    host = "{}.{}.amazonaws.com".format(service, region)
    endpoint = "https://{}".format(host)
    t = datetime.datetime.utcnow()  #
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")  # Format date as YYYYMMDD'T'HHMMSS'Z'
    datestamp = t.strftime("%Y%m%d")  # Date w/o time, used in credential scope
    canonical_uri = "/"
    canonical_headers = "host:" + host + "\n"
    signed_headers = "host"
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = datestamp + "/" + region + "/" + service + "/" + "aws4_request"

    canonical_querystring = "Action={}".format(action)
    canonical_querystring += "&X-Amz-Algorithm=AWS4-HMAC-SHA256"
    canonical_querystring += "&X-Amz-Credential=" + parse.quote_plus(access_key + "/" + credential_scope)
    canonical_querystring += "&X-Amz-Date=" + amz_date
    canonical_querystring += "&X-Amz-Expires=30"
    canonical_querystring += "&X-Amz-SignedHeaders=" + signed_headers

    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_request = (
        "GET"
        + "\n"
        + canonical_uri
        + "\n"
        + canonical_querystring
        + "\n"
        + canonical_headers
        + "\n"
        + signed_headers
        + "\n"
        + payload_hash
    )
    string_to_sign = (
        algorithm
        + "\n"
        + amz_date
        + "\n"
        + credential_scope
        + "\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )
    signing_key = get_signature_key(secret_key, datestamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    canonical_querystring += "&X-Amz-Signature=" + signature
    request_url = endpoint + "?" + canonical_querystring
    return request_url


def sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def get_signature_key(key, date_stamp, region_name, service_name):
    k_date = sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = sign(k_date, region_name)
    k_service = sign(k_region, service_name)
    k_signing = sign(k_service, "aws4_request")
    return k_signing

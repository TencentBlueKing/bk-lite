import logging
import boto3
from typing import List, Dict, Optional
from plugins.base_utils import convert_to_prometheus_format

logger = logging.getLogger(__name__)


class AWSManager:
    def __init__(self, params: dict):
        self.access_key_id = params.get("access_key_id")
        self.secret_access_key = params.get("secret_access_key")
        self.default_region = params.get('region', 'us-east-1')

    def get_session(self):
        session_args = {}
        if not all([self.access_key_id, self.secret_access_key]):
            raise ValueError(
                "Missing required AWS credentials: both aws_access_key_id and aws_secret_access_key must be provided")
        session_args['aws_access_key_id'] = self.access_key_id
        session_args['aws_secret_access_key'] = self.secret_access_key
        return boto3.Session(**session_args)


    def get_client(self, service: str, region_name: Optional[str] = None):
        session = self.get_session()
        region = region_name or self.default_region
        return session.client(service, region_name=region)

    def get_organization_info(self) -> Optional[Dict]:
        try:
            org_client = self.get_client('organizations', region_name='us-east-1')
            resp = org_client.describe_organization()
            org = resp.get('Organization', {})
            return {
                "org_id": org.get('Id'),
                "org_arn": org.get('Arn'),
                "org_master_account_id": org.get('MasterAccountId'),
                "org_master_account_email": org.get('MasterAccountEmail'),
            }
        except Exception as e:
            logger.warning(f"Could not get organization info: {e}")
            return None

    def get_available_regions(self, service_name: str = 'ec2'):
        try:
            ec2 = self.get_client('ec2', region_name=self.default_region)
            resp = ec2.describe_regions(AllRegions=False)
            regions = [r['RegionName'] for r in resp.get('Regions', []) if r.get('OptInStatus', 'opt-in-not-required') != 'not-opted-in']
            return regions
        except Exception as e:
            logger.error(f"get_available_regions error: {e}")
            return [self.default_region]

    # --- SAMPLE: EC2 ---
    def collect_ec2(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()
        for region in self.get_available_regions('ec2'):
            try:
                ec2 = self.get_client('ec2', region_name=region)
                paginator = ec2.get_paginator('describe_instances')
                for page in paginator.paginate():
                    for reservation in page.get('Reservations', []):
                        for inst in reservation.get('Instances', []):
                            inst_name = None
                            for tag in inst.get('Tags', []) or []:
                                if tag.get('Key') in ('Name','name'):
                                    inst_name = tag.get('Value')
                                    break
                            results.append({
                                "inst_name": inst_name,
                                "organization": org_info,
                                "resource_name": inst.get('InstanceId'),
                                "resource_id": inst.get('InstanceId'),
                                "ip_addr": inst.get('PrivateIpAddress'),
                                "public_ip": inst.get('PublicIpAddress'),
                                "region": region,
                                "zone": inst.get('Placement', {}).get('AvailabilityZone'),
                                "vpc": inst.get('VpcId'),
                                "status": inst.get('State', {}).get('Name'),
                                "instance_type": inst.get('InstanceType'),
                                "vcpus": (inst.get('CpuOptions', {}).get('CoreCount', 0) *
                                          inst.get('CpuOptions', {}).get('ThreadsPerCore', 1)) if inst.get('CpuOptions') else None,
                                "key_name": inst.get('KeyName'),
                            })
            except Exception as e:
                logger.exception(f"collect_ec2 error in region {region}: {e}")
        return results

    # --- RDS ---
    def collect_rds(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()

        for region in self.get_available_regions('rds'):
            try:
                client = self.get_client('rds', region_name=region)
                paginator = client.get_paginator('describe_db_instances')
                for page in paginator.paginate():
                    for inst in page.get('DBInstances', []):
                        endpoint = inst.get('Endpoint', {}) or {}
                        ca_id = inst.get('CACertificateIdentifier')
                        # 获取 CA certificate info
                        ca_start = None
                        ca_end = None
                        if ca_id:
                            try:
                                cert_resp = client.describe_certificates(CertificateIdentifier=ca_id)
                                certs = cert_resp.get('Certificates', [])
                                if certs:
                                    c = certs[0]
                                    ca_start = c.get('ValidFrom')
                                    ca_end = c.get('ValidTill')
                            except Exception as e:
                                logger.warning(f"Could not describe certificate {ca_id} in region {region}: {e}")

                        results.append({
                            "inst_name": inst.get('DBInstanceIdentifier'),
                            "organization": org_info,
                            "resource_name": inst.get('DBInstanceIdentifier'),
                            "resource_id": inst.get('DBInstanceArn'),
                            "region": region,
                            "zone": inst.get('AvailabilityZone'),
                            "vpc": inst.get('DBSubnetGroup', {}).get('VpcId'),
                            "status": inst.get('DBInstanceStatus'),
                            "instance_type": inst.get('DBInstanceClass'),
                            "engine": inst.get('Engine'),
                            "engine_version": inst.get('EngineVersion'),
                            "parameter_group": [pg.get('DBParameterGroupName') for pg in inst.get('DBParameterGroups', [])],
                            "endpoint": endpoint.get('Address'),
                            "maintenance_window": inst.get('PreferredMaintenanceWindow'),
                            "ca": ca_id,
                            "ca_start_date": ca_start,
                            "ca_end_date": ca_end,
                        })
            except Exception as e:
                logger.exception(f"collect_rds error in region {region}: {e}")
        return results

    # --- MSK ---
    def collect_msk(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()

        for region in self.get_available_regions('kafka'):
            try:
                client = self.get_client('kafka', region_name=region)
                paginator = client.get_paginator('list_clusters_v2')
                for page in paginator.paginate():
                    for cl in page.get('ClusterInfoList', []):
                        arn = cl.get('ClusterArn')
                        # 获取 describe
                        try:
                            desc = client.describe_cluster(ClusterArn=arn).get('ClusterInfo', {})
                        except Exception:
                            desc = cl
                        # node_disk: try getting from BrokerNodeGroupInfo.StorageInfo
                        node_disk = None
                        bgi = desc.get('BrokerNodeGroupInfo', {})
                        if bgi:
                            node_disk = bgi.get('StorageInfo', {}).get('EbsStorageInfo', {}).get('VolumeSize')
                        results.append({
                            "inst_name": desc.get('ClusterName'),
                            "organization": org_info,
                            "resource_name": desc.get('ClusterName'),
                            "resource_id": arn,
                            "region": region,
                            "node_type": bgi.get('InstanceType'),
                            "node_num": desc.get('NumberOfBrokerNodes'),
                            "node_disk": node_disk,
                            "status": desc.get('State'),
                            "cluster_version": desc.get('CurrentVersion'),
                        })
            except Exception as e:
                logger.exception(f"collect_msk error in region {region}: {e}")
        return results

    # --- ElastiCache ---
    def collect_elasticache(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()

        for region in self.get_available_regions('elasticache'):
            try:
                client = self.get_client('elasticache', region_name=region)
                paginator = client.get_paginator('describe_cache_clusters')
                for page in paginator.paginate(ShowCacheNodeInfo=True):
                    for c in page.get('CacheClusters', []):
                        results.append({
                            "inst_name": c.get('CacheClusterId'),
                            "organization": org_info,
                            "resource_name": c.get('CacheClusterId'),
                            "resource_id": c.get('CacheClusterArn', c.get('CacheClusterId')),
                            "region": region,
                            "status": c.get('CacheClusterStatus'),
                            "engine": c.get('Engine'),
                            "node_type": c.get('CacheNodeType'),
                            "node_num": len(c.get('CacheNodes', [])),
                            "backup_window": c.get('SnapshotRetentionLimit'),
                        })
            except Exception as e:
                logger.exception(f"collect_elasticache error in region {region}: {e}")
        return results

    # --- EKS ---
    def collect_eks(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()

        for region in self.get_available_regions('eks'):
            try:
                client = self.get_client('eks', region_name=region)
                paginator = client.get_paginator('list_clusters')
                for page in paginator.paginate():
                    for name in page.get('clusters', []):
                        desc = client.describe_cluster(name=name).get('cluster', {})
                        results.append({
                            "inst_name": desc.get('name'),
                            "organization": org_info,
                            "resource_name": desc.get('name'),
                            "resource_id": desc.get('arn'),
                            "region": region,
                            "status": desc.get('status'),
                            "k8s_version": desc.get('version'),
                        })
            except Exception as e:
                logger.exception(f"collect_eks error in region {region}: {e}")
        return results

    # --- CloudFront ---
    def collect_cloudfront(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()

        client = self.get_client('cloudfront', region_name='us-east-1')
        try:
            paginator = client.get_paginator('list_distributions')
            for page in paginator.paginate():
                for d in page.get('DistributionList', {}).get('Items', []):
                    results.append({
                        "inst_name": d.get('Id'),
                        "organization": org_info,
                        "resource_name": d.get('DomainName'),
                        "resource_id": d.get('Id'),
                        "status": d.get('Status'),
                        "domain": d.get('DomainName'),
                        "aliase_domain": ",".join(d.get('Aliases', {}).get('Items', [])) if d.get('Aliases') else None,
                        "modify_time": d.get('LastModifiedTime').isoformat() if d.get('LastModifiedTime') else None,
                        "price_class": d.get('PriceClass'),
                        "http_version": d.get('HttpVersion'),
                        "ssl_method": d.get('ViewerCertificate', {}).get('SSLSupportMethod'),
                    })
        except Exception as e:
            logger.exception(f"collect_cloudfront error: {e}")
        return results

    # --- ELBv2 ---
    def collect_elb(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()

        for region in self.get_available_regions('elbv2'):
            try:
                client = self.get_client('elbv2', region_name=region)
                paginator = client.get_paginator('describe_load_balancers')
                for page in paginator.paginate():
                    for lb in page.get('LoadBalancers', []):
                        results.append({
                            "inst_name": lb.get('LoadBalancerName'),
                            "organization": org_info,
                            "resource_name": lb.get('LoadBalancerName'),
                            "resource_id": lb.get('LoadBalancerArn'),
                            "region": region,
                            "zone": ",".join([az.get('ZoneName') for az in lb.get('AvailabilityZones', []) if az.get('ZoneName')]),
                            "vpc": lb.get('VpcId'),
                            "scheme": lb.get('Scheme'),
                            "status": lb.get('State', {}).get('Code'),
                            "type": lb.get('Type'),
                            "dns_name": lb.get('DNSName'),
                        })
            except Exception as e:
                logger.exception(f"collect_elb error in region {region}: {e}")
        return results

    # --- S3 Buckets ---
    def collect_s3(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()
        client = self.get_client('s3')
        try:
            resp = client.list_buckets()
            for b in resp.get('Buckets', []):
                bucket_name = b.get('Name')
                create_date = b.get('CreationDate')
                # region 获取位置，需要额外请求 get_bucket_location
                bucket_region = None
                try:
                    loc = client.get_bucket_location(Bucket=bucket_name)
                    bucket_region = loc.get('LocationConstraint')
                except Exception as e:
                    logger.warning(f"get_bucket_location for {bucket_name} failed: {e}")
                results.append({
                    "inst_name": bucket_name,
                    "organization": org_info,
                    "resource_name": bucket_name,
                    "resource_id": bucket_name,
                    "region": bucket_region,
                    "create_date": create_date.isoformat() if create_date else None,
                })
        except Exception as e:
            logger.exception(f"collect_s3 error: {e}")
        return results

    # --- DocumentDB ---
    def collect_docdb(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()
        for region in self.get_available_regions('docdb'):
            try:
                client = self.get_client('docdb', region_name=region)
                paginator = client.get_paginator('describe_db_instances')
                for page in paginator.paginate():
                    for inst in page.get('DBInstances', []):
                        results.append({
                            "inst_name": inst.get('DBInstanceIdentifier'),
                            "organization": org_info,
                            "resource_name": inst.get('DBInstanceIdentifier'),
                            "resource_id": inst.get('DBInstanceArn'),
                            "region": region,
                            "status": inst.get('DBInstanceStatus'),
                            "inst_num": 1,  # 如果有多个实例或子集群, 你可以调整
                            "port": inst.get('Endpoint', {}).get('Port'),
                            "engine": inst.get('Engine'),
                            "engine_version": inst.get('EngineVersion'),
                            "parameter_group": [pg.get('DBParameterGroupName') for pg in inst.get('DBParameterGroups', [])],
                            "maintenance_window": inst.get('PreferredMaintenanceWindow'),
                        })
            except Exception as e:
                logger.exception(f"collect_docdb error in region {region}: {e}")
        return results

    # --- MemoryDB ---
    def collect_memdb(self) -> List[Dict]:
        results = []
        org_info = self.get_organization_info()
        for region in self.get_available_regions('memorydb'):
            try:
                client = self.get_client('memorydb', region_name=region)
                paginator = client.get_paginator('describe_clusters')
                for page in paginator.paginate():
                    for cluster in page.get('Clusters', []):
                        endpoint = None
                        shards = cluster.get('Shards', []) or []
                        if shards:
                            nodes = shards[0].get('Nodes', []) or []
                            if nodes:
                                endpoint = nodes[0].get('Endpoint', {}).get('Address')
                        results.append({
                            "inst_name": cluster.get('Name'),
                            "organization": org_info,
                            "resource_name": cluster.get('Name'),
                            "resource_id": cluster.get('Arn'),
                            "region": region,
                            "node_type": cluster.get('NodeType'),
                            "shards_num": len(shards),
                            "node_num": sum(len(shard.get('Nodes', [])) for shard in shards),
                            "status": cluster.get('Status'),
                            "engine_version": cluster.get('EngineVersion'),
                            "parameter_group": cluster.get('ParameterGroupName'),
                            "endpoint": endpoint,
                            "maintenance_window": cluster.get('MaintenanceWindow'),
                        })
            except Exception as e:
                logger.exception(f"collect_memdb error in region {region}: {e}")
        return results

    # --- 全部聚合 ---
    def exec_script(self) -> Dict[str, List[Dict]]:
        return {
            "aws_ec2": self.collect_ec2(),
            "aws_rds": self.collect_rds(),
            "aws_msk": self.collect_msk(),
            "aws_elasticache": self.collect_elasticache(),
            "aws_eks": self.collect_eks(),
            "aws_cloudfront": self.collect_cloudfront(),
            "aws_elb": self.collect_elb(),
            "aws_s3_bucket": self.collect_s3(),
            "aws_docdb": self.collect_docdb(),
            "aws_memdb": self.collect_memdb(),
        }

    def list_all_resources(self) -> Dict[str, List[Dict]]:
        try:
            result = self.exec_script()
        except Exception:
            import traceback
            logger.error(f"{self.__class__.__name__} main error! {traceback.format_exc()}")
            result = {}
        return convert_to_prometheus_format(result)

    def test_connection(self) -> bool:
        try:
            sts = self.get_client('sts')
            resp = sts.get_caller_identity()
            logger.info(f"Caller identity: {resp}")
            return True
        except Exception as e:
            logger.error(f"test_connection error: {e}")
            return False


if __name__ == "__main__":
    import os
    params = {
        "access_key_id": os.getenv("access_key_id"),
        "secret_access_key": os.getenv("secret_access_key"),
        "region": os.getenv("region"),
    }

    manager = AWSManager(params)

    print("Test connection:", manager.test_connection())
    all_res = manager.exec_script()


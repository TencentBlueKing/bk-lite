# -*- coding: utf-8 -*-
from enum import Enum


class CloudType(Enum):
    UNKNOWNCLOUD = "unknownCloud"
    ALIYUN = "Aliyun"
    QClOUD = "QCloud"
    HUAWEICLOUD = "HuaweiCloud"
    OPENSTACK = "OpenStack"
    VMWARE = "VMware"
    FUSIONCOMPUTE = "FusionCompute"
    FUSIONCLOUD = "FusionCloud"
    MANAGEONE = "ManageOne"
    TCE = "TCE"
    TKE_CLOUD = "TKE"
    TDSQL = "TDSQL"
    APSARA = "Apsara"
    EASYSTACK = "EasyStack"
    CAS = "Cas"
    QINGCLOUD = "QingCloud"
    TSF = "TSF"
    AMAZONAWS = "AmazonAws"
    QINGCLOUDPRIVATE = "QingCloudPrivate"


CLOUD_TYPE_CHOICES = (
    (CloudType.UNKNOWNCLOUD.value, "未知云"),
    (CloudType.ALIYUN.value, "阿里云"),
    (CloudType.QClOUD.value, "腾讯云"),
    (CloudType.HUAWEICLOUD.value, "华为云"),
    (CloudType.OPENSTACK.value, "OpenStack"),
    (CloudType.VMWARE.value, "VMware"),
    (CloudType.FUSIONCOMPUTE.value, "FusionCompute"),
    (CloudType.FUSIONCLOUD.value, "FusionCloud"),
    # (CloudType.ManageOne.value, "ManageOne"),
    (CloudType.TCE.value, "TCE"),
    (CloudType.TKE_CLOUD.value, "TKE"),
    (CloudType.TDSQL.value, "TDSQL"),
    (CloudType.APSARA.value, "阿里云飞天"),
    (CloudType.EASYSTACK.value, "易捷行云"),
    (CloudType.CAS.value, "华三CAS"),
    (CloudType.QINGCLOUD.value, "青云"),
    (CloudType.TSF.value, "微服务平台"),
    (CloudType.AMAZONAWS.value, "亚马逊云"),
    (CloudType.QINGCLOUDPRIVATE.value, "青云私有云"),
)


class CloudResourceType(Enum):
    REGION = "region"
    ZONE = "zone"
    VM = "vm"
    SERVER = "server"
    DISK = "disk"
    STORAGE = "storage"
    IMAGE = "image"
    VPC = "vpc"
    SNAPSHOT = "snapshot"
    SUBNET = "subnet"
    SECURITY_GROUP = "security_group"
    HOST = "host"
    CLUSTER = "cluster"
    FLAVOR = "flavor"
    FLAVOR_FAMILY = "flavor_family"
    SECURITY_GROUP_RULE = "security_group_rule"
    EIP = "eip"
    BUCKET = "bucket"
    BucketFile = "bucket_file"
    PROJECT = "project"
    PRIVATE_STORAGE = "private_storage"
    DOMAIN = "domain"
    INSTANCE_TYPE = "instance_type"
    INSTANCE_TYPE_FAMILY = "instance_type_family"
    HYPERVISOR = "hypervisor"
    REDIS = "redis"
    TDSQL = "tdsql"
    MARIADB = "mariadb"
    FILE_SYSTEM = "file_system"
    PRIVATE_BUCKET = "private_bucket"
    LOAD_BALANCER = "load_balancer"
    TKE = "tke"
    TKE_INSTANCE = "tke_instance"
    TCR_IMAGE = "tag_image"
    MONGODB = "mongodb"
    # NOSHARD = "noshard" # 非分布式实例
    BMS = "bms"
    CKafka = "ckafka"
    SNAPSHOT_POLICY = "auto_snapshot_policy"
    ROUTE_TABLE = "route_tables"
    LISTENER = "listener"
    SERVER_CERTIFICATE = "server_certificates"
    RelayRule = "relay_rule"
    BACKEND_SECURITY_GROUP = "backend_server_group"
    APPLICATION = "application"
    RDS = "rds"
    CERTIFICATE = "certificate"
    CACHE_CLUSTER = "cache_cluster"


class VMStatusType(Enum):
    RUNNING = "RUNNING"  # 运行中
    STOP = "STOP"  # 已关机
    ERROR = "ERROR"  # 运行中
    BUILD = "BUILD"  # 创建中
    PENDING = "PENDING"  # 配置中


class VolumeStatus(Enum):
    CREATING = "创建中"
    IN_USE = "使用中"
    AVAILABLE = "未使用"
    ERROR = "错误"
    MODIFYING = "调整中"


class SnapshotStatus(Enum):
    AVAILABLE = "创建成功"
    CREATING = "创建中"
    ERROR = "创建失败"
    UNKNOWN = "未知状态"


class VPCStatus(Enum):
    ACTIVE = "可用"
    DOWN = "停止"
    BUILD = "创建中"
    ERROR = "故障"
    UNKNOWN = "未知"


class SubnetStatus(Enum):
    AVAILABLE = "可用"
    ERROR = "故障"
    PENDING = "Pending"  # 配置中
    UNKNOWN = "未知"


class ImageType(Enum):
    PUBLIC = "公共"
    PRIVATE = "私有"
    OTHERS = "其他"


class ImageStatus(Enum):
    CREATING = "创建中"
    AVAILABLE = "可用"
    UNAVAILABLE = "不可用"
    MODIFY = "调整中"
    FAILED = "创建失败"


class EipStatusType(Enum):
    BINDING = "绑定中"
    UNBINDING = "解绑中"
    AVAILABLE = "可用"
    INUSE = "已分配"
    UNKNOWN = "未知"


class EipChargeType(Enum):
    BANDWIDTH = "按带宽计费"
    TRAFFIC = "按流量计费"
    UNKNOWN = "未知"


class DiskCategory(Enum):
    CLOUD_BASIC = "普通云盘"
    CLOUD_EFFICIENCY = "高效云盘"
    CLOUD_SSD = "SSD盘"
    CLOUD_ESSD = "ESSD云盘"
    LOCAL_SSD_PRO = "I/O密集型本地盘"
    LOCAL_HDD_PRO = "吞吐密集型本地盘"
    EPHEMERAL = "本地盘"
    EPHEMERAL_SSD = "本地SSD盘"
    CLOUD_HSSD = "增强型SSD"
    CLOUD_PREMIUM = "高性能云硬盘"
    CLOUD_Q_SSD = "SSD云硬盘"
    SSD = "超高IO云硬盘"
    SAS = "高IO云硬盘"
    GPSSD = "通用型SSD云盘"
    SATA = "普通IO云硬盘"
    CLOUD_UNKNOWN = "未知类型"
    # fusioncompute
    SHARE = "共享"
    NORMAL = "普通"
    # vmware_vc
    THIN = "精简置备"
    EAGER = "厚置备快速置零"
    LAZY = "厚置备延迟置零"


class SnapShotType(Enum):
    PRIVATE_SNAPSHOT = "快照"
    SHARED_SNAPSHOT = "共享快照"


class PaidModal(Enum):
    PREPAID = "包年包月"
    POSTPAID = "按量付费"
    POSTPAID_BY_HOUR = "按小时付费"

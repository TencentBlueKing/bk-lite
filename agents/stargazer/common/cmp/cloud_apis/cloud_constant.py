# -*- coding: utf-8 -*-
from enum import Enum

from common.cmp.cloud_apis.constant import CloudType

from ..models import (  # HostMachine,
    TDSQL,
    TKE,
    VM,
    VPC,
    Application,
    Bucket,
    Cluster,
    Disk,
    Eip,
    FileSystem,
    HostMachine,
    Image,
    LoadBalancer,
    Mariadb,
    Mongodb,
    PrivateBucket,
    PrivateStorage,
    Redis,
    RegionInfo,
    SecurityGroup,
    SecurityGroupRule,
    Snapshot,
    Subnet,
    Tag,
    ZoneInfo,
)


# 资源和资源model映射
class ResourceModel:
    vm = VM
    disk = Disk
    snapshot = Snapshot
    image = Image
    vpc = VPC
    subnet = Subnet
    security_group = SecurityGroup
    eip = Eip
    private_storage = PrivateStorage
    host_machine = HostMachine
    cluster = Cluster
    bucket = Bucket
    redis = Redis
    tdsql = TDSQL
    mariadb = Mariadb
    file_system = FileSystem
    private_bucket = PrivateBucket
    load_balancer = LoadBalancer
    tke = TKE
    mongodb = Mongodb
    application = Application


class CloudPlatform:
    Aliyun = CloudType.ALIYUN.value
    Aliyun_cn = "阿里云"
    aliyun = "aliyun"

    Apsara = CloudType.APSARA.value
    Apsara_cn = "阿里云飞天"
    apsara = "apsara"

    QCloud = CloudType.QClOUD.value
    QCloud_cn = "腾讯云"
    qcloud = "qcloud"

    HuaweiCloud = CloudType.HUAWEICLOUD.value
    HuaweiCloud_cn = "华为云"
    huaweicloud = "huaweicloud"

    OpenStack = CloudType.OPENSTACK.value
    OpenStack_cn = "OpenStack"
    openstack = "openstack"

    VMware = CloudType.VMWARE.value
    VMware_cn = "VMware"
    vmware = "vmware_vc"

    FusionCompute = CloudType.FUSIONCOMPUTE.value
    FusionCompute_cn = "FusionCompute"
    fusioncompute = "fusioncompute"

    FusionCloud = CloudType.FUSIONCLOUD.value
    FusionCloud_cn = "FusionCloud"
    fusioncloud = "fusioncloud"

    TKE_CLOUD = CloudType.TKE_CLOUD.value
    TKE_CLOUD_cn = "TKE"
    tke_cloud = "tke"

    unknownCloud = CloudType.UNKNOWNCLOUD.value
    unknownCloud_cn = "未知云"
    unknowncloud = "unknowncloud"

    EasyStack = CloudType.EASYSTACK.value
    EasyStack_cn = "易捷行云"
    easystack = "easystack"

    Cas = CloudType.CAS.value
    Cas_cn = "华三CAS"
    cas = "cas"

    TCE = CloudType.TCE.value
    TCE_cn = "TCE"
    tce = "tce"

    TDSQL = CloudType.TDSQL.value
    TDSQL_cn = "TDSQL"
    tdsql = "tdsql"

    QingCloud = CloudType.QINGCLOUD.value
    QingCloud_cn = "青云"
    qingcloud = "qingcloud"

    TSF = CloudType.TSF.value
    TSF_cn = "微服务平台"
    tsf = "tsf"

    AmazonAws = CloudType.AMAZONAWS.value
    AmazonAws_cn = "亚马逊云"
    amazonaws = "amazonaws"

    QingCloudPrivate = CloudType.QINGCLOUDPRIVATE.value
    QingCloudPrivate_cn = "青云私有云"
    qingcloudprivate = "qingcloudprivate"

    ALL_CLOUD = [
        QCloud,
        Aliyun,
        HuaweiCloud,
        OpenStack,
        VMware,
        FusionCompute,
        FusionCloud,
        TCE,
        TDSQL,
        Apsara,
        EasyStack,
        Cas,
        TSF,
        QingCloud,
        AmazonAws,
        QingCloudPrivate,
    ]
    ALL_CLOUD_CN = [
        QCloud_cn,
        Aliyun_cn,
        HuaweiCloud_cn,
        OpenStack_cn,
        VMware_cn,
        FusionCompute_cn,
        FusionCloud_cn,
        TCE_cn,
        TDSQL_cn,
        Apsara_cn,
        EasyStack_cn,
        Cas_cn,
        TSF_cn,
        QingCloud_cn,
        AmazonAws_cn,
        QingCloudPrivate_cn,
    ]
    CLOUD = [QCloud, Aliyun, HuaweiCloud]
    CLOUDLOWER = [qcloud, aliyun, huaweicloud]
    CLOUD_cn = ["腾讯云", "华为云", "阿里云"]
    CLOUD_CLOUD_cn = {QCloud: "腾讯云", Aliyun: "阿里云", HuaweiCloud: "华为云"}
    # 私有云
    LOCAL = [
        OpenStack,
        VMware,
        FusionCompute,
        FusionCloud,
        TCE,
        TDSQL,
        Apsara,
        EasyStack,
        Cas,
        QingCloud,
        QingCloudPrivate,
    ]
    LOCAL_cn = [
        OpenStack_cn,
        VMware_cn,
        FusionCompute_cn,
        FusionCloud_cn,
        TCE_cn,
        TDSQL_cn,
        Apsara_cn,
        EasyStack_cn,
        Cas_cn,
        QingCloud_cn,
    ]
    LOCALLOWER = [
        openstack,
        vmware,
        fusioncompute,
        fusioncloud,
        tce,
        tdsql,
        apsara,
        easystack,
        cas,
        qingcloud,
        QingCloudPrivate,
    ]
    DATABASE = [TDSQL]
    DATABASE_cn = [TDSQL_cn]
    DATABASELOWER = [tdsql]

    REGION_CLOUD = {
        QCloud,
        Aliyun,
        HuaweiCloud,
        TCE,
        OpenStack,
        FusionCloud,
        FusionCompute,
        Apsara,
        QingCloud,
        AmazonAws,
        QingCloudPrivate,
    }

    EIP_CLOUD = [QCloud, Aliyun, HuaweiCloud, TCE, FusionCloud]

    SECURITY_GROUP_CLOUD = [
        QCloud,
        Aliyun,
        HuaweiCloud,
        TCE,
        OpenStack,
        FusionCloud,
        FusionCompute,
        QingCloud,
        QingCloudPrivate,
    ]

    # 有存储资源定价 即云硬盘价格
    STORAGE_PRICE_CLOUD = [QCloud, Aliyun, HuaweiCloud, TCE]


class BaseChargeType(Enum):
    """
    计费模式基础类
    """

    pass


class RegionStatus(Enum):
    AVAILABLE = RegionInfo.AVAILABLE
    UNAVAILABLE = RegionInfo.UNAVAILABLE


class ZoneStatus(Enum):
    AVAILABLE = ZoneInfo.AVAILABLE
    UNAVAILABLE = ZoneInfo.UNAVAILABLE


class VMStatus(Enum):
    """
    实例状态
    """

    RUNNING = VM.RUNNING
    STOP = VM.STOP
    ERROR = VM.ERROR
    BUILD = VM.BUILD
    PENDING = VM.PENDING


class VMRestrictState(Enum):
    """
    实例业务状态
    """

    IN_USE = VM.IN_USE
    EXPIRED = VM.EXPIRED
    PROTECTIVELY_ISOLATED = VM.PROTECTIVELY_ISOLATED


class VMChargeType(Enum):
    """
    实例计费模式
    """

    PREPAID = VM.PREPAID
    POSTPAID_BY_HOUR = VM.POSTPAID_BY_HOUR
    UNKNOWN = VM.UNKNOWN

    # 阿里云
    ALI_PREPAID = "PrePaid"  # 包年包月
    ALI_POSTPAID = "PostPaid"  # 按需付费

    ALI_PREPAID_CN = "包年包月"
    ALI_POSTPAID_CN = "按需付费"

    ALIYUN = [{"id": ALI_PREPAID, "name": ALI_PREPAID_CN}, {"id": ALI_POSTPAID, "name": ALI_POSTPAID_CN}]
    ALL = []

    # 腾讯云
    QC_PREPAID = "PREPAID"  # 包年包月
    QC_POSTPAID = "POSTPAID_BY_HOUR"  # 按需付费

    QC_PREPAID_CN = "包年包月"
    QC_POSTPAID_CN = "按需付费"
    QCLOUD = [{"id": QC_PREPAID, "name": QC_PREPAID_CN}, {"id": QC_POSTPAID, "name": QC_POSTPAID_CN}]

    # 华为云
    HW_PREPAID = "prePaid"  # 包年包月
    HW_POSTPAID = "postPaid"  # 按需付费

    HW_PREPAID_CN = "包年包月"
    HW_POSTPAID_CN = "按需付费"
    HUAWEICLOUD = [{"id": HW_PREPAID, "name": HW_PREPAID_CN}, {"id": HW_POSTPAID, "name": HW_POSTPAID_CN}]


class DiskStatus(Enum):
    UNATTACHED = Disk.UNATTACHED
    ATTACHED = Disk.ATTACHED
    ERROR = Disk.ERROR
    PENDING = Disk.PENDING


class DiskType(Enum):
    """
    磁盘类型（按用途分） 系统盘 数据盘
    """

    SYSTEM_DISK = Disk.SYSTEM_DISK
    DATA_DISK = Disk.DATA_DISK


class DiskCategory(Enum):
    """
    磁盘格式
    """

    CLOUD_BASIC = Disk.CLOUD_BASIC
    CLOUD_EFFICIENCY = Disk.CLOUD_EFFICIENCY
    CLOUD_SSD = Disk.CLOUD_SSD
    CLOUD_ESSD = Disk.CLOUD_ESSD
    CLOUD_UNKNOWN = Disk.CLOUD_UNKNOWN

    CLOUD_PREMIUM = "CLOUD_PREMIUM"  # 高性能云硬盘
    CLOUD_HSSD = "CLOUD_HSSD"  # 增强型SSD云硬盘
    CLOUD_TSSD = "CLOUD_TSSD"  # 极速SSD云硬盘

    LAZY = "LAZY"  # 厚置备延迟置零
    EAGER = "EAGER"  # 厚置备快速置零
    THIN = "THIN"  # 精简置备

    GPSSD = "GPSSD"
    SAS = "SAS"
    SSD = "SSD"

    NORMAL = "NORMAL"  # 普通
    SHARE = "SHARE"  # 共享

    CLOUD_PREMIUM_CN = "高性能云硬盘"
    CLOUD_HSSD_CN = "增强型SSD云硬盘"
    CLOUD_TSSD_CN = "极速SSD云硬盘"

    CLOUD_BASIC_CN = "普通云盘"
    CLOUD_EFFICIENCY_CN = "高效云盘"
    CLOUD_SSD_CN = "SSD云盘"
    CLOUD_ESSD_CN = "ESSD云盘"
    CLOUD_UNKNOWN_CN = "未知云盘"

    LAZY_CN = "厚置备延迟置零"
    EAGER_CN = "厚置备快速置零"
    THIN_CN = "精简置备"

    GPSSD_CN = "通用型SSD云盘"
    SAS_CN = "高IO云盘"
    SSD_CN = "超高IO云盘"

    NORMAL_CN = "普通"
    SHARE_CN = "共享"

    ALIYUN = [CLOUD_EFFICIENCY, CLOUD_SSD, CLOUD_ESSD]
    QCLOUD = [CLOUD_PREMIUM, CLOUD_SSD, CLOUD_HSSD]
    VMWARE = [LAZY, EAGER, THIN]
    HUAWEICLOUD = [GPSSD, SAS, SSD]
    FUSIONCOMPUTE = [NORMAL, SHARE]
    TCE = [CLOUD_BASIC, CLOUD_PREMIUM, CLOUD_SSD]
    ALL = []


class DiskChargeType(Enum):
    """
    磁盘付费模式
    """

    PREPAID = Disk.PREPAID
    POSTPAID_BY_HOUR = Disk.POSTPAID_BY_HOUR
    UNKNOWN = Disk.UNKNOWN


class SnapshotStatus(Enum):
    """
    快照状态
    """

    NORMAL = Snapshot.AVAILABLE
    CREATING = Snapshot.CREATING
    ROLLBACKING = Snapshot.ROLLBACKING
    ERROR = Snapshot.ERROR
    UNKNOWN = Snapshot.UNKNOWN


class ImageType(Enum):
    """
    镜像类型
    """

    PUBLIC = Image.PUBLIC
    PRIVATE = Image.PRIVATE
    OTHERS = Image.OTHERS
    MARKETPLACE = Image.MARKETPLACE


class OSType(Enum):
    """
    操作系统
    """

    WINDOWS = Image.WINDOWS
    LINUX = Image.LINUX
    UNKNOWN = Image.UNKNOWN


class ImageStatus(Enum):
    """
    镜像状态
    """

    UNAVAILABLE = Image.UNAVAILABLE
    AVAILABLE = Image.AVAILABLE
    CREATING = Image.CREATING
    ERROR = Image.ERROR


class VPCStatus(Enum):
    """
    VPC状态
    """

    PENDING = VPC.PENDING
    AVAILABLE = VPC.AVAILABLE
    ERROR = VPC.ERROR


class SubnetStatus(Enum):
    """
    子网状态
    """

    PENDING = Subnet.PENDING
    AVAILABLE = Subnet.AVAILABLE
    ERROR = Subnet.ERROR


class EipStatus(Enum):
    """
    EIP状态
    """

    CREATING = Eip.CREATING
    BINDING = Eip.BINDING
    BIND = Eip.BIND
    UNBINDING = Eip.UNBINDING
    UNBIND = Eip.UNBIND
    UNKNOWN = Eip.UNKNOWN


class EipChargeType(Enum):
    """
    弹性公网EIP计费模式
    """

    PREPAID = Eip.PREPAID
    POSTPAID_BY_HOUR = Eip.POSTPAID_BY_HOUR
    UNKNOWN_PAID = Eip.UNKNOWN_PAID


# class HostMachineStatus(Enum):
#     """
#     宿主机状态
#     """
#
#     AVAILABLE = HostMachine.AVAILABLE
#     PENDING = HostMachine.PENDING
#     ERROR = HostMachine.ERROR


class SecurityGroupRuleDirection(Enum):
    """
    安全组规则方向
    """

    INGRESS = SecurityGroupRule.INGRESS
    EGRESS = SecurityGroupRule.EGRESS
    ALL = SecurityGroupRule.ALL


class PrivateStorageStatus(Enum):
    """
    私有存储状态
    """

    AVAILABLE = PrivateStorage.AVAILABLE
    PENDING = PrivateStorage.PENDING
    ERROR = PrivateStorage.ERROR


class BucketType(Enum):
    """
    桶存储类型枚举
    """

    STANDARD = Bucket.STANDARD
    IA = Bucket.IA
    ARCHIVE = Bucket.ARCHIVE
    UNKNOWN = Bucket.UNKNOWN


class TagType(Enum):
    """
    标签类型
    """

    BUILD_IN = Tag.BUILD_IN
    SELF_DEFINE = Tag.SELF_DEFINE

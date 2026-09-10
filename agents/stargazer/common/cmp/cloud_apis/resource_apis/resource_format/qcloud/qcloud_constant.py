# -*- coding: utf-8 -*-
"""腾讯云属性枚举"""
from enum import Enum


class QCloudStatus(Enum):
    """适用于多种资源的状态 region zone"""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class QCloudChargeType(Enum):
    """适用于多种资源的付费类型 disk eip"""

    PREPAID = "PREPAID"  # 包年包月
    POSTPAID_BY_HOUR = "POSTPAID_BY_HOUR"  # 按量计费


class QCloudRegionStatus(Enum):
    pass


class QCloudZoneStatus(Enum):
    pass


class QCloudRestrictState(Enum):
    NORMAL = "NORMAL"
    EXPIRED = "EXPIRED"
    PROTECTIVELY_ISOLATED = "PROTECTIVELY_ISOLATED"


class QCloudVMStatus(Enum):
    PENDING = "PENDING"
    LAUNCH_FAILED = "LAUNCH_FAILED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    REBOOTING = "REBOOTING"
    SHUTDOWN = "SHUTDOWN"
    TERMINATING = "TERMINATING"


class QCloudVMChargeType(Enum):
    PREPAID = "PREPAID"  # 包年包月
    POSTPAID_BY_HOUR = "POSTPAID_BY_HOUR"  # 按量计费
    CDHPAID = "CDHPAID"  # CDH计费 只对CDH计费，不对CDH上的实例计费
    CDCPAID = "CDCPAID"  # 专用集群 CDC 上的实例，集群侧计费
    SPOTPAID = "SPOTPAID"  # 竞价实例付费


# ****************** 磁盘 disk
class QCloudDiskType(Enum):
    SYSTEM_DISK = "SYSTEM_DISK"
    DATA_DISK = "DATA_DISK"


class QCloudDiskCategory(Enum):
    CLOUD_BASIC = "CLOUD_BASIC"  # 普通云硬盘  腾讯云已停用
    CLOUD_PREMIUM = "CLOUD_PREMIUM"  # 高性能云硬盘
    CLOUD_SSD = "CLOUD_SSD"  # SSD云硬盘
    CLOUD_HSSD = "CLOUD_HSSD"  # 增强型SSD云硬盘
    CLOUD_TSSD = "CLOUD_TSSD"  # 极速SSD云硬盘


qcloud_disk_cn_dict = {
    "CLOUD_BASIC": "普通云硬盘",
    "CLOUD_PREMIUM": "高性能云硬盘",
    "CLOUD_SSD": "SSD云硬盘",
    "CLOUD_HSSD": "增强型SSD云硬盘",
    "CLOUD_TSSD": "极速型SSD云硬盘",
}


class QCloudDiskState(Enum):
    UNATTACHED = "UNATTACHED"  # 未挂载
    ATTACHING = "ATTACHING"  # 挂载中
    ATTACHED = "ATTACHED"  # 已挂载
    DETACHING = "DETACHING"  # 解挂中
    EXPANDING = "EXPANDING"  # 扩容中
    ROLLBACKING = "ROLLBACKING"  # 回滚中
    TORECYCLE = "TORECYCLE"  # 待回收
    DUMPING = "DUMPING"  # 拷贝硬盘中


class QCloudDiskChargeType(Enum):
    PREPAID = "PREPAID"
    POSTPAID_BY_HOUR = "POSTPAID_BY_HOUR"


# *********************************** 快照 snapshot
class QCloudSnapshotStatus(Enum):
    NORMAL = "NORMAL"  # 正常
    CREATING = "CREATING"  # 创建中
    ROLLBACKING = "ROLLBACKING"  # 回滚中
    COPYING_FROM_REMOTE = "COPYING_FROM_REMOTE"  # 跨地域复制快照拷贝中
    CHECKING_COPIED = "CHECKING_COPIED"  # 复制校验中
    TORECYCLE = "TORECYCLE"  # 待回收


# ********************************** 镜像 image
class QCloudImageStatus(Enum):
    CREATING = "CREATING"  # 创建中
    NORMAL = "NORMAL"  # 正常
    CREATEFAILED = "CREATEFAILED"  # 创建失败
    USING = "USING"  # 使用中
    SYNCING = "SYNCING"  # 同步中
    IMPORTING = "IMPORTING"  # 导入中
    IMPORTFAILED = "IMPORTFAILED"  # 导入失败


class QCloudImageType(Enum):
    PUBLIC_IMAGE = "PUBLIC_IMAGE"  # 公共镜像
    PRIVATE_IMAGE = "PRIVATE_IMAGE"  # 私有镜像
    SHARED_IMAGE = "SHARED_IMAGE"  # 共享镜像


# ********************************* 弹性公网 eip
class QCloudEipStatus(Enum):
    CREATING = "CREATING"  # 创建中
    BINDING = "BINDING"  # 绑定中
    BIND = "BIND"  # 已绑定
    UNBINDING = "UNBINDING"  # 解绑中
    UNBIND = "UNBIND"  # 已解绑
    OFFLINING = "OFFLINING"  # 释放中
    BIND_ENI = "BIND_ENI"  # 绑定悬空弹性网卡


class QCloudEIPProvider(Enum):
    """弹性公网IP的运营商 Model里未定义choice 暂时未用到"""

    CMCC = "CMCC"
    CTCC = "CTCC"
    CUCC = "CUCC"
    BGP = "BGP"


# ******************************** 安全组规则 security_group_rule
class QCloudSecurityGroupRuleDirection(Enum):
    Egress = "Egress"
    Ingress = "Ingress"


# *************************** 桶存储 bucket
class QCloudBucketType(Enum):
    STANDARD = "STANDARD"
    STANDARD_IA = "STANDARD_IA"
    ARCHIVE = "ARCHIVE"


qcloud_bucket_cn_dict = {
    "STANDARD": "标准存储",
    "STANDARD_IA": "低频存储",
    "ARCHIVE": "归档存储",
}

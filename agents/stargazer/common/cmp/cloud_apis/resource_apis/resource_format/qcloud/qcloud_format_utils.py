# -*- coding: utf-8 -*-
"""腾讯云源资源数据和本地数据枚举映射转换"""
from common.cmp.cloud_apis.cloud_constant import (
    BucketType,
    DiskCategory,
    DiskChargeType,
    DiskStatus,
    DiskType,
    EipStatus,
    ImageStatus,
    ImageType,
    RegionStatus,
    SecurityGroupRuleDirection,
    SnapshotStatus,
    SubnetStatus,
    VMChargeType,
    VMRestrictState,
    VMStatus,
    VPCStatus,
)
from common.cmp.cloud_apis.resource_apis.resource_format.qcloud.qcloud_constant import (
    QCloudBucketType,
    QCloudChargeType,
    QCloudDiskCategory,
    QCloudDiskChargeType,
    QCloudDiskState,
    QCloudDiskType,
    QCloudEipStatus,
    QCloudImageStatus,
    QCloudImageType,
    QCloudRestrictState,
    QCloudSecurityGroupRuleDirection,
    QCloudSnapshotStatus,
    QCloudStatus,
    QCloudVMChargeType,
    QCloudVMStatus,
)


def format_qcloud_status(status):
    """
    腾讯云区域、可用区状态值相同 公用方法
    Args:
        status ():

    Returns:

    """
    if status == QCloudStatus.AVAILABLE.value:
        return RegionStatus.AVAILABLE.value
    elif status == QCloudStatus.UNAVAILABLE.value:
        return RegionStatus.UNAVAILABLE.value
    else:
        # 返回状态不合法
        raise Exception("获取到未纳入本地的腾讯云状态{}，无法归类，请修改".format(status))


def format_qcloud_region_status(status):
    if status == QCloudStatus.AVAILABLE.value:
        return RegionStatus.AVAILABLE.value
    elif status == QCloudStatus.UNAVAILABLE.value:
        return RegionStatus.UNAVAILABLE.value
    else:
        # 返回状态不合法
        raise Exception("获取到未纳入本地的腾讯云区域状态{}，无法归类，请修改".format(status))


# ***************************** 虚拟机 vm
def format_qcloud_restrict_state(state):
    """
    转换虚拟机业务状态 qcloud
    Args:
        state ():

    Returns:

    """
    state_dict = {
        QCloudRestrictState.NORMAL.value: VMRestrictState.IN_USE.value,
        QCloudRestrictState.EXPIRED.value: VMRestrictState.EXPIRED.value,
        QCloudRestrictState.PROTECTIVELY_ISOLATED.value: VMRestrictState.PROTECTIVELY_ISOLATED.value,
    }
    if state not in state_dict:
        raise Exception("主机实例业务状态{}未纳入本地腾讯云，请检查".format(state))
    return state_dict[state]


def format_qcloud_vm_status(status):
    """
    转换虚拟机状态 qcloud
    Args:
        status ():

    Returns:

    """
    if status in [
        QCloudVMStatus.STOPPING.value,
        QCloudVMStatus.STARTING.value,
        QCloudVMStatus.REBOOTING.value,
        QCloudVMStatus.SHUTDOWN.value,
        QCloudVMStatus.TERMINATING.value,
    ]:
        return VMStatus.PENDING.value
    elif status == QCloudVMStatus.PENDING.value:
        return VMStatus.BUILD.value
    elif status == QCloudVMStatus.RUNNING.value:
        return VMStatus.RUNNING.value
    elif status == QCloudVMStatus.STOPPED.value:
        return VMStatus.STOP.value
    elif status == QCloudVMStatus.LAUNCH_FAILED.value:
        return VMStatus.ERROR
    else:
        raise Exception("主机实例状态{}未纳入本地腾讯云，请检查".format(status))


def format_qcloud_vm_charge_type(charge_type):
    if charge_type in [
        QCloudVMChargeType.PREPAID.value,
        QCloudVMChargeType.CDHPAID.value,
        QCloudVMChargeType.CDCPAID.value,
    ]:
        return VMChargeType.PREPAID.value
    elif charge_type in [QCloudVMChargeType.POSTPAID_BY_HOUR.value, QCloudVMChargeType.SPOTPAID.value]:
        return VMChargeType.POSTPAID_BY_HOUR.value
    else:
        raise Exception("主机实例付费模式{}未纳入本地腾讯云，请检查".format(charge_type))


def format_qcloud_tag(tags):
    if not tags:
        return []
    # return [{i.Key: i.Value} for i in tags]
    return [{getattr(i, "TagKey"): getattr(i, "TagValue")} for i in tags if hasattr(i, "TagKey") and hasattr(i, "TagValue")]


# ******************************* 磁盘 disk
def format_qcloud_disk_type(disk_type):
    if disk_type == QCloudDiskType.SYSTEM_DISK.value:
        return DiskType.SYSTEM_DISK.value
    elif disk_type == QCloudDiskType.DATA_DISK.value:
        return DiskType.DATA_DISK.value
    else:
        raise Exception("磁盘类型{}未纳入本地腾讯云，请检查".format(disk_type))


def format_qcloud_disk_charge_type(charge_type):
    if charge_type == QCloudDiskChargeType.PREPAID.value:
        return DiskChargeType.PREPAID.value
    elif charge_type == QCloudDiskChargeType.POSTPAID_BY_HOUR.value:
        return DiskChargeType.POSTPAID_BY_HOUR.value
    else:
        raise Exception("磁盘计费模式{}未纳入本地腾讯云，请检查".format(charge_type))


def format_qcloud_disk_category(category):
    if category == QCloudDiskCategory.CLOUD_BASIC.value:
        return DiskCategory.CLOUD_BASIC.value
    elif category == QCloudDiskCategory.CLOUD_PREMIUM.value:
        return DiskCategory.CLOUD_EFFICIENCY.value
    elif category in [
        QCloudDiskCategory.CLOUD_SSD.value,
        QCloudDiskCategory.CLOUD_HSSD.value,
        QCloudDiskCategory.CLOUD_TSSD.value,
    ]:
        return DiskCategory.CLOUD_SSD.value
    else:
        raise Exception("磁盘介质类型{}未纳入本地腾讯云，请检查".format(category))


def format_qcloud_disk_status(status):
    if status in [
        # QCloudDiskState.ATTACHED.value,
        QCloudDiskState.DETACHING.value,
        QCloudDiskState.EXPANDING.value,
        QCloudDiskState.ROLLBACKING.value,
        QCloudDiskState.TORECYCLE.value,
        QCloudDiskState.DUMPING.value,
    ]:
        return DiskStatus.PENDING.value
    elif status == QCloudDiskState.UNATTACHED.value:
        return DiskStatus.UNATTACHED.value
    elif status == QCloudDiskState.ATTACHED.value:
        return DiskStatus.ATTACHED.value
    else:
        return DiskStatus.ERROR.value


# ************************************ 快照 snapshot
def format_qcloud_snapshot_status(status):
    status_dict = {
        QCloudSnapshotStatus.COPYING_FROM_REMOTE.value: SnapshotStatus.UNKNOWN.value,
        QCloudSnapshotStatus.CHECKING_COPIED.value: SnapshotStatus.UNKNOWN.value,
        QCloudSnapshotStatus.TORECYCLE.value: SnapshotStatus.UNKNOWN.value,
        QCloudSnapshotStatus.NORMAL.value: SnapshotStatus.NORMAL.value,
        QCloudSnapshotStatus.ROLLBACKING.value: SnapshotStatus.ROLLBACKING.value,
        QCloudSnapshotStatus.CREATING.value: SnapshotStatus.CREATING.value,
    }
    return status_dict.get(status, SnapshotStatus.ERROR.value)


# ********************************** 镜像 image
def format_qcloud_image_status(status):
    status_dict = {
        QCloudImageStatus.CREATING.value: ImageStatus.CREATING.value,
        QCloudImageStatus.NORMAL.value: ImageStatus.AVAILABLE.value,
        QCloudImageStatus.CREATEFAILED.value: ImageStatus.ERROR.value,
        QCloudImageStatus.USING.value: ImageStatus.UNAVAILABLE.value,
        QCloudImageStatus.SYNCING.value: ImageStatus.UNAVAILABLE.value,
        QCloudImageStatus.IMPORTING.value: ImageStatus.UNAVAILABLE.value,
        QCloudImageStatus.IMPORTFAILED.value: ImageStatus.UNAVAILABLE.value,
    }
    if status not in status_dict:
        raise Exception("镜像状态{}未纳入本地腾讯云，请检查".format(status))
    return status_dict[status]


def format_qcloud_image_type(image_type):
    type_dict = {
        QCloudImageType.PUBLIC_IMAGE.value: ImageType.PUBLIC.value,
        QCloudImageType.PRIVATE_IMAGE.value: ImageType.PRIVATE.value,
        QCloudImageType.SHARED_IMAGE.value: ImageType.OTHERS.value,
    }
    if image_type not in type_dict:
        raise Exception("镜像类型{}未纳入本地腾讯云，请检查".format(image_type))
    return type_dict[image_type]


# 腾讯云子网和vpc都没有状态
# ********************************* vpc
def get_qcloud_vpc_status():
    return VPCStatus.AVAILABLE.value


# ********************************** 子网subnet
def get_qcloud_subnet_status():
    return SubnetStatus.AVAILABLE.value


# ********************************** 弹性公网 eip
def format_qcloud_eip_status(status):
    status_dict = {
        QCloudEipStatus.CREATING.value: EipStatus.CREATING.value,
        QCloudEipStatus.BINDING.value: EipStatus.BINDING.value,
        QCloudEipStatus.BIND.value: EipStatus.BIND.value,
        QCloudEipStatus.UNBINDING.value: EipStatus.UNBINDING.value,
        QCloudEipStatus.UNBIND.value: EipStatus.UNBIND.value,
        QCloudEipStatus.OFFLINING.value: EipStatus.UNKNOWN.value,
        QCloudEipStatus.BIND_ENI.value: EipStatus.UNKNOWN.value,
    }
    if status not in status_dict:
        raise Exception("弹性公网IP状态{}未纳入本地腾讯云，请检查".format(status))
    return status_dict[status]


def get_qcloud_eip_charge_type():
    return QCloudChargeType.POSTPAID_BY_HOUR.value


# ***************************** 安全组规则
def format_qcloud_security_group_rule_direction(direction):
    direction_dict = {
        QCloudSecurityGroupRuleDirection.Egress.value: SecurityGroupRuleDirection.EGRESS.value,
        QCloudSecurityGroupRuleDirection.Ingress.value: SecurityGroupRuleDirection.INGRESS.value,
    }
    return direction_dict.get(direction, SecurityGroupRuleDirection.ALL.value)


# ****************************** 桶存储 bucket
def format_bucket_type(bucket_type):
    bucket_type_dict = {
        QCloudBucketType.STANDARD.value: BucketType.STANDARD.value,
        QCloudBucketType.STANDARD_IA.value: BucketType.IA.value,
        QCloudBucketType.ARCHIVE.value: BucketType.ARCHIVE.value,
    }
    if bucket_type not in bucket_type_dict:
        raise Exception("获取到未纳入本地的腾讯云桶存储类型{}，无法处理".format(bucket_type))
    return bucket_type_dict[bucket_type]

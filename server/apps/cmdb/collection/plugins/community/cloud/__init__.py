"""Cloud collection plugins."""

from apps.cmdb.collection.plugins.community.cloud.aliyun import AliyunAccountCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.dell_unity import DellUnityCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.fusioninsight import FusionInsightCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.netapp_ontap import NetAppOntapCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.oceanstor import OceanStorCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.qcloud import QCloudCollectionPlugin

__all__ = [
    "AliyunAccountCollectionPlugin",
    "QCloudCollectionPlugin",
    "FusionInsightCollectionPlugin",
    "HwCloudCollectionPlugin",
    "DellUnityCollectionPlugin",
    "NetAppOntapCollectionPlugin",
    "OceanStorCollectionPlugin",
]

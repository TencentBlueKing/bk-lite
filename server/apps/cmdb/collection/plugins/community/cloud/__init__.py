"""Cloud collection plugins."""

from apps.cmdb.collection.plugins.community.cloud.aliyun import AliyunAccountCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.aws import AWSCloudCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.fusioninsight import FusionInsightCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.manageone import ManageOneCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.openstack import OpenStackCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.qcloud import QCloudCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.smartx import SmartXCollectionPlugin

__all__ = [
	"AliyunAccountCollectionPlugin",
	"QCloudCollectionPlugin",
	"AWSCloudCollectionPlugin",
	"FusionInsightCollectionPlugin",
	"HwCloudCollectionPlugin",
	"ManageOneCollectionPlugin",
	"OpenStackCollectionPlugin",
	"SmartXCollectionPlugin",
]
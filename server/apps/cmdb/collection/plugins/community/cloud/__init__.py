"""Cloud collection plugins."""

from apps.cmdb.collection.plugins.community.cloud.aliyun import AliyunAccountCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.aws import AWSCloudCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.manageone import ManageOneCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.qcloud import QCloudCollectionPlugin

__all__ = [
	"AliyunAccountCollectionPlugin",
	"QCloudCollectionPlugin",
	"AWSCloudCollectionPlugin",
	"HwCloudCollectionPlugin",
	"ManageOneCollectionPlugin",
]
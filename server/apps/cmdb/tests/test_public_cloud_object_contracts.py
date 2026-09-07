import pytest

from apps.cmdb.collection.plugins.community.cloud.aliyun import AliyunAccountCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin
from apps.cmdb.collection.plugins.community.cloud.qcloud import QCloudCollectionPlugin

pytestmark = pytest.mark.unit


def _metric_model_ids(plugin):
    suffix = "_info_gauge"
    aliases = getattr(plugin, "MODEL_ID_ALIASES", {})
    return {
        aliases.get(metric_name.removesuffix(suffix), metric_name.removesuffix(suffix))
        for metric_name in plugin.metric_names
        if metric_name.endswith(suffix)
    }


@pytest.mark.parametrize(
    "plugin",
    [
        AliyunAccountCollectionPlugin,
        QCloudCollectionPlugin,
        HwCloudCollectionPlugin,
    ],
)
def test_every_public_cloud_collected_object_has_a_field_mapping(plugin):
    assert set(plugin.field_mappings) == _metric_model_ids(plugin)

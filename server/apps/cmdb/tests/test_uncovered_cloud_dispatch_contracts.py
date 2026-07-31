"""补齐云采集任务到插件注册表的分派契约。"""

from types import SimpleNamespace

import pytest

from apps.cmdb.collection.collect_tasks import aliyun, aws, qcloud


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("module", "collector_class"),
    [
        (aliyun, aliyun.AliyunCollect),
        (aws, aws.AWSCollect),
        (qcloud, qcloud.QCloudCollect),
    ],
)
def test_cloud_collectors_resolve_plugin_from_task_type_and_model(
    monkeypatch, module, collector_class
):
    calls = []
    plugin = object()
    monkeypatch.setattr(
        module,
        "get_collection_plugin",
        lambda task_type, model_id: (
            calls.append((task_type, model_id)),
            plugin,
        )[1],
    )
    collector = collector_class.__new__(collector_class)
    collector.task = SimpleNamespace(task_type="cloud")
    collector.model_id = "host"

    assert collector.get_collect_plugin() is plugin
    assert calls == [("cloud", "host")]

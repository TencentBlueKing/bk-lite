"""适配器批量丰富测试：丰富从「每事件一次」改为「整批一次」。

对照 alert enrichment 引擎接入：create_events 应对整批仅调用 EnrichmentEngine.enrich_batch 一次，
并将 enrichment 落库到 Event。
"""

import pytest
from unittest.mock import patch


@pytest.fixture
def event_levels(db):
    from apps.alerts.constants.constants import LevelType
    from apps.alerts.models.models import Level

    for lid in (0, 1, 2, 3):
        Level.objects.create(
            level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.EVENT
        )


@pytest.fixture
def restful_source(db):
    from apps.alerts.models.alert_source import AlertSource

    return AlertSource.objects.create(
        name="restful源",
        source_id="restful",
        source_type="restful",
        secret="src-secret",
        team_secrets={},
        config={
            "event_fields_mapping": {
                "title": "title",
                "level": "level",
                "item": "item",
                "resource_id": "resource_id",
                "resource_name": "resource_name",
                "resource_type": "resource_type",
            }
        },
    )


@pytest.mark.django_db
@patch("apps.alerts.common.source_adapter.base.EnrichmentEngine")
def test_enrich_called_once_per_batch(mock_engine_cls, event_levels, restful_source):
    from apps.alerts.common.source_adapter.restful import RestFulAdapter
    from apps.alerts.models.models import Event

    def fake_enrich(event_dicts):
        for d in event_dicts:
            d["enrichment"] = {"cmdb": {"owner": "alice"}}

    mock_engine_cls.return_value.enrich_batch.side_effect = fake_enrich

    adapter = RestFulAdapter(alert_source=restful_source, secret="src-secret")
    add_events = [
        {"title": "a", "level": "0", "item": "cpu", "resource_type": "host", "resource_id": "1", "resource_name": "h1"},
        {"title": "b", "level": "0", "item": "cpu", "resource_type": "host", "resource_id": "2", "resource_name": "h2"},
    ]
    adapter.create_events(add_events)

    # 整批仅丰富一次，而非每事件一次
    assert mock_engine_cls.return_value.enrich_batch.call_count == 1
    # enrichment 落库到 Event
    assert Event.objects.get(title="a").enrichment == {"cmdb": {"owner": "alice"}}
    assert Event.objects.get(title="b").enrichment == {"cmdb": {"owner": "alice"}}

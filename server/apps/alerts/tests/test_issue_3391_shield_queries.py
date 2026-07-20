import pytest

from apps.alerts.common.source_adapter.base import AlertSourceAdapter
from apps.alerts.models.alert_operator import AlertShield


@pytest.mark.django_db
def test_get_active_shields_uses_single_query(django_assert_num_queries):
    AlertShield.objects.create(
        name="active-shield",
        match_type="all",
        match_rules=[],
        suppression_time={},
    )

    with django_assert_num_queries(1):
        shields = AlertSourceAdapter.get_active_shields()

    assert shields is not None
    assert shields.count() == 1

"""分享查询与筛选快照里仍直接返回给用户的错误文案。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from django.utils import translation

from apps.operation_analysis.services.filter_snapshot import FilterSnapshotError
from apps.operation_analysis.services.filter_snapshot_resolver import resolve_date_range
from apps.operation_analysis.services.share_service import ShareQueryParamsDenied, filter_share_query_params

pytestmark = pytest.mark.unit


def _dashboard():
    return SimpleNamespace(
        view_sets=[
            {
                "valueConfig": {
                    "dataSource": 7,
                    "dataSourceParams": [{"name": "region", "filterType": "fixed", "value": "cn"}],
                }
            },
            {
                "valueConfig": {
                    "dataSource": 7,
                    "dataSourceParams": [{"name": "region", "filterType": "fixed", "value": "us"}],
                }
            },
        ]
    )


def test_share_query_rejects_undeclared_and_fixed_params(monkeypatch):
    from apps.operation_analysis.services import share_service

    monkeypatch.setattr(share_service, "_datasource_param_specs", lambda data_source_id: [])
    dashboard = _dashboard()

    with translation.override("zh-hans"):
        with pytest.raises(ShareQueryParamsDenied, match=r"存在未声明参数: extra"):
            filter_share_query_params(dashboard=dashboard, data_source_id=7, request_data={"extra": 1})
        with pytest.raises(ShareQueryParamsDenied, match=r"参数 region 为固定值，不允许修改"):
            filter_share_query_params(dashboard=dashboard, data_source_id=7, request_data={"region": "eu"})

    with translation.override("en"):
        with pytest.raises(ShareQueryParamsDenied, match=r"Undeclared parameters: extra"):
            filter_share_query_params(dashboard=dashboard, data_source_id=7, request_data={"extra": 1})
        with pytest.raises(ShareQueryParamsDenied, match=r"Parameter region is fixed and cannot be changed"):
            filter_share_query_params(dashboard=dashboard, data_source_id=7, request_data={"region": "eu"})


def test_filter_snapshot_timezone_and_unknown_range():
    reference = datetime(2026, 1, 2, tzinfo=timezone.utc)

    with translation.override("zh-hans"):
        with pytest.raises(FilterSnapshotError, match=r"无效时区: Not/AZone"):
            resolve_date_range("today", reference_at=reference, timezone_name="Not/AZone")
        with pytest.raises(FilterSnapshotError, match=r"未知动态 dateRange 类型: custom"):
            resolve_date_range("custom", reference_at=reference, timezone_name="UTC")

    with translation.override("en"):
        with pytest.raises(FilterSnapshotError, match=r"Invalid timezone: Not/AZone"):
            resolve_date_range("today", reference_at=reference, timezone_name="Not/AZone")
        with pytest.raises(FilterSnapshotError, match=r"Unknown dynamic dateRange type: custom"):
            resolve_date_range("custom", reference_at=reference, timezone_name="UTC")

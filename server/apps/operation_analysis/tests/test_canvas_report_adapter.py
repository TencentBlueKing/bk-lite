"""Phase 1：CanvasReportAdapter 缝 — Dashboard 行为等价，无 schema 变更。"""

import pytest

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.services.canvas_report.registry import (
    UnknownCanvasReportType,
    get_canvas_report_adapter,
)
from apps.operation_analysis.services.canvas_report.types import (
    RESOURCE_TYPE_DASHBOARD,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def dashboard(authenticated_user):
    directory = Directory.objects.create(name="Adapter 测试目录", groups=[1])
    return Dashboard.objects.create(
        name="Adapter 测试仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
        view_sets=[
            {
                "id": "chart-1",
                "itemType": "widget",
                "valueConfig": {"chartType": "line", "dataSource": 17},
            },
            {
                "id": "group-1",
                "itemType": "group",
                "subGridOpts": {
                    "children": [
                        {
                            "id": "chart-2",
                            "itemType": "widget",
                            "valueConfig": {
                                "chartType": "table",
                                "dataSource": 18,
                            },
                        }
                    ]
                },
            },
        ],
        filters=[{"id": "environment"}],
        other={"title": "冻结标题"},
    )


def test_dashboard_adapter_is_registered():
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_DASHBOARD)
    assert adapter.resource_type == RESOURCE_TYPE_DASHBOARD


def test_unknown_resource_type_is_rejected():
    with pytest.raises(UnknownCanvasReportType):
        get_canvas_report_adapter("topology")


def test_dashboard_adapter_builds_manifest_from_layout(dashboard):
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_DASHBOARD)
    resource = adapter.load_resource(dashboard.id)
    assert adapter.build_manifest(resource) == [
        {
            "widget_id": "chart-1",
            "widget_type": "line",
            "datasource_id": 17,
        },
        {
            "widget_id": "chart-2",
            "widget_type": "table",
            "datasource_id": 18,
        },
    ]


def test_dashboard_adapter_render_snapshot_fields(dashboard):
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_DASHBOARD)
    resource = adapter.load_resource(dashboard.id)
    fields = adapter.build_render_snapshot_fields(resource)
    assert fields["dashboard_id"] == dashboard.id
    assert fields["dashboard_name"] == dashboard.name
    assert fields["filters"] == [{"id": "environment"}]
    assert fields["other"] == {"title": "冻结标题"}
    assert fields["widget_manifest"][0]["datasource_id"] == 17
    assert fields["view_sets"] is not dashboard.view_sets


def test_dashboard_adapter_render_route_key():
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_DASHBOARD)
    assert adapter.render_route_key() == "dashboard"


def test_can_view_canvas_superuser_bypasses_instance_check(
    dashboard, authenticated_user, monkeypatch
):
    from apps.operation_analysis.services.canvas_report.permissions import (
        can_view_canvas,
    )

    authenticated_user.is_superuser = True
    called = {"value": False}

    def _forbid(*args, **kwargs):
        called["value"] = True
        return False

    monkeypatch.setattr(
        "apps.operation_analysis.views.view.DashboardModelViewSet.get_has_permission",
        _forbid,
    )
    assert can_view_canvas(
        authenticated_user,
        RESOURCE_TYPE_DASHBOARD,
        dashboard.id,
        team_id=1,
    )
    assert called["value"] is False


def test_can_view_canvas_requires_team_context(dashboard, authenticated_user):
    from apps.operation_analysis.services.canvas_report.permissions import (
        can_view_canvas,
    )

    assert not can_view_canvas(
        authenticated_user,
        RESOURCE_TYPE_DASHBOARD,
        dashboard.id,
        team_id=None,
    )

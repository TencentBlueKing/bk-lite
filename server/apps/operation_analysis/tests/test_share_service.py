import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.core.utils.permission_cache import clear_user_permission_cache
from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.share_models import DashboardShareLink, DashboardShareSession
from apps.operation_analysis.services.share_service import (
    ShareLinkInvalid,
    SharePermissionDenied,
    create_or_get_share,
    exchange_share,
    resolve_link,
    resolve_session,
)
from apps.system_mgmt.models.user import User


@pytest.fixture
def sharer(db):
    return User.objects.create(
        username="alice",
        domain="domain.com",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[{"id": 1}],
    )


@pytest.fixture
def visitor(db):
    return User.objects.create(
        username="bob",
        domain="other.com",
        display_name="Bob",
        email="bob@example.com",
        password="x",
        group_list=[{"id": 99}],
    )


@pytest.fixture
def dashboard(db):
    directory = Directory.objects.create(name=f"share-dir-{uuid.uuid4()}", groups=[1], created_by="alice")
    return Dashboard.objects.create(
        name=f"share-dashboard-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets=[],
    )


@pytest.mark.django_db
def test_create_or_get_share_is_idempotent(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    first = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    second = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    assert second.link.pk == first.link.pk
    assert second.token == first.token
    assert (
        DashboardShareLink.objects.filter(
            dashboard_instance_id=dashboard.pk,
            sharer_username=sharer.username,
            sharer_domain=sharer.domain,
            status=DashboardShareLink.Status.ACTIVE,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_exchange_reuses_unexpired_session_and_resets_eight_hours(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    settings.DASHBOARD_SHARE_SESSION_AGE = 28800
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    first = exchange_share(token=result.token, visitor=visitor)
    exchange_time = first.expires_at - timedelta(hours=1)

    with mock.patch(
        "apps.operation_analysis.services.share_service.timezone.now",
        return_value=exchange_time,
    ):
        second = exchange_share(token=result.token, visitor=visitor)

    assert second.session_id == first.session_id
    assert second.expires_at == exchange_time + timedelta(hours=8)


@pytest.mark.django_db
def test_exchange_replaces_expired_session(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    settings.DASHBOARD_SHARE_SESSION_AGE = 28800
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    first = exchange_share(token=result.token, visitor=visitor)
    DashboardShareSession.objects.filter(pk=first.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    second = exchange_share(token=result.token, visitor=visitor)
    assert second.session_id != first.session_id
    assert not DashboardShareSession.objects.filter(pk=first.pk).exists()


@pytest.mark.django_db
def test_resolve_session_does_not_extend_expiry(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)
    original_expiry = session.expires_at

    resolve_session(session_id=session.session_id, visitor=visitor)

    session.refresh_from_db()
    assert session.expires_at == original_expiry


@pytest.mark.django_db
def test_share_sessions_cannot_be_used_across_visitors(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    visitor_c = User.objects.create(
        username="carol",
        domain="third.com",
        display_name="Carol",
        email="carol@example.com",
        password="x",
    )
    session_b = exchange_share(token=result.token, visitor=visitor)
    session_c = exchange_share(token=result.token, visitor=visitor_c)

    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session_b.session_id, visitor=visitor_c)
    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session_c.session_id, visitor=visitor)


@pytest.mark.django_db
def test_permission_loss_becomes_permanent_only_when_observed(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: False,
    )
    with pytest.raises(ShareLinkInvalid):
        resolve_link(result.link)

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.SHARER_PERMISSION_LOST
    with pytest.raises(ShareLinkInvalid):
        resolve_link(result.link)


@pytest.mark.django_db
def test_share_session_is_bound_to_visitor(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)
    other = User.objects.create(
        username="mallory",
        domain="third.com",
        display_name="Mallory",
        email="mallory@example.com",
        password="x",
    )

    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session.session_id, visitor=other)


@pytest.mark.django_db
def test_dashboard_delete_permanently_invalidates_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    dashboard.delete()

    result.link.refresh_from_db()
    assert result.link.dashboard is None
    assert result.link.status == DashboardShareLink.Status.DASHBOARD_INVALID


@pytest.mark.django_db
def test_dashboard_move_permanently_invalidates_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    dashboard.groups = [2]
    dashboard.save(update_fields=["groups"])

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.DASHBOARD_INVALID


@pytest.mark.django_db
def test_same_space_directory_move_does_not_invalidate_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    other_directory = Directory.objects.create(
        name=f"share-dir-moved-{uuid.uuid4()}",
        groups=[1],
        created_by="alice",
    )

    dashboard.directory = other_directory
    dashboard.save(update_fields=["directory"])

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.ACTIVE


@pytest.mark.django_db
def test_routine_permission_cache_clear_does_not_invalidate_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    clear_user_permission_cache(sharer.username, sharer.domain)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.ACTIVE


@pytest.mark.django_db
def test_actual_permission_loss_permanently_invalidates_link_and_session(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        space_id=1,
        tenant_domain=dashboard.domain,
    )
    session = exchange_share(token=result.token, visitor=visitor)

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: False,
    )

    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session.session_id, visitor=visitor)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.SHARER_PERMISSION_LOST


@pytest.mark.django_db
def test_new_share_after_permanent_invalidation_uses_new_token(
    settings, dashboard, sharer, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    first = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    first.link.mark_invalid(DashboardShareLink.Status.SHARER_PERMISSION_LOST, actor="system")

    second = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    assert second.link.pk != first.link.pk
    assert second.token != first.token
    with pytest.raises(ShareLinkInvalid):
        resolve_link(first.link)


@pytest.mark.django_db
def test_disabled_visitor_cannot_exchange_or_resolve_session(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)

    visitor.disabled = True
    visitor.save(update_fields=["disabled"])

    with pytest.raises(ShareLinkInvalid):
        exchange_share(token=result.token, visitor=visitor)
    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session.session_id, visitor=visitor)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.ACTIVE


@pytest.mark.django_db
def test_space_mismatch_marks_dashboard_invalid_not_permission_lost(
    settings, dashboard, sharer, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    # 绕过 pre_save signal，模拟归属已被改但链接仍为 active
    Dashboard.objects.filter(pk=dashboard.pk).update(groups=[2])
    dashboard.refresh_from_db()

    with pytest.raises(ShareLinkInvalid):
        resolve_link(result.link)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.DASHBOARD_INVALID


@pytest.mark.django_db
def test_non_member_cannot_create_share(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    sharer.group_list = [{"id": 99}]
    sharer.save(update_fields=["group_list"])
    with pytest.raises(SharePermissionDenied):
        create_or_get_share(
            dashboard=dashboard,
            sharer=sharer,
            tenant_domain=dashboard.domain,
            space_id=1,
        )


@pytest.mark.django_db
def test_share_query_rejects_undeclared_params(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    dashboard.view_sets = [
        {
            "valueConfig": {
                "dataSource": 1,
                "dataSourceParams": [{"name": "region", "filterType": "filter"}],
            }
        }
    ]
    dashboard.save(update_fields=["view_sets"])
    from apps.operation_analysis.services.share_service import (
        ShareQueryParamsDenied,
        filter_share_query_params,
    )

    with pytest.raises(ShareQueryParamsDenied):
        filter_share_query_params(
            dashboard=dashboard,
            data_source_id=1,
            request_data={"region": "east", "query_list": [{"k": "v"}]},
        )

    filtered = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=1,
        request_data={"region": "east", "page": 1},
    )
    assert filtered == {"region": "east", "page": 1}


@pytest.mark.django_db
def test_share_query_allows_runtime_group_by_from_value_config_params(settings, dashboard):
    """topN 等运行时切换键在 valueConfig.params；filterType=params 时允许访问者提交切换值。"""
    from apps.operation_analysis.services.share_service import filter_share_query_params

    dashboard.view_sets = [
        {
            "valueConfig": {
                "dataSource": 33,
                "dataSourceParams": [
                    {"name": "group_by", "filterType": "params", "value": "instance_type"},
                    {"name": "region", "filterType": "filter"},
                ],
                "params": {"group_by": "department"},
            }
        }
    ]
    dashboard.save(update_fields=["view_sets"])

    filtered = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=33,
        request_data={"group_by": "department", "region": "east"},
    )
    assert filtered == {"group_by": "department", "region": "east"}


@pytest.mark.django_db
def test_share_query_case1_widget_fixed_params_accepted(settings, dashboard):
    """case1: widget fixed 参数可进入最终请求，且保持配置值。"""
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.operation_analysis.services.share_service import filter_share_query_params

    datasource = DataSourceAPIModel.objects.create(
        name=f"share-fixed-ok-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        params=[
            {"name": "region", "filterType": "params", "value": "west"},
            {"name": "group_by", "filterType": "params", "value": "day"},
        ],
        created_by="alice",
        updated_by="alice",
    )
    dashboard.view_sets = [
        {
            "valueConfig": {
                "dataSource": datasource.id,
                "dataSourceParams": [
                    {"name": "region", "filterType": "fixed", "value": "east"},
                    {"name": "group_by", "filterType": "params", "value": "day"},
                ],
            }
        }
    ]
    dashboard.save(update_fields=["view_sets"])

    filtered = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=datasource.id,
        request_data={"region": "east", "group_by": "day"},
    )
    assert filtered == {"region": "east", "group_by": "day"}


@pytest.mark.django_db
def test_share_query_case2_visitor_cannot_change_widget_fixed_params(settings, dashboard):
    """case2: 访问者修改 fixed 参数 → 覆盖回画布声明值。"""
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.operation_analysis.services.share_service import filter_share_query_params

    datasource = DataSourceAPIModel.objects.create(
        name=f"share-fixed-tamper-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        # schema 为可改类型：若只靠 get_source_data 会接受 west；分享层必须覆盖
        params=[{"name": "region", "filterType": "params", "value": "west"}],
        created_by="alice",
        updated_by="alice",
    )
    dashboard.view_sets = [
        {
            "valueConfig": {
                "dataSource": datasource.id,
                "dataSourceParams": [{"name": "region", "filterType": "fixed", "value": "east"}],
            }
        }
    ]
    dashboard.save(update_fields=["view_sets"])

    filtered = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=datasource.id,
        request_data={"region": "west"},
    )
    assert filtered == {"region": "east"}

    # 省略 fixed 键时也应注入，避免访问者靠缺省绕过
    filtered_omitted = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=datasource.id,
        request_data={},
    )
    assert filtered_omitted == {"region": "east"}


@pytest.mark.django_db
def test_share_query_case3_widget_empty_rejects_schema_only_params(settings, dashboard):
    """case3: widget 未声明交互参数时，禁止提交 schema 非 fixed 键；fixed 仍强制注入。"""
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.operation_analysis.services.share_service import (
        ShareQueryParamsDenied,
        filter_share_query_params,
    )

    datasource = DataSourceAPIModel.objects.create(
        name=f"share-schema-fallback-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        params=[
            {"name": "group_by", "filterType": "params", "value": "day"},
            {"name": "limit", "filterType": "fixed", "value": 10},
        ],
        created_by="alice",
        updated_by="alice",
    )
    dashboard.view_sets = [{"valueConfig": {"dataSource": datasource.id, "dataSourceParams": []}}]
    dashboard.save(update_fields=["view_sets"])

    with pytest.raises(ShareQueryParamsDenied, match="未声明参数"):
        filter_share_query_params(
            dashboard=dashboard,
            data_source_id=datasource.id,
            request_data={"group_by": "week", "limit": 99},
        )

    filtered = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=datasource.id,
        request_data={"limit": 99},
    )
    assert filtered == {"limit": 10}

    filtered_empty = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=datasource.id,
        request_data={},
    )
    assert filtered_empty == {"limit": 10}


@pytest.mark.django_db
def test_share_query_case4_unknown_params_rejected(settings, dashboard):
    """case4: 未知参数 → 拒绝。"""
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.operation_analysis.services.share_service import (
        ShareQueryParamsDenied,
        filter_share_query_params,
    )

    datasource = DataSourceAPIModel.objects.create(
        name=f"share-unknown-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        params=[{"name": "region", "filterType": "filter", "value": "east"}],
        created_by="alice",
        updated_by="alice",
    )
    dashboard.view_sets = [
        {
            "valueConfig": {
                "dataSource": datasource.id,
                "dataSourceParams": [{"name": "region", "filterType": "filter", "value": "east"}],
            }
        }
    ]
    dashboard.save(update_fields=["view_sets"])

    with pytest.raises(ShareQueryParamsDenied, match="未声明参数"):
        filter_share_query_params(
            dashboard=dashboard,
            data_source_id=datasource.id,
            request_data={"region": "east", "secret_scope": "all"},
        )


@pytest.mark.django_db
def test_share_query_rejects_schema_only_params_when_widget_partial(settings, dashboard):
    """组件只声明部分 params 时，schema 中未在画布声明的非 fixed 键不可提交。"""
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.operation_analysis.services.share_service import (
        ShareQueryParamsDenied,
        filter_share_query_params,
    )

    datasource = DataSourceAPIModel.objects.create(
        name=f"share-partial-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        params=[
            {"name": "group_by", "filterType": "params", "value": "day"},
            {"name": "limit", "filterType": "fixed", "value": 10},
        ],
        created_by="alice",
        updated_by="alice",
    )
    dashboard.view_sets = [
        {
            "valueConfig": {
                "dataSource": datasource.id,
                "chartType": "topN",
                "dataSourceParams": [{"name": "limit", "filterType": "fixed", "value": 10}],
            }
        }
    ]
    dashboard.save(update_fields=["view_sets"])

    with pytest.raises(ShareQueryParamsDenied, match="未声明参数"):
        filter_share_query_params(
            dashboard=dashboard,
            data_source_id=datasource.id,
            request_data={"group_by": "day", "limit": 10},
        )

    filtered = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=datasource.id,
        request_data={"limit": 99},
    )
    assert filtered == {"limit": 10}

    with pytest.raises(ShareQueryParamsDenied):
        filter_share_query_params(
            dashboard=dashboard,
            data_source_id=datasource.id,
            request_data={"query_list": []},
        )


@pytest.mark.django_db
def test_share_query_allows_query_list_only_for_table_widgets(settings, dashboard):
    from apps.operation_analysis.services.share_service import (
        ShareQueryParamsDenied,
        filter_share_query_params,
    )

    dashboard.view_sets = [
        {
            "valueConfig": {
                "dataSource": 7,
                "chartType": "table",
                "dataSourceParams": [{"name": "region", "filterType": "filter"}],
            }
        }
    ]
    dashboard.save(update_fields=["view_sets"])

    filtered = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=7,
        request_data={
            "page": 1,
            "page_size": 20,
            "query_list": [{"field": "name", "type": "str*", "value": "bk"}],
        },
    )
    assert filtered["query_list"] == [{"field": "name", "type": "str*", "value": "bk"}]

    dashboard.view_sets = [
        {
            "valueConfig": {
                "dataSource": 7,
                "chartType": "line",
                "dataSourceParams": [{"name": "region", "filterType": "filter"}],
            }
        }
    ]
    dashboard.save(update_fields=["view_sets"])
    with pytest.raises(ShareQueryParamsDenied):
        filter_share_query_params(
            dashboard=dashboard,
            data_source_id=7,
            request_data={"query_list": []},
        )


@pytest.mark.django_db
def test_share_query_widget_empty_only_allows_fixed_and_runtime_keys(settings, dashboard):
    """widget 无 dataSourceParams 时，不可提交 schema 非 fixed；未知键仍拒绝。"""
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.operation_analysis.services.share_service import (
        ShareQueryParamsDenied,
        filter_share_query_params,
    )

    datasource = DataSourceAPIModel.objects.create(
        name=f"share-fallback-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        params=[
            {"name": "group_by", "filterType": "params", "value": "day"},
            {"name": "limit", "filterType": "fixed", "value": 10},
        ],
        created_by="alice",
        updated_by="alice",
    )
    dashboard.view_sets = [{"valueConfig": {"dataSource": datasource.id, "dataSourceParams": []}}]
    dashboard.save(update_fields=["view_sets"])

    with pytest.raises(ShareQueryParamsDenied, match="未声明参数"):
        filter_share_query_params(
            dashboard=dashboard,
            data_source_id=datasource.id,
            request_data={"group_by": "day", "limit": 10},
        )

    filtered = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=datasource.id,
        request_data={"limit": 10},
    )
    assert filtered == {"limit": 10}

    with pytest.raises(ShareQueryParamsDenied):
        filter_share_query_params(
            dashboard=dashboard,
            data_source_id=datasource.id,
            request_data={"unknown_key": 1},
        )


@pytest.mark.django_db
def test_share_query_rejects_undeclared_namespace_id(settings, dashboard):
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
    from apps.operation_analysis.services.share_service import (
        ShareQueryParamsDenied,
        filter_share_query_params,
    )

    allowed_ns = NameSpace.objects.create(
        name=f"share-ns-ok-{uuid.uuid4()}",
        account="a",
        password="b",
        domain="localhost:4222",
    )
    other_ns = NameSpace.objects.create(
        name=f"share-ns-other-{uuid.uuid4()}",
        account="a",
        password="b",
        domain="localhost:4222",
    )
    datasource = DataSourceAPIModel.objects.create(
        name=f"share-ns-{uuid.uuid4()}",
        rest_api="monitor/test",
        groups=[1],
        params=[],
        created_by="alice",
        updated_by="alice",
    )
    datasource.namespaces.add(allowed_ns)
    dashboard.view_sets = [{"valueConfig": {"dataSource": datasource.id, "dataSourceParams": []}}]
    dashboard.save(update_fields=["view_sets"])

    filtered = filter_share_query_params(
        dashboard=dashboard,
        data_source_id=datasource.id,
        request_data={"namespace_id": allowed_ns.id},
    )
    assert filtered == {"namespace_id": allowed_ns.id}

    with pytest.raises(ShareQueryParamsDenied):
        filter_share_query_params(
            dashboard=dashboard,
            data_source_id=datasource.id,
            request_data={"namespace_id": other_ns.id},
        )


@pytest.mark.django_db
def test_prepare_state_roundtrip_exchanges_without_raw_token(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    store = {}
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.set",
        lambda key, value, timeout=None: store.__setitem__(key, value),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.get",
        lambda key, default=None: store.get(key, default),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.delete",
        lambda key: store.pop(key, None) is not None,
    )
    from apps.operation_analysis.services.share_service import prepare_share_exchange

    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    state, nonce = prepare_share_exchange(token=result.token)
    session = exchange_share(state=state, prepare_nonce=nonce, visitor=visitor)
    assert session.share_link_id == result.link.id
    with pytest.raises(ShareLinkInvalid):
        exchange_share(state=state, prepare_nonce=nonce, visitor=visitor)


@pytest.mark.django_db
def test_exchange_state_requires_matching_prepare_nonce(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    store = {}
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.set",
        lambda key, value, timeout=None: store.__setitem__(key, value),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.get",
        lambda key, default=None: store.get(key, default),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.delete",
        lambda key: store.pop(key, None) is not None,
    )
    from apps.operation_analysis.services.share_service import prepare_share_exchange

    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    state, nonce = prepare_share_exchange(token=result.token)
    with pytest.raises(ShareLinkInvalid):
        exchange_share(state=state, prepare_nonce="wrong-nonce", visitor=visitor)
    # state 未被错误 nonce 消费，正确 nonce 仍可兑换
    session = exchange_share(state=state, prepare_nonce=nonce, visitor=visitor)
    assert session.share_link_id == result.link.id


@pytest.mark.django_db
def test_rate_limit_failure_does_not_consume_prepare_state(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    store = {}
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.set",
        lambda key, value, timeout=None: store.__setitem__(key, value),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.get",
        lambda key, default=None: store.get(key, default),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.delete",
        lambda key: store.pop(key, None) is not None,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.enforce_share_visitor_link_rate_limit",
        lambda **_: (_ for _ in ()).throw(ShareRateLimited()),
    )
    from apps.operation_analysis.services.share_service import (
        ShareRateLimited,
        prepare_share_exchange,
    )

    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    state, nonce = prepare_share_exchange(token=result.token)
    with pytest.raises(ShareRateLimited):
        exchange_share(state=state, prepare_nonce=nonce, visitor=visitor)

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.enforce_share_visitor_link_rate_limit",
        lambda **_: None,
    )
    session = exchange_share(state=state, prepare_nonce=nonce, visitor=visitor)
    assert session.share_link_id == result.link.id


@pytest.mark.django_db
def test_visitor_link_rate_limit_is_isolated_per_visitor(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    counters = {}

    def fake_add(key, value, timeout=None):
        if key in counters:
            return False
        counters[key] = value
        return True

    def fake_incr(key):
        counters[key] = counters.get(key, 0) + 1
        return counters[key]

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.add",
        fake_add,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.incr",
        fake_incr,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.SHARE_VISITOR_LINK_RATE_LIMIT",
        1,
    )
    from apps.operation_analysis.services.share_service import (
        ShareRateLimited,
        enforce_share_visitor_link_rate_limit,
    )

    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    visitor_c = User.objects.create(
        username="carol-rate",
        domain="third.com",
        display_name="Carol",
        email="carol-rate@example.com",
        password="x",
    )
    enforce_share_visitor_link_rate_limit(link_id=result.link.id, visitor=visitor)
    with pytest.raises(ShareRateLimited):
        enforce_share_visitor_link_rate_limit(link_id=result.link.id, visitor=visitor)
    # 另一访问者不受影响
    enforce_share_visitor_link_rate_limit(link_id=result.link.id, visitor=visitor_c)

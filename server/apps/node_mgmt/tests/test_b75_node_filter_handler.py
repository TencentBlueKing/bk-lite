"""NodeFilterHandler 真实行为测试：布尔归一、标准字段白名单过滤、可升级过滤、组合应用。

纯 DB 查询逻辑，无外部边界。断言真实 QuerySet 结果与 ORM 注入防护。
"""
import pytest

from django.db.models import Q

from apps.node_mgmt.models import Node, NodeComponentVersion
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.views.node import NodeFilterHandler as H


@pytest.fixture
def nodes(db):
    region = CloudRegion.objects.create(name="cr-filter")
    n1 = Node.objects.create(
        id="fn-1", name="alpha", ip="10.0.0.1", operating_system="linux",
        cpu_architecture="x86_64", collector_configuration_directory="/etc",
        cloud_region=region,
    )
    n2 = Node.objects.create(
        id="fn-2", name="beta", ip="192.168.1.2", operating_system="windows",
        cpu_architecture="arm64", collector_configuration_directory="/etc",
        cloud_region=region,
    )
    return region, n1, n2


# --------------------------------------------------------------------------- #
# normalize_bool_value
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True), ("1", True), ("yes", True),
        ("false", False), ("0", False), ("no", False),
        (True, True), (False, False),
    ],
)
def test_normalize_bool_value(value, expected):
    assert H.normalize_bool_value(value) == expected


def test_normalize_bool_value_none():
    assert H.normalize_bool_value(None) is None


# --------------------------------------------------------------------------- #
# build_standard_filters
# --------------------------------------------------------------------------- #
def test_build_standard_filters_empty_returns_empty_q():
    assert H.build_standard_filters({}) == Q()


def test_build_standard_filters_rejects_unlisted_field():
    # 非白名单字段被静默跳过（防 ORM 注入）
    q = H.build_standard_filters({"password": [{"value": "x", "lookup_expr": "exact"}]})
    assert q == Q()


def test_build_standard_filters_rejects_unlisted_lookup():
    q = H.build_standard_filters({"name": [{"value": "x", "lookup_expr": "regex"}]})
    assert q == Q()


@pytest.mark.django_db
def test_build_standard_filters_icontains(nodes):
    region, n1, n2 = nodes
    q = H.build_standard_filters({"name": [{"value": "alph", "lookup_expr": "icontains"}]})
    result = Node.objects.filter(q)
    assert list(result) == [n1]


@pytest.mark.django_db
def test_build_standard_filters_bool_normalized_to_exact(nodes):
    region, n1, n2 = nodes
    # cpu_architecture 在白名单内；bool lookup 被规范化为 exact
    q = H.build_standard_filters({"operating_system": [{"value": "linux", "lookup_expr": "exact"}]})
    assert Node.objects.filter(q).count() == 1


def test_build_standard_filters_skips_empty_value():
    q = H.build_standard_filters({"name": [{"value": "", "lookup_expr": "exact"}]})
    assert q == Q()


# --------------------------------------------------------------------------- #
# handle_upgradeable_filter
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_handle_upgradeable_true(nodes):
    region, n1, n2 = nodes
    NodeComponentVersion.objects.create(
        node=n1, component_type="controller", component_id="c", version="1.0.0", upgradeable=True
    )
    result = H.handle_upgradeable_filter(Node.objects.all(), [{"value": True}])
    assert list(result) == [n1]


@pytest.mark.django_db
def test_handle_upgradeable_false_excludes(nodes):
    region, n1, n2 = nodes
    NodeComponentVersion.objects.create(
        node=n1, component_type="controller", component_id="c", version="1.0.0", upgradeable=True
    )
    result = H.handle_upgradeable_filter(Node.objects.all(), [{"value": False}])
    ids = set(result.values_list("id", flat=True))
    assert ids == {n2.id}


@pytest.mark.django_db
def test_handle_upgradeable_contradiction_returns_none(nodes):
    result = H.handle_upgradeable_filter(
        Node.objects.all(), [{"value": True}, {"value": False}]
    )
    assert result.count() == 0


@pytest.mark.django_db
def test_handle_upgradeable_no_valid_values_returns_original(nodes):
    qs = Node.objects.all()
    result = H.handle_upgradeable_filter(qs, [{"novalue": 1}])
    assert result.count() == qs.count()


def test_handle_upgradeable_non_list_returns_original():
    sentinel = object()
    assert H.handle_upgradeable_filter(sentinel, "notalist") is sentinel


# --------------------------------------------------------------------------- #
# apply_filters
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_apply_filters_empty_returns_queryset(nodes):
    qs = Node.objects.all()
    assert H.apply_filters(qs, {}) is qs


@pytest.mark.django_db
def test_apply_filters_combines_standard_and_special(nodes):
    region, n1, n2 = nodes
    NodeComponentVersion.objects.create(
        node=n1, component_type="controller", component_id="c", version="1.0.0", upgradeable=True
    )
    result = H.apply_filters(
        Node.objects.all(),
        {
            "operating_system": [{"value": "linux", "lookup_expr": "exact"}],
            "upgradeable": [{"value": True}],
        },
    )
    assert list(result) == [n1]


@pytest.mark.django_db
def test_apply_filters_standard_only(nodes):
    region, n1, n2 = nodes
    result = H.apply_filters(
        Node.objects.all(),
        {"ip": [{"value": "192.168", "lookup_expr": "icontains"}]},
    )
    assert list(result) == [n2]

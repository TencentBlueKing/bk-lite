"""Issue #5851：内置 Minio 应按大小写不敏感匹配 DEFAULT_OBJ_ORDER 中的 MinIO。"""

import pytest

import apps.node_mgmt.models  # noqa: F401
from apps.monitor.constants.monitor_object import (
    MonitorObjConstants,
    default_order_name_matches,
    resolve_default_object_order,
)
from apps.monitor.management.services.default_order_migrate import migrate_default_order
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType


def _middleware_name_list():
    for item in MonitorObjConstants.DEFAULT_OBJ_ORDER:
        if item.get("type") == "Middleware":
            return item.get("name_list", [])
    raise AssertionError("DEFAULT_OBJ_ORDER 缺少 Middleware")


def _exact_name_idx(obj_name, type_id):
    for item in MonitorObjConstants.DEFAULT_OBJ_ORDER:
        if item.get("type") != type_id:
            continue
        for name_idx, name in enumerate(item.get("name_list", [])):
            if obj_name == name:
                return name_idx
    return None


def test_catalog_places_minio_after_activemq_before_jetty():
    names = _middleware_name_list()
    assert names.index("MinIO") == 12
    assert names[11] == "ActiveMQ"
    assert names[13] == "Jetty"
    assert "Minio" not in names


def test_exact_compare_misses_builtin_minio_name():
    assert _exact_name_idx("MinIO", "Middleware") == 12
    assert _exact_name_idx("Minio", "Middleware") is None


def test_name_match_is_casefold():
    assert default_order_name_matches("Minio", "MinIO") is True
    assert default_order_name_matches("MinIO", "MinIO") is True
    assert default_order_name_matches("Minio", "Jetty") is False
    assert default_order_name_matches(None, "MinIO") is False


def test_resolve_maps_minio_spellings_to_middleware_index():
    assert resolve_default_object_order("Minio", "Middleware") == 12
    assert resolve_default_object_order("MinIO", "Middleware") == 12


def test_resolve_keeps_mysql_in_database():
    assert resolve_default_object_order("Mysql", "Database") == 3


def test_resolve_unknown_name_is_none():
    assert resolve_default_object_order("NotAMonitorObject", "Middleware") is None


def test_resolve_does_not_cross_types():
    assert resolve_default_object_order("Minio", "Database") is None
    assert resolve_default_object_order("Mysql", "Middleware") is None


@pytest.mark.django_db
def test_migrate_assigns_builtin_minio_middleware_order():
    obj_type = MonitorObjectType.objects.create(id="Middleware", name="中间件", order=999)
    obj = MonitorObject.objects.create(name="Minio", level="base", type=obj_type, order=999)

    migrate_default_order()

    obj.refresh_from_db()
    assert obj.name == "Minio"
    assert obj.order == 12


@pytest.mark.django_db
def test_migrate_assigns_catalog_minio_spelling():
    obj_type = MonitorObjectType.objects.create(id="Middleware", name="中间件", order=999)
    obj = MonitorObject.objects.create(name="MinIO", level="base", type=obj_type, order=999)

    migrate_default_order()

    obj.refresh_from_db()
    assert obj.name == "MinIO"
    assert obj.order == 12


@pytest.mark.django_db
def test_migrate_skips_manually_ordered_objects():
    obj_type = MonitorObjectType.objects.create(id="Middleware", name="中间件", order=1)
    obj = MonitorObject.objects.create(name="Minio", level="base", type=obj_type, order=7)

    migrate_default_order()

    obj.refresh_from_db()
    assert obj.name == "Minio"
    assert obj.order == 7

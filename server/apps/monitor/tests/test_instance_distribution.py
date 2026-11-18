"""监控实例分布：分类/对象计数、0 行和返回条数。"""

import pytest

from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorObjectType
from apps.monitor.nats.generic_query import query_monitor_instance_distribution
from apps.monitor.nats.monitor import list_monitor_object_type_options, list_monitor_objects_by_type

pytestmark = pytest.mark.django_db


def _scope(monkeypatch, *, superuser=True):
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        lambda user_info: (user_info, 1, False, [1], superuser, None),
    )


def _type(type_id, name, order):
    return MonitorObjectType.objects.create(id=type_id, name=name, order=order)


def _object(name, type_id=None, order=999, *, visible=True, parent=None, level="base"):
    return MonitorObject.objects.create(
        name=name,
        type_id=type_id,
        order=order,
        is_visible=visible,
        parent=parent,
        level=level,
        display_name="",
    )


def _instance(obj, instance_id, *, active=True, org=1, deleted=False):
    item = MonitorInstance.objects.create(
        id=instance_id,
        name=instance_id,
        monitor_object=obj,
        is_active=active,
        ip="10.0.0.8",
    )
    if deleted:
        item.is_deleted = True
        item.save(update_fields=["is_deleted"])
    if org is not None:
        MonitorInstanceOrganization.objects.create(monitor_instance=item, organization=org)
    return item


def _rows(result):
    assert result["result"] is True, result
    return result["data"]


def test_open_type_distribution_drops_zeros_and_uncategorized(monkeypatch):
    _scope(monkeypatch)
    os_type = _type("os", "OS", 1)
    _type("net", "Network Device", 2)
    _type("empty", "Empty", 3)
    host = _object("Host", os_type.id, 1, visible=False)
    process = _object("Process", os_type.id, 2, parent=host, level="derivative")
    switch = _object("Switch", "net", 1)
    _object("Router", "net", 2)
    bare = _object("Bare")
    _instance(host, "host-1")
    _instance(host, "host-deleted", deleted=True)
    _instance(process, "proc-1")
    _instance(switch, "sw-1")
    _instance(bare, "bare-1")
    _instance(host, "host-other-org", org=2)

    rows = _rows(query_monitor_instance_distribution(group_by="monitor_object_type", user_info={"team": 1}))

    assert [(row["group_id"], row["instance_count"]) for row in rows] == [("os", 2), ("net", 1)]
    assert all(row["group_id"] != "empty" for row in rows)
    assert "Bare" not in {row["group_value"] for row in rows}


def test_open_object_distribution_keeps_uncategorized_and_splits_children(monkeypatch):
    _scope(monkeypatch)
    _type("os", "OS", 1)
    _type("net", "Network Device", 2)
    host = _object("Host", "os", 1, visible=False)
    process = _object("Process", "os", 2, parent=host, level="derivative")
    switch = _object("Switch", "net", 1)
    _object("Router", "net", 2)
    bare = _object("Bare", order=1)
    _instance(host, "host-1")
    _instance(process, "proc-1")
    _instance(switch, "sw-1")
    _instance(bare, "bare-1")

    rows = _rows(query_monitor_instance_distribution(group_by="monitor_object", user_info={"team": 1}))

    assert [(row["group_value"], row["instance_count"]) for row in rows] == [
        ("Host", 1),
        ("Process", 1),
        ("Switch", 1),
        ("Bare", 1),
    ]
    assert rows[0]["group_id"] == str(host.id)


def test_selected_types_keep_zero_and_page_size_cuts_after_sort(monkeypatch):
    _scope(monkeypatch)
    _type("os", "OS", 1)
    _type("net", "Network Device", 2)
    _type("empty", "Empty", 3)
    host = _object("Host", "os", 1)
    switch = _object("Switch", "net", 1)
    _instance(host, "host-1")
    _instance(host, "host-2")
    _instance(switch, "sw-1")

    rows = _rows(
        query_monitor_instance_distribution(
            group_by="monitor_object_type",
            monitor_object_type_ids=["net", "empty", "os"],
            user_info={"team": 1},
        )
    )
    assert [(row["group_id"], row["instance_count"]) for row in rows] == [("os", 2), ("net", 1), ("empty", 0)]
    topped = _rows(
        query_monitor_instance_distribution(
            group_by="monitor_object_type",
            monitor_object_type_ids="os,net,empty",
            page_size=2,
            user_info={"team": 1},
        )
    )
    assert [row["group_id"] for row in topped] == ["os", "net"]


def test_selected_type_lists_every_object_including_zero(monkeypatch):
    _scope(monkeypatch)
    _type("net", "Network Device", 1)
    _type("os", "OS", 2)
    switch = _object("Switch", "net", 2)
    router = _object("Router", "net", 1)
    _object("Host", "os", 1)
    _instance(switch, "sw-1")

    rows = _rows(
        query_monitor_instance_distribution(
            group_by="monitor_object",
            monitor_object_type_ids=["net"],
            user_info={"team": 1},
        )
    )

    assert [(row["group_value"], row["instance_count"]) for row in rows] == [("Switch", 1), ("Router", 0)]
    assert rows[1]["group_id"] == str(router.id)


def test_selected_objects_keep_zero_and_must_belong_to_the_categories(monkeypatch):
    _scope(monkeypatch)
    _type("os", "OS", 1)
    _type("net", "Network Device", 2)
    host = _object("Host", "os", 1)
    switch = _object("Switch", "net", 1)
    router = _object("Router", "net", 2)
    _instance(host, "host-1")
    _instance(switch, "sw-1")

    narrowed = _rows(
        query_monitor_instance_distribution(
            group_by="monitor_object_type",
            monitor_object_type_ids=["os", "net"],
            monitor_object_ids=[switch.id],
            user_info={"team": 1},
        )
    )
    assert [(row["group_id"], row["instance_count"]) for row in narrowed] == [("net", 1), ("os", 0)]
    objects = _rows(
        query_monitor_instance_distribution(
            group_by="monitor_object",
            monitor_object_type_ids=["net"],
            monitor_object_ids=[router.id, switch.id],
            user_info={"team": 1},
        )
    )
    assert [(row["group_id"], row["instance_count"]) for row in objects] == [
        (str(switch.id), 1),
        (str(router.id), 0),
    ]
    missing_type = query_monitor_instance_distribution(
        group_by="monitor_object",
        monitor_object_ids=[switch.id],
        user_info={"team": 1},
    )
    assert missing_type["result"] is False
    assert "必须先选择分类" in missing_type["message"]
    mismatched = query_monitor_instance_distribution(
        group_by="monitor_object",
        monitor_object_type_ids=["net"],
        monitor_object_ids=[host.id],
        user_info={"team": 1},
    )
    assert mismatched["result"] is False
    assert "不属于所选分类" in mismatched["message"]
    absent = query_monitor_instance_distribution(
        group_by="monitor_object_type",
        monitor_object_type_ids=["missing"],
        user_info={"team": 1},
    )
    assert absent["result"] is False
    assert "分类不存在" in absent["message"]
    unknown = query_monitor_instance_distribution(
        group_by="monitor_object",
        monitor_object_type_ids=["net"],
        monitor_object_ids=[999999],
        user_info={"team": 1},
    )
    assert unknown["result"] is False
    assert "不存在或无权访问" in unknown["message"]


def test_status_is_applied_before_counting(monkeypatch):
    _scope(monkeypatch)
    _type("os", "OS", 1)
    host = _object("Host", "os", 1)
    _instance(host, "host-on")
    _instance(host, "host-off", active=False)

    active = _rows(
        query_monitor_instance_distribution(
            group_by="monitor_object",
            monitor_object_type_ids=["os"],
            monitor_object_ids=[host.id],
            status="active",
            user_info={"team": 1},
        )
    )
    inactive = _rows(
        query_monitor_instance_distribution(
            group_by="monitor_object",
            monitor_object_type_ids=["os"],
            status="inactive",
            user_info={"team": 1},
        )
    )
    illegal = query_monitor_instance_distribution(
        group_by="monitor_object_type",
        status="paused",
        user_info={"team": 1},
    )

    assert active == [{"group_id": str(host.id), "group_value": "Host", "instance_count": 1}]
    assert inactive == [{"group_id": str(host.id), "group_value": "Host", "instance_count": 1}]
    assert illegal["result"] is False
    assert "实例状态不受支持" in illegal["message"]


def test_limits_and_rejected_controls(monkeypatch):
    _scope(monkeypatch)
    _type("os", "OS", 1)
    _type("net", "Network Device", 2)
    host = _object("Host", "os", 1)
    switch = _object("Switch", "net", 1)
    _instance(host, "host-1")
    _instance(switch, "sw-1")
    user_info = {"team": 1}

    for page_size in (0, 501, "x", True):
        result = query_monitor_instance_distribution(group_by="monitor_object_type", page_size=page_size, user_info=user_info)
        assert result["result"] is False
        assert "1 到 500" in result["message"]
    accepted = _rows(query_monitor_instance_distribution(group_by="monitor_object_type", page_size=500, user_info=user_info))
    assert [row["group_id"] for row in accepted] == ["os", "net"]
    assert "页码" in query_monitor_instance_distribution(group_by="monitor_object_type", page=1, user_info=user_info)["message"]
    assert "排序" in query_monitor_instance_distribution(group_by="monitor_object_type", order_by="name", user_info=user_info)["message"]
    assert "实例范围" in query_monitor_instance_distribution(group_by="monitor_object_type", instance_ids=["host-1"], user_info=user_info)["message"]
    assert "分析模式" in query_monitor_instance_distribution(group_by="monitor_object_type", analysis_mode="detail", user_info=user_info)["message"]
    assert "分布维度" in query_monitor_instance_distribution(user_info=user_info)["message"]

    monkeypatch.setattr("apps.monitor.services.instance_distribution.STAT_GROUP_MAX", 1)
    capped = query_monitor_instance_distribution(group_by="monitor_object_type", user_info=user_info)
    assert capped["result"] is False
    assert "500" in capped["message"]
    kept = _rows(query_monitor_instance_distribution(group_by="monitor_object_type", page_size=1, user_info=user_info))
    assert [row["group_id"] for row in kept] == ["os"]


def test_labels_follow_the_language_pack(monkeypatch):
    _scope(monkeypatch)
    _type("os", "OS", 1)
    host = _object("Host", "os", 1)
    host.display_name = "库内主机"
    host.save(update_fields=["display_name"])
    _instance(host, "host-1")

    class Loader:
        def __init__(self, app, default_lang):
            self.lang = default_lang

        def get(self, key, default=None):
            if self.lang == "zh-Hans" and key == "monitor_object_type.os":
                return "操作系统"
            if self.lang == "zh-Hans" and key == "monitor_object.Host":
                return "主机"
            return default

    monkeypatch.setattr("apps.monitor.services.instance_distribution.LanguageLoader", Loader)
    typed = _rows(query_monitor_instance_distribution(group_by="monitor_object_type", user_info={"team": 1, "locale": "zh-Hans"}))
    named = _rows(query_monitor_instance_distribution(group_by="monitor_object", user_info={"team": 1, "locale": "zh-Hans"}))
    assert typed[0]["group_value"] == "操作系统"
    assert named[0]["group_value"] == "主机"


def test_explicit_object_without_permission_fails(monkeypatch):
    _scope(monkeypatch, superuser=False)
    _type("os", "OS", 1)
    host = _object("Host", "os", 1)
    item = _instance(host, "host-1")
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_monitor_instance_permission",
        lambda monitor_object_id, user_info: ({}, None),
    )
    result = query_monitor_instance_distribution(
        group_by="monitor_object",
        monitor_object_type_ids=["os"],
        monitor_object_ids=[host.id],
        user_info={"team": 1},
    )
    assert result["result"] is False
    assert result["data"] == {"status": "forbidden"}
    assert "无权限" in result["message"]
    assert item.id == "host-1"


def test_open_scope_skips_objects_without_permission(monkeypatch):
    _scope(monkeypatch, superuser=False)
    _type("os", "OS", 1)
    visible = _object("Host", "os", 1)
    hidden = _object("Process", "os", 2)
    empty = _object("Switch", "os", 3)
    _instance(visible, "host-1")
    _instance(hidden, "proc-1")

    def permission(monitor_object_id, user_info):
        if int(monitor_object_id) == hidden.id:
            return {}, None
        return {"instance": True, "team": False}, None

    monkeypatch.setattr("apps.monitor.nats.generic_query._get_monitor_instance_permission", permission)
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_authorized_instance_queryset",
        lambda permission, scope_ids: MonitorInstance.objects.all(),
    )
    typed = _rows(query_monitor_instance_distribution(group_by="monitor_object_type", user_info={"team": 1}))
    objects = _rows(
        query_monitor_instance_distribution(
            group_by="monitor_object",
            monitor_object_type_ids=["os"],
            user_info={"team": 1},
        )
    )
    assert typed == [{"group_id": "os", "group_value": "OS", "instance_count": 1}]
    assert [(row["group_value"], row["instance_count"]) for row in objects] == [("Host", 1), ("Switch", 0)]
    assert empty.name == "Switch"


def test_category_and_object_options_follow_the_selected_types(monkeypatch):
    _type("os", "OS", 2)
    _type("net", "Network Device", 1)
    host = _object("Host", "os", 1, visible=False)
    _object("Switch", "net", 1)

    class Loader:
        def __init__(self, app, default_lang):
            pass

        def get(self, key, default=None):
            if key == "monitor_object_type.net":
                return "网络设备"
            if key == "monitor_object.Host":
                return "主机"
            return default

    monkeypatch.setattr("apps.monitor.nats.monitor.LanguageLoader", Loader)
    types = list_monitor_object_type_options(user_info={"locale": "zh-Hans"})
    objects = list_monitor_objects_by_type(monitor_object_type_ids=["os"], user_info={"locale": "zh-Hans"})
    empty = list_monitor_objects_by_type()

    assert types["result"] is True
    assert [(row["id"], row["display_name"]) for row in types["data"]] == [("net", "网络设备"), ("os", "OS")]
    assert objects["data"] == [{"id": host.id, "name": "Host", "display_name": "主机"}]
    assert empty["data"] == []

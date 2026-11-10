from apps.cmdb.services.ci_context_policy import (
    CONTEXT_APPLICATION,
    LINK_FOLLOW,
    LINK_INCLUDE,
    LINK_EXCLUDE,
    classify_application_edge,
)

APP = {"model_id": "application", "inst_uuid": "app-wecenter"}
HOST = {"model_id": "host", "inst_uuid": "host-1"}
MYSQL = {"model_id": "mysql", "inst_uuid": "mysql-1"}
REDIS = {"model_id": "redis", "inst_uuid": "redis-1"}
CUSTOM = {"model_id": "tidb_extra", "inst_uuid": "tidb-1"}
SWITCH = {"model_id": "switch", "inst_uuid": "sw-1"}
SYS = {"model_id": "system", "inst_uuid": "sys-1"}


def edge(asst_id, src, dst, model_asst_id=None, link=LINK_FOLLOW):
    return {
        "asst_id": asst_id,
        "model_asst_id": model_asst_id or f"{src['model_id']}_{asst_id}_{dst['model_id']}",
        "context_link": link,
        "src": src,
        "dst": dst,
    }


def test_rule1_application_run_host_is_layer1():
    d = classify_application_edge(edge("run", APP, HOST), src_is_member=False)
    assert d.include and d.layer == 1 and d.root_uuid == "app-wecenter" and d.ci_uuid == "host-1"


def test_rule1_application_connect_custom_model_needs_no_per_model_flag():
    d = classify_application_edge(edge("connect", APP, CUSTOM), src_is_member=False)
    assert d.include and d.layer == 1 and d.ci_uuid == "tidb-1"


def test_rule2_all_host_run_middleware_share_one_rule():
    for dst in (MYSQL, REDIS, CUSTOM):
        d = classify_application_edge(edge("run", HOST, dst), src_is_member=True)
        assert d.include and d.layer == 2 and d.via_uuid == "host-1"


def test_rule3_system_contains_only_attaches_system():
    d = classify_application_edge(edge("contains", SYS, APP), src_is_member=False)
    assert d.include is False and d.attach_system_uuid == "sys-1" and d.root_uuid == "app-wecenter"


def test_belong_not_in_index():
    d = classify_application_edge(
        edge("belong", HOST, {"model_id": "aliyun_account", "inst_uuid": "acc"}),
        src_is_member=True,
    )
    assert d.include is False


def test_switch_denylist_even_on_run():
    assert classify_application_edge(edge("run", APP, SWITCH), src_is_member=False).include is False


def test_legacy_model_asst_id_run_uses_asst_id_field():
    d = classify_application_edge(edge("run", APP, HOST, model_asst_id="run"), src_is_member=False)
    assert d.include and d.layer == 1


def test_exclude_override_blocks_run():
    d = classify_application_edge(edge("run", APP, HOST, link=LINK_EXCLUDE), src_is_member=False)
    assert d.include is False


def test_include_override_forces_belong():
    d = classify_application_edge(edge("belong", APP, CUSTOM, link=LINK_INCLUDE), src_is_member=False)
    assert d.include and d.layer == 1

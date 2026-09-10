from apps.cmdb.services.application_system import (
    APPLICATION_RUN_HOST,
    SYSTEM_CONTAINS_APPLICATION,
    build_application_system_row,
    expand_systems_to_host_uuids,
    query_association_edges,
)


def test_drop_system_without_uuid():
    assert build_application_system_row({"inst_name": "sys-ecom"}) is None
    assert build_application_system_row({"inst_uuid": "", "inst_name": "sys-ecom"}) is None


def test_system_row_uses_inst_name_as_display():
    row = build_application_system_row({"inst_uuid": "s1", "inst_name": "sys-ecom"})
    assert row == {"inst_uuid": "s1", "inst_name": "sys-ecom", "display_name": "sys-ecom"}


def test_expand_walks_system_application_host_and_dedupes():
    graph = {
        ("system", "s1"): [
            {
                "model_asst_id": SYSTEM_CONTAINS_APPLICATION,
                "inst_list": [
                    {"model_id": "application", "inst_uuid": "a1"},
                    {"model_id": "application", "inst_uuid": "a2"},
                    {"model_id": "host", "inst_uuid": "should-skip"},
                ],
            },
            {
                "model_asst_id": "system_depends_system",
                "inst_list": [{"model_id": "application", "inst_uuid": "other"}],
            },
        ],
        ("application", "a1"): [
            {
                "model_asst_id": APPLICATION_RUN_HOST,
                "inst_list": [
                    {"model_id": "host", "inst_uuid": "h1"},
                    {"model_id": "host", "inst_uuid": "h2"},
                ],
            }
        ],
        ("application", "a2"): [
            {
                "model_asst_id": APPLICATION_RUN_HOST,
                "inst_list": [
                    {"model_id": "host", "inst_uuid": "h2"},
                    {"model_id": "host", "inst_uuid": "h3"},
                    {"model_id": "application", "inst_uuid": "nested"},
                ],
            }
        ],
    }

    def loader(model_id, inst_uuid):
        return graph.get((model_id, inst_uuid), [])

    assert expand_systems_to_host_uuids(["s1"], association_loader=loader) == ["h1", "h2", "h3"]


def test_expand_empty_or_unknown_systems_returns_empty():
    assert expand_systems_to_host_uuids([], association_loader=lambda *_: []) == []
    assert expand_systems_to_host_uuids(["missing"], association_loader=lambda *_: []) == []


def test_expand_batches_two_association_queries_and_skips_wrong_peers():
    calls = []

    def edge_loader(asst_id, uuids):
        calls.append((asst_id, list(uuids)))
        if asst_id == SYSTEM_CONTAINS_APPLICATION:
            return [
                {
                    "src_model_id": "system",
                    "src_inst_uuid": "s1",
                    "dst_model_id": "application",
                    "dst_inst_uuid": "a1",
                },
                {
                    "src_model_id": "system",
                    "src_inst_uuid": "s1",
                    "dst_model_id": "host",
                    "dst_inst_uuid": "should-skip",
                },
                {
                    "src_model_id": "application",
                    "src_inst_uuid": "a2",
                    "dst_model_id": "system",
                    "dst_inst_uuid": "s1",
                },
            ]
        return [
            {
                "src_model_id": "application",
                "src_inst_uuid": "a1",
                "dst_model_id": "host",
                "dst_inst_uuid": "h1",
            },
            {
                "src_model_id": "host",
                "src_inst_uuid": "h2",
                "dst_model_id": "application",
                "dst_inst_uuid": "a2",
            },
            {
                "src_model_id": "application",
                "src_inst_uuid": "a1",
                "dst_model_id": "host",
                "dst_inst_uuid": "h1",
            },
        ]

    assert expand_systems_to_host_uuids(["s1"], edge_loader=edge_loader) == ["h1", "h2"]
    assert calls == [
        (SYSTEM_CONTAINS_APPLICATION, ["s1"]),
        (APPLICATION_RUN_HOST, ["a1", "a2"]),
    ]


def test_expand_default_uses_batched_edges_not_per_instance_loader(monkeypatch):
    association_calls = []

    def boom_association(model_id, inst_uuid, **kwargs):
        association_calls.append((model_id, inst_uuid))
        return []

    def fake_edges(asst_id, uuids, graph=None):
        if asst_id == SYSTEM_CONTAINS_APPLICATION:
            return [
                {
                    "src_model_id": "system",
                    "src_inst_uuid": "s1",
                    "dst_model_id": "application",
                    "dst_inst_uuid": "a1",
                }
            ]
        return [
            {
                "src_model_id": "application",
                "src_inst_uuid": "a1",
                "dst_model_id": "host",
                "dst_inst_uuid": "h1",
            }
        ]

    monkeypatch.setattr(
        "apps.cmdb.services.instance.InstanceManage.instance_association_instance_list_by_uuid",
        boom_association,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.application_system.query_association_edges",
        fake_edges,
    )
    assert expand_systems_to_host_uuids(["s1"]) == ["h1"]
    assert association_calls == []


class _FakeGraph:
    def __init__(self):
        self.calls = []

    def query_edge(self, label, params, return_entity=False):
        self.calls.append((label, params, return_entity))
        return [
            {
                "edge": {"model_asst_id": params[0]["value"]},
                "src": {"model_id": "system", "inst_uuid": "s1"},
                "dst": {"model_id": "application", "inst_uuid": "a1"},
            }
        ]


def test_query_association_edges_batches_both_orientations_without_empty_scan():
    graph = _FakeGraph()
    edges = query_association_edges(SYSTEM_CONTAINS_APPLICATION, ["s1", "s1"], graph=graph)
    assert [edge["dst_inst_uuid"] for edge in edges] == ["a1", "a1"]
    assert len(graph.calls) == 2
    for label, params, return_entity in graph.calls:
        assert label == "instance_association"
        assert return_entity is True
        assert params[0] == {"field": "model_asst_id", "type": "str=", "value": SYSTEM_CONTAINS_APPLICATION}
        assert params[1]["type"] == "str[]"
        assert params[1]["value"] == ["s1"]
    assert {params[1]["field"] for _, params, _ in graph.calls} == {"src_inst_uuid", "dst_inst_uuid"}

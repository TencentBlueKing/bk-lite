from apps.operation_analysis.services.application3d.relations import project_application_hosts, project_application_systems


class _FakeGraph:
    def __init__(self, edges):
        self._edges = edges

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query_edge(self, _label, params, return_entity=True):
        field = next(item["field"] for item in params if item["field"] in {"src_inst_uuid", "dst_inst_uuid"})
        values = set(next(item["value"] for item in params if item["field"] == field))
        asst = next(item["value"] for item in params if item["field"] == "model_asst_id")
        matched = []
        for edge in self._edges:
            if edge.get("model_asst_id") != asst:
                continue
            if edge.get(field) in values:
                # Mirror GraphClient return_entity=True shape when requested.
                if return_entity:
                    matched.append(
                        {
                            "edge": edge,
                            "src": {
                                "inst_uuid": edge.get("src_inst_uuid"),
                                "model_id": edge.get("src_model_id"),
                            },
                            "dst": {
                                "inst_uuid": edge.get("dst_inst_uuid"),
                                "model_id": edge.get("dst_model_id"),
                            },
                        }
                    )
                else:
                    matched.append(edge)
        return matched


def test_project_application_hosts_exact_asst_and_direction(monkeypatch):
    edges = [
        {
            "model_asst_id": "application_run_host",
            "src_model_id": "application",
            "dst_model_id": "host",
            "src_inst_uuid": "app-1",
            "dst_inst_uuid": "host-1",
        },
        {
            "model_asst_id": "application_run_host",
            "src_model_id": "application",
            "dst_model_id": "host",
            "src_inst_uuid": "app-1",
            "dst_inst_uuid": "host-1",
        },
        {
            "model_asst_id": "application_run_host",
            "src_model_id": "application",
            "dst_model_id": "mysql",
            "src_inst_uuid": "app-2",
            "dst_inst_uuid": "db-1",
        },
        {
            "model_asst_id": "other_asst",
            "src_model_id": "application",
            "dst_model_id": "host",
            "src_inst_uuid": "app-1",
            "dst_inst_uuid": "host-x",
        },
    ]
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.relations.GraphClient",
        lambda: _FakeGraph(edges),
    )

    mapping, failures = project_application_hosts(["app-1", "app-2"])
    assert mapping["app-1"] == ["host-1"]
    assert mapping["app-2"] == []
    assert failures == {"app-2"}


def test_project_application_systems_contains(monkeypatch):
    edges = [
        {
            "model_asst_id": "system_contains_application",
            "src_model_id": "system",
            "dst_model_id": "application",
            "src_inst_uuid": "sys-1",
            "dst_inst_uuid": "app-1",
        }
    ]
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.relations.GraphClient",
        lambda: _FakeGraph(edges),
    )
    mapping = project_application_systems(["app-1", "app-orphan"])
    assert mapping["app-1"] == ["sys-1"]
    assert mapping["app-orphan"] == []


def test_project_application_systems_fills_model_from_entities(monkeypatch):
    """Stock edges may omit model_id; return_entity src/dst must supply them."""
    edges = [
        {
            "model_asst_id": "system_contains_application",
            "src_inst_uuid": "sys-1",
            "dst_inst_uuid": "app-1",
        }
    ]

    class _EntityGraph(_FakeGraph):
        def query_edge(self, _label, params, return_entity=True):
            field = next(item["field"] for item in params if item["field"] in {"src_inst_uuid", "dst_inst_uuid"})
            values = set(next(item["value"] for item in params if item["field"] == field))
            asst = next(item["value"] for item in params if item["field"] == "model_asst_id")
            matched = []
            for edge in self._edges:
                if edge.get("model_asst_id") != asst or edge.get(field) not in values:
                    continue
                matched.append(
                    {
                        "edge": edge,
                        "src": {"inst_uuid": "sys-1", "model_id": "system"},
                        "dst": {"inst_uuid": "app-1", "model_id": "application"},
                    }
                )
            return matched

    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.relations.GraphClient",
        lambda: _EntityGraph(edges),
    )
    mapping = project_application_systems(["app-1"])
    assert mapping["app-1"] == ["sys-1"]

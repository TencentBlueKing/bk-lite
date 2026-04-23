from types import SimpleNamespace

from apps.job_mgmt.views import target


class _NodeMgmtStub:
    captured_query = None

    def node_list(self, query_data):
        self.__class__.captured_query = query_data
        return {
            "count": 0,
            "nodes": [],
        }


class _CloudRegionQuerySetStub:
    def values(self, *args):
        return []


class _CloudRegionManagerStub:
    def all(self):
        return _CloudRegionQuerySetStub()


class _CloudRegionStub:
    objects = _CloudRegionManagerStub()


def _make_request(current_team="2"):
    return SimpleNamespace(
        query_params={"page": "1", "page_size": "20"},
        COOKIES={"current_team": current_team, "include_children": "1"},
        user=SimpleNamespace(
            username="job_user",
            domain="domain.com",
            is_superuser=False,
            group_list=[1],
        ),
    )


def test_query_nodes_passes_node_permission_scope(monkeypatch):
    monkeypatch.setattr(target, "NodeMgmt", _NodeMgmtStub)
    monkeypatch.setattr(target, "CloudRegion", _CloudRegionStub)

    view = target.TargetViewSet()
    response = view.query_nodes.__wrapped__(view, _make_request())

    assert response.data["result"] is True
    assert _NodeMgmtStub.captured_query["organization_ids"] == []
    assert _NodeMgmtStub.captured_query["permission_data"] == {
        "username": "job_user",
        "domain": "domain.com",
        "current_team": 2,
        "include_children": True,
    }

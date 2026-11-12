"""模型关系 context_link 覆盖接口：两端 OPERATE，非法值归一为 follow。"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.services.model import ModelManage
from apps.cmdb.views.model import ModelViewSet
from apps.core.exceptions.base_app_exception import BaseAppException

VIEWS = "apps.cmdb.views.model"
MODEL_ASST_ID = "application_run_host"


@pytest.fixture
def superuser(authenticated_user):
    user = authenticated_user
    user.is_superuser = True
    user.group_list = [{"id": 1}]
    user.locale = "zh-Hans"
    return user


@pytest.fixture(autouse=True)
def _perm(monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *a, **k: {1: {"permission_instances_map": {}, "inst_names": []}},
    )
    monkeypatch.setattr(f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission", lambda **k: True)
    monkeypatch.setattr(f"{VIEWS}.get_default_group_id", lambda: [1])
    monkeypatch.setattr(f"{VIEWS}.ModelViewSet.organizations", lambda self, r, m: [1])
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "model_name": model_id, "group": [1], "is_visible": True},
    )


def _req(method, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn("/x/", data=data, format="json") if data is not None else fn("/x/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _put(user, data, model_asst_id=MODEL_ASST_ID):
    return ModelViewSet.as_view({"put": "model_association_context_link"})(
        _req("put", user, data=data),
        model_asst_id=model_asst_id,
    )


def _association(model_asst_id=MODEL_ASST_ID):
    return {"_id": 9, "model_asst_id": model_asst_id, "src_model_id": "application", "dst_model_id": "host"}


def _install_graph(monkeypatch, fake_graph):
    scheduled = []
    calls = []
    monkeypatch.setattr(f"{VIEWS}.ModelManage.model_association_info_search", lambda aid: _association(aid))
    monkeypatch.setattr(
        "apps.cmdb.services.ci_context.schedule_ci_context_pending",
        lambda **kwargs: scheduled.append(kwargs),
    )
    real = ModelManage.set_association_context_link

    def _spy(model_asst_id, context_link):
        calls.append((model_asst_id, context_link))
        return real(model_asst_id, context_link)

    monkeypatch.setattr(f"{VIEWS}.ModelManage.set_association_context_link", _spy)

    def _set(edge_id, properties):
        return {"_id": edge_id, "model_asst_id": MODEL_ASST_ID, **properties}

    graph = fake_graph("apps.cmdb.services.model", set_edge_properties=_set)
    return graph, scheduled, calls


@pytest.mark.django_db
@pytest.mark.parametrize("link", ["follow", "include", "exclude"])
def test_put_context_link_calls_service_and_pending(superuser, monkeypatch, fake_graph, link):
    graph, scheduled, calls = _install_graph(monkeypatch, fake_graph)
    response = _put(superuser, {"context_link": link})
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["context_link"] == link
    assert calls == [(MODEL_ASST_ID, link)]
    assert scheduled == [{"model_asst_ids": [MODEL_ASST_ID]}]
    writes = [call for call in graph.calls if call[0] == "set_edge_properties"]
    assert writes[-1][1] == (9, {"context_link": link})


@pytest.mark.django_db
@pytest.mark.parametrize("payload", [{"context_link": "sideways"}, {}])
def test_put_context_link_invalid_becomes_follow(superuser, monkeypatch, fake_graph, payload):
    graph, scheduled, calls = _install_graph(monkeypatch, fake_graph)
    response = _put(superuser, payload)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["context_link"] == "follow"
    assert calls == [(MODEL_ASST_ID, payload.get("context_link"))]
    assert scheduled == [{"model_asst_ids": [MODEL_ASST_ID]}]
    writes = [call for call in graph.calls if call[0] == "set_edge_properties"]
    assert writes[-1][1] == (9, {"context_link": "follow"})


@pytest.mark.django_db
def test_put_context_link_missing_association_404(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.model_association_info_search", lambda aid: {})

    def _boom(*args, **kwargs):
        raise AssertionError("missing association must not write context_link")

    monkeypatch.setattr(f"{VIEWS}.ModelManage.set_association_context_link", _boom)
    response = _put(superuser, {"context_link": "exclude"})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_put_context_link_permission_denied_403(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.model_association_info_search", lambda aid: _association(aid))
    monkeypatch.setattr(f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission", lambda **k: False)

    def _boom(*args, **kwargs):
        raise AssertionError("permission denied must not write context_link")

    monkeypatch.setattr(f"{VIEWS}.ModelManage.set_association_context_link", _boom)
    response = _put(superuser, {"context_link": "exclude"})
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_set_association_context_link_writes_edge_and_schedules(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search",
        lambda aid: {"_id": 9, "model_asst_id": aid},
    )
    scheduled = []
    monkeypatch.setattr(
        "apps.cmdb.services.ci_context.schedule_ci_context_pending",
        lambda **kwargs: scheduled.append(kwargs),
    )

    def _set(edge_id, properties):
        return {"_id": edge_id, **properties}

    graph = fake_graph("apps.cmdb.services.model", set_edge_properties=_set)
    result = ModelManage.set_association_context_link(MODEL_ASST_ID, "exclude")
    assert result["context_link"] == "exclude"
    assert graph.calls[0][1] == (9, {"context_link": "exclude"})
    assert scheduled == [{"model_asst_ids": [MODEL_ASST_ID]}]

    graph.calls.clear()
    scheduled.clear()
    result = ModelManage.set_association_context_link(MODEL_ASST_ID, "nope")
    assert result["context_link"] == "follow"
    assert graph.calls[0][1] == (9, {"context_link": "follow"})
    assert scheduled == [{"model_asst_ids": [MODEL_ASST_ID]}]


def test_context_link_route_is_more_specific_than_delete():
    from django.urls import reverse

    path = reverse("model-model-association-context-link", kwargs={"model_asst_id": MODEL_ASST_ID})
    assert path.endswith(f"/association/{MODEL_ASST_ID}/context_link/")

    from apps.cmdb.urls import router

    patterns = [str(getattr(url, "pattern", url)) for url in router.urls]
    link_at = next(index for index, pattern in enumerate(patterns) if "context_link" in pattern)
    delete_at = next(
        index
        for index, pattern in enumerate(patterns)
        if "association/" in pattern and "context_link" not in pattern and "batch_delete" not in pattern
    )
    assert link_at < delete_at


def test_set_association_context_link_missing_raises(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_info_search", lambda aid: {})
    with pytest.raises(BaseAppException, match="association not found!"):
        ModelManage.set_association_context_link("missing", "exclude")

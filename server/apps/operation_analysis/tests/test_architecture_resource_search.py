import json
import logging
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.logger import SafeLogException
from apps.operation_analysis.services.architecture_resource_search import ArchitectureResourceSearchService
from apps.operation_analysis.views.share_view import DashboardShareAccessViewSet
from apps.operation_analysis.views.view import ArchitectureModelViewSet

SECRET = "super-secret-resource-search"
USER_INFO = {"user": "alice", "team": 1, "domain": "domain.com"}
REQUEST = SimpleNamespace()


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _patch_user(monkeypatch, user_info=None):
    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_resource_search.build_nats_user_info",
        lambda request: user_info or USER_INFO,
    )


def _cmdb(monkeypatch, **methods):
    class _Client:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            def _missing(**kwargs):
                self.calls.append((name, kwargs))
                handler = methods.get(name)
                if handler is None:
                    raise AssertionError(name)
                return handler(**kwargs)

            return _missing

    client = _Client()
    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_resource_search.CMDB",
        lambda: client,
    )
    return client


def _auth(request, *, superuser):
    force_authenticate(
        request,
        user=SimpleNamespace(
            is_authenticated=True,
            is_superuser=superuser,
            username="alice" if superuser else "bob",
            locale="zh",
            permission={} if not superuser else {"view-View": ["*"]},
        ),
    )


def _post(body, *, superuser=True):
    request = APIRequestFactory().post(
        "/operation_analysis/api/architecture/resource_search/",
        body,
        format="json",
    )
    _auth(request, superuser=superuser)
    return ArchitectureModelViewSet.as_view({"post": "resource_search"})(request)


def _hit(**overrides):
    item = {
        "inst_uuid": "u1",
        "inst_name": "web-01",
        "ip_addr": "10.0.0.8",
        "model_id": "host",
        "password": SECRET,
    }
    item.update(overrides)
    return item


def test_models_use_permission_aware_rpc(monkeypatch):
    client = _cmdb(
        monkeypatch,
        search_models_for_llm=lambda **kwargs: [
            {"model_id": "host", "model_name": "主机", "icn": "host"},
        ],
    )
    _patch_user(monkeypatch)
    models = ArchitectureResourceSearchService.list_models(REQUEST)
    assert client.calls[0][0] == "search_models_for_llm"
    assert client.calls[0][1] == {"user_info": USER_INFO}
    assert [name for name, _kwargs in client.calls] == ["search_models_for_llm"]
    assert models[0]["model_id"] == "host"
    assert models[0]["icn"] == "host"


def test_by_type_pages_on_the_server(monkeypatch):
    seen = {}

    def list_instances_for_llm(**kwargs):
        seen.update(kwargs)
        return {"count": 45, "items": [_hit(), {"inst_name": "skip"}]}

    _cmdb(monkeypatch, list_instances_for_llm=list_instances_for_llm)
    _patch_user(monkeypatch)
    data = ArchitectureResourceSearchService.search(
        REQUEST,
        {"keyword": "  ", "model_id": " host ", "page": 2, "page_size": 30, "case_sensitive": False},
    )
    assert seen == {
        "protocol_version": "2",
        "user_info": USER_INFO,
        "model_id": "host",
        "params": [],
        "page": 2,
        "page_size": 30,
    }
    assert data == {
        "mode": "by-type",
        "hits": [{"inst_uuid": "u1", "inst_name": "web-01", "ip_addr": "10.0.0.8", "model_id": "host"}],
        "total": 45,
        "page": 2,
        "page_size": 30,
    }
    assert SECRET not in json.dumps(data)


def test_by_model_text_pages_on_the_server(monkeypatch):
    seen = {}

    def fulltext_search_by_model(**kwargs):
        seen.update(kwargs)
        return {"total": 8, "data": [_hit(inst_name="db-01", model_id="mysql")], "page": 1}

    _cmdb(monkeypatch, fulltext_search_by_model=fulltext_search_by_model)
    _patch_user(monkeypatch)
    data = ArchitectureResourceSearchService.search(
        REQUEST,
        {"keyword": " db ", "model_id": "mysql", "page": 1, "page_size": 20, "case_sensitive": True},
    )
    assert seen["search"] == "db"
    assert seen["model_id"] == "mysql"
    assert seen["page"] == 1
    assert seen["page_size"] == 20
    assert seen["case_sensitive"] is True
    assert seen["user_info"] == USER_INFO
    assert data["mode"] == "by-model-text"
    assert data["total"] == 8
    assert data["hits"] == [{"inst_uuid": "u1", "inst_name": "db-01", "ip_addr": "10.0.0.8", "model_id": "mysql"}]
    assert SECRET not in json.dumps(data)


def test_fulltext_returns_the_whole_hit_list(monkeypatch):
    def fulltext_search(**kwargs):
        assert kwargs["search"] == "web"
        assert kwargs["case_sensitive"] is False
        assert kwargs["user_info"] == USER_INFO
        assert "page" not in kwargs
        return [_hit(inst_uuid="u1"), _hit(inst_uuid="u2", model_id="mysql", ip_addr="")]

    _cmdb(monkeypatch, fulltext_search=fulltext_search)
    _patch_user(monkeypatch)
    data = ArchitectureResourceSearchService.search(
        REQUEST,
        {"keyword": "web", "model_id": "", "page": 3, "page_size": 20, "case_sensitive": False},
    )
    assert data["mode"] == "fulltext"
    assert data["total"] == 2
    assert [hit["inst_uuid"] for hit in data["hits"]] == ["u1", "u2"]
    assert data["page"] == 3
    assert data["page_size"] == 20
    assert len(data["hits"]) == data["total"]
    assert SECRET not in json.dumps(data)


def test_empty_keyword_and_model_skips_rpc(monkeypatch):
    client = _cmdb(monkeypatch)
    with pytest.raises(ValidationError) as exc:
        ArchitectureResourceSearchService.search(REQUEST, {"keyword": " ", "model_id": "", "page": 1, "page_size": 30})
    assert client.calls == []
    assert "请输入关键词或选择模型" in str(exc.value.detail)


def test_page_size_above_cap_skips_rpc(monkeypatch):
    client = _cmdb(monkeypatch)
    with pytest.raises(ValidationError) as exc:
        ArchitectureResourceSearchService.search(REQUEST, {"keyword": "web", "model_id": "host", "page": 1, "page_size": 101})
    assert client.calls == []
    assert "page_size" in exc.value.detail


def test_page_below_one_skips_rpc(monkeypatch):
    client = _cmdb(monkeypatch)
    with pytest.raises(ValidationError):
        ArchitectureResourceSearchService.search(REQUEST, {"keyword": "web", "page": 0, "page_size": 30})
    assert client.calls == []


def test_rpc_exception_is_a_readable_message(monkeypatch, caplog):
    def fulltext_search(**kwargs):
        raise RuntimeError(f"nats dump {SECRET}")

    _cmdb(monkeypatch, fulltext_search=fulltext_search)
    _patch_user(monkeypatch)
    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(ValidationError) as exc:
            ArchitectureResourceSearchService.search(REQUEST, {"keyword": "web", "page": 1, "page_size": 30})
    assert exc.value.detail["detail"] == "资源搜索失败"
    assert SECRET not in json.dumps(exc.value.detail)
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.msg == "event=architecture_resource_search_failed failed_stage=%s error_type=%s model_id=%s"
    assert record.args == ("fulltext", "RuntimeError", "-")
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[1].__traceback__ is None
    assert record.exc_info[2] is not None
    rendered = f"{record.getMessage()}\n{logging.Formatter().formatException(record.exc_info)}"
    assert SECRET not in rendered


def test_rpc_false_result_does_not_dump_the_body(monkeypatch, caplog):
    def list_instances_for_llm(**kwargs):
        return {"result": False, "message": SECRET, "data": {"password": SECRET}}

    _cmdb(monkeypatch, list_instances_for_llm=list_instances_for_llm)
    _patch_user(monkeypatch)
    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(ValidationError) as exc:
            ArchitectureResourceSearchService.search(REQUEST, {"model_id": "host", "page": 1, "page_size": 100})
    assert exc.value.detail["detail"] == "资源搜索失败"
    assert SECRET not in json.dumps(exc.value.detail)
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.args == ("by-type", "NatsResultFalse", "host")
    assert record.exc_info is None
    assert SECRET not in record.getMessage()


def test_view_returns_models_and_search_and_share_has_neither(monkeypatch):
    monkeypatch.setattr(
        ArchitectureResourceSearchService,
        "list_models",
        staticmethod(lambda request: [{"model_id": "host", "model_name": "主机"}]),
    )
    monkeypatch.setattr(
        ArchitectureResourceSearchService,
        "search",
        staticmethod(
            lambda request, payload: {
                "mode": "by-type",
                "hits": [{"inst_uuid": "u1", "inst_name": "web", "ip_addr": "", "model_id": "host"}],
                "total": 1,
                "page": payload["page"],
                "page_size": payload["page_size"],
            }
        ),
    )
    models_request = APIRequestFactory().get("/operation_analysis/api/architecture/models/")
    _auth(models_request, superuser=True)
    models_response = ArchitectureModelViewSet.as_view({"get": "models"})(models_request)
    models_body = _render(models_response)
    assert models_response.status_code == 200
    assert models_body["result"] is True
    assert models_body["data"][0]["model_id"] == "host"

    search_response = _post({"keyword": "", "model_id": "host", "page": 1, "page_size": 30, "case_sensitive": False})
    search_body = _render(search_response)
    assert search_response.status_code == 200
    assert search_body["result"] is True
    assert search_body["data"]["mode"] == "by-type"
    assert search_body["message"] == "success"
    assert not hasattr(DashboardShareAccessViewSet, "models")
    assert not hasattr(DashboardShareAccessViewSet, "resource_search")


def test_view_rejects_user_without_architecture_permission():
    models_request = APIRequestFactory().get("/operation_analysis/api/architecture/models/")
    _auth(models_request, superuser=False)
    assert ArchitectureModelViewSet.as_view({"get": "models"})(models_request).status_code == 403
    assert _post({"keyword": "web"}, superuser=False).status_code == 403


def test_view_empty_search_is_400_without_rpc(monkeypatch):
    def boom():
        raise AssertionError("rpc")

    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_resource_search.CMDB",
        boom,
    )
    response = _post({"keyword": "", "model_id": "", "page": 1, "page_size": 30})
    body = _render(response)
    assert response.status_code == 400
    assert body["result"] is False
    assert "请输入关键词或选择模型" in body["message"]


def test_view_page_size_cap_is_400(monkeypatch):
    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_resource_search.CMDB",
        lambda: (_ for _ in ()).throw(AssertionError("rpc")),
    )
    response = _post({"keyword": "web", "model_id": "", "page": 1, "page_size": 101})
    assert response.status_code == 400
    body = _render(response)
    assert body["result"] is False
    assert "page_size" in body["message"]

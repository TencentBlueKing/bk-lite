"""opspilot-views2 切片: viewsets/web_page_knowledge_view.WebPageKnowledgeViewSet 真实 DRF + DB 测试。

create_web_page_knowledge action 真实驱动:
- 缺 url / 缺 knowledge_base_id 返回 result False;
- 非超管越权(current_team 不在用户组 / 知识库不含 current_team)抛 403;
- 知识库不存在抛 403(PermissionDenied 包装);
- 正常创建: 落库 KnowledgeDocument(knowledge_source_type=web_page) + WebPageKnowledge,
  并写 OperationLog;
- sync_enabled=True 时真实创建 django_celery_beat PeriodicTask;
- list/retrieve/update/destroy 被 http_method_names 禁用(405)。
仅 KnowledgeDocument.create_new_document 真实落库,无外部 mock。
"""

import pydantic.root_model  # noqa
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.models import KnowledgeBase, KnowledgeDocument, WebPageKnowledge
from apps.opspilot.viewsets.web_page_knowledge_view import WebPageKnowledgeViewSet

pytestmark = pytest.mark.django_db


def _json(resp):
    import json

    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _user(*, superuser=False, groups=None):
    from apps.base.models import User

    u = User.objects.create_user(
        username=f"wp_{'su' if superuser else 'usr'}_{User.objects.count()}",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=groups if groups is not None else [{"id": 1, "name": "T1"}],
    )
    if superuser:
        u.is_superuser = True
        u.save()
    else:
        u.permission = {"opspilot": {"knowledge_document-Add"}}
    return u


def _kb(team=None, name="kb1"):
    return KnowledgeBase.objects.create(name=name, team=team if team is not None else [1])


def _post(user, data, current_team=None):
    factory = APIRequestFactory()
    request = factory.post("/", data=data, format="json")
    force_authenticate(request, user=user)
    if current_team is not None:
        request.COOKIES["current_team"] = str(current_team)
    return WebPageKnowledgeViewSet.as_view({"post": "create_web_page_knowledge"})(request)


class TestValidation:
    def test_缺url返回false(self):
        resp = _post(_user(superuser=True), {"knowledge_base_id": 1, "url": "   "})
        assert _json(resp)["result"] is False

    def test_缺knowledge_base_id返回false(self):
        resp = _post(_user(superuser=True), {"url": "http://example.com"})
        assert _json(resp)["result"] is False


class TestPermission:
    def test_知识库不存在抛403(self):
        resp = _post(_user(superuser=True), {"url": "http://example.com", "knowledge_base_id": 999999})
        assert resp.status_code == 403

    def test_非超管current_team不在用户组抛403(self):
        kb = _kb(team=[1])
        user = _user(groups=[{"id": 1, "name": "T1"}])
        resp = _post(user, {"url": "http://x.com", "knowledge_base_id": kb.id}, current_team=99)
        assert resp.status_code == 403

    def test_非超管知识库不含current_team抛403(self):
        kb = _kb(team=[2])
        user = _user(groups=[{"id": 1, "name": "T1"}])
        resp = _post(user, {"url": "http://x.com", "knowledge_base_id": kb.id}, current_team=1)
        assert resp.status_code == 403


class TestCreate:
    def test_超管正常创建落库并写日志(self):
        from apps.system_mgmt.models import OperationLog

        user = _user(superuser=True)
        kb = _kb()
        before = OperationLog.objects.filter(app="opspilot").count()
        resp = _post(
            user,
            {"url": "  http://example.com/docs  ", "knowledge_base_id": kb.id, "name": "wp-doc"},
        )
        assert resp.status_code == 200
        body = _json(resp)
        assert body["result"] is True
        doc_id = body["data"]
        doc = KnowledgeDocument.objects.get(id=doc_id)
        assert doc.knowledge_source_type == "web_page"
        assert doc.name == "wp-doc"
        # WebPageKnowledge 关联且 url 已 strip
        wp = WebPageKnowledge.objects.get(knowledge_document_id=doc_id)
        assert wp.url == "http://example.com/docs"
        assert wp.max_depth == 1
        assert wp.sync_enabled is False
        # 写了操作日志
        assert OperationLog.objects.filter(app="opspilot").count() == before + 1

    def test_sync_enabled创建周期任务(self):
        from django_celery_beat.models import PeriodicTask

        user = _user(superuser=True)
        kb = _kb()
        resp = _post(
            user,
            {
                "url": "http://example.com/sync",
                "knowledge_base_id": kb.id,
                "name": "wp-sync",
                "sync_enabled": True,
                "sync_time": "03:30",
                "max_depth": 2,
            },
        )
        assert resp.status_code == 200
        doc_id = _json(resp)["data"]
        wp = WebPageKnowledge.objects.get(knowledge_document_id=doc_id)
        assert wp.sync_enabled is True
        assert wp.max_depth == 2
        # 真实创建了 django_celery_beat 周期任务
        task = PeriodicTask.objects.get(name=f"sync_web_page_knowledge_{wp.id}")
        assert task.task == "apps.opspilot.tasks.sync_web_page_knowledge"
        assert task.args == f"[{wp.id}]"
        assert task.crontab.hour == "3"
        assert task.crontab.minute == "30"


class TestDisabledMethods:
    @pytest.mark.parametrize("verb,action", [("get", "list"), ("get", "retrieve")])
    def test_禁用方法返回405(self, verb, action):
        user = _user(superuser=True)
        factory = APIRequestFactory()
        request = getattr(factory, verb)("/")
        force_authenticate(request, user=user)
        view = WebPageKnowledgeViewSet.as_view({verb: action})
        if action == "retrieve":
            resp = view(request, pk=1)
        else:
            resp = view(request)
        assert resp.status_code == 405

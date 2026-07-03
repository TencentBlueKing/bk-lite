"""opspilot-biz 切片: viewsets/qa_pairs_view.QAPairsViewSet 真实 DRF + DB 测试。

通过 APIRequestFactory 真实驱动 DRF 视图、真实 ORM 落库，断言：
- create 内置接口被禁用(405)；
- list 强制 knowledge_base_id、KB 不存在、超管放行、非超管团队/知识库越权(403)、正常分页；
- destroy 在 generating/pending 状态被拦截、正常删除返回 204；
- 序列化器 update 在训练中抛异常、正常更新触发 celery .delay 契约。
仅 mock celery .delay(分布式任务边界)，其余走真实数据库。
"""

import pydantic.root_model  # noqa
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.models import KnowledgeBase, QAPairs
from apps.opspilot.viewsets.qa_pairs_view import QAPairsViewSet

pytestmark = pytest.mark.django_db


def _json(resp):
    """解析 Django JsonResponse / DRF Response 的 JSON body。"""
    import json

    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _user(*, superuser=False, roles=None, groups=None, perm=True):
    from apps.base.models import User

    u = User.objects.create_user(
        username=f"qa_{'su' if superuser else 'usr'}_{User.objects.count()}",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=groups if groups is not None else [{"id": 1, "name": "T1"}],
        roles=roles or [],
    )
    if superuser:
        u.is_superuser = True
        u.save()
    elif perm:
        # 赋予 opspilot 下 knowledge_document-View 权限以通过 @HasPermission，
        # 从而能够进入 list 的团队/知识库权限校验逻辑。
        u.permission = {"opspilot": {"knowledge_document-View"}}
    return u


def _kb(team=None, name="kb1"):
    return KnowledgeBase.objects.create(name=name, team=team if team is not None else [1])


def _qa(kb, name="qa1", status="completed"):
    return QAPairs.objects.create(name=name, knowledge_base=kb, status=status)


def _get(user, query="", current_team=None):
    factory = APIRequestFactory()
    request = factory.get(f"/{query}")
    force_authenticate(request, user=user)
    if current_team is not None:
        request.COOKIES["current_team"] = str(current_team)
    return QAPairsViewSet.as_view({"get": "list"})(request)


class TestCreateDisabled:
    def test_内置create返回405(self):
        factory = APIRequestFactory()
        request = factory.post("/", data={"name": "x"}, format="json")
        force_authenticate(request, user=_user(superuser=True))
        resp = QAPairsViewSet.as_view({"post": "create"})(request)
        assert resp.status_code == 405


class TestList:
    def test_缺少knowledge_base_id返回400(self):
        resp = _get(_user(superuser=True))
        assert resp.status_code == 400
        assert _json(resp)["result"] is False

    def test_知识库不存在返回404(self):
        resp = _get(_user(superuser=True), query="?knowledge_base_id=999999")
        assert resp.status_code == 404
        assert _json(resp)["result"] is False

    def test_超管正常返回数据(self):
        kb = _kb()
        _qa(kb, name="qa-a")
        _qa(kb, name="qa-b")
        resp = _get(_user(superuser=True), query=f"?knowledge_base_id={kb.id}")
        assert resp.status_code == 200
        # 分页响应或自定义 result，二者都应含两条
        body = _json(resp)
        items = body.get("items") or body.get("data") or body.get("results")
        assert len(items) == 2

    def test_非超管current_team不在用户组返回403(self):
        kb = _kb(team=[1])
        _qa(kb)
        user = _user(roles=["knowledge_document-View"], groups=[{"id": 1, "name": "T1"}])
        # current_team=2 不在用户 group(1) 内
        resp = _get(user, query=f"?knowledge_base_id={kb.id}", current_team=2)
        assert resp.status_code == 403

    def test_非超管知识库不含current_team返回403(self):
        kb = _kb(team=[5])  # 知识库属于组 5
        _qa(kb)
        user = _user(roles=["knowledge_document-View"], groups=[{"id": 1, "name": "T1"}])
        resp = _get(user, query=f"?knowledge_base_id={kb.id}", current_team=1)
        assert resp.status_code == 403

    def test_非超管有权访问正常返回(self):
        kb = _kb(team=[1])
        _qa(kb, name="ok")
        user = _user(roles=["knowledge_document-View"], groups=[{"id": 1, "name": "T1"}])
        resp = _get(user, query=f"?knowledge_base_id={kb.id}", current_team=1)
        assert resp.status_code == 200


class TestDestroy:
    def _destroy(self, user, pk, current_team=1):
        factory = APIRequestFactory()
        request = factory.delete("/")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = str(current_team)
        return QAPairsViewSet.as_view({"delete": "destroy"})(request, pk=pk)

    def test_generating状态禁止删除(self, mocker):
        kb = _kb()
        qa = _qa(kb, status="generating")
        mocker.patch("apps.opspilot.viewsets.qa_pairs_view.log_operation")
        resp = self._destroy(_user(superuser=True), qa.id)
        assert _json(resp)["result"] is False
        assert QAPairs.objects.filter(id=qa.id).exists()  # 未删除

    def test_pending状态禁止删除(self, mocker):
        kb = _kb()
        qa = _qa(kb, status="pending")
        mocker.patch("apps.opspilot.viewsets.qa_pairs_view.log_operation")
        resp = self._destroy(_user(superuser=True), qa.id)
        assert _json(resp)["result"] is False

    def test_completed状态正常删除204并记录操作(self, mocker):
        kb = _kb()
        qa = _qa(kb, status="completed")
        log = mocker.patch("apps.opspilot.viewsets.qa_pairs_view.log_operation")
        # 删除会触发 post_delete signal 清理 ES，mock 掉向量后端
        mocker.patch("apps.opspilot.services.knowledge_search_service.KnowledgeSearchService.delete_es_content")
        resp = self._destroy(_user(superuser=True), qa.id)
        assert resp.status_code == 204
        assert not QAPairs.objects.filter(id=qa.id).exists()
        log.assert_called_once()


class TestSerializerUpdate:
    def test_训练中状态update抛异常(self):
        from apps.opspilot.serializers.qa_pairs_serializers import QAPairsSerializer

        kb = _kb()
        qa = _qa(kb, status="generating")
        ser = QAPairsSerializer()
        with pytest.raises(Exception) as exc:
            ser.update(qa, {"name": "new"})
        assert "being trained" in str(exc.value)

    def test_正常update触发celery_delay(self, mocker):
        from apps.opspilot.serializers import qa_pairs_serializers as qps

        kb = _kb()
        qa = _qa(kb, status="completed", name="old")
        delay = mocker.patch.object(qps.create_qa_pairs, "delay")
        ser = qps.QAPairsSerializer()
        updated = ser.update(qa, {"name": "新名字", "only_question": True})
        updated.refresh_from_db()
        assert updated.name == "新名字"
        # 校验 celery 任务调用契约: [id], only_question, True
        delay.assert_called_once_with([qa.id], True, True)

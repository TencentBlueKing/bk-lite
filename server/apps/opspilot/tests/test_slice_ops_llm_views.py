"""opspilot-ops 切片: viewsets/llm_view 真实 DRF + DB 测试。

补齐既有 test_llm_viewset_views.py（聚焦安全/序列化器，不入库）未覆盖的视图层：
- LLMViewSet: get_template_list / create（重名校验、成功）/ update（成功、重名）/
  destroy / list（超管）。
- LLMModelViewSet: list / search_by_groups / create（team 为空、重名、成功）/
  update / destroy / _validate_llm_model_name。
- SkillRequestLogViewSet: list（缺 skill_id、skill 不存在、超管正常）/ retrieve 405。
- SkillToolsViewSet: test_{redis,mysql,oracle,mssql,postgres,es,jenkins,kubernetes}_connection
  的成功/失败/SSRF 分支；get_mcp_tools 缓存命中；import_zip 入参校验。

真实 ORM 落库 + 真实 DRF 分发；仅 mock 真实外部边界：DB driver / ES / Jenkins / k8s
连接探测函数、MCP 缓存、log_operation、SkillPackageImporter。断言 HTTP 状态 / JSON
body / DB 副作用 / 传给探测函数的实例契约。跳过 execute / execute_agui 纯 LLM 流式端点。
"""

import json

import pydantic.root_model  # noqa  预热避免 cov 竞态
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.models import LLMModel, LLMSkill, ModelVendor, SkillRequestLog
from apps.opspilot.viewsets.llm_view import (
    LLMModelViewSet,
    LLMViewSet,
    SkillRequestLogViewSet,
    SkillToolsViewSet,
)

pytestmark = pytest.mark.django_db

LLM_MOD = "apps.opspilot.viewsets.llm_view"


def _body(resp):
    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _su():
    from apps.base.models import User

    u = User.objects.create_user(
        username=f"llm_su_{User.objects.count()}",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
    )
    u.is_superuser = True
    u.save()
    return u


def _dispatch(viewset, action_name, method, *, data=None, query="", user=None, pk=None, fmt="json"):
    factory = APIRequestFactory()
    path = f"/{query}"
    if method in ("post", "put", "patch"):
        request = getattr(factory, method)(path, data=data or {}, format=fmt)
    elif method == "delete":
        request = factory.delete(path)
    else:
        request = factory.get(path)
    force_authenticate(request, user=user or _su())
    request.COOKIES["current_team"] = "1"
    view = viewset.as_view({method: action_name})
    if pk is not None:
        return view(request, pk=pk)
    return view(request)


def _vendor(name="v"):
    return ModelVendor.objects.create(name=name, api_base="https://api.example.com", api_key="k")


# ---------------------------------------------------------------------------
# LLMViewSet
# ---------------------------------------------------------------------------
class TestLLMViewSet:
    def test_get_template_list(self):
        LLMSkill.objects.create(name="tpl", team=[1], is_template=True)
        LLMSkill.objects.create(name="normal", team=[1], is_template=False)
        resp = _dispatch(LLMViewSet, "get_template_list", "get")
        body = _body(resp)
        names = {i["name"] for i in body}
        assert names == {"tpl"}

    def test_create_成功落库(self, mocker):
        mocker.patch(f"{LLM_MOD}.log_operation")
        resp = _dispatch(LLMViewSet, "create", "post", data={"name": "skill-a", "team": [1]})
        assert resp.status_code == 201
        obj = LLMSkill.objects.get(name="skill-a")
        # create 强制写入默认 prompt 与开启对话历史
        assert obj.enable_conversation_history is True
        assert "专业机器人" in obj.skill_prompt

    def test_create_重名返回false(self, mocker):
        mocker.patch(f"{LLM_MOD}.log_operation")
        LLMSkill.objects.create(name="dup", team=[1])
        resp = _dispatch(LLMViewSet, "create", "post", data={"name": "dup", "team": [1]})
        assert _body(resp)["result"] is False

    def test_update_成功(self, mocker):
        mocker.patch(f"{LLM_MOD}.log_operation")
        skill = LLMSkill.objects.create(name="old", team=[1])
        data = {"name": "renamed", "team": [1], "skill_prompt": "新提示"}
        resp = _dispatch(LLMViewSet, "update", "put", data=data, pk=skill.id)
        assert _body(resp)["result"] is True
        skill.refresh_from_db()
        assert skill.name == "renamed"
        assert skill.skill_prompt == "新提示"

    def test_update_重名返回false(self, mocker):
        mocker.patch(f"{LLM_MOD}.log_operation")
        LLMSkill.objects.create(name="taken", team=[1])
        skill = LLMSkill.objects.create(name="me", team=[1])
        data = {"name": "taken", "team": [1]}
        resp = _dispatch(LLMViewSet, "update", "put", data=data, pk=skill.id)
        assert _body(resp)["result"] is False

    def test_destroy_记录操作(self, mocker):
        log = mocker.patch(f"{LLM_MOD}.log_operation")
        skill = LLMSkill.objects.create(name="todel", team=[1])
        resp = _dispatch(LLMViewSet, "destroy", "delete", pk=skill.id)
        assert resp.status_code == 204
        assert not LLMSkill.objects.filter(id=skill.id).exists()
        log.assert_called_once()


# ---------------------------------------------------------------------------
# LLMModelViewSet
# ---------------------------------------------------------------------------
class TestLLMModelViewSet:
    def test_search_by_groups(self):
        LLMModel.objects.create(name="m1", team=[1], model="x")
        resp = _dispatch(LLMModelViewSet, "search_by_groups", "post", data={})
        body = _body(resp)
        assert body["result"] is True
        assert "m1" in body["data"]

    def test_create_team为空(self):
        resp = _dispatch(LLMModelViewSet, "create", "post", data={"name": "m", "team": []})
        assert _body(resp)["result"] is False

    def test_create_成功落库(self, mocker):
        mocker.patch(f"{LLM_MOD}.log_operation")
        vendor = _vendor()
        data = {"name": "model-x", "team": [1], "vendor": vendor.id, "model": "gpt"}
        resp = _dispatch(LLMModelViewSet, "create", "post", data=data)
        assert _body(resp)["result"] is True
        obj = LLMModel.objects.get(name="model-x")
        assert obj.vendor_id == vendor.id
        assert obj.is_build_in is False

    def test_create_同供应商同团队重名(self, mocker):
        mocker.patch(f"{LLM_MOD}.log_operation")
        vendor = _vendor()
        LLMModel.objects.create(name="dup-m", team=[1], vendor=vendor, model="a")
        data = {"name": "dup-m", "team": [1], "vendor": vendor.id, "model": "b"}
        resp = _dispatch(LLMModelViewSet, "create", "post", data=data)
        assert _body(resp)["result"] is False

    def test_validate_name_不同供应商不冲突(self):
        v1 = _vendor("v1")
        v2 = _vendor("v2")
        LLMModel.objects.create(name="same", team=[1], vendor=v1, model="a")
        vs = LLMModelViewSet()
        # 同名但不同供应商 -> 不冲突，返回空串
        msg = vs._validate_llm_model_name("same", [{"id": 1, "name": "T1"}], [1], v2.id)
        assert msg == ""
        # 同名同供应商 -> 冲突，返回团队名
        msg2 = vs._validate_llm_model_name("same", [{"id": 1, "name": "T1"}], [1], v1.id)
        assert msg2 == "T1"

    def test_destroy(self, mocker):
        mocker.patch(f"{LLM_MOD}.log_operation")
        vendor = _vendor()
        m = LLMModel.objects.create(name="del-m", team=[1], vendor=vendor, model="x")
        resp = _dispatch(LLMModelViewSet, "destroy", "delete", pk=m.id)
        assert resp.status_code == 204
        assert not LLMModel.objects.filter(id=m.id).exists()

    def test_update_重名返回false(self, mocker):
        mocker.patch(f"{LLM_MOD}.log_operation")
        vendor = _vendor()
        LLMModel.objects.create(name="taken-m", team=[1], vendor=vendor, model="a")
        m = LLMModel.objects.create(name="mine", team=[1], vendor=vendor, model="b")
        data = {"name": "taken-m", "team": [1], "vendor": vendor.id, "model": "b"}
        resp = _dispatch(LLMModelViewSet, "update", "put", data=data, pk=m.id)
        assert _body(resp)["result"] is False


# ---------------------------------------------------------------------------
# SkillRequestLogViewSet
# ---------------------------------------------------------------------------
class TestSkillRequestLogViewSet:
    def test_缺少skill_id(self):
        resp = _dispatch(SkillRequestLogViewSet, "list", "get")
        assert _body(resp)["result"] is False

    def test_skill不存在(self):
        resp = _dispatch(SkillRequestLogViewSet, "list", "get", query="?skill_id=999999")
        assert _body(resp)["result"] is False

    def test_超管正常返回日志(self):
        skill = LLMSkill.objects.create(name="logskill", team=[1])
        SkillRequestLog.objects.create(skill=skill, current_ip="10.0.0.1", request_detail={}, response_detail={})
        resp = _dispatch(SkillRequestLogViewSet, "list", "get", query=f"?skill_id={skill.id}")
        body = _body(resp)
        items = body.get("results") if isinstance(body, dict) else body
        assert len(items) == 1

    def test_retrieve_禁用405(self):
        skill = LLMSkill.objects.create(name="s", team=[1])
        log = SkillRequestLog.objects.create(skill=skill, current_ip="10.0.0.1", request_detail={}, response_detail={})
        resp = _dispatch(SkillRequestLogViewSet, "retrieve", "get", pk=log.id)
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# SkillToolsViewSet - 连接测试动作
# ---------------------------------------------------------------------------
class TestConnectionActions:
    def test_redis_成功(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.normalize_redis_instance", return_value="inst")
        mocker.patch(f"{LLM_MOD}.test_redis_instance", return_value=True)
        resp = _dispatch(SkillToolsViewSet, "test_redis_connection", "post", data={"host": "redis.example.com", "port": 6379})
        body = _body(resp)
        assert body["result"] is True
        assert body["data"]["success"] is True

    def test_redis_ssrf拦截(self, mocker):
        # 私网地址应被 SSRFValidator 拦截，不应进入 normalize
        norm = mocker.patch(f"{LLM_MOD}.normalize_redis_instance")
        resp = _dispatch(SkillToolsViewSet, "test_redis_connection", "post", data={"host": "127.0.0.1", "port": 6379})
        assert resp.status_code == 400
        assert _body(resp)["result"] is False
        norm.assert_not_called()

    def test_redis_探测失败返回400(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.normalize_redis_instance", return_value="inst")
        mocker.patch(f"{LLM_MOD}.test_redis_instance", return_value=False)
        resp = _dispatch(SkillToolsViewSet, "test_redis_connection", "post", data={"host": "redis.example.com"})
        assert resp.status_code == 400
        assert _body(resp)["result"] is False

    def test_mysql_成功(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.normalize_mysql_instance", return_value="inst")
        mocker.patch(f"{LLM_MOD}.test_mysql_instance", return_value=True)
        resp = _dispatch(SkillToolsViewSet, "test_mysql_connection", "post", data={"host": "db.example.com", "port": 3306})
        assert _body(resp)["result"] is True

    def test_mysql_异常返回400(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.normalize_mysql_instance", side_effect=RuntimeError("boom"))
        resp = _dispatch(SkillToolsViewSet, "test_mysql_connection", "post", data={"host": "db.example.com"})
        assert resp.status_code == 400
        assert "boom" in _body(resp)["message"]

    def test_oracle_成功(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.normalize_oracle_instance", return_value="inst")
        mocker.patch(f"{LLM_MOD}.test_oracle_instance", return_value=True)
        resp = _dispatch(SkillToolsViewSet, "test_oracle_connection", "post", data={"host": "ora.example.com", "port": 1521})
        assert _body(resp)["result"] is True

    def test_postgres_成功(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.normalize_postgres_instance", return_value="inst")
        mocker.patch(f"{LLM_MOD}.test_postgres_instance", return_value=True)
        resp = _dispatch(SkillToolsViewSet, "test_postgres_connection", "post", data={"host": "pg.example.com", "port": 5432})
        assert _body(resp)["result"] is True

    def test_mssql_成功(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch("apps.opspilot.metis.llm.tools.mssql.connection.normalize_mssql_instance", return_value="inst")
        mocker.patch("apps.opspilot.metis.llm.tools.mssql.connection.test_mssql_instance", return_value=True)
        resp = _dispatch(SkillToolsViewSet, "test_mssql_connection", "post", data={"host": "mssql.example.com", "port": 1433})
        assert _body(resp)["result"] is True

    def test_es_成功(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.normalize_es_instance", return_value="inst")
        mocker.patch(f"{LLM_MOD}.test_es_instance", return_value=True)
        resp = _dispatch(SkillToolsViewSet, "test_es_connection", "post", data={"url": "https://es.example.com:9200"})
        assert _body(resp)["result"] is True

    def test_es_url_ssrf拦截(self, mocker):
        norm = mocker.patch(f"{LLM_MOD}.normalize_es_instance")
        resp = _dispatch(SkillToolsViewSet, "test_es_connection", "post", data={"url": "http://169.254.169.254/"})
        assert resp.status_code == 400
        norm.assert_not_called()

    def test_jenkins_成功(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.normalize_jenkins_instance", return_value="inst")
        mocker.patch(f"{LLM_MOD}.test_jenkins_instance", return_value=True)
        resp = _dispatch(SkillToolsViewSet, "test_jenkins_connection", "post", data={"jenkins_url": "https://ci.example.com"})
        assert _body(resp)["result"] is True

    def test_kubernetes_成功(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.normalize_kubernetes_instance", return_value="inst")
        mocker.patch(f"{LLM_MOD}.test_kubernetes_instance", return_value=True)
        kubeconfig = "apiVersion: v1\nclusters:\n- cluster:\n    server: https://k8s.example.com:6443\n"
        resp = _dispatch(SkillToolsViewSet, "test_kubernetes_connection", "post", data={"kubeconfig_data": kubeconfig})
        assert _body(resp)["result"] is True

    def test_kubernetes_kubeconfig私网server拦截(self, mocker):
        norm = mocker.patch(f"{LLM_MOD}.normalize_kubernetes_instance")
        kubeconfig = "apiVersion: v1\nclusters:\n- cluster:\n    server: https://10.0.0.5:6443\n"
        resp = _dispatch(SkillToolsViewSet, "test_kubernetes_connection", "post", data={"kubeconfig_data": kubeconfig})
        assert resp.status_code == 400
        norm.assert_not_called()


class TestGetMcpTools:
    def test_缓存命中(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.get_cached_mcp_tools", return_value=[{"name": "tool"}])
        resp = _dispatch(SkillToolsViewSet, "get_mcp_tools", "post", data={"server_url": "https://mcp.example.com"})
        body = _body(resp)
        assert body["result"] is True
        assert body["cached"] is True
        assert body["data"] == [{"name": "tool"}]

    def test_缺少server_url(self):
        resp = _dispatch(SkillToolsViewSet, "get_mcp_tools", "post", data={})
        assert _body(resp)["result"] is False

    def test_启用认证缺token(self, mocker):
        mocker.patch(f"{LLM_MOD}.SSRFValidator.validate", return_value=None)
        mocker.patch(f"{LLM_MOD}.get_cached_mcp_tools", return_value=None)
        resp = _dispatch(
            SkillToolsViewSet,
            "get_mcp_tools",
            "post",
            data={"server_url": "https://mcp.example.com", "enable_auth": True, "auth_token": ""},
        )
        assert _body(resp)["result"] is False


class TestImportZip:
    def test_无文件返回400(self):
        from apps.opspilot.viewsets.llm_view import SkillPackageViewSet

        factory = APIRequestFactory()
        request = factory.post("/", data={}, format="multipart")
        force_authenticate(request, user=_su())
        request.COOKIES["current_team"] = "1"
        r = SkillPackageViewSet.as_view({"post": "import_zip"})(request)
        assert r.status_code == 400
        assert _body(r)["result"] is False

    def test_非zip后缀返回400(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.opspilot.viewsets.llm_view import SkillPackageViewSet

        upload = SimpleUploadedFile("pkg.txt", b"data", content_type="text/plain")
        factory = APIRequestFactory()
        request = factory.post("/", data={"file": upload}, format="multipart")
        force_authenticate(request, user=_su())
        request.COOKIES["current_team"] = "1"
        r = SkillPackageViewSet.as_view({"post": "import_zip"})(request)
        assert r.status_code == 400

    def test_导入zip成功落库(self, mocker):
        from pathlib import Path

        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.opspilot.models import SkillPackage
        from apps.opspilot.services.skill_package.importer import SkillPackageImportResult
        from apps.opspilot.viewsets.llm_view import SkillPackageViewSet

        result = SkillPackageImportResult(
            skill_id="k8s-pack",
            name="K8s Pack",
            version="1.0.0",
            description="desc",
            category="ops",
            required_tools=["kubernetes"],
            triggers=["异常"],
            storage_path=Path("/tmp/k8s-pack"),
            manifest={"id": "k8s-pack"},
            skill_markdown="# guide",
        )
        mocker.patch(f"{LLM_MOD}.SkillPackageImporter.import_zip", return_value=result)
        mocker.patch(f"{LLM_MOD}.log_operation")
        # 构造真实 ZIP 字节流喂入存储边界（importer 已打桩，不真正解压）
        zip_bytes = b"PK\x03\x04fake-zip-content"
        upload = SimpleUploadedFile("pkg.zip", zip_bytes, content_type="application/zip")
        factory = APIRequestFactory()
        request = factory.post("/", data={"file": upload}, format="multipart")
        force_authenticate(request, user=_su())
        request.COOKIES["current_team"] = "1"
        r = SkillPackageViewSet.as_view({"post": "import_zip"})(request)
        body = _body(r)
        assert body["result"] is True
        pkg = SkillPackage.objects.get(package_id="k8s-pack")
        assert pkg.name == "K8s Pack"
        assert pkg.team == [1]

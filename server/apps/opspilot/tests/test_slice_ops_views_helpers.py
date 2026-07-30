"""opspilot-ops 切片: views.py 纯工具函数 + 统计/校验入口 真实 DB 测试。

覆盖既有 test_views_auth_entrypoints_views.py（聚焦 token 鉴权入口）未覆盖的部分：
- 纯解析/取值工具: parse_json_body / extract_api_token / pick_request_value /
  safe_conversation_window_size / get_loader / _extract_token_usage /
  format_knowledge_sources / set_channel_type_line / _user_team_ids / _bot_in_user_team。
- token 校验: validate_openai_token（无 token / UserAPISecret 命中 / verify_token 兜底）、
  validate_header_token（无 token / bot 不在线 / 鉴权失败 / 成功）、_get_user_locale。
- skill 解析: get_skill_and_params（无 model / skill 不存在 / 消息缺失 / 成功）。
- 统计端点: get_total_token_consumption / get_token_consumption_overview /
  get_conversations_line_data / get_active_users_line_data（含跨团队 bot 作用域拒绝）。

真实 ORM 落库 + 真实 RequestFactory；仅 mock 真实外部边界：SystemMgmt RPC（verify_token /
get_pilot_permission_by_token）。断言真实返回结构 / DB 派生数值 / 越权空集。
"""

import datetime
import json
from types import SimpleNamespace

import pydantic.root_model  # noqa  预热避免 cov 竞态
import pytest
from django.test import RequestFactory

from apps.base.models import UserAPISecret
from apps.opspilot import views
from apps.opspilot.models import Bot, LLMSkill, SkillRequestLog
from apps.system_mgmt.models import User as SysUser

pytestmark = pytest.mark.django_db

VIEWS = "apps.opspilot.views"


def _body(resp):
    return json.loads(resp.content.decode("utf-8"))


# ---------------------------------------------------------------------------
# 纯工具函数（无需 DB）
# ---------------------------------------------------------------------------
class TestPureHelpers:
    def test_parse_json_body_空(self):
        req = RequestFactory().post("/", data=b"", content_type="application/json")
        data, err = views.parse_json_body(req)
        assert data == {} and err is None

    def test_parse_json_body_合法(self):
        req = RequestFactory().post("/", data=json.dumps({"a": 1}), content_type="application/json")
        data, err = views.parse_json_body(req)
        assert data == {"a": 1} and err is None

    def test_parse_json_body_非法(self):
        req = RequestFactory().post("/", data=b"{bad", content_type="application/json")
        data, err = views.parse_json_body(req)
        assert data is None
        assert "Invalid JSON" in err

    def test_extract_api_token_各种格式(self):
        rf = RequestFactory()
        assert views.extract_api_token(rf.get("/")) == ""
        assert views.extract_api_token(rf.get("/", HTTP_AUTHORIZATION="TOKEN abc")) == "abc"
        assert views.extract_api_token(rf.get("/", HTTP_AUTHORIZATION="Bearer xyz")) == "xyz"
        assert views.extract_api_token(rf.get("/", HTTP_AUTHORIZATION="raw")) == "raw"

    def test_pick_request_value(self):
        assert views.pick_request_value({"k": 5}, "k", 0) == 5
        assert views.pick_request_value({"k": None}, "k", 9) == 9
        assert views.pick_request_value({}, "k", 9) == 9

    def test_safe_conversation_window_size(self):
        assert views.safe_conversation_window_size({}, 10) == 10
        assert views.safe_conversation_window_size({"conversation_window_size": 5}, 10) == 5
        assert views.safe_conversation_window_size({"conversation_window_size": "abc"}, 10) == 10
        assert views.safe_conversation_window_size({"conversation_window_size": 0}, 10) == 10

    def test_get_loader_默认与用户locale(self):
        loader = views.get_loader()
        assert loader is not None
        req = RequestFactory().get("/")
        req.user = SysUser(username="u", domain="domain.com", locale="zh-Hans")
        loader2 = views.get_loader(req)
        assert loader2 is not None

    def test_extract_token_usage(self):
        assert views._extract_token_usage(None) == (0, 0, 0)
        assert views._extract_token_usage({"usage": "bad"}) == (0, 0, 0)
        assert views._extract_token_usage({"usage": {"prompt_tokens": 3, "completion_tokens": 4}}) == (3, 4, 7)
        # total_tokens 显式优先
        assert views._extract_token_usage({"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 9}}) == (1, 1, 9)

    def test_format_knowledge_sources(self):
        # RAG 知识库引用已移除,函数现为 no-op 直接返回 content
        skill = LLMSkill(name="s")
        assert views.format_knowledge_sources("hi", skill) == "hi"
        skill2 = LLMSkill(name="s2")
        # json 内容原样返回
        assert views.format_knowledge_sources('{"a":1}', skill2) == '{"a":1}'
        # doc_map / title_map 参数保留(签名兼容)但被忽略
        doc_map = {"k1": {"name": "文档A"}}
        title_map = {"k1": True}
        assert views.format_knowledge_sources("正文", skill2, doc_map, title_map) == "正文"

    def test_set_channel_type_line(self):
        start = datetime.datetime(2026, 1, 1)
        end = datetime.datetime(2026, 1, 2)
        qs = [{"channel_user__channel_type": "web", "date": datetime.date(2026, 1, 1), "count": 3}]
        result = views.set_channel_type_line(end, qs, start)
        assert "web" in result and "total" in result
        web_day0 = {d["time"]: d["count"] for d in result["web"]}
        assert web_day0["2026-01-01"] == 3
        total = {d["time"]: d["count"] for d in result["total"]}
        assert total["2026-01-01"] == 3


# ---------------------------------------------------------------------------
# team 作用域工具（需 DB）
# ---------------------------------------------------------------------------
class TestTeamScope:
    def _req(self, *, superuser=False, groups=None):
        req = RequestFactory().get("/")
        req.user = SimpleNamespace(
            username="u",
            domain="domain.com",
            is_superuser=superuser,
            group_list=groups or [{"id": 1, "name": "T1"}],
        )
        return req

    def test_user_team_ids(self):
        assert views._user_team_ids(self._req(superuser=True)) == set()
        assert views._user_team_ids(self._req(groups=[{"id": 2}, {"id": 3}])) == {2, 3}

    def test_bot_in_user_team(self):
        bot = Bot.objects.create(name="b", team=[2], api_token="t")
        assert views._bot_in_user_team(self._req(groups=[{"id": 2}]), bot.id) is True
        assert views._bot_in_user_team(self._req(groups=[{"id": 9}]), bot.id) is False
        assert views._bot_in_user_team(self._req(superuser=True), bot.id) is True
        assert views._bot_in_user_team(self._req(), 999999) is False


# ---------------------------------------------------------------------------
# token / header 校验
# ---------------------------------------------------------------------------
class TestValidateTokens:
    def test_openai_无token(self):
        ok, payload = views.validate_openai_token("")
        assert ok is False
        assert "content" in payload["choices"][0]["message"]

    def test_openai_secret命中(self):
        UserAPISecret.objects.create(username="alice", domain="domain.com", api_secret="secret-1", team=1)
        SysUser.objects.create(username="alice", domain="domain.com", locale="zh-Hans")
        ok, user = views.validate_openai_token("Bearer secret-1")
        assert ok is True
        assert user.username == "alice"
        assert user.locale == "zh-Hans"

    def test_openai_verify_token兜底(self, mocker):
        client = mocker.patch(f"{VIEWS}.SystemMgmt").return_value
        client.verify_token.return_value = {
            "result": True,
            "data": {"username": "bob", "domain": "domain.com", "locale": "en", "group_list": [{"id": 1}]},
        }
        ok, user = views.validate_openai_token("Bearer unknown-token", team=1)
        assert ok is True
        assert user.username == "bob"
        assert user.team == 1

    def test_openai_verify_token失败(self, mocker):
        client = mocker.patch(f"{VIEWS}.SystemMgmt").return_value
        client.verify_token.return_value = {"result": False}
        ok, payload = views.validate_openai_token("Bearer x", team=1)
        assert ok is False

    def test_header_无token(self):
        ok, payload = views.validate_header_token("", 1)
        assert ok is False

    def test_header_bot不在线(self):
        ok, payload = views.validate_header_token("Bearer t", 999999)
        assert ok is False

    def test_header_成功(self, mocker):
        bot = Bot.objects.create(name="b", team=[1], api_token="x", online=True)
        client = mocker.patch(f"{VIEWS}.SystemMgmt").return_value
        client.get_pilot_permission_by_token.return_value = {"result": True, "data": {"username": "carol"}}
        ok, data = views.validate_header_token("Bearer tok", bot.id)
        assert ok is True
        assert data["username"] == "carol"

    def test_header_鉴权失败(self, mocker):
        bot = Bot.objects.create(name="b2", team=[1], api_token="x", online=True)
        client = mocker.patch(f"{VIEWS}.SystemMgmt").return_value
        client.get_pilot_permission_by_token.return_value = {"result": False}
        ok, payload = views.validate_header_token("Bearer tok", bot.id)
        assert ok is False

    def test_get_user_locale(self):
        SysUser.objects.create(username="dora", domain="domain.com", locale="zh-Hans")
        assert views._get_user_locale("dora", "domain.com") == "zh-Hans"
        assert views._get_user_locale("nobody", "domain.com") == "en"


# ---------------------------------------------------------------------------
# get_skill_and_params
# ---------------------------------------------------------------------------
class TestGetSkillAndParams:
    def test_无model(self):
        skill, params, err = views.get_skill_and_params({}, 1)
        assert skill is None and params is None and err is not None

    def test_skill不存在(self):
        skill, params, err = views.get_skill_and_params({"model": "ghost", "messages": [{"role": "user", "content": "hi"}]}, 1)
        assert err is not None

    def test_消息缺失(self):
        LLMSkill.objects.create(name="sk", team=[1])
        skill, params, err = views.get_skill_and_params({"model": "sk", "messages": []}, 1)
        assert err is not None

    def test_成功(self):
        LLMSkill.objects.create(name="sk2", team=[1], skill_prompt="P", conversation_window_size=5)
        skill, params, err = views.get_skill_and_params(
            {"model": "sk2", "messages": [{"role": "user", "content": "你好"}]}, 1
        )
        assert err is None
        assert skill.name == "sk2"
        assert params["user_message"] == "你好"
        assert params["group"] == 1


# ---------------------------------------------------------------------------
# 统计端点（@HasRole("admin")）
# ---------------------------------------------------------------------------
class TestTokenConsumption:
    def _admin_req(self, query=""):
        req = RequestFactory().get(f"/{query}")
        req.user = SimpleNamespace(username="admin", domain="domain.com", is_superuser=True, group_list=[{"id": 1}])
        return req

    def test_total_token_consumption(self):
        skill = LLMSkill.objects.create(name="ts", team=[1])
        SkillRequestLog.objects.create(
            skill=skill, current_ip="10.0.0.1", state=True,
            request_detail={}, response_detail={"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        )
        resp = views.get_total_token_consumption(self._admin_req())
        body = _body(resp)
        assert body["result"] is True
        assert body["data"]["total_tokens"] == 15
        assert body["data"]["input_tokens"] == 10
        assert body["data"]["output_tokens"] == 5

    def test_overview_按天聚合(self):
        skill = LLMSkill.objects.create(name="tov", team=[1])
        SkillRequestLog.objects.create(
            skill=skill, current_ip="10.0.0.1", state=True,
            request_detail={}, response_detail={"usage": {"total_tokens": 7}},
        )
        resp = views.get_token_consumption_overview(self._admin_req())
        body = _body(resp)
        assert body["result"] is True
        assert isinstance(body["data"]["items"], list)
        assert sum(i["tokens"] for i in body["data"]["items"]) == 7

    def test_bot_跨团队作用域返回空(self, mocker):
        # bot 不属于调用者团队 -> queryset.none()，统计为 0
        skill = LLMSkill.objects.create(name="tsx", team=[1])
        SkillRequestLog.objects.create(
            skill=skill, current_ip="10.0.0.1", state=True,
            request_detail={}, response_detail={"usage": {"total_tokens": 99}},
        )
        bot = Bot.objects.create(name="other", team=[5], api_token="z")
        req = RequestFactory().get(f"/?bot_id={bot.id}")
        req.user = SimpleNamespace(username="u", domain="domain.com", is_superuser=False, roles=["admin"], group_list=[{"id": 1}])
        resp = views.get_total_token_consumption(req)
        assert _body(resp)["data"]["total_tokens"] == 0


class TestLineData:
    def _admin_req(self, query=""):
        req = RequestFactory().get(f"/{query}")
        req.user = SimpleNamespace(username="admin", domain="domain.com", is_superuser=True, group_list=[{"id": 1}])
        return req

    def test_conversations_line_data(self):
        bot = Bot.objects.create(name="lb", team=[1], api_token="t")
        resp = views.get_conversations_line_data(self._admin_req(f"?bot_id={bot.id}"))
        body = _body(resp)
        assert body["result"] is True
        assert "total" in body["data"]

    def test_conversations_跨团队拒绝(self):
        bot = Bot.objects.create(name="lb2", team=[5], api_token="t")
        req = RequestFactory().get(f"/?bot_id={bot.id}")
        req.user = SimpleNamespace(username="u", domain="domain.com", is_superuser=False, roles=["admin"], group_list=[{"id": 1}])
        resp = views.get_conversations_line_data(req)
        body = _body(resp)
        # 非本团队 bot -> 返回空线数据但 result True
        assert body["result"] is True
        assert all(v == [] or all(p["count"] == 0 for p in v) for v in body["data"].values())

    def test_active_users_line_data(self):
        bot = Bot.objects.create(name="au", team=[1], api_token="t")
        resp = views.get_active_users_line_data(self._admin_req(f"?bot_id={bot.id}"))
        body = _body(resp)
        assert body["result"] is True
        assert "total" in body["data"]

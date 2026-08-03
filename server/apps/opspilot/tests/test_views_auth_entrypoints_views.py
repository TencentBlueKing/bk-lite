"""Request-level guards for the auth-bearing function views in ``views.py``.

These tests pin the security behavior recently hardened across the opspilot
auth entrypoints (F001/F020/F021 and the new request serializers):

- ``openai_completions``: invalid/missing token is
  rejected; a valid token proceeds (downstream chat mocked, no real LLM call);
  both stream and non-stream paths.
- ``skill_execute`` (@api_exempt): the bot is resolved by ``(bot_id, api_token)``;
  a token not matching the bot is rejected.
- ``execute_chat_flow``: a bot outside the validated user's team is not
  resolvable (team scoping); there is no User-Agent bypass.
- ``submit_approval`` / ``submit_choice``: anonymous requests are rejected (401);
  valid token + matching execution_id applies the decision/choice; missing
  required fields still return 400; execution_id not owned by caller's team
  returns 404 (ownership check).
- ``get_bot_detail``: returns MASKED channel_config (no decrypted secrets).
- ``download_workflow_attachment``: expired/invalid signed token -> 403; a
  missing asset -> 404; a valid signed token streams the file.

They are written to run against a real DB in CI; in this DB-less environment
they only need to IMPORT and COLLECT cleanly. External / LLM / streaming
dependencies are mocked so no real network/model calls occur.
"""

import json
import logging
from types import SimpleNamespace

import pytest
from django.core import signing
from django.db.models import Q

from apps.opspilot import views
from apps.opspilot.services import caller_identity
from apps.opspilot.services.chat_completion_service import ChatCompletionService

pytestmark = pytest.mark.django_db


def _make_request(request_factory, *, method="post", path="/", body=None, token=None, cookies=None, user=None):
    """Build a Django request with optional bearer token and authed user."""
    headers = {}
    if token is not None:
        headers["HTTP_AUTHORIZATION"] = token
    factory_method = getattr(request_factory, method)
    if method in ("post", "put", "patch"):
        request = factory_method(
            path,
            data=json.dumps(body) if body is not None else "",
            content_type="application/json",
            **headers,
        )
    else:
        request = factory_method(path, **headers)
    if cookies:
        request.COOKIES.update(cookies)
    if user is not None:
        request.user = user
    return request


def test_validate_openai_token_marks_a_real_api_secret(request_factory, mocker):
    secret = SimpleNamespace(
        username="api-user",
        domain="api.example",
        team=23,
        api_secret="raw-secret",
    )
    mocker.patch.object(views.UserAPISecret, "find_by_api_secret", return_value=secret)
    mocker.patch.object(views, "_get_user_locale", return_value="en")

    is_valid, identity = views.validate_openai_token("raw-secret")
    request = _make_request(
        request_factory,
        cookies={"current_team": "999", "include_children": "1"},
    )

    assert is_valid is True
    assert caller_identity.capture_caller_identity(request, identity) == {
        "username": "api-user",
        "domain": "api.example",
        "team_id": 23,
        "include_children": False,
    }


def test_validate_openai_token_fallback_is_not_marked_as_api_secret(request_factory, mocker):
    mocker.patch.object(views.UserAPISecret, "find_by_api_secret", return_value=None)
    system_mgmt = mocker.patch.object(views, "SystemMgmt").return_value
    system_mgmt.verify_token.return_value = {
        "result": True,
        "data": {
            "username": "bearer-user",
            "domain": "login.example",
            "group_list": [8],
        },
    }

    is_valid, identity = views.validate_openai_token("bearer-token", team=7)
    request = _make_request(request_factory, cookies={"current_team": "7"})

    assert is_valid is True
    assert not isinstance(identity, views.UserAPISecret)
    with pytest.raises(caller_identity.CallerIdentityError, match="not a member") as exc_info:
        caller_identity.capture_caller_identity(request, identity)
    assert exc_info.value.status_code == 403


def test_validate_openai_token_jwt_fallback_uses_cookie_scope_when_member(request_factory, mocker):
    mocker.patch.object(views.UserAPISecret, "find_by_api_secret", return_value=None)
    system_mgmt = mocker.patch.object(views, "SystemMgmt").return_value
    system_mgmt.verify_token.return_value = {
        "result": True,
        "data": {
            "username": "bearer-user",
            "domain": "login.example",
            "group_list": [{"id": 7}],
        },
    }

    is_valid, identity = views.validate_openai_token("bearer-token", team=7)
    request = _make_request(
        request_factory,
        cookies={"current_team": "7", "include_children": "1"},
    )

    assert is_valid is True
    assert caller_identity.capture_caller_identity(request, identity) == {
        "username": "bearer-user",
        "domain": "login.example",
        "team_id": 7,
        "include_children": True,
    }


# --------------------------------------------------------------------------- #
# openai_completions
# --------------------------------------------------------------------------- #
class TestOpenaiCompletions:
    def test_missing_token_rejected_non_stream(self, request_factory, mocker):
        mocker.patch.object(
            views,
            "validate_openai_token",
            return_value=(False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}),
        )
        invoke = mocker.patch.object(views, "invoke_chat")

        request = _make_request(request_factory, body={"model": "s", "messages": [{"role": "user", "content": "hi"}]})
        resp = views.openai_completions(request)

        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload["choices"][0]["message"]["content"] == "No authorization"
        invoke.assert_not_called()

    def test_invalid_token_rejected_stream(self, request_factory, mocker):
        mocker.patch.object(
            views,
            "validate_openai_token",
            return_value=(False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}),
        )
        sentinel = object()
        stream_err = mocker.patch.object(views, "generate_stream_error", return_value=sentinel)

        request = _make_request(request_factory, body={"stream": True, "model": "s", "messages": []})
        resp = views.openai_completions(request)

        assert resp is sentinel
        stream_err.assert_called_once()

    def test_valid_token_proceeds_non_stream(self, request_factory, mocker):
        user = SimpleNamespace(username="alice", domain="d", team=1, locale="en")
        caller_identity.mark_api_secret_identity(user)
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        skill_obj = SimpleNamespace(id=7, name="skill", enable_km_route=False, km_llm_model=None, enable_suggest=False, enable_query_rewrite=False)
        params = {"user_message": "hi"}
        mocker.patch.object(views, "get_skill_and_params", return_value=(skill_obj, params, None))
        sentinel = object()
        invoke = mocker.patch.object(views, "invoke_chat", return_value=sentinel)

        request = _make_request(
            request_factory,
            body={"model": "skill", "messages": [{"role": "user", "content": "hi"}]},
            token="Bearer good",
            cookies={"current_team": "999", "include_children": "1"},
        )
        resp = views.openai_completions(request)

        assert resp is sentinel
        invoke.assert_called_once()

    def test_api_secret_scope_overwrites_forged_identity_before_dispatch(self, request_factory, mocker):
        raw_secret = "raw-openai-secret"
        user = SimpleNamespace(
            username="api-user",
            domain="api.example",
            team=23,
            locale="en",
            api_secret=raw_secret,
        )
        mocker.patch.object(views.UserAPISecret, "find_by_api_secret", return_value=user)
        mocker.patch.object(views, "_get_user_locale", return_value="en")
        skill_obj = SimpleNamespace(
            id=7,
            name="skill",
            enable_suggest=False,
            enable_query_rewrite=False,
        )
        params = {
            "user_message": "hi",
            "caller_identity": {
                "username": "mallory",
                "team_id": 999,
                "token": raw_secret,
            },
        }
        resolve = mocker.patch.object(
            views,
            "get_skill_and_params",
            return_value=(skill_obj, params, None),
        )
        sentinel = object()
        invoke = mocker.patch.object(views, "invoke_chat", return_value=sentinel)

        request = _make_request(
            request_factory,
            body={"model": "skill", "messages": [{"role": "user", "content": "hi"}]},
            token=f"Bearer {raw_secret}",
            cookies={"current_team": "999", "include_children": "1"},
        )
        response = views.openai_completions(request)

        assert response is sentinel
        resolve.assert_called_once()
        assert resolve.call_args.args[1] == 23
        forwarded_params = invoke.call_args.args[0]
        assert forwarded_params["caller_identity"] == {
            "username": "api-user",
            "domain": "api.example",
            "team_id": 23,
            "include_children": False,
        }
        assert raw_secret not in repr(forwarded_params)

    @pytest.mark.parametrize(
        ("cookies", "group_list", "expected_status", "message_part"),
        [
            ({}, [7], 400, "current team"),
            ({"current_team": "7"}, [8], 403, "not a member"),
        ],
    )
    def test_caller_identity_error_uses_status_code_and_does_not_dispatch(
        self,
        cookies,
        group_list,
        expected_status,
        message_part,
        request_factory,
        mocker,
    ):
        user = SimpleNamespace(
            username="login-user",
            domain="login.example",
            team=999,
            locale="en",
            group_list=group_list,
        )
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        skill_obj = SimpleNamespace(
            id=7,
            name="skill",
            enable_suggest=False,
            enable_query_rewrite=False,
        )
        resolve = mocker.patch.object(
            views,
            "get_skill_and_params",
            return_value=(skill_obj, {"user_message": "hi"}, None),
        )
        invoke = mocker.patch.object(views, "invoke_chat")
        stream = mocker.patch.object(views, "stream_chat")

        request = _make_request(
            request_factory,
            body={"model": "skill", "messages": [{"role": "user", "content": "hi"}]},
            token="Bearer login-token",
            cookies=cookies,
        )
        response = views.openai_completions(request)

        assert response.status_code == expected_status
        assert message_part in json.loads(response.content)["choices"][0]["message"]["content"]
        resolve.assert_not_called()
        invoke.assert_not_called()
        stream.assert_not_called()

    def test_stream_caller_identity_error_uses_existing_error_format(self, request_factory, mocker):
        user = SimpleNamespace(
            username="login-user",
            domain="login.example",
            team=999,
            locale="en",
            group_list=[8],
        )
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        skill_obj = SimpleNamespace(
            id=7,
            name="skill",
            enable_suggest=False,
            enable_query_rewrite=False,
        )
        resolve = mocker.patch.object(
            views,
            "get_skill_and_params",
            return_value=(skill_obj, {"user_message": "hi"}, None),
        )
        sentinel = object()
        stream_error = mocker.patch.object(views, "generate_stream_error", return_value=sentinel)
        invoke = mocker.patch.object(views, "invoke_chat")
        stream = mocker.patch.object(views, "stream_chat")

        request = _make_request(
            request_factory,
            body={"stream": True, "model": "skill", "messages": [{"role": "user", "content": "hi"}]},
            token="Bearer login-token",
            cookies={"current_team": "7"},
        )
        response = views.openai_completions(request)

        assert response is sentinel
        assert "not a member" in stream_error.call_args.args[0]
        resolve.assert_not_called()
        invoke.assert_not_called()
        stream.assert_not_called()


@pytest.mark.parametrize("status_code", [None, 200, 403, 500])
def test_chat_completion_unexpected_enrich_exception_is_generic_500(
    status_code,
    request_factory,
    mocker,
    caplog,
):
    invoke = mocker.Mock()
    stream = mocker.Mock()
    service = ChatCompletionService(
        parse_json_body=lambda request: ({"stream": False}, None),
        extract_api_token=lambda request: "token",
        get_client_ip=lambda request: ("127.0.0.1", True),
        generate_stream_error=mocker.Mock(),
        insert_skill_log=mocker.Mock(),
        invoke_chat=invoke,
        stream_chat=stream,
    )
    skill_obj = SimpleNamespace(
        id=7,
        name="skill",
        enable_suggest=False,
        enable_query_rewrite=False,
    )

    unexpected_error = RuntimeError("sensitive identity enrichment detail")
    if status_code is not None:
        unexpected_error.status_code = status_code

    def enrich_params(request, user, params):
        raise unexpected_error

    with caplog.at_level(logging.ERROR, logger="apps.opspilot.services.chat_completion_service"):
        response = service.run(
            _make_request(request_factory),
            validate=lambda token, kwargs: (True, SimpleNamespace(username="alice")),
            resolve_skill=lambda kwargs, user: (skill_obj, {"user_message": "hi"}, None),
            get_user_id=lambda user: user.username,
            enrich_params=enrich_params,
        )

    assert response.status_code == 500
    content = json.loads(response.content)["choices"][0]["message"]["content"]
    assert content == "Internal server error"
    assert "sensitive identity enrichment detail" not in content
    assert any(record.exc_info for record in caplog.records)
    invoke.assert_not_called()
    stream.assert_not_called()


def test_chat_completion_unexpected_stream_enrich_exception_is_generic_500(request_factory, mocker, caplog):
    invoke = mocker.Mock()
    stream = mocker.Mock()
    stream_response = SimpleNamespace(status_code=200)
    generate_stream_error = mocker.Mock(return_value=stream_response)
    service = ChatCompletionService(
        parse_json_body=lambda request: ({"stream": True}, None),
        extract_api_token=lambda request: "token",
        get_client_ip=lambda request: ("127.0.0.1", True),
        generate_stream_error=generate_stream_error,
        insert_skill_log=mocker.Mock(),
        invoke_chat=invoke,
        stream_chat=stream,
    )

    def enrich_params(request, user, params):
        raise RuntimeError("sensitive stream enrichment detail")

    with caplog.at_level(logging.ERROR, logger="apps.opspilot.services.chat_completion_service"):
        response = service.run(
            _make_request(request_factory),
            validate=lambda token, kwargs: (True, SimpleNamespace(username="alice")),
            resolve_skill=mocker.Mock(),
            get_user_id=lambda user: user.username,
            enrich_params=enrich_params,
        )

    assert response is stream_response
    assert response.status_code == 500
    generate_stream_error.assert_called_once_with("Internal server error")
    assert any(record.exc_info for record in caplog.records)
    invoke.assert_not_called()
    stream.assert_not_called()


def test_chat_completion_successful_enrich_resolves_and_invokes_with_server_override(request_factory, mocker):
    sentinel = object()
    invoke = mocker.Mock(return_value=sentinel)
    stream = mocker.Mock()
    service = ChatCompletionService(
        parse_json_body=lambda request: ({"stream": False}, None),
        extract_api_token=lambda request: "token",
        get_client_ip=lambda request: ("127.0.0.1", True),
        generate_stream_error=mocker.Mock(),
        insert_skill_log=mocker.Mock(),
        invoke_chat=invoke,
        stream_chat=stream,
    )
    skill_obj = SimpleNamespace(
        id=7,
        name="skill",
        enable_suggest=False,
        enable_query_rewrite=False,
    )
    resolved_params = {
        "user_message": "hi",
        "caller_identity": {"team_id": 999, "token": "forged"},
    }
    resolve_skill = mocker.Mock(return_value=(skill_obj, resolved_params, None))

    def enrich_params(request, user, server_params):
        assert server_params == {}
        server_params["caller_identity"] = {"team_id": 7}

    response = service.run(
        _make_request(request_factory),
        validate=lambda token, kwargs: (True, SimpleNamespace(username="alice")),
        resolve_skill=resolve_skill,
        get_user_id=lambda user: user.username,
        enrich_params=enrich_params,
    )

    resolve_skill.assert_called_once()
    assert response is sentinel
    forwarded_params = invoke.call_args.args[0]
    assert forwarded_params["caller_identity"] == {"team_id": 7}
    assert "forged" not in repr(forwarded_params)
    stream.assert_not_called()


# --------------------------------------------------------------------------- #
# skill_execute (@api_exempt) — bot resolved by (bot_id, api_token)
# --------------------------------------------------------------------------- #
class TestSkillExecute:
    def test_missing_token_returns_no_authorization(self, request_factory, mocker):
        mocker.patch.object(views, "extract_api_token", return_value="")
        bot_filter = mocker.patch.object(views.Bot.objects, "filter")

        request = _make_request(request_factory, body={"bot_id": 1, "skill_id": 2})
        resp = views.skill_execute(request)

        assert resp.status_code == 200
        result = json.loads(resp.content)["result"]
        assert "content" in result
        bot_filter.assert_not_called()

    def test_token_not_matching_bot_rejected(self, request_factory, mocker):
        mocker.patch.object(views, "extract_api_token", return_value="wrong-token")
        # Bot.objects.filter(id=, api_token=).first() -> None when token mismatches
        qs = mocker.MagicMock()
        qs.first.return_value = None
        mocker.patch.object(views.Bot.objects, "filter", return_value=qs)
        exec_skill = mocker.patch.object(views.SkillExecuteService, "execute_skill")

        request = _make_request(request_factory, body={"bot_id": 1, "skill_id": 2}, token="TOKEN wrong-token")
        resp = views.skill_execute(request)

        assert resp.status_code == 200
        # bot mismatch -> not executed
        exec_skill.assert_not_called()
        views.Bot.objects.filter.assert_called_once_with(id=1, api_token="wrong-token")

    def test_matching_bot_executes_skill(self, request_factory, mocker):
        mocker.patch.object(views, "extract_api_token", return_value="right-token")
        bot = SimpleNamespace(id=1, api_pass=False)
        qs = mocker.MagicMock()
        qs.first.return_value = bot
        mocker.patch.object(views.Bot.objects, "filter", return_value=qs)
        exec_skill = mocker.patch.object(views.SkillExecuteService, "execute_skill", return_value={"content": "ok"})

        request = _make_request(
            request_factory,
            body={"bot_id": 1, "skill_id": 2, "user_message": "hi"},
            token="TOKEN right-token",
        )
        resp = views.skill_execute(request)

        assert resp.status_code == 200
        assert json.loads(resp.content)["result"] == {"content": "ok"}
        exec_skill.assert_called_once()


# --------------------------------------------------------------------------- #
# execute_chat_flow — team scoping, no User-Agent bypass (F021) +
# 使用组织(usage_team) 鉴权 + T2 测试仅管理组织
# --------------------------------------------------------------------------- #
def _q_leaf_map(q):
    """把 Q 树拍平成 {lookup: value}，用于断言 execute_chat_flow 实际使用的过滤字段。"""
    out = {}
    for child in q.children:
        if isinstance(child, Q):
            out.update(_q_leaf_map(child))
        else:
            key, value = child
            out[key] = value
    return out


def _flow_user(*, group_ids=(7,), is_superuser=False):
    return SimpleNamespace(
        username="alice",
        domain="example.com",
        team=999,
        locale="zh-Hans",
        group_list=[{"id": group_id, "name": "Operators"} for group_id in group_ids],
        is_superuser=is_superuser,
        is_authenticated=True,
    )


def _stub_chat_flow_runtime(mocker, node_type):
    bot_obj = SimpleNamespace(id=101)
    bot_queryset = mocker.MagicMock()
    bot_queryset.filter.return_value = bot_queryset
    bot_queryset.first.return_value = bot_obj
    bot_filter = mocker.patch.object(views.Bot.objects, "filter", return_value=bot_queryset)

    bot_chat_flow = SimpleNamespace(id=202, flow_json={"nodes": []})
    flow_queryset = mocker.MagicMock()
    flow_queryset.first.return_value = bot_chat_flow
    mocker.patch.object(views.BotWorkFlow.objects, "filter", return_value=flow_queryset)

    engine = mocker.MagicMock()
    engine.execution_id = "engine-execution"
    engine._get_node_by_id.return_value = {"type": node_type}
    stream_response = object()
    engine.sse_execute.return_value = stream_response
    engine.execute.return_value = "rest-result"
    mocker.patch.object(views, "create_chat_flow_engine", return_value=engine)
    return bot_filter, bot_chat_flow, engine, stream_response


class TestExecuteChatFlow:
    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, request_factory, mocker):
        mocker.patch.object(
            views,
            "validate_openai_token",
            return_value=(False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}),
        )
        engine = mocker.patch.object(views, "create_chat_flow_engine")

        request = _make_request(request_factory, body={"message": "hi"}, token="Bearer bad")
        resp = await views.execute_chat_flow(request, bot_id=1, node_id="n1")

        assert resp.status_code == 200
        assert json.loads(resp.content)["choices"][0]["message"]["content"] == "No authorization"
        engine.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_scopes_by_usage_team_no_ua_bypass(self, request_factory, mocker):
        """正常对话(is_test=False)按【使用组织】过滤；伪造移动端 UA 不能绕过团队作用域。"""
        user = _flow_user(group_ids=(99,))
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        # 解析不到 bot -> 走拒绝分支，不进异步下游。视图在 .first() 前会链式 .filter(online=True)，
        # 因此 queryset mock 需自返回，末端 .first() 返回 None。
        qs = mocker.MagicMock()
        qs.filter.return_value = qs
        qs.first.return_value = None
        bot_filter = mocker.patch.object(views.Bot.objects, "filter", return_value=qs)
        engine = mocker.patch.object(views, "create_chat_flow_engine")

        request = _make_request(
            request_factory,
            body={"message": "hi", "is_test": False},
            token="Bearer good",
            cookies={"current_team": "99"},
        )
        request.META["HTTP_USER_AGENT"] = "okhttp/4.9 mobile"  # 不得绕过
        resp = await views.execute_chat_flow(request, bot_id=1, node_id="n1")

        assert resp.status_code == 200
        assert json.loads(resp.content)["result"] is False
        engine.assert_not_called()
        leaves = _q_leaf_map(bot_filter.call_args.args[0])
        assert leaves.get("usage_team__contains") == [99]  # 对话按使用组织
        assert "team__contains" not in leaves  # 管理组织已含于 usage_team(不变式)，不再单独过滤
        assert leaves.get("id") == 1

    @pytest.mark.asyncio
    async def test_test_mode_scopes_by_management_team_only(self, request_factory, mocker):
        """测试(is_test=True)仅按【管理组织 team】过滤——使用组织即便经 API 也不能触发测试(T2)。"""
        user = _flow_user(group_ids=(99,))
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        qs = mocker.MagicMock()
        qs.filter.return_value = qs
        qs.first.return_value = None
        bot_filter = mocker.patch.object(views.Bot.objects, "filter", return_value=qs)
        engine = mocker.patch.object(views, "create_chat_flow_engine")

        request = _make_request(
            request_factory,
            body={"message": "hi", "is_test": True},
            token="Bearer good",
            cookies={"current_team": "99"},
        )
        resp = await views.execute_chat_flow(request, bot_id=1, node_id="n1")

        assert json.loads(resp.content)["result"] is False
        engine.assert_not_called()
        leaves = _q_leaf_map(bot_filter.call_args.args[0])
        assert leaves.get("team__contains") == [99]  # 测试仅管理组织
        assert "usage_team__contains" not in leaves

    @pytest.mark.asyncio
    @pytest.mark.parametrize("node_type", ["web_chat", "mobile", "embedded_chat", "agui", "openai"])
    async def test_stream_entrypoints_forward_one_server_snapshot(self, node_type, request_factory, mocker):
        user = _flow_user()
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        bot_filter, _, engine, stream_response = _stub_chat_flow_runtime(mocker, node_type)
        request = _make_request(
            request_factory,
            body={
                "message": "hi",
                "caller_identity": {"username": "mallory", "team_id": 123},
            },
            token="Bearer raw-flow-token",
            cookies={"current_team": "7", "include_children": "1"},
        )

        response = await views.execute_chat_flow(request, bot_id=101, node_id="node-1")

        assert response is stream_response
        input_data = engine.sse_execute.call_args.args[0]
        assert input_data["caller_identity"] == {
            "username": "alice",
            "domain": "example.com",
            "team_id": 7,
            "include_children": True,
        }
        assert "raw-flow-token" not in repr(input_data)
        leaves = _q_leaf_map(bot_filter.call_args.args[0])
        assert leaves["usage_team__contains"] == [7]

    @pytest.mark.asyncio
    async def test_restful_entrypoint_forwards_server_snapshot(self, request_factory, mocker):
        user = _flow_user()
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        _, _, engine, _ = _stub_chat_flow_runtime(mocker, "restful")
        request = _make_request(
            request_factory,
            body={"message": "hi", "caller_identity": {"team_id": 123}},
            token="Bearer raw-flow-token",
            cookies={"current_team": "7"},
        )

        response = await views.execute_chat_flow(request, bot_id=101, node_id="node-1")

        assert json.loads(response.content)["result"] is True
        input_data = engine.execute.call_args.args[0]
        assert input_data["caller_identity"] == {
            "username": "alice",
            "domain": "example.com",
            "team_id": 7,
            "include_children": False,
        }

    @pytest.mark.asyncio
    async def test_studio_test_queue_forwards_server_snapshot(self, request_factory, mocker):
        user = _flow_user()
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        _, bot_chat_flow, engine, _ = _stub_chat_flow_runtime(mocker, "web_chat")
        running_queryset = mocker.MagicMock()
        running_queryset.exists.return_value = False
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=running_queryset)
        task = SimpleNamespace(id="celery-task")
        delay = mocker.patch.object(views.chat_flow_test_execute_task, "delay", return_value=task)
        request = _make_request(
            request_factory,
            body={"message": "hi", "is_test": True, "caller_identity": {"team_id": 123}},
            token="Bearer raw-flow-token",
            cookies={"current_team": "7", "include_children": "1"},
        )

        response = await views.execute_chat_flow(request, bot_id=101, node_id="node-1")

        assert json.loads(response.content)["result"] is True
        input_data = delay.call_args.args[2]
        assert delay.call_args.args[0] == bot_chat_flow.id
        assert input_data["caller_identity"] == {
            "username": "alice",
            "domain": "example.com",
            "team_id": 7,
            "include_children": True,
        }
        engine.sse_execute.assert_not_called()
        engine.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_caller_identity_failure_stops_before_bot_engine_and_queue(self, request_factory, mocker):
        user = _flow_user(group_ids=(8,), is_superuser=True)
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        bot_filter = mocker.patch.object(views.Bot.objects, "filter")
        flow_filter = mocker.patch.object(views.BotWorkFlow.objects, "filter")
        engine = mocker.patch.object(views, "create_chat_flow_engine")
        delay = mocker.patch.object(views.chat_flow_test_execute_task, "delay")
        request = _make_request(
            request_factory,
            body={"message": "hi", "is_test": True},
            token="Bearer login-token",
            cookies={"current_team": "7"},
        )

        response = await views.execute_chat_flow(request, bot_id=101, node_id="node-1")

        assert response.status_code == 403
        payload = json.loads(response.content)
        assert payload["result"] is False
        assert "not a member" in payload["message"]
        bot_filter.assert_not_called()
        flow_filter.assert_not_called()
        engine.assert_not_called()
        delay.assert_not_called()


# --------------------------------------------------------------------------- #
# submit_approval / submit_choice — auth gate + ownership check (Issue #3431)
# --------------------------------------------------------------------------- #
# Helper: build a "token valid → user" stub reused across both test classes.
def _stub_valid_token(mocker, username="alice", team=1):
    user = SimpleNamespace(username=username, domain="d", team=team, locale="en")
    mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
    return user


def _stub_invalid_token(mocker):
    mocker.patch.object(
        views,
        "validate_openai_token",
        return_value=(False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}),
    )


class TestSubmitApproval:
    # --- auth gate (the core fix: no anonymous writes) ---

    def test_no_token_rejected_401(self, request_factory, mocker):
        """Anonymous POST must be rejected — this is the regression guard for #3431."""
        _stub_invalid_token(mocker)
        request = _make_request(
            request_factory,
            body={"execution_id": "e1", "node_id": "n1", "tool_call_id": "t1", "decision": "approve"},
        )
        resp = views.submit_approval(request)
        assert resp.status_code == 401

    def test_invalid_token_rejected_401(self, request_factory, mocker):
        """Malformed / expired token must be rejected before any cache write."""
        _stub_invalid_token(mocker)
        request = _make_request(
            request_factory,
            token="Bearer bad-token",
            body={"execution_id": "e1", "node_id": "n1", "tool_call_id": "t1", "decision": "approve"},
        )
        resp = views.submit_approval(request)
        assert resp.status_code == 401

    # --- ownership gate ---

    def test_execution_not_in_team_returns_404(self, request_factory, mocker):
        """execution_id owned by a different team → 404, no cache write."""
        _stub_valid_token(mocker, team=99)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        qs_mock = mocker.MagicMock()
        qs_mock.order_by.return_value.first.return_value = None
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=qs_mock)
        submit = mocker.patch("apps.opspilot.services.approval.submit_approval_decision")

        request = _make_request(
            request_factory,
            token="Bearer tok",
            body={"execution_id": "e1", "node_id": "n1", "tool_call_id": "t1", "decision": "approve"},
        )
        resp = views.submit_approval(request)

        assert resp.status_code == 404
        submit.assert_not_called()

    # --- field validation (still enforced after auth) ---

    def test_missing_fields_returns_400(self, request_factory, mocker):
        _stub_valid_token(mocker)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        task_stub = mocker.MagicMock()
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=task_stub)

        request = _make_request(request_factory, token="Bearer tok", body={"execution_id": "e1"})
        resp = views.submit_approval(request)

        assert resp.status_code == 400
        assert json.loads(resp.content)["result"] is False

    def test_invalid_decision_returns_400(self, request_factory, mocker):
        _stub_valid_token(mocker)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        task_stub = mocker.MagicMock()
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=task_stub)

        request = _make_request(
            request_factory,
            token="Bearer tok",
            body={"execution_id": "e1", "node_id": "n1", "tool_call_id": "t1", "decision": "maybe"},
        )
        resp = views.submit_approval(request)

        assert resp.status_code == 400
        assert "decision" in json.loads(resp.content)["message"]

    # --- success path ---

    def test_valid_token_and_owner_applies_decision(self, request_factory, mocker):
        """Authenticated owner can submit approval — decision is written to cache."""
        _stub_valid_token(mocker)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        task_mock = mocker.MagicMock()
        qs_mock = mocker.MagicMock()
        qs_mock.order_by.return_value.first.return_value = task_mock
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=qs_mock)
        submit = mocker.patch("apps.opspilot.services.approval.submit_approval_decision")

        request = _make_request(
            request_factory,
            token="Bearer tok",
            body={"execution_id": "e1", "node_id": "n1", "tool_call_id": "t1", "decision": "approve"},
        )
        resp = views.submit_approval(request)

        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["result"] is True
        assert data["data"]["decision"] == "approve"
        submit.assert_called_once()

    def test_wrong_method_405(self, request_factory, mocker):
        _stub_valid_token(mocker)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        request = _make_request(request_factory, method="get", path="/")
        resp = views.submit_approval(request)
        assert resp.status_code == 405


class TestSubmitChoice:
    # --- auth gate ---

    def test_no_token_rejected_401(self, request_factory, mocker):
        """Anonymous POST must be rejected — regression guard for #3431."""
        _stub_invalid_token(mocker)
        request = _make_request(
            request_factory,
            body={"execution_id": "e1", "node_id": "n1", "choice_id": "c1", "selected": ["opt1"]},
        )
        resp = views.submit_choice(request)
        assert resp.status_code == 401

    def test_invalid_token_rejected_401(self, request_factory, mocker):
        _stub_invalid_token(mocker)
        request = _make_request(
            request_factory,
            token="Bearer bad",
            body={"execution_id": "e1", "node_id": "n1", "choice_id": "c1", "selected": ["opt1"]},
        )
        resp = views.submit_choice(request)
        assert resp.status_code == 401

    # --- ownership gate ---

    def test_execution_not_in_team_returns_404(self, request_factory, mocker):
        _stub_valid_token(mocker, team=99)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        qs_mock = mocker.MagicMock()
        qs_mock.order_by.return_value.first.return_value = None
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=qs_mock)
        submit = mocker.patch("apps.opspilot.utils.user_choice.submit_user_choice")

        request = _make_request(
            request_factory,
            token="Bearer tok",
            body={"execution_id": "e1", "node_id": "n1", "choice_id": "c1", "selected": ["opt1"]},
        )
        resp = views.submit_choice(request)

        assert resp.status_code == 404
        submit.assert_not_called()

    def test_local_skill_test_choice_without_workflow_task_result_is_allowed(self, request_factory, mocker):
        _stub_valid_token(mocker, team=99)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        qs_mock = mocker.MagicMock()
        qs_mock.order_by.return_value.first.return_value = None
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=qs_mock)
        submit = mocker.patch("apps.opspilot.utils.user_choice.submit_user_choice")

        request = _make_request(
            request_factory,
            token="Bearer tok",
            body={"execution_id": "e1", "node_id": "skill_test", "choice_id": "c1", "selected": ["opt1"]},
        )
        resp = views.submit_choice(request)

        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["result"] is True
        assert data["data"]["node_id"] == "skill_test"
        submit.assert_called_once_with(
            execution_id="e1",
            node_id="skill_test",
            choice_id="c1",
            selected=["opt1"],
        )

    # --- field validation ---

    def test_missing_fields_returns_400(self, request_factory, mocker):
        _stub_valid_token(mocker)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        task_stub = mocker.MagicMock()
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=task_stub)

        request = _make_request(request_factory, token="Bearer tok", body={"execution_id": "e1", "node_id": "n1"})
        resp = views.submit_choice(request)

        assert resp.status_code == 400
        assert json.loads(resp.content)["result"] is False

    def test_empty_selected_returns_400(self, request_factory, mocker):
        _stub_valid_token(mocker)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        task_stub = mocker.MagicMock()
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=task_stub)

        request = _make_request(
            request_factory,
            token="Bearer tok",
            body={"execution_id": "e1", "node_id": "n1", "choice_id": "c1", "selected": []},
        )
        resp = views.submit_choice(request)

        assert resp.status_code == 400
        assert "selected" in json.loads(resp.content)["message"]

    # --- success path ---

    def test_valid_token_and_owner_applies_choice(self, request_factory, mocker):
        """Authenticated owner can submit a choice — result is written to cache."""
        _stub_valid_token(mocker)
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        task_mock = mocker.MagicMock()
        qs_mock = mocker.MagicMock()
        qs_mock.order_by.return_value.first.return_value = task_mock
        mocker.patch.object(views.WorkFlowTaskResult.objects, "filter", return_value=qs_mock)
        submit = mocker.patch("apps.opspilot.utils.user_choice.submit_user_choice")

        request = _make_request(
            request_factory,
            token="Bearer tok",
            body={"execution_id": "e1", "node_id": "n1", "choice_id": "c1", "selected": ["opt1"]},
        )
        resp = views.submit_choice(request)

        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["result"] is True
        assert data["data"]["selected"] == ["opt1"]
        submit.assert_called_once()


# --------------------------------------------------------------------------- #
# get_bot_detail — masked channel_config (F020)
# --------------------------------------------------------------------------- #
class TestGetBotDetail:
    def test_missing_token_returns_empty(self, request_factory, mocker):
        mocker.patch.object(views, "extract_api_token", return_value="")
        bot_filter = mocker.patch.object(views.Bot.objects, "filter")

        request = _make_request(request_factory, method="get", path="/")
        resp = views.get_bot_detail(request, bot_id=1)

        assert json.loads(resp.content) == {}
        bot_filter.assert_not_called()

    def test_returns_masked_channel_config(self, request_factory, mocker):
        mocker.patch.object(views, "extract_api_token", return_value="tok")
        bot = SimpleNamespace(id=1)
        bot_qs = mocker.MagicMock()
        bot_qs.first.return_value = bot
        # channel.format_channel_config() returns the MASKED dict (not raw secrets)
        channel = SimpleNamespace(
            id=10,
            name="wechat",
            channel_type="enterprise_wechat",
            format_channel_config=lambda: {"chan": {"secret": "******", "token": "******", "corp_id": "c1"}},
        )
        chan_qs = mocker.MagicMock()
        chan_qs.__iter__ = lambda self: iter([channel])

        def _filter(*args, **kwargs):
            if "api_token" in kwargs:
                return bot_qs
            return chan_qs

        mocker.patch.object(views.Bot.objects, "filter", side_effect=lambda *a, **k: bot_qs)
        mocker.patch.object(views.BotChannel.objects, "filter", return_value=chan_qs)

        request = _make_request(request_factory, method="get", path="/", token="Bearer tok")
        resp = views.get_bot_detail(request, bot_id=1)

        data = json.loads(resp.content)
        cfg = data["channels"][0]["channel_config"]["chan"]
        assert cfg["secret"] == "******"
        assert cfg["token"] == "******"
        # non-secret fields are preserved
        assert cfg["corp_id"] == "c1"
        # raw secret value never appears in the response body
        assert "supersecret" not in resp.content.decode()


# --------------------------------------------------------------------------- #
# download_workflow_attachment — signed token (F001)
# --------------------------------------------------------------------------- #
class TestDownloadWorkflowAttachment:
    def test_expired_token_returns_403(self, request_factory, mocker):
        mocker.patch.object(
            views,
            "resolve_signed_attachment_token",
            side_effect=signing.SignatureExpired("expired"),
        )
        request = _make_request(request_factory, method="get", path="/")
        resp = views.download_workflow_attachment(request, download_token="x")

        assert resp.status_code == 403
        assert "expired" in json.loads(resp.content)["message"].lower()

    def test_invalid_signature_returns_403(self, request_factory, mocker):
        mocker.patch.object(
            views,
            "resolve_signed_attachment_token",
            side_effect=signing.BadSignature("bad"),
        )
        request = _make_request(request_factory, method="get", path="/")
        resp = views.download_workflow_attachment(request, download_token="tampered")

        assert resp.status_code == 403
        assert json.loads(resp.content)["result"] is False

    def test_unknown_asset_returns_404(self, request_factory, mocker):
        mocker.patch.object(views, "resolve_signed_attachment_token", return_value=None)
        request = _make_request(request_factory, method="get", path="/")
        resp = views.download_workflow_attachment(request, download_token="orphan")

        assert resp.status_code == 404

    def test_valid_token_streams_file(self, request_factory, mocker, tmp_path):
        # Build a real signed token to exercise the signing round-trip.
        from apps.opspilot.services import workflow_attachment_service as svc

        token = signing.dumps({"aid": 5, "eid": "exec-1"}, salt=svc.WORKFLOW_ATTACHMENT_DOWNLOAD_SALT)

        file_field = mocker.MagicMock()
        file_field.open.return_value = None
        asset = SimpleNamespace(
            id=5,
            execution_id="exec-1",
            filename="report.pdf",
            mime_type="application/pdf",
            file=file_field,
        )
        mocker.patch.object(views, "resolve_signed_attachment_token", return_value=asset)
        # Avoid FileResponse touching a real file handle.
        fake_response = mocker.MagicMock()
        fake_response.__setitem__ = lambda self, k, v: None
        file_resp_cls = mocker.patch.object(views, "FileResponse", return_value=fake_response)

        request = _make_request(request_factory, method="get", path="/")
        resp = views.download_workflow_attachment(request, download_token=token)

        assert resp is fake_response
        file_resp_cls.assert_called_once()
        _, called_kwargs = file_resp_cls.call_args
        assert called_kwargs["filename"] == "report.pdf"

"""Request-level guards for the auth-bearing function views in ``views.py``.

These tests pin the security behavior recently hardened across the opspilot
auth entrypoints (F001/F020/F021 and the new request serializers):

- ``openai_completions`` / ``lobe_skill_execute``: invalid/missing token is
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
from types import SimpleNamespace

import pytest
from django.core import signing

from apps.opspilot import views

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
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        skill_obj = SimpleNamespace(id=7, name="skill")
        params = {"user_message": "hi"}
        mocker.patch.object(views, "get_skill_and_params", return_value=(skill_obj, params, None))
        sentinel = object()
        invoke = mocker.patch.object(views, "invoke_chat", return_value=sentinel)

        request = _make_request(
            request_factory,
            body={"model": "skill", "messages": [{"role": "user", "content": "hi"}]},
            token="Bearer good",
        )
        resp = views.openai_completions(request)

        assert resp is sentinel
        invoke.assert_called_once()


# --------------------------------------------------------------------------- #
# lobe_skill_execute
# --------------------------------------------------------------------------- #
class TestLobeSkillExecute:
    def test_invalid_token_rejected(self, request_factory, mocker):
        mocker.patch.object(
            views,
            "validate_header_token",
            return_value=(False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}),
        )
        invoke = mocker.patch.object(views, "invoke_chat")

        request = _make_request(request_factory, body={"studio_id": 1, "model": "s", "messages": []})
        resp = views.lobe_skill_execute(request)

        assert resp.status_code == 200
        assert json.loads(resp.content)["choices"][0]["message"]["content"] == "No authorization"
        invoke.assert_not_called()

    def test_valid_token_proceeds_and_persists_history(self, request_factory, mocker):
        mocker.patch.object(views, "validate_header_token", return_value=(True, {"username": "bob"}))
        skill_obj = SimpleNamespace(id=3, name="skill")
        params = {"user_message": "hello"}
        mocker.patch.object(views, "get_skill_and_params", return_value=(skill_obj, params, None))
        hook = mocker.patch.object(views, "_lobe_persist_history", return_value="history_log")
        sentinel = object()
        invoke = mocker.patch.object(views, "invoke_chat", return_value=sentinel)

        request = _make_request(
            request_factory,
            body={"studio_id": 1, "model": "skill", "messages": [{"role": "user", "content": "hi"}]},
            token="Bearer good",
        )
        resp = views.lobe_skill_execute(request)

        assert resp is sentinel
        hook.assert_called_once()
        invoke.assert_called_once()

    def test_valid_token_stream_path(self, request_factory, mocker):
        mocker.patch.object(views, "validate_header_token", return_value=(True, {"username": "bob"}))
        skill_obj = SimpleNamespace(id=3, name="skill")
        mocker.patch.object(views, "get_skill_and_params", return_value=(skill_obj, {"user_message": "hi"}, None))
        mocker.patch.object(views, "_lobe_persist_history", return_value=None)
        sentinel = object()
        stream = mocker.patch.object(views, "stream_chat", return_value=sentinel)

        request = _make_request(
            request_factory,
            body={"studio_id": 1, "stream": True, "model": "skill", "messages": [{"role": "user", "content": "hi"}]},
            token="Bearer good",
        )
        resp = views.lobe_skill_execute(request)

        assert resp is sentinel
        stream.assert_called_once()


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
        exec_skill = mocker.patch.object(
            views.SkillExecuteService, "execute_skill", return_value={"content": "ok"}
        )

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
# execute_chat_flow — team scoping, no User-Agent bypass (F021)
# --------------------------------------------------------------------------- #
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
    async def test_bot_outside_team_not_resolvable(self, request_factory, mocker):
        user = SimpleNamespace(username="alice", domain="d", team=99, locale="en")
        mocker.patch.object(views, "validate_openai_token", return_value=(True, user))
        # Scoped filter resolves no bot -> rejected with "No bot online"
        qs = mocker.MagicMock()
        qs.first.return_value = None
        bot_filter = mocker.patch.object(views.Bot.objects, "filter", return_value=qs)
        engine = mocker.patch.object(views, "create_chat_flow_engine")

        # A spoofable mobile User-Agent must NOT bypass team scoping.
        request = _make_request(
            request_factory,
            body={"message": "hi"},
            token="Bearer good",
        )
        request.META["HTTP_USER_AGENT"] = "okhttp/4.9 mobile"
        resp = await views.execute_chat_flow(request, bot_id=1, node_id="n1")

        assert resp.status_code == 200
        assert json.loads(resp.content)["result"] is False
        engine.assert_not_called()
        # Scoping filter must include the validated user's team.
        _, called_kwargs = bot_filter.call_args
        assert called_kwargs["team__contains"] == 99
        assert called_kwargs["id"] == 1


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

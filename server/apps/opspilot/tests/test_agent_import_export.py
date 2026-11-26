"""智能体导入导出：按钮调用的导出与导入动作。"""

import io
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot.models import LLMModel, LLMSkill, MemorySpace, SkillChannel, SkillConversation, SkillPackage, SkillTools, WikiKnowledgeBase
from apps.opspilot.models.bot_mgmt import Bot
from apps.opspilot.services import agent_transfer
from apps.opspilot.services.skill_package.importer import DEFAULT_SKILL_PACKAGE_ROOT
from apps.opspilot.viewsets.llm_view import LLMViewSet

pytestmark = pytest.mark.django_db


def _body(resp):
    if hasattr(resp, "data") and resp.data is not None:
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _user(*, superuser=False, permissions=None, groups=None, domain="domain.com"):
    user = User.objects.create_user(
        username=f"agent_xfer_{User.objects.count()}",
        password="x",
        domain=domain,
        locale="en",
        group_list=groups if groups is not None else [{"id": 1, "name": "T1"}],
    )
    user.is_superuser = superuser
    user.save()
    if not superuser:
        user.permission = {"opspilot": set(permissions or [])}
    return user


def _export(pk, user, *, cookie="1"):
    factory = APIRequestFactory()
    request = factory.get("/")
    force_authenticate(request, user=user)
    if cookie is not None:
        request.COOKIES["current_team"] = cookie
    return LLMViewSet.as_view({"get": "export_agent"})(request, pk=pk)


def _import(payload, user, *, cookie="1", upload=None):
    factory = APIRequestFactory()
    if upload is None:
        upload = SimpleUploadedFile("agent.zip", payload, content_type="application/zip")
        request = factory.post("/", {"file": upload}, format="multipart")
    else:
        request = factory.post("/")
        request.FILES["file"] = upload
    force_authenticate(request, user=user)
    if cookie is not None:
        request.COOKIES["current_team"] = cookie
    return LLMViewSet.as_view({"post": "import_agent"})(request)


def _zip_text(blob: bytes) -> str:
    chunks = []
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for name in archive.namelist():
            data = archive.read(name)
            if name.endswith(".zip"):
                chunks.append(_zip_text(data))
            else:
                chunks.append(data.decode("utf-8", errors="ignore"))
    return "\n".join(chunks)


def _agent_zip(document, blobs=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("agent.json", json.dumps(document, ensure_ascii=False))
        for index, blob in enumerate(blobs or []):
            archive.writestr(f"packages/{index}.zip", blob)
    return buffer.getvalue()


def _recipe(**overrides):
    document = {
        "kind": "opspilot-agent",
        "format_version": 1,
        "name": "助手",
        "introduction": "INTRO-KEEP",
        "skill_prompt": "PROMPT-KEEP",
        "guide": "GUIDE-KEEP",
        "skill_params": [{"key": "city", "type": "text", "value": "TEXT-KEEP"}],
        "conversation_window_size": 7,
        "run_model_call_limit": 4,
        "builtin_tools": [],
        "builtin_packages": [],
        "packages": [],
        "omitted_packages": [],
        "mcp": [],
    }
    document.update(overrides)
    return document


def _skill_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "inspect/SKILL.md",
            "---\nname: 巡检\nversion: 1.2.0\nrequired_tools:\n  - no-such-tool\n---\n# 巡检\nPACKAGE-BODY-SENTINEL\n",
        )
    return buffer.getvalue()


def _counts():
    return (LLMSkill.objects.count(), SkillTools.objects.count(), SkillPackage.objects.count())


def test_export_keeps_recipe_and_drops_secrets():
    user = _user(superuser=True)
    model = LLMModel.objects.create(name="MODEL-SENTINEL-NAME", team=[1])
    builtin_tool = SkillTools.objects.create(name="kubernetes", description="", is_build_in=True, params={})
    mcp = SkillTools.objects.create(
        name="ticket",
        description="DESC-KEEP",
        user_tags=["搜索", " 123 ", "搜索", ""],
        is_build_in=False,
        params={
            "url": "https://mcp.example/tools",
            "transport": "streamable_http",
            "enable_auth": True,
            "auth_token": "TOKEN-SENTINEL",
            "kwargs": [
                {"key": "aaa", "type": "text", "isRequired": False, "value": "KWARG-VALUE-SENTINEL"},
                {"key": "bbb", "type": "password", "isRequired": True, "value": "KWARG-SECRET-SENTINEL"},
            ],
        },
    )
    package_bytes = _skill_zip()
    storage = DEFAULT_SKILL_PACKAGE_ROOT / "export-src" / uuid.uuid4().hex / "1.2.0"
    storage.mkdir(parents=True)
    (storage / "original.zip").write_bytes(package_bytes)
    builtin_package = SkillPackage.objects.create(
        package_id="ppt-master",
        name="PPT",
        version="1.0.0",
        is_build_in=True,
        domain="domain.com",
    )
    custom_package = SkillPackage.objects.create(
        package_id="old-package",
        name="巡检",
        version="1.2.0",
        is_build_in=False,
        storage_path=str(storage),
        domain="domain.com",
    )
    omitted = SkillPackage.objects.create(
        package_id="conversation-package",
        name="对话技能",
        version="0.1.0",
        is_build_in=False,
        storage_path="",
        domain="domain.com",
    )
    skill = LLMSkill.objects.create(
        name="助手",
        introduction="INTRO-KEEP",
        skill_prompt="PROMPT-KEEP",
        guide="GUIDE-KEEP",
        skill_params=[
            {"key": "city", "type": "text", "value": "TEXT-KEEP"},
            {"key": "api_token", "type": "password", "value": "PASSWORD-SENTINEL"},
        ],
        conversation_window_size=7,
        run_model_call_limit=4,
        enable_conversation_history=False,
        temperature=0.1,
        force_wiki_grounded=True,
        team=[99],
        usage_team=[99],
        llm_model=model,
        tools=[
            {"id": builtin_tool.id, "name": builtin_tool.name, "kwargs": {"password": "KWARGS-SENTINEL"}},
            {"id": mcp.id, "name": mcp.name, "kwargs": {"auth_token": "TOKEN-SENTINEL"}},
        ],
        skill_packages=[
            {"id": builtin_package.id, "package_id": builtin_package.package_id, "name": builtin_package.name, "version": "1.0.0"},
            {"id": custom_package.id, "package_id": custom_package.package_id, "name": "巡检", "version": "1.2.0"},
            {"id": omitted.id, "package_id": omitted.package_id, "name": "对话技能", "version": "0.1.0"},
        ],
        skill_package_params={"old-package": [{"key": "host", "value": "PACKAGE-PARAM-SENTINEL"}]},
        domain="domain.com",
    )
    wiki = WikiKnowledgeBase.objects.create(name="WIKI-SENTINEL", team=[1])
    skill.wiki_knowledge_bases.add(wiki)
    memory = MemorySpace.objects.create(name="MEMORY-SENTINEL", team=[1])
    skill.memory_space = memory
    skill.save(update_fields=["memory_space"])
    channel = SkillChannel.objects.create(skill=skill, name="CHANNEL-SENTINEL", channel_type="web_chat")
    SkillConversation.objects.create(skill=skill, channel=channel, session_id=uuid.uuid4().hex, title="HISTORY-SENTINEL")
    bench = Bot.objects.create(name="BENCH-SENTINEL", team=[1], api_token="BENCH-TOKEN-SENTINEL")
    bench.llm_skills.add(skill)

    try:
        response = _export(skill.id, user)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/zip"
        text = _zip_text(response.content)
        for kept in ("PROMPT-KEEP", "INTRO-KEEP", "GUIDE-KEEP", "TEXT-KEEP", "kubernetes", "ppt-master", "PACKAGE-BODY-SENTINEL"):
            assert kept in text
        for secret in (
            "PASSWORD-SENTINEL",
            "KWARGS-SENTINEL",
            "PACKAGE-PARAM-SENTINEL",
            "TOKEN-SENTINEL",
            "KWARG-VALUE-SENTINEL",
            "KWARG-SECRET-SENTINEL",
            "MODEL-SENTINEL-NAME",
            "WIKI-SENTINEL",
            "MEMORY-SENTINEL",
            "CHANNEL-SENTINEL",
            "HISTORY-SENTINEL",
            "BENCH-SENTINEL",
            "BENCH-TOKEN-SENTINEL",
        ):
            assert secret not in text
        document = json.loads(zipfile.ZipFile(io.BytesIO(response.content)).read("agent.json"))
        assert document["conversation_window_size"] == 7
        assert document["run_model_call_limit"] == 4
        assert document["skill_params"][1]["value"] == ""
        assert document["omitted_packages"] == ["对话技能"]
        assert document["mcp"] == [
            {
                "name": "ticket",
                "url": "https://mcp.example/tools",
                "transport": "streamable_http",
                "auth_required": True,
                "description": "DESC-KEEP",
                "user_tags": ["搜索", "123"],
                "kwargs": [
                    {"key": "aaa", "type": "text", "isRequired": False, "value": ""},
                    {"key": "bbb", "type": "password", "isRequired": True, "value": ""},
                ],
            }
        ]
        assert "enable_conversation_history" not in document
        assert "team" not in document
    finally:
        shutil.rmtree(storage.parent, ignore_errors=True)


def test_import_creates_portable_agent_without_touching_existing_rows():
    user = _user(superuser=True, domain="import.example")
    SkillTools.objects.create(name="kubernetes", description="", is_build_in=True, icon="k8s")
    SkillTools.objects.create(name="ticket", description="", is_build_in=False, params={"url": "https://old", "auth_token": "OLD-TOKEN"})
    builtin = SkillPackage.objects.create(package_id="ppt-master", name="PPT", version="9.9.9", is_build_in=True, domain="other")
    old_body = _skill_zip().replace(b"PACKAGE-BODY-SENTINEL", b"OLD-PACKAGE-BODY")
    old_storage = DEFAULT_SKILL_PACKAGE_ROOT / "existing-src" / uuid.uuid4().hex / "1.2.0"
    old_storage.mkdir(parents=True)
    (old_storage / "original.zip").write_bytes(old_body)
    existing_package = SkillPackage.objects.create(
        package_id="same-short-name",
        name="巡检",
        version="1.2.0",
        is_build_in=False,
        storage_path=str(old_storage),
        domain="import.example",
        manifest={"name": "巡检", "version": "1.2.0"},
    )
    slug = f"agent-transfer-decoy-{uuid.uuid4().hex}"
    marker = DEFAULT_SKILL_PACKAGE_ROOT / "1" / slug / "1.2.0" / "marker.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text("KEEP-SLUG", encoding="utf-8")
    package_bytes = _skill_zip()
    LLMSkill.objects.create(name="助手", team=[1], usage_team=[1])
    before_packages = SkillPackage.objects.count()
    document = _recipe(
        builtin_tools=["kubernetes"],
        builtin_packages=["ppt-master"],
        packages=[{"archive": "packages/0.zip", "source_name": "巡检"}],
        omitted_packages=["对话技能"],
        mcp=[
            {
                "name": "ticket",
                "url": "https://mcp.example/tools",
                "transport": "streamable_http",
                "auth_required": True,
                "description": "查工单",
                "user_tags": ["搜索", " 123 ", "搜索", ""],
                "kwargs": [
                    {"key": "aaa", "type": "text", "isRequired": False, "value": "SHOULD-NOT-LAND"},
                    {"key": "bbb", "type": "password", "isRequired": True},
                    {"key": "count", "type": "nope", "isRequired": True},
                    {"key": "  ", "type": "text", "isRequired": False},
                ],
            }
        ],
        skill_params=[
            {"key": "city", "type": "text", "value": "TEXT-KEEP"},
            {"key": "api_token", "type": "password", "value": "PASSWORD-SENTINEL"},
        ],
        domain="FOREIGN-DOMAIN",
        llm_model="MODEL-SENTINEL-NAME",
    )
    try:
        response = _import(_agent_zip(document, [package_bytes]), user)
        assert response.status_code == 200
        body = _body(response)
        created = LLMSkill.objects.get(id=body["data"]["id"])
        assert created.name == "助手 2"
        assert created.llm_model_id is None
        assert created.enable_conversation_history is True
        assert created.conversation_window_size == 7
        assert created.run_model_call_limit == 4
        assert created.temperature == 0.7
        assert created.force_wiki_grounded is False
        assert created.team == [1]
        assert created.usage_team == [1]
        assert created.domain == "import.example"
        assert created.skill_package_params == {}
        assert created.wiki_knowledge_bases.count() == 0
        assert created.memory_space_id is None
        assert created.tools[0]["name"] == "kubernetes"
        assert created.tools[0]["kwargs"] == []
        copied = SkillPackage.objects.get(name="巡检 2", domain="import.example", is_build_in=False)
        assert copied.package_id != existing_package.package_id
        assert copied.manifest["name"] == "巡检 2"
        existing_package.refresh_from_db()
        assert existing_package.name == "巡检"
        assert existing_package.package_id == "same-short-name"
        assert b"OLD-PACKAGE-BODY" in (Path(existing_package.storage_path) / "original.zip").read_bytes()
        assert "PACKAGE-BODY-SENTINEL" in _zip_text(_export(created.id, user).content)
        assert len(copied.package_id) == 32
        assert copied.domain == "import.example"
        assert copied.team == [1]
        archive_path = Path(copied.storage_path) / "original.zip"
        assert archive_path.is_file()
        assert b"PACKAGE-BODY-SENTINEL" in archive_path.read_bytes()
        assert "my-skill" not in copied.storage_path
        assert marker.read_text(encoding="utf-8") == "KEEP-SLUG"
        assert SkillPackage.objects.filter(package_id="ppt-master").count() == 1
        assert builtin.version == "9.9.9"
        old_mcp = SkillTools.objects.get(name="ticket")
        assert old_mcp.params["auth_token"] == "OLD-TOKEN"
        assert old_mcp.params["url"] == "https://old"
        assert old_mcp.description == ""
        mcp = SkillTools.objects.get(name="ticket 2")
        assert mcp.description == "查工单"
        assert mcp.user_tags == ["搜索", "123"]
        assert old_mcp.user_tags == []
        assert mcp.params["url"] == "https://mcp.example/tools"
        assert mcp.params["transport"] == "streamable_http"
        assert mcp.params["enable_auth"] is False
        assert mcp.params["auth_token"] == ""
        assert mcp.params["kwargs"] == [
            {"key": "aaa", "type": "text", "isRequired": False, "value": ""},
            {"key": "bbb", "type": "password", "isRequired": True, "value": ""},
            {"key": "count", "type": "text", "isRequired": True, "value": ""},
        ]
        assert mcp.is_build_in is False
        notes = "\n".join(body["data"]["notes"])
        assert "助手 2" in notes
        assert "ticket 2" in notes
        assert "缺少凭据" in notes
        assert "api_token" in notes
        assert "对话技能" in notes
        assert "巡检 2" in notes
        assert SkillPackage.objects.count() == before_packages + 1
        assert created.skill_params[1]["value"] == ""
        assert created.skill_params[0]["value"] == "TEXT-KEEP"
        assert any(item["package_id"] == "ppt-master" for item in created.skill_packages)
        assert any(item["package_id"] == copied.package_id for item in created.skill_packages)
    finally:
        shutil.rmtree(marker.parents[1], ignore_errors=True)
        shutil.rmtree(old_storage.parent, ignore_errors=True)
        for path in SkillPackage.objects.filter(is_build_in=False).values_list("storage_path", flat=True):
            if path:
                shutil.rmtree(Path(path).parent, ignore_errors=True)


def test_import_rejects_unknown_file_before_permission_or_writes():
    user = _user(permissions=[])
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as archive:
        archive.writestr("SKILL.md", "---\nname: bare\n---\n# bare\n")
    before = _counts()
    response = _import(blob.getvalue(), user)
    assert response.status_code == 400
    assert _body(response)["message"] == "文件无法识别，导入已取消"
    assert _counts() == before


def test_import_names_missing_permission_and_writes_nothing():
    before = _counts()
    no_add = _user(permissions=[])
    response = _import(_agent_zip(_recipe()), no_add)
    assert response.status_code == 403
    assert _body(response)["message"] == "缺少新建智能体权限"
    needs_tool = _user(permissions=["skill_list-Add"])
    response = _import(
        _agent_zip(_recipe(mcp=[{"name": "ticket", "url": "https://mcp.example", "transport": "sse", "auth_required": False}])),
        needs_tool,
    )
    assert response.status_code == 403
    assert _body(response)["message"] == "缺少工具新增权限"
    assert _counts() == before


def test_prompt_only_import_does_not_require_tool_permission():
    user = _user(permissions=["skill_list-Add"], domain="only.example")
    response = _import(_agent_zip(_recipe()), user)
    assert response.status_code == 200
    created = LLMSkill.objects.get(id=_body(response)["data"]["id"])
    assert created.skill_prompt == "PROMPT-KEEP"
    assert created.tools == []
    assert created.domain == "only.example"


def test_import_rejects_invalid_org_and_missing_builtins_before_writes():
    before = _counts()
    outsider = _user(permissions=["skill_list-Add"], groups=[{"id": 2, "name": "T2"}])
    response = _import(_agent_zip(_recipe()), outsider)
    assert response.status_code == 400
    assert _body(response)["message"] == "当前组织无效，导入已取消"
    missing_cookie = _user(permissions=["skill_list-Add"])
    response = _import(_agent_zip(_recipe()), missing_cookie, cookie=None)
    assert response.status_code == 400
    assert "当前组织无效" in _body(response)["message"]
    user = _user(superuser=True)
    response = _import(_agent_zip(_recipe(builtin_tools=["kube"], builtin_packages=["missing-package"])), user)
    assert response.status_code == 400
    message = _body(response)["message"]
    assert "kube" in message
    assert "missing-package" in message
    assert "请升级版本" in message
    assert _counts() == before


def test_unreadable_inner_package_keeps_the_agent():
    user = _user(superuser=True)
    document = _recipe(packages=[{"archive": "packages/0.zip", "source_name": "坏包"}])
    response = _import(_agent_zip(document, [b"not-a-zip"]), user)
    assert response.status_code == 200
    body = _body(response)
    assert LLMSkill.objects.filter(id=body["data"]["id"]).exists()
    assert "坏包" in "\n".join(body["data"]["notes"])
    assert SkillPackage.objects.filter(name="坏包").count() == 0


def test_conversation_skill_round_trips_and_same_domain_name_gets_a_suffix():
    user = _user(superuser=True, domain="import.example")
    conversation = SkillPackage.objects.create(
        package_id="conv-disk",
        name="磁盘空间排查",
        version="0.1.0",
        description="看看磁盘",
        source_type="conversation",
        storage_path="",
        skill_markdown="CONVERSATION-BODY",
        triggers=["磁盘"],
        domain="domain.com",
        is_build_in=False,
    )
    SkillPackage.objects.create(
        package_id="disk-existing",
        name="磁盘空间排查",
        version="0.1.0",
        domain="import.example",
        is_build_in=False,
        storage_path="",
    )
    skill = LLMSkill.objects.create(
        name="带对话技能",
        team=[1],
        domain="domain.com",
        skill_packages=[{"id": conversation.id, "package_id": conversation.package_id, "name": conversation.name}],
    )
    exported = _export(skill.id, user)
    assert exported.status_code == 200
    assert "CONVERSATION-BODY" in _zip_text(exported.content)
    document = json.loads(zipfile.ZipFile(io.BytesIO(exported.content)).read("agent.json"))
    assert document["omitted_packages"] == []
    assert document["packages"][0]["source_name"] == "磁盘空间排查"
    try:
        response = _import(exported.content, user)
        assert response.status_code == 200
        body = _body(response)
        created = LLMSkill.objects.get(id=body["data"]["id"])
        copied = SkillPackage.objects.get(name="磁盘空间排查 2", domain="import.example")
        assert "CONVERSATION-BODY" in copied.skill_markdown
        assert copied.description == "看看磁盘"
        assert copied.triggers == ["磁盘"]
        assert any(item["name"] == "磁盘空间排查 2" for item in created.skill_packages)
        assert "磁盘空间排查 2" in "\n".join(body["data"]["notes"])
        assert SkillPackage.objects.get(package_id="disk-existing").name == "磁盘空间排查"
        assert SkillPackage.objects.get(package_id="conv-disk").skill_markdown == "CONVERSATION-BODY"
    finally:
        for path in SkillPackage.objects.filter(name="磁盘空间排查 2").values_list("storage_path", flat=True):
            if path:
                shutil.rmtree(Path(path).parent, ignore_errors=True)


def test_stale_package_binding_exports_by_manifest_id():
    user = _user(superuser=True)
    foreign = SkillPackage.objects.create(
        package_id="foreign-ad",
        name="别域技能",
        version="0.1.0",
        domain="other.example",
        is_build_in=False,
        storage_path="",
        skill_markdown="FOREIGN-PACKAGE-BODY",
        manifest={"id": "foreign-ad", "name": "别域技能"},
    )
    SkillPackage.objects.create(
        package_id="566aa12464824402924fb09576c686ba",
        name="AD 域运维",
        version="0.1.0",
        domain="domain.com",
        is_build_in=False,
        storage_path="",
        skill_markdown="AD-BODY",
        manifest={"id": "ad-domain-ops", "name": "AD 域运维"},
    )
    skill = LLMSkill.objects.create(
        name="带AD",
        team=[1],
        domain="domain.com",
        skill_packages=[
            {
                "id": foreign.id,
                "package_id": "ad-domain-ops",
                "name": "AD 域运维",
                "version": "0.1.0",
            }
        ],
    )
    exported = _export(skill.id, user)
    assert exported.status_code == 200
    text = _zip_text(exported.content)
    assert "AD-BODY" in text
    assert "FOREIGN-PACKAGE-BODY" not in text
    document = json.loads(zipfile.ZipFile(io.BytesIO(exported.content)).read("agent.json"))
    assert document["omitted_packages"] == []
    assert document["packages"][0]["source_name"] == "AD 域运维"


def test_stale_package_id_from_another_domain_is_omitted():
    user = _user(superuser=True)
    foreign = SkillPackage.objects.create(
        package_id="foreign-only",
        name="外域包",
        version="0.1.0",
        domain="other.example",
        is_build_in=False,
        storage_path="",
        skill_markdown="FOREIGN-ONLY-BODY",
        manifest={"id": "foreign-only", "name": "外域包"},
    )
    skill = LLMSkill.objects.create(
        name="只挂了外域包",
        team=[1],
        domain="domain.com",
        skill_packages=[
            {
                "id": foreign.id,
                "package_id": foreign.package_id,
                "name": foreign.name,
                "version": foreign.version,
            }
        ],
    )
    exported = _export(skill.id, user)
    assert exported.status_code == 200
    assert "FOREIGN-ONLY-BODY" not in _zip_text(exported.content)
    document = json.loads(zipfile.ZipFile(io.BytesIO(exported.content)).read("agent.json"))
    assert document["packages"] == []
    assert document["omitted_packages"] == ["外域包"]


def test_export_requires_setting_edit_permission():
    user = _user(permissions=["skill_list-Add"])
    skill = LLMSkill.objects.create(name="助手", team=[1])
    response = _export(skill.id, user)
    assert response.status_code == 403
    assert _body(response)["message"] == "缺少设置编辑权限"
    assert not response.content.startswith(b"PK")


def _rules(team=None, instance=None):
    return {"team": team or [], "instance": instance or []}


def test_export_rejects_other_org_or_missing_instance_operate():
    editor = _user(permissions=["skill_setting-Edit"], groups=[{"id": 1, "name": "T1"}])
    other = LLMSkill.objects.create(name="别的组织", team=[2], domain="domain.com", skill_prompt="OTHER-ORG-PROMPT")
    response = _export(other.id, editor)
    assert response.status_code == 403
    assert _body(response)["result"] is False
    assert not response.content.startswith(b"PK")
    assert b"OTHER-ORG-PROMPT" not in response.content

    local = LLMSkill.objects.create(name="本组织", team=[1], domain="domain.com", skill_prompt="LOCAL-PROMPT")
    view_only = [{"id": local.id, "permission": ["View"]}]
    with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=_rules(instance=view_only)):
        response = _export(local.id, editor)
    assert response.status_code == 403
    assert _body(response)["result"] is False
    assert _body(response)["message"] == "You do not have permission to update this instance"
    assert not response.content.startswith(b"PK")
    assert b"LOCAL-PROMPT" not in response.content


def test_export_rejects_current_team_cookie_outside_user_groups():
    editor = _user(permissions=["skill_setting-Edit"], groups=[{"id": 1, "name": "T1"}])
    skill = LLMSkill.objects.create(name="伪造组织", team=[9], domain="domain.com", skill_prompt="COOKIE-PROMPT")
    with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=_rules(team=[9])):
        response = _export(skill.id, editor, cookie="9")
    assert response.status_code == 403
    assert _body(response)["result"] is False
    assert not response.content.startswith(b"PK")
    assert b"COOKIE-PROMPT" not in response.content


def test_export_allows_editor_with_instance_operate():
    editor = _user(permissions=["skill_setting-Edit"])
    skill = LLMSkill.objects.create(name="可导出", team=[1], domain="domain.com", skill_prompt="ALLOWED-PROMPT")
    operate = [{"id": skill.id, "permission": ["Operate"]}]
    with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=_rules(instance=operate)):
        response = _export(skill.id, editor)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert "ALLOWED-PROMPT" in _zip_text(response.content)


def test_export_skips_other_org_tool_and_names_missing_custom_tool():
    user = _user(superuser=True)
    foreign = SkillTools.objects.create(
        name="foreign-mcp",
        description="FOREIGN-TOOL-DESC",
        is_build_in=False,
        domain="domain.com",
        team=[2],
        params={"url": "https://mcp.example/FOREIGN-MCP-URL", "transport": "sse", "auth_token": "FOREIGN-TOKEN"},
    )
    skill = LLMSkill.objects.create(
        name="工具边界",
        team=[1],
        domain="domain.com",
        tools=[
            {"id": foreign.id, "name": foreign.name, "kwargs": []},
            {"id": 999999, "name": "LOST-MCP", "kwargs": []},
        ],
    )
    exported = _export(skill.id, user)
    assert exported.status_code == 200
    text = _zip_text(exported.content)
    assert "FOREIGN-MCP-URL" not in text
    assert "FOREIGN-TOKEN" not in text
    assert "FOREIGN-TOOL-DESC" not in text
    document = json.loads(zipfile.ZipFile(io.BytesIO(exported.content)).read("agent.json"))
    assert document["builtin_tools"] == []
    assert document["mcp"] == []
    assert document["omitted_tools"] == ["foreign-mcp", "LOST-MCP"]
    imported = _import(exported.content, user)
    assert imported.status_code == 200
    notes = "\n".join(_body(imported)["data"]["notes"])
    assert "foreign-mcp" in notes
    assert "LOST-MCP" in notes
    created = LLMSkill.objects.get(id=_body(imported)["data"]["id"])
    assert created.tools == []


def test_import_does_not_read_an_oversized_upload():
    class Probe:
        name = "agent.zip"
        size = 10**12

        def read(self, n=-1):
            raise AssertionError(n)

        def chunks(self, chunk_size=None):
            raise AssertionError("chunks")

    user = _user(permissions=["skill_list-Add"])
    before = _counts()
    response = _import(b"", user, upload=Probe())
    assert response.status_code == 400
    assert "超过大小限制" in _body(response)["message"]
    assert _counts() == before


def _zip_with_extra(document):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("agent.json", json.dumps(document, ensure_ascii=False))
        archive.writestr("extra.txt", "EXTRA")
    return buffer.getvalue()


def test_import_rejects_agent_zip_over_entry_or_uncompressed_limit(monkeypatch):
    user = _user(superuser=True)
    before = _counts()
    monkeypatch.setattr(agent_transfer, "MAX_AGENT_ENTRIES", 1)
    response = _import(_zip_with_extra(_recipe()), user)
    assert response.status_code == 400
    assert "条目过多" in _body(response)["message"]
    assert _counts() == before

    monkeypatch.setattr(agent_transfer, "MAX_AGENT_ENTRIES", 128)
    monkeypatch.setattr(agent_transfer, "MAX_AGENT_UNCOMPRESSED_BYTES", 8)
    response = _import(_agent_zip(_recipe()), user)
    assert response.status_code == 400
    assert "解压后超过大小限制" in _body(response)["message"]
    assert _counts() == before


def test_import_rejects_inner_package_over_limit(monkeypatch):
    user = _user(superuser=True)
    document = _recipe(packages=[{"archive": "packages/0.zip", "source_name": "大包"}])
    payload = _agent_zip(document, [_skill_zip()])
    before = _counts()
    monkeypatch.setattr(agent_transfer, "MAX_PACKAGE_ENTRIES", 0)
    response = _import(payload, user)
    assert response.status_code == 400
    assert "技能包条目过多" in _body(response)["message"]
    assert _counts() == before

    monkeypatch.setattr(agent_transfer, "MAX_PACKAGE_ENTRIES", 2000)
    monkeypatch.setattr(agent_transfer, "MAX_PACKAGE_UNCOMPRESSED_BYTES", 8)
    response = _import(payload, user)
    assert response.status_code == 400
    assert "技能包解压后超过大小限制" in _body(response)["message"]
    assert _counts() == before

    monkeypatch.setattr(agent_transfer, "MAX_PACKAGE_UNCOMPRESSED_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(agent_transfer, "MAX_PACKAGE_ARCHIVE_BYTES", 8)
    response = _import(payload, user)
    assert response.status_code == 400
    assert "技能包超过大小限制" in _body(response)["message"]
    assert _counts() == before


def test_export_fails_when_skill_package_exceeds_encoded_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_transfer, "MAX_PACKAGE_ARCHIVE_BYTES", 16)
    user = _user(superuser=True)
    storage = tmp_path / "pkg" / "1.0.0"
    storage.mkdir(parents=True)
    (storage / "original.zip").write_bytes(b"x" * 32)
    package = SkillPackage.objects.create(
        package_id="fat-package",
        name="大包",
        version="1.0.0",
        is_build_in=False,
        storage_path=str(storage),
        domain="domain.com",
    )
    skill = LLMSkill.objects.create(
        name="带大包",
        team=[1],
        domain="domain.com",
        skill_packages=[{"id": package.id, "package_id": package.package_id, "name": package.name, "version": package.version}],
    )
    response = _export(skill.id, user)
    assert response.status_code == 400
    assert "技能包超过大小限制" in _body(response)["message"]
    assert not response.content.startswith(b"PK")

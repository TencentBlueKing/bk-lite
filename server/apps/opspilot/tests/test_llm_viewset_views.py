"""LLMViewSet / SkillToolsViewSet 安全行为单测（F015 / F016 / F017）。

这些用例聚焦于近期加固的安全行为，**不依赖数据库**：

- create / update 不允许通过请求体批量赋值受保护字段（F017）：
  - ``UPDATABLE_SKILL_FIELDS`` 白名单确保只有显式字段会被 ``setattr`` 到模型；
  - 序列化器 ``read_only_fields`` 将 id/created_by/is_builtin 等审计字段标记只读。
- ``get_mcp_tools`` 通过统一的 SSRFValidator 拒绝私网 / 链路本地目标（F015）。
- ``test_*_connection`` 动作拒绝私网 / 内网主机（F016）。
- ``get_skill_params`` 读取时对 password 类型参数做掩码（******）。

实现说明：视图方法上叠加了 ``@action`` / ``@HasPermission`` 装饰器，后者用
``functools.wraps`` 保留了 ``__wrapped__``，因此可直接取 ``__wrapped__`` 调用未鉴权的
原始函数，从而无需真实路由 / DB / 鉴权中间件即可断言安全逻辑。网络 / LLM / DB
依赖一律 mock。
"""

import json
from types import SimpleNamespace

import pytest
from rest_framework.response import Response

from apps.core.utils.ssrf_validator import SSRFError
from apps.opspilot.serializers.llm_serializer import LLMSerializer
from apps.opspilot.viewsets.llm_view import LLMViewSet, SkillToolsViewSet

pytestmark = pytest.mark.unit


def _json_body(response):
    """从 JsonResponse 中解出 dict 主体。"""
    return json.loads(response.content.decode("utf-8"))


# ---------------------------------------------------------------------------
# F017: mass-assignment 防护 —— UPDATABLE_SKILL_FIELDS 白名单
# ---------------------------------------------------------------------------


def test_updatable_skill_fields_excludes_protected_audit_fields():
    """白名单不得包含 id / 审计 / 域 / 内建标记等受保护字段。"""
    protected = {"id", "created_by", "updated_by", "domain", "updated_by_domain", "is_builtin"}
    assert protected.isdisjoint(LLMViewSet.UPDATABLE_SKILL_FIELDS)


def test_serializer_marks_audit_fields_read_only():
    """序列化器把审计 / 系统字段标记为 read_only，杜绝请求体篡改。"""
    read_only = set(LLMSerializer.Meta.read_only_fields)
    assert {"id", "created_by", "updated_by", "domain", "updated_by_domain", "is_builtin"} <= read_only


def test_skill_packages_are_serialized_and_updatable():
    """智能体可保存多个技能包，但仍必须通过显式白名单进入模型。"""
    assert "skill_packages" in LLMSerializer.Meta.fields
    assert "skill_packages" in LLMViewSet.UPDATABLE_SKILL_FIELDS


def test_apply_skill_packages_records_visible_match_summary(mocker):
    """执行智能体时要把命中的技能包注入提示词，并保留可观测的命中摘要。"""
    mocker.patch("apps.opspilot.viewsets.llm_view.hydrate_skill_packages", side_effect=lambda packages: packages)

    viewset = LLMViewSet()
    skill = SimpleNamespace(
        skill_prompt="你是运维助手。",
        skill_packages=[
            {
                "id": "kubernetes-specialist",
                "name": "Kubernetes Specialist",
                "description": "Kubernetes workload troubleshooting",
                "required_tools": ["kubernetes"],
                "triggers": ["异常工作负载"],
                "capabilities": ["config_analysis_report", "repair_diff_report"],
                "reports": {"config_analysis": {"source_tool": "analyze_deployment_configurations"}},
                "workflows": {"after_config_analysis": [{"type": "choice"}]},
                "skill_markdown": "Use workload troubleshooting workflow.",
            }
        ],
    )
    params = {
        "skill_prompt": skill.skill_prompt,
        "user_message": "查看当前 K8s 集群有哪些异常工作负载",
        "tools": [{"name": "kubernetes"}],
    }

    viewset._apply_skill_packages_to_params(params, skill)

    assert "已命中技能包：Kubernetes Specialist" in params["skill_prompt"]
    assert params["matched_skill_packages"] == [
        {
            "id": "kubernetes-specialist",
            "name": "Kubernetes Specialist",
            "package_id": "kubernetes-specialist",
            "description": "Kubernetes workload troubleshooting",
            "missing_tools": [],
            "capabilities": ["config_analysis_report", "repair_diff_report"],
            "reports": {"config_analysis": {"source_tool": "analyze_deployment_configurations"}},
            "workflows": {"after_config_analysis": [{"type": "choice"}]},
        }
    ]
    assert params["skill_package_capabilities"] == ["config_analysis_report", "repair_diff_report"]
    assert params["skill_package_reports"] == {"config_analysis": {"source_tool": "analyze_deployment_configurations"}}
    assert params["skill_package_workflows"] == {"after_config_analysis": [{"type": "choice"}]}


class _FakeSkill:
    """最小化的 LLMSkill 替身：仅暴露白名单可能写入的属性与受保护字段。"""

    def __init__(self):
        # 受保护字段（绝不应被请求体覆盖）
        self.id = 42
        self.created_by = "owner"
        self.is_builtin = True
        self.domain = "domain.com"
        # 可更新字段
        self.name = "old-name"
        self.skill_prompt = "old-prompt"
        self.team = [1]
        self.skill_params = []
        self.skill_packages = []
        self.knowledge_base = SimpleNamespace(set=lambda *a, **k: None, clear=lambda: None)
        self.rag_score_threshold_map = {}
        self.saved = False
        self.updated_by = None

    def save(self, *args, **kwargs):
        self.saved = True


def test_update_ignores_protected_fields_via_mass_assignment(mocker):
    """update 收到 id/created_by/is_builtin 等键时必须忽略，只写白名单字段。"""
    viewset = LLMViewSet()
    viewset.loader = None
    instance = _FakeSkill()

    mocker.patch.object(LLMViewSet, "get_object", return_value=instance)
    mocker.patch.object(LLMViewSet, "_validate_name", return_value="")
    mocker.patch.object(LLMViewSet, "delete_rules")
    mocker.patch("apps.opspilot.viewsets.llm_view.log_operation")

    malicious = {
        "name": "new-name",
        "team": [1],
        # 攻击者尝试覆盖的受保护字段
        "id": 9999,
        "created_by": "attacker",
        "is_builtin": False,
        "domain": "evil.com",
        # 不在白名单内的任意键
        "totally_unknown_field": "x",
    }
    request = SimpleNamespace(
        user=SimpleNamespace(is_superuser=True, username="tester", group_list=[{"id": 1, "name": "g"}]),
        data=malicious,
        COOKIES={},
    )

    response = LLMViewSet.update.__wrapped__(viewset, request)

    assert _json_body(response) == {"result": True}
    # 白名单字段被写入
    assert instance.name == "new-name"
    # 受保护字段保持不变
    assert instance.id == 42
    assert instance.created_by == "owner"
    assert instance.is_builtin is True
    assert instance.domain == "domain.com"
    # 未知键不应被 setattr 到模型
    assert not hasattr(instance, "totally_unknown_field")
    assert instance.saved is True


def test_create_passes_only_validated_payload_to_serializer(mocker):
    """create 不直接 setattr 模型，而是交由序列化器（read_only_fields 守门）。"""
    viewset = LLMViewSet()
    viewset.loader = None

    mocker.patch.object(LLMViewSet, "_validate_org_field_permission")
    mocker.patch.object(LLMViewSet, "_validate_name", return_value="")
    mocker.patch.object(LLMViewSet, "perform_create")
    mocker.patch.object(LLMViewSet, "get_success_headers", return_value={})
    mocker.patch("apps.opspilot.viewsets.llm_view.log_operation")

    captured = {}

    def fake_get_serializer(*args, **kwargs):
        captured["data"] = kwargs.get("data")
        return SimpleNamespace(
            is_valid=lambda raise_exception=False: True,
            data={"name": "demo", "id": 1},
        )

    mocker.patch.object(LLMViewSet, "get_serializer", side_effect=fake_get_serializer)

    request = SimpleNamespace(
        user=SimpleNamespace(username="tester", group_list=[{"id": 1, "name": "g"}]),
        data={
            "name": "demo",
            "team": [1],
            # 即便传入受保护字段，最终落库由 read_only_fields 守门
            "is_builtin": True,
            "created_by": "attacker",
        },
        COOKIES={"current_team": "1"},
    )

    response = LLMViewSet.create.__wrapped__(viewset, request)

    assert response.status_code == 201
    # 序列化器是唯一写入路径；read_only_fields 会丢弃受保护字段
    read_only = set(LLMSerializer.Meta.read_only_fields)
    assert {"is_builtin", "created_by"} <= read_only


# ---------------------------------------------------------------------------
# F015: get_mcp_tools 的 SSRF 防护
# ---------------------------------------------------------------------------


def test_get_mcp_tools_rejects_ssrf_target(mocker):
    """私网 / 链路本地 server_url 被 SSRFValidator 拦截，且不发起真实连接。"""
    viewset = SkillToolsViewSet()
    viewset.loader = None

    validate = mocker.patch(
        "apps.opspilot.viewsets.llm_view.SSRFValidator.validate",
        side_effect=SSRFError("blocked private address"),
    )
    mcp_client = mocker.patch("apps.opspilot.viewsets.llm_view.MCPClient")
    cache_get = mocker.patch("apps.opspilot.viewsets.llm_view.get_cached_mcp_tools")

    request = SimpleNamespace(
        data={"server_url": "http://169.254.169.254/latest/meta-data/"},
        user=SimpleNamespace(locale="en"),
    )

    response = SkillToolsViewSet.get_mcp_tools.__wrapped__(viewset, request)

    body = _json_body(response)
    assert body["result"] is False
    assert "blocked private address" in body["message"]
    validate.assert_called_once_with("http://169.254.169.254/latest/meta-data/")
    # SSRF 命中后不得查缓存，更不得建立 MCP 连接
    cache_get.assert_not_called()
    mcp_client.assert_not_called()


def test_get_mcp_tools_requires_server_url(mocker):
    """缺少 server_url 时直接拒绝，不进入 SSRF / 连接逻辑。"""
    viewset = SkillToolsViewSet()
    viewset.loader = None

    validate = mocker.patch("apps.opspilot.viewsets.llm_view.SSRFValidator.validate")
    request = SimpleNamespace(data={}, user=SimpleNamespace(locale="en"))

    response = SkillToolsViewSet.get_mcp_tools.__wrapped__(viewset, request)

    assert _json_body(response)["result"] is False
    validate.assert_not_called()


# ---------------------------------------------------------------------------
# F016: test_*_connection 的 SSRF 防护（私网 / 内网主机）
# ---------------------------------------------------------------------------


def test_test_mysql_connection_rejects_private_host(mocker):
    """test_mysql_connection 对私网 host 触发 SSRF 拦截，不建立真实连接。"""
    viewset = SkillToolsViewSet()
    viewset.loader = None

    guard = mocker.patch.object(
        SkillToolsViewSet,
        "_guard_connection_host",
        side_effect=SSRFError("private host blocked"),
    )
    normalize = mocker.patch("apps.opspilot.viewsets.llm_view.normalize_mysql_instance")
    tester = mocker.patch("apps.opspilot.viewsets.llm_view.test_mysql_instance")

    request = SimpleNamespace(data={"host": "10.0.0.5", "port": 3306})

    response = SkillToolsViewSet.test_mysql_connection.__wrapped__(viewset, request)

    body = _json_body(response)
    assert response.status_code == 400
    assert body["result"] is False
    assert "private host blocked" in body["message"]
    guard.assert_called_once_with("10.0.0.5", 3306)
    # 拦截后不得 normalize / 真实测试连接
    normalize.assert_not_called()
    tester.assert_not_called()


def test_test_redis_connection_rejects_private_url(mocker):
    """test_redis_connection 对私网 url 触发 SSRF 拦截。"""
    viewset = SkillToolsViewSet()
    viewset.loader = None

    mocker.patch.object(
        SkillToolsViewSet,
        "_guard_connection_url",
        side_effect=SSRFError("loopback url blocked"),
    )
    normalize = mocker.patch("apps.opspilot.viewsets.llm_view.normalize_redis_instance")
    tester = mocker.patch("apps.opspilot.viewsets.llm_view.test_redis_instance")

    request = SimpleNamespace(data={"url": "redis://127.0.0.1:6379"})

    response = SkillToolsViewSet.test_redis_connection.__wrapped__(viewset, request)

    body = _json_body(response)
    assert response.status_code == 400
    assert body["result"] is False
    assert "loopback url blocked" in body["message"]
    normalize.assert_not_called()
    tester.assert_not_called()


def test_guard_connection_host_invokes_ssrf_validator(mocker):
    """_guard_connection_host 把 host:port 拼成 URL 走统一 SSRFValidator。"""
    validate = mocker.patch("apps.opspilot.viewsets.llm_view.SSRFValidator.validate")

    SkillToolsViewSet._guard_connection_host("192.168.1.10", 5432)

    validate.assert_called_once_with("http://192.168.1.10:5432")


def test_guard_connection_host_skips_empty_target(mocker):
    """host 为空时跳过校验，避免误报。"""
    validate = mocker.patch("apps.opspilot.viewsets.llm_view.SSRFValidator.validate")

    SkillToolsViewSet._guard_connection_host("", None)
    SkillToolsViewSet._guard_connection_host(None, None)

    validate.assert_not_called()


# ---------------------------------------------------------------------------
# skill_params 读取时 password 掩码
# ---------------------------------------------------------------------------


def test_get_skill_params_masks_password_value():
    """get_skill_params 对 password 类型参数的 value 掩码为 ******。"""
    instance = SimpleNamespace(
        skill_params=[
            {"key": "token", "type": "password", "value": "super-secret"},
            {"key": "endpoint", "type": "text", "value": "https://api.example.com"},
        ]
    )

    result = LLMSerializer.get_skill_params(instance)

    masked = {p["key"]: p["value"] for p in result}
    assert masked["token"] == "******"
    # 非 password 字段保持原值
    assert masked["endpoint"] == "https://api.example.com"


def test_get_skill_params_does_not_mutate_instance():
    """掩码逻辑不得污染原始 instance.skill_params（按值拷贝）。"""
    original = [{"key": "token", "type": "password", "value": "secret"}]
    instance = SimpleNamespace(skill_params=original)

    LLMSerializer.get_skill_params(instance)

    assert instance.skill_params[0]["value"] == "secret"


def test_get_skill_params_handles_none():
    """skill_params 为空时返回空列表，不抛异常。"""
    instance = SimpleNamespace(skill_params=None)

    assert LLMSerializer.get_skill_params(instance) == []


def test_skill_package_cleanup_storage_path_removes_directory(tmp_path, mocker):
    """_cleanup_storage_path:storage_path 落在 root 之下时,rmtree 掉。"""
    from apps.opspilot.viewsets.llm_view import SkillPackageViewSet

    storage_dir = tmp_path / "1" / "my-skill" / "0.1.0"
    storage_dir.mkdir(parents=True)
    (storage_dir / "SKILL.md").write_text("# hi")

    mocker.patch(
        "apps.opspilot.services.skill_package.importer.DEFAULT_SKILL_PACKAGE_ROOT",
        tmp_path,
    )

    result = SkillPackageViewSet._cleanup_storage_path(str(storage_dir))

    assert result is True
    assert not storage_dir.exists()
    # 上层 /1 目录还在(我们只删 skill_id/version 那一层)
    assert (tmp_path / "1").exists()


def test_skill_package_cleanup_storage_path_refuses_path_outside_root(tmp_path, mocker):
    """Safety:_cleanup_storage_path 拒绝删 storage_root 之外的目录。"""
    from apps.opspilot.viewsets.llm_view import SkillPackageViewSet

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "important.txt").write_text("data")

    mocker.patch(
        "apps.opspilot.services.skill_package.importer.DEFAULT_SKILL_PACKAGE_ROOT",
        tmp_path / "totally_unrelated_root",
    )

    result = SkillPackageViewSet._cleanup_storage_path(str(outside_dir))

    assert result is False
    # 目录不能被删
    assert outside_dir.exists()
    assert (outside_dir / "important.txt").read_text() == "data"


def test_skill_package_cleanup_storage_path_empty_string_is_noop(tmp_path, mocker):
    """空 storage_path(老数据 / 没解压过)不报错,直接返回 False。"""
    from apps.opspilot.viewsets.llm_view import SkillPackageViewSet

    result = SkillPackageViewSet._cleanup_storage_path("")
    assert result is False

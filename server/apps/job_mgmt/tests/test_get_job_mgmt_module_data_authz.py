"""get_job_mgmt_module_data 鉴权与 KeyError 防崩溃回归测试（Issue #3430）。

Django-free harness：往 sys.modules 注入 stub nats_client / queryset，避免
依赖真实 DB（Postgres）+ Django app ready。覆盖两个缺陷场景：

1. 非法 module / child_module → 不再 KeyError 崩溃，返回明确错误
2. 调用方声明的 group_id 超出其授权 team 白名单 → 拒绝，不返回数据

参考：server/apps/opspilot/tests/test_nats_api_module_data.py（同款 Issue #3433 修复测试）。
"""
import importlib.util
import sys
import types
from pathlib import Path


class _FakeQS:
    """伪造 Django QuerySet：跟踪 filter 调用参数 + 返回可控结果。"""

    def __init__(self, items=None):
        self._items = list(items or [])
        self.filter_calls = []

    def filter(self, **kwargs):
        self.filter_calls.append(kwargs)
        return _FakeQS(items=self._items)

    def count(self):
        return len(self._items)

    def __getitem__(self, slc):
        return self._items[slc]

    def values(self, *fields):
        return self


def _make_model_stub(queryset):
    class _Model:
        objects = queryset

    return _Model


def _ensure_package(name):
    """Ensure parent packages exist in sys.modules so 'a.b.c' imports resolve."""
    parts = name.split(".")
    for i in range(1, len(parts)):
        pkg = ".".join(parts[:i])
        if pkg not in sys.modules:
            mod = types.ModuleType(pkg)
            mod.__path__ = []  # mark as package
            sys.modules[pkg] = mod


def _install(name, **attrs):
    """Install a stub module into sys.modules; ensure parents exist."""
    _ensure_package(name)
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_nats_api(scripts_qs=None, targets_qs=None, executions_qs=None,
                   dangerous_rule_qs=None, dangerous_path_qs=None,
                   scheduled_task_qs=None, playbook_qs=None):
    """
    在不触发 Django setup 的前提下，importlib.util.spec_from_file_location + exec_module
    加载 server/apps/job_mgmt/nats_api.py，并注入所有需要的 stub。
    """
    # ── nats_client stub ──────────────────────────────────────────────────
    registered_handlers = {}

    def register(fn):
        registered_handlers[fn.__name__] = fn
        return fn

    _install("nats_client", register=register)

    # ── apps.job_mgmt.models stub ─────────────────────────────────────────
    Script = _make_model_stub(scripts_qs or _FakeQS())
    Target = _make_model_stub(targets_qs or _FakeQS())
    JobExecution = _make_model_stub(executions_qs or _FakeQS())
    Playbook = _make_model_stub(playbook_qs or _FakeQS())
    ScheduledTask = _make_model_stub(scheduled_task_qs or _FakeQS())
    DangerousRule = _make_model_stub(dangerous_rule_qs or _FakeQS())
    DangerousPath = _make_model_stub(dangerous_path_qs or _FakeQS())
    DistributionFile = type("DistributionFile", (), {})

    _install(
        "apps.job_mgmt.models",
        Script=Script,
        Target=Target,
        JobExecution=JobExecution,
        Playbook=Playbook,
        ScheduledTask=ScheduledTask,
        DangerousRule=DangerousRule,
        DangerousPath=DangerousPath,
        DistributionFile=DistributionFile,
    )

    # ── 其它 transitively imported modules ─────────────────────────────────
    # asgiref.sync
    _install("asgiref.sync", async_to_sync=lambda f: f)

    # celery
    _install("celery", current_app=type("CA", (), {})())

    # django stub package, with timezone submodule
    _install("django")
    _install("django.utils.timezone", now=lambda: None, timezone=type("TZ", (), {})())

    # django.db stub
    _install("django.db")
    _install("django.db.models")

    # apps.core.logger
    _install("apps.core.logger", job_logger=__import__("logging").getLogger("test"))

    # apps.core.utils.ssrf_validator
    class _DummyValidator:
        @staticmethod
        def validate_callback(url):
            return None

    _install("apps.core.utils.ssrf_validator", SSRFError=Exception, SSRFValidator=_DummyValidator)

    # apps.job_mgmt.constants
    _install(
        "apps.job_mgmt.constants",
        CallbackType=type("CT", (), {
            "WEB": "web", "NATS": "nats", "BOTH": "both",
            "use_web": staticmethod(lambda t: t in ("web", "both")),
            "use_nats": staticmethod(lambda t: t in ("nats", "both")),
        }),
        ExecutionStatus=type("ES", (), {}),
        JobType=type("JT", (), {}),
        TriggerSource=type("TS", (), {}),
    )

    # Services / tasks / utils
    _install("apps.job_mgmt.services.callback_service", send_callback=lambda *a, **kw: None)
    _install("apps.job_mgmt.services.dangerous_checker",
             DangerousChecker=type("DC", (), {"check_command": staticmethod(lambda *a, **kw: None)}))
    _install("apps.job_mgmt.services.execution_stream_service", publish_done_sentinel=lambda *a, **kw: None)
    _install("apps.job_mgmt.services.script_params_service", ScriptParamsService=type("SPS", (), {}))

    def _task(name):
        return type(f"T_{name}", (), {"delay": staticmethod(lambda *a, **kw: type("R", (), {"id": "fake"})())})()

    _install("apps.job_mgmt.tasks",
             distribute_files_task=_task("distribute"),
             execute_script_task=_task("execute"),
             finalize_cancelling_execution=_task("finalize"))

    # team_authz 用真模块（这是被测目标依赖的工具函数）。
    # 用 importlib 直接 load file，绕过 apps.job_mgmt.utils package 限制。
    _ta_src = Path(__file__).parent.parent / "utils" / "team_authz.py"
    _ta_spec = importlib.util.spec_from_file_location("apps.job_mgmt.utils.team_authz", _ta_src)
    _ta_mod = importlib.util.module_from_spec(_ta_spec)
    _ta_spec.loader.exec_module(_ta_mod)
    sys.modules["apps.job_mgmt.utils.team_authz"] = _ta_mod

    # node_mgmt / rpc 依赖
    _install("apps.node_mgmt.utils.s3", delete_s3_file=lambda *a, **kw: None)
    _install("apps.rpc.sensitive", sanitize_sensitive_data=lambda d: d, summarize_ansible_callback=lambda d: str(d))

    # ── 加载真正的 nats_api 模块 ──────────────────────────────────────────
    src = Path(__file__).parent.parent / "nats_api.py"
    spec = importlib.util.spec_from_file_location("job_mgmt_nats_api", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return mod, registered_handlers, {
        "Script": Script,
        "Target": Target,
        "JobExecution": JobExecution,
        "Playbook": Playbook,
        "ScheduledTask": ScheduledTask,
        "DangerousRule": DangerousRule,
        "DangerousPath": DangerousPath,
    }


# ── 测试 ────────────────────────────────────────────────────────────────


class TestKeyErrorGuard:
    """Issue #3430 R1：未知 module/child_module 必须返回错误，不能 KeyError 崩溃。"""

    @classmethod
    def setup_class(cls):
        cls.mod, cls.handlers, cls.models = _load_nats_api()

    def test_unknown_top_module_returns_error(self):
        fn = self.handlers["get_job_mgmt_module_data"]
        out = fn(module="nonexistent_module", child_module=None, page=1, page_size=10, group_id=1, team=[1])
        assert out["result"] is False
        assert "Unknown module" in out["message"]

    def test_unknown_child_module_returns_error(self):
        fn = self.handlers["get_job_mgmt_module_data"]
        out = fn(module="system", child_module="nonexistent_child", page=1, page_size=10, group_id=1, team=[1])
        assert out["result"] is False
        assert "Unknown child_module" in out["message"]

    def test_empty_string_module_returns_error(self):
        fn = self.handlers["get_job_mgmt_module_data"]
        out = fn(module="", child_module=None, page=1, page_size=10, group_id=1, team=[1])
        assert out["result"] is False

    def test_empty_string_child_module_returns_error(self):
        fn = self.handlers["get_job_mgmt_module_data"]
        out = fn(module="system", child_module="", page=1, page_size=10, group_id=1, team=[1])
        assert out["result"] is False


class TestTeamAuthorization:
    """Issue #3430 R2：调用方声明的 group_id 必须落在其授权 team 白名单内。"""

    @classmethod
    def setup_class(cls):
        cls.mod, cls.handlers, cls.models = _load_nats_api()

    def test_missing_team_returns_error(self):
        fn = self.handlers["get_job_mgmt_module_data"]
        out = fn(module="script", child_module=None, page=1, page_size=10, group_id=1)
        assert out["result"] is False
        assert "team" in out["message"]

    def test_empty_team_returns_error(self):
        fn = self.handlers["get_job_mgmt_module_data"]
        out = fn(module="script", child_module=None, page=1, page_size=10, group_id=1, team=[])
        assert out["result"] is False
        assert "team" in out["message"]

    def test_none_team_returns_error(self):
        fn = self.handlers["get_job_mgmt_module_data"]
        out = fn(module="script", child_module=None, page=1, page_size=10, group_id=1, team=None)
        assert out["result"] is False
        assert "team" in out["message"]

    def test_cross_team_access_rejected_before_db_hit(self):
        """调用方仅声明 team=[1]，但 group_id=2 → 在 filter 之前拒绝。

        验证：拒绝路径不触达 .filter()，revert 修复即 fail。
        """
        scripts_qs = _FakeQS(items=[])
        mod, handlers, models = _load_nats_api(scripts_qs=scripts_qs)
        fn = handlers["get_job_mgmt_module_data"]
        out = fn(module="script", child_module=None, page=1, page_size=10, group_id=2, team=[1])
        assert out["result"] is False
        assert "无权" in out["message"]
        # 关键：跨团队拒绝时不应触达 .filter()，否则说明鉴权被绕过
        assert len(scripts_qs.filter_calls) == 0, (
            f"filter was called before auth check; got calls: {scripts_qs.filter_calls}"
        )

    def test_authorized_team_triggers_db_filter(self):
        """调用方声明 team=[1, 2]，group_id=2 → 允许，并触达 .filter(team__contains=2)。"""
        scripts_qs = _FakeQS(items=[])
        mod, handlers, models = _load_nats_api(scripts_qs=scripts_qs)
        fn = handlers["get_job_mgmt_module_data"]
        out = fn(module="script", child_module=None, page=1, page_size=10, group_id=2, team=[1, 2])
        assert "count" in out
        assert out["count"] == 0
        # 关键：合法调用必须触达 filter(team__contains=2)
        assert any("team__contains" in c for c in scripts_qs.filter_calls), (
            f"expected filter(team__contains=2); got: {scripts_qs.filter_calls}"
        )

    def test_team_with_string_ids_normalized(self):
        """team 传入字符串 ID 也应被 normalize_team 规整为 int。"""
        scripts_qs = _FakeQS(items=[])
        mod, handlers, models = _load_nats_api(scripts_qs=scripts_qs)
        fn = handlers["get_job_mgmt_module_data"]
        out = fn(module="script", child_module=None, page=1, page_size=10, group_id=1, team=["1"])
        assert "count" in out


class TestRegressionCompat:
    """修改后既有合法路径仍可工作（保护 Script/Target/JobExecution/DangerousRule/DangerousPath）。"""

    @classmethod
    def setup_class(cls):
        cls.mod, cls.handlers, cls.models = _load_nats_api()

    def test_script_module_with_team(self):
        scripts_qs = _FakeQS(items=[{"id": 1, "name": "s1"}])
        mod, handlers, models = _load_nats_api(scripts_qs=scripts_qs)
        fn = handlers["get_job_mgmt_module_data"]
        out = fn(module="script", child_module=None, page=1, page_size=10, group_id=1, team=[1])
        assert out["count"] == 1
        assert out["items"][0]["name"] == "s1"

    def test_target_module_with_team(self):
        targets_qs = _FakeQS(items=[{"id": 1, "name": "t1"}])
        mod, handlers, models = _load_nats_api(targets_qs=targets_qs)
        fn = handlers["get_job_mgmt_module_data"]
        out = fn(module="target", child_module=None, page=1, page_size=10, group_id=1, team=[1])
        assert out["count"] == 1

    def test_job_execution_module_with_team(self):
        executions_qs = _FakeQS(items=[{"id": 1, "name": "e1"}])
        mod, handlers, models = _load_nats_api(executions_qs=executions_qs)
        fn = handlers["get_job_mgmt_module_data"]
        out = fn(module="job_execution", child_module=None, page=1, page_size=10, group_id=1, team=[1])
        assert out["count"] == 1

    def test_system_dangerous_rule_with_team(self):
        rule_qs = _FakeQS(items=[{"id": 1, "name": "r1"}])
        mod, handlers, models = _load_nats_api(dangerous_rule_qs=rule_qs)
        fn = handlers["get_job_mgmt_module_data"]
        out = fn(module="system", child_module="dangerous_rule", page=1, page_size=10, group_id=1, team=[1])
        assert out["count"] == 1

    def test_system_dangerous_path_with_team(self):
        path_qs = _FakeQS(items=[{"id": 1, "name": "p1"}])
        mod, handlers, models = _load_nats_api(dangerous_path_qs=path_qs)
        fn = handlers["get_job_mgmt_module_data"]
        out = fn(module="system", child_module="dangerous_path", page=1, page_size=10, group_id=1, team=[1])
        assert out["count"] == 1


# ── Direct invocation (Django-free, run via `python <file>.py`) ─────────
if __name__ == "__main__":
    failures = 0
    passed = 0
    for cls in [TestKeyErrorGuard, TestTeamAuthorization, TestRegressionCompat]:
        cls.setup_class()
        inst = cls()
        for name in dir(cls):
            if not name.startswith("test_"):
                continue
            method = getattr(inst, name)
            try:
                method()
                print(f"PASS: {cls.__name__}.{name}")
                passed += 1
            except Exception as e:
                failures += 1
                print(f"FAIL: {cls.__name__}.{name}: {type(e).__name__}: {e}")

    print(f"\n{'=' * 60}")
    print(f"Passed: {passed}, Failed: {failures}")
    sys.exit(1 if failures else 0)
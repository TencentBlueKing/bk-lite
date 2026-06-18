"""
Pure unit tests for JobExecution index definitions — issue #3425.

These tests verify that the model class carries the required index metadata.
No database connection required.
"""

import sys
import types
import importlib.util
from pathlib import Path


def _make_fake_django():
    """Install minimal Django stubs so execution.py can be imported without settings."""
    # django
    django = types.ModuleType("django")
    sys.modules.setdefault("django", django)

    # django.db
    db = types.ModuleType("django.db")
    django.db = db
    sys.modules.setdefault("django.db", db)

    # django.db.models — minimal Field / ForeignKey / Index stubs
    _models = types.ModuleType("django.db.models")

    class _Field:
        def __init__(self, *args, **kwargs):
            self._kwargs = kwargs

        def __set_name__(self, owner, name):
            self.attname = name

    class CharField(_Field):
        pass

    class IntegerField(_Field):
        pass

    class TextField(_Field):
        pass

    class JSONField(_Field):
        pass

    class DateTimeField(_Field):
        pass

    class ForeignKey(_Field):
        pass

    class Index:
        def __init__(self, *, fields, name):
            self.fields = fields
            self.name = name

    class Model:
        pass

    _models.CharField = CharField
    _models.IntegerField = IntegerField
    _models.TextField = TextField
    _models.JSONField = JSONField
    _models.DateTimeField = DateTimeField
    _models.ForeignKey = ForeignKey
    _models.Index = Index
    _models.Model = Model
    _models.SET_NULL = "SET_NULL"

    db.models = _models
    sys.modules["django.db.models"] = _models

    # Stub out ancestor modules used by execution.py
    for stub in [
        "apps",
        "apps.core",
        "apps.core.models",
        "apps.core.models.maintainer_info",
        "apps.core.models.time_info",
        "apps.job_mgmt",
        "apps.job_mgmt.constants",
        "apps.job_mgmt.models",
        "apps.job_mgmt.models.playbook",
        "apps.job_mgmt.models.script",
    ]:
        sys.modules.setdefault(stub, types.ModuleType(stub))

    # MaintainerInfo / TimeInfo — must be distinct classes to avoid "duplicate base class" error
    class MaintainerInfo:
        pass

    class TimeInfo:
        pass

    mi = sys.modules["apps.core.models.maintainer_info"]
    ti = sys.modules["apps.core.models.time_info"]
    mi.MaintainerInfo = MaintainerInfo
    ti.TimeInfo = TimeInfo

    # ExecutionStatus + constants
    class _ExecutionStatus:
        PENDING = "pending"
        RUNNING = "running"
        CHOICES = (("pending", "等待中"), ("running", "执行中"))

    constants = sys.modules["apps.job_mgmt.constants"]
    constants.ExecutionStatus = _ExecutionStatus

    class _JobType:
        CHOICES = ()

    class _TriggerSource:
        MANUAL = "manual"
        CHOICES = ()

    class _OverwriteStrategy:
        OVERWRITE = "overwrite"
        CHOICES = ()

    class _ScriptType:
        CHOICES = ()

    class _TargetSource:
        MANUAL = "manual"
        CHOICES = ()

    constants.JobType = _JobType
    constants.TriggerSource = _TriggerSource
    constants.OverwriteStrategy = _OverwriteStrategy
    constants.ScriptType = _ScriptType
    constants.TargetSource = _TargetSource

    # Playbook / Script stubs
    playbook_mod = sys.modules["apps.job_mgmt.models.playbook"]
    script_mod = sys.modules["apps.job_mgmt.models.script"]
    playbook_mod.Playbook = type("Playbook", (Model,), {})
    script_mod.Script = type("Script", (Model,), {})


def _load_execution_module():
    _make_fake_django()
    path = Path(__file__).parent.parent / "models" / "execution.py"
    spec = importlib.util.spec_from_file_location("job_mgmt.models.execution", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestJobExecutionStatusIndex:
    """Verify that JobExecution.status carries db_index=True (issue #3425)."""

    def setup_method(self):
        self.mod = _load_execution_module()
        self.cls = self.mod.JobExecution

    def test_status_field_has_db_index(self):
        """status 字段必须有 db_index=True，否则过滤查询退化为全表扫描。"""
        # Find the status field instance via class __dict__ (descriptor protocol)
        status_field = None
        for name, value in vars(self.cls).items():
            if name == "status":
                status_field = value
                break
        assert status_field is not None, "JobExecution 中未找到 status 字段"
        assert status_field._kwargs.get("db_index") is True, (
            "JobExecution.status 缺少 db_index=True，并发策略检查和列表过滤会退化为全表扫描"
        )

    def test_composite_index_on_scheduled_task_and_status(self):
        """Meta.indexes 必须包含 (scheduled_task, status) 复合索引。"""
        meta = getattr(self.cls, "Meta", None)
        assert meta is not None, "JobExecution 缺少 Meta 内部类"
        indexes = getattr(meta, "indexes", [])
        assert indexes, "JobExecution.Meta.indexes 为空，缺少复合索引"

        composite = next(
            (idx for idx in indexes if set(idx.fields) == {"scheduled_task", "status"}),
            None,
        )
        assert composite is not None, (
            "Meta.indexes 中缺少 (scheduled_task, status) 复合索引，"
            "SKIP/QUEUE 策略检查仍需扫描该定时任务下所有执行记录"
        )
        assert composite.name == "jobexec_task_status_idx", (
            f"复合索引名应为 jobexec_task_status_idx，实际为 {composite.name}"
        )

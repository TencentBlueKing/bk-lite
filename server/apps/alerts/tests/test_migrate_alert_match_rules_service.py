"""已发布旧规则升级后仍能回显并按当前目录执行。"""

import os
import subprocess
import sys
import textwrap
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.apps import apps
from django.db import connection
from django.db.migrations.state import ProjectState
from django.utils import timezone

from apps.alerts.action.matcher import event_matches as action_matches
from apps.alerts.action.payload import build_rule_payload
from apps.alerts.aggregation.strategy.instant_matcher import InstantMatcher
from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.enrichment.matcher import event_matches as enrichment_matches
from apps.alerts.models import Alert, AlertSource, Event
from apps.alerts.models.alert_operator import AlertAssignment
from apps.alerts.models.models import Level
from apps.alerts.serializers.action import ActionRuleSerializer
from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer, AlertShieldModelSerializer
from apps.alerts.serializers.enrichment import EnrichmentRuleModelSerializer
from apps.alerts.serializers.strategy import AlarmStrategySerializer
from apps.alerts.utils.monitor_source_rules import MonitorSourceRuleMatcher
from apps.alerts.utils.rule_catalog import rules_are_valid
from apps.alerts.utils.typed_rules import matches_payload

migration = import_module("apps.alerts.migrations.0033_migrate_legacy_match_rules")
MODELS = {scope: apps.get_model("alerts", name) for scope, name in migration.MODEL_NAMES.items()}


registry = ProjectState.from_apps(apps).apps


def converter(scope):
    return migration.LegacyRuleConverter(scope, registry, "default")


def run_migration():
    migration.migrate_rules(registry, SimpleNamespace(connection=connection))


@pytest.mark.django_db
def test_migrate_legacy_assignment_level_restores_valid_rule():
    Level.objects.create(level_type="alert", level_id=1, level_name="critical", level_display_name="严重")
    assignment = AlertAssignment.objects.create(name="存量分派", match_type="filter", match_rules=[[{"key": "level", "operator": "eq", "value": ["1"]}]])
    assert not rules_are_valid(assignment.match_rules, "assignment")

    run_migration()

    assignment.refresh_from_db()
    assert assignment.match_rules == [[{"key": "level", "operator": "any_of", "value": ["1"]}]]
    assert rules_are_valid(assignment.match_rules, "assignment")


SCOPES = ["correlation", "assignment", "shield", "enrichment", "action"]
SERIALIZERS = dict(
    zip(
        SCOPES,
        [AlarmStrategySerializer, AlertAssignmentModelSerializer, AlertShieldModelSerializer, EnrichmentRuleModelSerializer, ActionRuleSerializer],
    )
)


@pytest.fixture
def levels(db):
    for kind in ["event", "alert"]:
        for number in [1, 2]:
            Level.objects.create(level_type=kind, level_id=number, level_name=str(number), level_display_name=str(number))


def policy(scope, rules, **kwargs):
    defaults = {"name": f"{scope}-{MODELS[scope].objects.count()}", "match_rules": rules}
    if scope in ["assignment", "shield"]:
        defaults["match_type"] = "filter"
    if scope == "enrichment":
        defaults["input_binding"] = {"model_id": "resource_type", "inst_uuid": "resource_id"}
    return MODELS[scope].objects.create(**(defaults | kwargs))


@pytest.mark.django_db
@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize(
    "key,value",
    [("level", 1), ("resource_type", "host"), ("resource_id", "001"), ("resource_name", "生产,主机"), ("item", "cpu%_load"), ("source_name", "平台A")],
)
@pytest.mark.parametrize("old_operator,new_operator", [("eq", "any_of"), ("ne", "none_of")])
def test_all_entries_legacy_candidates_roundtrip_and_match(scope, key, value, old_operator, new_operator, levels):
    saved = policy(scope, [[{"key": key, "operator": old_operator, "value": value}]])
    initial_updated_at = saved.updated_at
    run_migration()
    saved.refresh_from_db()
    new_key = "source_names" if key == "source_name" and scope in ["assignment", "action"] else key
    expected = [[{"key": new_key, "operator": new_operator, "value": [str(value)]}]]
    assert saved.match_rules == expected and saved.updated_at == initial_updated_at
    serialized = SERIALIZERS[scope](saved).data
    assert serialized["match_rules"] == expected
    validator = SERIALIZERS[scope](saved, data={"match_rules": serialized["match_rules"]}, partial=True)
    assert validator.is_valid(), validator.errors
    actual = [str(value)] if new_key == "source_names" else str(value)
    other = ["other"] if new_key == "source_names" else "other"
    assert matches_payload({new_key: actual}, saved.match_rules, scope) is (old_operator == "eq")
    assert matches_payload({new_key: other}, saved.match_rules, scope) is (old_operator == "ne")
    assert not matches_payload({new_key: None}, saved.match_rules, scope)


@pytest.mark.django_db
@pytest.mark.parametrize("scope", SCOPES)
def test_source_id_migration_uses_correct_identity_and_real_matcher(scope):
    source = AlertSource.objects.create(name="平台,主源", source_id="source-business-code", source_type="restful", secret="test")
    raw_value = source.source_id if scope == "enrichment" else str(source.pk)
    saved = policy(scope, [[{"key": "source_id", "operator": "eq", "value": raw_value}]])
    run_migration()
    saved.refresh_from_db()
    event = Event.objects.create(source=source, event_id="created", title="cpu", level="1", action="created", start_time=timezone.now(), raw_data={})
    recovery = Event.objects.create(
        source=source, event_id="recovery", title="cpu", level="1", action="recovery", start_time=timezone.now(), raw_data={}
    )
    if scope == "correlation":
        assert InstantMatcher.match_in_memory(event, saved.match_rules)
        assert list(StrategyMatcher.match_events_to_strategy(Event.objects.filter(pk=event.pk), saved.match_rules)) == [event]
    elif scope == "shield":
        assert MonitorSourceRuleMatcher({}, source_field="push_source_id").filter_queryset(Event.objects.filter(pk=event.pk), saved.match_rules) == [
            event.pk
        ]
    elif scope == "enrichment":
        assert enrichment_matches({"source_name": source.name}, saved.match_rules)
        assert not enrichment_matches({"source_name": "other"}, saved.match_rules)
    else:
        alert = Alert.objects.create(alert_id="migration", fingerprint="migration", title="cpu", content="", level="1")
        alert.events.add(recovery)
        matcher = MonitorSourceRuleMatcher({}, source_field="push_source_ids")
        assert not matcher.filter_queryset(Alert.objects.all(), saved.match_rules)
        assert not action_matches(build_rule_payload(alert), saved.match_rules)
        alert.events.add(event)
        assert matcher.filter_queryset(Alert.objects.all(), saved.match_rules) == [alert.pk]
        assert action_matches(build_rule_payload(alert), saved.match_rules)


@pytest.mark.django_db
@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("operator", ["eq", "ne"])
def test_monitor_source_candidates_support_scalar_and_set(scope, operator):
    key = "push_source_id" if scope in ["correlation", "shield", "enrichment"] else "push_source_ids"
    saved = policy(scope, [[{"key": key, "operator": operator, "value": "001"}]])
    run_migration()
    saved.refresh_from_db()
    assert saved.match_rules == [[{"key": key, "operator": "any_of" if operator == "eq" else "none_of", "value": ["001"]}]]
    actual = "001" if key == "push_source_id" else ["001", "extra"]
    assert matches_payload({key: actual}, saved.match_rules, scope) is (operator == "eq")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key,operator,value",
    [
        ("title", "re", "^cpu"),
        ("resource_id", "contains", "prod"),
        ("push_source_ids", "contains", "a"),
        ("level", "gt", 1),
        ("labels.ip", "eq", "host"),
        ("title", "eq", ""),
        ("title", "eq", True),
        ("title", None, "cpu"),
        ("level", "eq", "999"),
        ("title", "eq", "x" * 257),
        ("level", "in", "1,2"),
        ("title", "text_any", "cpu"),
        ("push_source_ids", "all_of", "a"),
    ],
)
def test_unsupported_rule_blocks_whole_policy_without_dropping_or_branch(key, operator, value, levels):
    rules = [[{"key": "title", "operator": "contains", "value": "safe"}], [{"key": key, "operator": operator, "value": value}]]
    saved = policy("assignment", rules)
    with pytest.raises(RuntimeError, match=f"scope=assignment id={saved.pk}"):
        run_migration()
    saved.refresh_from_db()
    assert saved.match_rules == rules


@pytest.mark.django_db
def test_source_collision_missing_and_soft_deleted_sources():
    selected = AlertSource.all_objects.create(name="同名", source_id="old", source_type="restful", is_delete=True, secret="test")
    other = AlertSource.objects.create(name="同名", source_id="other", source_type="restful", secret="test")
    convert = converter("assignment").convert
    old = [[{"key": "source_id", "operator": "eq", "value": selected.pk}]]
    with pytest.raises(ValueError, match="同名"):
        convert(old)
    with pytest.raises(ValueError, match="不存在"):
        convert([[{"key": "source_id", "operator": "eq", "value": other.pk + 100}]])
    other.name = "另一个"
    other.save(update_fields=["name"])
    assert convert(old) == [[{"key": "source_names", "operator": "any_of", "value": ["同名"]}]]
    with pytest.raises(ValueError, match="文本或正则"):
        convert([[{"key": "source_id", "operator": "contains", "value": selected.pk}]])


@pytest.mark.django_db
@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize(
    "old_operator,actual,expected",
    [
        ("any_of", "cpu", True),
        ("any_of", "mem", True),
        ("any_of", "none", False),
        ("none_of", "cpu", False),
        ("none_of", "none", True),
        ("text_any", "CPU busy", True),
        ("text_any", "MEM busy", True),
        ("text_any", "none", False),
        ("text_all", "CPU and MEM", True),
        ("text_all", "CPU only", False),
        ("text_none", "none", True),
        ("text_none", "CPU busy", False),
    ],
)
def test_legacy_text_lists_expand_without_changing_group_logic(scope, old_operator, actual, expected):
    old = [
        [
            {"key": "title", "operator": old_operator, "value": ["cpu", "mem"]},
            {"key": "description" if scope in ["correlation", "shield", "enrichment"] else "content", "operator": "contains", "value": "gate"},
        ]
    ]
    rules = converter(scope).convert(old)
    payload = {"title": actual, "description": "gate", "content": "gate"}
    assert matches_payload(payload, rules, scope) is expected
    payload.update(description="no", content="no")
    assert not matches_payload(payload, rules, scope)


@pytest.mark.django_db
def test_expansion_limits_and_valid_current_rules():
    convert = converter("assignment").convert
    rule = {"key": "title", "operator": "any_of", "value": ["a", "b", "c", "d", "e"]}
    with pytest.raises(ValueError, match="20"):
        convert([[rule, rule]])
    with pytest.raises(ValueError, match="100"):
        convert([[{"key": "title", "operator": "eq", "value": "a"}] * 101])
    with pytest.raises(ValueError, match="50"):
        convert([[{"key": "resource_id", "operator": "eq", "value": list(range(51))}]])
    current = [[{"key": "push_source_ids", "operator": "all_of", "value": ["a", "b"]}]]
    assert convert(current) == current
    assert convert([[{"key": "push_source_ids", "operator": "all_of", "value": [1, 2]}]]) == [
        [{"key": "push_source_ids", "operator": "all_of", "value": ["1", "2"]}]
    ]
    assert convert([[{"key": "resource_id", "operator": "eq", "value": ["001", "001", "1"]}]]) == [
        [{"key": "resource_id", "operator": "any_of", "value": ["001", "1"]}]
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "scope,key,operator,value,expected",
    [
        ("correlation", "对象实例", "等于", "主机A", {"key": "resource_name", "operator": "any_of", "value": ["主机A"]}),
        ("shield", "content", "包含", "CPU", {"key": "description", "operator": "contains", "value": "CPU"}),
        ("enrichment", "content", "不包含", "CPU", {"key": "description", "operator": "not_contains", "value": "CPU"}),
        ("correlation", "source", "eq", "平台A", {"key": "source_name", "operator": "any_of", "value": ["平台A"]}),
        ("assignment", "source__name", "ne", "平台A", {"key": "source_names", "operator": "none_of", "value": ["平台A"]}),
        ("action", "resource_name", "regex", "^CPU", {"key": "resource_name", "operator": "re", "value": "^CPU"}),
    ],
)
def test_historical_aliases_keep_their_original_field_identity(scope, key, operator, value, expected):
    assert converter(scope).convert([[{"key": key, "operator": operator, "value": value}]]) == [[expected]]


@pytest.mark.django_db
@pytest.mark.parametrize("operator,expected", [("eq", True), ("ne", False), ("in", True), ("not_in", False)])
def test_old_text_list_equality_and_negation_are_expanded(operator, expected):
    rules = converter("action").convert([[{"key": "title", "operator": operator, "value": ["cpu", "mem"]}]])
    assert matches_payload({"title": "cpu"}, rules, "action") is expected
    assert matches_payload({"title": "other"}, rules, "action") is not expected


@pytest.mark.django_db
@pytest.mark.parametrize("rules", [None, {}, [[]], [[{"key": "title", "value": "sentinel"}]]])
def test_malformed_policies_are_reported_without_write(rules):
    # JSONField 不接受 SQL NULL；转换器仍须拒绝 JSON null 这类输入。
    with pytest.raises(ValueError):
        converter("assignment").convert(rules)


@pytest.mark.django_db
def test_empty_filter_does_not_become_all_and_other_empty_defaults_stay_unchanged():
    policy("assignment", [])
    for scope in ["correlation", "enrichment", "action"]:
        policy(scope, [])
    with pytest.raises(RuntimeError, match="迁移失败"):
        run_migration()
    assert all(model.objects.get().match_rules == [] for key, model in MODELS.items() if key != "shield")


@pytest.mark.django_db
def test_errors_never_print_rule_business_values():
    sentinel = "private-business-sentinel"
    policy("assignment", [[{"key": "title", "operator": "re", "value": sentinel}]])
    with pytest.raises(RuntimeError) as error:
        run_migration()
    assert sentinel not in str(error.value)


@pytest.mark.django_db
def test_migration_failure_rolls_back_all_five_entries_then_can_retry(levels):
    old = [[{"key": "level", "operator": "eq", "value": 1}]]
    saved = [policy(scope, old) for scope in SCOPES]
    broken = policy("action", [[{"key": "title", "operator": "re", "value": "private"}]])
    with pytest.raises(RuntimeError, match=f"scope=action id={broken.pk}"):
        run_migration()
    for obj in saved:
        obj.refresh_from_db()
        assert obj.match_rules == old
    broken.delete()
    run_migration()
    for obj in saved:
        obj.refresh_from_db()
        assert obj.match_rules == [[{"key": "level", "operator": "any_of", "value": ["1"]}]]


@pytest.mark.django_db
def test_batches_idempotency_and_unrelated_configuration(levels):
    old = [[{"key": "level", "operator": "eq", "value": 1}]]
    historical_model = registry.get_model("alerts", "AlertAssignment")
    historical_model.objects.bulk_create(
        [
            historical_model(name=f"legacy-{i}", match_type="filter", match_rules=old, priority=37, personnel=["alice"], is_active=False)
            for i in range(405)
        ]
    )
    timestamps = list(historical_model.objects.order_by("pk").values_list("pk", "updated_at"))
    ignored = policy("assignment", old, match_type="all")
    run_migration()
    assert historical_model.objects.exclude(pk=ignored.pk).count() == 405
    assert all(
        row.match_rules == [[{"key": "level", "operator": "any_of", "value": ["1"]}]]
        and row.priority == 37
        and row.personnel == ["alice"]
        and not row.is_active
        for row in historical_model.objects.exclude(pk=ignored.pk)
    )
    ignored.refresh_from_db()
    assert ignored.match_rules == old
    assert list(historical_model.objects.exclude(pk=ignored.pk).order_by("pk").values_list("pk", "updated_at")) == timestamps
    with patch("django.db.models.query.QuerySet.update", side_effect=AssertionError("重复迁移不应更新")):
        run_migration()


@pytest.mark.django_db
def test_frozen_migration_does_not_depend_on_runtime_catalog_or_model_managers():
    old = [[{"key": "resource_type", "operator": "eq", "value": "host"}]]
    saved = policy("assignment", old)
    with patch("apps.alerts.utils.rule_catalog.FIELDS", {}), patch.object(AlertAssignment.objects, "using", side_effect=AssertionError("运行期模型")):
        run_migration()
    saved.refresh_from_db()
    assert saved.match_rules == [[{"key": "resource_type", "operator": "any_of", "value": ["host"]}]]


def test_real_migration_executor_upgrade_once_failure_retry_and_empty_database():
    # 独立数据库按 0032 历史状态建表；只对 0033 使用真实执行器与迁移记录。
    # 0009 在 SQLite 删字段时残留索引，完整历史链的基线失败单独记入迁移说明。
    script = textwrap.dedent(
        """
        import django
        from django.conf import settings
        # 项目 SQLite 配置可能将 DB_NAME 与目录拼接；这里显式保证是独立内存库。
        settings.DATABASES['default'] = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
        django.setup()
        from django.apps import apps
        from django.conf import settings
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        from django.db.migrations.exceptions import IrreversibleError
        from django.db.migrations.recorder import MigrationRecorder
        from unittest.mock import patch
        from importlib import import_module

        settings.MIGRATION_MODULES = {app.label: None for app in apps.get_app_configs()}
        settings.MIGRATION_MODULES['alerts'] = 'apps.alerts.migrations'
        before = [('alerts', '0032_alertassignment_priority')]
        after = [('alerts', '0033_migrate_legacy_match_rules')]
        def prepare_previous_schema():
            executor = MigrationExecutor(connection)
            historical = executor.loader.project_state(before).apps
            with connection.schema_editor() as editor:
                for model in historical.get_app_config('alerts').get_models():
                    editor.create_model(model)
            recorder = MigrationRecorder(connection)
            for migration_key in executor.loader.graph.forwards_plan(before[0]):
                recorder.record_applied(*migration_key)
            return historical
        historical = prepare_previous_schema()
        source = historical.get_model('alerts', 'AlertSource')._base_manager.create(
            name='旧平台', source_id='business-code', source_type='restful', secret='test', is_delete=True)
        old = [[{'key': 'source_id', 'operator': 'eq', 'value': source.pk}]]
        assignment = historical.get_model('alerts', 'AlertAssignment').objects.create(
            name='客户旧分派', match_type='filter', match_rules=old, priority=37)
        broken = historical.get_model('alerts', 'ActionRule').objects.create(
            name='旧正则', match_rules=[[{'key': 'title', 'operator': 're', 'value': '^cpu'}]])
        try:
            MigrationExecutor(connection).migrate(after)
        except RuntimeError as error:
            assert 'scope=action' in str(error)
        else:
            raise AssertionError('不可转换规则应回滚并拒绝记录迁移成功')
        assignment.refresh_from_db()
        assert assignment.match_rules == old
        assert not MigrationRecorder(connection).migration_qs.filter(app='alerts', name=after[0][1]).exists()
        broken.delete()
        MigrationExecutor(connection).migrate(after)
        assignment.refresh_from_db()
        assert assignment.match_rules == [[{'key': 'source_names', 'operator': 'any_of', 'value': ['旧平台']}]]
        assert assignment.priority == 37
        assert MigrationRecorder(connection).migration_qs.filter(app='alerts', name=after[0][1]).count() == 1
        module = import_module('apps.alerts.migrations.0033_migrate_legacy_match_rules')
        with patch.object(module.LegacyRuleConverter, 'convert', side_effect=AssertionError('已经执行过')):
            executor = MigrationExecutor(connection)
            assert executor.migration_plan(after) == []
            executor.migrate(after)
        try:
            MigrationExecutor(connection).migrate(before)
        except IrreversibleError:
            pass
        else:
            raise AssertionError('有损转换不得伪造逆迁移')
        # 使用第二个内存库验证没有存量规则的升级路径。
        connection.close()
        connection.connection.close()
        connection.connection = None
        historical = prepare_previous_schema()
        MigrationExecutor(connection).migrate(after)
        assert MigrationRecorder(connection).migration_qs.filter(app='alerts', name=after[0][1]).count() == 1
        assert historical.get_model('alerts', 'AlertAssignment').objects.count() == 0
    """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "DB_ENGINE": "sqlite",
            "DB_NAME": ":memory:",
            "SECRET_KEY": "migration-test",
            "ENABLE_CELERY": "true",
            "CELERY_BROKER_URL": "memory://",
            "CELERY_RESULT_BACKEND": "cache+memory://",
        },
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr

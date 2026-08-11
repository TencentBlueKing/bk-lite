import io
import json

import pytest
from django.core.management import CommandError, call_command

from apps.log.models.log_group import LogGroup, LogGroupOrganization


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _group(group_id, mode, *, created_by="owner"):
    rule = {"conditions": [{"field": "cluster", "op": "==", "value": "prod"}]}
    if mode is not ...:
        rule["mode"] = mode
    return LogGroup.objects.create(id=group_id, name=f"group-{group_id}", rule=rule, created_by=created_by)


def test_audit_command_reports_only_identifiers_and_scope_without_full_rules():
    valid = _group("g-valid", "AND")
    legacy = _group("g-legacy", "ADN", created_by="legacy-owner")
    invalid = _group("g-invalid", None)
    LogGroupOrganization.objects.create(log_group=valid, organization=1)
    LogGroupOrganization.objects.create(log_group=legacy, organization=2)
    LogGroupOrganization.objects.create(log_group=legacy, organization=3)
    LogGroupOrganization.objects.create(log_group=invalid, organization=4)
    stdout = io.StringIO()

    call_command("audit_log_group_rule_modes", format="jsonl", batch_size=1, stdout=stdout)

    records = [json.loads(line) for line in stdout.getvalue().splitlines()]
    findings = [record for record in records if record["type"] == "finding"]
    summary = records[-1]
    assert findings == [
        {
            "type": "finding",
            "classification": "invalid",
            "covered_by_legacy_or": False,
            "id": "g-invalid",
            "name": "group-g-invalid",
            "created_by": "owner",
            "organizations": [4],
        },
        {
            "type": "finding",
            "classification": "legacy_or",
            "covered_by_legacy_or": False,
            "id": "g-legacy",
            "name": "group-g-legacy",
            "created_by": "legacy-owner",
            "organizations": [2, 3],
        },
    ]
    assert summary == {"type": "summary", "valid": 1, "legacy_or": 1, "invalid": 1, "uncovered": 2}
    assert "cluster" not in stdout.getvalue()
    assert "prod" not in stdout.getvalue()
    assert "ADN" not in stdout.getvalue()


def test_audit_command_can_fail_a_preflight_when_invalid_rules_exist():
    _group("g-legacy", "ADN")

    with pytest.raises(CommandError, match="legacy_or=1"):
        call_command("audit_log_group_rule_modes", format="jsonl", fail_on_invalid=True, stdout=io.StringIO())


def test_audit_command_strict_preflight_accepts_explicit_legacy_coverage(settings):
    settings.LOG_GROUP_LEGACY_OR_GROUP_IDS = frozenset({"g-legacy"})
    _group("g-legacy", "ADN")
    stdout = io.StringIO()

    call_command("audit_log_group_rule_modes", format="jsonl", fail_on_uncovered=True, stdout=stdout)

    records = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert records[0]["covered_by_legacy_or"] is True
    assert records[-1]["uncovered"] == 0


def test_audit_command_strict_preflight_rejects_falsey_non_object_rule():
    LogGroup.objects.create(id="g-invalid", name="invalid", rule=[])

    with pytest.raises(CommandError, match="uncovered=1"):
        call_command("audit_log_group_rule_modes", format="jsonl", fail_on_uncovered=True, stdout=io.StringIO())


def test_audit_command_strict_preflight_rejects_malformed_conditions():
    LogGroup.objects.create(id="g-invalid", name="invalid", rule={"mode": "AND", "conditions": ""})

    with pytest.raises(CommandError, match="uncovered=1"):
        call_command("audit_log_group_rule_modes", format="jsonl", fail_on_uncovered=True, stdout=io.StringIO())


def test_audit_command_strict_preflight_rejects_logs_query_injection_rule():
    LogGroup.objects.create(
        id="g-injection",
        name="injection",
        rule={
            "mode": "AND",
            "conditions": [{"field": "cluster", "op": "==", "value": 'prod") OR (*) OR (cluster:"prod'}],
        },
    )

    with pytest.raises(CommandError, match="uncovered=1"):
        call_command("audit_log_group_rule_modes", format="jsonl", fail_on_uncovered=True, stdout=io.StringIO())


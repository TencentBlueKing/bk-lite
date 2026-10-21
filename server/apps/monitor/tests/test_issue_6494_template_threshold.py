"""Issue 6494：模板更新和覆盖同步必须在写库前拒绝非法阈值。"""

import io
import json
import zipfile

import pytest

import apps.node_mgmt  # noqa: F401 - monitor 启动会加载 nats，依赖 node_mgmt
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.models import MonitorObject, MonitorPlugin, MonitorPolicy, PolicyTemplate
from apps.monitor.services.policy import PolicyService

pytestmark = pytest.mark.django_db

LEGAL_THRESHOLD = [{"level": "warning", "value": 80, "method": ">="}]
UPDATED_THRESHOLD = [{"level": "warning", "value": 70, "method": ">"}]
BOGUS_THRESHOLD = [{"level": "warning", "value": 90, "method": "bogus"}]


def _user():
    return type("User", (), {"username": "tester", "domain": "domain.com"})()


def _catalog(name):
    monitor_object = MonitorObject.objects.create(name=name, level="base")
    plugin = MonitorPlugin.objects.create(name=f"{name}Plugin", collector="Telegraf", collect_type="host")
    plugin.monitor_object.add(monitor_object)
    return monitor_object, plugin


def _issued_template(name, *, organization=1, policy_count=1):
    monitor_object, plugin = _catalog(name)
    template = PolicyTemplate.objects.create(
        key=f"{name}-key",
        scope_key=f"custom:{organization}",
        template_type=PolicyTemplate.TYPE_CUSTOM,
        organization=organization,
        monitor_object=monitor_object,
        plugin=plugin,
        name="CPU 模板",
        description="原描述",
        config={
            "alert_name": "CPU 告警",
            "query_condition": {"type": "pmq", "query": "up"},
            "threshold": list(LEGAL_THRESHOLD),
        },
    )
    policies = [
        MonitorPolicy.objects.create(
            monitor_object=monitor_object,
            name=f"已下发策略-{index}",
            algorithm="avg",
            enable=True,
            source_template=template,
            threshold=list(LEGAL_THRESHOLD),
            source={"type": "instance", "values": []},
        )
        for index in range(policy_count)
    ]
    return template, policies


def _update(template, threshold, *, name="CPU 模板", organization=1):
    config = {
        "alert_name": "CPU 告警",
        "query_condition": {"type": "pmq", "query": "up"},
        "threshold": threshold,
    }
    return PolicyService.update_custom_template(
        organization=organization,
        template_key=f"custom:{template.id}",
        name=name,
        description="原描述",
        config=config,
        user=_user(),
    )


def _archive_with_threshold(template, organization, *, name, threshold):
    source = PolicyService.export_archive([f"custom:{template.id}"], organization)
    output = io.BytesIO()
    with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(output, "w") as outgoing:
        for info in incoming.infolist():
            payload = incoming.read(info.filename)
            if info.filename.startswith("templates/") and info.filename.endswith(".json"):
                data = json.loads(payload)
                data["name"] = name
                data["config"]["threshold"] = threshold
                payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            outgoing.writestr(info.filename, payload)
    output.seek(0)
    return output


def test_update_custom_template_rejects_bogus_threshold_before_sync(mocker):
    template, policies = _issued_template("Issue6494Update")
    policy = policies[0]
    sync = mocker.spy(PolicyService, "sync_issued_policies_from_template")

    raised = None
    try:
        _update(template, BOGUS_THRESHOLD, name="被污染的模板")
    except ValidationAppException as exc:
        raised = exc

    template.refresh_from_db()
    policy.refresh_from_db()
    assert raised is not None and raised.STATUS_CODE == 400, (
        f"非法阈值已落库 template={template.config.get('threshold')} "
        f"policy={policy.threshold} name={template.name} sync_calls={sync.call_count}"
    )
    assert sync.call_count == 0
    assert template.name == "CPU 模板"
    assert template.config["threshold"] == LEGAL_THRESHOLD
    assert policy.threshold == LEGAL_THRESHOLD
    assert policy.enable is True


def test_sync_issued_policies_rejects_bogus_threshold_before_any_write():
    template, policies = _issued_template("Issue6494Sync", policy_count=2)
    template.config = {**template.config, "threshold": list(BOGUS_THRESHOLD)}
    template.save(update_fields=["config"])

    with pytest.raises(ValidationAppException) as exc_info:
        PolicyService.sync_issued_policies_from_template(template, _user())

    assert exc_info.value.STATUS_CODE == 400
    for policy in policies:
        policy.refresh_from_db()
        assert policy.threshold == LEGAL_THRESHOLD


def test_import_overwrite_rolls_back_bogus_threshold():
    template, policies = _issued_template("Issue6494Import", organization=7)
    policy = policies[0]
    archive = _archive_with_threshold(
        template,
        7,
        name="被污染的模板",
        threshold=list(BOGUS_THRESHOLD),
    )

    with pytest.raises(ValidationAppException) as exc_info:
        PolicyService.import_archive(archive, organization=7, user=_user(), overwrite=True)

    assert exc_info.value.STATUS_CODE == 400
    template.refresh_from_db()
    policy.refresh_from_db()
    assert template.name == "CPU 模板"
    assert template.config["threshold"] == LEGAL_THRESHOLD
    assert policy.threshold == LEGAL_THRESHOLD


def test_update_custom_template_syncs_legal_threshold():
    template, policies = _issued_template("Issue6494Legal")
    policy = policies[0]

    updated, updated_policy_count = _update(template, UPDATED_THRESHOLD, name="CPU 模板已更新")

    template.refresh_from_db()
    policy.refresh_from_db()
    assert updated.id == template.id
    assert updated_policy_count == 1
    assert template.name == "CPU 模板已更新"
    assert template.config["threshold"] == UPDATED_THRESHOLD
    assert policy.threshold == UPDATED_THRESHOLD


def test_update_custom_template_allows_empty_threshold():
    template, policies = _issued_template("Issue6494Empty")
    policy = policies[0]

    _, updated_policy_count = _update(template, [])

    template.refresh_from_db()
    policy.refresh_from_db()
    assert updated_policy_count == 1
    assert template.config["threshold"] == []
    assert policy.threshold == []

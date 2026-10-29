"""用户同步按映射写入标准档案和禁用，目录消失的用户仍然删除。"""

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password

from apps.system_mgmt.models import IntegrationInstance, User, UserFieldDefinition, UserFieldValue, UserSyncSource
from apps.system_mgmt.models.user import EmploymentStatus
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services.user_sync_service import execute_user_sync

pytestmark = pytest.mark.django_db


@pytest.fixture
def source(db):
    instance = IntegrationInstance.objects.create(
        name="profile-sync",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
    )
    source = UserSyncSource.objects.create(
        name="profile-sync-source",
        integration_instance=instance,
        enabled=True,
        root_group_name="placeholder",
        business_config={"root_department_id": "0"},
        field_mapping={
            "username": "user_id",
            "display_name": "name",
            "job_title": "title",
            "job_level": "level",
            "employee_no": "employee_no",
            "manager": "manager",
            "employment_status": "staff_status",
            "account_expires_at": "account_expires_at",
            "badge_no": "badge",
        },
        schedule_config={"mode": "disabled"},
    )
    source.root_group_name = f"Profile Sync Root {source.id}"
    source.save(update_fields=["root_group_name"])
    return source


def _user(source, username, **kwargs):
    defaults = dict(
        user_id=str(uuid.uuid4()),
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password=make_password(""),
        domain="domain.com",
        group_list=[],
        sync_source=source,
    )
    defaults.update(kwargs)
    return User.objects.create(**defaults)


def _run(source, user_list):
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={"group_list": [], "user_list": user_list},
    )
    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_user_sync(source.id)
    assert result["result"] is True
    return result


def test_missing_directory_user_is_deleted(source):
    gone = _user(
        source,
        "gone",
        disabled=True,
        job_title="工程师",
        employment_status=EmploymentStatus.EMPLOYED,
    )
    _run(source, [])
    assert not User.objects.filter(id=gone.id).exists()


def test_unmapped_sync_keeps_local_disable(source):
    person = _user(source, "person", disabled=True, job_title="工程师")
    _run(source, [{"user_id": "person", "name": "person", "department_ids": ["0"]}])
    person.refresh_from_db()
    assert person.disabled is True
    assert person.job_title == "工程师"


def test_mapped_disable_value_updates_disabled(source):
    source.field_mapping = {**source.field_mapping, "disabled": "account_disabled"}
    source.save(update_fields=["field_mapping"])
    person = _user(source, "person", disabled=False)
    _run(
        source,
        [
            {
                "user_id": "person",
                "name": "person",
                "department_ids": ["0"],
                "account_disabled": "禁用",
            }
        ],
    )
    person.refresh_from_db()
    assert person.disabled is True

    _run(
        source,
        [
            {
                "user_id": "person",
                "name": "person",
                "department_ids": ["0"],
                "account_disabled": "启用",
            }
        ],
    )
    person.refresh_from_db()
    assert person.disabled is False


def test_blank_or_unrecognized_disable_value_does_not_change_disabled(source):
    source.field_mapping = {**source.field_mapping, "disabled": "account_disabled"}
    source.save(update_fields=["field_mapping"])
    person = _user(source, "person", disabled=True)
    _run(
        source,
        [
            {
                "user_id": "person",
                "name": "person",
                "department_ids": ["0"],
                "account_disabled": "",
            }
        ],
    )
    person.refresh_from_db()
    assert person.disabled is True
    _run(
        source,
        [
            {
                "user_id": "person",
                "name": "person",
                "department_ids": ["0"],
                "account_disabled": "maybe",
            }
        ],
    )
    person.refresh_from_db()
    assert person.disabled is True


def test_blank_profile_values_do_not_overwrite_local_fields(source):
    boss = _user(None, "boss")
    person = _user(source, "person", job_title="工程师", job_level="P6", employee_no="E1", manager=boss)
    _run(
        source,
        [
            {
                "user_id": "person",
                "name": "person",
                "department_ids": ["0"],
                "title": "",
                "level": "",
                "employee_no": "",
                "manager": "",
            }
        ],
    )
    person.refresh_from_db()
    assert person.job_title == "工程师"
    assert person.job_level == "P6"
    assert person.employee_no == "E1"
    assert person.manager_id == boss.id


def test_unresolved_manager_and_status_do_not_drop_the_user(source):
    person = _user(source, "person", job_title="旧职位")
    _run(
        source,
        [
            {
                "user_id": "person",
                "name": "person",
                "department_ids": ["0"],
                "title": "新职位",
                "manager": "missing-boss",
                "staff_status": "unknown",
                "account_expires_at": "not-a-date",
            }
        ],
    )
    person.refresh_from_db()
    assert person.sync_source_id == source.id
    assert person.job_title == "新职位"
    assert person.manager_id is None
    assert person.employment_status == EmploymentStatus.UNSPECIFIED
    assert person.account_expires_at is None


def test_manager_cycle_keeps_the_previous_manager(source):
    boss = _user(source, "boss")
    person = _user(source, "person", manager=boss)
    boss.manager = person
    boss.save(update_fields=["manager"])
    _run(
        source,
        [
            {"user_id": "boss", "name": "boss", "department_ids": ["0"]},
            {
                "user_id": "person",
                "name": "person",
                "department_ids": ["0"],
                "manager": "person",
            },
        ],
    )
    person.refresh_from_db()
    assert person.manager_id == boss.id


def test_unparseable_custom_number_is_skipped(source):
    definition = UserFieldDefinition.objects.create(name="工牌", key="badge_no", field_type="number")
    person = _user(source, "person")
    UserFieldValue.objects.create(user=person, field=definition, value="7")
    _run(source, [{"user_id": "person", "name": "person", "department_ids": ["0"], "badge": "abc"}])
    stored = UserFieldValue.objects.get(user=person, field=definition)
    assert stored.value == "7"


def test_disabled_custom_field_is_not_written_by_sync(source):
    definition = UserFieldDefinition.objects.create(
        name="工牌",
        key="badge_no",
        field_type="text",
        is_enabled=False,
    )
    person = _user(source, "person")
    UserFieldValue.objects.create(user=person, field=definition, value="kept")
    _run(source, [{"user_id": "person", "name": "person", "department_ids": ["0"], "badge": "replaced"}])
    stored = UserFieldValue.objects.get(user=person, field=definition)
    assert stored.value == "kept"


def test_unchanged_profile_does_not_rewrite_the_user(source):
    person = _user(source, "person", display_name="person", job_title="工程师")
    payload = [{"user_id": "person", "name": "person", "department_ids": ["0"], "title": "工程师"}]
    _run(source, payload)
    person.refresh_from_db()
    calls = []
    real_bulk_update = User.objects.bulk_update

    def record_bulk_update(*args, **kwargs):
        calls.append(args[0] if args else kwargs.get("objs"))
        return real_bulk_update(*args, **kwargs)

    with patch.object(User.objects, "bulk_update", side_effect=record_bulk_update):
        _run(source, payload)
    assert calls == []


def test_existing_disabled_user_keeps_only_disabled_flag():
    user = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="legacy-disabled",
        display_name="legacy-disabled",
        email="legacy-disabled@example.com",
        password=make_password(""),
        domain="domain.com",
        group_list=[],
        disabled=True,
    )
    user.refresh_from_db()
    assert user.disabled is True
    assert not hasattr(user, "manual_disabled")
    assert not hasattr(user, "sync_disabled")
    assert user.employment_status == EmploymentStatus.UNSPECIFIED
    assert user.account_expires_at is None

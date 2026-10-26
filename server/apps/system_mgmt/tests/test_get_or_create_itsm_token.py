import hashlib
import logging
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.system_mgmt.models import SystemAPIToken
from apps.system_mgmt.services.itsm_system_token import ITSM_SYSTEM_ID, ITSM_TOKEN_NAME

_CREATED_LOG = "event=itsm_system_token_created system_id=%s token_id=%s"
_EXISTS_LOG = "event=itsm_system_token_exists system_id=%s token_id=%s"
_REPLACED_LOG = "event=itsm_system_token_replaced system_id=%s token_id=%s"
_REJECTED_LOG = "event=itsm_system_token_rejected failed_stage=%s error_type=%s"
_REJECTED_ROW_LOG = "event=itsm_system_token_rejected failed_stage=%s error_type=%s system_id=%s token_id=%s"
_VALID_KEY = "bksys_" + "ab" * 32
_OTHER_KEY = "bksys_" + "cd" * 32
_INVALID_KEY = "bksys_NOT-A-SECRET-SENTINEL"


def _run(key):
    stdout = StringIO()
    call_command("get_or_create_itsm_token", key=key, stdout=stdout)
    return stdout.getvalue()


def _hash(secret):
    return "sha256$" + hashlib.sha256(secret.encode()).hexdigest()


def _store(**kwargs):
    secret = kwargs.pop("secret")
    return SystemAPIToken.objects.create(
        system_id=kwargs.get("system_id", ITSM_SYSTEM_ID),
        name=kwargs.get("name", ITSM_TOKEN_NAME),
        secret_hash=_hash(secret),
        scope=kwargs.get("scope", {"mode": "allowlist", "endpoints": ["GET itsm/orders"]}),
        enabled=kwargs.get("enabled", False),
        expires_at=kwargs.get("expires_at", timezone.now() - timedelta(days=1)),
        created_by="admin",
    )


@pytest.mark.django_db
def test_command_stores_hash_and_prints_created(caplog):
    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        output = _run(_VALID_KEY)

    assert output == "created\n"
    row = SystemAPIToken.objects.get()
    assert row.system_id == ITSM_SYSTEM_ID
    assert row.name == ITSM_TOKEN_NAME
    assert row.secret_hash == _hash(_VALID_KEY)
    assert _VALID_KEY not in row.secret_hash
    assert row.scope == {"mode": "all"}
    assert row.enabled is True
    assert row.expires_at is None
    assert SystemAPIToken.find_live_by_secret(_VALID_KEY).pk == row.pk

    created = [record for record in caplog.records if record.msg == _CREATED_LOG]
    assert len(created) == 1
    assert created[0].args == (ITSM_SYSTEM_ID, row.pk)
    rendered = created[0].getMessage()
    assert rendered == f"event=itsm_system_token_created system_id={ITSM_SYSTEM_ID} token_id={row.pk}"
    formatted = logging.Formatter("%(levelname)s %(message)s").format(created[0])
    assert _VALID_KEY not in rendered
    assert _VALID_KEY not in formatted
    assert _VALID_KEY not in str(created[0].args)
    assert _VALID_KEY not in caplog.text
    assert not [record for record in caplog.records if record.exc_info]


@pytest.mark.django_db
def test_same_key_prints_exists_and_leaves_the_row_unchanged(caplog):
    row = _store(secret=_VALID_KEY)
    original = (row.secret_hash, row.name, row.scope, row.enabled, row.expires_at, row.updated_at)

    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        output = _run(_VALID_KEY)

    row.refresh_from_db()
    assert output == "exists\n"
    assert SystemAPIToken.objects.count() == 1
    assert (row.secret_hash, row.name, row.scope, row.enabled, row.expires_at, row.updated_at) == original
    reused = [record for record in caplog.records if record.msg == _EXISTS_LOG]
    assert len(reused) == 1
    assert reused[0].args == (ITSM_SYSTEM_ID, row.pk)
    assert reused[0].getMessage() == f"event=itsm_system_token_exists system_id={ITSM_SYSTEM_ID} token_id={row.pk}"
    assert _VALID_KEY not in caplog.text


@pytest.mark.django_db
def test_second_call_after_create_does_not_add_a_row():
    assert _run(_VALID_KEY) == "created\n"
    assert _run(_VALID_KEY) == "exists\n"
    assert SystemAPIToken.objects.count() == 1


@pytest.mark.django_db
def test_invalid_key_is_rejected_without_echoing_it(caplog):
    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        with pytest.raises(CommandError, match="格式不正确") as exc_info:
            _run(_INVALID_KEY)

    assert SystemAPIToken.objects.count() == 0
    assert _INVALID_KEY not in str(exc_info.value)
    assert _INVALID_KEY not in caplog.text
    rejected = [record for record in caplog.records if record.msg == _REJECTED_LOG]
    assert len(rejected) == 1
    assert rejected[0].args == ("validate_key", "ItsmSystemTokenError")
    assert rejected[0].levelno == logging.WARNING
    assert not [record for record in caplog.records if record.exc_info]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key",
    [
        "",
        "ab" * 32,
        "bksys_" + "AB" * 32,
        "bksys_" + "ab" * 31,
        "bksys_" + "ab" * 32 + "a",
        "sha256$" + "ab" * 32,
    ],
)
def test_non_canonical_keys_are_rejected(key):
    with pytest.raises(CommandError, match="格式不正确"):
        _run(key)
    assert SystemAPIToken.objects.count() == 0


@pytest.mark.django_db
def test_key_bound_to_another_system_is_not_reused(caplog):
    row = _store(secret=_VALID_KEY, system_id="cmdb", name="cmdb")
    original_hash = row.secret_hash

    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        with pytest.raises(CommandError, match="已绑定其他系统") as exc_info:
            _run(_VALID_KEY)

    row.refresh_from_db()
    assert SystemAPIToken.objects.count() == 1
    assert row.secret_hash == original_hash
    assert _VALID_KEY not in str(exc_info.value)
    assert _VALID_KEY not in caplog.text
    rejected = [record for record in caplog.records if record.msg == _REJECTED_ROW_LOG]
    assert rejected[0].args == ("lookup", "ItsmSystemTokenError", "cmdb", row.pk)
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.django_db
def test_different_key_replaces_only_the_secret_hash(caplog):
    row = _store(secret=_OTHER_KEY)
    kept = (row.pk, row.name, row.scope, row.enabled, row.expires_at)

    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        output = _run(_VALID_KEY)

    row.refresh_from_db()
    assert output == "replaced\n"
    assert SystemAPIToken.objects.count() == 1
    assert (row.pk, row.name, row.scope, row.enabled, row.expires_at) == kept
    assert row.secret_hash == _hash(_VALID_KEY)
    assert SystemAPIToken.find_by_secret_including_disabled(_VALID_KEY).pk == row.pk
    assert SystemAPIToken.find_by_secret_including_disabled(_OTHER_KEY) is None
    assert _run(_VALID_KEY) == "exists\n"
    replaced = [record for record in caplog.records if record.msg == _REPLACED_LOG]
    assert len(replaced) == 1
    assert replaced[0].args == (ITSM_SYSTEM_ID, row.pk)
    rendered = replaced[0].getMessage()
    assert rendered == f"event=itsm_system_token_replaced system_id={ITSM_SYSTEM_ID} token_id={row.pk}"
    assert _VALID_KEY not in rendered
    assert _OTHER_KEY not in rendered
    assert _VALID_KEY not in caplog.text
    assert _OTHER_KEY not in caplog.text
    assert not [record for record in caplog.records if record.exc_info]


@pytest.mark.django_db
def test_key_bound_to_another_itsm_name_does_not_replace_the_target(caplog):
    other = _store(secret=_VALID_KEY, name="page-token")
    target = _store(secret=_OTHER_KEY)
    target_hash = target.secret_hash

    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        with pytest.raises(CommandError, match="已绑定其他系统"):
            _run(_VALID_KEY)

    other.refresh_from_db()
    target.refresh_from_db()
    assert other.secret_hash == _hash(_VALID_KEY)
    assert target.secret_hash == target_hash
    assert _VALID_KEY not in caplog.text

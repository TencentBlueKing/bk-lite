import logging

import pytest

from apps.system_mgmt.services.credential_ref_count import (
    INQUIRY_FAILED_TEMPLATE,
    INQUIRY_FINISHED_TEMPLATE,
    INQUIRY_STARTED_TEMPLATE,
    assert_credential_unreferenced,
    attach_public_refs,
    list_ref_chips,
    parse_counts,
    query_module_counts,
)
from apps.system_mgmt.services.credential_service import CredentialServiceError

pytestmark = pytest.mark.unit

SSH_A = "crd-ssh-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SSH_B = "crd-ssh-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _ok(counts):
    return lambda ids, **kwargs: {"result": True, "data": {"counts": counts}}


def test_parse_counts_requires_explicit_zero_and_rejects_invalid():
    assert parse_counts({"result": True, "data": {"counts": {SSH_A: 2, SSH_B: 0}}}, [SSH_A, SSH_B]) == {
        SSH_A: 2,
        SSH_B: 0,
    }
    with pytest.raises(ValueError):
        parse_counts({"result": True, "data": {"counts": {SSH_A: 2}}}, [SSH_A, SSH_B])
    with pytest.raises(ValueError):
        parse_counts({"result": False, "data": {"counts": {SSH_A: 0}}}, [SSH_A])
    with pytest.raises(ValueError):
        parse_counts({"result": True, "data": {"counts": {SSH_A: -1}}}, [SSH_A])


def test_list_shows_dash_when_all_modules_fail_and_chips_when_one_succeeds():
    failed = lambda ids, **kwargs: (_ for _ in ()).throw(TimeoutError("rpc"))
    assert list_ref_chips([SSH_A], queriers=(("cmdb", failed), ("monitor", failed))) == {SSH_A: None}
    chips = list_ref_chips(
        [SSH_A, SSH_B],
        queriers=(
            ("cmdb", _ok({SSH_A: 2, SSH_B: 0})),
            ("monitor", failed),
        ),
    )
    assert chips[SSH_A] == [{"module": "cmdb", "count": 2}]
    assert chips[SSH_B] == []


def test_assert_unreferenced_fail_closed_on_timeout_or_positive_count():
    failed = lambda ids, **kwargs: (_ for _ in ()).throw(TimeoutError("rpc"))
    with pytest.raises(CredentialServiceError) as timeout_exc:
        assert_credential_unreferenced(SSH_A, queriers=(("cmdb", failed), ("monitor", _ok({SSH_A: 0}))))
    assert timeout_exc.value.code == "in_use"
    with pytest.raises(CredentialServiceError) as used_exc:
        assert_credential_unreferenced(
            SSH_A,
            queriers=(("cmdb", _ok({SSH_A: 1})), ("monitor", _ok({SSH_A: 0}))),
        )
    assert used_exc.value.code == "in_use"
    assert_credential_unreferenced(
        SSH_A,
        queriers=(("cmdb", _ok({SSH_A: 0})), ("monitor", _ok({SSH_A: 0}))),
    )


def test_attach_public_refs_and_inquiry_logs_omit_credential_ids(caplog):
    secret = "crd-ssh-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    def failed(ids, **kwargs):
        raise TimeoutError(secret)

    with caplog.at_level(logging.INFO, logger="system-manager"):
        counts = query_module_counts([secret], queriers=(("cmdb", failed), ("monitor", _ok({secret: 0}))))
    assert counts == {"cmdb": None, "monitor": {secret: 0}}

    started = [record for record in caplog.records if record.msg == INQUIRY_STARTED_TEMPLATE]
    finished = [record for record in caplog.records if record.msg == INQUIRY_FINISHED_TEMPLATE]
    failed_records = [record for record in caplog.records if record.msg == INQUIRY_FAILED_TEMPLATE]
    assert [(record.args, record.getMessage()) for record in started] == [
        (
            ("cmdb_count_credential_refs", "cmdb", 1),
            "event=credential_ref_count_inquiry_started method=cmdb_count_credential_refs module=cmdb id_count=1",
        ),
        (
            ("monitor_count_credential_refs", "monitor", 1),
            "event=credential_ref_count_inquiry_started method=monitor_count_credential_refs module=monitor id_count=1",
        ),
    ]
    assert failed_records[0].levelno == logging.WARNING
    assert failed_records[0].args == ("cmdb_count_credential_refs", "cmdb", 1, "TimeoutError")
    assert failed_records[0].getMessage() == (
        "event=credential_ref_count_inquiry_failed method=cmdb_count_credential_refs module=cmdb "
        "failed_stage=rpc id_count=1 error_type=TimeoutError"
    )
    assert failed_records[0].exc_info is None
    assert finished[0].args == ("monitor_count_credential_refs", "monitor", "ok", 1)
    assert finished[0].getMessage() == (
        "event=credential_ref_count_inquiry_finished method=monitor_count_credential_refs module=monitor "
        "outcome=ok id_count=1"
    )
    formatter = logging.Formatter("%(levelname)s %(message)s")
    formatted = "".join(formatter.format(record) for record in caplog.records)
    assert secret not in formatted
    assert secret not in caplog.text

    items = attach_public_refs(
        [{"credential_id": secret, "name": "jump"}],
        queriers=(("cmdb", _ok({secret: 3})), ("monitor", _ok({secret: 0}))),
    )
    assert items[0]["refs"] == [{"module": "cmdb", "count": 3}]


def test_query_module_counts_chunks_ids():
    seen = []

    def record(ids, **kwargs):
        seen.append(list(ids))
        return {"result": True, "data": {"counts": {item: 0 for item in ids}}}

    ids = [f"crd-ssh-{index:032x}" for index in range(101)]
    query_module_counts(ids, queriers=(("cmdb", record),))
    assert [len(chunk) for chunk in seen] == [100, 1]

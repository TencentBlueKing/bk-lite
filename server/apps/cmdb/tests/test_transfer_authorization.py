from types import SimpleNamespace

import pytest

from apps.cmdb.services.transfer_authorization import TransferAuthorization
from apps.cmdb.services.transfer_service import TransferError


def test_disabled_owner_does_not_load_model_or_permissions():
    with pytest.raises(TransferError) as error:
        TransferAuthorization.resolve(SimpleNamespace(disabled=True), 1, False, "host", "export")
    assert error.value.status_code == 403


def test_revalidation_fails_closed_if_authorization_changes():
    context = SimpleNamespace(snapshot={"teams": [1]}, schema_hash="v1")
    task = SimpleNamespace(authorization={"teams": [1, 2]}, schema_hash="v1")
    with pytest.raises(TransferError) as error:
        TransferAuthorization.validate_task(task, context)
    assert error.value.code == "authorization_changed"
    task.authorization = context.snapshot
    context.schema_hash = "v2"
    with pytest.raises(TransferError) as error:
        TransferAuthorization.validate_task(task, context)
    assert error.value.code == "schema_changed"


def test_add_permission_does_not_implicitly_allow_updating_existing_instances():
    context = SimpleNamespace(can_update=False, permission_map={1: {"permission_instances_map": {}, "inst_names": []}})
    instance = {"inst_name": "one", "model_id": "host", "organization": [1]}
    with pytest.raises(TransferError) as error:
        TransferAuthorization.check_instance(context, instance, write=True)
    assert error.value.status_code == 403
    TransferAuthorization.check_instance(context, instance, write=True, require_edit=False)

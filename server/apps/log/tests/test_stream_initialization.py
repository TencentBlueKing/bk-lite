import pytest

from apps.log.management.services.stream import init_stream
from apps.log.models import LogGroup, LogGroupOrganization

pytestmark = pytest.mark.django_db


def _mock_default_group_rpc(mocker, *, response=None, side_effect=None):
    system_mgmt = mocker.patch("apps.log.management.services.stream.SystemMgmt")
    system_mgmt.return_value.get_group_id.return_value = response
    system_mgmt.return_value.get_group_id.side_effect = side_effect
    return system_mgmt


def test_rpc_failure_does_not_persist_default_group(mocker):
    _mock_default_group_rpc(mocker, side_effect=RuntimeError("rpc unavailable"))

    with pytest.raises(RuntimeError, match="rpc unavailable"):
        init_stream()

    assert not LogGroup.objects.filter(id="default").exists()


def test_retry_after_rpc_failure_creates_complete_default_group(mocker):
    _mock_default_group_rpc(
        mocker,
        side_effect=[
            RuntimeError("rpc unavailable"),
            {"result": True, "data": 1},
        ],
    )

    with pytest.raises(RuntimeError, match="rpc unavailable"):
        init_stream()
    init_stream()

    assert LogGroup.objects.filter(id="default").exists()
    assert LogGroupOrganization.objects.filter(log_group_id="default", organization=1).exists()


@pytest.mark.parametrize(
    "response",
    [
        {"result": False, "message": "Default group not found"},
        {"result": True},
        {"result": True, "data": 0},
    ],
)
def test_invalid_rpc_response_does_not_persist_default_group(mocker, response):
    _mock_default_group_rpc(mocker, response=response)

    with pytest.raises(ValueError, match="默认组织"):
        init_stream()

    assert not LogGroup.objects.filter(id="default").exists()
    assert not LogGroupOrganization.objects.filter(log_group_id="default").exists()


def test_relation_failure_rolls_back_default_group(mocker):
    _mock_default_group_rpc(mocker, response={"result": True, "data": 1})
    mocker.patch.object(
        LogGroupOrganization,
        "save",
        side_effect=RuntimeError("relation insert failed"),
    )

    with pytest.raises(RuntimeError, match="relation insert failed"):
        init_stream()

    assert not LogGroup.objects.filter(id="default").exists()


def test_legacy_zero_relation_is_repaired(mocker):
    LogGroup.objects.create(id="default", name="Default", created_by="system", updated_by="system")
    LogGroupOrganization.objects.create(log_group_id="default", organization=0)
    _mock_default_group_rpc(mocker, response={"result": True, "data": 1})

    init_stream()

    assert LogGroupOrganization.objects.filter(log_group_id="default", organization=1).exists()
    assert not LogGroupOrganization.objects.filter(log_group_id="default", organization=0).exists()


def test_existing_valid_relation_is_preserved_without_rpc(mocker):
    LogGroup.objects.create(id="default", name="Default", created_by="system", updated_by="admin")
    LogGroupOrganization.objects.create(log_group_id="default", organization=0)
    LogGroupOrganization.objects.create(log_group_id="default", organization=9)
    system_mgmt = _mock_default_group_rpc(mocker, side_effect=RuntimeError("must not call"))

    init_stream()

    system_mgmt.assert_not_called()
    assert list(
        LogGroupOrganization.objects.filter(log_group_id="default")
        .order_by("organization")
        .values_list("organization", flat=True)
    ) == [0, 9]

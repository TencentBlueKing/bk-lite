import pytest
from django.core.management import call_command

from apps.log.management.services.stream import init_stream
from apps.log.models import LogGroup, LogGroupOrganization

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _mock_default_group_lookup(mocker, *, response=None, side_effect=None):
    system_mgmt = mocker.patch("apps.log.management.services.stream.SystemMgmt")
    system_mgmt.return_value.get_group_id.return_value = response
    system_mgmt.return_value.get_group_id.side_effect = side_effect
    return system_mgmt


def test_group_lookup_failure_is_observable_without_persisting_default_group(mocker):
    _mock_default_group_lookup(mocker, side_effect=RuntimeError("group lookup unavailable"))
    logger = mocker.patch("apps.log.management.services.stream.logger")

    assert init_stream() is False

    assert not LogGroup.objects.filter(id="default").exists()
    logger.exception.assert_called_once()
    assert "RuntimeError: group lookup unavailable" in logger.exception.call_args.args[0]


def test_log_init_command_continues_after_group_lookup_failure(mocker):
    _mock_default_group_lookup(mocker, side_effect=RuntimeError("group lookup unavailable"))
    stream_logger = mocker.patch("apps.log.management.services.stream.logger")
    command_logger = mocker.patch("apps.log.management.commands.log_init.logger")
    mocker.patch("apps.log.management.commands.log_init.migrate_collect_type")

    call_command("log_init")

    stream_logger.exception.assert_called_once()
    command_logger.info.assert_any_call("默认数据流初始化完成！")


def test_retry_after_group_lookup_failure_creates_complete_default_group(mocker):
    _mock_default_group_lookup(
        mocker,
        side_effect=[
            RuntimeError("group lookup unavailable"),
            {"result": True, "data": 1},
        ],
    )
    mocker.patch("apps.log.management.services.stream.logger")

    assert init_stream() is False
    assert init_stream() is True

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
def test_invalid_group_lookup_response_does_not_persist_default_group(mocker, response):
    _mock_default_group_lookup(mocker, response=response)
    logger = mocker.patch("apps.log.management.services.stream.logger")

    assert init_stream() is False

    assert not LogGroup.objects.filter(id="default").exists()
    assert not LogGroupOrganization.objects.filter(log_group_id="default").exists()
    assert "ValueError: 无法获取有效的默认组织 ID" in logger.exception.call_args.args[0]


def test_relation_failure_rolls_back_default_group(mocker):
    _mock_default_group_lookup(mocker, response={"result": True, "data": 1})
    logger = mocker.patch("apps.log.management.services.stream.logger")
    mocker.patch.object(
        LogGroupOrganization,
        "save",
        side_effect=RuntimeError("relation insert failed"),
    )

    assert init_stream() is False

    assert not LogGroup.objects.filter(id="default").exists()
    assert "RuntimeError: relation insert failed" in logger.exception.call_args.args[0]


def test_legacy_zero_relation_is_repaired(mocker):
    LogGroup.objects.create(id="default", name="Default", created_by="system", updated_by="system")
    LogGroupOrganization.objects.create(log_group_id="default", organization=0)
    _mock_default_group_lookup(mocker, response={"result": True, "data": 1})

    assert init_stream() is True

    assert LogGroupOrganization.objects.filter(log_group_id="default", organization=1).exists()
    assert not LogGroupOrganization.objects.filter(log_group_id="default", organization=0).exists()


def test_existing_valid_relation_is_preserved_without_rpc(mocker):
    LogGroup.objects.create(id="default", name="Default", created_by="system", updated_by="admin")
    LogGroupOrganization.objects.create(log_group_id="default", organization=0)
    LogGroupOrganization.objects.create(log_group_id="default", organization=9)
    system_mgmt = _mock_default_group_lookup(mocker, side_effect=RuntimeError("must not call"))

    assert init_stream() is True

    system_mgmt.assert_not_called()
    assert list(
        LogGroupOrganization.objects.filter(log_group_id="default")
        .order_by("organization")
        .values_list("organization", flat=True)
    ) == [9]

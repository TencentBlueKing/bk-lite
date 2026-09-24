from unittest.mock import Mock

import pytest

from apps.rpc.exceptions import RpcLocalClientRequiredError
from apps.rpc.job_mgmt import JobMgmt


def test_automation_interface_requires_local_client(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    client = JobMgmt(is_local_client=False)

    with pytest.raises(RpcLocalClientRequiredError):
        client.list_automation_targets({}, {"authorized_team_ids": [7]})


def test_automation_interface_forwards_trusted_context_locally():
    client = JobMgmt.__new__(JobMgmt)
    client.is_local_client = True
    client.client = Mock()
    actor = {"username": "operator", "authorized_team_ids": [7]}

    client.execute_automation_script({"team": [7]}, actor)
    client.client.run.assert_called_once_with("execute_automation_script_local", {"team": [7]}, actor)

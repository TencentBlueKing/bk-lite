"""补齐 Patch Management RPC 客户端的本地分派契约。"""

import pytest

from apps.rpc import patch_mgmt


pytestmark = pytest.mark.unit


def test_patch_client_uses_local_app_transport_and_forwards_module_query(
    monkeypatch,
):
    calls = []

    class Client:
        def run(self, method):
            calls.append(method)
            return [{"name": "baseline"}]

    monkeypatch.setenv("IS_LOCAL_RPC", "1")
    monkeypatch.setattr(
        patch_mgmt,
        "AppClient",
        lambda module: (
            calls.append(("transport", module)),
            Client(),
        )[1],
    )

    client = patch_mgmt.PatchMgmt()

    assert client.get_module_list() == [{"name": "baseline"}]
    assert calls == [
        ("transport", "apps.patch_mgmt.nats_api"),
        "get_patch_mgmt_module_list",
    ]

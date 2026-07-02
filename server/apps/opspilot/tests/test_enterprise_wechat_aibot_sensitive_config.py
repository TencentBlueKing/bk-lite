from copy import deepcopy
from types import SimpleNamespace

from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils
from apps.opspilot.utils.workflow_sensitive_config import (
    MASKED_SECRET_VALUE,
    decrypt_workflow_sensitive_config,
    encrypt_workflow_sensitive_config,
    mask_workflow_sensitive_config,
    merge_masked_workflow_sensitive_config,
)


def _workflow(token="plain-token", encoding_aes_key="plain-aes-key"):
    return {
        "nodes": [
            {
                "id": "aibot-node",
                "type": "enterprise_wechat_aibot",
                "data": {
                    "config": {
                        "connectionMode": "webhook",
                        "webhook": {
                            "token": token,
                            "encodingAESKey": encoding_aes_key,
                            "aibotid": "bot-a",
                        },
                    }
                },
            }
        ],
        "edges": [],
    }


def test_encrypt_workflow_sensitive_config_removes_plaintext_credentials(settings):
    settings.SECRET_KEY = "unit-test-secret"
    encrypted = encrypt_workflow_sensitive_config(_workflow())
    webhook = encrypted["nodes"][0]["data"]["config"]["webhook"]

    assert webhook["token"] != "plain-token"
    assert webhook["encodingAESKey"] != "plain-aes-key"

    decrypted = decrypt_workflow_sensitive_config(encrypted)
    decrypted_webhook = decrypted["nodes"][0]["data"]["config"]["webhook"]
    assert decrypted_webhook["token"] == "plain-token"
    assert decrypted_webhook["encodingAESKey"] == "plain-aes-key"


def test_mask_workflow_sensitive_config_hides_credentials(settings):
    settings.SECRET_KEY = "unit-test-secret"
    encrypted = encrypt_workflow_sensitive_config(_workflow())
    masked = mask_workflow_sensitive_config(encrypted)
    webhook = masked["nodes"][0]["data"]["config"]["webhook"]

    assert webhook["token"] == MASKED_SECRET_VALUE
    assert webhook["encodingAESKey"] == MASKED_SECRET_VALUE
    assert webhook["aibotid"] == "bot-a"


def test_merge_masked_workflow_sensitive_config_preserves_existing_secret(settings):
    settings.SECRET_KEY = "unit-test-secret"
    encrypted_existing = encrypt_workflow_sensitive_config(_workflow(token="old-token"))
    submitted = _workflow(token=MASKED_SECRET_VALUE, encoding_aes_key="new-aes-key")

    merged = merge_masked_workflow_sensitive_config(submitted, encrypted_existing)
    webhook = decrypt_workflow_sensitive_config(merged)["nodes"][0]["data"]["config"]["webhook"]

    assert webhook["token"] == "old-token"
    assert webhook["encodingAESKey"] == "new-aes-key"


def test_get_aibot_node_config_returns_decrypted_runtime_config(settings):
    settings.SECRET_KEY = "unit-test-secret"
    encrypted = encrypt_workflow_sensitive_config(_workflow())
    workflow = SimpleNamespace(flow_json=deepcopy(encrypted))

    node_id, config = EnterpriseWechatAibotChatFlowUtils.get_aibot_node_config(workflow)

    assert node_id == "aibot-node"
    assert config["webhook"]["token"] == "plain-token"
    assert config["webhook"]["encodingAESKey"] == "plain-aes-key"

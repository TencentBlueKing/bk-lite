"""Ansible 回调测试身份构造器。"""

import hashlib

TEST_ATTEMPT_ID = "test-attempt"
TEST_CALLBACK_TOKEN = "test-callback-token"


def authorize_execution(execution):
    execution.callback_attempt_id = TEST_ATTEMPT_ID
    execution.callback_token_hash = hashlib.sha256(TEST_CALLBACK_TOKEN.encode()).hexdigest()
    execution.save(update_fields=["callback_attempt_id", "callback_token_hash", "updated_at"])
    return execution


def callback_context(execution_id):
    return {
        "caller": "ansible-executor",
        "execution_id": execution_id,
        "attempt_id": TEST_ATTEMPT_ID,
        "token": TEST_CALLBACK_TOKEN,
    }


def with_callback_identity(execution, payload):
    payload["callback_context"] = callback_context(execution.id)
    return payload

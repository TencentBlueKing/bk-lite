"""rpc.sensitive 脱敏逻辑纯函数测试。

针对 sanitize_sensitive_data / summarize_ansible_callback 的真实输出断言：
直接 key 屏蔽、递归屏蔽、字符串内 key=value 与 PEM 私钥块脱敏、ansible 回调摘要结构。
"""
import pydantic.root_model  # noqa

import pytest

from apps.rpc.sensitive import (
    MASKED_VALUE,
    sanitize_sensitive_data,
    summarize_ansible_callback,
)

pytestmark = pytest.mark.unit


def test_direct_mask_password():
    out = sanitize_sensitive_data({"password": "secret", "name": "x"})
    assert out == {"password": MASKED_VALUE, "name": "x"}


def test_direct_mask_key_case_insensitive():
    out = sanitize_sensitive_data({"Password": "secret"})
    assert out == {"Password": MASKED_VALUE}


def test_direct_mask_empty_value_not_masked():
    # 空字符串/None 不替换为 *** （保留原值）
    out = sanitize_sensitive_data({"password": "", "private_key": None})
    assert out == {"password": "", "private_key": None}


def test_all_direct_mask_keys():
    keys = [
        "password",
        "passphrase",
        "private_key",
        "private_key_content",
        "private_key_passphrase",
        "inventory_content",
        "ansible_password",
        "ansible_ssh_passphrase",
        "ansible_become_password",
    ]
    payload = {k: "v" for k in keys}
    out = sanitize_sensitive_data(payload)
    assert all(out[k] == MASKED_VALUE for k in keys)


def test_recurse_only_key_host_credentials():
    payload = {"host_credentials": {"password": "p", "user": "u"}}
    out = sanitize_sensitive_data(payload)
    assert out == {"host_credentials": {"password": MASKED_VALUE, "user": "u"}}


def test_nested_dict_recursion():
    payload = {"outer": {"inner": {"password": "p", "keep": 1}}}
    out = sanitize_sensitive_data(payload)
    assert out == {"outer": {"inner": {"password": MASKED_VALUE, "keep": 1}}}


def test_list_recursion():
    payload = [{"password": "a"}, {"x": 1}]
    out = sanitize_sensitive_data(payload)
    assert out == [{"password": MASKED_VALUE}, {"x": 1}]


def test_tuple_recursion_preserves_type():
    out = sanitize_sensitive_data(({"password": "a"}, 5))
    assert isinstance(out, tuple)
    assert out == ({"password": MASKED_VALUE}, 5)


def test_non_string_scalars_passthrough():
    assert sanitize_sensitive_data(42) == 42
    assert sanitize_sensitive_data(None) is None
    assert sanitize_sensitive_data(True) is True


def test_string_assignment_unquoted_masked():
    out = sanitize_sensitive_data("password=hunter2 next")
    assert out == f"password={MASKED_VALUE} next"


def test_string_assignment_single_quoted_keeps_quotes():
    out = sanitize_sensitive_data("password='hunter2'")
    assert out == f"password='{MASKED_VALUE}'"


def test_string_assignment_double_quoted_keeps_quotes():
    out = sanitize_sensitive_data('password="hunter2"')
    assert out == f'password="{MASKED_VALUE}"'


def test_string_assignment_colon_separator():
    out = sanitize_sensitive_data("ansible_password: topsecret")
    assert out == f"ansible_password: {MASKED_VALUE}"


def test_string_non_sensitive_unchanged():
    assert sanitize_sensitive_data("hello world") == "hello world"


def test_empty_string_unchanged():
    assert sanitize_sensitive_data("") == ""


def test_pem_private_key_block_masked():
    pem = (
        "before\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAA\nabcd\n"
        "-----END RSA PRIVATE KEY-----\nafter"
    )
    out = sanitize_sensitive_data(pem)
    assert "MIIEowIBAA" not in out
    assert MASKED_VALUE in out
    assert out.startswith("before")
    assert out.endswith("after")


# ---- PC 发现：WinRM/SSH 凭据形态的脱敏合同 ----


def test_pc_windows_host_credentials_masked():
    payload = {
        "host_credentials": [
            {
                "host": "10.0.0.8",
                "user": "ACME\\alice",
                "connection": "winrm",
                "port": 5986,
                "password": "S3cret!Passw0rd#PC",
                "winrm_scheme": "https",
                "winrm_transport": "ntlm",
            }
        ]
    }
    out = sanitize_sensitive_data(payload)
    cred = out["host_credentials"][0]
    assert cred["password"] == MASKED_VALUE
    assert cred["user"] == "ACME\\alice"
    assert cred["port"] == 5986
    assert "S3cret!Passw0rd#PC" not in str(out)


def test_pc_macos_host_credentials_private_key_and_passphrase_masked():
    payload = {
        "host_credentials": [
            {
                "host": "10.0.0.9",
                "user": "admin",
                "port": 22,
                "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\nKEYDATA\n-----END OPENSSH PRIVATE KEY-----",
                "passphrase": "pc-passphrase-001",
            }
        ]
    }
    out = sanitize_sensitive_data(payload)
    cred = out["host_credentials"][0]
    assert cred["private_key"] == MASKED_VALUE
    assert cred["passphrase"] == MASKED_VALUE
    assert "KEYDATA" not in str(out)
    assert "pc-passphrase-001" not in str(out)


def test_openssh_private_key_block_masked():
    pem = (
        "before\n-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n"
        "-----END OPENSSH PRIVATE KEY-----\nafter"
    )
    out = sanitize_sensitive_data(pem)
    assert "b3BlbnNzaC1rZXktdjEAAAAA" not in out
    assert MASKED_VALUE in out
    assert out.startswith("before")
    assert out.endswith("after")


def test_summarize_basic_fields():
    data = {
        "task_id": "t1",
        "task_type": "run",
        "status": "done",
        "success": True,
        "started_at": "s",
        "finished_at": "f",
    }
    out = summarize_ansible_callback(data)
    # result 缺失（None 非 list）时，会记录 result_type=NoneType
    assert out == {
        "task_id": "t1",
        "task_type": "run",
        "status": "done",
        "success": True,
        "started_at": "s",
        "finished_at": "f",
        "result_type": "NoneType",
    }


def test_summarize_error_sanitized():
    data = {"error": "password=oops"}
    out = summarize_ansible_callback(data)
    assert out["error"] == f"password={MASKED_VALUE}"


def test_summarize_no_error_key_absent():
    out = summarize_ansible_callback({"task_id": "t"})
    assert "error" not in out


def test_summarize_result_list_hosts():
    data = {
        "result": [
            {"host": "h1", "status": "ok", "exit_code": 0, "output_truncated": False},
            {"host": "h2", "status": "fail", "exit_code": 1, "output_truncated": True},
            "not-a-dict",
        ]
    }
    out = summarize_ansible_callback(data)
    assert out["result_count"] == 3
    assert out["hosts"] == [
        {"host": "h1", "status": "ok", "exit_code": 0, "output_truncated": False},
        {"host": "h2", "status": "fail", "exit_code": 1, "output_truncated": True},
    ]
    assert "result_type" not in out


def test_summarize_result_non_list_records_type():
    out = summarize_ansible_callback({"result": {"a": 1}})
    assert out["result_type"] == "dict"
    assert "result_count" not in out

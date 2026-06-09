"""job_mgmt.utils.callback_signer 生产规格测试。

规格（HMAC-SHA256 回调签名，接收方据此验证来源）：
- sign_callback 对相同 payload+timestamp 稳定，且与 key 顺序无关（sort_keys）；
- payload/timestamp 任一变化签名即变化；
- verify_callback_signature：正确签名通过；篡改/过期(超 max_age)拒绝；
- get_signed_headers 产出可被 verify 验证的头部。
"""

import time

import pytest

from apps.job_mgmt.utils.callback_signer import (
    get_signed_headers,
    sign_callback,
    verify_callback_signature,
)

pytestmark = pytest.mark.unit


class TestSign:
    def test_确定性且与键顺序无关(self):
        a = sign_callback({"a": 1, "b": 2}, 1000)
        b = sign_callback({"b": 2, "a": 1}, 1000)
        assert a == b
        assert len(a) == 64  # sha256 hex

    def test_payload_变化签名变化(self):
        assert sign_callback({"a": 1}, 1000) != sign_callback({"a": 2}, 1000)

    def test_timestamp_变化签名变化(self):
        assert sign_callback({"a": 1}, 1000) != sign_callback({"a": 1}, 1001)


class TestVerify:
    def test_正确签名通过(self):
        payload = {"job": 1, "status": "done"}
        ts = int(time.time())
        sig = sign_callback(payload, ts)
        assert verify_callback_signature(payload, ts, sig) is True

    def test_篡改_payload_拒绝(self):
        ts = int(time.time())
        sig = sign_callback({"job": 1}, ts)
        assert verify_callback_signature({"job": 2}, ts, sig) is False

    def test_错误签名拒绝(self):
        ts = int(time.time())
        assert verify_callback_signature({"job": 1}, ts, "deadbeef") is False

    def test_过期时间戳拒绝(self):
        payload = {"job": 1}
        old_ts = int(time.time()) - 600  # 超过默认 max_age=300
        sig = sign_callback(payload, old_ts)
        assert verify_callback_signature(payload, old_ts, sig) is False


class TestSignedHeaders:
    def test_头部可被验证(self):
        payload = {"job": 42}
        headers = get_signed_headers(payload)
        assert headers["X-BK-Lite-Source"] == "bk-lite-job-mgmt"
        assert headers["Content-Type"] == "application/json"
        ts = int(headers["X-BK-Lite-Timestamp"])
        assert verify_callback_signature(payload, ts, headers["X-BK-Lite-Signature"]) is True

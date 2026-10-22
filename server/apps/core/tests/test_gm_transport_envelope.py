import pytest

from apps.core.utils.crypto.gm_transport import (
    GmTransportCryptoError,
    frame_plaintext,
    kid_from_public_key_hex,
    open_request_envelope,
    open_response_envelope,
    public_key_hex_from_private,
    request_mac_message,
    response_mac_message,
    seal_request_envelope,
    seal_response_envelope,
    unframe_plaintext,
    unwrap_sm4_key,
    wrap_sm4_key,
)

# GM/T 0003.5 示例私钥。公钥由该私钥导出，不手写。
PRIVATE_KEY = "3945208F7B2144B13F36E38AC6D39F95889393692860B51A42FB81EF4DF7C5B8"
PUBLIC_KEY = "09f9df311e5421a150dd7d161e4bc5c672179fad1833fc076bb08ff356f35020ccea490ce26775a52dc6ea718cc1aa600aed05fbf35e084a6632f6072da9ad13"
KID = "3d92bed6d685f38b"
SM4_KEY = bytes.fromhex("0123456789abcdeffedcba9876543210")
REQUEST_IV = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
RESPONSE_IV = bytes.fromhex("0f0e0d0c0b0a09080706050403020100")
NONCE = "00112233445566778899aabbccddeeff"
TS = 1760490000000
QUERY = "name=a&q=中文"
BODY = b'{"username":"admin"}'
REQUEST_VECTOR = {
    "v": 1,
    "ts": TS,
    "nonce": NONCE,
    "kid": KID,
    "method": "POST",
    "path": "/core/api/login/",
    "cty": "application/json",
    "ek": (
        "3Jz1pFBBPfdJYdkZIPmOr/LRzzDWZIl++alLHRkStvp5JRM9zKRRkY89vU6qSCBM"
        "F6btP0U4qQvp4kEubvTc8LgSA6LIyrCZfijjCjYWum0eI/u9dOY9TStCAnUoiXl6"
        "M85EnOWmLfij6XXvAIvpyQ=="
    ),
    "iv": "AAECAwQFBgcICQoLDA0ODw==",
    "ct": "LmWdPuqenZzyexiGuwQ+ZqRpqA2XVRAOSXjuErGmJFcogC26JV9hJuv8kmmqNEuv",
    "mac": "1vrjDrA/Qd5zCnO0ocOSzeWHZylXxF9fd88tvOeP+hA=",
}
RESPONSE_VECTOR = {
    "v": 1,
    "nonce": NONCE,
    "seq": 1,
    "status": 200,
    "cty": "application/json",
    "iv": "Dw4NDAsKCQgHBgUEAwIBAA==",
    "ct": "kmvPmNfbk2kZvfR1L9V9Aw==",
    "mac": "BwDX2gztEfzq3K/b6MP2VC+senzQS5cKH3W1xTSrezo=",
}
RESPONSE_BODY = b'{"result":true}'


@pytest.mark.unit
def test_mac_messages_use_the_specified_lines_without_a_trailing_newline():
    request = request_mac_message(
        ts=TS,
        nonce=NONCE,
        method="POST",
        path="/core/api/login/",
        cty="application/json",
        iv_b64=REQUEST_VECTOR["iv"],
        ct_b64=REQUEST_VECTOR["ct"],
    )
    assert request == (
        b"1\n"
        b"1760490000000\n"
        b"00112233445566778899aabbccddeeff\n"
        b"POST\n"
        b"/core/api/login/\n"
        b"application/json\n"
        b"AAECAwQFBgcICQoLDA0ODw==\n"
        b"LmWdPuqenZzyexiGuwQ+ZqRpqA2XVRAOSXjuErGmJFcogC26JV9hJuv8kmmqNEuv"
    )
    assert not request.endswith(b"\n")

    response = response_mac_message(
        nonce=NONCE,
        seq=1,
        status=200,
        cty="application/json",
        iv_b64=RESPONSE_VECTOR["iv"],
        ct_b64=RESPONSE_VECTOR["ct"],
    )
    assert response == (
        b"1\n"
        b"resp\n"
        b"00112233445566778899aabbccddeeff\n"
        b"1\n"
        b"200\n"
        b"application/json\n"
        b"Dw4NDAsKCQgHBgUEAwIBAA==\n"
        b"kmvPmNfbk2kZvfR1L9V9Aw=="
    )


@pytest.mark.unit
def test_public_key_and_kid_match_the_fixed_vector():
    assert public_key_hex_from_private(PRIVATE_KEY) == PUBLIC_KEY
    assert kid_from_public_key_hex(PUBLIC_KEY) == KID


@pytest.mark.unit
def test_request_envelope_matches_the_fixed_sm4_and_mac_vector():
    sealed = seal_request_envelope(
        public_key_hex=PUBLIC_KEY,
        sm4_key=SM4_KEY,
        iv=REQUEST_IV,
        nonce=NONCE,
        ts=TS,
        method="post",
        path="/core/api/login/",
        cty="application/json",
        query=QUERY,
        body=BODY,
    )
    assert sealed["method"] == "POST"
    assert sealed["kid"] == KID
    assert sealed["iv"] == REQUEST_VECTOR["iv"]
    assert sealed["ct"] == REQUEST_VECTOR["ct"]
    assert sealed["mac"] == REQUEST_VECTOR["mac"]
    assert len(unwrap_sm4_key(PRIVATE_KEY, _b64(sealed["ek"]))) == 16


@pytest.mark.unit
def test_fixed_request_vector_opens_to_the_original_query_and_body():
    opened = open_request_envelope(
        REQUEST_VECTOR,
        PRIVATE_KEY,
        expected_method="POST",
        expected_path="/core/api/login/",
    )
    assert opened.query == QUERY
    assert opened.body == BODY
    assert opened.sm4_key == SM4_KEY


@pytest.mark.unit
def test_changed_request_mac_byte_is_rejected():
    tampered = dict(REQUEST_VECTOR)
    tampered["mac"] = "0vrjDrA/Qd5zCnO0ocOSzeWHZylXxF9fd88tvOeP+hA="
    with pytest.raises(GmTransportCryptoError):
        open_request_envelope(
            tampered,
            PRIVATE_KEY,
            expected_method="POST",
            expected_path="/core/api/login/",
        )


@pytest.mark.unit
def test_changed_timestamp_is_rejected():
    tampered = dict(REQUEST_VECTOR)
    tampered["ts"] = TS + 1
    with pytest.raises(GmTransportCryptoError):
        open_request_envelope(
            tampered,
            PRIVATE_KEY,
            expected_method="POST",
            expected_path="/core/api/login/",
        )


@pytest.mark.unit
def test_response_vector_opens_and_rejects_a_swapped_nonce():
    assert (
        open_response_envelope(
            RESPONSE_VECTOR,
            SM4_KEY,
            expected_nonce=NONCE,
            expected_seq=1,
            expected_status=200,
        )
        == RESPONSE_BODY
    )
    swapped = dict(RESPONSE_VECTOR)
    swapped["nonce"] = "ff" + NONCE[2:]
    with pytest.raises(GmTransportCryptoError):
        open_response_envelope(
            swapped,
            SM4_KEY,
            expected_nonce=NONCE,
            expected_seq=1,
            expected_status=200,
        )


@pytest.mark.unit
def test_response_frames_concatenate_in_sequence():
    first = seal_response_envelope(
        sm4_key=SM4_KEY,
        iv=RESPONSE_IV,
        nonce=NONCE,
        seq=1,
        status=200,
        cty="text/event-stream",
        body=b"data: one\n\n",
    )
    second = seal_response_envelope(
        sm4_key=SM4_KEY,
        iv=REQUEST_IV,
        nonce=NONCE,
        seq=2,
        status=200,
        cty="text/event-stream",
        body=b"data: two\n\n",
    )
    plain = b"".join(
        open_response_envelope(
            frame,
            SM4_KEY,
            expected_nonce=NONCE,
            expected_seq=seq,
            expected_status=200,
        )
        for seq, frame in ((1, first), (2, second))
    )
    assert plain == b"data: one\n\ndata: two\n\n"
    with pytest.raises(GmTransportCryptoError):
        open_response_envelope(
            second,
            SM4_KEY,
            expected_nonce=NONCE,
            expected_seq=1,
            expected_status=200,
        )


@pytest.mark.unit
def test_sm2_wrapped_key_is_c1c3c2_without_an_extra_prefix_byte():
    wrapped = wrap_sm4_key(PUBLIC_KEY, SM4_KEY)
    assert len(wrapped) == 64 + 32 + 16
    assert unwrap_sm4_key(PRIVATE_KEY, wrapped) == SM4_KEY


@pytest.mark.unit
def test_frame_roundtrip_and_rejects_a_leading_question_mark():
    framed = frame_plaintext("a=1", b"raw")
    assert unframe_plaintext(framed) == ("a=1", b"raw")
    assert unframe_plaintext(frame_plaintext("", b"")) == ("", b"")
    with pytest.raises(GmTransportCryptoError):
        frame_plaintext("?a=1", b"")


def _b64(value: str) -> bytes:
    import base64

    return base64.b64decode(value)

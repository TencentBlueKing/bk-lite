"""请求信封与响应信封的纯函数。

SM4-CBC 与 HMAC-SM3 使用 cryptography。SM2 使用 gmssl，密文排列固定为 C1C3C2，不带 04 前缀。
"""

import base64
import hmac
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.hmac import HMAC
from gmssl import sm2

SM4_KEY_LENGTH = 16
SM4_IV_LENGTH = 16
SM4_BLOCK_BITS = 128
NONCE_HEX_LENGTH = 32
PUBLIC_KEY_HEX_LENGTH = 128
PRIVATE_KEY_HEX_LENGTH = 64
SM2_C1_LENGTH = 64
SM2_C3_LENGTH = 32


class GmTransportCryptoError(Exception):
    """MAC、填充、SM2 或信封格式失败。调用方对外使用同一个错误。"""


@dataclass(frozen=True)
class OpenedRequest:
    query: str
    body: bytes
    sm4_key: bytes


def frame_plaintext(query: str, body: bytes) -> bytes:
    if query.startswith("?"):
        raise GmTransportCryptoError("query must not include a leading question mark")
    query_bytes = query.encode("utf-8")
    if len(query_bytes) > 0xFFFFFFFF:
        raise GmTransportCryptoError("query is too long")
    return len(query_bytes).to_bytes(4, "big") + query_bytes + body


def unframe_plaintext(plaintext: bytes) -> tuple[str, bytes]:
    if len(plaintext) < 4:
        raise GmTransportCryptoError("framed plaintext is too short")
    query_length = int.from_bytes(plaintext[:4], "big")
    if len(plaintext) < 4 + query_length:
        raise GmTransportCryptoError("framed query length exceeds plaintext")
    query_bytes = plaintext[4 : 4 + query_length]
    try:
        query = query_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GmTransportCryptoError("framed query is not utf-8") from exc
    return query, plaintext[4 + query_length :]


def request_mac_message(
    *,
    ts: int,
    nonce: str,
    method: str,
    path: str,
    cty: str,
    iv_b64: str,
    ct_b64: str,
) -> bytes:
    lines = ("1", str(ts), nonce, method, path, cty, iv_b64, ct_b64)
    return "\n".join(lines).encode("utf-8")


def response_mac_message(
    *,
    nonce: str,
    seq: int,
    status: int,
    cty: str,
    iv_b64: str,
    ct_b64: str,
) -> bytes:
    lines = ("1", "resp", nonce, str(seq), str(status), cty, iv_b64, ct_b64)
    return "\n".join(lines).encode("utf-8")


def public_key_hex_from_private(private_key_hex: str) -> str:
    _validate_private_key_hex(private_key_hex)
    crypt = _sm2(private_key_hex, "00" * 32)
    public_key_hex = crypt._kg(int(private_key_hex, 16), crypt.ecc_table["g"])
    if len(public_key_hex) != PUBLIC_KEY_HEX_LENGTH:
        raise GmTransportCryptoError("derived public key has the wrong length")
    return public_key_hex


def kid_from_public_key_hex(public_key_hex: str) -> str:
    raw = _decode_public_key(public_key_hex)
    digest = hashes.Hash(hashes.SM3())
    digest.update(raw)
    return digest.finalize()[:8].hex()


def encrypt_sm4_cbc(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    _validate_sm4_key_iv(key, iv)
    padder = padding.PKCS7(SM4_BLOCK_BITS).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.SM4(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def decrypt_sm4_cbc(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    _validate_sm4_key_iv(key, iv)
    if not ciphertext or len(ciphertext) % SM4_KEY_LENGTH != 0:
        raise GmTransportCryptoError("ciphertext length is not a multiple of the block size")
    decryptor = Cipher(algorithms.SM4(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(SM4_BLOCK_BITS).unpadder()
    try:
        return unpadder.update(padded) + unpadder.finalize()
    except ValueError as exc:
        raise GmTransportCryptoError("pkcs7 padding is invalid") from exc


def hmac_sm3(key: bytes, message: bytes) -> bytes:
    if len(key) != SM4_KEY_LENGTH:
        raise GmTransportCryptoError("hmac key must be 16 bytes")
    mac = HMAC(key, hashes.SM3())
    mac.update(message)
    return mac.finalize()


def wrap_sm4_key(public_key_hex: str, sm4_key: bytes) -> bytes:
    if len(sm4_key) != SM4_KEY_LENGTH:
        raise GmTransportCryptoError("sm4 key must be 16 bytes")
    _decode_public_key(public_key_hex)
    ciphertext = _sm2("", public_key_hex).encrypt(sm4_key)
    if not isinstance(ciphertext, (bytes, bytearray)) or not _is_c1c3c2(ciphertext, SM4_KEY_LENGTH):
        raise GmTransportCryptoError("sm2 ciphertext is not C1C3C2")
    return bytes(ciphertext)


def unwrap_sm4_key(private_key_hex: str, wrapped: bytes) -> bytes:
    if not _is_c1c3c2(wrapped, SM4_KEY_LENGTH):
        raise GmTransportCryptoError("sm2 ciphertext is not C1C3C2")
    sm4_key = _sm2_decrypt_c1c3c2(private_key_hex, wrapped)
    if len(sm4_key) != SM4_KEY_LENGTH:
        raise GmTransportCryptoError("sm2 decrypt failed")
    return sm4_key


def seal_request_envelope(
    *,
    public_key_hex: str,
    sm4_key: bytes,
    iv: bytes,
    nonce: str,
    ts: int,
    method: str,
    path: str,
    cty: str,
    query: str,
    body: bytes,
) -> dict:
    _validate_nonce(nonce)
    method = method.upper()
    framed = frame_plaintext(query, body)
    ciphertext = encrypt_sm4_cbc(sm4_key, iv, framed)
    iv_b64 = _b64encode(iv)
    ct_b64 = _b64encode(ciphertext)
    mac = hmac_sm3(
        sm4_key,
        request_mac_message(
            ts=ts,
            nonce=nonce,
            method=method,
            path=path,
            cty=cty,
            iv_b64=iv_b64,
            ct_b64=ct_b64,
        ),
    )
    return {
        "v": 1,
        "ts": ts,
        "nonce": nonce,
        "kid": kid_from_public_key_hex(public_key_hex),
        "method": method,
        "path": path,
        "cty": cty,
        "ek": _b64encode(wrap_sm4_key(public_key_hex, sm4_key)),
        "iv": iv_b64,
        "ct": ct_b64,
        "mac": _b64encode(mac),
    }


def open_request_envelope(
    envelope: dict,
    private_key_hex: str,
    *,
    expected_method: str,
    expected_path: str,
) -> OpenedRequest:
    _require_request_fields(envelope)
    if envelope.get("v") != 1:
        raise GmTransportCryptoError("unsupported envelope version")
    if envelope["method"] != expected_method.upper() or envelope["path"] != expected_path:
        raise GmTransportCryptoError("method or path does not match the request")
    public_key_hex = public_key_hex_from_private(private_key_hex)
    if envelope["kid"] != kid_from_public_key_hex(public_key_hex):
        raise GmTransportCryptoError("kid does not match the current public key")
    sm4_key = unwrap_sm4_key(private_key_hex, _b64decode(envelope["ek"]))
    expected_mac = hmac_sm3(
        sm4_key,
        request_mac_message(
            ts=envelope["ts"],
            nonce=envelope["nonce"],
            method=envelope["method"],
            path=envelope["path"],
            cty=envelope["cty"],
            iv_b64=envelope["iv"],
            ct_b64=envelope["ct"],
        ),
    )
    if not hmac.compare_digest(expected_mac, _b64decode(envelope["mac"])):
        raise GmTransportCryptoError("mac does not match")
    plaintext = decrypt_sm4_cbc(sm4_key, _b64decode(envelope["iv"]), _b64decode(envelope["ct"]))
    query, body = unframe_plaintext(plaintext)
    return OpenedRequest(query=query, body=body, sm4_key=sm4_key)


def seal_response_envelope(
    *,
    sm4_key: bytes,
    iv: bytes,
    nonce: str,
    seq: int,
    status: int,
    cty: str,
    body: bytes,
) -> dict:
    _validate_nonce(nonce)
    ciphertext = encrypt_sm4_cbc(sm4_key, iv, body)
    iv_b64 = _b64encode(iv)
    ct_b64 = _b64encode(ciphertext)
    mac = hmac_sm3(
        sm4_key,
        response_mac_message(
            nonce=nonce,
            seq=seq,
            status=status,
            cty=cty,
            iv_b64=iv_b64,
            ct_b64=ct_b64,
        ),
    )
    return {
        "v": 1,
        "nonce": nonce,
        "seq": seq,
        "status": status,
        "cty": cty,
        "iv": iv_b64,
        "ct": ct_b64,
        "mac": _b64encode(mac),
    }


def open_response_envelope(
    envelope: dict,
    sm4_key: bytes,
    *,
    expected_nonce: str,
    expected_seq: int,
    expected_status: int,
) -> bytes:
    _require_response_fields(envelope)
    if envelope.get("v") != 1:
        raise GmTransportCryptoError("unsupported envelope version")
    if envelope["nonce"] != expected_nonce or envelope["seq"] != expected_seq or envelope["status"] != expected_status:
        raise GmTransportCryptoError("response is not bound to this request")
    expected_mac = hmac_sm3(
        sm4_key,
        response_mac_message(
            nonce=envelope["nonce"],
            seq=envelope["seq"],
            status=envelope["status"],
            cty=envelope["cty"],
            iv_b64=envelope["iv"],
            ct_b64=envelope["ct"],
        ),
    )
    if not hmac.compare_digest(expected_mac, _b64decode(envelope["mac"])):
        raise GmTransportCryptoError("mac does not match")
    return decrypt_sm4_cbc(sm4_key, _b64decode(envelope["iv"]), _b64decode(envelope["ct"]))


def _sm2(private_key_hex: str, public_key_hex: str) -> sm2.CryptSM2:
    return sm2.CryptSM2(private_key=private_key_hex, public_key=public_key_hex, mode=1, asn1=False)


def _sm2_decrypt_c1c3c2(private_key_hex: str, ciphertext: bytes) -> bytes:
    """gmssl 的 decrypt 算出 C3 后没有比较。这里按 C1C3C2 解密并核对 C3。"""
    from gmssl import sm3

    _validate_private_key_hex(private_key_hex)
    crypt = _sm2(private_key_hex, "00" * 32)
    data = ciphertext.hex()
    c1_hex_length = 2 * crypt.para_len
    c3_end = c1_hex_length + 64
    c1 = data[:c1_hex_length]
    c3 = data[c1_hex_length:c3_end]
    c2 = data[c3_end:]
    try:
        xy = crypt._kg(int(private_key_hex, 16), c1)
    except Exception as exc:
        raise GmTransportCryptoError("sm2 decrypt failed") from exc
    x2 = xy[: crypt.para_len]
    y2 = xy[crypt.para_len : c1_hex_length]
    t = sm3.sm3_kdf(xy.encode("utf8"), len(c2) / 2)
    if int(t, 16) == 0:
        raise GmTransportCryptoError("sm2 decrypt failed")
    message_hex = "%%0%dx" % len(c2) % (int(c2, 16) ^ int(t, 16))
    digest = sm3.sm3_hash([byte for byte in bytes.fromhex(f"{x2}{message_hex}{y2}")])
    if not hmac.compare_digest(digest.lower(), c3.lower()):
        raise GmTransportCryptoError("sm2 decrypt failed")
    return bytes.fromhex(message_hex)


def _is_c1c3c2(ciphertext: bytes, plaintext_length: int) -> bool:
    return len(ciphertext) == SM2_C1_LENGTH + SM2_C3_LENGTH + plaintext_length


def _validate_sm4_key_iv(key: bytes, iv: bytes) -> None:
    if len(key) != SM4_KEY_LENGTH or len(iv) != SM4_IV_LENGTH:
        raise GmTransportCryptoError("sm4 key and iv must both be 16 bytes")


def _validate_nonce(nonce: str) -> None:
    if len(nonce) != NONCE_HEX_LENGTH:
        raise GmTransportCryptoError("nonce must be 32 hex characters")
    try:
        bytes.fromhex(nonce)
    except ValueError as exc:
        raise GmTransportCryptoError("nonce must be 32 hex characters") from exc


def _validate_private_key_hex(private_key_hex: str) -> None:
    if len(private_key_hex) != PRIVATE_KEY_HEX_LENGTH:
        raise GmTransportCryptoError("private key must be 64 hex characters")
    try:
        int(private_key_hex, 16)
    except ValueError as exc:
        raise GmTransportCryptoError("private key must be 64 hex characters") from exc


def _decode_public_key(public_key_hex: str) -> bytes:
    if len(public_key_hex) != PUBLIC_KEY_HEX_LENGTH:
        raise GmTransportCryptoError("public key must be 128 hex characters")
    try:
        return bytes.fromhex(public_key_hex)
    except ValueError as exc:
        raise GmTransportCryptoError("public key must be 128 hex characters") from exc


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise GmTransportCryptoError("base64 field is invalid") from exc


def _require_request_fields(envelope: dict) -> None:
    required = ("v", "ts", "nonce", "kid", "method", "path", "cty", "ek", "iv", "ct", "mac")
    if any(field not in envelope for field in required):
        raise GmTransportCryptoError("request envelope is missing a field")


def _require_response_fields(envelope: dict) -> None:
    required = ("v", "nonce", "seq", "status", "cty", "iv", "ct", "mac")
    if any(field not in envelope for field in required):
        raise GmTransportCryptoError("response envelope is missing a field")

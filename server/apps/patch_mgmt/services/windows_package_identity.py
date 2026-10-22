"""确认手工 Windows 包是带微软签名、且 KB 与补丁记录一致的更新包。"""

from __future__ import annotations

import hashlib
import io
import re
import struct
import tempfile
import zipfile
from dataclasses import dataclass

from signify.authenticode.cert_store import TRUSTED_CERTIFICATE_STORE
from signify.authenticode.signed_data import AuthenticodeSignature
from signify.exceptions import SignifyError
from signify.x509.context import CertificateStore

from apps.patch_mgmt.config import PATCH_MGMT_MAX_PACKAGE_SIZE_MB
from apps.patch_mgmt.exceptions import CodedMessageError
from apps.patch_mgmt.services.windows_dotnet import resolve_dotnet_version

_MAX_ENTRIES = 8192
_MAX_NAME_LENGTH = 255
_MAX_SIGNATURE_BYTES = 1024 * 1024
_MAX_NESTED_CABS = 8
_KB_RE = re.compile(r"(?i)(?<![A-Za-z0-9])KB(\d{6,8})(?!\d)")


class WindowsPackageIdentityError(CodedMessageError):
    """补丁包不是可接受的微软更新包。"""


@dataclass(frozen=True)
class WindowsPackageIdentity:
    kb_numbers: frozenset[str]
    dotnet_version: str


def _normalize_kb(value: str) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("KB"):
        text = text[2:]
    if not text.isdigit():
        raise WindowsPackageIdentityError("package_kb_invalid", "The patch KB number is invalid")
    return f"KB{text}"


def _kbs_in_name(name: str) -> set[str]:
    return {f"KB{match.group(1).upper()}" for match in _KB_RE.finditer(name)}


def _read_cstring(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\x00", offset, offset + _MAX_NAME_LENGTH + 1)
    if end < 0:
        raise WindowsPackageIdentityError("package_catalog_unreadable", "The patch package catalog cannot be read")
    raw = data[offset:end]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text, end + 1


def _signature_span(data: bytes) -> tuple[int, int]:
    """定位 CAB 末尾的 PKCS7。签名长度在保留头，签名本身贴在文件末尾。"""
    if len(data) < 60 or data[:4] != b"MSCF":
        raise WindowsPackageIdentityError("package_unsigned", "The patch package is not signed by Microsoft")
    if struct.unpack_from("<I", data, 4)[0] != 0:
        raise WindowsPackageIdentityError("package_unsigned", "The patch package is not signed by Microsoft")
    flags = struct.unpack_from("<H", data, 30)[0]
    if flags & 0x0004 == 0:
        raise WindowsPackageIdentityError("package_unsigned", "The patch package is not signed by Microsoft")
    header_reserve, _folder_reserve, _data_reserve = struct.unpack_from("<HBB", data, 36)
    if header_reserve != 20 or 60 > len(data):
        raise WindowsPackageIdentityError("package_unsigned", "The patch package is not signed by Microsoft")
    marker, sigpos, length, _unknown2, _unknown3 = struct.unpack_from("<IIIII", data, 40)
    if marker != 0x00100000 or length <= 0 or length > _MAX_SIGNATURE_BYTES:
        raise WindowsPackageIdentityError("package_unsigned", "The patch package is not signed by Microsoft")
    start = len(data) - length
    if start < 60 or sigpos > start or data[start : start + 1] != b"\x30":
        raise WindowsPackageIdentityError("package_unsigned", "The patch package is not signed by Microsoft")
    return start, length


def _cabinet_names(data: bytes) -> tuple[str, ...]:
    if len(data) < 36 or data[:4] != b"MSCF":
        raise WindowsPackageIdentityError("package_catalog_unreadable", "The patch package catalog cannot be read")
    _coff, _reserved3, _ver_min, _ver_maj, folders, files, flags = struct.unpack_from("<IIBBHHH", data, 16)
    if files < 0 or files > _MAX_ENTRIES or folders < 0 or folders > _MAX_ENTRIES:
        raise WindowsPackageIdentityError("package_catalog_unreadable", "The patch package catalog cannot be read")
    offset = 36
    folder_reserve = 0
    if flags & 0x0004:
        if offset + 4 > len(data):
            raise WindowsPackageIdentityError("package_catalog_unreadable", "The patch package catalog cannot be read")
        header_reserve, folder_reserve, _data_reserve = struct.unpack_from("<HBB", data, offset)
        offset += 4 + header_reserve
    if flags & 0x0001:
        _previous, offset = _read_cstring(data, offset)
        _previous_disk, offset = _read_cstring(data, offset)
    if flags & 0x0002:
        _next_name, offset = _read_cstring(data, offset)
        _next_disk, offset = _read_cstring(data, offset)
    offset += folders * (8 + folder_reserve)
    names: list[str] = []
    for _index in range(files):
        if offset + 16 > len(data):
            raise WindowsPackageIdentityError("package_catalog_unreadable", "The patch package catalog cannot be read")
        offset += 16
        name, offset = _read_cstring(data, offset)
        names.append(name)
    return tuple(names)


def _cabinet_imprint(data: bytes, signature_start: int, algorithm) -> bytes:
    """按微软 CAB Authenticode 计算摘要：跳过校验和、柜序号和签名位置字段。"""
    hasher = algorithm()
    hasher.update(data[0:4])
    hasher.update(data[8:34])
    hasher.update(data[56:60])
    hasher.update(data[60:signature_start])
    return hasher.digest()


def _verify_signature(data: bytes, trust_store: CertificateStore | None) -> None:
    start, length = _signature_span(data)
    signature = AuthenticodeSignature.from_envelope(data[start : start + length])
    expected = _cabinet_imprint(data, start, signature.indirect_data.digest_algorithm)
    try:
        signature.verify(
            expected_hash=expected,
            trusted_certificate_store=trust_store or TRUSTED_CERTIFICATE_STORE,
            countersignature_mode="permit",
            verify_additional_hashes=False,
        )
    except SignifyError as exc:
        raise WindowsPackageIdentityError("package_signature_invalid", "The patch package failed Microsoft signature verification") from exc


def _inspect_cabinet(
    data: bytes,
    *,
    trust_store: CertificateStore | None,
) -> tuple[frozenset[str], tuple[str, ...]]:
    _verify_signature(data, trust_store)
    names = _cabinet_names(data)
    found: set[str] = set()
    for name in names:
        found.update(_kbs_in_name(name))
    return frozenset(found), names


def _inspect_zip(
    data: bytes,
    *,
    trust_store: CertificateStore | None,
) -> tuple[frozenset[str], tuple[str, ...]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise WindowsPackageIdentityError("package_catalog_unreadable", "The patch package catalog cannot be read") from exc
    infos = archive.infolist()
    if len(infos) > _MAX_ENTRIES:
        raise WindowsPackageIdentityError("package_catalog_unreadable", "The patch package catalog cannot be read")
    size_limit = PATCH_MGMT_MAX_PACKAGE_SIZE_MB * 1024 * 1024
    found: set[str] = set()
    names: list[str] = []
    nested = 0
    for info in infos:
        if info.file_size > size_limit:
            raise WindowsPackageIdentityError("package_catalog_unreadable", "The patch package catalog cannot be read")
        entry_name = info.filename.rsplit("/", 1)[-1]
        if not entry_name.lower().endswith(".cab"):
            continue
        nested += 1
        if nested > _MAX_NESTED_CABS:
            raise WindowsPackageIdentityError("package_catalog_unreadable", "The patch package catalog cannot be read")
        payload = archive.read(info)
        if payload[:4] != b"MSCF":
            raise WindowsPackageIdentityError("package_unsigned", "The patch package is not signed by Microsoft")
        entry_kbs, entry_names = _inspect_cabinet(payload, trust_store=trust_store)
        found.update(entry_kbs)
        names.extend(entry_names)
    if nested == 0:
        raise WindowsPackageIdentityError("package_unsigned", "The patch package is not signed by Microsoft")
    return frozenset(found), tuple(names)


def inspect_windows_update_package(
    payload: bytes,
    *,
    expected_kb: str,
    file_name: str,
    declared_dotnet_version: str = "",
    trust_store: CertificateStore | None = None,
) -> WindowsPackageIdentity:
    """校验签名和包内 KB，并解析 .NET 版本标记。"""
    if len(payload) > PATCH_MGMT_MAX_PACKAGE_SIZE_MB * 1024 * 1024:
        raise WindowsPackageIdentityError(
            "package_too_large",
            "The patch package cannot exceed {limit} MB",
            limit=PATCH_MGMT_MAX_PACKAGE_SIZE_MB,
        )
    expected = _normalize_kb(expected_kb)
    if payload[:4] == b"MSCF":
        found, names = _inspect_cabinet(payload, trust_store=trust_store)
    elif payload[:2] == b"PK":
        found, names = _inspect_zip(payload, trust_store=trust_store)
    else:
        raise WindowsPackageIdentityError("package_unsigned", "The patch package is not signed by Microsoft")
    if expected not in found:
        raise WindowsPackageIdentityError("package_kb_mismatch", "The KB inside the patch package does not match this patch")
    try:
        dotnet_version = resolve_dotnet_version(
            file_name=file_name,
            entry_names=names,
            declared=declared_dotnet_version,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "declared":
            raise WindowsPackageIdentityError("package_dotnet_invalid", "The declared .NET version is invalid") from exc
        if code in {"conflict", "declared-conflict", "multiple"}:
            raise WindowsPackageIdentityError("package_dotnet_conflict", "The declared .NET version does not match the package marker") from exc
        raise WindowsPackageIdentityError("package_dotnet_conflict", "The declared .NET version does not match the package marker") from exc
    return WindowsPackageIdentity(kb_numbers=found, dotnet_version=dotnet_version)


def read_package_bytes(uploaded_file) -> bytes:
    """把上传文件读入有界缓冲。调用方已经限制过声明大小。"""
    limit = PATCH_MGMT_MAX_PACKAGE_SIZE_MB * 1024 * 1024
    uploaded_file.seek(0)
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    total = 0
    try:
        while True:
            chunk = uploaded_file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise WindowsPackageIdentityError(
                    "package_too_large",
                    "The patch package cannot exceed {limit} MB",
                    limit=PATCH_MGMT_MAX_PACKAGE_SIZE_MB,
                )
            spool.write(chunk)
        spool.seek(0)
        return spool.read()
    finally:
        spool.close()
        uploaded_file.seek(0)


def package_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

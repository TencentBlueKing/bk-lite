"""手工 Windows 包必须是微软签名更新，且 KB 与 .NET 标记可核对。"""

from __future__ import annotations

import hashlib
import struct
from datetime import datetime, timedelta, timezone

import pytest
from asn1crypto import cms
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from django.core.files.uploadedfile import SimpleUploadedFile
from signify.asn1 import spc
from signify.x509.certificates import Certificate
from signify.x509.context import CertificateStore

from apps.patch_mgmt.constants import OSType, PackageStatus, RequirementAssessmentStatus
from apps.patch_mgmt.models import Patch, WindowsPatchDetail
from apps.patch_mgmt.services.windows_dotnet import classify_dotnet_release, dotnet_version_from_text, windows_dotnet_decision
from apps.patch_mgmt.services.windows_package import WindowsPackageError, store_windows_package
from apps.patch_mgmt.services.windows_package_identity import WindowsPackageIdentityError, _cabinet_imprint, inspect_windows_update_package


def test_filename_tokens_prefer_the_longer_marker():
    assert dotnet_version_from_text("Windows11.0-KB1-x64-NDP481-24H2.msu") == "4.8.1"
    assert dotnet_version_from_text("Windows10.0-KB1-x64-ndp48.msu") == "4.8"
    assert dotnet_version_from_text("package-NDP472.cab") == "4.7.2"
    assert dotnet_version_from_text("Windows10.0-KB1-x64.msu") == ""


def test_release_boundaries_match_the_published_ranges():
    assert classify_dotnet_release(533509) == "4.8.1"
    assert classify_dotnet_release(533320) == "4.8.1"
    assert classify_dotnet_release(533319) == "4.8"
    assert classify_dotnet_release(528040) == "4.8"
    assert classify_dotnet_release(528039) == "4.7.2"
    assert classify_dotnet_release(461808) == "4.7.2"
    assert classify_dotnet_release(461807) == ""
    assert classify_dotnet_release(None) == ""


def test_dotnet_mismatch_names_both_versions_and_missing_release_stays_unknown():
    status, reason = windows_dotnet_decision("4.8", 533320, "KB1")
    assert status == RequirementAssessmentStatus.NOT_APPLICABLE
    assert "4.8" in reason
    assert "533320" in reason
    assert "4.8.1" in reason

    status, reason = windows_dotnet_decision("4.8.1", None, "KB1")
    assert status == RequirementAssessmentStatus.UNKNOWN
    assert "KB1" in reason

    assert windows_dotnet_decision("", 533320, "KB1") == ("", "")
    assert windows_dotnet_decision("4.8.1", 533325, "KB1") == ("", "")


def _test_authority() -> tuple[RSAPrivateKey, x509.Certificate, CertificateStore]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "BKLite Test Update")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=False)
        .sign(key, hashes.SHA256())
    )
    store = CertificateStore(trusted=True)
    store.append(Certificate.from_der(cert.public_bytes(serialization.Encoding.DER)))
    return key, cert, store


def _pkcs7(key: RSAPrivateKey, cert: x509.Certificate, file_digest: bytes, signature: bytes | None) -> bytes:
    indirect = spc.SpcIndirectDataContent(
        {
            "data": {
                "type": "microsoft_spc_pe_image_data",
                "value": {"flags": set(), "file": {"file": {"unicode": "<<<Obsolete>>>"}}},
            },
            "message_digest": {
                "digest_algorithm": {"algorithm": "sha256"},
                "digest": file_digest,
            },
        }
    )
    attrs = cms.CMSAttributes(
        [
            cms.CMSAttribute({"type": "content_type", "values": ["microsoft_spc_indirect_data_content"]}),
            cms.CMSAttribute({"type": "message_digest", "values": [hashlib.sha256(indirect.contents).digest()]}),
        ]
    )
    if signature is None:
        encoded_attrs = bytearray(attrs.dump())
        if encoded_attrs[0] == 0xA0:
            encoded_attrs[0] = 0x31
        signature = key.sign(bytes(encoded_attrs), padding.PKCS1v15(), hashes.SHA256())
    cert_asn1 = asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
    signed = cms.SignedData(
        {
            "version": "v1",
            "digest_algorithms": [cms.DigestAlgorithm({"algorithm": "sha256"})],
            "encap_content_info": {
                "content_type": "microsoft_spc_indirect_data_content",
                "content": indirect,
            },
            "certificates": [cert_asn1],
            "signer_infos": [
                cms.SignerInfo(
                    {
                        "version": "v1",
                        "sid": cms.SignerIdentifier(
                            {
                                "issuer_and_serial_number": cms.IssuerAndSerialNumber(
                                    {"issuer": cert_asn1.issuer, "serial_number": cert_asn1.serial_number}
                                )
                            }
                        ),
                        "digest_algorithm": cms.DigestAlgorithm({"algorithm": "sha256"}),
                        "signed_attrs": attrs,
                        "signature_algorithm": cms.SignedDigestAlgorithm({"algorithm": "sha256_rsa"}),
                        "signature": signature,
                    }
                )
            ],
        }
    )
    return cms.ContentInfo({"content_type": "signed_data", "content": signed}).dump()


def _cabinet(names: list[str], signature: bytes) -> bytes:
    files = b""
    for name in names:
        files += struct.pack("<IIHHHH", 1, 0, 0, 0, 0, 0) + name.encode("ascii") + b"\x00"
    signature_start = 60 + len(files)
    reserve = struct.pack("<IIIII", 0x00100000, signature_start, len(signature), 0, 0)
    header = struct.pack(
        "<4sIIIIIBBHHHHH",
        b"MSCF",
        0,
        signature_start,
        0,
        60,
        0,
        3,
        1,
        0,
        len(names),
        0x0004,
        0,
        0,
    )
    return header + struct.pack("<HBB", 20, 0, 0) + reserve + files + signature


def _signed_cabinet(names: list[str]) -> tuple[bytes, CertificateStore]:
    key, cert, store = _test_authority()
    placeholder = _pkcs7(key, cert, b"\x00" * 32, b"\x11" * 256)
    body = _cabinet(names, placeholder)
    start = len(body) - len(placeholder)
    file_digest = _cabinet_imprint(body, start, hashlib.sha256)
    signature = _pkcs7(key, cert, file_digest, None)
    if len(signature) != len(placeholder):
        placeholder = _pkcs7(key, cert, b"\x00" * 32, b"\x11" * (256 + len(signature) - len(placeholder)))
        body = _cabinet(names, placeholder)
        start = len(body) - len(placeholder)
        file_digest = _cabinet_imprint(body, start, hashlib.sha256)
        signature = _pkcs7(key, cert, file_digest, None)
    assert len(signature) == len(placeholder)
    return body[:start] + signature, store


def test_signed_package_records_the_inner_marker_and_rejects_a_different_kb():
    payload, store = _signed_cabinet(["Windows10.0-KB6000101-x64-NDP481.cab"])

    accepted = inspect_windows_update_package(
        payload,
        expected_kb="KB6000101",
        file_name="renamed.msu",
        trust_store=store,
    )

    assert accepted.dotnet_version == "4.8.1"
    with pytest.raises(WindowsPackageIdentityError) as mismatch:
        inspect_windows_update_package(
            payload,
            expected_kb="KB6000102",
            file_name="renamed.msu",
            trust_store=store,
        )
    assert mismatch.value.code == "package_kb_mismatch"


def test_declared_version_cannot_contradict_the_filename():
    payload, store = _signed_cabinet(["Windows10.0-KB6000101-x64.cab"])

    with pytest.raises(WindowsPackageIdentityError) as conflict:
        inspect_windows_update_package(
            payload,
            expected_kb="KB6000101",
            file_name="update-NDP48.msu",
            declared_dotnet_version="4.8.1",
            trust_store=store,
        )
    assert conflict.value.code == "package_dotnet_conflict"


def test_unsigned_container_is_rejected():
    with pytest.raises(WindowsPackageIdentityError) as unsigned:
        inspect_windows_update_package(
            b"MSCF" + b"not-a-real-update",
            expected_kb="KB6000101",
            file_name="update.msu",
        )
    assert unsigned.value.code == "package_unsigned"


@pytest.mark.django_db
def test_store_rejects_unsigned_package_and_marks_the_patch_failed():
    patch = Patch.objects.create(title="未签名", os_type=OSType.WINDOWS, pkg_status=PackageStatus.DOWNLOADING, team=[1])
    WindowsPatchDetail.objects.create(patch=patch, kb_number="KB6000101")

    with pytest.raises(WindowsPackageError) as rejected:
        store_windows_package(patch, SimpleUploadedFile("update.msu", b"MSCF" + b"junk"))
    assert rejected.value.code == "package_unsigned"

    patch.refresh_from_db()
    assert patch.pkg_status == PackageStatus.DOWNLOAD_FAILED

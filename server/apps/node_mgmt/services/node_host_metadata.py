import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

HOST_METADATA_CACHE_VERSION = 1
HOST_METADATA_FINGERPRINT_KEY = "host_identity_fingerprint"
HOST_METADATA_RESERVED_KEYS = frozenset(
    {
        "node.name_b64",
        "node.ip_b64",
        "node__name_b64",
        "node__ip_b64",
    }
)


def _encode_utf8_base64(value: str) -> str:
    return base64.b64encode(str(value or "").encode("utf-8")).decode("ascii")


@dataclass(frozen=True)
class NodeHostMetadataRenderContext:
    """Trusted render values and cache identity for Node host metadata."""

    variables: Mapping[str, str]
    fingerprint: str

    @classmethod
    def build(cls, name: str, ip: str):
        normalized_name = str(name or "")
        normalized_ip = str(ip or "")
        identity = json.dumps([normalized_name, normalized_ip], ensure_ascii=False, separators=(",", ":"))
        encoded_name = _encode_utf8_base64(normalized_name)
        encoded_ip = _encode_utf8_base64(normalized_ip)
        return cls(
            variables={
                "node.name_b64": encoded_name,
                "node.ip_b64": encoded_ip,
                "node__name_b64": encoded_name,
                "node__ip_b64": encoded_ip,
            },
            fingerprint=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        )

    @staticmethod
    def without_reserved_variables(variables: Mapping | None) -> dict:
        return {key: value for key, value in (variables or {}).items() if key not in HOST_METADATA_RESERVED_KEYS}

    @classmethod
    def prepare_template_variables(cls, variables: Mapping | None, trusted_reserved_variables: Mapping | None = None) -> dict:
        prepared = cls.without_reserved_variables(variables)
        prepared.update({key: value for key, value in (trusted_reserved_variables or {}).items() if key in HOST_METADATA_RESERVED_KEYS})
        return prepared

    def build_cache_entry(self, etag: str) -> dict:
        return {
            "version": HOST_METADATA_CACHE_VERSION,
            "etag": etag,
            HOST_METADATA_FINGERPRINT_KEY: self.fingerprint,
        }

    def matches_cache_entry(self, cached_entry, client_etag: str | None) -> bool:
        return (
            isinstance(cached_entry, dict)
            and cached_entry.get("version") == HOST_METADATA_CACHE_VERSION
            and cached_entry.get("etag") == client_etag
            and cached_entry.get(HOST_METADATA_FINGERPRINT_KEY) == self.fingerprint
        )

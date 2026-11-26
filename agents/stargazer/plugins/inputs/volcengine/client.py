# -*- coding: utf-8 -*-
"""火山引擎 OpenAPI / TOS 清单客户端。

传输层可注入，测试不访问公网。签名只放在请求头里，日志不记录密钥、请求体和响应体。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

_RETRYABLE_CODES = {"FlowLimitExceeded", "RequestLimitExceeded", "Throttling", "AccountFlowLimitExceeded"}
_MAX_PAGES = 200
_MAX_BODY = 8 * 1024 * 1024
_BOOTSTRAP_REGION = "cn-beijing"


class VolcengineApiError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = str(code or "Error")
        self.message = str(message or "")
        super().__init__(self.code if not self.message else f"{self.code}: {self.message}")


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hmac_sha256(key: bytes, content: str) -> bytes:
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="-_.~")


def _canonical_query(params: dict) -> str:
    parts = []
    for key in sorted(params):
        parts.append(f"{_quote(key)}={_quote(params[key])}")
    return "&".join(parts)


def _sign(secret: str, date_stamp: str, region: str, service: str, string_to_sign: str) -> str:
    key = _hmac_sha256(secret.encode("utf-8"), date_stamp)
    key = _hmac_sha256(key, region)
    key = _hmac_sha256(key, service)
    key = _hmac_sha256(key, "request")
    return hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


def _authorization(algorithm: str, access_key: str, scope: str, signed_headers: str, signature: str) -> str:
    return f"{algorithm} Credential={access_key}/{scope}, SignedHeaders={signed_headers}, Signature={signature}"


def _xml_text(node, name: str) -> str:
    if node is None:
        return ""
    for child in list(node):
        tag = child.tag.split("}", 1)[-1]
        if tag == name and child.text:
            return child.text.strip()
    return ""


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


class VolcengineClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str = "",
        endpoint: str = "",
        transport=None,
        sleeper=None,
        clock=None,
        max_attempts: int = 3,
    ):
        self.access_key = access_key or ""
        self.secret_key = secret_key or ""
        self.region = region or ""
        self.endpoint = (endpoint or "").strip()
        self.transport = transport or _urllib_transport
        self.sleeper = sleeper or time.sleep
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_attempts = max_attempts

    def describe_regions(self) -> list[dict]:
        region = self.region or _BOOTSTRAP_REGION
        rows = self._paginate_token(
            service="ecs",
            version="2020-04-01",
            action="DescribeRegions",
            region=region,
            page_size=20,
            list_keys=("Regions",),
        )
        return rows

    def describe_instances(self) -> list[dict]:
        return self._paginate_token(
            service="ecs",
            version="2020-04-01",
            action="DescribeInstances",
            region=self._require_region(),
            page_size=100,
            list_keys=("Instances",),
        )

    def describe_eips(self) -> list[dict]:
        return self._paginate_token(
            service="vpc",
            version="2020-04-01",
            action="DescribeEipAddresses",
            region=self._require_region(),
            page_size=100,
            list_keys=("EipAddresses",),
        )

    def describe_load_balancers(self) -> list[dict]:
        return self._paginate_page(
            service="clb",
            version="2020-04-01",
            action="DescribeLoadBalancers",
            region=self._require_region(),
            page_size=100,
            list_keys=("LoadBalancers",),
        )

    def describe_mysql(self) -> list[dict]:
        return self._paginate_page(
            service="rds_mysql",
            version="2022-01-01",
            action="DescribeDBInstances",
            region=self._require_region(),
            page_size=100,
            list_keys=("Instances", "DBInstances", "Datas"),
        )

    def describe_postgresql(self) -> list[dict]:
        return self._paginate_page(
            service="rds_postgresql",
            version="2022-01-01",
            action="DescribeDBInstances",
            region=self._require_region(),
            page_size=100,
            list_keys=("Instances", "DBInstances", "Datas"),
        )

    def list_buckets(self) -> list[dict]:
        region = self._require_region()
        marker = ""
        buckets = []
        for _ in range(_MAX_PAGES):
            payload = self._request_tos(region, marker)
            buckets.extend(payload["buckets"])
            if not payload["truncated"]:
                return buckets
            marker = payload["next"]
            if not marker:
                raise VolcengineApiError("Truncated", "missing marker")
        raise VolcengineApiError("Truncated", "too many pages")

    def _require_region(self) -> str:
        if not self.region:
            raise VolcengineApiError("MissingRegion", "region is required")
        return self.region

    def _paginate_token(self, *, service, version, action, region, page_size, list_keys) -> list[dict]:
        token = ""
        seen = set()
        rows = []
        for _ in range(_MAX_PAGES):
            body = {"MaxResults": page_size}
            if token:
                body["NextToken"] = token
            result = self._request_openapi(service, version, action, body, region)
            rows.extend(self._rows(result, list_keys))
            token = str(result.get("NextToken") or "")
            if not token:
                return rows
            if token in seen:
                raise VolcengineApiError("Truncated", "repeated token")
            seen.add(token)
        raise VolcengineApiError("Truncated", "too many pages")

    def _paginate_page(self, *, service, version, action, region, page_size, list_keys) -> list[dict]:
        page = 1
        rows = []
        total = None
        for _ in range(_MAX_PAGES):
            result = self._request_openapi(
                service,
                version,
                action,
                {"PageNumber": page, "PageSize": page_size},
                region,
            )
            batch = self._rows(result, list_keys)
            if total is None:
                total = self._total(result)
            rows.extend(batch)
            if total is not None and len(rows) >= total:
                return rows
            if len(batch) < page_size:
                if total is not None and len(rows) < total:
                    raise VolcengineApiError("Truncated", "short page")
                return rows
            page += 1
        raise VolcengineApiError("Truncated", "too many pages")

    @staticmethod
    def _total(result: dict):
        for key in ("TotalCount", "Total"):
            if result.get(key) in (None, ""):
                continue
            try:
                return int(result[key])
            except (TypeError, ValueError):
                return None
        return None

    @classmethod
    def _rows(cls, result: dict, keys: tuple[str, ...]) -> list[dict]:
        if not isinstance(result, dict):
            raise VolcengineApiError("InvalidResponse", "result is not an object")
        for key in keys:
            found = cls._as_list(result.get(key))
            if found is not None:
                return found
        if any(result.get(key) for key in ("TaskId", "TaskID", "task_id")):
            raise VolcengineApiError("AsyncTask", "instance list missing")
        return []

    @staticmethod
    def _as_list(value):
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for nested in value.values():
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
            return [value] if value else []
        return None

    def _request_openapi(self, service: str, version: str, action: str, body: dict, region: str) -> dict:
        attempt = 0
        while True:
            attempt += 1
            status, payload = self._signed_openapi(service, version, action, body, region)
            try:
                return self._unwrap(status, payload)
            except VolcengineApiError as exc:
                if attempt >= self.max_attempts or not _retryable(status, exc):
                    raise
                self.sleeper(0.2 * (2 ** (attempt - 1)))

    def _request_tos(self, region: str, marker: str) -> dict:
        attempt = 0
        while True:
            attempt += 1
            status, payload = self._signed_tos(region, marker)
            try:
                return self._unwrap_tos(status, payload)
            except VolcengineApiError as exc:
                if attempt >= self.max_attempts or not _retryable(status, exc):
                    raise
                self.sleeper(0.2 * (2 ** (attempt - 1)))

    def _signed_openapi(self, service: str, version: str, action: str, body: dict, region: str):
        host_name, url_base = self._target(self._service_host(service, region))
        payload = json.dumps(body or {}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        now = self.clock()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        content_hash = _sha256_hex(payload)
        query = _canonical_query({"Action": action, "Version": version})
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical_headers = f"content-type:application/json\nhost:{host_name}\nx-content-sha256:{content_hash}\nx-date:{amz_date}\n"
        canonical = "\n".join(["POST", "/", query, canonical_headers, signed_headers, content_hash])
        scope = f"{date_stamp}/{region}/{self._sign_service(service)}/request"
        string_to_sign = "\n".join(["HMAC-SHA256", amz_date, scope, _sha256_hex(canonical.encode("utf-8"))])
        signature = _sign(self.secret_key, date_stamp, region, self._sign_service(service), string_to_sign)
        headers = {
            "Content-Type": "application/json",
            "Host": host_name,
            "X-Date": amz_date,
            "X-Content-Sha256": content_hash,
            "Authorization": _authorization("HMAC-SHA256", self.access_key, scope, signed_headers, signature),
        }
        return self.transport("POST", f"{url_base}/?{query}", headers, payload)

    def _signed_tos(self, region: str, marker: str):
        host_name, url_base = self._target(self._tos_host(region))
        now = self.clock()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        content_hash = _sha256_hex(b"")
        query = _canonical_query({"marker": marker}) if marker else ""
        signed_headers = "host;x-tos-content-sha256;x-tos-date"
        canonical_headers = f"host:{host_name}\nx-tos-content-sha256:{content_hash}\nx-tos-date:{amz_date}\n"
        canonical = "\n".join(["GET", "/", query, canonical_headers, signed_headers, content_hash])
        scope = f"{date_stamp}/{region}/tos/request"
        string_to_sign = "\n".join(["TOS4-HMAC-SHA256", amz_date, scope, _sha256_hex(canonical.encode("utf-8"))])
        signature = _sign(self.secret_key, date_stamp, region, "tos", string_to_sign)
        headers = {
            "Host": host_name,
            "X-Tos-Date": amz_date,
            "X-Tos-Content-Sha256": content_hash,
            "Authorization": _authorization("TOS4-HMAC-SHA256", self.access_key, scope, signed_headers, signature),
        }
        url = f"{url_base}/" if not query else f"{url_base}/?{query}"
        return self.transport("GET", url, headers, b"")

    def _target(self, public_host: str) -> tuple[str, str]:
        if not self.endpoint:
            return public_host, f"https://{public_host}"
        parsed = urllib.parse.urlparse(self.endpoint if "://" in self.endpoint else f"https://{self.endpoint}")
        host_name = parsed.netloc or parsed.path
        scheme = parsed.scheme or "https"
        return host_name, f"{scheme}://{host_name}"

    @staticmethod
    def _service_host(service: str, region: str) -> str:
        names = {
            "ecs": "ecs",
            "vpc": "vpc",
            "clb": "clb",
            "rds_mysql": "rds-mysql",
            "rds_postgresql": "rds-postgresql",
        }
        return f"{names[service]}.{region}.volcengineapi.com"

    @staticmethod
    def _sign_service(service: str) -> str:
        if service.startswith("rds_"):
            return service.replace("_", "-")
        return service

    @staticmethod
    def _tos_host(region: str) -> str:
        return f"tos-{region}.volces.com"

    def _unwrap(self, status: int, payload) -> dict:
        data = _as_json(payload)
        error = _response_error(data)
        if error or status >= 400:
            code, message = error if error else (str(status), "")
            raise VolcengineApiError(code, _redact(message, self.secret_key, self.access_key))
        result = data.get("Result", data)
        if not isinstance(result, dict):
            raise VolcengineApiError("InvalidResponse", "result is not an object")
        return result

    def _unwrap_tos(self, status: int, payload) -> dict:
        if isinstance(payload, dict):
            error = _response_error(payload)
            if error or status >= 400:
                code, message = error if error else (str(status), "")
                raise VolcengineApiError(code, _redact(message, self.secret_key, self.access_key))
        text = payload if isinstance(payload, str) else ""
        if status >= 400 or (text.lstrip().startswith("<") and "<Error" in text):
            code, message = _xml_error(text)
            raise VolcengineApiError(code or str(status), _redact(message, self.secret_key, self.access_key))
        return _parse_buckets(text)


def _retryable(status: int, exc: VolcengineApiError) -> bool:
    return status == 429 or exc.code in _RETRYABLE_CODES


def _as_json(payload) -> dict:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str) and payload.strip():
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _response_error(data: dict):
    meta = data.get("ResponseMetadata") if isinstance(data, dict) else None
    error = None
    if isinstance(meta, dict):
        error = meta.get("Error")
    if error is None and isinstance(data, dict):
        error = data.get("Error")
    if not isinstance(error, dict) or not (error.get("Code") or error.get("Message")):
        return None
    return str(error.get("Code") or "Error"), str(error.get("Message") or "")


def _xml_error(text: str) -> tuple[str, str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return "Error", ""
    return _xml_text(root, "Code"), _xml_text(root, "Message")


def _parse_buckets(text: str) -> dict:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise VolcengineApiError("InvalidResponse", "bucket list is not xml") from exc
    buckets = []
    truncated = False
    marker = ""
    for node in root.iter():
        name = _local(node.tag)
        if name == "Bucket":
            buckets.append(
                {
                    "Name": _xml_text(node, "Name"),
                    "Location": _xml_text(node, "Location"),
                    "CreationDate": _xml_text(node, "CreationDate"),
                    "ExtranetEndpoint": _xml_text(node, "ExtranetEndpoint"),
                    "IntranetEndpoint": _xml_text(node, "IntranetEndpoint"),
                    "BucketType": _xml_text(node, "BucketType"),
                }
            )
        elif name == "IsTruncated":
            truncated = str(node.text or "").strip().lower() == "true"
        elif name in {"NextMarker", "Marker"} and node.text:
            marker = node.text.strip()
    return {"buckets": buckets, "truncated": truncated, "next": marker}


def _redact(message: str, *secrets: str) -> str:
    text = message or ""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "")
    return text[:200]


def _read_limited(stream) -> bytes:
    raw = stream.read(_MAX_BODY + 1)
    if len(raw or b"") > _MAX_BODY:
        raise VolcengineApiError("ResponseTooLarge", "")
    return raw or b""


def _urllib_transport(method: str, url: str, headers: dict, body: bytes):
    request = urllib.request.Request(url, data=body or None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = _read_limited(response)
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = _read_limited(exc)
        status = exc.code
    text = raw.decode("utf-8", errors="replace")
    stripped = text.lstrip()
    if stripped.startswith("<"):
        return status, text
    try:
        parsed = json.loads(text) if text else {}
    except json.JSONDecodeError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}

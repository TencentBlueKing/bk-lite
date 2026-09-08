import ipaddress
import json
from urllib.parse import unquote, urlsplit

import httpx
from core.collection.contracts import AccessProbeResult, AccessProbeStatus
from core.logger import logger, safe_exception_info, safe_log_value


class RedfishCollectionError(ValueError):
    pass


class PhyscialServerRedfishInfo:
    """只读 Redfish 整机基础信息采集器。"""

    MAX_RESPONSE_BYTES = 1024 * 1024
    MAX_COLLECTION_PAGES = 32

    def __init__(self, kwargs, *, transport=None):
        self.host = str(kwargs.get("host") or "").strip()
        self.port = int(kwargs.get("port", 443))
        self.username = str(kwargs.get("username", kwargs.get("user", "")))
        self.password = str(kwargs.get("password", ""))
        self.model_id = kwargs.get("model_id", "physcial_server")
        self.collection_task_id = kwargs.get("collection_task_id")
        raw_verify_tls = kwargs.get("verify_tls", True)
        self.verify_tls = (
            raw_verify_tls if isinstance(raw_verify_tls, bool) else str(raw_verify_tls).strip().lower() not in {"0", "false", "no", "off"}
        )
        self._transport = transport
        self.base_url = f"https://{self._url_host()}:{self.port}"

    def _url_host(self):
        try:
            address = ipaddress.ip_address(self.host)
        except ValueError as exc:
            raise RedfishCollectionError("Redfish target must be an IP address") from exc
        return f"[{address}]" if address.version == 6 else str(address)

    def _client(self):
        return httpx.AsyncClient(
            auth=httpx.BasicAuth(self.username, self.password),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            timeout=httpx.Timeout(10.0, connect=5.0),
            transport=self._transport,
            trust_env=False,
            verify=self.verify_tls,
        )

    def _resource_url(self, resource_link):
        raw_link = resource_link.get("@odata.id") if isinstance(resource_link, dict) else resource_link
        parsed = urlsplit(str(raw_link or ""))
        is_service_path = parsed.path == "/redfish/v1" or parsed.path.startswith("/redfish/v1/")
        decoded_segments = unquote(parsed.path).split("/")
        is_absolute = bool(parsed.scheme or parsed.netloc)
        if (
            not is_service_path
            or ".." in decoded_segments
            or "." in decoded_segments
            or parsed.fragment
            or (is_absolute and not self._is_same_origin(parsed))
        ):
            raise RedfishCollectionError("Redfish resource link must stay on the target service")
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{self.base_url}{parsed.path}{query}"

    def _is_same_origin(self, parsed):
        if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
            return False
        try:
            parsed_host = ipaddress.ip_address(parsed.hostname or "")
            target_host = ipaddress.ip_address(self.host)
            parsed_port = parsed.port if parsed.port is not None else 443
        except (ValueError, TypeError):
            return False
        return parsed_host == target_host and parsed_port == self.port

    async def _get_json(self, client, resource_link):
        url = self._resource_url(resource_link)
        async with client.stream("GET", url) as response:
            if response.status_code == 401:
                raise RedfishCollectionError("Redfish authentication failed")
            if response.status_code == 403:
                raise RedfishCollectionError("Redfish account lacks inventory permission")
            if response.status_code >= 500:
                raise RedfishCollectionError("Redfish service is unavailable")
            if response.status_code != 200:
                raise RedfishCollectionError(f"Redfish resource returned HTTP {response.status_code}")

            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > self.MAX_RESPONSE_BYTES:
                    raise RedfishCollectionError("Redfish response exceeds size limit")
        try:
            payload = json.loads(body)
        except (TypeError, ValueError, UnicodeError) as exc:
            raise RedfishCollectionError("Redfish resource returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RedfishCollectionError("Redfish resource must be a JSON object")
        return payload

    async def _get_system_members(self, client, collection_link):
        members = []
        next_link = collection_link
        visited = set()
        for _ in range(self.MAX_COLLECTION_PAGES):
            canonical_url = self._resource_url(next_link)
            if canonical_url in visited:
                raise RedfishCollectionError("Redfish Systems pagination contains a cycle")
            visited.add(canonical_url)

            page = await self._get_json(client, next_link)
            page_members = page.get("Members")
            if not isinstance(page_members, list):
                raise RedfishCollectionError("Redfish Systems collection must contain Members")
            members.extend(page_members)

            member_count = page.get("Members@odata.count")
            if member_count not in (None, ""):
                try:
                    member_count = int(member_count)
                except (TypeError, ValueError) as exc:
                    raise RedfishCollectionError("Redfish Systems member count is invalid") from exc
                if member_count != 1:
                    raise RedfishCollectionError("Redfish target must expose exactly one ComputerSystem")
            if len(members) > 1:
                raise RedfishCollectionError("Redfish target must expose exactly one ComputerSystem")

            next_link = page.get("Members@odata.nextLink")
            if not next_link:
                return members
        raise RedfishCollectionError("Redfish Systems pagination exceeds page limit")

    async def probe(self):
        try:
            async with self._client() as client:
                root = await self._get_json(client, "/redfish/v1/")
                if not root.get("Systems"):
                    return AccessProbeResult(
                        status=AccessProbeStatus.PROTOCOL_MISMATCH,
                        error_code="redfish_protocol_mismatch",
                    )
            return AccessProbeResult(
                status=AccessProbeStatus.READY,
                evidence={"redfish_version": str(root.get("RedfishVersion") or "")},
            )
        except RedfishCollectionError as exc:
            message = str(exc)
            if "authentication" in message:
                status = AccessProbeStatus.AUTH_FAILED
                code = "authentication_failed"
            elif "permission" in message:
                status = AccessProbeStatus.CAPABILITY_DENIED
                code = "capability_denied"
            elif "unavailable" in message:
                status = AccessProbeStatus.SERVICE_UNAVAILABLE
                code = "service_unavailable"
            else:
                status = AccessProbeStatus.PROTOCOL_MISMATCH
                code = "redfish_protocol_mismatch"
            return AccessProbeResult(status=status, error_code=code)
        except httpx.TimeoutException:
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="protocol_probe_no_response",
            )
        except httpx.HTTPError as exc:
            message = str(exc).lower()
            if "certificate" in message or "ssl" in message or "tls" in message:
                return AccessProbeResult(
                    status=AccessProbeStatus.TLS_VALIDATION_FAILED,
                    error_code="tls_validation_failed",
                )
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="protocol_probe_no_response",
            )

    async def list_all_resources(self):
        try:
            if not self.username or not self.password:
                raise RedfishCollectionError("Redfish username and password are required")
            async with self._client() as client:
                root = await self._get_json(client, "/redfish/v1/")
                members = await self._get_system_members(client, root.get("Systems"))
                if len(members) != 1:
                    raise RedfishCollectionError("Redfish target must expose exactly one ComputerSystem")
                system = await self._get_json(client, members[0])

            raw = {
                "ip_addr": self.host,
                "port": self.port,
                "serial_number": system.get("SerialNumber"),
                "model": system.get("Model"),
                "brand": system.get("Manufacturer"),
                "asset_code": system.get("AssetTag"),
            }
            result_data = {key: value for key, value in raw.items() if value not in (None, "")}
            return {"success": True, "result": {self.model_id: [result_data]}}
        except RedfishCollectionError as exc:
            logger.warning(
                "event=physical_server_redfish_collect_rejected host=%s task_id=%s failed_stage=inventory error_type=%s",
                safe_log_value(self.host),
                safe_log_value(self.collection_task_id or "-"),
                type(exc).__name__,
            )
            return {"result": {"cmdb_collect_error": str(exc)}, "success": False}
        except (httpx.HTTPError, ValueError) as exc:
            logger.error(
                "event=physical_server_redfish_collect_failed host=%s task_id=%s failed_stage=inventory error_type=%s",
                safe_log_value(self.host),
                safe_log_value(self.collection_task_id or "-"),
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            message = str(exc).lower()
            if isinstance(exc, httpx.HTTPError) and any(marker in message for marker in ("certificate", "ssl", "tls")):
                error = "Redfish TLS validation failed"
            else:
                error = "Redfish collection failed"
            return {"result": {"cmdb_collect_error": error}, "success": False}

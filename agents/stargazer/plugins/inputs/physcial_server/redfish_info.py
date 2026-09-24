import asyncio
import ipaddress
import json
import ssl
from urllib.parse import unquote, urlsplit

import httpx
from core.collection.contracts import AccessProbeResult, AccessProbeStatus
from core.logger import logger, safe_exception_info, safe_log_value
from plugins.inputs.physcial_server.redfish_inventory import build_redfish_result

# 部分 BMC（如 H3C HDM）仅提供 TLS_RSA_WITH_AES_256_GCM_SHA384；OpenSSL 3 默认 SECLEVEL 不含该套件。
_TLS_CIPHERS = ("DEFAULT:@SECLEVEL=0", "DEFAULT:@SECLEVEL=1", "DEFAULT")


def _tls_verify(verify_tls: bool):
    """构造 httpx verify：保留校验证书开关，只放宽套件以完成握手。"""
    if verify_tls:
        ctx = ssl.create_default_context()
    else:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    for cipher in _TLS_CIPHERS:
        try:
            ctx.set_ciphers(cipher)
            break
        except ssl.SSLError:
            continue
    return ctx


class RedfishCollectionError(ValueError):
    pass


class PhyscialServerRedfishInfo:
    """只读 Redfish 整机基础信息与可选子资源清单采集器。"""

    MAX_RESPONSE_BYTES = 1024 * 1024
    MAX_COLLECTION_PAGES = 32
    CHILD_CONCURRENCY = 4

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
        self._child_semaphore = asyncio.Semaphore(self.CHILD_CONCURRENCY)
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
            limits=httpx.Limits(
                max_connections=self.CHILD_CONCURRENCY,
                max_keepalive_connections=max(1, self.CHILD_CONCURRENCY // 2),
            ),
            timeout=httpx.Timeout(10.0, connect=5.0),
            transport=self._transport,
            trust_env=False,
            verify=_tls_verify(self.verify_tls),
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

    async def _get_collection_members(self, client, collection_link):
        members = []
        next_link = collection_link
        visited = set()
        for _ in range(self.MAX_COLLECTION_PAGES):
            canonical_url = self._resource_url(next_link)
            if canonical_url in visited:
                raise RedfishCollectionError("Redfish collection pagination contains a cycle")
            visited.add(canonical_url)
            page = await self._child_get_json(client, next_link)
            page_members = page.get("Members")
            if not isinstance(page_members, list):
                raise RedfishCollectionError("Redfish collection must contain Members")
            members.extend(page_members)
            next_link = page.get("Members@odata.nextLink")
            if not next_link:
                return members
        raise RedfishCollectionError("Redfish collection pagination exceeds page limit")

    async def _read_optional_collection(self, client, link):
        if not link:
            return None
        try:
            return await self._get_collection_members(client, link)
        except (RedfishCollectionError, httpx.HTTPError) as exc:
            self._log_child_skip(exc)
            return None

    async def _child_get_json(self, client, resource_link):
        async with self._child_semaphore:
            return await self._get_json(client, resource_link)

    async def _read_resource(self, client, link):
        try:
            return await self._child_get_json(client, link)
        except (RedfishCollectionError, httpx.HTTPError) as exc:
            self._log_child_skip(exc)
            return None

    def _log_child_skip(self, exc):
        logger.warning(
            "event=physical_server_redfish_child_skipped host=%s task_id=%s failed_stage=child_collection error_type=%s",
            safe_log_value(self.host),
            safe_log_value(self.collection_task_id or "-"),
            type(exc).__name__,
        )

    def _as_links(self, value):
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        return []

    async def _read_linked_resources(self, client, links):
        unique_links = []
        seen = set()
        for link in links:
            try:
                canonical_url = self._resource_url(link)
            except RedfishCollectionError as exc:
                self._log_child_skip(exc)
                continue
            if canonical_url in seen:
                continue
            seen.add(canonical_url)
            unique_links.append(link)
        if not unique_links:
            return []
        results = await asyncio.gather(*(self._read_resource(client, link) for link in unique_links))
        return [resource for resource in results if resource is not None]

    async def _read_inventory(self, client, system):
        processors, memory, drives, chassis_inventory = await asyncio.gather(
            self._read_collection_resources(client, system.get("Processors")),
            self._read_collection_resources(client, system.get("Memory")),
            self._read_drives(client, system.get("Storage")),
            self._read_chassis_inventory(client, system),
        )
        assemblies, nic_records = chassis_inventory
        return {
            "processors": processors,
            "memory": memory,
            "drives": drives,
            "nic_records": nic_records,
            "assemblies": assemblies,
        }

    async def _read_collection_resources(self, client, link):
        links = await self._read_optional_collection(client, link)
        if links is None:
            return None
        return await self._read_linked_resources(client, links)

    async def _read_drives(self, client, storage_link):
        storage_links = await self._read_optional_collection(client, storage_link)
        if storage_links is None:
            return None
        storages = await self._read_linked_resources(client, storage_links)
        drive_links = []
        for storage in storages:
            drives = storage.get("Drives")
            if isinstance(drives, list):
                drive_links.extend(self._as_links(drives))
            elif isinstance(drives, dict):
                members = await self._read_optional_collection(client, drives)
                if members:
                    drive_links.extend(members)
        return await self._read_linked_resources(client, drive_links)

    async def _read_chassis_inventory(self, client, system):
        links = system.get("Links") if isinstance(system.get("Links"), dict) else {}
        chassis_resources = await self._read_linked_resources(client, self._as_links(links.get("Chassis")))
        assemblies = []
        nic_records = []
        adapter_sources = []
        if system.get("NetworkAdapters"):
            adapter_sources.append(system.get("NetworkAdapters"))
        saw_assembly = False
        for chassis in chassis_resources:
            if chassis.get("Assembly"):
                saw_assembly = True
                assembly = await self._read_resource(client, chassis.get("Assembly"))
                members = assembly.get("Assemblies") if isinstance(assembly, dict) else None
                if isinstance(members, list):
                    assemblies.extend(members)
            if chassis.get("NetworkAdapters"):
                adapter_sources.append(chassis.get("NetworkAdapters"))
        successful_adapter_sources = 0
        for source in adapter_sources:
            adapters = await self._read_optional_collection(client, source)
            if adapters is None:
                continue
            successful_adapter_sources += 1
            for adapter in await self._read_linked_resources(client, adapters):
                functions = await self._read_optional_collection(client, adapter.get("NetworkDeviceFunctions"))
                if not functions:
                    continue
                for function in await self._read_linked_resources(client, functions):
                    nic_records.append({"adapter": adapter, "function": function})
        if not saw_assembly:
            assemblies = None
        if not adapter_sources or successful_adapter_sources == 0:
            nic_records = None
        return assemblies, nic_records

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
                inventory = await self._read_inventory(client, system)

            server = {
                "ip_addr": self.host,
                "port": self.port,
                "serial_number": system.get("SerialNumber"),
                "model": system.get("Model"),
                "brand": system.get("Manufacturer"),
                "asset_code": system.get("AssetTag"),
            }
            return {"success": True, "result": build_redfish_result(server, **inventory)}
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

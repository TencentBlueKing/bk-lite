#!/usr/bin/env python3
"""批量验证 Stargazer SNMP 网络设备采集的协议连通性。"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass
from typing import Awaitable, Callable

SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"
DEFAULT_MAX_HOSTS = 1024
MAX_CONCURRENCY = 256


@dataclass(frozen=True)
class ProbeResult:
    host: str
    port: int
    status: str
    detail: str
    elapsed_ms: int
    sys_name: str = ""

    @property
    def success(self) -> bool:
        return self.status == "success"


def _append_target(targets: list[str], seen: set[str], address: ipaddress.IPv4Address, max_hosts: int) -> None:
    text = str(address)
    if text in seen:
        return
    if len(targets) >= max_hosts:
        raise ValueError(f"目标数量超过安全上限 {max_hosts}，请缩小 IP 段或显式调大 --max-hosts")
    seen.add(text)
    targets.append(text)


def expand_targets(specs: list[str], *, max_hosts: int = DEFAULT_MAX_HOSTS) -> list[str]:
    """展开单 IP、CIDR、起止 IP；保持输入顺序并去重。"""
    if max_hosts < 1:
        raise ValueError("--max-hosts 必须大于 0")

    targets: list[str] = []
    seen: set[str] = set()
    tokens = [token.strip() for spec in specs for token in spec.split(",") if token.strip()]
    if not tokens:
        raise ValueError("至少需要一个 IP、CIDR 或 IP 范围")

    for token in tokens:
        try:
            if "-" in token:
                start_text, end_text = (part.strip() for part in token.split("-", 1))
                start = ipaddress.ip_address(start_text)
                end = ipaddress.ip_address(end_text)
                if not isinstance(start, ipaddress.IPv4Address) or not isinstance(end, ipaddress.IPv4Address):
                    raise ValueError("目前仅支持 IPv4")
                if int(end) < int(start):
                    raise ValueError("范围结束 IP 小于起始 IP")
                if int(end) - int(start) + 1 > max_hosts:
                    raise ValueError(f"目标数量超过安全上限 {max_hosts}")
                for value in range(int(start), int(end) + 1):
                    _append_target(targets, seen, ipaddress.IPv4Address(value), max_hosts)
            elif "/" in token:
                network = ipaddress.ip_network(token, strict=False)
                if not isinstance(network, ipaddress.IPv4Network):
                    raise ValueError("目前仅支持 IPv4")
                if network.num_addresses > max_hosts + 2:
                    raise ValueError(f"目标数量超过安全上限 {max_hosts}")
                for address in network.hosts():
                    _append_target(targets, seen, address, max_hosts)
            else:
                address = ipaddress.ip_address(token)
                if not isinstance(address, ipaddress.IPv4Address):
                    raise ValueError("目前仅支持 IPv4")
                _append_target(targets, seen, address, max_hosts)
        except ValueError as error:
            message = str(error)
            if "安全上限" in message:
                raise
            raise ValueError(f"无效目标 {token!r}: {message}") from error
    return targets


def _secret_value(args: argparse.Namespace, value_name: str, env_name: str) -> str:
    direct = getattr(args, value_name, None)
    configured_env = getattr(args, env_name, None)
    return str(direct or (os.getenv(configured_env, "") if configured_env else ""))


def build_credential(args: argparse.Namespace) -> dict:
    """构造与 plugins.inputs.network.snmp_facts 相同字段名的凭据。"""
    version = str(args.version).lower()
    if version in {"v2", "v2c"}:
        community = _secret_value(args, "community", "community_env")
        if not community:
            raise ValueError("SNMP v2c 必须通过 --community 或 --community-env 提供 community")
        return {"version": version, "community": community}

    username = _secret_value(args, "username", "username_env")
    auth_key = _secret_value(args, "auth_key", "auth_key_env")
    priv_key = _secret_value(args, "priv_key", "priv_key_env")
    if not username:
        raise ValueError("SNMP v3 必须通过 --username 或 --username-env 提供 username")
    if len(auth_key) < 8:
        raise ValueError("SNMP v3 auth key 至少需要 8 个字符")
    if args.level == "authPriv" and len(priv_key) < 8:
        raise ValueError("SNMP v3 authPriv 的 privacy key 至少需要 8 个字符")
    return {
        "version": "v3",
        "username": username,
        "level": args.level,
        "integrity": args.integrity,
        "privacy": args.privacy,
        "authkey": auth_key,
        "privkey": priv_key,
    }


def local_route_probe(host: str, port: int) -> tuple[bool, str]:
    """检查操作系统是否有到目标的本地路由；UDP connect 不代表远端端口可达。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((host, port))
        source = sock.getsockname()[0]
        return True, f"本地路由存在(source={source})"
    except OSError as error:
        return False, f"本地路由失败({type(error).__name__}: {error})"
    finally:
        sock.close()


async def _snmp_get(host: str, port: int, timeout: float, retries: int, credential: dict):
    """按生产 SnmpFacts 的认证/传输参数，GET 同一个 sysName.0 OID。"""
    from core.infra.snmp_engine_pool import shared_snmp_engine
    from plugins.inputs.network import snmp_facts

    if credential["version"] in {"v2", "v2c"}:
        auth = snmp_facts.CommunityData(credential["community"])
    elif credential["level"] == "authNoPriv":
        auth = snmp_facts.UsmUserData(
            credential["username"],
            authKey=credential["authkey"],
            authProtocol={
                "sha": snmp_facts.usmHMACSHAAuthProtocol,
                "md5": snmp_facts.usmHMACMD5AuthProtocol,
            }[credential["integrity"]],
        )
    else:
        auth = snmp_facts.UsmUserData(
            credential["username"],
            authKey=credential["authkey"],
            privKey=credential["privkey"],
            authProtocol={
                "sha": snmp_facts.usmHMACSHAAuthProtocol,
                "md5": snmp_facts.usmHMACMD5AuthProtocol,
            }[credential["integrity"]],
            privProtocol={
                "aes": snmp_facts.usmAesCfb128Protocol,
                "des": snmp_facts.usmDESPrivProtocol,
            }[credential["privacy"]],
        )
    target = snmp_facts.UdpTransportTarget((host, port), timeout=timeout, retries=retries)
    async with shared_snmp_engine(auth, target=(host, port)) as engine:
        return await snmp_facts.getCmd(
            engine,
            auth,
            target,
            snmp_facts.ContextData(),
            snmp_facts.ObjectType(snmp_facts.ObjectIdentity(SYS_NAME_OID)),
            lookupMib=False,
        )


def _safe_text(value, *, limit: int = 160) -> str:
    pretty = getattr(value, "prettyPrint", None)
    text = str(pretty() if callable(pretty) else value)
    text = "".join(character if character.isprintable() else "?" for character in text)
    return text[:limit]


def _classify_indication(indication: object, *, credential: dict) -> tuple[str, str]:
    raw = _safe_text(indication)
    for field in ("community", "username", "authkey", "privkey"):
        secret = str(credential.get(field) or "")
        if secret:
            raw = raw.replace(secret, "[REDACTED]")
    normalized = raw.lower()
    if any(token in normalized for token in ("authorization", "authentication", "unknown user", "usm")):
        return "auth_failed", f"设备明确返回 SNMP 认证失败: {raw}"
    if "refused" in normalized:
        return "snmp_rejected", f"目标立即拒绝 UDP/SNMP 请求: {raw}"
    if "timeout" in normalized or "no response" in normalized:
        credential_hint = "，也可能是 community 错误后设备静默丢弃" if credential["version"] in {"v2", "v2c"} else ""
        return (
            "snmp_timeout",
            "本地路由存在，但未收到 SNMP 响应；可能是网络/ACL、UDP 161、SNMP 服务或设备策略问题" f"{credential_hint}: {raw}",
        )
    return "snmp_error", f"SNMP 客户端错误: {raw}"


async def probe_host(
    host: str,
    *,
    port: int,
    timeout: float,
    retries: int,
    credential: dict,
    snmp_get: Callable[[str, int, float, int, dict], Awaitable] = _snmp_get,
    route_probe: Callable[[str, int], tuple[bool, str]] = local_route_probe,
) -> ProbeResult:
    started = time.monotonic()
    route_ok, route_detail = route_probe(host, port)
    if not route_ok:
        return ProbeResult(host, port, "network_unreachable", route_detail, int((time.monotonic() - started) * 1000))

    try:
        error_indication, error_status, error_index, var_binds = await snmp_get(host, port, timeout, retries, credential)
    except Exception as error:  # noqa: BLE001 - 诊断脚本需逐目标汇总 SDK/Socket 错误
        status, detail = _classify_indication(error, credential=credential)
        return ProbeResult(host, port, status, detail, int((time.monotonic() - started) * 1000))

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if error_indication:
        status, detail = _classify_indication(error_indication, credential=credential)
        return ProbeResult(host, port, status, detail, elapsed_ms)
    if error_status:
        status_text = _safe_text(error_status)
        return ProbeResult(host, port, "protocol_error", f"SNMP 协议错误: {status_text} at {error_index}", elapsed_ms)
    if not var_binds:
        return ProbeResult(host, port, "empty_response", "收到空 SNMP 响应", elapsed_ms)
    return ProbeResult(host, port, "success", "SNMP GET sysName.0 成功", elapsed_ms, _safe_text(var_binds[0][1]))


async def run_probes(args: argparse.Namespace, targets: list[str], credential: dict) -> list[ProbeResult]:
    semaphore = asyncio.Semaphore(args.concurrency)

    async def bounded_probe(host: str) -> ProbeResult:
        async with semaphore:
            return await probe_host(
                host,
                port=args.port,
                timeout=args.timeout,
                retries=args.retries,
                credential=credential,
            )

    return list(await asyncio.gather(*(bounded_probe(host) for host in targets)))


def _print_results(results: list[ProbeResult], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps([asdict(result) | {"success": result.success} for result in results], ensure_ascii=False, indent=2))
        return

    for result in results:
        marker = "PASS" if result.success else "FAIL"
        sys_name = f" sysName={result.sys_name!r}" if result.sys_name else ""
        print(f"{marker:<4} {result.host}:{result.port} {result.status} {result.elapsed_ms}ms{sys_name} - {result.detail}")
    succeeded = sum(result.success for result in results)
    print(f"\n汇总: total={len(results)} success={succeeded} failed={len(results) - succeeded}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按 Stargazer network 插件的 SNMP GET 写法批量测试 IP 段连通性",
        epilog="目标示例: 10.0.0.1、10.0.0.0/24、10.0.0.10-10.0.0.20（可重复或逗号分隔）",
    )
    parser.add_argument("targets", nargs="+", help="IP、CIDR 或起止 IP")
    parser.add_argument("--version", choices=("v2", "v2c", "v3"), default="v2c")
    parser.add_argument("--port", type=int, default=161)
    parser.add_argument("--timeout", type=float, default=5.0, help="单次 SNMP 等待秒数")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--max-hosts", type=int, default=DEFAULT_MAX_HOSTS)
    parser.add_argument("--json", action="store_true", help="输出 JSON")

    parser.add_argument("--community", help="v2c community（更推荐 --community-env）")
    parser.add_argument("--community-env", help="保存 v2c community 的环境变量名")
    parser.add_argument("--username", help="v3 username")
    parser.add_argument("--username-env", help="保存 v3 username 的环境变量名")
    parser.add_argument("--level", choices=("authNoPriv", "authPriv"), default="authNoPriv")
    parser.add_argument("--integrity", choices=("sha", "md5"), default="sha")
    parser.add_argument("--privacy", choices=("aes", "des"), default="aes")
    parser.add_argument("--auth-key", help="v3 auth key（更推荐 --auth-key-env）")
    parser.add_argument("--auth-key-env", help="保存 v3 auth key 的环境变量名")
    parser.add_argument("--priv-key", help="v3 privacy key（更推荐 --priv-key-env）")
    parser.add_argument("--priv-key-env", help="保存 v3 privacy key 的环境变量名")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError("--port 必须在 1..65535")
        if args.timeout <= 0 or args.retries < 0:
            raise ValueError("--timeout 必须大于 0，--retries 不能小于 0")
        if not 1 <= args.concurrency <= MAX_CONCURRENCY:
            raise ValueError(f"--concurrency 必须在 1..{MAX_CONCURRENCY}")
        targets = expand_targets(args.targets, max_hosts=args.max_hosts)
        credential = build_credential(args)
    except ValueError as error:
        parser.error(str(error))

    results = asyncio.run(run_probes(args, targets, credential))
    _print_results(results, as_json=args.json)
    return 0 if all(result.success for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())

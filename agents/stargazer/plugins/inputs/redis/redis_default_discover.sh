#!/usr/bin/env bash
set -u

# Upgraded collector (no new files) with minimal-impact fallback.
# Preferred path: run embedded Python logic (supports sentinel + cluster relation fields).
# Fallback path: keep legacy behavior if python is unavailable.

if command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  PY_BIN="python3"
  if ! command -v "$PY_BIN" >/dev/null 2>&1; then
    PY_BIN="python"
  fi

  exec "$PY_BIN" - "$@" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

BASE_FIELDS = [
    "inst_name",
    "bk_obj_id",
    "ip_addr",
    "port",
    "version",
    "install_path",
    "max_conn",
    "max_mem",
    "database_role",
]

REL_FIELDS = [
    "topo_mode",
    "cluster_uuid",
    "master_group_list",
    "master_group_name",
    "slaves",
    "master",
]

OUTPUT_FIELDS = BASE_FIELDS + REL_FIELDS


def parse_key_values(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def parse_config_get(text: str) -> str:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    return lines[1] if len(lines) >= 2 else ""


def parse_resp_pairs(text: str) -> List[Dict[str, str]]:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    pairs: List[Tuple[str, str]] = []
    for i in range(0, len(lines) - 1, 2):
        pairs.append((lines[i], lines[i + 1]))
    blocks: List[Dict[str, str]] = []
    cur: Dict[str, str] = {}
    for k, v in pairs:
        if k == "name" and cur:
            blocks.append(cur)
            cur = {}
        cur[k] = v
    if cur:
        blocks.append(cur)
    return blocks


def parse_cluster_nodes(text: str) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        node_id, addr, flags, master_id, ping_sent, pong_recv, epoch, link_state = parts[:8]
        slots = parts[8:] if len(parts) > 8 else []
        nodes.append(
            {
                "node_id": node_id,
                "addr": addr,
                "flags": flags,
                "master_id": master_id,
                "ping_sent": ping_sent,
                "pong_recv": pong_recv,
                "config_epoch": epoch,
                "link_state": link_state,
                "slots": slots,
            }
        )
    return nodes


def split_addr(addr: str) -> Tuple[str, str]:
    raw = addr.split("@", 1)[0]
    if ":" in raw:
        host, port = raw.rsplit(":", 1)
        return host, port
    return raw, ""


def probe(host: str, port: int, timeout: float = 0.7) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def discover_ports_from_process() -> List[int]:
    try:
        p = subprocess.run(
            ["ps", "-e", "-o", "pid=,comm=,args="],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return []
    ports: List[int] = []
    for line in p.stdout.splitlines():
        if "redis-server" not in line:
            continue
        for m in re.finditer(r"(?:\*|(?:\d{1,3}\.){3}\d{1,3}):(\d{1,5})", line):
            v = int(m.group(1))
            if 1 <= v <= 65535:
                ports.append(v)
    out: List[int] = []
    seen = set()
    for x in ports:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


@dataclass
class CliResult:
    ok: bool
    out: str
    err: str


class RedisCliRunner:
    def __init__(self) -> None:
        self.cli_bin = os.getenv("REDIS_CLI_BIN", "redis-cli")
        self.timeout = int(os.getenv("REDIS_CLI_TIMEOUT", "6"))

    def run(self, host: str, port: int, *args: str) -> CliResult:
        cmd = [self.cli_bin, "-h", host, "-p", str(port), *args]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, check=False)
            return CliResult(p.returncode == 0, p.stdout.strip(), p.stderr.strip())
        except Exception as e:
            return CliResult(False, "", str(e))


def detect_mode(info_sentinel: Dict[str, str], cluster_info: Dict[str, str], role: str) -> str:
    if int(info_sentinel.get("sentinel_masters", "0") or "0") > 0:
        return "sentinel"
    if cluster_info.get("cluster_state"):
        return "cluster"
    if role in {"master", "slave"}:
        return "replication"
    return "standalone"


def collect_instance(runner: RedisCliRunner, host: str, port: int, local_ip: str) -> Optional[Dict[str, Any]]:
    if not probe(host, port):
        return None
    if not runner.run(host, port, "PING").ok:
        return None

    info_server = parse_key_values(runner.run(host, port, "INFO", "server").out)
    info_repl = parse_key_values(runner.run(host, port, "INFO", "replication").out)
    info_sentinel = parse_key_values(runner.run(host, port, "INFO", "sentinel").out)
    cinfo = runner.run(host, port, "CLUSTER", "INFO")
    cluster_info = parse_key_values(cinfo.out) if cinfo.ok else {}
    role = info_repl.get("role", "")
    mode = detect_mode(info_sentinel, cluster_info, role)

    return {
        "inst_name": f"{local_ip}-redis-{port}",
        "bk_obj_id": "redis",
        "ip_addr": local_ip,
        "port": str(port),
        "version": info_server.get("redis_version", ""),
        "install_path": "",
        "max_conn": parse_config_get(runner.run(host, port, "CONFIG", "GET", "maxclients").out),
        "max_mem": parse_config_get(runner.run(host, port, "CONFIG", "GET", "maxmemory").out),
        "database_role": role,
        "_mode": mode,
        "_run_id": info_server.get("run_id", ""),
        "_target_host": host,
    }


def collect_sentinel(runner: RedisCliRunner, sentinel_instances: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not sentinel_instances:
        return None
    seed = sentinel_instances[0]
    host = seed["_target_host"]
    port = int(seed["port"])
    masters = runner.run(host, port, "SENTINEL", "MASTERS")
    if not masters.ok:
        return None
    monitored = parse_resp_pairs(masters.out)
    replicas_all: List[Dict[str, str]] = []
    set_names: List[str] = []
    for m in monitored:
        g = m.get("name", "")
        if not g:
            continue
        set_names.append(g)
        rs = runner.run(host, port, "SENTINEL", "REPLICAS", g)
        if rs.ok:
            for item in parse_resp_pairs(rs.out):
                item["master_set_name"] = g
                replicas_all.append(item)
    uid_src = "|".join(sorted(set(set_names))) + "#" + "|".join(sorted({x.get("runid", "") for x in replicas_all if x.get("runid")}))
    uid = hashlib.sha1(uid_src.encode("utf-8")).hexdigest() if uid_src else ""
    return {"cluster_uuid": uid, "master_group_list": sorted(set(set_names)), "monitored_masters": monitored, "replicas": replicas_all}


def collect_cluster(runner: RedisCliRunner, cluster_instances: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not cluster_instances:
        return None
    seed = cluster_instances[0]
    host = seed["_target_host"]
    port = int(seed["port"])
    info = runner.run(host, port, "CLUSTER", "INFO")
    nodes_raw = runner.run(host, port, "CLUSTER", "NODES")
    if not info.ok or not nodes_raw.ok:
        return None
    nodes = parse_cluster_nodes(nodes_raw.out)
    masters = [n for n in nodes if "master" in str(n.get("flags", ""))]
    master_ids = [str(m.get("node_id", "")) for m in masters if m.get("node_id")]
    uid_src = "|".join(sorted({str(n.get("node_id", "")) for n in nodes if n.get("node_id")}))
    uid = hashlib.sha1(uid_src.encode("utf-8")).hexdigest() if uid_src else ""
    return {"cluster_uuid": uid, "master_group_list": master_ids, "nodes": nodes}


def apply_relations(instances: List[Dict[str, Any]], sentinel: Optional[Dict[str, Any]], cluster: Optional[Dict[str, Any]) -> None:
    s_groups = (sentinel or {}).get("master_group_list", [])
    s_uuid = (sentinel or {}).get("cluster_uuid", "")
    c_groups = (cluster or {}).get("master_group_list", [])
    c_uuid = (cluster or {}).get("cluster_uuid", "")
    c_nodes = (cluster or {}).get("nodes", [])

    c_node_by_id: Dict[str, Dict[str, Any]] = {str(n.get("node_id", "")): n for n in c_nodes if n.get("node_id")}
    c_by_port: Dict[str, List[Dict[str, Any]]] = {}
    c_slave_set_by_master: Dict[str, List[Dict[str, str]]] = {}
    for n in c_nodes:
        host, p = split_addr(str(n.get("addr", "")))
        n["_host"] = host
        n["_port"] = p
        if p:
            c_by_port.setdefault(p, []).append(n)
        flags = str(n.get("flags", ""))
        nid = str(n.get("node_id", ""))
        if "master" in flags and nid:
            c_slave_set_by_master.setdefault(nid, [])
    for n in c_nodes:
        mid = str(n.get("master_id", ""))
        if mid in c_slave_set_by_master:
            c_slave_set_by_master[mid].append({"ip": str(n.get("_host", "")), "port": str(n.get("_port", "")), "runid": str(n.get("node_id", ""))})

    s_master_by_group: Dict[str, Dict[str, Any]] = {}
    s_slave_set_by_group: Dict[str, List[Dict[str, str]]] = {}
    if sentinel:
        for m in sentinel.get("monitored_masters", []):
            g = str(m.get("name", ""))
            if g:
                s_master_by_group[g] = m
        for g in s_groups:
            s_slave_set_by_group[g] = []
            for r in sentinel.get("replicas", []):
                if str(r.get("master_set_name", "")) != g:
                    continue
                s_slave_set_by_group[g].append({"ip": str(r.get("ip", "")), "port": str(r.get("port", "")), "runid": str(r.get("runid", ""))})

    for inst in instances:
        mode = str(inst.get("_mode", "standalone"))
        role = str(inst.get("database_role", ""))
        port = str(inst.get("port", ""))
        run_id = str(inst.get("_run_id", ""))

        inst["topo_mode"] = mode
        inst["cluster_uuid"] = ""
        inst["master_group_list"] = []
        inst["master_group_name"] = ""
        inst["slaves"] = []
        inst["master"] = {}

        if mode == "sentinel":
            inst["cluster_uuid"] = s_uuid
            # 哨兵模式下不输出 master_group_list / master_group_name，保持为 [] 和 ""
            continue

        if mode == "cluster":
            inst["cluster_uuid"] = c_uuid
            inst["master_group_list"] = c_groups
            candidates = c_by_port.get(port, [])
            node = candidates[0] if len(candidates) == 1 else None
            if not node:
                continue
            nid = str(node.get("node_id", ""))
            flags = str(node.get("flags", ""))
            if "master" in flags:
                inst["master_group_name"] = nid
                inst["slaves"] = c_slave_set_by_master.get(nid, [])
            elif "slave" in flags:
                mid = str(node.get("master_id", ""))
                inst["master_group_name"] = mid
                mnode = c_node_by_id.get(mid, {})
                inst["master"] = {"ip": str(mnode.get("_host", "")), "port": str(mnode.get("_port", "")), "node_id_or_runid": mid}
            continue

        if s_uuid:
            inst["cluster_uuid"] = s_uuid
            inst["master_group_list"] = s_groups
            group = s_groups[0] if len(s_groups) == 1 else ""
            if not group and run_id:
                for g, slaves in s_slave_set_by_group.items():
                    if any(str(x.get("runid", "")) == run_id for x in slaves):
                        group = g
                        break
            if not group and role == "master":
                for g, m in s_master_by_group.items():
                    if str(m.get("runid", "")) == run_id:
                        group = g
                        break
            if not group:
                continue
            inst["master_group_name"] = group
            m = s_master_by_group.get(group, {})
            if role == "master":
                inst["slaves"] = s_slave_set_by_group.get(group, [])
            elif role == "slave":
                inst["master"] = {"ip": str(m.get("ip", "")), "port": str(m.get("port", "")), "node_id_or_runid": str(m.get("runid", ""))}


def sanitize(instances: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for inst in instances:
        row: Dict[str, Any] = {}
        mode = inst.get("topo_mode", "")
        for k in OUTPUT_FIELDS:
            if mode == "sentinel" and k in ("master_group_list", "master_group_name"):
                continue  # 哨兵模式下不输出这两项
            if k == "master_group_list":
                row[k] = inst.get(k, [])
            elif k in {"slaves"}:
                row[k] = inst.get(k, [])
            elif k in {"master"}:
                row[k] = inst.get(k, {})
            else:
                row[k] = inst.get(k, "")
        out.append(row)
    return out


def main() -> int:
    runner = RedisCliRunner()
    local_ip = os.getenv("BK_HOST_INNERIP", "127.0.0.1")
    scan_host = os.getenv("REDIS_TARGET_HOST", "127.0.0.1")
    ports = discover_ports_from_process()
    if not ports:
        return 0
    instances: List[Dict[str, Any]] = []
    for p in ports:
        item = collect_instance(runner, scan_host, p, local_ip)
        if item:
            instances.append(item)
    if not instances:
        return 0
    sentinel = collect_sentinel(runner, [x for x in instances if x.get("_mode") == "sentinel"])
    cluster = collect_cluster(runner, [x for x in instances if x.get("_mode") == "cluster"])
    apply_relations(instances, sentinel, cluster)
    for row in sanitize(instances):
        print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
fi

# -----------------------------
# Legacy fallback (no python)
# -----------------------------
run_cmd() {
    cmd="$1"
    result=$(eval "$cmd" 2>&1)
    echo "$result"
}

_procs() {
    local redis_dict
    redis_dict=()
    local pids
    pids=$(ps -e -o pid,comm 2>/dev/null | grep redis-server | awk '{print $1}')
    for pid in $pids; do
        local cmdline
        cmdline=$(ps -p "$pid" -o args= 2>/dev/null)
        local ipport
        ipport=$(echo "$cmdline" | sed -n 's/.*\([0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}:[0-9]\{1,5\}\).*/\1/p')
        if [ -z "$ipport" ]; then
            ipport=$(echo "$cmdline" | sed -n 's/.*\(\*:[0-9]\{1,5\}\).*/\1/p')
        fi
        if [ -n "$ipport" ]; then
            local redis_ip redis_port redis_cli install_path exe
            redis_ip=$(echo "$ipport" | cut -d: -f1)
            redis_port=$(echo "$ipport" | cut -d: -f2)
            if [ "$redis_ip" = "*" ]; then
                redis_ip="0.0.0.0"
            fi
            if [ -f "/proc/$pid/exe" ]; then
                exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null)
                install_path=$(dirname "$exe" 2>/dev/null | sed 's|/bin$||')
                redis_cli="${install_path}/bin/redis-cli"
            else
                redis_cli="redis-cli"
                install_path=""
            fi
            redis_dict+=("$pid:$redis_ip:$redis_port:$redis_cli:$install_path")
        fi
    done
    echo "${redis_dict[@]}"
}

discover_redis() {
    local procs_output
    procs_output=$(_procs)
    local procs
    read -r -a procs <<< "$procs_output"
    if [ ${#procs[@]} -eq 0 ]; then
        exit 0
    fi
    local bk_host_innerip
    if command -v hostname >/dev/null 2>&1; then
        bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi
    if [ -z "$bk_host_innerip" ]; then
        bk_host_innerip=$(ifconfig 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n1)
    fi
    bk_host_innerip=${bk_host_innerip:-"127.0.0.1"}
    local processed_ports=""
    for proc in "${procs[@]}"; do
        local pid ip port redis_cli install_path version max_clients max_memory role inst_name redis_info
        pid=$(echo "$proc" | cut -d: -f1)
        ip=$(echo "$proc" | cut -d: -f2)
        port=$(echo "$proc" | cut -d: -f3)
        redis_cli=$(echo "$proc" | cut -d: -f4)
        install_path=$(echo "$proc" | cut -d: -f5)
        if echo "$processed_ports" | grep -q "|$port|"; then
            continue
        fi
        processed_ports="$processed_ports|$port|"
        if [ -n "$install_path" ] && [ -d "$install_path" ]; then
            install_path=$(cd "$install_path" 2>/dev/null && pwd)
        fi
        if [ -x "$redis_cli" ]; then
            version=$(run_cmd "$redis_cli -p $port --version" 2>/dev/null | awk '{print $2}')
            max_clients=$(run_cmd "$redis_cli -p $port config get maxclients" 2>/dev/null | grep -A1 "maxclients" | tail -n1)
            max_memory=$(run_cmd "$redis_cli -p $port config get maxmemory" 2>/dev/null | grep -A1 "maxmemory" | tail -n1)
            role=$(run_cmd "$redis_cli -p $port info replication" 2>/dev/null | grep "role:" | awk -F: '{print $2}' | tr -d '\r')
        else
            continue
        fi
        inst_name="${bk_host_innerip}-redis-${port}"
        redis_info=$(printf '{"inst_name":"%s","bk_obj_id":"redis","ip_addr":"%s","port":"%s","version":"%s","install_path":"%s","max_conn":"%s","max_mem":"%s","database_role":"%s"}' \
            "$inst_name" "$bk_host_innerip" "$port" "$version" "$install_path" "$max_clients" "$max_memory" "$role")
        echo "$redis_info"
    done
}

discover_redis
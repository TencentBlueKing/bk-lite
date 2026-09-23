import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from apps.cmdb.models.scan_model import SCAN_MIDDLEWARE_FAMILY, SCAN_MIDDLEWARE_TYPES, ScanFamilyRun, ScanHit, ScanTask

SCAN_JOB_BATCH_SIZE = 8
SCAN_MIDDLEWARE_LISTEN_PORTS = {
    "nginx": (80, 443),
    "tomcat": (8080,),
    "kafka": (9092,),
    "zookeeper": (2181,),
    "rabbitmq": (5672, 15672),
    "consul": (8500,),
    "etcd": (2379,),
}


def is_scan_job_model(model_id: str) -> bool:
    return model_id == "host" or model_id in SCAN_MIDDLEWARE_TYPES


def initial_scan_schedule(task: ScanTask) -> dict:
    families = list(task.families or [])
    return {
        "host_selected": "host" in families,
        "middleware_selected": SCAN_MIDDLEWARE_FAMILY in families or bool(set(families) & set(SCAN_MIDDLEWARE_TYPES)),
        "host_enqueued": False,
        "middleware_enqueued": False,
        "job_queue": [],
        "job_cursor": 0,
        "in_flight_family_run_id": None,
        "batch_deadline_at": None,
    }


def expand_scan_ip_ranges(ip_ranges) -> list[str]:
    hosts = []
    seen = set()
    for item in ip_ranges or []:
        if not isinstance(item, dict):
            continue
        begin = str(item.get("begin") or "").strip()
        end = str(item.get("end") or "").strip()
        if not begin or not end:
            continue
        start = ipaddress.IPv4Address(begin)
        stop = ipaddress.IPv4Address(end)
        if int(stop) < int(start):
            start, stop = stop, start
        for value in range(int(start), int(stop) + 1):
            host = str(ipaddress.IPv4Address(value))
            if host in seen:
                continue
            seen.add(host)
            hosts.append(host)
    return hosts


def chunk_hosts(hosts, size=None) -> list[list[str]]:
    chunk_size = int(size or SCAN_JOB_BATCH_SIZE or 8)
    chunk_size = max(chunk_size, 1)
    items = list(hosts or [])
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def hosts_to_ip_ranges(hosts) -> list[dict]:
    if not hosts:
        return []
    addresses = sorted(ipaddress.IPv4Address(host) for host in hosts)
    ranges = []
    run_start = addresses[0]
    previous = addresses[0]
    for address in addresses[1:]:
        if int(address) == int(previous) + 1:
            previous = address
            continue
        ranges.append({"begin": str(run_start), "end": str(previous)})
        run_start = address
        previous = address
    ranges.append({"begin": str(run_start), "end": str(previous)})
    return ranges


def probe_open_ports(hosts, ports, timeout=0.2, max_workers=64) -> dict[str, list[int]]:
    host_list = [str(host) for host in (hosts or []) if host]
    port_list = [int(port) for port in (ports or []) if int(port) > 0]
    if not host_list or not port_list:
        return {}
    opened = {host: [] for host in host_list}

    def _probe(host, port):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return host, port, True
        except OSError:
            return host, port, False

    workers = max(1, min(int(max_workers or 1), len(host_list) * len(port_list)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_probe, host, port) for host in host_list for port in port_list]
        for future in as_completed(futures):
            host, port, ok = future.result()
            if ok:
                opened[host].append(port)
    return {host: ports_found for host, ports_found in opened.items() if ports_found}


def middleware_listen_ports() -> list[int]:
    ports = set()
    for values in SCAN_MIDDLEWARE_LISTEN_PORTS.values():
        ports.update(values)
    return sorted(ports)


def middleware_hosts_by_type(hosts, open_ports) -> dict[str, list[str]]:
    host_list = list(hosts or [])
    types = sorted(SCAN_MIDDLEWARE_TYPES)
    if not open_ports:
        return {model_id: list(host_list) for model_id in types if host_list}
    matched = {}
    for model_id in types:
        wanted = set(SCAN_MIDDLEWARE_LISTEN_PORTS.get(model_id) or ())
        found = [host for host in host_list if wanted.intersection(open_ports.get(host) or [])]
        if found:
            matched[model_id] = found
    return matched


def snmp_success_hosts(execution) -> set[str]:
    return set(
        ScanHit.objects.filter(
            execution=execution,
            family_run__model_id="network",
            status=ScanHit.STATUS_SUCCESS,
        ).values_list("host", flat=True)
    )


def host_success_hosts(execution) -> set[str]:
    return set(
        ScanHit.objects.filter(
            execution=execution,
            family_run__model_id="host",
            status=ScanHit.STATUS_SUCCESS,
        ).values_list("host", flat=True)
    )


def append_job_batches(schedule, model_id, hosts) -> int:
    queue = list(schedule.get("job_queue") or [])
    existing = [item.get("batch_index") or 0 for item in queue if item.get("model_id") == model_id]
    next_index = max(existing, default=-1) + 1
    added = 0
    for chunk in chunk_hosts(hosts):
        queue.append(
            {
                "model_id": str(model_id),
                "ip_ranges": hosts_to_ip_ranges(chunk),
                "batch_index": next_index,
            }
        )
        next_index += 1
        added += 1
    schedule["job_queue"] = queue
    return added


def family_run_finished(family_run: ScanFamilyRun) -> bool:
    if family_run.admit_status == ScanFamilyRun.ADMIT_FAILED:
        return True
    if int(family_run.target_count or 0) <= 0:
        return True
    return int(family_run.received_count or 0) >= int(family_run.target_count or 0)

import asyncio
import time

import pytest
from core.collection.enums import WorkloadClass
from core.collection.scheduler import CollectionScheduler
from core.scan.events import MemoryScanPublisher
from core.scan.orchestrator import ScanDiscoverRequest, ScanOrchestrator
from core.scan.process_match import match_process_fingerprints


def _scheduler():
    return CollectionScheduler(
        max_in_flight=160,
        workload_weights={
            WorkloadClass.CONFIGURATION: 80,
            WorkloadClass.MONITORING: 20,
            WorkloadClass.NETWORK_TOPOLOGY: 20,
            WorkloadClass.SCAN: 40,
        },
        capacity_group_limits={"remote_job": 20, "scan": 40, "scan_job": 8, "default": 160},
    )


@pytest.mark.asyncio
async def test_scan_is_accepted_when_configuration_slots_are_full():
    scheduler = _scheduler()
    config_release = asyncio.Event()

    async def config_handle(item):
        await config_release.wait()
        return item

    scan_started = []

    async def scan_handle(item):
        scan_started.append(item)
        return item

    config_task = asyncio.create_task(
        scheduler.execute("cfg", range(80), config_handle, workload=WorkloadClass.CONFIGURATION, capacity_group="default")
    )
    deadline = time.monotonic() + 2
    while scheduler.active_by_workload[WorkloadClass.CONFIGURATION] < 80 and time.monotonic() < deadline:
        await asyncio.sleep(0)
    assert scheduler.active_by_workload[WorkloadClass.CONFIGURATION] == 80

    scan_task = asyncio.create_task(scheduler.execute("scan", range(5), scan_handle, workload=WorkloadClass.SCAN, capacity_group="scan"))
    deadline = time.monotonic() + 2
    while not scan_started and time.monotonic() < deadline:
        await asyncio.sleep(0)

    assert scan_started
    assert scheduler.active_by_workload[WorkloadClass.CONFIGURATION] == 80
    assert scheduler.active_by_capacity_group.get("remote_job", 0) == 0

    config_release.set()
    await asyncio.gather(config_task, scan_task)
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_configuration_is_accepted_when_scan_slots_are_full():
    scheduler = _scheduler()
    scan_release = asyncio.Event()

    async def scan_handle(item):
        await scan_release.wait()
        return item

    config_started = []

    async def config_handle(item):
        config_started.append(item)
        return item

    scan_task = asyncio.create_task(scheduler.execute("scan", range(40), scan_handle, workload=WorkloadClass.SCAN, capacity_group="scan"))
    deadline = time.monotonic() + 2
    while scheduler.active_by_workload[WorkloadClass.SCAN] < 40 and time.monotonic() < deadline:
        await asyncio.sleep(0)
    assert scheduler.active_by_workload[WorkloadClass.SCAN] == 40

    config_task = asyncio.create_task(
        scheduler.execute("cfg", range(5), config_handle, workload=WorkloadClass.CONFIGURATION, capacity_group="default")
    )
    deadline = time.monotonic() + 2
    while not config_started and time.monotonic() < deadline:
        await asyncio.sleep(0)

    assert config_started
    scan_release.set()
    await asyncio.gather(scan_task, config_task)
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_port_stage_emits_success_and_process_upgrades_without_ssh_skips_process():
    scheduler = _scheduler()
    publisher = MemoryScanPublisher()
    open_ports = {("10.0.1.8", 3306)}

    async def probe(host, port, timeout=1.0):
        del timeout
        return (host, port) in open_ports

    orchestrator = ScanOrchestrator(scheduler, publisher, probe=probe)
    request = ScanDiscoverRequest(
        execution_id=9,
        ip_ranges=[{"begin": "10.0.1.8", "end": "10.0.1.8"}],
        port_fingerprints=[{"port": 3306, "target_type": "mysql"}],
        process_fingerprints=[{"target_type": "mysql", "linux_process": r"mysqld|mariadbd"}],
    )
    await orchestrator.run(request)
    assert [event["stage"] for event in publisher.events] == ["port", "done"]
    assert publisher.events[0]["target_type"] == "mysql"
    assert publisher.events[0]["status"] == "success"
    assert publisher.events[-1]["collect_task_id"] == 9
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_process_stage_lists_once_and_emits_upgrade():
    scheduler = _scheduler()
    publisher = MemoryScanPublisher()
    listed = []

    async def probe(host, port, timeout=1.0):
        del host, port, timeout
        return True

    async def list_processes(host):
        listed.append(host)
        return ["/usr/sbin/mysqld --datadir=/var/lib/mysql"]

    orchestrator = ScanOrchestrator(scheduler, publisher, probe=probe, list_processes=list_processes)
    request = ScanDiscoverRequest(
        execution_id=11,
        ip_ranges=[{"begin": "10.0.1.8", "end": "10.0.1.8"}],
        port_fingerprints=[{"port": 3306, "target_type": "mysql"}],
        process_fingerprints=[{"target_type": "mysql", "linux_process": r"mysqld|mariadbd"}],
        host_login={"credential_id": "agent"},
    )
    await orchestrator.run(request)
    assert listed == ["10.0.1.8"]
    stages = [event["stage"] for event in publisher.events]
    assert stages == ["port", "process", "done"]
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_collect_stage_only_hits_with_credentials():
    scheduler = _scheduler()
    publisher = MemoryScanPublisher()
    collected = []

    async def probe(host, port, timeout=1.0):
        del timeout
        return port == 3306

    async def collect_plugin(hit, pool):
        collected.append((hit["target_type"], hit["host"], hit["port"], len(pool)))
        return {"success": True, "snapshot": {"version": "8.0"}}

    orchestrator = ScanOrchestrator(scheduler, publisher, probe=probe, collect_plugin=collect_plugin)
    request = ScanDiscoverRequest(
        execution_id=12,
        ip_ranges=[{"begin": "10.0.1.8", "end": "10.0.1.8"}],
        port_fingerprints=[
            {"port": 3306, "target_type": "mysql"},
            {"port": 80, "target_type": "nginx"},
        ],
        collect_credentials={"mysql": [{"credential_id": "cred-db", "username": "u"}]},
    )
    await orchestrator.run(request)
    assert collected == [("mysql", "10.0.1.8", 3306, 1)]
    stages = [event["stage"] for event in publisher.events]
    assert "collect" in stages
    assert stages[-1] == "done"
    assert all(event.get("target_type") != "nginx" or event.get("stage") != "collect" for event in publisher.events)
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_collect_failure_keeps_port_event_and_emits_failed():
    scheduler = _scheduler()
    publisher = MemoryScanPublisher()

    async def probe(host, port, timeout=1.0):
        del host, timeout
        return port == 3306

    async def collect_plugin(hit, pool):
        del hit, pool
        return {"success": False, "error_code": "auth_failed"}

    orchestrator = ScanOrchestrator(scheduler, publisher, probe=probe, collect_plugin=collect_plugin)
    request = ScanDiscoverRequest(
        execution_id=13,
        ip_ranges=[{"begin": "10.0.1.8", "end": "10.0.1.8"}],
        port_fingerprints=[{"port": 3306, "target_type": "mysql"}],
        collect_credentials={"mysql": [{"credential_id": "cred-db"}]},
    )
    await orchestrator.run(request)
    stages = [(event["stage"], event["status"]) for event in publisher.events]
    assert ("port", "success") in stages
    assert ("collect", "failed") in stages
    assert stages[-1] == ("done", "success")
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_process_stage_skips_snmp_hosts_and_hosts_without_port_hits():
    scheduler = _scheduler()
    publisher = MemoryScanPublisher()
    listed = []
    open_ports = {("10.0.1.8", 3306), ("10.0.1.9", 3306)}

    async def probe(host, port, timeout=1.0):
        del timeout
        return (host, port) in open_ports

    async def list_processes(host):
        listed.append(host)
        return ["/usr/sbin/mysqld"]

    orchestrator = ScanOrchestrator(scheduler, publisher, probe=probe, list_processes=list_processes)
    request = ScanDiscoverRequest(
        execution_id=21,
        ip_ranges=[{"begin": "10.0.1.8", "end": "10.0.1.10"}],
        port_fingerprints=[{"port": 3306, "target_type": "mysql"}],
        process_fingerprints=[{"target_type": "mysql", "linux_process": r"mysqld"}],
        host_login={"pool": [{"credential_id": "agent"}]},
        skip_hosts=["10.0.1.9"],
    )
    await orchestrator.run(request)
    assert listed == ["10.0.1.8"]
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_host_collect_runs_on_port_hit_hosts():
    scheduler = _scheduler()
    publisher = MemoryScanPublisher()
    collected = []

    async def probe(host, port, timeout=1.0):
        del timeout
        return (host, port) == ("10.0.1.8", 3306)

    async def collect_plugin(hit, pool):
        collected.append(hit["target_type"])
        return {"success": True, "snapshot": {"hostname": "box"}}

    orchestrator = ScanOrchestrator(scheduler, publisher, probe=probe, collect_plugin=collect_plugin)
    request = ScanDiscoverRequest(
        execution_id=22,
        ip_ranges=[{"begin": "10.0.1.8", "end": "10.0.1.9"}],
        port_fingerprints=[{"port": 3306, "target_type": "mysql"}],
        collect_credentials={"host": [{"credential_id": "cred-ssh"}]},
    )
    await orchestrator.run(request)
    assert collected == ["host"]
    assert publisher.events[-1]["stage"] == "done"
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_closed_ports_still_publish_done():
    scheduler = _scheduler()
    publisher = MemoryScanPublisher()

    async def probe(host, port, timeout=1.0):
        del host, port, timeout
        return False

    orchestrator = ScanOrchestrator(scheduler, publisher, probe=probe)
    request = ScanDiscoverRequest(
        execution_id=31,
        ip_ranges=[{"begin": "10.0.1.8", "end": "10.0.1.10"}],
        port_fingerprints=[{"port": 3306, "target_type": "mysql"}],
    )
    await orchestrator.run(request)
    assert [event["stage"] for event in publisher.events] == ["done"]
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_publish_done_after_stage_failure():
    scheduler = _scheduler()
    publisher = MemoryScanPublisher()

    async def probe(host, port, timeout=1.0):
        del host, port, timeout
        raise RuntimeError("probe boom")

    orchestrator = ScanOrchestrator(scheduler, publisher, probe=probe)
    request = ScanDiscoverRequest(
        execution_id=32,
        ip_ranges=[{"begin": "10.0.1.8", "end": "10.0.1.8"}],
        port_fingerprints=[{"port": 3306, "target_type": "mysql"}],
    )
    with pytest.raises(RuntimeError, match="probe boom"):
        await orchestrator.run(request)
    assert publisher.events[-1]["stage"] == "done"
    assert publisher.events[-1]["status"] == "failed"
    await scheduler.shutdown()


def test_process_match_uses_regex():
    hits = match_process_fingerprints(
        ["java kafka.Kafka /opt/kafka"],
        [{"target_type": "kafka", "linux_process": r"kafka\.Kafka"}],
    )
    assert hits == [{"target_type": "kafka", "linux_process": r"kafka\.Kafka"}]

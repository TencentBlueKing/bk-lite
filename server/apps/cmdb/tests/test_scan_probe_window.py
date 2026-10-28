import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from apps.cmdb.services import scan_schedule_service
from apps.cmdb.services.scan_schedule_service import middleware_listen_ports, probe_open_ports


class _OpenSocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_probe_open_ports_bounds_unfinished_submissions_to_workers(monkeypatch):
    hosts = [f"10.0.0.{index}" for index in range(1, 9)]
    ports = middleware_listen_ports()
    max_workers = 4
    open_pairs = {("10.0.0.2", 80), ("10.0.0.2", 443), ("10.0.0.5", 9092)}
    release = threading.Event()
    started = threading.Condition()
    state = {"entered": 0, "seen": set(), "timeouts": []}
    recorder = {}

    def fake_connect(address, timeout=None):
        host, port = str(address[0]), int(address[1])
        with started:
            state["entered"] += 1
            state["seen"].add((host, port))
            state["timeouts"].append(timeout)
            started.notify_all()
        if not release.wait(5):
            raise TimeoutError("socket probe was not released")
        if (host, port) in open_pairs:
            return _OpenSocket()
        raise OSError("closed")

    class RecordingExecutor(ThreadPoolExecutor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._count_lock = threading.Lock()
            self.outstanding = 0
            self.peak = 0
            recorder["executor"] = self

        def submit(self, fn, *args, **kwargs):
            def wrapped(*inner_args, **inner_kwargs):
                try:
                    return fn(*inner_args, **inner_kwargs)
                finally:
                    with self._count_lock:
                        self.outstanding -= 1

            with self._count_lock:
                self.outstanding += 1
                self.peak = max(self.peak, self.outstanding)
            return super().submit(wrapped, *args, **kwargs)

    monkeypatch.setattr(scan_schedule_service.socket, "create_connection", fake_connect)
    monkeypatch.setattr(scan_schedule_service, "ThreadPoolExecutor", RecordingExecutor)

    outcome = {}

    def _run():
        try:
            outcome["result"] = probe_open_ports(hosts, ports, max_workers=max_workers)
        except Exception as exc:
            outcome["error"] = exc

    worker = threading.Thread(target=_run, name="probe-open-ports")
    worker.start()
    try:
        deadline = time.monotonic() + 3
        with started:
            while state["entered"] < max_workers and time.monotonic() < deadline:
                started.wait(timeout=max(0.0, deadline - time.monotonic()))
            entered = state["entered"]
        assert entered >= max_workers
        time.sleep(0.2)
    finally:
        release.set()
        worker.join(5)

    combinations = len(hosts) * len(ports)
    peak = recorder["executor"].peak
    assert not worker.is_alive()
    assert "error" not in outcome, outcome.get("error")
    assert peak <= max_workers, (
        f"unfinished submissions peaked at {peak}, workers={max_workers}, combinations={combinations}"
    )
    assert state["seen"] == {(host, port) for host in hosts for port in ports}
    assert set(state["timeouts"]) == {0.2}
    assert {host: sorted(found) for host, found in outcome["result"].items()} == {
        "10.0.0.2": [80, 443],
        "10.0.0.5": [9092],
    }


def test_probe_open_ports_empty_inputs_stay_empty():
    assert probe_open_ports([], [80, 443]) == {}
    assert probe_open_ports(["10.0.0.1"], []) == {}
    assert probe_open_ports(None, None) == {}


def test_probe_open_ports_raises_unexpected_probe_errors(monkeypatch):
    def fake_connect(address, timeout=None):
        raise RuntimeError("probe failed")

    monkeypatch.setattr(scan_schedule_service.socket, "create_connection", fake_connect)

    with pytest.raises(RuntimeError, match="probe failed"):
        probe_open_ports(["10.0.0.8"], [9092], max_workers=2)

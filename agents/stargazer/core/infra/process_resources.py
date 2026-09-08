"""进程与容器资源采样；采样失败时返回 -1，不影响采集主链路。"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Callable

_MIB = 1024 * 1024


class ProcessResourceSampler:
    """按采样周期计算进程 CPU，并读取 Linux procfs/cgroup v1 或 v2 资源。"""

    def __init__(
        self,
        *,
        proc_root: str | Path = "/proc",
        cgroup_root: str | Path = "/sys/fs/cgroup",
        monotonic: Callable[[], float] = time.monotonic,
        process_time: Callable[[], float] = time.process_time,
        page_size: int | None = None,
    ) -> None:
        self._proc_root = Path(proc_root)
        self._cgroup_root = Path(cgroup_root)
        self._monotonic = monotonic
        self._process_time = process_time
        self._page_size = page_size or self._detect_page_size()
        self._last_wall_seconds = monotonic()
        self._last_process_cpu_seconds = process_time()
        self._last_throttled_seconds: float | None = None
        self._last_throttled_periods: int | None = None

    def sample(self) -> dict[str, float | int]:
        process_cpu_percent = self._sample_process_cpu_percent()
        cgroup_dir = self._cgroup_v2_directory()
        if cgroup_dir is not None:
            memory_current = self._read_int(cgroup_dir / "memory.current")
            memory_limit = self._read_limit(cgroup_dir / "memory.max")
            cpu_limit_cores = self._read_cpu_limit(cgroup_dir / "cpu.max")
            cpu_stat = self._read_key_values(cgroup_dir / "cpu.stat")
            throttled_seconds = self._microseconds(cpu_stat.get("throttled_usec"))
        else:
            memory_dir, cpu_dir = self._cgroup_v1_directories()
            memory_current = self._read_int(memory_dir / "memory.usage_in_bytes")
            memory_limit = self._read_v1_memory_limit(memory_dir / "memory.limit_in_bytes")
            cpu_limit_cores = self._read_v1_cpu_limit(cpu_dir)
            cpu_stat = self._read_key_values(cpu_dir / "cpu.stat")
            throttled_seconds = self._nanoseconds(cpu_stat.get("throttled_time"))
        throttled_periods = cpu_stat.get("nr_throttled", -1)

        snapshot: dict[str, float | int] = {
            "process_cpu_percent": process_cpu_percent,
            "process_cpu_quota_utilization_percent": self._quota_utilization(
                process_cpu_percent,
                cpu_limit_cores,
            ),
            "process_rss_mb": self._process_rss_mb(),
            "process_threads": self._process_threads(),
            "process_open_fds": self._open_file_descriptors(),
            "cgroup_memory_current_mb": self._bytes_to_mib(memory_current),
            "cgroup_memory_limit_mb": self._bytes_to_mib(memory_limit),
            "cgroup_memory_utilization_percent": self._percentage(memory_current, memory_limit),
            "cgroup_cpu_limit_cores": cpu_limit_cores,
            "cgroup_cpu_throttled_seconds_total": throttled_seconds,
            "cgroup_cpu_throttled_seconds_delta": self._throttled_seconds_delta(throttled_seconds),
            "cgroup_cpu_throttled_periods_total": throttled_periods,
            "cgroup_cpu_throttled_periods_delta": self._throttled_periods_delta(throttled_periods),
        }
        return snapshot

    def _sample_process_cpu_percent(self) -> float:
        wall_seconds = self._monotonic()
        process_cpu_seconds = self._process_time()
        wall_delta = wall_seconds - self._last_wall_seconds
        cpu_delta = process_cpu_seconds - self._last_process_cpu_seconds
        self._last_wall_seconds = wall_seconds
        self._last_process_cpu_seconds = process_cpu_seconds
        if wall_delta <= 0 or cpu_delta < 0:
            return -1.0
        # reporter 启动后会立即采样；极短区间只反映初始化抖动，不用于容量判断。
        if wall_delta < 0.1:
            return 0.0
        return round(cpu_delta / wall_delta * 100, 2)

    def _cgroup_v2_directory(self) -> Path | None:
        if (self._cgroup_root / "cgroup.controllers").exists():
            return self._cgroup_root
        try:
            lines = (self._proc_root / "self/cgroup").read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return None
        for line in lines:
            parts = line.split(":", 2)
            if len(parts) == 3 and parts[0] == "0" and parts[1] == "":
                candidate = self._cgroup_root / parts[2].lstrip("/")
                if candidate.exists():
                    return candidate
        return None

    def _cgroup_v1_directories(self) -> tuple[Path, Path]:
        memory_dir = self._cgroup_root / "memory"
        cpu_dir = self._cgroup_root / "cpu,cpuacct"
        try:
            lines = (self._proc_root / "self/cgroup").read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return memory_dir, cpu_dir
        for line in lines:
            parts = line.split(":", 2)
            if len(parts) != 3 or not parts[1]:
                continue
            controller_group, relative = parts[1], parts[2].lstrip("/")
            controllers = controller_group.split(",")
            candidates = (controller_group, *controllers)
            if "memory" in controllers:
                memory_dir = self._first_existing_cgroup_path(candidates, relative)
            if "cpu" in controllers:
                cpu_dir = self._first_existing_cgroup_path(candidates, relative)
        return memory_dir, cpu_dir

    def _first_existing_cgroup_path(self, controller_names: tuple[str, ...], relative: str) -> Path:
        candidates = tuple(self._cgroup_root / name / relative for name in controller_names)
        return next((path for path in candidates if path.exists()), candidates[0])

    def _process_rss_mb(self) -> float:
        try:
            fields = (self._proc_root / "self/statm").read_text(encoding="utf-8").split()
            return round(int(fields[1]) * self._page_size / _MIB, 2)
        except (OSError, UnicodeError, ValueError, IndexError):
            return -1.0

    def _process_threads(self) -> int:
        try:
            for line in (self._proc_root / "self/status").read_text(encoding="utf-8").splitlines():
                if line.startswith("Threads:"):
                    return int(line.split(":", 1)[1].strip())
        except (OSError, UnicodeError, ValueError):
            pass
        return threading.active_count()

    def _open_file_descriptors(self) -> int:
        try:
            return len(list((self._proc_root / "self/fd").iterdir()))
        except OSError:
            return -1

    def _read_int(self, path: Path) -> int:
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeError, ValueError):
            return -1

    def _read_limit(self, path: Path) -> int:
        try:
            raw = path.read_text(encoding="utf-8").strip()
            return -1 if raw == "max" else int(raw)
        except (OSError, UnicodeError, ValueError):
            return -1

    def _read_v1_memory_limit(self, path: Path) -> int:
        value = self._read_int(path)
        return -1 if value >= 1 << 60 else value

    def _read_v1_cpu_limit(self, directory: Path) -> float:
        quota = self._read_int(directory / "cpu.cfs_quota_us")
        period = self._read_int(directory / "cpu.cfs_period_us")
        if quota < 0 or period <= 0:
            return -1.0
        return round(quota / period, 2)

    def _read_cpu_limit(self, path: Path) -> float:
        try:
            quota, period = path.read_text(encoding="utf-8").split()[:2]
            if quota == "max":
                return -1.0
            return round(int(quota) / int(period), 2)
        except (OSError, UnicodeError, ValueError, IndexError, ZeroDivisionError):
            return -1.0

    def _read_key_values(self, path: Path) -> dict[str, int]:
        result: dict[str, int] = {}
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                key, value = line.split(maxsplit=1)
                result[key] = int(value)
        except (OSError, UnicodeError, ValueError):
            return {}
        return result

    def _throttled_seconds_delta(self, total: float) -> float:
        previous = self._last_throttled_seconds
        self._last_throttled_seconds = total if total >= 0 else previous
        if total < 0 or previous is None:
            return 0.0 if total >= 0 else -1.0
        return round(max(0.0, total - previous), 3)

    def _throttled_periods_delta(self, total: int) -> int:
        previous = self._last_throttled_periods
        self._last_throttled_periods = total if total >= 0 else previous
        if total < 0 or previous is None:
            return 0 if total >= 0 else -1
        return max(0, total - previous)

    @staticmethod
    def _detect_page_size() -> int:
        try:
            return int(os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError):
            return 4096

    @staticmethod
    def _microseconds(value: int | None) -> float:
        return -1.0 if value is None else round(value / 1_000_000, 3)

    @staticmethod
    def _nanoseconds(value: int | None) -> float:
        return -1.0 if value is None else round(value / 1_000_000_000, 3)

    @staticmethod
    def _bytes_to_mib(value: int) -> float:
        return -1.0 if value < 0 else round(value / _MIB, 2)

    @staticmethod
    def _percentage(used: int, limit: int) -> float:
        if used < 0 or limit <= 0:
            return -1.0
        return round(used / limit * 100, 2)

    @staticmethod
    def _quota_utilization(process_cpu_percent: float, cpu_limit_cores: float) -> float:
        if process_cpu_percent < 0 or cpu_limit_cores <= 0:
            return -1.0
        return round(process_cpu_percent / cpu_limit_cores, 2)

from core.infra.process_resources import ProcessResourceSampler


def test_process_resource_sampler_reads_proc_and_cgroup_v2(tmp_path):
    proc_root = tmp_path / "proc"
    cgroup_root = tmp_path / "cgroup"
    fd_root = proc_root / "self/fd"
    fd_root.mkdir(parents=True)
    cgroup_root.mkdir()
    for name in ("1", "2", "3"):
        (fd_root / name).touch()
    (proc_root / "self/statm").write_text("1000 128 0 0 0 0 0\n", encoding="utf-8")
    (proc_root / "self/status").write_text("Name:\ttest\nThreads:\t7\n", encoding="utf-8")
    (cgroup_root / "cgroup.controllers").write_text("cpu memory\n", encoding="utf-8")
    (cgroup_root / "memory.current").write_text("536870912\n", encoding="utf-8")
    (cgroup_root / "memory.max").write_text("1073741824\n", encoding="utf-8")
    (cgroup_root / "cpu.max").write_text("200000 100000\n", encoding="utf-8")
    (cgroup_root / "cpu.stat").write_text(
        "usage_usec 12000000\nnr_periods 100\nnr_throttled 40\nthrottled_usec 2500000\n",
        encoding="utf-8",
    )
    wall_times = iter((100.0, 102.0))
    cpu_times = iter((10.0, 11.0))
    sampler = ProcessResourceSampler(
        proc_root=proc_root,
        cgroup_root=cgroup_root,
        monotonic=lambda: next(wall_times),
        process_time=lambda: next(cpu_times),
        page_size=4096,
    )

    snapshot = sampler.sample()

    assert snapshot["process_cpu_percent"] == 50.0
    assert snapshot["process_cpu_quota_utilization_percent"] == 25.0
    assert snapshot["process_rss_mb"] == 0.5
    assert snapshot["process_threads"] == 7
    assert snapshot["process_open_fds"] == 3
    assert snapshot["cgroup_memory_current_mb"] == 512.0
    assert snapshot["cgroup_memory_limit_mb"] == 1024.0
    assert snapshot["cgroup_memory_utilization_percent"] == 50.0
    assert snapshot["cgroup_cpu_limit_cores"] == 2.0
    assert snapshot["cgroup_cpu_throttled_seconds_total"] == 2.5
    assert snapshot["cgroup_cpu_throttled_seconds_delta"] == 0.0
    assert snapshot["cgroup_cpu_throttled_periods_total"] == 40
    assert snapshot["cgroup_cpu_throttled_periods_delta"] == 0


def test_process_resource_sampler_fails_open_when_linux_files_are_unavailable(tmp_path):
    wall_times = iter((100.0, 101.0))
    cpu_times = iter((10.0, 10.5))
    sampler = ProcessResourceSampler(
        proc_root=tmp_path / "missing-proc",
        cgroup_root=tmp_path / "missing-cgroup",
        monotonic=lambda: next(wall_times),
        process_time=lambda: next(cpu_times),
    )

    snapshot = sampler.sample()

    assert snapshot["process_cpu_percent"] == 50.0
    assert snapshot["process_rss_mb"] == -1.0
    assert snapshot["process_open_fds"] == -1
    assert snapshot["cgroup_memory_current_mb"] == -1.0
    assert snapshot["cgroup_cpu_limit_cores"] == -1.0
    assert snapshot["cgroup_cpu_throttled_seconds_delta"] == -1.0


def test_process_resource_sampler_ignores_immediate_startup_cpu_spike(tmp_path):
    wall_times = iter((100.0, 100.01))
    cpu_times = iter((10.0, 10.01))
    sampler = ProcessResourceSampler(
        proc_root=tmp_path / "missing-proc",
        cgroup_root=tmp_path / "missing-cgroup",
        monotonic=lambda: next(wall_times),
        process_time=lambda: next(cpu_times),
    )

    assert sampler.sample()["process_cpu_percent"] == 0.0

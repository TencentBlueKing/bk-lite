//go:build linux

package main

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"unsafe"
)

const rlimitNproc = 6

func applyResourceLimits(pid int, memBytes uint64) {
	applyCgroupV2(pid, memBytes)
	applyPrlimit(pid, memBytes)
}

func applyPrlimit(pid int, memBytes uint64) {
	nproc := syscall.Rlimit{Cur: 32, Max: 32}
	_ = prlimit(pid, rlimitNproc, &nproc)
	fsize := syscall.Rlimit{Cur: 10 << 20, Max: 10 << 20}
	_ = prlimit(pid, syscall.RLIMIT_FSIZE, &fsize)
	nofile := syscall.Rlimit{Cur: 256, Max: 256}
	_ = prlimit(pid, syscall.RLIMIT_NOFILE, &nofile)
}

func prlimit(pid, resource int, newLimit *syscall.Rlimit) error {
	_, _, errno := syscall.RawSyscall6(
		syscall.SYS_PRLIMIT64,
		uintptr(pid),
		uintptr(resource),
		uintptr(unsafe.Pointer(newLimit)),
		0,
		0,
		0,
	)
	if errno != 0 {
		return errno
	}
	return nil
}

func applyCgroupV2(pid int, memBytes uint64) {
	base := currentCgroupDir()
	if base == "" {
		return
	}
	dir := filepath.Join(base, "bklite-script", strconv.Itoa(pid))
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return
	}
	if memBytes > 0 {
		_ = os.WriteFile(filepath.Join(dir, "memory.max"), []byte(strconv.FormatUint(memBytes, 10)), 0o644)
	}
	_ = os.WriteFile(filepath.Join(dir, "cpu.max"), []byte("10000 100000"), 0o644)
	_ = os.WriteFile(filepath.Join(dir, "pids.max"), []byte("32"), 0o644)
	_ = os.WriteFile(filepath.Join(dir, "cgroup.procs"), []byte(strconv.Itoa(pid)+"\n"), 0o644)
}

func currentCgroupDir() string {
	if _, err := os.Stat("/sys/fs/cgroup/cgroup.controllers"); err != nil {
		return ""
	}
	data, err := os.ReadFile("/proc/self/cgroup")
	if err != nil {
		return ""
	}
	rel := ""
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "0::") {
			rel = strings.TrimPrefix(line, "0::")
			break
		}
	}
	if rel == "" {
		return "/sys/fs/cgroup"
	}
	return filepath.Join("/sys/fs/cgroup", strings.TrimPrefix(rel, "/"))
}

//go:build windows

package main

import (
	"os"
	"os/exec"
	"strconv"
	"syscall"
)

func lookupUser(name string) (uint32, uint32, bool, error) {
	return 0, 0, false, nil
}

func chownToUser(path, name string) error {
	return nil
}

func shouldDropPrivileges(userName string) bool {
	return false
}

func sysProcAttrFor(uid, gid uint32, drop bool) *syscall.SysProcAttr {
	return &syscall.SysProcAttr{
		HideWindow:    true,
		CreationFlags: 0x00000200,
	}
}

func killProcessGroup(pid int) {
	_ = exec.Command("taskkill", "/F", "/T", "/PID", strconv.Itoa(pid)).Run()
	if proc, err := os.FindProcess(pid); err == nil {
		_ = proc.Kill()
	}
}

//go:build windows

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"golang.org/x/sys/windows"
)

func restrictSensitiveFile(path string) error {
	output, err := exec.Command(
		"icacls.exe",
		path,
		"/inheritance:r",
		"/grant:r",
		"*S-1-5-18:F",
		"*S-1-5-32-544:F",
	).CombinedOutput()
	if err != nil {
		return fmt.Errorf("restrict file ACL: %s", string(output))
	}
	return nil
}

func acquireInstallLock(installDir string) (func(), error) {
	lockPath := installDir + ".bklite-install.lock"
	if err := os.MkdirAll(filepath.Dir(lockPath), 0755); err != nil {
		return nil, err
	}
	file, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	overlapped := new(windows.Overlapped)
	if err := windows.LockFileEx(
		windows.Handle(file.Fd()),
		windows.LOCKFILE_EXCLUSIVE_LOCK|windows.LOCKFILE_FAIL_IMMEDIATELY,
		0,
		1,
		0,
		overlapped,
	); err != nil {
		_ = file.Close()
		return nil, fmt.Errorf("another installation is already running: %w", err)
	}
	return func() {
		_ = windows.UnlockFileEx(windows.Handle(file.Fd()), 0, 1, 0, overlapped)
		_ = file.Close()
	}, nil
}

//go:build !windows

package main

import (
	"fmt"
	"os"
	"path/filepath"

	"golang.org/x/sys/unix"
)

func restrictSensitiveFile(path string) error {
	return os.Chmod(path, 0600)
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
	if err := unix.Flock(int(file.Fd()), unix.LOCK_EX|unix.LOCK_NB); err != nil {
		_ = file.Close()
		return nil, fmt.Errorf("another installation is already running: %w", err)
	}
	return func() {
		_ = unix.Flock(int(file.Fd()), unix.LOCK_UN)
		_ = file.Close()
	}, nil
}

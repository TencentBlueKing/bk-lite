package main

import (
	"os"
	"path/filepath"
)

func acquireLock(cfg config) (*os.File, error) {
	dir := filepath.Dir(lockPath(cfg))
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	file, err := os.OpenFile(lockPath(cfg), os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, err
	}
	if err := lockExclusive(file); err != nil {
		_ = file.Close()
		return nil, err
	}
	return file, nil
}

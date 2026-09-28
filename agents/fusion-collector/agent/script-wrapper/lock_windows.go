//go:build windows

package main

import (
	"os"
	"syscall"
	"unsafe"
)

const (
	lockfileExclusiveLock    = 0x0002
	lockfileFailImmediately  = 0x0001
)

var (
	modkernel32  = syscall.NewLazyDLL("kernel32.dll")
	procLockFileEx = modkernel32.NewProc("LockFileEx")
)

func lockExclusive(file *os.File) error {
	var overlapped syscall.Overlapped
	r1, _, err := procLockFileEx.Call(
		file.Fd(),
		uintptr(lockfileExclusiveLock|lockfileFailImmediately),
		0,
		1,
		0,
		uintptr(unsafe.Pointer(&overlapped)),
	)
	if r1 == 0 {
		if err != nil {
			return err
		}
		return syscall.EINVAL
	}
	return nil
}

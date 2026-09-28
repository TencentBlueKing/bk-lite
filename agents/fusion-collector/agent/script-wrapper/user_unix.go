//go:build unix

package main

import (
	"os"
	"os/user"
	"strconv"
	"syscall"
)

func lookupUser(name string) (uint32, uint32, bool, error) {
	if name == "" {
		return uint32(os.Geteuid()), uint32(os.Getegid()), os.Geteuid() == 0, nil
	}
	account, err := user.Lookup(name)
	if err != nil {
		return 0, 0, false, err
	}
	uid64, err := strconv.ParseUint(account.Uid, 10, 32)
	if err != nil {
		return 0, 0, false, err
	}
	gid64, err := strconv.ParseUint(account.Gid, 10, 32)
	if err != nil {
		return 0, 0, false, err
	}
	return uint32(uid64), uint32(gid64), uid64 == 0, nil
}

func chownToUser(path, name string) error {
	if name == "" || os.Geteuid() != 0 {
		return nil
	}
	uid, gid, _, err := lookupUser(name)
	if err != nil {
		return err
	}
	return os.Chown(path, int(uid), int(gid))
}

func shouldDropPrivileges(userName string) bool {
	return os.Geteuid() == 0 && userName != ""
}

func sysProcAttrFor(uid, gid uint32, drop bool) *syscall.SysProcAttr {
	attr := &syscall.SysProcAttr{Setpgid: true}
	if drop {
		attr.Credential = &syscall.Credential{Uid: uid, Gid: gid}
	}
	return attr
}

func killProcessGroup(pid int) {
	_ = syscall.Kill(-pid, syscall.SIGKILL)
	_ = syscall.Kill(pid, syscall.SIGKILL)
}

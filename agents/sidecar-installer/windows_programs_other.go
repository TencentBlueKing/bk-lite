//go:build !windows

package main

import (
	"errors"
	"os"
)

func newWindowsProgramsEnv() *windowsProgramsEnv {
	return &windowsProgramsEnv{
		Executable:      os.Executable,
		CopyUninstaller: copyExecutableAsUninstaller,
		IconExists:      installerIconExists,
		Registry:        unavailableProgramRegistry{},
		IsElevated: func() bool {
			return false
		},
		Confirm: func() (bool, error) {
			return false, errors.New("Windows uninstall prompt requires Windows")
		},
		Notify: func(bool, string) error {
			return errors.New("Windows uninstall prompt requires Windows")
		},
		AcquireLock: acquireInstallLock,
		StopAndDeleteService: func() error {
			return errors.New("sidecar service control requires Windows")
		},
		ListRetainedBackups: func() ([]string, error) {
			return nil, errors.New("Windows uninstall paths require Windows")
		},
		RemovePath: removeOwnedWindowsPath,
		StageUninstaller: func(sourcePath string) (string, error) {
			return stageWindowsUninstallCopy(os.TempDir(), sourcePath)
		},
		Launch: func(string, []string, string, bool) (int, error) {
			return 1, errors.New("Windows process launch requires Windows")
		},
		MoveOriginalUninstaller: moveOriginalUninstaller,
		ScheduleDelete: func(string) error {
			return errors.New("reboot deletion requires Windows")
		},
		Stderr: os.Stderr,
	}
}

type unavailableProgramRegistry struct{}

func (unavailableProgramRegistry) Apply([]registryValueOp) error {
	return errors.New("Windows program registry requires Windows")
}

func (unavailableProgramRegistry) Delete() error {
	return errors.New("Windows program registry requires Windows")
}

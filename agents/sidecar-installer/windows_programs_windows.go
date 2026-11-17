//go:build windows

package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

const messageBoxButtonOK int32 = 1

func newWindowsProgramsEnv() *windowsProgramsEnv {
	return &windowsProgramsEnv{
		Executable:           os.Executable,
		CopyUninstaller:      copyExecutableAsUninstaller,
		IconExists:           installerIconExists,
		Registry:             windowsProgramRegistryStore{},
		IsElevated:           currentProcessElevated,
		Confirm:              confirmWindowsUninstall,
		Notify:               notifyWindowsUninstall,
		AcquireLock:          acquireInstallLock,
		StopAndDeleteService: stopAndDeleteSidecarService,
		ListRetainedBackups:  listWindowsRetainedBackupDirs,
		RemovePath:           removeOwnedWindowsPath,
		StageUninstaller: func(sourcePath string) (string, error) {
			return stageWindowsUninstallCopy(os.TempDir(), sourcePath)
		},
		Launch:                  launchWindowsProcess,
		MoveOriginalUninstaller: moveOriginalUninstaller,
		ScheduleDelete:          scheduleDeleteOnReboot,
		Stderr:                  os.Stderr,
	}
}

type windowsProgramRegistryStore struct{}

func (windowsProgramRegistryStore) Apply(ops []registryValueOp) error {
	key, _, err := registry.CreateKey(
		registry.LOCAL_MACHINE,
		windowsUninstallRegistryKey,
		registry.ALL_ACCESS|windowsRegistry32BitView,
	)
	if err != nil {
		return err
	}
	defer key.Close()
	for _, op := range ops {
		var opErr error
		switch op.Kind {
		case registryValueString:
			opErr = key.SetStringValue(op.Name, op.String)
		case registryValueDWord:
			opErr = key.SetDWordValue(op.Name, op.DWord)
		case registryValueDelete:
			opErr = key.DeleteValue(op.Name)
			if registryKeyAbsent(opErr) {
				opErr = nil
			}
		default:
			opErr = fmt.Errorf("unknown registry operation %q", op.Kind)
		}
		if opErr != nil {
			return opErr
		}
	}
	return nil
}

func (windowsProgramRegistryStore) Delete() error {
	if err := deleteRegistryKey(windowsUninstallRegistryKey); err != nil {
		return err
	}
	return deleteRegistryKey(windowsProductRegistryKey)
}

func deleteRegistryKey(path string) error {
	parent, leaf, ok := splitRegistryKey(path)
	if !ok {
		return fmt.Errorf("invalid registry key")
	}
	key, err := registry.OpenKey(registry.LOCAL_MACHINE, parent, registry.ALL_ACCESS|windowsRegistry32BitView)
	if registryKeyAbsent(err) {
		return nil
	}
	if err != nil {
		return err
	}
	defer key.Close()
	err = registry.DeleteKey(key, leaf)
	if registryKeyAbsent(err) {
		return nil
	}
	return err
}

func splitRegistryKey(path string) (string, string, bool) {
	path = strings.Trim(path, `\`)
	index := strings.LastIndex(path, `\`)
	if index <= 0 || index == len(path)-1 {
		return "", "", false
	}
	return path[:index], path[index+1:], true
}

func registryKeyAbsent(err error) bool {
	return err != nil && (errors.Is(err, registry.ErrNotExist) || errors.Is(err, windows.ERROR_PATH_NOT_FOUND))
}

func currentProcessElevated() bool {
	return windows.GetCurrentProcessToken().IsElevated()
}

func confirmWindowsUninstall() (bool, error) {
	result, err := showMessageBox(uninstallConfirmMessage, "Collector Sidecar", windows.MB_OKCANCEL|windows.MB_ICONQUESTION)
	if err != nil {
		return false, err
	}
	return result == messageBoxButtonOK, nil
}

func notifyWindowsUninstall(success bool, message string) error {
	flags := uint32(windows.MB_OK)
	if success {
		flags |= windows.MB_ICONINFORMATION
	} else {
		flags |= windows.MB_ICONERROR
	}
	_, err := showMessageBox(message, "Collector Sidecar", flags)
	return err
}

func showMessageBox(body, caption string, flags uint32) (int32, error) {
	text, err := windows.UTF16PtrFromString(body)
	if err != nil {
		return 0, err
	}
	title, err := windows.UTF16PtrFromString(caption)
	if err != nil {
		return 0, err
	}
	return windows.MessageBox(0, text, title, flags)
}

func listWindowsRetainedBackupDirs() ([]string, error) {
	entries, err := os.ReadDir(`C:\`)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	found := []string{}
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		full := `C:\` + entry.Name()
		if isWindowsRetainedBackupDir(full) {
			found = append(found, full)
		}
	}
	return found, nil
}

func stopAndDeleteSidecarService() error {
	queryOutput, queryErr := exec.Command("sc.exe", "query", windowsSidecarServiceName).CombinedOutput()
	if queryErr != nil {
		if serviceOutputMissing(queryOutput) {
			return nil
		}
		return errors.New("query sidecar service")
	}
	if !strings.Contains(string(queryOutput), "STOPPED") {
		_, _ = exec.Command("sc.exe", "stop", windowsSidecarServiceName).CombinedOutput()
		if err := waitForSidecar(func(output []byte, err error) bool {
			if err != nil && serviceOutputMissing(output) {
				return true
			}
			return strings.Contains(string(output), "STOPPED")
		}); err != nil {
			return err
		}
	}
	deleteOutput, deleteErr := exec.Command("sc.exe", "delete", windowsSidecarServiceName).CombinedOutput()
	if deleteErr != nil && !serviceDeleteAccepted(deleteErr, deleteOutput) {
		return errors.New("delete sidecar service")
	}
	return waitForSidecar(func(output []byte, err error) bool {
		return err != nil && serviceOutputMissing(output)
	})
}

func serviceOutputMissing(output []byte) bool {
	text := strings.ToLower(string(output))
	return strings.Contains(string(output), "1060") || strings.Contains(text, "does not exist")
}

func serviceDeleteAccepted(err error, output []byte) bool {
	if serviceOutputMissing(output) {
		return true
	}
	var exitErr *exec.ExitError
	if !errors.As(err, &exitErr) {
		return false
	}
	switch exitErr.ExitCode() {
	case 0, 1060, 1072:
		return true
	default:
		return false
	}
}

func waitForSidecar(done func(output []byte, err error) bool) error {
	for attempt := 0; attempt < windowsServiceTransitionAttempts; attempt++ {
		output, err := exec.Command("sc.exe", "query", windowsSidecarServiceName).CombinedOutput()
		if done(output, err) {
			return nil
		}
		if attempt+1 < windowsServiceTransitionAttempts {
			time.Sleep(time.Second)
		}
	}
	return errors.New("timed out waiting for sidecar service")
}

// 静默卸载必须把子进程退出码交还给调用方；ShellExecute 拿不到这个结果。
// 交互式仍用 ShellExecute，未提权时才能用 runas 拉起 UAC。
func launchWindowsProcess(path string, args []string, verb string, wait bool) (int, error) {
	if wait {
		command := exec.Command(path, args...)
		command.Dir = filepath.Dir(path)
		command.Stdout = os.Stdout
		command.Stderr = os.Stderr
		err := command.Run()
		if err == nil {
			return 0, nil
		}
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			return exitErr.ExitCode(), nil
		}
		return 1, err
	}
	if err := shellExecuteVerb(verb, path, strings.Join(args, " ")); err != nil {
		return 1, err
	}
	return 0, nil
}

func shellExecuteVerb(verb, file, args string) error {
	verbPtr, err := windows.UTF16PtrFromString(verb)
	if err != nil {
		return err
	}
	filePtr, err := windows.UTF16PtrFromString(file)
	if err != nil {
		return err
	}
	var argsPtr *uint16
	if args != "" {
		argsPtr, err = windows.UTF16PtrFromString(args)
		if err != nil {
			return err
		}
	}
	cwdPtr, err := windows.UTF16PtrFromString(filepath.Dir(file))
	if err != nil {
		return err
	}
	return windows.ShellExecute(0, verbPtr, filePtr, argsPtr, cwdPtr, windows.SW_SHOWNORMAL)
}

func scheduleDeleteOnReboot(path string) error {
	path = strings.TrimSpace(path)
	if path == "" {
		return errors.New("empty path")
	}
	pointer, err := windows.UTF16PtrFromString(path)
	if err != nil {
		return err
	}
	return windows.MoveFileEx(pointer, nil, windows.MOVEFILE_DELAY_UNTIL_REBOOT)
}

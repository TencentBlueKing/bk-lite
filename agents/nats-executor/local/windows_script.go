package local

import (
	"fmt"
	"os"
	"path/filepath"
)

// Align with ansible-executor WINDOWS_SCRIPT_MAX_BYTES: file-based Windows
// execution bypasses CreateProcess command-line limits, with a 512 KiB cap.
const windowsScriptMaxBytes = 512 * 1024

type windowsScriptLaunch struct {
	Name    string
	Args    []string
	Path    string
	Cleanup func()
}

func usesWindowsFileScript(shell, goos string) bool {
	if goos != "windows" {
		return false
	}
	switch shell {
	case ShellTypeBat, ShellTypeCmd, ShellTypePowerShell, ShellTypePwsh:
		return true
	default:
		return false
	}
}

// prepareWindowsLocalScript writes the script to a temp file and returns a short
// argv suitable for CreateProcess. Returns (nil, nil) when file-based launch
// does not apply. Caller must invoke Cleanup after the process finishes.
func prepareWindowsLocalScript(shell, command, goos string) (*windowsScriptLaunch, error) {
	if !usesWindowsFileScript(shell, goos) {
		return nil, nil
	}
	if len(command) > windowsScriptMaxBytes {
		return nil, fmt.Errorf("Windows script exceeds 512 KiB limit: %d bytes", len(command))
	}

	isPowerShell := shell == ShellTypePowerShell || shell == ShellTypePwsh
	suffix := ".cmd"
	if isPowerShell {
		suffix = ".ps1"
	}

	file, err := os.CreateTemp("", "bklite-job-*"+suffix)
	if err != nil {
		return nil, fmt.Errorf("create Windows script temp file: %w", err)
	}
	path := file.Name()
	cleanup := func() {
		_ = os.Remove(path)
	}

	var content []byte
	if isPowerShell {
		// UTF-8 BOM + existing console encoding preamble, then user script.
		wrapped := wrapPowerShellCommandForOS(command, goos)
		content = append([]byte{0xef, 0xbb, 0xbf}, []byte(wrapped)...)
	} else {
		content = []byte(wrapCmdCommandForOS(command, goos))
	}

	if _, err := file.Write(content); err != nil {
		_ = file.Close()
		cleanup()
		return nil, fmt.Errorf("write Windows script temp file: %w", err)
	}
	if err := file.Close(); err != nil {
		cleanup()
		return nil, fmt.Errorf("close Windows script temp file: %w", err)
	}

	absPath, err := filepath.Abs(path)
	if err != nil {
		cleanup()
		return nil, fmt.Errorf("resolve Windows script temp path: %w", err)
	}

	launch := &windowsScriptLaunch{
		Path:    absPath,
		Cleanup: cleanup,
	}
	if isPowerShell {
		launch.Name = shell
		launch.Args = []string{
			"-NoProfile",
			"-NonInteractive",
			"-ExecutionPolicy",
			"Bypass",
			"-File",
			absPath,
		}
	} else {
		launch.Name = "cmd"
		launch.Args = []string{"/d", "/q", "/c", absPath}
	}
	return launch, nil
}

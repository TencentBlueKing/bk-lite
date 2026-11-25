package local

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf16"
	"unicode/utf8"
)

// Align with ansible-executor WINDOWS_SCRIPT_MAX_BYTES: file-based Windows
// execution bypasses CreateProcess command-line limits, with a 512 KiB cap.
const windowsScriptMaxBytes = 512 * 1024

type windowsScriptLaunch struct {
	Name    string
	Args    []string
	Env     []string
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
func prepareWindowsLocalScript(shell, command, goos string, batArgs []string) (*windowsScriptLaunch, error) {
	if len(batArgs) > 0 && (goos != "windows" || (shell != ShellTypeBat && shell != ShellTypeCmd)) {
		return nil, fmt.Errorf("bat_args require a Windows batch script")
	}
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
		if len(batArgs) > 0 {
			launch.Args, launch.Env, err = batchCommandArgs(absPath, batArgs)
			if err != nil {
				cleanup()
				return nil, err
			}
		}
	}
	return launch, nil
}

// cmd.exe expands the fixed references once with delayed expansion disabled.
// Quoting the resulting values in the environment keeps user data out of the
// launcher command line and avoids CreateProcess's C-style argument escaping.
func batchCommandArgs(path string, values []string) ([]string, []string, error) {
	const limit = 8191 // cmd.exe command-line limit in UTF-16 code units
	args := []string{"/d", "/q", "/v:off", "/s", "/c", "%BK_JOB_BAT_SCRIPT%"}
	quotedPath := `"` + path + `"`
	env := []string{"BK_JOB_BAT_SCRIPT=" + quotedPath, "BK_JOB_BAT_ARGS_READY=1"}
	rawLen := len("cmd ") + len(strings.Join(args, " "))
	expandedLen := rawLen - len("%BK_JOB_BAT_SCRIPT%") + utf16Units(quotedPath)
	for index, value := range values {
		// Up to three UTF-8 bytes fit in one UTF-16 code unit.
		if len(value) > 3*limit {
			return nil, nil, fmt.Errorf("batch arguments exceed the Windows command-line limit")
		}
		if !utf8.ValidString(value) || strings.IndexFunc(value, func(r rune) bool {
			return r == '"' || r < 32 || r == 127 || r == '\ufffe' || r == '\uffff'
		}) >= 0 {
			return nil, nil, fmt.Errorf("invalid character in batch argument %d", index+1)
		}
		if value == "" || strings.ContainsAny(value, ",;=&|<>()^%!") || strings.IndexFunc(value, unicode.IsSpace) >= 0 {
			value = `"` + value + `"`
		}
		key := "BK_JOB_BAT_ARG_" + strconv.Itoa(index+1)
		ref := "%" + key + "%"
		rawLen += 1 + len(ref)
		expandedLen += 1 + utf16Units(value)
		if rawLen > limit || expandedLen > limit {
			return nil, nil, fmt.Errorf("batch arguments exceed the Windows command-line limit")
		}
		args = append(args, ref)
		env = append(env, key+"="+value)
	}
	return args, env, nil
}

func utf16Units(value string) int {
	units := 0
	for _, r := range value {
		units += utf16.RuneLen(r)
	}
	return units
}

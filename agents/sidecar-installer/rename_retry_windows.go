//go:build windows

package main

import (
	"errors"
	"fmt"
	"os/exec"
	"strings"

	"golang.org/x/sys/windows"
)

func isTransientRenameError(err error) bool {
	return errors.Is(err, windows.ERROR_ACCESS_DENIED) || errors.Is(err, windows.ERROR_SHARING_VIOLATION)
}

// renameFailureProcessHints 尽力列出可执行文件位于受影响路径下的进程，帮助现场
// 区分"目录被残留进程占用"与"安全软件拦截"。收集失败不影响主错误返回。
func renameFailureProcessHints(paths ...string) string {
	output, err := exec.Command(
		"powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
		"Get-CimInstance Win32_Process | ForEach-Object { '{0}|{1}' -f $_.ProcessId, $_.ExecutablePath }",
	).Output()
	if err != nil {
		return ""
	}
	hints := []string{}
	for _, line := range strings.Split(string(output), "\n") {
		pid, executable, found := strings.Cut(strings.TrimSpace(line), "|")
		if !found || executable == "" {
			continue
		}
		for _, path := range paths {
			if strings.HasPrefix(strings.ToLower(executable), strings.ToLower(path)+`\`) {
				hints = append(hints, fmt.Sprintf("%s (pid %s)", executable, pid))
				break
			}
		}
	}
	if len(hints) == 0 {
		return ""
	}
	return "; processes inside affected directories: " + strings.Join(hints, ", ")
}

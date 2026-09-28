package main

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

func writeScript(cfg config) (string, error) {
	if cfg.Body == "" {
		return "", fmt.Errorf("script body is empty")
	}
	dir := filepath.Join(cfg.Root, "run", "script-wrapper", cfg.ConfigID)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	name := "script.sh"
	if runtime.GOOS == "windows" {
		name = "script.ps1"
		if looksLikeCmd(cfg.Interpreter) {
			name = "script.bat"
		}
	}
	path := filepath.Join(dir, name)
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, []byte(cfg.Body), 0o700); err != nil {
		return "", err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return "", err
	}
	_ = os.Chmod(dir, 0o700)
	_ = os.Chmod(path, 0o700)
	if err := chownToUser(dir, cfg.User); err != nil {
		return "", err
	}
	if err := chownToUser(path, cfg.User); err != nil {
		return "", err
	}
	return path, nil
}

func looksLikeCmd(interpreter string) bool {
	lower := strings.ToLower(interpreter)
	return strings.Contains(lower, "cmd") || strings.HasSuffix(lower, "cmd.exe")
}

func lockPath(cfg config) string {
	return filepath.Join(cfg.Root, "run", "script-wrapper", cfg.ConfigID+".lock")
}

func resolveInterpreter(cfg config, scriptPath string) []string {
	if cfg.Interpreter != "" {
		return interpreterArgs(cfg.Interpreter, scriptPath)
	}
	if shebang := readShebang(cfg.Body); shebang != "" {
		return append(strings.Fields(shebang), scriptPath)
	}
	if runtime.GOOS == "windows" {
		if strings.HasSuffix(strings.ToLower(scriptPath), ".bat") {
			return []string{"cmd.exe", "/c", scriptPath}
		}
		return []string{"powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", scriptPath}
	}
	return []string{"/bin/sh", scriptPath}
}

func interpreterArgs(interpreter, scriptPath string) []string {
	fields := strings.Fields(interpreter)
	if len(fields) == 0 {
		return []string{scriptPath}
	}
	return append(fields, scriptPath)
}

func readShebang(body string) string {
	line, _, _ := strings.Cut(body, "\n")
	line = strings.TrimSpace(line)
	if !strings.HasPrefix(line, "#!") {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(line, "#!"))
}

package main

import (
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func captureStdout(t *testing.T, fn func()) string {
	t.Helper()
	originalStdout := os.Stdout
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("pipe stdout: %v", err)
	}
	os.Stdout = w
	defer func() {
		os.Stdout = originalStdout
	}()

	fn()
	_ = w.Close()
	output, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("read stdout: %v", err)
	}
	return string(output)
}

func parseEventPayload(t *testing.T, output string) InstallerEvent {
	t.Helper()
	line := strings.TrimSpace(output)
	if !strings.HasPrefix(line, "BKINSTALL_EVENT ") {
		t.Fatalf("unexpected event output: %s", output)
	}
	payload := strings.TrimSpace(strings.TrimPrefix(line, "BKINSTALL_EVENT "))
	var event InstallerEvent
	if err := json.Unmarshal([]byte(payload), &event); err != nil {
		t.Fatalf("unmarshal event: %v", err)
	}
	return event
}

func TestEmitEventWithOptionsPreservesLegacyAndNewFields(t *testing.T) {
	output := captureStdout(t, func() {
		emitEventWithOptions("download_package", "failed", "Download failed", nil, 0, 0, "Download failed: get object failed: nats: object not found", &EventOptions{
			ErrorType:       "object_missing",
			Bucket:          "bklite",
			FileKey:         "linux/arm64/Controller/3.1.22/fusion-collectors-arm64.tar.gz",
			PackageName:     "fusion-collectors-arm64.tar.gz",
			CPUArchitecture: "arm64",
			InstallDir:      "/opt/fusion-collectors",
		})
	})

	event := parseEventPayload(t, output)
	if event.Step != "download_package" || event.Status != "failed" {
		t.Fatalf("unexpected legacy fields: %#v", event)
	}
	if event.ErrorType != "object_missing" {
		t.Fatalf("expected object_missing, got %q", event.ErrorType)
	}
	if event.Bucket != "bklite" || event.FileKey == "" || event.InstallDir != "/opt/fusion-collectors" {
		t.Fatalf("missing structured context: %#v", event)
	}
}

func TestExtractTargetPathParsesBusyBinary(t *testing.T) {
	path := extractTargetPath(errors.New("open /opt/fusion-collectors/bin/vector: text file busy"))
	if path != "/opt/fusion-collectors/bin/vector" {
		t.Fatalf("unexpected target path: %q", path)
	}
}

func TestClassifyDownloadErrorDetectsObjectMissing(t *testing.T) {
	if got := classifyDownloadError(errors.New("get object failed: nats: object not found")); got != "object_missing" {
		t.Fatalf("unexpected error type: %q", got)
	}
}

func TestClassifyDownloadErrorDetectsIOTimeout(t *testing.T) {
	// Issue #2985: "read pipe: i/o timeout" 应被归类为 timeout（服务端可识别枚举），而非空字符串
	if got := classifyDownloadError(errors.New("Download failed: read pipe: i/o timeout")); got != "timeout" {
		t.Fatalf("expected timeout, got %q", got)
	}
}

func TestRunLinuxInstallerDoesNotExposeAPITokenInArgv(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell script test is only for Unix-like systems")
	}

	installDir := t.TempDir()
	token := "issue-3842-secret-token"
	installScript := filepath.Join(installDir, "install.sh")
	script := `#!/bin/sh
set -eu
for arg in "$@"; do
    printf '<%s>\n' "$arg"
done > argv.txt
printf '%s' "$BK_LITE_SERVER_API_TOKEN_FILE" > token-file-path.txt
stat -f '%Lp' "$BK_LITE_SERVER_API_TOKEN_FILE" > token-file-mode.txt 2>/dev/null || stat -c '%a' "$BK_LITE_SERVER_API_TOKEN_FILE" > token-file-mode.txt
cat "$BK_LITE_SERVER_API_TOKEN_FILE" > token-value.txt
`
	if err := os.WriteFile(installScript, []byte(script), 0644); err != nil {
		t.Fatalf("write install.sh: %v", err)
	}

	cfg := &Config{
		ServerURL:  "https://bk.example",
		APIToken:   token,
		ZoneID:     "zone-a",
		GroupID:    "group-a",
		NodeName:   "node-a",
		NodeID:     "node-1",
		InstallDir: installDir,
		Package: PackageConfig{
			CPUArchitecture: "x86_64",
		},
	}

	if err := runLinuxInstaller(cfg); err != nil {
		t.Fatalf("runLinuxInstaller: %v", err)
	}

	argv := readTestFile(t, filepath.Join(installDir, "argv.txt"))
	if strings.Contains(argv, token) {
		t.Fatalf("API token leaked through argv: %q", argv)
	}

	args := strings.Split(strings.TrimSpace(argv), "\n")
	wantArgs := []string{"<https://bk.example>", "<>", "<zone-a>", "<group-a>", "<node-a>", "<node-1>", "<x86_64>"}
	if !equalStringSlices(args, wantArgs) {
		t.Fatalf("unexpected argv\nwant: %#v\n got: %#v", wantArgs, args)
	}

	if got := readTestFile(t, filepath.Join(installDir, "token-value.txt")); got != token {
		t.Fatalf("install script did not receive API token, got %q", got)
	}
	tokenFilePath := readTestFile(t, filepath.Join(installDir, "token-file-path.txt"))
	if strings.Contains(tokenFilePath, token) {
		t.Fatalf("token file path contains token: %q", tokenFilePath)
	}
	if _, err := os.Stat(tokenFilePath); !os.IsNotExist(err) {
		t.Fatalf("expected token file to be cleaned up, stat error: %v", err)
	}
	mode := readTestFile(t, filepath.Join(installDir, "token-file-mode.txt"))
	if mode != "600" {
		t.Fatalf("expected token file mode 600, got %q", mode)
	}
}

func TestLinuxInstallerAPITokenInputsKeepsEmptyTokenOnArgv(t *testing.T) {
	arg, env, cleanup, err := linuxInstallerAPITokenInputs(t.TempDir(), "")
	if err != nil {
		t.Fatalf("linuxInstallerAPITokenInputs: %v", err)
	}
	defer cleanup()
	if arg != "" || env != "" {
		t.Fatalf("empty token should not create env/file inputs, got arg=%q env=%q", arg, env)
	}
}

func readTestFile(t *testing.T, path string) string {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(content)
}

func equalStringSlices(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

package main

import (
	"archive/zip"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

type fakeWindowsServiceController struct {
	serviceExisted bool
	registerErrors []error
	registerCalls  []string
	stopCalls      int
}

func (fake *fakeWindowsServiceController) StopAndDelete() (bool, error) {
	fake.stopCalls++
	return fake.serviceExisted, nil
}

func (fake *fakeWindowsServiceController) Register(installDir string) error {
	fake.registerCalls = append(fake.registerCalls, installDir)
	if len(fake.registerErrors) == 0 {
		return nil
	}
	err := fake.registerErrors[0]
	fake.registerErrors = fake.registerErrors[1:]
	return err
}

func writeControllerZip(t *testing.T, files map[string]string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "controller.zip")
	archiveFile, err := os.Create(path)
	if err != nil {
		t.Fatalf("create archive: %v", err)
	}
	writer := zip.NewWriter(archiveFile)
	for name, content := range files {
		entry, err := writer.Create(name)
		if err != nil {
			t.Fatalf("create archive entry: %v", err)
		}
		if _, err := entry.Write([]byte(content)); err != nil {
			t.Fatalf("write archive entry: %v", err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatalf("close archive writer: %v", err)
	}
	if err := archiveFile.Close(); err != nil {
		t.Fatalf("close archive: %v", err)
	}
	return path
}

func TestInstallWindowsPackageRestoresExistingInstallationWhenNewServiceFails(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	oldBinary := filepath.Join(installDir, "collector-sidecar.exe")
	if err := os.WriteFile(oldBinary, []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{
		"controller/collector-sidecar.exe": "new-binary",
		"controller/bin/new.txt":           "new-file",
	})
	controller := &fakeWindowsServiceController{
		serviceExisted: true,
		registerErrors: []error{fmt.Errorf("new service failed"), nil},
	}
	cfg := &Config{
		ServerURL:  "https://bk.example",
		APIToken:   "token",
		NodeID:     "node-1",
		NodeName:   "node-1",
		ZoneID:     "1",
		GroupID:    "1",
		OS:         "windows",
		InstallDir: installDir,
		Package:    PackageConfig{CPUArchitecture: "x86_64"},
	}

	err := installWindowsPackage(cfg, zipPath, controller)

	if err == nil || !strings.Contains(err.Error(), "new service failed") {
		t.Fatalf("expected service failure, got %v", err)
	}
	content, readErr := os.ReadFile(oldBinary)
	if readErr != nil {
		t.Fatalf("read restored binary: %v", readErr)
	}
	if string(content) != "old-binary" {
		t.Fatalf("old installation was not restored: %q", content)
	}
	if len(controller.registerCalls) != 2 {
		t.Fatalf("expected new and rollback service registration, got %#v", controller.registerCalls)
	}
	if controller.stopCalls != 2 {
		t.Fatalf("expected failed new service to be removed before rollback, got %d stop calls", controller.stopCalls)
	}
}

func TestRestorePreviousWindowsInstallationRestoresDirectoryAndService(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	backupDir := installDir + ".bklite-backup"
	if err := os.MkdirAll(backupDir, 0755); err != nil {
		t.Fatalf("create backup dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(backupDir, "collector-sidecar.exe"), []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	controller := &fakeWindowsServiceController{serviceExisted: true}

	err := restorePreviousWindowsInstallation(controller, installDir, backupDir, true, true, nil)

	if err != nil {
		t.Fatalf("restore previous Windows installation: %v", err)
	}
	content, readErr := os.ReadFile(filepath.Join(installDir, "collector-sidecar.exe"))
	if readErr != nil || string(content) != "old-binary" {
		t.Fatalf("previous installation was not restored: %q, %v", content, readErr)
	}
	if len(controller.registerCalls) != 1 || controller.registerCalls[0] != installDir {
		t.Fatalf("previous service was not restored: %#v", controller.registerCalls)
	}
}

func TestInstallWindowsPackagePreservesRuntimeDataAfterSuccessfulActivation(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	logDir := filepath.Join(installDir, "logs")
	if err := os.MkdirAll(logDir, 0755); err != nil {
		t.Fatalf("create log dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "collector-sidecar.exe"), []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	if err := os.WriteFile(filepath.Join(logDir, "sidecar.log"), []byte("existing-log"), 0644); err != nil {
		t.Fatalf("write existing log: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{
		"controller/collector-sidecar.exe": "new-binary",
	})
	controller := &fakeWindowsServiceController{serviceExisted: true}
	cfg := &Config{
		ServerURL:  "https://bk.example",
		APIToken:   "token",
		NodeID:     "node-1",
		NodeName:   "node-1",
		ZoneID:     "1",
		GroupID:    "1",
		OS:         "windows",
		InstallDir: installDir,
		Package:    PackageConfig{CPUArchitecture: "x86_64"},
	}

	if err := installWindowsPackage(cfg, zipPath, controller); err != nil {
		t.Fatalf("install Windows package: %v", err)
	}
	newBinary, err := os.ReadFile(filepath.Join(installDir, "collector-sidecar.exe"))
	if err != nil || string(newBinary) != "new-binary" {
		t.Fatalf("new binary was not activated: %q, %v", newBinary, err)
	}
	existingLog, err := os.ReadFile(filepath.Join(logDir, "sidecar.log"))
	if err != nil || string(existingLog) != "existing-log" {
		t.Fatalf("runtime log was not preserved: %q, %v", existingLog, err)
	}
	if _, err := os.Stat(installDir + ".bklite-backup"); !os.IsNotExist(err) {
		t.Fatalf("backup directory should be removed after success: %v", err)
	}
}

func TestInstallWindowsPackageRejectsOversizedExpansionBeforeStoppingService(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	oldBinary := filepath.Join(installDir, "collector-sidecar.exe")
	if err := os.WriteFile(oldBinary, []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{
		"controller/collector-sidecar.exe": "new-binary",
	})
	previousLimit := controllerPackageMaxExpandedBytes
	controllerPackageMaxExpandedBytes = 4
	defer func() { controllerPackageMaxExpandedBytes = previousLimit }()
	controller := &fakeWindowsServiceController{serviceExisted: true}
	cfg := &Config{InstallDir: installDir, OS: "windows"}

	err := installWindowsPackage(cfg, zipPath, controller)

	if err == nil || !strings.Contains(err.Error(), "expanded size") {
		t.Fatalf("expected expanded size limit failure, got %v", err)
	}
	if controller.stopCalls != 0 {
		t.Fatalf("service must not be stopped before package validation")
	}
	content, readErr := os.ReadFile(oldBinary)
	if readErr != nil || string(content) != "old-binary" {
		t.Fatalf("existing installation was modified: %q, %v", content, readErr)
	}
}

func TestResolveConfigURLReadsRestrictedFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "session-url")
	if err := os.WriteFile(path, []byte("  https://bk.example/session?token=secret\n"), 0600); err != nil {
		t.Fatalf("write session URL file: %v", err)
	}

	got, err := resolveConfigURL("", path)
	if err != nil {
		t.Fatalf("resolveConfigURL: %v", err)
	}
	if got != "https://bk.example/session?token=secret" {
		t.Fatalf("unexpected URL: %q", got)
	}
}

func TestResolveConfigURLRejectsMissingInputs(t *testing.T) {
	if _, err := resolveConfigURL("", ""); err == nil {
		t.Fatal("expected missing URL inputs to fail")
	}
}

func TestResolveConfigURLRejectsAmbiguousInputs(t *testing.T) {
	if _, err := resolveConfigURL("https://bk.example/session", "session-url"); err == nil {
		t.Fatal("expected direct URL and URL file together to fail")
	}
}

func TestNewHTTPClientVerifiesTLSByDefault(t *testing.T) {
	client := newHTTPClient(false)
	transport, ok := client.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("unexpected transport type: %T", client.Transport)
	}
	if transport.TLSClientConfig != nil && transport.TLSClientConfig.InsecureSkipVerify {
		t.Fatal("TLS verification must be enabled by default")
	}
}

func TestWriteConfigKeepsSidecarTLSVerificationEnabled(t *testing.T) {
	installDir := t.TempDir()
	cfg := &Config{
		ServerURL:  "https://bk.example",
		APIToken:   "token",
		NodeID:     "node-1",
		NodeName:   "node-1",
		ZoneID:     "1",
		GroupID:    "1",
		InstallDir: installDir,
		Package:    PackageConfig{CPUArchitecture: "x86_64"},
	}

	if err := writeConfig(cfg); err != nil {
		t.Fatalf("write config: %v", err)
	}
	content, err := os.ReadFile(filepath.Join(installDir, "sidecar.yml"))
	if err != nil {
		t.Fatalf("read config: %v", err)
	}
	if !strings.Contains(string(content), "tls_skip_verify: false") {
		t.Fatalf("TLS verification was not enabled: %s", content)
	}
}

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
	mode := strings.TrimSpace(readTestFile(t, filepath.Join(installDir, "token-file-mode.txt")))
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

package main

import (
	"archive/zip"
	"bytes"
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
	"time"
)

type recordingProgressPublisher struct {
	subjects []string
	payloads [][]byte
	flushes  int
}

type recordingCloser struct {
	closed bool
}

func (closer *recordingCloser) Close() error {
	closer.closed = true
	return nil
}

func TestCloseAndRemovePartialDownloadClosesBeforeRemove(t *testing.T) {
	closer := &recordingCloser{}
	removed := false
	remove := func(path string) error {
		if !closer.closed {
			t.Fatal("partial download must be closed before removal on Windows")
		}
		if path != `C:\Windows\Temp\sidecar-partial.zip` {
			t.Fatalf("unexpected removal path: %s", path)
		}
		removed = true
		return nil
	}

	if err := closeAndRemovePartialDownload(closer, `C:\Windows\Temp\sidecar-partial.zip`, remove); err != nil {
		t.Fatalf("cleanup partial download: %v", err)
	}
	if !removed {
		t.Fatal("partial download was not removed")
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}

type timedResponseBody struct {
	payload     []byte
	deliveredAt time.Time
}

func (body *timedResponseBody) Read(buffer []byte) (int, error) {
	if body.payload == nil {
		return 0, io.EOF
	}
	time.Sleep(10 * time.Millisecond)
	n := copy(buffer, body.payload)
	body.payload = nil
	body.deliveredAt = time.Now()
	return n, io.EOF
}

func (body *timedResponseBody) Close() error {
	return nil
}

func (publisher *recordingProgressPublisher) Publish(subject string, payload []byte) error {
	publisher.subjects = append(publisher.subjects, subject)
	publisher.payloads = append(publisher.payloads, append([]byte(nil), payload...))
	return nil
}

func (publisher *recordingProgressPublisher) FlushTimeout(_ time.Duration) error {
	publisher.flushes++
	return nil
}

type fakeWindowsServiceController struct {
	serviceExisted bool
	startErrors    []error
	stopErrors     []error
	startCalls     []string
	stopCalls      int
	removeCalls    int
}

type preservingWindowsServiceController struct {
	serviceExisted bool
	stopCalls      int
	startCalls     int
	removeCalls    int
	onStop         func() error
}

func (fake *preservingWindowsServiceController) Stop() (bool, error) {
	fake.stopCalls++
	if fake.onStop != nil {
		if err := fake.onStop(); err != nil {
			return false, err
		}
	}
	return fake.serviceExisted, nil
}

func (fake *preservingWindowsServiceController) Start(_ string, _ bool) error {
	fake.startCalls++
	return nil
}

func (fake *preservingWindowsServiceController) Remove() error {
	fake.removeCalls++
	return nil
}

func (fake *fakeWindowsServiceController) Stop() (bool, error) {
	fake.stopCalls++
	if len(fake.stopErrors) > 0 {
		err := fake.stopErrors[0]
		fake.stopErrors = fake.stopErrors[1:]
		return fake.serviceExisted, err
	}
	return fake.serviceExisted, nil
}

func (fake *fakeWindowsServiceController) Start(installDir string, _ bool) error {
	fake.startCalls = append(fake.startCalls, installDir)
	if len(fake.startErrors) == 0 {
		return nil
	}
	err := fake.startErrors[0]
	fake.startErrors = fake.startErrors[1:]
	return err
}

func (fake *fakeWindowsServiceController) Remove() error {
	fake.removeCalls++
	return nil
}

// observingWindowsServiceController records whether a backup directory was in
// place when the new service was started, which is the only moment where a
// transactional upgrade is distinguishable from a fresh install.
type observingWindowsServiceController struct {
	backupDir            string
	backupExistedOnStart bool
}

func (fake *observingWindowsServiceController) Stop() (bool, error) {
	return false, nil
}

func (fake *observingWindowsServiceController) Start(_ string, _ bool) error {
	if _, err := os.Stat(fake.backupDir); err == nil {
		fake.backupExistedOnStart = true
	}
	return nil
}

func (fake *observingWindowsServiceController) Remove() error {
	return nil
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

func TestInstallerEventReporterPublishesTheSameEventKeptInStdout(t *testing.T) {
	var output bytes.Buffer
	publisher := &recordingProgressPublisher{}
	reporter, err := NewInstallerEventReporter(&output, "installer.progress.0123456789abcdef0123456789abcdef", "0123456789abcdef0123456789abcdef")
	if err != nil {
		t.Fatalf("create event reporter: %v", err)
	}
	reporter.Attach(publisher)

	reporter.Emit(InstallerEvent{Step: "download_package", Status: "running", Message: "Downloading"})

	stdoutLine := strings.TrimSpace(output.String())
	if !strings.HasPrefix(stdoutLine, `BKINSTALL_EVENT {"step":"download_package","status":"running","message":"Downloading"`) {
		t.Fatalf("stdout did not retain installer event: %s", stdoutLine)
	}
	if len(publisher.payloads) != 1 || publisher.subjects[0] != "installer.progress.0123456789abcdef0123456789abcdef" {
		t.Fatalf("unexpected progress publications: subjects=%#v payloads=%d", publisher.subjects, len(publisher.payloads))
	}
	var envelope map[string]any
	if err := json.Unmarshal(publisher.payloads[0], &envelope); err != nil {
		t.Fatalf("decode progress envelope: %v", err)
	}
	if envelope["execution_id"] != "0123456789abcdef0123456789abcdef" || envelope["line"] != stdoutLine {
		t.Fatalf("published event differs from stdout: %#v", envelope)
	}
}

func TestInstallerEventReporterFlushesTerminalEventBeforeProcessExit(t *testing.T) {
	publisher := &recordingProgressPublisher{}
	reporter, err := NewInstallerEventReporter(io.Discard, "installer.progress.0123456789abcdef0123456789abcdef", "0123456789abcdef0123456789abcdef")
	if err != nil {
		t.Fatalf("create event reporter: %v", err)
	}
	reporter.Attach(publisher)
	reporter.Emit(InstallerEvent{Step: "download_package", Status: "failed", Error: "object missing"})
	if publisher.flushes != 1 {
		t.Fatalf("terminal event must be flushed before fatal can exit, got %d flushes", publisher.flushes)
	}
}

func TestValidateClockSkewAllowsBoundaryAndBothDirections(t *testing.T) {
	serverTime := time.Date(2026, 7, 29, 2, 0, 0, 0, time.UTC)
	tests := []struct {
		name       string
		offset     time.Duration
		wantAhead  bool
		wantBehind bool
	}{
		{name: "same time"},
		{name: "ahead within boundary", offset: 300 * time.Second, wantAhead: true},
		{name: "behind within boundary", offset: -300 * time.Second, wantBehind: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			midpoint := serverTime.Add(tt.offset)
			cfg := &Config{
				ClockValidation: &ClockValidationConfig{
					ServerTimeUnixMS: serverTime.UnixMilli(),
					MaxSkewSeconds:   300,
				},
				sessionRequestStartedAt:  midpoint.Add(-50 * time.Millisecond),
				sessionRequestFinishedAt: midpoint.Add(50 * time.Millisecond),
			}

			result, err := validateClockSkew(cfg)
			if err != nil {
				t.Fatalf("expected clock skew to pass: %v", err)
			}
			if result == nil {
				t.Fatal("expected clock skew details")
			}
			if tt.wantAhead && result.OffsetSeconds <= 0 {
				t.Fatalf("expected node clock ahead, got %f", result.OffsetSeconds)
			}
			if tt.wantBehind && result.OffsetSeconds >= 0 {
				t.Fatalf("expected node clock behind, got %f", result.OffsetSeconds)
			}
		})
	}
}

func TestValidateClockSkewRejectsAheadAndBehindBeyondBoundary(t *testing.T) {
	serverTime := time.Date(2026, 7, 29, 2, 0, 0, 0, time.UTC)
	for _, offset := range []time.Duration{300*time.Second + 2*time.Millisecond, -300*time.Second - 2*time.Millisecond} {
		midpoint := serverTime.Add(offset)
		cfg := &Config{
			ClockValidation: &ClockValidationConfig{
				ServerTimeUnixMS: serverTime.UnixMilli(),
				MaxSkewSeconds:   300,
			},
			sessionRequestStartedAt:  midpoint.Add(-50 * time.Millisecond),
			sessionRequestFinishedAt: midpoint.Add(50 * time.Millisecond),
		}

		result, err := validateClockSkew(cfg)
		if err == nil || !strings.Contains(err.Error(), "maximum allowed skew is 300 seconds") {
			t.Fatalf("expected clock skew rejection for %v, got result=%#v err=%v", offset, result, err)
		}
	}
}

func TestValidateClockSkewRejectsInvalidContractAndAllowsMissingLegacyContract(t *testing.T) {
	if result, err := validateClockSkew(&Config{}); err != nil || result != nil {
		t.Fatalf("legacy session without clock contract must remain compatible: result=%#v err=%v", result, err)
	}

	invalid := &Config{
		ClockValidation:          &ClockValidationConfig{},
		sessionRequestStartedAt:  time.Now(),
		sessionRequestFinishedAt: time.Now(),
	}
	if _, err := validateClockSkew(invalid); err == nil {
		t.Fatal("invalid clock validation contract must fail")
	}
}

func TestConfigRejectsExplicitNullClockValidation(t *testing.T) {
	var cfg Config
	if err := json.Unmarshal([]byte(`{"clock_validation":null}`), &cfg); err == nil {
		t.Fatal("explicit null clock validation must fail")
	}
	if err := json.Unmarshal([]byte(`{}`), &cfg); err != nil {
		t.Fatalf("legacy session without clock validation must remain valid: %v", err)
	}
}

func TestFetchConfigRecordsFinishAfterReadingAndParsingResponse(t *testing.T) {
	body := &timedResponseBody{payload: []byte(`{"node_id":"node-1"}`)}
	client := &http.Client{Transport: roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: http.StatusOK, Body: body}, nil
	})}

	cfg, err := fetchConfig(client, "https://server.example/session")
	if err != nil {
		t.Fatalf("fetch config: %v", err)
	}
	if cfg.sessionRequestFinishedAt.Before(body.deliveredAt) {
		t.Fatalf("request finished at %s before response body was delivered at %s", cfg.sessionRequestFinishedAt, body.deliveredAt)
	}
}

func TestInstallerStepPositionUsesNewEightStepProtocol(t *testing.T) {
	index, total := installerStepPosition("download_package")
	if index != 4 || total != 8 {
		t.Fatalf("expected download step 4/8, got %d/%d", index, total)
	}
}

func TestInstallWindowsPackageTreatsPreCreatedEmptyDirectoryAsFreshInstall(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{
		"controller/collector-sidecar.exe": "new-binary",
	})
	controller := &observingWindowsServiceController{backupDir: installDir + ".bklite-backup"}
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
	if controller.backupExistedOnStart {
		t.Fatal("fresh install must not back up the pre-created empty directory")
	}
	if _, err := os.Stat(installDir + ".bklite-backup"); !os.IsNotExist(err) {
		t.Fatalf("fresh install must not leave a backup directory: %v", err)
	}
	for _, marker := range []string{windowsActivationPendingMarker, windowsActivationCommittedMarker} {
		if _, err := os.Stat(filepath.Join(installDir, marker)); !os.IsNotExist(err) {
			t.Fatalf("fresh install must not leave activation marker %s: %v", marker, err)
		}
	}
	content, err := os.ReadFile(filepath.Join(installDir, "collector-sidecar.exe"))
	if err != nil {
		t.Fatalf("read installed binary: %v", err)
	}
	if string(content) != "new-binary" {
		t.Fatalf("new installation was not activated: %q", content)
	}
}

func TestInstallWindowsPackageReportsActualPhaseBoundaries(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	zipPath := writeControllerZip(t, map[string]string{
		"controller/collector-sidecar.exe": "new-binary",
	})
	controller := &observingWindowsServiceController{backupDir: installDir + ".bklite-backup"}
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
	events := []string{}

	err := installWindowsPackageWithProgress(
		cfg,
		zipPath,
		controller,
		func(step, status, _ string) { events = append(events, step+":"+status) },
	)

	if err != nil {
		t.Fatalf("install Windows package: %v", err)
	}
	want := []string{
		"extract_package:running",
		"extract_package:success",
		"configure_runtime:running",
		"configure_runtime:success",
		"run_package_installer:running",
		"run_package_installer:success",
	}
	if strings.Join(events, ",") != strings.Join(want, ",") {
		t.Fatalf("unexpected Windows install progress: got %v, want %v", events, want)
	}
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
		startErrors:    []error{fmt.Errorf("new service failed"), nil},
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
	if len(controller.startCalls) != 2 {
		t.Fatalf("expected new and rollback service starts, got %#v", controller.startCalls)
	}
	if controller.stopCalls != 2 || controller.removeCalls != 0 {
		t.Fatalf("existing service registration must be retained: stop=%d remove=%d", controller.stopCalls, controller.removeCalls)
	}
}

func TestInstallWindowsPackageRecoversRetainedBackupOnRetry(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	oldBinary := filepath.Join(installDir, "collector-sidecar.exe")
	if err := os.WriteFile(oldBinary, []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{"collector-sidecar.exe": "new-binary"})
	controller := &fakeWindowsServiceController{
		serviceExisted: true,
		startErrors:    []error{fmt.Errorf("new service failed"), nil},
		stopErrors: []error{
			nil,
			fmt.Errorf("failed service is still stopping"),
			fmt.Errorf("failed service remains stuck"),
		},
	}
	cfg := &Config{InstallDir: installDir, OS: "windows"}

	firstErr := installWindowsPackage(cfg, zipPath, controller)
	if firstErr == nil || !strings.Contains(firstErr.Error(), "previous installation retained") {
		t.Fatalf("expected retained recovery backup, got %v", firstErr)
	}
	if _, err := os.Stat(installDir + ".bklite-backup"); err != nil {
		t.Fatalf("previous installation backup was not retained: %v", err)
	}
	if _, err := os.Stat(filepath.Join(installDir+".bklite-backup", windowsActivationPendingMarker)); err != nil {
		t.Fatalf("pending activation marker was not retained: %v", err)
	}

	retryErr := installWindowsPackage(cfg, zipPath, controller)
	if retryErr == nil || !strings.Contains(retryErr.Error(), "recovered previous Windows installation") {
		t.Fatalf("expected recovery-before-retry result, got %v", retryErr)
	}
	content, readErr := os.ReadFile(oldBinary)
	if readErr != nil || string(content) != "old-binary" {
		t.Fatalf("previous installation was not recovered: %q, %v", content, readErr)
	}
	if _, err := os.Stat(installDir + ".bklite-backup"); !os.IsNotExist(err) {
		t.Fatalf("recovery backup should be consumed, got %v", err)
	}
}

func TestInterruptedRecoveryRevalidatesLeaseAfterStoppingService(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	backupDir := installDir + ".bklite-backup"
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create current install: %v", err)
	}
	if err := os.MkdirAll(backupDir, 0755); err != nil {
		t.Fatalf("create backup install: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "collector-sidecar.exe"), []byte("current"), 0644); err != nil {
		t.Fatalf("write current binary: %v", err)
	}
	if err := os.WriteFile(filepath.Join(backupDir, "collector-sidecar.exe"), []byte("previous"), 0644); err != nil {
		t.Fatalf("write previous binary: %v", err)
	}
	if err := os.WriteFile(filepath.Join(backupDir, windowsActivationPendingMarker), []byte("pending\n"), 0600); err != nil {
		t.Fatalf("write pending marker: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{"collector-sidecar.exe": "unused"})
	controller := &fakeWindowsServiceController{serviceExisted: true}
	validationCalls := 0
	cfg := &Config{
		InstallDir:       installDir,
		OS:               "windows",
		RemoteTaskNodeID: 32, RemoteAttempt: 1, RemoteExecutionID: "recovery-lease",
		RemoteDeadlineUnix: time.Now().Add(time.Hour).Unix(),
		RemoteLeaseValidator: func() error {
			validationCalls++
			if validationCalls == 2 {
				return fmt.Errorf("server recovery lease revoked")
			}
			return nil
		},
	}

	err := installWindowsPackage(cfg, zipPath, controller)

	if err == nil || !strings.Contains(err.Error(), "server recovery lease revoked") {
		t.Fatalf("expected recovery lease rejection, got %v", err)
	}
	if validationCalls != 2 || controller.stopCalls != 1 || len(controller.startCalls) != 1 {
		t.Fatalf("expected recovery lease checks and service restart: validations=%d controller=%#v", validationCalls, controller)
	}
	current, readErr := os.ReadFile(filepath.Join(installDir, "collector-sidecar.exe"))
	if readErr != nil || string(current) != "current" {
		t.Fatalf("recovery modified current install after revocation: %q, %v", current, readErr)
	}
	if _, statErr := os.Stat(backupDir); statErr != nil {
		t.Fatalf("recovery backup was removed after revocation: %v", statErr)
	}
}

func TestInterruptedRecoveryRestartsServiceWhenStopFails(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	backupDir := installDir + ".bklite-backup"
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create current install: %v", err)
	}
	if err := os.MkdirAll(backupDir, 0755); err != nil {
		t.Fatalf("create backup install: %v", err)
	}
	if err := os.WriteFile(filepath.Join(backupDir, "collector-sidecar.exe"), []byte("previous"), 0644); err != nil {
		t.Fatalf("write previous binary: %v", err)
	}
	controller := &fakeWindowsServiceController{
		serviceExisted: true,
		stopErrors:     []error{fmt.Errorf("recovery stop timed out")},
	}

	err := recoverInterruptedWindowsInstallation(
		controller,
		installDir,
		backupDir,
		&Config{InstallDir: installDir, OS: "windows"},
	)

	if err == nil || !strings.Contains(err.Error(), "recovery stop timed out") {
		t.Fatalf("expected recovery stop failure, got %v", err)
	}
	if len(controller.startCalls) != 1 || controller.startCalls[0] != installDir {
		t.Fatalf("service was not restarted after recovery stop failure: %#v", controller.startCalls)
	}
	if _, statErr := os.Stat(backupDir); statErr != nil {
		t.Fatalf("backup changed after recovery stop failure: %v", statErr)
	}
}

func TestInstallWindowsPackageRejectsInvalidRecoveryBackupBeforeStoppingService(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir+".bklite-backup", 0755); err != nil {
		t.Fatalf("create invalid backup dir: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{"collector-sidecar.exe": "new-binary"})
	controller := &fakeWindowsServiceController{serviceExisted: true}

	err := installWindowsPackage(&Config{InstallDir: installDir, OS: "windows"}, zipPath, controller)

	if err == nil || !strings.Contains(err.Error(), "requires manual recovery") {
		t.Fatalf("expected invalid recovery backup rejection, got %v", err)
	}
	if controller.stopCalls != 0 {
		t.Fatalf("invalid recovery backup must be rejected before stopping service")
	}
}

func TestInstallWindowsPackageDoesNotRollbackCommittedBackupResidue(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	backupDir := installDir + ".bklite-backup"
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create healthy install dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "collector-sidecar.exe"), []byte("healthy-new"), 0644); err != nil {
		t.Fatalf("write healthy binary: %v", err)
	}
	if err := os.MkdirAll(backupDir, 0755); err != nil {
		t.Fatalf("create committed backup: %v", err)
	}
	if err := os.WriteFile(filepath.Join(backupDir, "collector-sidecar.exe"), []byte("old"), 0644); err != nil {
		t.Fatalf("write old backup binary: %v", err)
	}
	if err := os.WriteFile(filepath.Join(backupDir, windowsActivationCommittedMarker), []byte("committed\n"), 0600); err != nil {
		t.Fatalf("write committed marker: %v", err)
	}
	invalidZip := filepath.Join(t.TempDir(), "invalid.zip")
	if err := os.WriteFile(invalidZip, []byte("not a zip"), 0600); err != nil {
		t.Fatalf("write invalid zip: %v", err)
	}
	controller := &fakeWindowsServiceController{serviceExisted: true}

	err := installWindowsPackage(&Config{InstallDir: installDir, OS: "windows"}, invalidZip, controller)

	if err == nil {
		t.Fatalf("expected invalid package error")
	}
	content, readErr := os.ReadFile(filepath.Join(installDir, "collector-sidecar.exe"))
	if readErr != nil || string(content) != "healthy-new" {
		t.Fatalf("committed healthy installation was rolled back: %q, %v", content, readErr)
	}
	if controller.stopCalls != 0 {
		t.Fatalf("package validation should fail before stopping healthy service")
	}
}

func TestInstallWindowsPackageRestartsExistingServiceWhenStopFails(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	oldBinary := filepath.Join(installDir, "collector-sidecar.exe")
	if err := os.WriteFile(oldBinary, []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{"collector-sidecar.exe": "new-binary"})
	controller := &fakeWindowsServiceController{
		serviceExisted: true,
		stopErrors:     []error{fmt.Errorf("stop timed out")},
	}
	cfg := &Config{InstallDir: installDir, OS: "windows"}

	err := installWindowsPackage(cfg, zipPath, controller)

	if err == nil || !strings.Contains(err.Error(), "stop timed out") {
		t.Fatalf("expected stop failure, got %v", err)
	}
	if len(controller.startCalls) != 1 || controller.startCalls[0] != installDir {
		t.Fatalf("old service must be restarted after stop failure: %#v", controller.startCalls)
	}
	content, readErr := os.ReadFile(oldBinary)
	if readErr != nil || string(content) != "old-binary" {
		t.Fatalf("old installation changed after stop failure: %q, %v", content, readErr)
	}
}

func TestInstallWindowsPackageRevalidatesServerLeaseAfterStoppingService(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	oldBinary := filepath.Join(installDir, "collector-sidecar.exe")
	if err := os.WriteFile(oldBinary, []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{"collector-sidecar.exe": "new-binary"})
	controller := &fakeWindowsServiceController{serviceExisted: true}
	validationCalls := 0
	cfg := &Config{
		InstallDir:       installDir,
		OS:               "windows",
		RemoteTaskNodeID: 31, RemoteAttempt: 1, RemoteExecutionID: "lease-test",
		RemoteDeadlineUnix: time.Now().Add(time.Hour).Unix(),
		RemoteLeaseValidator: func() error {
			validationCalls++
			if validationCalls == 3 {
				return fmt.Errorf("server lease revoked")
			}
			return nil
		},
	}

	err := installWindowsPackage(cfg, zipPath, controller)

	if err == nil || !strings.Contains(err.Error(), "server lease revoked") {
		t.Fatalf("expected revoked lease failure, got %v", err)
	}
	if validationCalls != 3 || controller.stopCalls != 1 || len(controller.startCalls) != 1 {
		t.Fatalf("expected pre/post-stop validation and service restart: validations=%d controller=%#v", validationCalls, controller)
	}
	content, readErr := os.ReadFile(oldBinary)
	if readErr != nil || string(content) != "old-binary" {
		t.Fatalf("old installation changed after lease revocation: %q, %v", content, readErr)
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
	if len(controller.startCalls) != 1 || controller.startCalls[0] != installDir {
		t.Fatalf("previous service was not restored: %#v", controller.startCalls)
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

func TestInstallWindowsPackagePreservesUninstallEntrypointAfterSuccessfulActivation(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "collector-sidecar.exe"), []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "uninstall.exe"), []byte("nsis-uninstaller"), 0644); err != nil {
		t.Fatalf("write uninstaller: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "installer.ico"), []byte("icon"), 0644); err != nil {
		t.Fatalf("write installer icon: %v", err)
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
	uninstaller, err := os.ReadFile(filepath.Join(installDir, "uninstall.exe"))
	if err != nil || string(uninstaller) != "nsis-uninstaller" {
		t.Fatalf("uninstaller was not preserved: %q, %v", uninstaller, err)
	}
	icon, err := os.ReadFile(filepath.Join(installDir, "installer.ico"))
	if err != nil || string(icon) != "icon" {
		t.Fatalf("installer icon was not preserved: %q, %v", icon, err)
	}
}

func TestInstallWindowsPackageKeepsPackageProvidedInstallerFiles(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "collector-sidecar.exe"), []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "uninstall.exe"), []byte("old-uninstaller"), 0644); err != nil {
		t.Fatalf("write old uninstaller: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{
		"controller/collector-sidecar.exe": "new-binary",
		"controller/uninstall.exe":         "packaged-uninstaller",
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
	uninstaller, err := os.ReadFile(filepath.Join(installDir, "uninstall.exe"))
	if err != nil || string(uninstaller) != "packaged-uninstaller" {
		t.Fatalf("package-provided uninstaller must win: %q, %v", uninstaller, err)
	}
}

func TestInstallWindowsPackageSucceedsWithoutPreviousUninstaller(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	zipPath := writeControllerZip(t, map[string]string{
		"controller/collector-sidecar.exe": "new-binary",
	})
	controller := &fakeWindowsServiceController{}
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
		t.Fatalf("first Windows installation: %v", err)
	}
	if _, err := os.Stat(filepath.Join(installDir, "uninstall.exe")); !os.IsNotExist(err) {
		t.Fatalf("first installation must not fabricate an uninstaller: %v", err)
	}
	newBinary, err := os.ReadFile(filepath.Join(installDir, "collector-sidecar.exe"))
	if err != nil || string(newBinary) != "new-binary" {
		t.Fatalf("new binary was not activated: %q, %v", newBinary, err)
	}
}

func TestInstallWindowsPackagePreservesExistingServiceRegistration(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "collector-sidecar.exe"), []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{
		"controller/collector-sidecar.exe": "new-binary",
	})
	controller := &preservingWindowsServiceController{serviceExisted: true}
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
	if controller.stopCalls != 1 || controller.startCalls != 1 {
		t.Fatalf("existing service should be stopped and restarted once: stop=%d start=%d", controller.stopCalls, controller.startCalls)
	}
	if controller.removeCalls != 0 {
		t.Fatalf("existing service registration must be preserved, got %d removals", controller.removeCalls)
	}
}

func TestInstallWindowsPackageRestartsExistingServiceWhenBackupFails(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	backupDir := installDir + ".bklite-backup"
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(installDir, "collector-sidecar.exe"), []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	zipPath := writeControllerZip(t, map[string]string{
		"controller/collector-sidecar.exe": "new-binary",
	})
	controller := &preservingWindowsServiceController{
		serviceExisted: true,
		onStop: func() error {
			if err := os.MkdirAll(backupDir, 0755); err != nil {
				return err
			}
			return os.WriteFile(filepath.Join(backupDir, "unexpected-file"), []byte("occupied"), 0644)
		},
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

	if err == nil || !strings.Contains(err.Error(), "backup existing installation") {
		t.Fatalf("expected backup failure, got %v", err)
	}
	if controller.startCalls != 1 {
		t.Fatalf("existing service must restart after backup failure, got %d starts", controller.startCalls)
	}
	if controller.removeCalls != 0 {
		t.Fatalf("existing service registration must not be removed, got %d removals", controller.removeCalls)
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

func TestInstallWindowsPackageRejectsConcurrentInstallationBeforeStoppingService(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	releaseLock, err := acquireInstallLock(installDir)
	if err != nil {
		t.Fatalf("acquire first install lock: %v", err)
	}
	defer releaseLock()
	zipPath := writeControllerZip(t, map[string]string{"collector-sidecar.exe": "new-binary"})
	controller := &fakeWindowsServiceController{serviceExisted: true}
	cfg := &Config{InstallDir: installDir, OS: "windows"}

	err = installWindowsPackage(cfg, zipPath, controller)

	if err == nil || !strings.Contains(err.Error(), "another installation is already running") {
		t.Fatalf("expected concurrent installation rejection, got %v", err)
	}
	if controller.stopCalls != 0 {
		t.Fatalf("concurrent attempt must fail before stopping service")
	}
}

func TestPrepareInstallDirectoriesDoesNotModifyExistingWindowsInstallation(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	if err := os.MkdirAll(installDir, 0755); err != nil {
		t.Fatalf("create install dir: %v", err)
	}
	oldBinary := filepath.Join(installDir, "collector-sidecar.exe")
	if err := os.WriteFile(oldBinary, []byte("old-binary"), 0644); err != nil {
		t.Fatalf("write old binary: %v", err)
	}
	cfg := &Config{OS: "windows", InstallDir: installDir}

	if err := prepareInstallDirectories(cfg); err != nil {
		t.Fatalf("prepare Windows install target: %v", err)
	}
	for _, name := range windowsRuntimeDirectories {
		if _, err := os.Stat(filepath.Join(installDir, name)); !os.IsNotExist(err) {
			t.Fatalf("Windows preparation modified live %s directory: %v", name, err)
		}
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

func TestValidateHTTPSURLRejectsHTTPAndRelativeURLs(t *testing.T) {
	for _, candidate := range []string{"http://bk.example/session", "/session", ""} {
		if err := validateHTTPSURL(candidate); err == nil {
			t.Fatalf("expected insecure URL to fail: %q", candidate)
		}
	}
	if err := validateHTTPSURL("https://bk.example/session"); err != nil {
		t.Fatalf("expected HTTPS URL to pass: %v", err)
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

func TestWriteConfigPersistsNATSTLSCAForWindowsCollectors(t *testing.T) {
	installDir := t.TempDir()
	caContent := "-----BEGIN CERTIFICATE-----\ntest-ca\n-----END CERTIFICATE-----\n"
	cfg := &Config{
		ServerURL:  "https://bk.example",
		APIToken:   "token",
		NodeID:     "node-1",
		NodeName:   "node-1",
		ZoneID:     "1",
		GroupID:    "1",
		InstallDir: installDir,
		Package:    PackageConfig{CPUArchitecture: "x86_64"},
		Storage:    StorageConfig{NATSTLSCA: caContent},
	}

	if err := writeConfig(cfg); err != nil {
		t.Fatalf("write config: %v", err)
	}
	content, err := os.ReadFile(filepath.Join(installDir, "certs", "nats-ca.crt"))
	if err != nil {
		t.Fatalf("read persisted NATS CA: %v", err)
	}
	if string(content) != caContent {
		t.Fatalf("unexpected persisted NATS CA: %q", content)
	}
}

func TestWriteConfigPreservesExplicitLegacyTLSCompatibility(t *testing.T) {
	installDir := t.TempDir()
	cfg := &Config{
		ServerURL:           "https://legacy.example",
		APIToken:            "token",
		NodeID:              "node-1",
		NodeName:            "node-1",
		ZoneID:              "1",
		GroupID:             "1",
		InstallDir:          installDir,
		SkipTLSVerification: true,
		Package:             PackageConfig{CPUArchitecture: "x86_64"},
	}

	if err := writeConfig(cfg); err != nil {
		t.Fatalf("write config: %v", err)
	}
	content, err := os.ReadFile(filepath.Join(installDir, "sidecar.yml"))
	if err != nil {
		t.Fatalf("read config: %v", err)
	}
	if !strings.Contains(string(content), "tls_skip_verify: true") {
		t.Fatalf("explicit legacy TLS compatibility was not preserved: %s", content)
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

func TestClassifyInstallErrorMarksRetainedBackupForManualRecovery(t *testing.T) {
	err := fmt.Errorf("activate new service: failed; previous installation retained at C:\\fusion-collectors.bklite-backup for recovery")
	if got := classifyInstallError(err); got != "manual_recovery_required" {
		t.Fatalf("expected manual_recovery_required, got %q", got)
	}
}

func TestWindowsInstallFenceRejectsOlderOrDuplicateRemoteExecution(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	deadline := time.Now().Add(time.Hour).Unix()
	first := &Config{RemoteTaskNodeID: 31, RemoteAttempt: 2, RemoteExecutionID: "first", RemoteDeadlineUnix: deadline}
	if err := claimWindowsInstallFence(first, installDir); err != nil {
		t.Fatalf("claim first fence: %v", err)
	}
	newer := &Config{RemoteTaskNodeID: 32, RemoteAttempt: 1, RemoteExecutionID: "newer", RemoteDeadlineUnix: deadline}
	if err := claimWindowsInstallFence(newer, installDir); err != nil {
		t.Fatalf("claim newer fence: %v", err)
	}
	for _, stale := range []*Config{
		{RemoteTaskNodeID: 31, RemoteAttempt: 3, RemoteExecutionID: "older-node", RemoteDeadlineUnix: deadline},
		{RemoteTaskNodeID: 32, RemoteAttempt: 1, RemoteExecutionID: "duplicate", RemoteDeadlineUnix: deadline},
	} {
		if err := claimWindowsInstallFence(stale, installDir); err == nil {
			t.Fatalf("expected stale fence rejection for %#v", stale)
		}
	}
}

func TestWindowsInstallFenceRejectsExpiredExecutionWithoutReplacingFence(t *testing.T) {
	installDir := filepath.Join(t.TempDir(), "fusion-collectors")
	active := &Config{
		RemoteTaskNodeID: 31, RemoteAttempt: 1, RemoteExecutionID: "active",
		RemoteDeadlineUnix: time.Now().Add(time.Hour).Unix(),
	}
	if err := claimWindowsInstallFence(active, installDir); err != nil {
		t.Fatalf("claim active fence: %v", err)
	}
	original, err := os.ReadFile(installDir + ".bklite-install.fence")
	if err != nil {
		t.Fatalf("read active fence: %v", err)
	}
	expired := &Config{
		RemoteTaskNodeID: 32, RemoteAttempt: 1, RemoteExecutionID: "expired",
		RemoteDeadlineUnix: time.Now().Add(-time.Second).Unix(),
	}
	if err := claimWindowsInstallFence(expired, installDir); err == nil {
		t.Fatal("expected expired execution rejection")
	}
	retained, err := os.ReadFile(installDir + ".bklite-install.fence")
	if err != nil {
		t.Fatalf("read retained fence: %v", err)
	}
	if !bytes.Equal(original, retained) {
		t.Fatalf("expired execution replaced the active fence: %q", retained)
	}
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

func TestRunLinuxInstallerIncludesScriptOutputOnFailure(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell script test is only for Unix-like systems")
	}

	installDir := t.TempDir()
	installScript := filepath.Join(installDir, "install.sh")
	script := `#!/bin/sh
echo "用法: install.sh {server_url} ..."
exit 1
`
	if err := os.WriteFile(installScript, []byte(script), 0755); err != nil {
		t.Fatalf("write install.sh: %v", err)
	}

	cfg := &Config{
		ServerURL:  "https://bk.example",
		APIToken:   "",
		ZoneID:     "zone-a",
		GroupID:    "group-a",
		NodeName:   "node-a",
		NodeID:     "node-1",
		InstallDir: installDir,
		Package: PackageConfig{
			CPUArchitecture: "x86_64",
		},
	}

	err := runLinuxInstaller(cfg)
	if err == nil {
		t.Fatal("expected install.sh failure")
	}
	message := err.Error()
	if !strings.Contains(message, "exit status 1") {
		t.Fatalf("expected exit status in error, got %q", message)
	}
	if !strings.Contains(message, "用法: install.sh") {
		t.Fatalf("expected install.sh stdout in error, got %q", message)
	}
}

func TestTruncateInstallerOutputKeepsTail(t *testing.T) {
	got := truncateInstallerOutput("abcdefghij", 4)
	if got != "...ghij" {
		t.Fatalf("unexpected truncation: %q", got)
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

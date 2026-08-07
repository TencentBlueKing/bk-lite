package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func withInjectedTransientRename(t *testing.T, check func(error) bool, delay time.Duration) {
	t.Helper()
	previousCheck := transientRenameErrorCheck
	previousDelay := windowsRenameRetryDelay
	transientRenameErrorCheck = check
	windowsRenameRetryDelay = delay
	t.Cleanup(func() {
		transientRenameErrorCheck = previousCheck
		windowsRenameRetryDelay = previousDelay
	})
}

func makeDirWithFile(t *testing.T, dir, file string) {
	t.Helper()
	if err := os.MkdirAll(dir, 0755); err != nil {
		t.Fatalf("create dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, file), []byte(file), 0644); err != nil {
		t.Fatalf("write file: %v", err)
	}
}

func TestRenameWithWindowsTransientRetryRecoversOnceBlockerClears(t *testing.T) {
	withInjectedTransientRename(t, func(error) bool { return true }, 10*time.Millisecond)
	base := t.TempDir()
	source := filepath.Join(base, "staging")
	target := filepath.Join(base, "install")
	makeDirWithFile(t, source, "collector-sidecar.exe")
	makeDirWithFile(t, target, "scan-blocker")

	go func() {
		time.Sleep(35 * time.Millisecond)
		_ = os.RemoveAll(target)
	}()

	if err := renameWithWindowsTransientRetry(source, target); err != nil {
		t.Fatalf("rename must succeed once the transient blocker clears: %v", err)
	}
	if _, err := os.Stat(filepath.Join(target, "collector-sidecar.exe")); err != nil {
		t.Fatalf("renamed content missing: %v", err)
	}
}

func TestRenameWithWindowsTransientRetryFailsFastOnPermanentErrors(t *testing.T) {
	withInjectedTransientRename(t, func(error) bool { return false }, time.Hour)
	base := t.TempDir()

	started := time.Now()
	err := renameWithWindowsTransientRetry(filepath.Join(base, "missing"), filepath.Join(base, "install"))

	if err == nil {
		t.Fatal("expected failure for missing source")
	}
	if elapsed := time.Since(started); elapsed > 5*time.Second {
		t.Fatalf("permanent errors must not be retried, took %s", elapsed)
	}
	if strings.Contains(err.Error(), "attempts") {
		t.Fatalf("permanent failure must not carry retry diagnostics: %v", err)
	}
}

func TestRenameWithWindowsTransientRetryReportsDiagnosticsAfterExhaustion(t *testing.T) {
	withInjectedTransientRename(t, func(error) bool { return true }, time.Millisecond)
	base := t.TempDir()
	source := filepath.Join(base, "staging")
	target := filepath.Join(base, "install")
	makeDirWithFile(t, source, "collector-sidecar.exe")
	makeDirWithFile(t, target, "scan-blocker")

	err := renameWithWindowsTransientRetry(source, target)

	if err == nil {
		t.Fatal("expected exhaustion failure while target stays blocked")
	}
	message := err.Error()
	if !strings.Contains(message, "10 attempts") {
		t.Fatalf("error must report retry count: %v", err)
	}
	if !strings.Contains(message, "source exists: true") || !strings.Contains(message, "target exists: true") {
		t.Fatalf("error must report path existence diagnostics: %v", err)
	}
}

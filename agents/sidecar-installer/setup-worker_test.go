package main

import (
	"encoding/json"
	"errors"
	"io"
	"os"
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

package utils

import (
	"strings"
	"testing"
)

func TestSharedOutputCaptureAppliesOneSharedLimit(t *testing.T) {
	capture := NewSharedOutputCapture(64)

	if _, err := capture.StdoutWriter().Write([]byte("abcdefghij")); err != nil {
		t.Fatalf("stdout write failed: %v", err)
	}
	if _, err := capture.StderrWriter().Write([]byte("klmnopqrst")); err != nil {
		t.Fatalf("stderr write failed: %v", err)
	}

	snapshot := capture.Snapshot()
	if snapshot.Truncated {
		t.Fatal("did not expect truncation before limit is reached")
	}
	if string(snapshot.Stdout) != "abcdefghij" {
		t.Fatalf("unexpected stdout capture: %q", string(snapshot.Stdout))
	}
	if string(snapshot.Stderr) != "klmnopqrst" {
		t.Fatalf("unexpected stderr capture: %q", string(snapshot.Stderr))
	}
	if snapshot.StdoutDropped != 0 || snapshot.StderrDropped != 0 {
		t.Fatalf("unexpected dropped counters: %+v", snapshot)
	}

	if _, err := capture.StderrWriter().Write([]byte(strings.Repeat("z", 48))); err != nil {
		t.Fatalf("second stderr write failed: %v", err)
	}

	snapshot = capture.Snapshot()
	if snapshot.StderrDropped == 0 {
		t.Fatalf("expected stderr bytes to be dropped: %+v", snapshot)
	}

	output := FormatCapturedOutput(string(snapshot.Stdout), string(snapshot.Stderr), snapshot)
	if len(output) > snapshot.Limit {
		t.Fatalf("expected rendered output within limit, got %d", len(output))
	}
	if !strings.Contains(output, "output truncated") {
		t.Fatalf("expected truncation notice, got %q", output)
	}
}

func TestSharedOutputCaptureExactLimitHasNoMarker(t *testing.T) {
	capture := NewSharedOutputCapture(8)
	if _, err := capture.StdoutWriter().Write([]byte("abcd")); err != nil {
		t.Fatalf("stdout write failed: %v", err)
	}
	if _, err := capture.StderrWriter().Write([]byte("efgh")); err != nil {
		t.Fatalf("stderr write failed: %v", err)
	}

	snapshot := capture.Snapshot()
	if snapshot.Truncated {
		t.Fatal("did not expect truncation")
	}
	output := FormatCapturedOutput(string(snapshot.Stdout), string(snapshot.Stderr), snapshot)
	if output != "abcdefgh" {
		t.Fatalf("unexpected output: %q", output)
	}
}

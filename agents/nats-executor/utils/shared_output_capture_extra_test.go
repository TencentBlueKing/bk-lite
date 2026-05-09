package utils

import "testing"

func TestSharedOutputCaptureHelperCornerCases(t *testing.T) {
	capture := NewSharedOutputCapture(0)
	if capture.limit != CommandOutputLimitBytes {
		t.Fatalf("expected default limit, got %d", capture.limit)
	}

	if got := appendTruncationNotice("payload", "notice", 0); got != "notice" {
		t.Fatalf("unexpected zero-limit truncation notice: %q", got)
	}
	if got := appendTruncationNotice("payload", "notice", 3); got != "not" {
		t.Fatalf("unexpected short-limit notice: %q", got)
	}
	if got := truncateUTF8ToByteLimit("中文输出", 5); got != "中" {
		t.Fatalf("unexpected utf8 truncation: %q", got)
	}
	if got := truncateUTF8ToByteLimit("payload", -1); got != "" {
		t.Fatalf("expected empty result for non-positive limit, got %q", got)
	}
	if got := truncateUTF8ToByteLimit("payload", len("payload")); got != "payload" {
		t.Fatalf("expected exact limit to keep payload, got %q", got)
	}
}

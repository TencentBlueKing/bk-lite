package utils

import (
	"bytes"
	"strings"
	"testing"
)

func TestBoundedBufferKeepsTailWithTruncationMarker(t *testing.T) {
	buffer := NewBoundedBuffer(8)
	if _, err := buffer.Write([]byte("abcdefghij")); err != nil {
		t.Fatalf("write failed: %v", err)
	}

	output := buffer.String()
	if !strings.Contains(output, "output truncated") {
		t.Fatalf("expected truncation marker, got %q", output)
	}
	if !strings.HasSuffix(output, "cdefghij") {
		t.Fatalf("expected buffer to keep tail, got %q", output)
	}
	if buffer.TotalLen() != 10 {
		t.Fatalf("unexpected total length: %d", buffer.TotalLen())
	}
}

func TestBoundedBufferLimitsLargeWrites(t *testing.T) {
	buffer := NewBoundedBuffer(1024)
	payload := bytes.Repeat([]byte("x"), 4096)
	if _, err := buffer.Write(payload); err != nil {
		t.Fatalf("write failed: %v", err)
	}

	if buffer.Len() != 1024 {
		t.Fatalf("expected captured buffer to stay bounded, got %d", buffer.Len())
	}
	if !buffer.Truncated() {
		t.Fatal("expected truncation flag")
	}
}

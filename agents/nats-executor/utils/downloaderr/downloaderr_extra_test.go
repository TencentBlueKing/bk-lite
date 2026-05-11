package downloaderr

import (
	"context"
	"errors"
	"testing"

	"github.com/nats-io/nats.go"
)

func TestErrorAndUnwrapBehaviors(t *testing.T) {
	baseErr := errors.New("disk full")
	err := &Error{Kind: KindIO, Err: baseErr}

	if got := err.Error(); got != "disk full" {
		t.Fatalf("unexpected error string: %q", got)
	}
	if unwrapped := err.Unwrap(); !errors.Is(unwrapped, baseErr) {
		t.Fatalf("expected unwrap to expose base error, got %v", unwrapped)
	}

	var nilErr *Error
	if nilErr.Error() != "" {
		t.Fatal("expected nil typed error to stringify to empty string")
	}
	if nilErr.Unwrap() != nil {
		t.Fatal("expected nil typed error to unwrap to nil")
	}
}

func TestKindOfMapsWellKnownErrors(t *testing.T) {
	if got := KindOf(context.DeadlineExceeded); got != KindTimeout {
		t.Fatalf("expected deadline exceeded to map to timeout, got %s", got)
	}
	if got := KindOf(nats.ErrTimeout); got != KindTimeout {
		t.Fatalf("expected nats timeout to map to timeout, got %s", got)
	}
	if got := KindOf(context.Canceled); got != KindCanceled {
		t.Fatalf("expected canceled to map to canceled, got %s", got)
	}
	if got := KindOf(errors.New("boom")); got != KindUnknown {
		t.Fatalf("expected plain error to map to unknown, got %s", got)
	}
}

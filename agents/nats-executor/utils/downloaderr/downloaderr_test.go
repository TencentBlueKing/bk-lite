package downloaderr

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"github.com/nats-io/nats.go"
)

func TestNewReturnsNilForNilError(t *testing.T) {
	if err := New(KindDependency, nil); err != nil {
		t.Fatalf("expected nil, got %v", err)
	}
}

func TestKindOfPreservesWrappedTypedError(t *testing.T) {
	err := fmt.Errorf("wrap: %w", New(KindIO, errors.New("rename failed")))

	if got := KindOf(err); got != KindIO {
		t.Fatalf("expected io kind, got %s", got)
	}
}

func TestKindOfDetectsTimeoutSources(t *testing.T) {
	tests := []struct {
		name string
		err  error
	}{
		{name: "context deadline exceeded", err: context.DeadlineExceeded},
		{name: "nats timeout", err: nats.ErrTimeout},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := KindOf(tt.err); got != KindTimeout {
				t.Fatalf("expected timeout kind, got %s", got)
			}
		})
	}
}

func TestKindOfDetectsCanceledContext(t *testing.T) {
	if got := KindOf(context.Canceled); got != KindCanceled {
		t.Fatalf("expected canceled kind, got %s", got)
	}
}

func TestKindOfReturnsUnknownForPlainErrors(t *testing.T) {
	if got := KindOf(errors.New("boom")); got != KindUnknown {
		t.Fatalf("expected unknown kind, got %s", got)
	}
}

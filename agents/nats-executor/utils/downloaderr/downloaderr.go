package downloaderr

import (
	"context"
	"errors"

	"github.com/nats-io/nats.go"
)

type Kind string

const (
	KindUnknown    Kind = "unknown"
	KindTimeout    Kind = "timeout"
	KindCanceled   Kind = "canceled"
	KindDependency Kind = "dependency"
	KindIO         Kind = "io"
)

type Error struct {
	Kind Kind
	Err  error
}

func (e *Error) Error() string {
	if e == nil || e.Err == nil {
		return ""
	}
	return e.Err.Error()
}

func (e *Error) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Err
}

func New(kind Kind, err error) error {
	if err == nil {
		return nil
	}
	return &Error{Kind: kind, Err: err}
}

func KindOf(err error) Kind {
	var typedErr *Error
	if errors.As(err, &typedErr) && typedErr != nil {
		return typedErr.Kind
	}

	switch {
	case errors.Is(err, context.DeadlineExceeded), errors.Is(err, nats.ErrTimeout):
		return KindTimeout
	case errors.Is(err, context.Canceled):
		return KindCanceled
	default:
		return KindUnknown
	}
}

package wire

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/nats-io/nats.go"
)

// ControlClient is the ctl-class RUM controller client used by composition
// roots (apps/server). It implements the plugins/ops/server/rum RUM control plane port: it
// mints request envelopes with a fresh idempotency key per call (so a NATS
// retry never double-applies) and maps controller errors onto ControlError so
// handlers can translate them to HTTP status.
type ControlClient struct {
	client *Client
	newID  func() string
}

// NewControlClient wraps a NATS connection. timeout and retries govern the
// underlying request-reply calls.
func NewControlClient(connection *nats.Conn, timeout time.Duration, retries int) *ControlClient {
	return &ControlClient{
		client: NewClient(connection, timeout, retries),
		newID:  uuid.NewString,
	}
}

// Available reports whether the client can issue control requests.
func (client *ControlClient) Available() bool {
	return client != nil &&
		client.client != nil &&
		client.client.connection != nil &&
		client.client.connection.IsConnected()
}

// Close drains and closes the NATS connection.
func (client *ControlClient) Close() {
	if client == nil || client.client == nil || client.client.connection == nil {
		return
	}
	_ = client.client.connection.Drain()
	client.client.connection.Close()
}

// Request issues a rumwire request-reply against subject and decodes the
// controller response envelope.
func (client *ControlClient) Request(
	ctx context.Context,
	subject string,
	actor string,
	payload json.RawMessage,
	expectedRevision *int64,
) (revision int64, data json.RawMessage, err error) {
	if client == nil || client.client == nil || client.client.connection == nil {
		return 0, nil, &ControlError{Code: "unavailable", Message: "RUM controller is not configured"}
	}
	request := RequestEnvelope{
		APIVersion:       APIVersion,
		RequestID:        client.newID(),
		IdempotencyKey:   client.newID(),
		ExpectedRevision: expectedRevision,
		Actor:            actor,
		Payload:          payload,
	}
	response, err := client.client.Call(ctx, subject, request)
	if err != nil {
		switch {
		case errors.Is(err, nats.ErrNoResponders):
			return 0, nil, &ControlError{Code: "unavailable", Message: "RUM controller has no running instance"}
		case errors.Is(err, nats.ErrConnectionClosed),
			errors.Is(err, nats.ErrDisconnected),
			errors.Is(err, nats.ErrConnectionReconnecting):
			return 0, nil, &ControlError{Code: "unavailable", Message: "RUM control NATS connection is unavailable"}
		}
		return 0, nil, err
	}
	if response.Error != nil {
		return 0, nil, &ControlError{Code: string(response.Error.Code), Message: response.Error.Message}
	}
	data, err = json.Marshal(response.Data)
	if err != nil {
		return 0, nil, err
	}
	return response.Revision, data, nil
}

// ControlError is a controller error carried over NATS. ControlCode implements
// the coder interface used by plugin handlers to map to HTTP status.
type ControlError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func (err *ControlError) Error() string { return err.Code + ": " + err.Message }

func (err *ControlError) ControlCode() string { return err.Code }

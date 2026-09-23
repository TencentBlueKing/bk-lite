package wire_test

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"

	"github.com/bk-lite/rum-collector/pkg/rum/wire"
)

func TestControlClientMapsControllerErrorAndNoResponders(t *testing.T) {
	ns, err := server.NewServer(&server.Options{Host: "127.0.0.1", Port: -1, NoLog: true, NoSigs: true})
	require.NoError(t, err)
	ns.Start()
	require.True(t, ns.ReadyForConnections(3*time.Second))
	t.Cleanup(ns.Shutdown)

	nc, err := nats.Connect(ns.ClientURL())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	_, err = nc.Subscribe(wire.SubjectStatusGet, func(message *nats.Msg) {
		var request wire.RequestEnvelope
		require.NoError(t, json.Unmarshal(message.Data, &request))
		response, _ := json.Marshal(wire.ResponseEnvelope{
			RequestID: request.RequestID,
			Error:     &wire.ResponseError{Code: wire.ErrorNotFound, Message: "missing application"},
		})
		_ = message.Respond(response)
	})
	require.NoError(t, err)
	require.NoError(t, nc.Flush())

	client := wire.NewControlClient(nc, time.Second, 1)
	require.True(t, client.Available())

	_, _, err = client.Request(context.Background(), wire.SubjectStatusGet, "tester", json.RawMessage(`{}`), nil)
	var controlErr *wire.ControlError
	require.ErrorAs(t, err, &controlErr)
	require.Equal(t, string(wire.ErrorNotFound), controlErr.Code)
	require.Equal(t, "missing application", controlErr.Message)
	require.Equal(t, string(wire.ErrorNotFound), controlErr.ControlCode())

	_, _, err = client.Request(context.Background(), "rum.v1.control.missing", "tester", json.RawMessage(`{}`), nil)
	require.ErrorAs(t, err, &controlErr)
	require.Equal(t, "unavailable", controlErr.Code)

	nilClient := (*wire.ControlClient)(nil)
	require.False(t, nilClient.Available())
	_, _, err = nilClient.Request(context.Background(), wire.SubjectStatusGet, "tester", nil, nil)
	require.ErrorAs(t, err, &controlErr)
	require.Equal(t, "unavailable", controlErr.Code)
}

func TestConnectControlClientAcceptsNATSPasswordURL(t *testing.T) {
	ns, err := server.NewServer(&server.Options{
		Host:     "127.0.0.1",
		Port:     -1,
		Username: "rum_controller",
		Password: "rum-controller-contract-password",
		NoLog:    true,
		NoSigs:   true,
	})
	require.NoError(t, err)
	ns.Start()
	require.True(t, ns.ReadyForConnections(3*time.Second))
	t.Cleanup(ns.Shutdown)

	url := "nats://rum_controller:rum-controller-contract-password@" + ns.Addr().String()
	nc, err := wire.ConnectControlClient(wire.ControlClientConfig{URL: url}, "test-controller")
	require.NoError(t, err)
	t.Cleanup(nc.Close)
	require.True(t, nc.IsConnected())
}

func TestConnectControlClientRejectsTLSEmbeddedCredentials(t *testing.T) {
	_, err := wire.ConnectControlClient(wire.ControlClientConfig{
		URL: "tls://user:password@nats:4222",
	}, "test-controller")
	require.ErrorContains(t, err, "embedded credentials")
}

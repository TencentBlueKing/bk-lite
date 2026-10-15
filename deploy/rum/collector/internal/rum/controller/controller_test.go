package controller

import (
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
)

func TestControllerServesVersionedRequestReplyThroughQueueSubscription(t *testing.T) {
	service, _ := newTestService(t)
	natsServer := runTestNATSServer(t)
	connection, err := nats.Connect(natsServer.ClientURL())
	require.NoError(t, err)
	t.Cleanup(connection.Close)

	controller := NewController(connection, service)
	require.NoError(t, controller.Start())
	t.Cleanup(func() { require.NoError(t, controller.Drain()) })

	request := requestBytes(t, "req-nats", "idem-nats", nil, projectionPayload("storefront", "browser-key-current", 1, true))
	message, err := connection.Request(SubjectProjectionApply, request, time.Second)
	require.NoError(t, err)
	var response ResponseEnvelope
	require.NoError(t, json.Unmarshal(message.Data, &response))
	require.Nil(t, response.Error)
	require.Equal(t, int64(1), response.Revision)
}

func TestControlRequestFailsWithoutAControllerInsteadOfBeingQueued(t *testing.T) {
	natsServer := runTestNATSServer(t)
	connection, err := nats.Connect(natsServer.ClientURL())
	require.NoError(t, err)
	t.Cleanup(connection.Close)

	_, err = connection.Request(SubjectStatusGet, []byte(`{}`), time.Second)
	require.True(t, errors.Is(err, nats.ErrNoResponders) || errors.Is(err, nats.ErrTimeout))
}

func runTestNATSServer(t *testing.T) *server.Server {
	t.Helper()
	natsServer, err := server.NewServer(&server.Options{
		Host: "127.0.0.1",
		Port: -1,
	})
	require.NoError(t, err)
	natsServer.Start()
	require.True(t, natsServer.ReadyForConnections(5*time.Second))
	t.Cleanup(natsServer.Shutdown)
	return natsServer
}

package controller

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nkeys"
	"github.com/stretchr/testify/require"
)

func TestDeployedNATSACLAllowsOnlyControlRequestReply(t *testing.T) {
	ctlKey, ctlPublic := newUserNKey(t)
	controllerKey, controllerPublic := newUserNKey(t)
	t.Setenv("RUM_CTL_PUBLIC_NKEY", ctlPublic)
	t.Setenv("RUM_CONTROLLER_PUBLIC_NKEY", controllerPublic)

	caFile, certFile, keyFile := writeTestTLSFiles(t)
	configBytes, err := os.ReadFile("testdata/nats.conf")
	require.NoError(t, err)
	config := string(configBytes)
	config = strings.Replace(config, "port: 4222", "port: -1", 1)
	config = strings.Replace(config, "http_port: 8222", "http_port: -1", 1)
	config = strings.ReplaceAll(config, "/run/secrets/rum_nats_tls_cert", certFile)
	config = strings.ReplaceAll(config, "/run/secrets/rum_nats_tls_key", keyFile)
	config = strings.ReplaceAll(config, "/run/secrets/rum_nats_tls_ca", caFile)
	configFile := filepath.Join(t.TempDir(), "nats.conf")
	require.NoError(t, os.WriteFile(configFile, []byte(config), 0o600))

	options, err := server.ProcessConfigFile(configFile)
	require.NoError(t, err)
	natsServer, err := server.NewServer(options)
	require.NoError(t, err)
	natsServer.Start()
	require.True(t, natsServer.ReadyForConnections(5*time.Second))
	t.Cleanup(natsServer.Shutdown)

	controller := connectNKey(t, natsServer.ClientURL(), caFile, controllerPublic, controllerKey, nil)
	subscription, err := controller.QueueSubscribe(SubjectStatusGet, QueueGroupController, func(message *nats.Msg) {
		require.NoError(t, message.Respond([]byte(`{"requestId":"req-1","data":{"ready":true}}`)))
	})
	require.NoError(t, err)
	require.NoError(t, controller.Flush())
	t.Cleanup(func() { _ = subscription.Unsubscribe() })

	ctl := connectNKey(t, natsServer.ClientURL(), caFile, ctlPublic, ctlKey, nil)
	response, err := ctl.Request(SubjectStatusGet, []byte(`{
		"apiVersion":"rum.control/v1",
		"requestId":"req-1",
		"idempotencyKey":"idem-1",
		"actor":"test",
		"payload":{}
	}`), time.Second)
	require.NoError(t, err)
	require.Contains(t, string(response.Data), `"ready":true`)

	expectPermissionViolation(t, natsServer.ClientURL(), caFile, ctlPublic, ctlKey, func(connection *nats.Conn) error {
		return connection.Publish("agents.v1.control.reconcile", []byte("forbidden"))
	})
	expectPermissionViolation(t, natsServer.ClientURL(), caFile, ctlPublic, ctlKey, func(connection *nats.Conn) error {
		_, err := connection.Subscribe(SubjectStatusGet, func(*nats.Msg) {})
		return err
	})
	expectPermissionViolation(t, natsServer.ClientURL(), caFile, controllerPublic, controllerKey, func(connection *nats.Conn) error {
		return connection.Publish(SubjectStatusGet, []byte("forbidden"))
	})
	expectPermissionViolation(t, natsServer.ClientURL(), caFile, controllerPublic, controllerKey, func(connection *nats.Conn) error {
		_, err := connection.Subscribe("otel.v1.>", func(*nats.Msg) {})
		return err
	})
}

func newUserNKey(t *testing.T) (nkeys.KeyPair, string) {
	t.Helper()
	key, err := nkeys.CreateUser()
	require.NoError(t, err)
	public, err := key.PublicKey()
	require.NoError(t, err)
	t.Cleanup(func() { key.Wipe() })
	return key, public
}

func connectNKey(
	t *testing.T,
	url string,
	caFile string,
	public string,
	key nkeys.KeyPair,
	errorHandler nats.ErrHandler,
) *nats.Conn {
	t.Helper()
	options := []nats.Option{
		nats.RootCAs(caFile),
		nats.Nkey(public, key.Sign),
	}
	if errorHandler != nil {
		options = append(options, nats.ErrorHandler(errorHandler))
	}
	connection, err := nats.Connect(url, options...)
	require.NoError(t, err)
	t.Cleanup(connection.Close)
	return connection
}

func expectPermissionViolation(
	t *testing.T,
	url string,
	caFile string,
	public string,
	key nkeys.KeyPair,
	action func(*nats.Conn) error,
) {
	t.Helper()
	errors := make(chan error, 1)
	connection := connectNKey(t, url, caFile, public, key, func(_ *nats.Conn, _ *nats.Subscription, err error) {
		select {
		case errors <- err:
		default:
		}
	})
	require.NoError(t, action(connection))
	_ = connection.Flush()
	select {
	case err := <-errors:
		require.ErrorContains(t, err, "Permissions Violation")
	case <-time.After(2 * time.Second):
		t.Fatal("expected NATS permission violation")
	}
}

func writeTestTLSFiles(t *testing.T) (string, string, string) {
	t.Helper()
	now := time.Now()
	caKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	caTemplate := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "RUM test CA"},
		NotBefore:             now.Add(-time.Minute),
		NotAfter:              now.Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, caTemplate, caTemplate, &caKey.PublicKey, caKey)
	require.NoError(t, err)

	serverKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	serverTemplate := &x509.Certificate{
		SerialNumber: big.NewInt(2),
		Subject:      pkix.Name{CommonName: "nats"},
		DNSNames:     []string{"nats"},
		IPAddresses:  []net.IP{net.ParseIP("127.0.0.1"), net.ParseIP("0.0.0.0")},
		NotBefore:    now.Add(-time.Minute),
		NotAfter:     now.Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	serverDER, err := x509.CreateCertificate(rand.Reader, serverTemplate, caTemplate, &serverKey.PublicKey, caKey)
	require.NoError(t, err)

	directory := t.TempDir()
	caFile := filepath.Join(directory, "ca.pem")
	certFile := filepath.Join(directory, "server.pem")
	keyFile := filepath.Join(directory, "server-key.pem")
	require.NoError(t, os.WriteFile(caFile, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER}), 0o600))
	require.NoError(t, os.WriteFile(certFile, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: serverDER}), 0o600))
	require.NoError(t, os.WriteFile(keyFile, pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(serverKey)}), 0o600))
	return caFile, certFile, keyFile
}

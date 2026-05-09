package main

import (
	"bytes"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"io"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
)

func writeTestCertificateFiles(t *testing.T) (string, string, string) {
	t.Helper()

	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("failed to generate private key: %v", err)
	}

	template := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "nats-executor.test"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(time.Hour),
		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment | x509.KeyUsageCertSign,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth, x509.ExtKeyUsageServerAuth},
		IsCA:                  true,
		BasicConstraintsValid: true,
	}

	der, err := x509.CreateCertificate(rand.Reader, template, template, &privateKey.PublicKey, privateKey)
	if err != nil {
		t.Fatalf("failed to create certificate: %v", err)
	}

	dir := t.TempDir()
	certPath := filepath.Join(dir, "client.pem")
	keyPath := filepath.Join(dir, "client.key")
	caPath := filepath.Join(dir, "ca.pem")

	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(privateKey)})

	for path, content := range map[string][]byte{
		certPath: certPEM,
		keyPath:  keyPEM,
		caPath:   certPEM,
	} {
		if err := os.WriteFile(path, content, 0o600); err != nil {
			t.Fatalf("failed to write %s: %v", path, err)
		}
	}

	return certPath, keyPath, caPath
}

func TestBuildTLSConfigSkipsDisabledTLS(t *testing.T) {
	cfg := &Config{TLSEnabled: "false"}

	tlsConfig, err := buildTLSConfig(cfg)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if tlsConfig != nil {
		t.Fatalf("expected nil TLS config when TLS disabled, got %#v", tlsConfig)
	}
}

func TestBuildTLSConfigBuildsMutualTLSConfig(t *testing.T) {
	certPath, keyPath, caPath := writeTestCertificateFiles(t)
	cfg := &Config{
		TLSEnabled:    "true",
		TLSHostname:   "nats.internal",
		TLSSkipVerify: "true",
		TLSCAFile:     caPath,
		TLSCertFile:   certPath,
		TLSKeyFile:    keyPath,
	}

	tlsConfig, err := buildTLSConfig(cfg)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if tlsConfig == nil {
		t.Fatal("expected TLS config")
	}
	if !tlsConfig.InsecureSkipVerify {
		t.Fatal("expected InsecureSkipVerify to be true")
	}
	if tlsConfig.ServerName != "nats.internal" {
		t.Fatalf("unexpected server name: %q", tlsConfig.ServerName)
	}
	if len(tlsConfig.Certificates) != 1 {
		t.Fatalf("expected one client certificate, got %d", len(tlsConfig.Certificates))
	}
	if tlsConfig.RootCAs == nil {
		t.Fatal("expected root CAs to be populated")
	}
}

func TestBuildTLSConfigRejectsInvalidCAFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "ca.pem")
	if err := os.WriteFile(path, []byte("not-a-cert"), 0o600); err != nil {
		t.Fatalf("failed to write invalid CA: %v", err)
	}

	_, err := buildTLSConfig(&Config{TLSEnabled: "true", TLSCAFile: path})
	if err == nil {
		t.Fatal("expected invalid CA to fail")
	}
}

func TestBuildTLSConfigRejectsMissingCertificatePair(t *testing.T) {
	_, err := buildTLSConfig(&Config{
		TLSEnabled:  "true",
		TLSCertFile: "/tmp/missing-cert.pem",
		TLSKeyFile:  "/tmp/missing-key.pem",
	})
	if err == nil {
		t.Fatal("expected missing client certificate files to fail")
	}
}

func TestBuildNATSOptionsAddsTLSOptionWhenEnabled(t *testing.T) {
	certPath, keyPath, caPath := writeTestCertificateFiles(t)
	cfg := &Config{
		NatsConnTimeout: 7,
		TLSEnabled:      "true",
		TLSHostname:     "nats.internal",
		TLSCAFile:       caPath,
		TLSCertFile:     certPath,
		TLSKeyFile:      keyPath,
	}

	opts, err := buildNATSOptions(cfg)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(opts) != 4 {
		t.Fatalf("expected 4 NATS options with TLS enabled, got %d", len(opts))
	}
}

func TestBuildNATSOptionsKeepsBaseOptionsWithoutTLS(t *testing.T) {
	opts, err := buildNATSOptions(&Config{NatsConnTimeout: 3, TLSEnabled: "false"})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(opts) != 3 {
		t.Fatalf("expected 3 base NATS options, got %d", len(opts))
	}
}

func TestRunHappyPathAndErrorScenarios(t *testing.T) {
	originalLoadConfig := loadConfigFn
	originalBuildNATSOptions := buildNATSOptionsFn
	originalConnectNATS := connectNATS
	originalCloseNATSConn := closeNATSConn
	originalRegisterSubscriptions := registerSubscriptionsFn
	defer func() {
		loadConfigFn = originalLoadConfig
		buildNATSOptionsFn = originalBuildNATSOptions
		connectNATS = originalConnectNATS
		closeNATSConn = originalCloseNATSConn
		registerSubscriptionsFn = originalRegisterSubscriptions
	}()

	t.Run("happy path version command prints version", func(t *testing.T) {
		var stdout bytes.Buffer
		if err := run([]string{"version"}, &stdout, func() { t.Fatal("wait should not be called") }); err != nil {
			t.Fatalf("expected no error, got %v", err)
		}
		if got := stdout.String(); got != version+"\n" {
			t.Fatalf("unexpected version output: %q", got)
		}
	})

	t.Run("corner case missing config path returns explicit error", func(t *testing.T) {
		err := run(nil, io.Discard, func() {})
		if err == nil || err.Error() != "please specify the config file path using --config" {
			t.Fatalf("unexpected error: %v", err)
		}
	})

	t.Run("corner case load config failure bubbles up", func(t *testing.T) {
		loadConfigFn = func(path string) (*Config, error) { return nil, errors.New("bad yaml") }
		err := run([]string{"--config", "/tmp/config.yaml"}, io.Discard, func() {})
		if err == nil || !strings.Contains(err.Error(), "failed to load config: bad yaml") {
			t.Fatalf("unexpected error: %v", err)
		}
	})

	t.Run("corner case build options failure bubbles up", func(t *testing.T) {
		loadConfigFn = func(path string) (*Config, error) { return &Config{NATSUrls: "nats://demo:4222"}, nil }
		buildNATSOptionsFn = func(cfg *Config) ([]nats.Option, error) { return nil, errors.New("bad tls") }
		err := run([]string{"--config", "/tmp/config.yaml"}, io.Discard, func() {})
		if err == nil || !strings.Contains(err.Error(), "failed to build NATS options: bad tls") {
			t.Fatalf("unexpected error: %v", err)
		}
	})

	t.Run("corner case connect failure bubbles up", func(t *testing.T) {
		loadConfigFn = func(path string) (*Config, error) { return &Config{NATSUrls: "nats://demo:4222"}, nil }
		buildNATSOptionsFn = func(cfg *Config) ([]nats.Option, error) { return []nats.Option{}, nil }
		connectNATS = func(url string, options ...nats.Option) (*nats.Conn, error) {
			return nil, errors.New("connect refused")
		}
		err := run([]string{"--config", "/tmp/config.yaml"}, io.Discard, func() {})
		if err == nil || !strings.Contains(err.Error(), "failed to connect to NATS server: connect refused") {
			t.Fatalf("unexpected error: %v", err)
		}
	})

	t.Run("happy path registers subscriptions and waits", func(t *testing.T) {
		loadConfigFn = func(path string) (*Config, error) {
			return &Config{NATSUrls: "nats://demo:4222", NATSInstanceID: "instance-1", TLSEnabled: "false"}, nil
		}
		buildNATSOptionsFn = func(cfg *Config) ([]nats.Option, error) { return []nats.Option{nats.Name("test")}, nil }
		connectNATS = func(url string, options ...nats.Option) (*nats.Conn, error) {
			if url != "nats://demo:4222" {
				t.Fatalf("unexpected url: %s", url)
			}
			return &nats.Conn{}, nil
		}

		var closed, waited bool
		closeNATSConn = func(nc *nats.Conn) { closed = true }
		registerSubscriptionsFn = func(nc *nats.Conn, instanceID string) {
			if nc == nil || instanceID != "instance-1" {
				t.Fatalf("unexpected registration inputs: nc=%#v instanceID=%q", nc, instanceID)
			}
		}

		if err := run([]string{"--config", "/tmp/config.yaml"}, io.Discard, func() { waited = true }); err != nil {
			t.Fatalf("expected no error, got %v", err)
		}
		if !closed || !waited {
			t.Fatalf("expected close and wait to run, closed=%v waited=%v", closed, waited)
		}
	})
}

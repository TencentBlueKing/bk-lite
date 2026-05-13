package main

import (
	"github.com/nats-io/nats.go"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRenderEnvVars(t *testing.T) {
	t.Setenv("NATS_HOST", "127.0.0.1")

	rendered := renderEnvVars("nats://${NATS_HOST}:4222")
	if rendered != "nats://127.0.0.1:4222" {
		t.Fatalf("unexpected rendered value: %s", rendered)
	}
}

func TestRenderEnvVarsSupportsShortForm(t *testing.T) {
	t.Setenv("NATS_HOST", "127.0.0.1")
	t.Setenv("NATS_PORT", "4222")

	rendered := renderEnvVars("nats://$NATS_HOST:$NATS_PORT")
	if rendered != "nats://127.0.0.1:4222" {
		t.Fatalf("unexpected rendered value: %s", rendered)
	}
}

func TestRenderEnvVarsKeepsMissingPlaceholder(t *testing.T) {
	rendered := renderEnvVars("nats://${MISSING_HOST}:4222")
	if rendered != "nats://${MISSING_HOST}:4222" {
		t.Fatalf("missing placeholder should be preserved, got: %s", rendered)
	}
}

func TestRenderEnvVarsKeepsMissingShortFormPlaceholder(t *testing.T) {
	rendered := renderEnvVars("nats://$MISSING_HOST:4222")
	if rendered != "nats://$MISSING_HOST:4222" {
		t.Fatalf("missing short-form placeholder should be preserved, got: %s", rendered)
	}
}

func TestLoadConfigRendersEnvVars(t *testing.T) {
	t.Setenv("TEST_NATS_URL", "nats://localhost:4222")

	configPath := filepath.Join(t.TempDir(), "config.yaml")
	config := []byte(strings.Join([]string{
		"nats_urls: ${TEST_NATS_URL}",
		"nats_instanceId: executor-1",
		"nats_conn_timeout: 5",
		"tls_enabled: true",
	}, "\n"))

	if err := os.WriteFile(configPath, config, 0o600); err != nil {
		t.Fatalf("failed to write config: %v", err)
	}

	cfg, err := loadConfig(configPath)
	if err != nil {
		t.Fatalf("loadConfig failed: %v", err)
	}

	if cfg.NATSUrls != "nats://localhost:4222" {
		t.Fatalf("unexpected nats url: %s", cfg.NATSUrls)
	}

	if cfg.NATSInstanceID != "executor-1" {
		t.Fatalf("unexpected instance id: %s", cfg.NATSInstanceID)
	}
}

func TestLoadConfigRendersEnvVarsForAllStringFields(t *testing.T) {
	t.Setenv("TEST_NATS_URL", "nats://tls-host:4222")
	t.Setenv("TEST_INSTANCE_ID", "executor-from-env")
	t.Setenv("TEST_TLS_ENABLED", "true")
	t.Setenv("TEST_TLS_HOSTNAME", "nats.internal")
	t.Setenv("TEST_TLS_CA", "/tmp/ca.pem")
	t.Setenv("TEST_TLS_CERT", "/tmp/client.pem")
	t.Setenv("TEST_TLS_KEY", "/tmp/client.key")
	t.Setenv("TEST_TLS_SKIP_VERIFY", "false")

	configPath := filepath.Join(t.TempDir(), "config.yaml")
	config := []byte(strings.Join([]string{
		"nats_urls: ${TEST_NATS_URL}",
		"nats_instanceId: ${TEST_INSTANCE_ID}",
		"nats_conn_timeout: 5",
		"tls_enabled: ${TEST_TLS_ENABLED}",
		"tls_hostname: ${TEST_TLS_HOSTNAME}",
		"tls_ca_file: ${TEST_TLS_CA}",
		"tls_cert_file: ${TEST_TLS_CERT}",
		"tls_key_file: ${TEST_TLS_KEY}",
		"tls_skip_verify: ${TEST_TLS_SKIP_VERIFY}",
	}, "\n"))

	if err := os.WriteFile(configPath, config, 0o600); err != nil {
		t.Fatalf("failed to write config: %v", err)
	}

	cfg, err := loadConfig(configPath)
	if err != nil {
		t.Fatalf("loadConfig failed: %v", err)
	}

	if cfg.NATSUrls != "nats://tls-host:4222" {
		t.Fatalf("unexpected nats url: %s", cfg.NATSUrls)
	}
	if cfg.NATSInstanceID != "executor-from-env" {
		t.Fatalf("unexpected instance id: %s", cfg.NATSInstanceID)
	}
	if cfg.TLSEnabled != "true" {
		t.Fatalf("unexpected tls_enabled: %s", cfg.TLSEnabled)
	}
	if cfg.TLSHostname != "nats.internal" {
		t.Fatalf("unexpected tls_hostname: %s", cfg.TLSHostname)
	}
	if cfg.TLSCAFile != "/tmp/ca.pem" {
		t.Fatalf("unexpected tls_ca_file: %s", cfg.TLSCAFile)
	}
	if cfg.TLSCertFile != "/tmp/client.pem" {
		t.Fatalf("unexpected tls_cert_file: %s", cfg.TLSCertFile)
	}
	if cfg.TLSKeyFile != "/tmp/client.key" {
		t.Fatalf("unexpected tls_key_file: %s", cfg.TLSKeyFile)
	}
	if cfg.TLSSkipVerify != "false" {
		t.Fatalf("unexpected tls_skip_verify: %s", cfg.TLSSkipVerify)
	}
}

func TestParseBool(t *testing.T) {
	tests := map[string]bool{
		"true":       true,
		"  YES ":     true,
		"1":          true,
		"on":         true,
		"false":      false,
		"":           false,
		"${SECRET}":  false,
		"{{SECRET}}": false,
	}

	for input, expected := range tests {
		if got := parseBool(input); got != expected {
			t.Fatalf("parseBool(%q) = %v, want %v", input, got, expected)
		}
	}
}

func TestParseString(t *testing.T) {
	if got := parseString("  example "); got != "example" {
		t.Fatalf("unexpected parsed string: %q", got)
	}

	if got := parseString("${SECRET}"); got != "" {
		t.Fatalf("placeholder should be cleared, got %q", got)
	}

	if got := parseString("{{SECRET}}"); got != "" {
		t.Fatalf("template placeholder should be cleared, got %q", got)
	}
}

func TestParseCLIArgsSupportsVersionSubcommand(t *testing.T) {
	configPath, showVersion, err := parseCLIArgs([]string{"version"})
	if err != nil {
		t.Fatalf("parseCLIArgs returned error: %v", err)
	}
	if !showVersion {
		t.Fatal("expected version subcommand to enable version mode")
	}
	if configPath != "" {
		t.Fatalf("unexpected config path: %q", configPath)
	}
}

func TestParseCLIArgsSupportsConfigFlag(t *testing.T) {
	configPath, showVersion, err := parseCLIArgs([]string{"--config", "/tmp/config.yaml"})
	if err != nil {
		t.Fatalf("parseCLIArgs returned error: %v", err)
	}
	if showVersion {
		t.Fatal("did not expect version mode for config startup")
	}
	if configPath != "/tmp/config.yaml" {
		t.Fatalf("unexpected config path: %q", configPath)
	}
}

func TestParseCLIArgsRejectsUnknownFlag(t *testing.T) {
	_, _, err := parseCLIArgs([]string{"--unknown"})
	if err == nil {
		t.Fatal("expected unknown flag to return error")
	}
}

func TestRegisterSubscriptionsRegistersAllHandlers(t *testing.T) {
	originalLocalExecutor := subscribeLocalExecutor
	originalDownloadToLocal := subscribeDownloadToLocal
	originalUnzipToLocal := subscribeUnzipToLocal
	originalHealthCheck := subscribeHealthCheck
	originalSSHExecutor := subscribeSSHExecutor
	originalDownloadToRemote := subscribeDownloadToRemote
	originalUploadToRemote := subscribeUploadToRemote
	defer func() {
		subscribeLocalExecutor = originalLocalExecutor
		subscribeDownloadToLocal = originalDownloadToLocal
		subscribeUnzipToLocal = originalUnzipToLocal
		subscribeHealthCheck = originalHealthCheck
		subscribeSSHExecutor = originalSSHExecutor
		subscribeDownloadToRemote = originalDownloadToRemote
		subscribeUploadToRemote = originalUploadToRemote
	}()

	var calls []string
	record := func(name string) func(*nats.Conn, *string) {
		return func(nc *nats.Conn, instanceID *string) {
			if nc != nil {
				t.Fatalf("%s should receive nil test connection, got %#v", name, nc)
			}
			if instanceID == nil || *instanceID != "instance-1" {
				t.Fatalf("%s received unexpected instance id: %#v", name, instanceID)
			}
			calls = append(calls, name)
		}
	}

	subscribeLocalExecutor = record("local.execute")
	subscribeDownloadToLocal = record("download.local")
	subscribeUnzipToLocal = record("unzip.local")
	subscribeHealthCheck = record("health.check")
	subscribeSSHExecutor = record("ssh.execute")
	subscribeDownloadToRemote = record("download.remote")
	subscribeUploadToRemote = record("upload.remote")

	registerSubscriptions(nil, "instance-1")

	expected := []string{
		"local.execute",
		"download.local",
		"unzip.local",
		"health.check",
		"ssh.execute",
		"download.remote",
		"upload.remote",
	}
	if len(calls) != len(expected) {
		t.Fatalf("registered %d handlers, want %d (%v)", len(calls), len(expected), calls)
	}
	for i, want := range expected {
		if calls[i] != want {
			t.Fatalf("handler %d = %q, want %q (all=%v)", i, calls[i], want, calls)
		}
	}
}

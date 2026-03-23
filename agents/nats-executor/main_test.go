package main

import (
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

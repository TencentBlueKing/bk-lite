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

func TestRenderEnvVarsKeepsMissingPlaceholder(t *testing.T) {
	rendered := renderEnvVars("nats://${MISSING_HOST}:4222")
	if rendered != "nats://${MISSING_HOST}:4222" {
		t.Fatalf("missing placeholder should be preserved, got: %s", rendered)
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

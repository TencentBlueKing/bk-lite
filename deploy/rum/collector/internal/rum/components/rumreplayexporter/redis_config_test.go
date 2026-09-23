package rumreplayexporter

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestRedisPasswordFileKeepsProductionSecretOutOfURL(t *testing.T) {
	secretPath := filepath.Join(t.TempDir(), "rum_redis_replay_exporter_password")
	secret := strings.Repeat("a", 48)
	require.NoError(t, os.WriteFile(secretPath, []byte(secret+"\n"), 0o600))

	cfg := defaultConfig()
	cfg.MinIOAccessKey = "access"
	cfg.MinIOSecretKey = "secret"
	cfg.RedisURL = "redis://rum-replay-exporter@rum-redis:6379"
	cfg.RedisPasswordFile = secretPath
	require.NoError(t, cfg.Validate())

	options, err := redisClientOptions(cfg)
	require.NoError(t, err)
	require.Equal(t, "rum-replay-exporter", options.Username)
	require.Equal(t, secret, options.Password)
	require.NotContains(t, cfg.RedisURL, secret)
}

func TestRedisConfigRejectsSharedOrLeakyAuthorities(t *testing.T) {
	for name, mutate := range map[string]func(*Config){
		"missing user":        func(cfg *Config) { cfg.RedisURL = "redis://rum-redis:6379" },
		"legacy broad user":   func(cfg *Config) { cfg.RedisURL = "redis://rum:" + strings.Repeat("b", 48) + "@rum-redis:6379" },
		"web user":            func(cfg *Config) { cfg.RedisURL = "redis://rum-web:" + strings.Repeat("b", 48) + "@rum-redis:6379" },
		"worker user":         func(cfg *Config) { cfg.RedisURL = "redis://rum-worker:" + strings.Repeat("b", 48) + "@rum-redis:6379" },
		"shared default user": func(cfg *Config) { cfg.RedisURL = "redis://redis:6379" },
		"passwordless dev":    func(cfg *Config) { cfg.RedisURL = "redis://rum-replay-exporter@rum-redis:6379" },
		"password plus file": func(cfg *Config) {
			cfg.RedisURL = "redis://rum-replay-exporter:" + strings.Repeat("b", 48) + "@rum-redis:6379"
			cfg.RedisPasswordFile = "/run/secrets/rum_redis_replay_exporter_password"
		},
		"relative file": func(cfg *Config) {
			cfg.RedisURL = "redis://rum-replay-exporter@rum-redis:6379"
			cfg.RedisPasswordFile = "secrets/rum_redis_replay_exporter_password"
		},
	} {
		t.Run(name, func(t *testing.T) {
			cfg := defaultConfig()
			cfg.MinIOAccessKey = "access"
			cfg.MinIOSecretKey = "secret"
			mutate(cfg)
			require.Error(t, cfg.Validate())
		})
	}
}

func TestRedisPasswordFileFailsClosed(t *testing.T) {
	cfg := defaultConfig()
	cfg.RedisURL = "redis://rum-replay-exporter@rum-redis:6379"
	cfg.RedisPasswordFile = filepath.Join(t.TempDir(), "missing")

	_, err := redisClientOptions(cfg)
	require.ErrorContains(t, err, "password file")

	secretPath := filepath.Join(t.TempDir(), "invalid")
	require.NoError(t, os.WriteFile(secretPath, []byte("too-short"), 0o600))
	cfg.RedisPasswordFile = secretPath
	_, err = redisClientOptions(cfg)
	require.ErrorContains(t, err, "32-256")

	leakyPath := filepath.Join(t.TempDir(), "leaky")
	require.NoError(t, os.WriteFile(leakyPath, []byte(strings.Repeat("x", 48)), 0o644))
	cfg.RedisPasswordFile = leakyPath
	_, err = redisClientOptions(cfg)
	require.ErrorContains(t, err, "0600")
}

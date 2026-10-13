package maintainer

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestMaintainerRedisAcceptsPasswordFileWithoutUsername(t *testing.T) {
	secretPath := writeRedisSecret(t, strings.Repeat("m", 32))
	options, err := maintainerRedisOptions(RedisConfig{
		URL:          "redis://rum-redis:6379",
		PasswordFile: secretPath,
	})
	require.NoError(t, err)
	require.Equal(t, "", options.Username)
	require.Equal(t, strings.Repeat("m", 32), options.Password)
}

func TestMaintainerRedisRejectsACLUsernameMismatch(t *testing.T) {
	secretPath := writeRedisSecret(t, strings.Repeat("m", 32))
	_, err := maintainerRedisOptions(RedisConfig{
		URL:                "redis://other@rum-redis:6379",
		PasswordFile:       secretPath,
		RequireACLIdentity: true,
	})
	require.ErrorContains(t, err, "ACL username must be rum-maintainer")

	options, err := maintainerRedisOptions(RedisConfig{
		URL:                "redis://shared-rum@rum-redis:6379",
		PasswordFile:       secretPath,
		RequireACLIdentity: true,
		ACLUsername:        "shared-rum",
	})
	require.NoError(t, err)
	require.Equal(t, "shared-rum", options.Username)
}

func TestReplayIndexRedisAcceptsPasswordWithoutUsername(t *testing.T) {
	store, err := NewRedisIndexStore(RedisIndexConfig{
		URL: "redis://:" + strings.Repeat("i", 32) + "@127.0.0.1:1",
	})
	require.NoError(t, err)
	require.NoError(t, store.Close())
}

func TestReplayIndexRedisRejectsACLUsernameMismatch(t *testing.T) {
	_, err := NewRedisIndexStore(RedisIndexConfig{
		URL:                "redis://other:" + strings.Repeat("i", 32) + "@127.0.0.1:1",
		RequireACLIdentity: true,
	})
	require.ErrorContains(t, err, "ACL username must be rum-replay-index-maintainer")

	store, err := NewRedisIndexStore(RedisIndexConfig{
		URL:                "redis://shared-rum:" + strings.Repeat("i", 32) + "@127.0.0.1:1",
		RequireACLIdentity: true,
		ACLUsername:        "shared-rum",
	})
	require.NoError(t, err)
	require.NoError(t, store.Close())
}

func writeRedisSecret(t *testing.T, secret string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "redis-password")
	require.NoError(t, os.WriteFile(path, []byte(secret+"\n"), 0o600))
	return path
}

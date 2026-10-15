package rumsessionprocessor

import (
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/stretchr/testify/require"
)

func TestAssignSucceedsOnMiniRedisWithoutAOF(t *testing.T) {
	server := miniredis.RunT(t)
	password := strings.Repeat("p", 32)
	server.RequireAuth(password)
	cfg := defaultConfig()
	cfg.RedisURL = "redis://:" + password + "@" + server.Addr()
	require.NoError(t, cfg.Validate())

	store, err := newRedisSessionStore(cfg)
	require.NoError(t, err)
	t.Cleanup(func() { _ = store.shutdown(t.Context()) })

	assigned, err := store.assign(t.Context(), assignment{
		StateKey:     "ops:rum:v2:session:test",
		ObservedAt:   time.Date(2026, 10, 12, 0, 0, 0, 0, time.UTC),
		CandidateKey: "0123456789abcdef0123456789abcdef",
		TrafficClass: "human",
	})
	require.NoError(t, err)
	require.Equal(t, "0123456789abcdef0123456789abcdef", assigned.SessionKey)
	require.Equal(t, "human", assigned.TrafficClass)
	require.True(t, assigned.Rolled)
}

func TestRedisURLAcceptsPasswordWithoutUsername(t *testing.T) {
	cfg := defaultConfig()
	cfg.RedisURL = "redis://:" + strings.Repeat("a", 32) + "@rum-redis:6379"
	require.NoError(t, cfg.Validate())
}

func TestRedisACLUsernameMismatchIsRejectedWhenRequired(t *testing.T) {
	cfg := defaultConfig()
	cfg.RedisRequireACLIdentity = true
	cfg.RedisURL = "redis://other:" + strings.Repeat("a", 32) + "@rum-redis:6379"
	require.ErrorContains(t, cfg.Validate(), "ACL username must be rum-sessionizer")

	cfg.RedisACLUsername = "shared-rum"
	cfg.RedisURL = "redis://shared-rum:" + strings.Repeat("a", 32) + "@rum-redis:6379"
	require.NoError(t, cfg.Validate())
}

package maintainer

import (
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"

	rumstate "github.com/bk-lite/rum-collector/internal/rum/state"
)

func TestRedisStateCompleteAndAcknowledge(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	state := &RedisState{client: client, consumer: "maintainer-test", now: time.Now}
	require.NoError(t, state.Start(t.Context()))

	messageID, err := client.XAdd(t.Context(), &redis.XAddArgs{
		Stream: rumstate.ErasureStreamKey,
		Values: map[string]any{
			"operation_id": "op-complete",
			"application":  "storefront",
			"actor":        "test",
			"identities":   "[]",
		},
	}).Result()
	require.NoError(t, err)
	_, err = client.XReadGroup(t.Context(), &redis.XReadGroupArgs{
		Group:    maintainerGroup,
		Consumer: state.consumer,
		Streams:  []string{rumstate.ErasureStreamKey, ">"},
		Count:    1,
		Block:    -1,
	}).Result()
	require.NoError(t, err)

	require.NoError(t, state.Complete(t.Context(), "op-complete"))
	require.NoError(t, state.acknowledge(t.Context(), rumstate.ErasureStreamKey, messageID))
	pending, err := client.XPending(t.Context(), rumstate.ErasureStreamKey, maintainerGroup).Result()
	require.NoError(t, err)
	require.Equal(t, int64(0), pending.Count)
}

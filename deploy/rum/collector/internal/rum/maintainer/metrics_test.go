package maintainer

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	rumstate "github.com/bk-lite/rum-collector/internal/rum/state"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func TestOperationalMetricsExposeReplayErasureAndReconciliationHealth(t *testing.T) {
	now := time.Date(2026, 8, 5, 10, 0, 0, 0, time.UTC)
	operations := &fakeOperationHealth{overdue: 2}
	replay := &fakeReplayHealth{
		pending:   3,
		lastRun:   now.Add(-time.Minute),
		conflicts: 1,
	}
	metrics := NewOperationalMetrics(operations, replay)
	metrics.now = func() time.Time { return now }

	require.NoError(t, metrics.refresh(t.Context()))
	require.Equal(t, float64(3), testutil.ToFloat64(metrics.pendingReplay))
	require.Equal(t, float64(2), testutil.ToFloat64(metrics.overdueErasures))
	require.Equal(t, float64(1), testutil.ToFloat64(metrics.recentConflicts))
	require.Equal(t, float64(replay.lastRun.Unix()), testutil.ToFloat64(metrics.lastReconcileTime))
	require.Equal(t, now.Add(-2*time.Minute), replay.pendingBefore)
	require.Equal(t, now.Add(-30*time.Minute), operations.before)
	require.Equal(t, now.Add(-10*time.Minute), replay.conflictsSince)
}

func TestOperationalMetricsDoNotOverwriteLastGoodValueOnBackendFailure(t *testing.T) {
	operations := &fakeOperationHealth{overdue: 2}
	replay := &fakeReplayHealth{pending: 3, err: errors.New("ClickHouse unavailable")}
	metrics := NewOperationalMetrics(operations, replay)
	metrics.pendingReplay.Set(9)

	require.Error(t, metrics.refresh(t.Context()))
	require.Equal(t, float64(9), testutil.ToFloat64(metrics.pendingReplay))
	require.Equal(t, float64(2), testutil.ToFloat64(metrics.overdueErasures))
}

func TestCountOverdueErasuresSkipsOperationStreamsAndCursors(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	state := &RedisState{client: client, now: time.Now}
	now := time.Date(2026, 8, 5, 10, 0, 0, 0, time.UTC)
	require.NoError(t, client.XAdd(t.Context(), &redis.XAddArgs{
		Stream: rumstate.ReconcileStreamKey,
		Values: map[string]any{"operation_id": "op-stream"},
	}).Err())
	require.NoError(t, client.HSet(
		t.Context(),
		replayCursorKeyPrefix+"storefront",
		"accepted_at_unix_nano",
		"123",
		"segment_id",
		"segment-a",
	).Err())
	for operationID, values := range map[string]map[string]any{
		"op-overdue": {
			"operation_id": "op-overdue",
			"type":         "erasure",
			"status":       "pending",
			"created_at":   now.Add(-31 * time.Minute).Format(time.RFC3339Nano),
		},
		"op-young": {
			"operation_id": "op-young",
			"type":         "erasure",
			"status":       "pending",
			"created_at":   now.Add(-29 * time.Minute).Format(time.RFC3339Nano),
		},
		"op-complete": {
			"operation_id": "op-complete",
			"type":         "erasure",
			"status":       "completed",
			"created_at":   now.Add(-time.Hour).Format(time.RFC3339Nano),
		},
	} {
		require.NoError(t, client.HSet(
			t.Context(),
			rumstate.OperationKeyPrefix+operationID,
			values,
		).Err())
	}

	count, err := state.CountOverdueErasures(t.Context(), now.Add(-30*time.Minute))
	require.NoError(t, err)
	require.Equal(t, int64(1), count)
}

type fakeOperationHealth struct {
	overdue int64
	before  time.Time
	err     error
}

func (health *fakeOperationHealth) CountOverdueErasures(
	_ context.Context,
	before time.Time,
) (int64, error) {
	health.before = before
	return health.overdue, health.err
}

type fakeReplayHealth struct {
	pending        int64
	lastRun        time.Time
	conflicts      uint64
	pendingBefore  time.Time
	conflictsSince time.Time
	err            error
}

func (health *fakeReplayHealth) CountReplayPending(
	_ context.Context,
	before time.Time,
) (int64, error) {
	health.pendingBefore = before
	return health.pending, health.err
}

func (health *fakeReplayHealth) ReconciliationHealth(
	_ context.Context,
	since time.Time,
) (time.Time, uint64, error) {
	health.conflictsSince = since
	return health.lastRun, health.conflicts, health.err
}

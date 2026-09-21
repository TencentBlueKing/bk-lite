package rumgate

import (
	"strconv"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.uber.org/zap"
)

func TestApplicationsFromLogsReadsRecordAttribute(t *testing.T) {
	logs := plog.NewLogs()
	resource := logs.ResourceLogs().AppendEmpty()
	resource.Resource().Attributes().PutStr("tenant.id", "core")
	record := resource.ScopeLogs().AppendEmpty().LogRecords().AppendEmpty()
	record.Attributes().PutStr("rum.application", "storefront")
	second := resource.ScopeLogs().AppendEmpty().LogRecords().AppendEmpty()
	second.Attributes().PutStr("rum.application", "storefront")
	third := resource.ScopeLogs().AppendEmpty().LogRecords().AppendEmpty()
	third.Attributes().PutStr("rum.application", "checkout")

	require.Equal(t, []string{"checkout", "storefront"}, applicationsFromLogs(logs))
}

func TestApplicationsFromTracesReadsResourceAttribute(t *testing.T) {
	traces := ptrace.NewTraces()
	resource := traces.ResourceSpans().AppendEmpty()
	resource.Resource().Attributes().PutStr("rum.application", "storefront")
	other := traces.ResourceSpans().AppendEmpty()
	other.Resource().Attributes().PutStr("rum.application", "")

	require.Equal(t, []string{"storefront"}, applicationsFromTraces(traces))
}

func TestStoredMarkerRecordsLastStoredAt(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	now := time.Date(2026, 8, 6, 12, 0, 0, 0, time.UTC)
	require.NoError(t, client.HSet(t.Context(), "ops:rum:v2:app:storefront", "revision", "1").Err())
	require.NoError(t, client.HSet(t.Context(), "ops:rum:v2:app:checkout", "revision", "1").Err())

	marker := &redisStoredMarker{client: client, now: func() time.Time { return now }, logger: zap.NewNop()}
	marker.Record(t.Context(), []string{"storefront", "checkout"})

	expected := strconv.FormatInt(now.Unix(), 10)
	require.Equal(t, expected, server.HGet("ops:rum:v2:app:storefront", "last_stored_at"))
	require.Equal(t, expected, server.HGet("ops:rum:v2:app:checkout", "last_stored_at"))
}

func TestStoredMarkerDoesNotCreateUnregisteredAppHash(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	marker := &redisStoredMarker{client: client, now: time.Now, logger: zap.NewNop()}
	marker.Record(t.Context(), []string{"local-demo"})

	require.False(t, server.Exists("ops:rum:v2:app:local-demo"))
}

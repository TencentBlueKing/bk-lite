package rumroutecap

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/processor"
	"go.opentelemetry.io/collector/processor/processortest"
	"go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

func TestHundredthRouteStaysItselfAndTheNextIsOther(t *testing.T) {
	redisURL, server := startRedis(t)
	sink := &captureLogs{}
	proc, _ := startProcessor(t, redisURL, "shard-a", sink)

	for index := 0; index < maxRoutesPerApplication; index++ {
		route := routeName(index)
		original := oneEvent("core", "storefront", route, "view")
		before := cloneLogs(original)
		require.NoError(t, proc.ConsumeLogs(t.Context(), original))
		requireLogsEqual(t, before, original)
		require.Equal(t, route, capturedRoute(t, sink))
	}

	overflow := oneEvent("core", "storefront", "/overflow", "view")
	before := cloneLogs(overflow)
	require.NoError(t, proc.ConsumeLogs(t.Context(), overflow))
	requireLogsEqual(t, before, overflow)
	require.Equal(t, otherRoute, capturedRoute(t, sink))
	require.Equal(t, "/r-0", capturedRouteAt(t, sink, 0))
	require.NotContains(t, attributeDump(sink.latest()), "user-secret")
	require.NotContains(t, attributeDump(sink.latest()), "token=secret")

	client := redisClient(t, server)
	keys, err := client.Keys(t.Context(), "ops:rum:v2:aggregate:routes:*").Result()
	require.NoError(t, err)
	require.Len(t, keys, 1)
	require.Equal(t, int64(maxRoutesPerApplication), client.SCard(t.Context(), keys[0]).Val())
	ttl := client.PTTL(t.Context(), keys[0]).Val()
	require.Greater(t, ttl, admissionTTL-time.Minute)
	require.LessOrEqual(t, ttl, admissionTTL)

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "billing", "/only", "view")))
	require.Equal(t, "/only", capturedRoute(t, sink))
	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("other-tenant", "storefront", "/only", "view")))
	require.Equal(t, "/only", capturedRoute(t, sink))
}

func TestTwoProcessorsSharingRedisAdmitTheSameRoutes(t *testing.T) {
	redisURL, _ := startRedis(t)
	firstSink := &captureLogs{}
	secondSink := &captureLogs{}
	first, _ := startProcessor(t, redisURL, "shard-a", firstSink)
	second, _ := startProcessor(t, redisURL, "shard-b", secondSink)

	require.NoError(t, first.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/checkout", "view")))
	require.NoError(t, second.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/checkout", "view")))
	require.Equal(t, "/checkout", capturedRoute(t, firstSink))
	require.Equal(t, "/checkout", capturedRoute(t, secondSink))

	for index := 1; index < maxRoutesPerApplication; index++ {
		require.NoError(t, first.ConsumeLogs(t.Context(), oneEvent("core", "storefront", routeName(index), "view")))
	}
	overflow := oneEvent("core", "storefront", "/overflow", "view")
	require.NoError(t, first.ConsumeLogs(t.Context(), overflow))
	require.NoError(t, second.ConsumeLogs(t.Context(), overflow))
	require.Equal(t, otherRoute, capturedRoute(t, firstSink))
	require.Equal(t, otherRoute, capturedRoute(t, secondSink))

	freshSink := &captureLogs{}
	fresh, _ := startProcessor(t, redisURL, "shard-a", freshSink)
	require.NoError(t, fresh.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/checkout", "view")))
	require.Equal(t, "/checkout", capturedRoute(t, freshSink))
	require.NoError(t, fresh.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/overflow", "view")))
	require.Equal(t, otherRoute, capturedRoute(t, freshSink))
}

func TestConcurrentProcessorsNeverAdmitMoreThanOneHundred(t *testing.T) {
	redisURL, server := startRedis(t)
	first, _ := startProcessor(t, redisURL, "shard-a", &captureLogs{})
	second, _ := startProcessor(t, redisURL, "shard-b", &captureLogs{})
	var group sync.WaitGroup
	errs := make(chan error, 160)
	for index := 0; index < 80; index++ {
		route := routeName(index)
		group.Add(2)
		go func() {
			defer group.Done()
			errs <- first.ConsumeLogs(t.Context(), oneEvent("core", "storefront", route, "view"))
		}()
		go func() {
			defer group.Done()
			errs <- second.ConsumeLogs(t.Context(), oneEvent("core", "storefront", route, "error"))
		}()
	}
	group.Wait()
	close(errs)
	for err := range errs {
		require.NoError(t, err)
	}

	client := redisClient(t, server)
	keys, err := client.Keys(t.Context(), "ops:rum:v2:aggregate:routes:*").Result()
	require.NoError(t, err)
	require.Len(t, keys, 1)
	require.LessOrEqual(t, client.SCard(t.Context(), keys[0]).Val(), int64(maxRoutesPerApplication))

	probeSink := &captureLogs{}
	probe, _ := startProcessor(t, redisURL, "shard-c", probeSink)
	admitted := 0
	for index := 0; index < 80; index++ {
		require.NoError(t, probe.ConsumeLogs(t.Context(), oneEvent("core", "storefront", routeName(index), "view")))
		if capturedRoute(t, probeSink) != otherRoute {
			admitted++
		}
	}
	require.LessOrEqual(t, admitted, maxRoutesPerApplication)
	require.Equal(t, int64(admitted), client.SCard(t.Context(), keys[0]).Val())
}

func TestRedisOutageLabelsUnknownRoutesOtherAndCounts(t *testing.T) {
	redisURL, server := startRedis(t)
	sink := &captureLogs{}
	proc, reader := startProcessor(t, redisURL, "shard-a", sink)
	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/checkout", "view")))
	require.Equal(t, "/checkout", capturedRoute(t, sink))

	server.Close()
	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/checkout", "view")))
	require.Equal(t, "/checkout", capturedRoute(t, sink))
	require.Equal(t, int64(0), failureCount(t, reader))

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/new", "error")))
	require.Equal(t, otherRoute, capturedRoute(t, sink))
	require.Equal(t, int64(1), failureCount(t, reader))

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/new", "vital")))
	require.Equal(t, otherRoute, capturedRoute(t, sink))
	require.Equal(t, int64(2), failureCount(t, reader))
}

func TestProcessorStartsWhenRedisIsDownAndDoesNotFailTheCaller(t *testing.T) {
	redisURL, server := startRedis(t)
	server.Close()
	sink := &captureLogs{err: errors.New("remote write unavailable")}
	proc, reader := startProcessor(t, redisURL, "shard-a", sink)
	original := oneEvent("core", "storefront", "/checkout", "view")
	require.NoError(t, proc.ConsumeLogs(t.Context(), original))
	require.Equal(t, otherRoute, capturedRoute(t, sink))
	require.GreaterOrEqual(t, failureCount(t, reader), int64(1))
	_, hasRoute := original.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().Get(aggregateRouteAttribute)
	require.False(t, hasRoute)
	_, hasService := original.ResourceLogs().At(0).Resource().Attributes().Get("service.name")
	require.False(t, hasService)
}

func TestCustomEventsDoNotConsumeRouteSlots(t *testing.T) {
	redisURL, server := startRedis(t)
	proc, _ := startProcessor(t, redisURL, "shard-a", &captureLogs{})
	for index := 0; index < maxRoutesPerApplication+5; index++ {
		require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", routeName(index), "console")))
	}
	client := redisClient(t, server)
	keys, err := client.Keys(t.Context(), "ops:rum:v2:aggregate:routes:*").Result()
	require.NoError(t, err)
	require.Empty(t, keys)

	sink := &captureLogs{}
	views, _ := startProcessor(t, redisURL, "shard-a", sink)
	require.NoError(t, views.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/checkout", "view")))
	require.Equal(t, "/checkout", capturedRoute(t, sink))
	_, hasService := sink.latest().ResourceLogs().At(0).Resource().Attributes().Get("service.name")
	require.False(t, hasService)
}

func TestBlankRouteUsesUnknownAndShardIsRequired(t *testing.T) {
	redisURL, _ := startRedis(t)
	sink := &captureLogs{}
	proc, _ := startProcessor(t, redisURL, "shard-a", sink)
	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "", "view")))
	require.Equal(t, unknownRoute, capturedRoute(t, sink))

	factory := NewFactory()
	cfg := factory.CreateDefaultConfig().(*Config)
	cfg.RedisURL = redisURL
	require.ErrorContains(t, cfg.Validate(), "shard")
	cfg.Shard = "bad shard"
	require.ErrorContains(t, cfg.Validate(), "shard")
}

func TestPasswordFileIsAcceptedAndEmbeddedPasswordIsRejectedWithIt(t *testing.T) {
	secretPath := filepath.Join(t.TempDir(), "rum_sessionizer_redis_password")
	require.NoError(t, os.WriteFile(secretPath, []byte(redisPassword()+"\n"), 0o600))
	cfg := defaultConfig()
	cfg.RedisURL = "redis://rum-redis:6379/1"
	cfg.RedisPasswordFile = secretPath
	cfg.Shard = "shard-a"
	store, err := newRouteStore(cfg)
	require.NoError(t, err)
	require.NoError(t, store.close())

	cfg.RedisURL = "redis://:" + redisPassword() + "@rum-redis:6379/1"
	require.ErrorContains(t, cfg.Validate(), "must not embed a password")
}

type captureLogs struct {
	mu  sync.Mutex
	got []plog.Logs
	err error
}

func (capture *captureLogs) Capabilities() consumer.Capabilities {
	return consumer.Capabilities{MutatesData: true}
}

func (capture *captureLogs) ConsumeLogs(_ context.Context, ld plog.Logs) error {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	capture.got = append(capture.got, cloneLogs(ld))
	return capture.err
}

func (capture *captureLogs) latest() plog.Logs {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	return capture.got[len(capture.got)-1]
}

func startRedis(t *testing.T) (string, *miniredis.Miniredis) {
	t.Helper()
	server := miniredis.RunT(t)
	server.RequireAuth(redisPassword())
	return "redis://:" + redisPassword() + "@" + server.Addr() + "/0", server
}

func redisPassword() string {
	return strings.Repeat("p", 32)
}

func redisClient(t *testing.T, server *miniredis.Miniredis) *redis.Client {
	t.Helper()
	client := redis.NewClient(&redis.Options{Addr: server.Addr(), Password: redisPassword()})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func startProcessor(t *testing.T, redisURL, shard string, next consumer.Logs) (processor.Logs, *metric.ManualReader) {
	t.Helper()
	reader := metric.NewManualReader()
	provider := metric.NewMeterProvider(metric.WithReader(reader))
	factory := NewFactory()
	cfg := factory.CreateDefaultConfig().(*Config)
	cfg.RedisURL = redisURL
	cfg.Shard = shard
	set := processortest.NewNopSettings(factory.Type())
	set.MeterProvider = provider
	created, err := factory.CreateLogs(t.Context(), set, cfg, next)
	require.NoError(t, err)
	require.NoError(t, created.Start(t.Context(), nil))
	t.Cleanup(func() {
		require.NoError(t, created.Shutdown(context.Background()))
	})
	return created, reader
}

func oneEvent(tenant, application, route, eventType string) plog.Logs {
	logs := plog.NewLogs()
	resource := logs.ResourceLogs().AppendEmpty()
	resourceAttrs := resource.Resource().Attributes()
	resourceAttrs.PutStr("tenant.id", tenant)
	resourceAttrs.PutStr("rum.traffic.class", "human")
	resourceAttrs.PutStr("user_agent.original", "Mozilla/5.0")
	record := resource.ScopeLogs().AppendEmpty().LogRecords().AppendEmpty()
	attrs := record.Attributes()
	attrs.PutStr("rum.application", application)
	attrs.PutStr("rum.environment", "production")
	if route != "" {
		attrs.PutStr("rum.view.name", route)
	}
	attrs.PutStr("rum.event.type", eventType)
	attrs.PutStr("rum.user.id", "user-secret")
	attrs.PutStr("rum.page.url", "https://shop.example/pay?token=secret")
	return logs
}

func cloneLogs(logs plog.Logs) plog.Logs {
	cloned := plog.NewLogs()
	logs.CopyTo(cloned)
	return cloned
}

func capturedRoute(t *testing.T, sink *captureLogs) string {
	t.Helper()
	return capturedRouteAt(t, sink, -1)
}

func capturedRouteAt(t *testing.T, sink *captureLogs, index int) string {
	t.Helper()
	sink.mu.Lock()
	defer sink.mu.Unlock()
	require.NotEmpty(t, sink.got)
	if index < 0 {
		index = len(sink.got) - 1
	}
	value, ok := sink.got[index].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().Get(aggregateRouteAttribute)
	require.True(t, ok)
	return value.Str()
}

func attributeDump(logs plog.Logs) string {
	raw := logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().AsRaw()
	return fmt.Sprint(raw["rum.aggregate.route"])
}

func requireLogsEqual(t *testing.T, want, got plog.Logs) {
	t.Helper()
	require.Equal(t, want.ResourceLogs().At(0).Resource().Attributes().AsRaw(), got.ResourceLogs().At(0).Resource().Attributes().AsRaw())
	require.Equal(t,
		want.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().AsRaw(),
		got.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().AsRaw(),
	)
}

func failureCount(t *testing.T, reader *metric.ManualReader) int64 {
	t.Helper()
	var collected metricdata.ResourceMetrics
	require.NoError(t, reader.Collect(t.Context(), &collected))
	var total int64
	for _, scope := range collected.ScopeMetrics {
		for _, item := range scope.Metrics {
			if item.Name != failureInstrument {
				continue
			}
			sum, ok := item.Data.(metricdata.Sum[int64])
			require.True(t, ok)
			for _, point := range sum.DataPoints {
				total += point.Value
			}
		}
	}
	return total
}

func routeName(index int) string {
	return fmt.Sprintf("/r-%d", index)
}

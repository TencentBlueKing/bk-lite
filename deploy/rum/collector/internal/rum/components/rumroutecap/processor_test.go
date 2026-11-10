package rumroutecap

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
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
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"go.uber.org/zap/zaptest/observer"
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

func TestRedisOutageOpensCircuitAndResumes(t *testing.T) {
	redisURL, server := startRedis(t)
	logger, recorded, formatted := warnLogger()
	sink := &captureLogs{}
	proc, reader := startProcessorWithLogger(t, redisURL, "shard-a", sink, logger)
	concrete := proc.(*logsProcessor)
	counter := &countingAdmittor{inner: concrete.store}
	concrete.store = counter
	clock := useClock(t, time.Unix(1_700_000_000, 0))
	const connectionSentinel = "redis://:super-secret-password@10.1.2.3:6379/0"
	server.SetError("LOADING " + connectionSentinel)

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "route-secret-sentinel", "view")))
	require.Equal(t, otherRoute, capturedRoute(t, sink))
	require.Equal(t, 1, counter.callCount())

	require.Len(t, recorded.All(), 1)
	require.Equal(t, int64(1), fieldInt(t, recorded.All()[0], "failure_count"))

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/second", "error")))
	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/third", "vital")))
	require.Equal(t, otherRoute, capturedRoute(t, sink))
	require.Equal(t, 1, counter.callCount())
	require.Equal(t, int64(3), failureCount(t, reader))
	require.Len(t, recorded.All(), 1)

	*clock = clock.Add(redisCircuitOpenFor)
	server.SetError("")
	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/after", "view")))
	require.Equal(t, 2, counter.callCount())
	require.Equal(t, "/after", capturedRoute(t, sink))
	require.Equal(t, int64(3), failureCount(t, reader))
	entries := recorded.All()
	require.Len(t, entries, 2)
	require.Equal(t, "rum aggregate route redis lookup failed", entries[0].Message)
	require.Equal(t, "route_admission", fieldString(t, entries[0], "failed_stage"))
	require.NotEmpty(t, fieldString(t, entries[0], "error_type"))
	require.Equal(t, int64(1), fieldInt(t, entries[0], "failure_count"))
	require.Equal(t, "route_admission", fieldString(t, entries[1], "failed_stage"))
	require.NotEmpty(t, fieldString(t, entries[1], "error_type"))
	require.Equal(t, int64(2), fieldInt(t, entries[1], "failure_count"))
	blob := logBlob(entries[0]) + logBlob(entries[1]) + formatted.String()
	require.Contains(t, formatted.String(), `"failed_stage":"route_admission"`)
	require.Contains(t, formatted.String(), `"failure_count":1`)
	require.Contains(t, formatted.String(), `"failure_count":2`)
	require.NotContains(t, formatted.String(), "stacktrace")
	for _, secret := range []string{
		connectionSentinel,
		"super-secret-password",
		"10.1.2.3",
		server.Addr(),
		redisPassword(),
		"route-secret-sentinel",
		"/second",
		"/third",
		"/after",
		"user-secret",
		"token=secret",
	} {
		require.NotContains(t, blob, secret)
	}
}

func TestRedisFailureLogRollsUpOneWarnPerWindow(t *testing.T) {
	redisURL, _ := startRedis(t)
	logger, recorded, formatted := warnLogger()
	sink := &captureLogs{}
	proc, _ := startProcessorWithLogger(t, redisURL, "shard-a", sink, logger)
	concrete := proc.(*logsProcessor)
	admit := true
	concrete.store = admitFunc(func(context.Context, string, string, string) (bool, error) {
		if admit {
			return true, nil
		}
		return false, errors.New("dial redis://:super-secret-password@10.1.2.3:6379/0 route-secret-sentinel")
	})
	clock := useClock(t, time.Unix(1_710_000_000, 0))
	admit = false

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "route-secret-sentinel", "view")))
	require.Len(t, recorded.All(), 1)
	require.Equal(t, "route_admission", fieldString(t, recorded.All()[0], "failed_stage"))
	require.NotEmpty(t, fieldString(t, recorded.All()[0], "error_type"))
	require.Equal(t, int64(1), fieldInt(t, recorded.All()[0], "failure_count"))

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/second", "error")))
	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/third", "vital")))
	require.Len(t, recorded.All(), 1)

	*clock = clock.Add(failureLogWindow)
	admit = true
	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/after", "view")))
	require.Equal(t, "/after", capturedRoute(t, sink))
	entries := recorded.All()
	require.Len(t, entries, 2)
	require.Equal(t, "route_admission", fieldString(t, entries[1], "failed_stage"))
	require.NotEmpty(t, fieldString(t, entries[1], "error_type"))
	require.Equal(t, int64(2), fieldInt(t, entries[1], "failure_count"))
	blob := logBlob(entries[0]) + logBlob(entries[1]) + formatted.String()
	require.Contains(t, formatted.String(), `"failed_stage":"route_admission"`)
	require.Contains(t, formatted.String(), `"failure_count":1`)
	require.Contains(t, formatted.String(), `"failure_count":2`)
	require.NotContains(t, formatted.String(), "stacktrace")
	require.NotContains(t, blob, "super-secret-password")
	require.NotContains(t, blob, "10.1.2.3")
	require.NotContains(t, blob, "redis://")
	require.NotContains(t, blob, "route-secret-sentinel")
	require.NotContains(t, blob, "/second")
	require.NotContains(t, blob, "/third")
	require.NotContains(t, blob, "/after")
	require.NotContains(t, blob, "user-secret")
	require.NotContains(t, blob, "token=secret")
}

func TestRedisFailureLogFlushesRemainderOnShutdown(t *testing.T) {
	redisURL, _ := startRedis(t)
	logger, recorded, _ := warnLogger()
	proc, _ := startProcessorWithLogger(t, redisURL, "shard-a", &captureLogs{}, logger)
	concrete := proc.(*logsProcessor)
	concrete.store = admitFunc(func(context.Context, string, string, string) (bool, error) {
		return false, errors.New("redis unavailable")
	})
	useClock(t, time.Unix(1_720_000_000, 0))

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/one", "view")))
	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/two", "view")))
	require.Len(t, recorded.All(), 1)
	require.Equal(t, int64(1), fieldInt(t, recorded.All()[0], "failure_count"))

	concrete.flushFailure()
	require.Len(t, recorded.All(), 2)
	require.Equal(t, int64(1), fieldInt(t, recorded.All()[1], "failure_count"))
	concrete.flushFailure()
	require.Len(t, recorded.All(), 2)
}

func TestOverflowCacheStaysWithinLimitAndDropsExpiredEntries(t *testing.T) {
	cache := newRouteCache()
	start := time.Unix(1_800_000_000, 0)
	clock := useClock(t, start)
	for index := 0; index < overflowCacheLimit; index++ {
		cache.rememberOverflow(fmt.Sprintf("kept-%d", index))
	}
	cache.rememberOverflow("extra")
	cache.mu.Lock()
	require.Len(t, cache.overflow, overflowCacheLimit)
	_, ok := cache.overflow["extra"]
	require.False(t, ok)
	_, ok = cache.overflow["kept-0"]
	require.True(t, ok)
	for key := range cache.overflow {
		cache.overflow[key] = start.Add(-time.Second)
	}
	cache.mu.Unlock()

	cache.rememberOverflow("after-expiry")
	cache.mu.Lock()
	require.LessOrEqual(t, len(cache.overflow), overflowCacheLimit)
	_, ok = cache.overflow["after-expiry"]
	require.True(t, ok)
	cache.mu.Unlock()

	cache.rememberOverflow("stale")
	cache.maintain(*clock)
	cache.mu.Lock()
	cache.overflow["stale"] = start.Add(-time.Second)
	cache.mu.Unlock()
	cache.maintain(start.Add(time.Second))
	cache.mu.Lock()
	_, ok = cache.overflow["stale"]
	require.True(t, ok)
	cache.mu.Unlock()

	*clock = start.Add(overflowSweepInterval)
	cache.maintain(*clock)
	cache.mu.Lock()
	_, ok = cache.overflow["stale"]
	require.False(t, ok)
	cache.mu.Unlock()
}

func TestLaterRouteSweepsExpiredOverflowWithoutRepeatingIt(t *testing.T) {
	redisURL, _ := startRedis(t)
	sink := &captureLogs{}
	proc, _ := startProcessor(t, redisURL, "shard-a", sink)
	concrete := proc.(*logsProcessor)
	clock := useClock(t, time.Unix(1_900_000_000, 0))
	concrete.cache.mu.Lock()
	concrete.cache.overflow["stale-route"] = clock.Add(-time.Second)
	concrete.cache.lastSweep = clock.Add(-overflowSweepInterval)
	concrete.cache.mu.Unlock()

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/fresh", "view")))
	require.Equal(t, "/fresh", capturedRoute(t, sink))
	concrete.cache.mu.Lock()
	_, ok := concrete.cache.overflow["stale-route"]
	concrete.cache.mu.Unlock()
	require.False(t, ok)
}

func TestFullOverflowCacheStillLabelsTheNewRouteOther(t *testing.T) {
	redisURL, server := startRedis(t)
	sink := &captureLogs{}
	proc, _ := startProcessor(t, redisURL, "shard-a", sink)
	concrete := proc.(*logsProcessor)
	useClock(t, time.Unix(1_910_000_000, 0))
	for index := 0; index < overflowCacheLimit; index++ {
		concrete.cache.rememberOverflow(fmt.Sprintf("seed-%d", index))
	}
	key := admissionKey("core", "storefront")
	for index := 0; index < maxRoutesPerApplication; index++ {
		_, err := server.SAdd(key, routeName(index))
		require.NoError(t, err)
	}

	require.NoError(t, proc.ConsumeLogs(t.Context(), oneEvent("core", "storefront", "/brand-new", "view")))
	require.Equal(t, otherRoute, capturedRoute(t, sink))
	concrete.cache.mu.Lock()
	defer concrete.cache.mu.Unlock()
	require.LessOrEqual(t, len(concrete.cache.overflow), overflowCacheLimit)
	_, ok := concrete.cache.overflow["core\x00storefront\x00/brand-new"]
	require.False(t, ok)
}

func TestConcurrentOutageAndOverflowCache(t *testing.T) {
	redisURL, _ := startRedis(t)
	proc, _ := startProcessor(t, redisURL, "shard-a", &captureLogs{})
	concrete := proc.(*logsProcessor)
	var calls atomic.Int32
	concrete.store = admitFunc(func(_ context.Context, _, _, route string) (bool, error) {
		calls.Add(1)
		if strings.Contains(route, "/err-") {
			return false, errors.New("redis unavailable")
		}
		return false, nil
	})

	const workers = 16
	const loops = 80
	var group sync.WaitGroup
	errs := make(chan error, workers*loops)
	for worker := 0; worker < workers; worker++ {
		group.Add(1)
		go func(worker int) {
			defer group.Done()
			for index := 0; index < loops; index++ {
				route := fmt.Sprintf("/over-%d-%d", worker, index)
				if index%5 == 0 {
					route = fmt.Sprintf("/err-%d", worker)
				}
				errs <- proc.ConsumeLogs(context.Background(), oneEvent("core", "storefront", route, "view"))
			}
		}(worker)
	}
	group.Wait()
	close(errs)
	for err := range errs {
		require.NoError(t, err)
	}
	concrete.cache.mu.Lock()
	require.LessOrEqual(t, len(concrete.cache.overflow), overflowCacheLimit)
	concrete.cache.mu.Unlock()
	require.Positive(t, calls.Load())
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
	return startProcessorWithLogger(t, redisURL, shard, next, nil)
}

func startProcessorWithLogger(t *testing.T, redisURL, shard string, next consumer.Logs, logger *zap.Logger) (processor.Logs, *metric.ManualReader) {
	t.Helper()
	reader := metric.NewManualReader()
	provider := metric.NewMeterProvider(metric.WithReader(reader))
	factory := NewFactory()
	cfg := factory.CreateDefaultConfig().(*Config)
	cfg.RedisURL = redisURL
	cfg.Shard = shard
	set := processortest.NewNopSettings(factory.Type())
	set.MeterProvider = provider
	if logger != nil {
		set.Logger = logger
	}
	created, err := factory.CreateLogs(t.Context(), set, cfg, next)
	require.NoError(t, err)
	require.NoError(t, created.Start(t.Context(), nil))
	t.Cleanup(func() {
		require.NoError(t, created.Shutdown(context.Background()))
	})
	return created, reader
}

func warnLogger() (*zap.Logger, *observer.ObservedLogs, *bytes.Buffer) {
	formatted := &bytes.Buffer{}
	core, recorded := observer.New(zap.WarnLevel)
	logger := zap.New(zapcore.NewTee(
		core,
		zapcore.NewCore(
			zapcore.NewJSONEncoder(zap.NewProductionEncoderConfig()),
			zapcore.AddSync(formatted),
			zapcore.WarnLevel,
		),
	))
	return logger, recorded, formatted
}

func useClock(t *testing.T, start time.Time) *time.Time {
	t.Helper()
	current := start
	previous := nowFn
	nowFn = func() time.Time { return current }
	t.Cleanup(func() { nowFn = previous })
	return &current
}

type countingAdmittor struct {
	inner routeAdmittor
	mu    sync.Mutex
	calls int
}

func (counter *countingAdmittor) admit(ctx context.Context, tenant, application, route string) (bool, error) {
	counter.mu.Lock()
	counter.calls++
	counter.mu.Unlock()
	return counter.inner.admit(ctx, tenant, application, route)
}

func (counter *countingAdmittor) callCount() int {
	counter.mu.Lock()
	defer counter.mu.Unlock()
	return counter.calls
}

type admitFunc func(context.Context, string, string, string) (bool, error)

func (fn admitFunc) admit(ctx context.Context, tenant, application, route string) (bool, error) {
	return fn(ctx, tenant, application, route)
}

func fieldString(t *testing.T, entry observer.LoggedEntry, key string) string {
	t.Helper()
	for _, field := range entry.Context {
		if field.Key != key {
			continue
		}
		require.Equal(t, zapcore.StringType, field.Type)
		return field.String
	}
	require.Failf(t, "missing log field", "%s", key)
	return ""
}

func fieldInt(t *testing.T, entry observer.LoggedEntry, key string) int64 {
	t.Helper()
	for _, field := range entry.Context {
		if field.Key != key {
			continue
		}
		require.Equal(t, zapcore.Int64Type, field.Type)
		return field.Integer
	}
	require.Failf(t, "missing log field", "%s", key)
	return 0
}

func logBlob(entry observer.LoggedEntry) string {
	parts := []string{entry.Message}
	for _, field := range entry.Context {
		parts = append(parts, field.Key, field.String, strconv.FormatInt(field.Integer, 10), fmt.Sprint(field.Interface))
	}
	return strings.Join(parts, " ")
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

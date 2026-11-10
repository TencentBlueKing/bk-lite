package rumroutecap

import (
	"context"
	"fmt"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/processor"
	"go.opentelemetry.io/otel/metric"
	"go.uber.org/zap"
)

var typeStr = component.MustNewType("rumroutecap")

func NewFactory() processor.Factory {
	return processor.NewFactory(
		typeStr,
		func() component.Config { return defaultConfig() },
		processor.WithLogs(createLogsProcessor, component.StabilityLevelAlpha),
	)
}

func createLogsProcessor(
	_ context.Context,
	set processor.Settings,
	raw component.Config,
	next consumer.Logs,
) (processor.Logs, error) {
	cfg := raw.(*Config)
	store, err := newRouteStore(cfg)
	if err != nil {
		return nil, err
	}
	counter, err := set.MeterProvider.Meter(typeStr.String()).Int64Counter(
		failureInstrument,
		metric.WithDescription("Aggregate route lookups labeled 其他 because Redis was unavailable."),
		metric.WithUnit("{lookup}"),
	)
	if err != nil {
		_ = store.close()
		return nil, fmt.Errorf("create aggregate route failure counter: %w", err)
	}
	logger := set.Logger
	if logger == nil {
		logger = zap.NewNop()
	}
	return &logsProcessor{
		redis: store,
		limiter: limiter{
			store:    store,
			cache:    newRouteCache(),
			shard:    cfg.Shard,
			logger:   logger,
			failures: failureCounter{counter: counter},
			next:     next,
		},
	}, nil
}

type failureCounter struct {
	counter metric.Int64Counter
}

func (counter failureCounter) Add(ctx context.Context, value int64) {
	counter.counter.Add(ctx, value)
}

type logsProcessor struct {
	limiter
	redis *routeStore
}

func (processor *logsProcessor) Capabilities() consumer.Capabilities {
	return consumer.Capabilities{MutatesData: false}
}

func (processor *logsProcessor) ConsumeLogs(ctx context.Context, ld plog.Logs) error {
	out := plog.NewLogs()
	ld.CopyTo(out)
	processor.stamp(ctx, out)
	if err := processor.next.ConsumeLogs(ctx, out); err != nil {
		processor.logger.Warn(
			"rum aggregate branch ignored a downstream error",
			zap.String("failed_stage", "consume"),
			zap.String("error_type", fmt.Sprintf("%T", err)),
		)
	}
	return nil
}

func (processor *logsProcessor) Start(ctx context.Context, _ component.Host) error {
	pingCtx, cancel := context.WithTimeout(ctx, redisTimeout)
	defer cancel()
	if err := processor.redis.client.Ping(pingCtx).Err(); err != nil {
		processor.circuit.trip(nowFn(), errorTypeName(err))
		processor.logger.Warn(
			"rum aggregate route redis is not reachable; unknown routes will be labeled 其他",
			zap.String("failed_stage", "route_admission"),
			zap.String("error_type", errorTypeName(err)),
		)
	}
	return nil
}

func (processor *logsProcessor) Shutdown(context.Context) error {
	processor.flushFailure()
	return processor.redis.close()
}

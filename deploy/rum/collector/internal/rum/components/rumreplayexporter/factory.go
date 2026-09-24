package rumreplayexporter

import (
	"context"
	"fmt"
	"time"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/exporter"
	"go.opentelemetry.io/collector/exporter/exporterhelper"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.uber.org/zap"
)

var exporterType = component.MustNewType("rum_replay")

// NewFactory exposes the coordinated object-plus-index writer as a standard
// logs exporter. The queue acknowledges the receiver only after persistence.
func NewFactory() exporter.Factory {
	return exporter.NewFactory(
		exporterType,
		func() component.Config { return defaultConfig() },
		exporter.WithLogs(createLogsExporter, component.StabilityLevelAlpha),
	)
}

func createLogsExporter(
	ctx context.Context,
	settings exporter.Settings,
	config component.Config,
) (exporter.Logs, error) {
	cfg, ok := config.(*Config)
	if !ok {
		return nil, fmt.Errorf("invalid rumreplay config type %T", config)
	}
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	objects, err := newMinIOObjectStore(cfg)
	if err != nil {
		return nil, err
	}
	indexes, err := newRedisIndexStore(cfg)
	if err != nil {
		return nil, err
	}
	leases, err := newRedisLeaseStore(cfg)
	if err != nil {
		return nil, err
	}
	implementation := &replayExporter{
		objects:        objects,
		indexes:        indexes,
		leases:         leases,
		bucket:         cfg.MinIOBucket,
		now:            time.Now,
		maxQueueAge:    cfg.MaxQueueAge,
		observeAgeDrop: newReplayAgeDropObserver(settings),
	}
	return exporterhelper.NewLogs(
		ctx,
		settings,
		config,
		implementation.pushLogs,
		exporterhelper.WithStart(implementation.Start),
		exporterhelper.WithShutdown(implementation.Shutdown),
		exporterhelper.WithTimeout(cfg.TimeoutConfig),
		exporterhelper.WithRetry(cfg.BackOffConfig),
		exporterhelper.WithQueue(cfg.QueueSettings),
	)
}

func newReplayAgeDropObserver(settings exporter.Settings) func(context.Context, replayAgeDrop) {
	counter, err := settings.MeterProvider.Meter("weops.rum.queue").Int64Counter(
		"rum_queue_dropped_total",
		metric.WithDescription("RUM persistent queue items discarded by the absolute accepted-at gate"),
	)
	if err != nil {
		settings.Logger.Error("Failed to create RUM Replay queue age metric", zap.Error(err))
	}
	return func(ctx context.Context, drop replayAgeDrop) {
		settings.Logger.Warn(
			"RUM persistent queue item discarded by absolute age gate",
			zap.String("signal", "replay"),
			zap.String("reason", drop.Reason),
			zap.Int("count", drop.Count),
		)
		if err == nil {
			counter.Add(ctx, int64(drop.Count), metric.WithAttributes(
				attribute.String("signal", "replay"),
				attribute.String("reason", drop.Reason),
			))
		}
	}
}

package rumgate

import (
	"context"
	"fmt"

	"go.opentelemetry.io/collector/exporter"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.uber.org/zap"
)

// NewAgeFilterObserver records persistent-queue age drops.
func NewAgeFilterObserver(settings exporter.Settings) (AgeFilterObserver, error) {
	counter, err := settings.MeterProvider.Meter("weops.rum.queue").Int64Counter(
		"rum_queue_dropped_total",
		metric.WithDescription("RUM persistent queue items discarded by the absolute accepted-at gate"),
	)
	if err != nil {
		return nil, fmt.Errorf("create RUM queue age metric: %w", err)
	}
	return func(ctx context.Context, signal string, result ageFilterResult) {
		settings.Logger.Warn(
			"RUM persistent queue item discarded by absolute age gate",
			zap.String("signal", signal),
			zap.Int("expired", result.Expired),
			zap.Int("invalid", result.Invalid),
			zap.Int("kept", result.Kept),
		)
		if result.Expired > 0 {
			counter.Add(ctx, int64(result.Expired), metric.WithAttributes(
				attribute.String("signal", signal),
				attribute.String("reason", "expired"),
			))
		}
		if result.Invalid > 0 {
			counter.Add(ctx, int64(result.Invalid), metric.WithAttributes(
				attribute.String("signal", signal),
				attribute.String("reason", "invalid-accepted-at"),
			))
		}
		if result.Fenced > 0 {
			counter.Add(ctx, int64(result.Fenced), metric.WithAttributes(
				attribute.String("signal", signal),
				attribute.String("reason", "erasure_fence"),
			))
		}
	}, nil
}

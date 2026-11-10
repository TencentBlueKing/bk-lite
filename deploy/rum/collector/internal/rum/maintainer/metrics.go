package maintainer

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

const sessionEndLostMetric = "core_rum_session_end_records_lost_total"

type operationHealthSource interface {
	CountOverdueErasures(context.Context, time.Time) (int64, error)
}

type replayHealthSource interface {
	CountReplayPending(context.Context, time.Time) (int64, error)
	ReconciliationHealth(context.Context, time.Time) (time.Time, uint64, error)
}

type OperationalMetrics struct {
	operations        operationHealthSource
	replay            replayHealthSource
	registry          *prometheus.Registry
	pendingReplay     prometheus.Gauge
	overdueErasures   prometheus.Gauge
	recentConflicts   prometheus.Gauge
	lastReconcileTime prometheus.Gauge
	up                prometheus.Gauge
	sessionEndLost    prometheus.Counter
	now               func() time.Time
}

func NewOperationalMetrics(
	operations operationHealthSource,
	replay replayHealthSource,
) *OperationalMetrics {
	registry := prometheus.NewRegistry()
	metrics := &OperationalMetrics{
		operations: operations,
		replay:     replay,
		registry:   registry,
		pendingReplay: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "core_rum_replay_pending_segments",
			Help: "Replay segments that have remained pending for more than two minutes.",
		}),
		overdueErasures: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "core_rum_erasure_overdue_operations",
			Help: "Pending erasure operations older than the 30 minute completion target.",
		}),
		recentConflicts: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "core_rum_reconciliation_recent_conflicts",
			Help: "Replay identity or checksum conflicts recorded during the last ten minutes.",
		}),
		lastReconcileTime: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "core_rum_reconciliation_last_run_timestamp_seconds",
			Help: "Unix timestamp of the most recent persisted Replay reconciliation run.",
		}),
		up: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "core_rum_operational_metrics_up",
			Help: "Whether the most recent Redis and warehouse operational health collection succeeded.",
		}),
		sessionEndLost: prometheus.NewCounter(prometheus.CounterOpts{
			Name: sessionEndLostMetric,
			Help: "Session-end records dropped because their snapshot expired before it could be written.",
		}),
		now: time.Now,
	}
	registry.MustRegister(
		metrics.pendingReplay,
		metrics.overdueErasures,
		metrics.recentConflicts,
		metrics.lastReconcileTime,
		metrics.up,
		metrics.sessionEndLost,
	)
	return metrics
}

func (metrics *OperationalMetrics) SessionEndLost() prometheus.Counter {
	return metrics.sessionEndLost
}

func (metrics *OperationalMetrics) Run(ctx context.Context, address string) error {
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return fmt.Errorf("listen for maintainer metrics: %w", err)
	}
	server := &http.Server{
		Handler:           promhttp.HandlerFor(metrics.registry, promhttp.HandlerOpts{}),
		ReadHeaderTimeout: 5 * time.Second,
	}
	serveErr := make(chan error, 1)
	go func() {
		serveErr <- server.Serve(listener)
	}()

	metrics.collect(ctx)
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			if err := server.Shutdown(shutdownCtx); err != nil {
				return fmt.Errorf("stop maintainer metrics: %w", err)
			}
			err := <-serveErr
			if err != nil && !errors.Is(err, http.ErrServerClosed) {
				return err
			}
			return nil
		case err := <-serveErr:
			if err != nil && !errors.Is(err, http.ErrServerClosed) {
				return fmt.Errorf("serve maintainer metrics: %w", err)
			}
			return nil
		case <-ticker.C:
			metrics.collect(ctx)
		}
	}
}

func (metrics *OperationalMetrics) collect(ctx context.Context) {
	if err := metrics.refresh(ctx); err != nil {
		metrics.up.Set(0)
		slog.Error("collect RUM operational metrics", "error", err)
		return
	}
	metrics.up.Set(1)
}

func (metrics *OperationalMetrics) refresh(ctx context.Context) error {
	now := metrics.now().UTC()
	pending, pendingErr := metrics.replay.CountReplayPending(ctx, now.Add(-2*time.Minute))
	if pendingErr == nil {
		metrics.pendingReplay.Set(float64(pending))
	}
	overdue, overdueErr := metrics.operations.CountOverdueErasures(ctx, now.Add(-30*time.Minute))
	if overdueErr == nil {
		metrics.overdueErasures.Set(float64(overdue))
	}
	lastRun, conflicts, reconcileErr := metrics.replay.ReconciliationHealth(ctx, now.Add(-10*time.Minute))
	if reconcileErr == nil {
		metrics.recentConflicts.Set(float64(conflicts))
		if lastRun.IsZero() {
			metrics.lastReconcileTime.Set(0)
		} else {
			metrics.lastReconcileTime.Set(float64(lastRun.Unix()))
		}
	}
	return errors.Join(pendingErr, overdueErr, reconcileErr)
}

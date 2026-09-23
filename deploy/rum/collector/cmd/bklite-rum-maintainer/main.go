package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/maintainer"
	"golang.org/x/sync/errgroup"
)

func main() {
	if err := run(); err != nil {
		slog.Error("bklite-rum-maintainer stopped", "error", err)
		os.Exit(1)
	}
}

func run() error {
	var redisConfig maintainer.RedisConfig
	var indexConfig maintainer.RedisIndexConfig
	var victoriaConfig maintainer.VictoriaWarehouseConfig
	var minIOConfig maintainer.MinIOConfig
	var metricsAddress string
	var indexEpoch string
	flag.StringVar(&redisConfig.URL, "redis-url", "", "maintainer Redis URL (ACL user rum-maintainer)")
	flag.StringVar(&redisConfig.PasswordFile, "redis-password-file", "", "maintainer Redis password file")
	flag.StringVar(&indexConfig.URL, "replay-index-redis-url", "", "Replay index Redis URL (ACL user rum-replay-index-maintainer)")
	flag.StringVar(&indexConfig.PasswordFile, "replay-index-redis-password-file", "", "Replay index Redis password file")
	flag.StringVar(&indexEpoch, "replay-index-epoch", "", "RFC3339 Replay index cutover; required")
	flag.StringVar(&victoriaConfig.LogsEndpoint, "victoria-logs-endpoint", "", "VictoriaLogs HTTP endpoint")
	flag.StringVar(&victoriaConfig.TracesEndpoint, "victoria-traces-endpoint", "", "VictoriaTraces HTTP endpoint")
	flag.StringVar(&minIOConfig.Endpoint, "minio-endpoint", "", "MinIO endpoint")
	flag.BoolVar(&minIOConfig.Secure, "minio-secure", true, "use TLS for MinIO")
	flag.StringVar(&minIOConfig.AccessKey, "minio-access-key", "", "MinIO maintainer access key")
	flag.StringVar(&minIOConfig.SecretKeyFile, "minio-secret-key-file", "", "MinIO maintainer secret key file")
	flag.StringVar(&minIOConfig.Bucket, "minio-bucket", "rum-replay", "Replay bucket")
	flag.StringVar(&metricsAddress, "metrics-address", "0.0.0.0:9090", "internal Prometheus metrics listen address")
	flag.Parse()

	state, err := maintainer.NewRedisState(redisConfig)
	if err != nil {
		return err
	}
	defer state.Close()
	epoch, err := time.Parse(time.RFC3339, strings.TrimSpace(indexEpoch))
	if err != nil {
		return fmt.Errorf("replay-index-epoch is required RFC3339: %w", err)
	}
	indexes, err := maintainer.NewRedisIndexStore(indexConfig)
	if err != nil {
		return err
	}
	warehouse, err := maintainer.NewVictoriaWarehouse(victoriaConfig)
	if err != nil {
		return err
	}
	objects, err := maintainer.NewMinIOStore(minIOConfig)
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	if err := state.Start(ctx); err != nil {
		return err
	}
	if err := indexes.Start(ctx); err != nil {
		return err
	}
	if err := warehouse.Start(ctx); err != nil {
		return err
	}
	if err := objects.Start(ctx); err != nil {
		return err
	}
	processor := maintainer.NewProcessor(indexes, warehouse, objects, state)
	reconciler, err := maintainer.NewReconciler(indexes, objects, state, epoch)
	if err != nil {
		return err
	}
	metrics := maintainer.NewOperationalMetrics(state, indexes)
	group, groupCtx := errgroup.WithContext(ctx)
	group.Go(func() error {
		return state.Run(groupCtx, processor, reconciler)
	})
	group.Go(func() error {
		runScheduled := func() {
			runCtx, cancel := context.WithTimeout(groupCtx, 4*time.Minute)
			err := reconciler.RunScheduled(runCtx)
			cancel()
			if err != nil {
				slog.Error("scheduled Replay reconciliation failed", "error", err)
			}
		}
		runScheduled()
		reconcileTicker := time.NewTicker(5 * time.Minute)
		defer reconcileTicker.Stop()
		orphanTicker := time.NewTicker(24 * time.Hour)
		defer orphanTicker.Stop()
		for {
			select {
			case <-groupCtx.Done():
				return nil
			case <-reconcileTicker.C:
				runScheduled()
			case <-orphanTicker.C:
				runCtx, cancel := context.WithTimeout(groupCtx, 2*time.Hour)
				err := reconciler.RunOrphanScan(runCtx)
				cancel()
				if err != nil {
					slog.Error("daily Replay orphan scan failed", "error", err)
				}
			}
		}
	})
	group.Go(func() error {
		return metrics.Run(groupCtx, metricsAddress)
	})
	slog.Info("bklite-rum-maintainer ready")
	if err := group.Wait(); err != nil {
		return fmt.Errorf("maintainer runtime: %w", err)
	}
	return nil
}

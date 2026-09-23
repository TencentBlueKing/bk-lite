package rumvictoriaexporter

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/components/rumgate"
	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/config/configoptional"
	"go.opentelemetry.io/collector/config/configretry"
	"go.opentelemetry.io/collector/exporter"
	"go.opentelemetry.io/collector/exporter/exporterhelper"
	"go.opentelemetry.io/collector/exporter/otlphttpexporter"
)

var exporterType = component.MustNewType("rum_victoria")

// Config wraps otlphttp with the RUM age/fence/marker gate.
type Config struct {
	exporterhelper.TimeoutConfig `mapstructure:",squash"`
	configretry.BackOffConfig    `mapstructure:"retry_on_failure"`
	QueueSettings                configoptional.Optional[exporterhelper.QueueBatchConfig] `mapstructure:"sending_queue"`
	LogsEndpoint                 string                                                   `mapstructure:"logs_endpoint"`
	TracesEndpoint               string                                                   `mapstructure:"traces_endpoint"`
	MaxQueueAge                  time.Duration                                            `mapstructure:"max_queue_age"`
	AdmissionRedisURL            string                                                   `mapstructure:"admission_redis_url"`
	AdmissionRedisPassword       string                                                   `mapstructure:"admission_redis_password_file"`
}

func defaultConfig() *Config {
	queue := exporterhelper.NewDefaultQueueConfig()
	storageID := component.MustNewIDWithName("file_storage", "rum")
	queue.StorageID = &storageID
	return &Config{
		TimeoutConfig:     exporterhelper.TimeoutConfig{Timeout: 10 * time.Second},
		BackOffConfig:     configretry.NewDefaultBackOffConfig(),
		QueueSettings:     configoptional.Some(queue),
		MaxQueueAge:       rumgate.MaxPersistentQueueAge,
		AdmissionRedisURL: "redis://rum-admission:rum-admission-dev-secret-2026-000002@rum-redis:6379",
	}
}

func (cfg *Config) Validate() error {
	var result error
	if strings.TrimSpace(cfg.LogsEndpoint) == "" && strings.TrimSpace(cfg.TracesEndpoint) == "" {
		result = errors.Join(result, errors.New("logs_endpoint or traces_endpoint is required"))
	}
	if cfg.MaxQueueAge <= 0 || cfg.MaxQueueAge > rumgate.MaxPersistentQueueAge {
		result = errors.Join(result, fmt.Errorf("max_queue_age must be positive and at most %s", rumgate.MaxPersistentQueueAge))
	}
	if err := ingress.ValidateConfig(ingress.Config{
		RedisURL:          cfg.AdmissionRedisURL,
		RedisPasswordFile: cfg.AdmissionRedisPassword,
	}); err != nil {
		result = errors.Join(result, fmt.Errorf("invalid exporter erasure fence Redis: %w", err))
	}
	return result
}

// NewFactory wraps otlphttp with the shared RUM age/fence/marker gate.
func NewFactory() exporter.Factory {
	return exporter.NewFactory(
		exporterType,
		func() component.Config { return defaultConfig() },
		exporter.WithLogs(createLogsExporter, component.StabilityLevelAlpha),
		exporter.WithTraces(createTracesExporter, component.StabilityLevelAlpha),
	)
}

func victoriaOTLPConfig(cfg *Config) *otlphttpexporter.Config {
	downstream := otlphttpexporter.NewFactory().CreateDefaultConfig().(*otlphttpexporter.Config)
	downstream.LogsEndpoint = cfg.LogsEndpoint
	downstream.TracesEndpoint = cfg.TracesEndpoint
	downstream.QueueConfig = configoptional.None[exporterhelper.QueueBatchConfig]()
	downstream.RetryConfig.Enabled = false
	return downstream
}

func downstreamSettings(settings exporter.Settings) exporter.Settings {
	downstream := settings
	downstream.ID = component.NewIDWithName(component.MustNewType("otlphttp"), settings.ID.Name())
	return downstream
}

func createLogsExporter(ctx context.Context, settings exporter.Settings, config component.Config) (exporter.Logs, error) {
	cfg, ok := config.(*Config)
	if !ok {
		return nil, fmt.Errorf("invalid rum_victoria config type %T", config)
	}
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	downstream, err := otlphttpexporter.NewFactory().CreateLogs(ctx, downstreamSettings(settings), victoriaOTLPConfig(cfg))
	if err != nil {
		return nil, err
	}
	observer, err := rumgate.NewAgeFilterObserver(settings)
	if err != nil {
		return nil, err
	}
	fences, err := ingress.NewLeaseManager(ingress.Config{
		RedisURL:          cfg.AdmissionRedisURL,
		RedisPasswordFile: cfg.AdmissionRedisPassword,
	})
	if err != nil {
		return nil, err
	}
	marker, err := rumgate.NewStoredMarker(ingress.Config{
		RedisURL:          cfg.AdmissionRedisURL,
		RedisPasswordFile: cfg.AdmissionRedisPassword,
	}, settings.Logger)
	if err != nil {
		return nil, err
	}
	gate := rumgate.NewLogsAgeGate(downstream, fences, marker, settings.Logger, time.Now, cfg.MaxQueueAge, observer)
	return exporterhelper.NewLogs(
		ctx, settings, config, gate.PushLogs,
		exporterhelper.WithStart(gate.Start),
		exporterhelper.WithShutdown(gate.Shutdown),
		exporterhelper.WithTimeout(cfg.TimeoutConfig),
		exporterhelper.WithRetry(cfg.BackOffConfig),
		exporterhelper.WithQueue(cfg.QueueSettings),
	)
}

func createTracesExporter(ctx context.Context, settings exporter.Settings, config component.Config) (exporter.Traces, error) {
	cfg, ok := config.(*Config)
	if !ok {
		return nil, fmt.Errorf("invalid rum_victoria config type %T", config)
	}
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	downstream, err := otlphttpexporter.NewFactory().CreateTraces(ctx, downstreamSettings(settings), victoriaOTLPConfig(cfg))
	if err != nil {
		return nil, err
	}
	observer, err := rumgate.NewAgeFilterObserver(settings)
	if err != nil {
		return nil, err
	}
	fences, err := ingress.NewLeaseManager(ingress.Config{
		RedisURL:          cfg.AdmissionRedisURL,
		RedisPasswordFile: cfg.AdmissionRedisPassword,
	})
	if err != nil {
		return nil, err
	}
	marker, err := rumgate.NewStoredMarker(ingress.Config{
		RedisURL:          cfg.AdmissionRedisURL,
		RedisPasswordFile: cfg.AdmissionRedisPassword,
	}, settings.Logger)
	if err != nil {
		return nil, err
	}
	gate := rumgate.NewTracesAgeGate(downstream, fences, marker, settings.Logger, time.Now, cfg.MaxQueueAge, observer)
	return exporterhelper.NewTraces(
		ctx, settings, config, gate.PushTraces,
		exporterhelper.WithStart(gate.Start),
		exporterhelper.WithShutdown(gate.Shutdown),
		exporterhelper.WithTimeout(cfg.TimeoutConfig),
		exporterhelper.WithRetry(cfg.BackOffConfig),
		exporterhelper.WithQueue(cfg.QueueSettings),
	)
}

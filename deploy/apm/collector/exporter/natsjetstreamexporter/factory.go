package natsjetstreamexporter

import (
	"context"
	"time"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/config/configoptional"
	"go.opentelemetry.io/collector/config/configretry"
	"go.opentelemetry.io/collector/exporter"
	"go.opentelemetry.io/collector/exporter/exporterhelper"
	"go.opentelemetry.io/otel/metric"
)

var componentType = component.MustNewType("nats_jetstream")

func NewFactory() exporter.Factory {
	return exporter.NewFactory(
		componentType,
		createDefaultConfig,
		exporter.WithTraces(createTracesExporter, component.StabilityLevelDevelopment),
	)
}

func createDefaultConfig() component.Config {
	return &Config{
		TimeoutConfig:   exporterhelper.NewDefaultTimeoutConfig(),
		QueueConfig:     configoptional.Some(exporterhelper.NewDefaultQueueConfig()),
		RetryConfig:     configretry.NewDefaultBackOffConfig(),
		URLs:            []string{natsDefaultURL},
		ConnectTimeout:  5 * time.Second,
		MaxMessageBytes: 8 * 1024 * 1024,
	}
}

const natsDefaultURL = "nats://127.0.0.1:4222"

func createTracesExporter(
	ctx context.Context,
	settings exporter.Settings,
	configuration component.Config,
) (exporter.Traces, error) {
	cfg := configuration.(*Config)
	meter := settings.MeterProvider.Meter("github.com/bk-lite/apm-collector/exporter/natsjetstreamexporter")
	publishACKs, err := meter.Int64Counter(
		"bklite.apm.nats.publish_acks",
		metric.WithDescription("JetStream trace batches acknowledged as persisted"),
	)
	if err != nil {
		return nil, err
	}
	duplicateACKs, err := meter.Int64Counter(
		"bklite.apm.nats.duplicate_acks",
		metric.WithDescription("JetStream publishes suppressed by the duplicate window"),
	)
	if err != nil {
		return nil, err
	}
	instance := &tracesExporter{cfg: cfg, publishACKs: publishACKs, duplicateACKs: duplicateACKs}
	return exporterhelper.NewTraces(
		ctx,
		settings,
		cfg,
		instance.pushTraces,
		exporterhelper.WithTimeout(cfg.TimeoutConfig),
		exporterhelper.WithRetry(cfg.RetryConfig),
		exporterhelper.WithQueue(cfg.QueueConfig),
		exporterhelper.WithStart(instance.start),
		exporterhelper.WithShutdown(instance.shutdown),
	)
}

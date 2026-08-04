package natsjetstreamreceiver

import (
	"context"
	"time"

	"github.com/nats-io/nats.go"
	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/receiver"
	"go.opentelemetry.io/otel/metric"
)

var componentType = component.MustNewType("nats_jetstream")

func NewFactory() receiver.Factory {
	return receiver.NewFactory(
		componentType,
		createDefaultConfig,
		receiver.WithTraces(createTracesReceiver, component.StabilityLevelDevelopment),
	)
}

func createDefaultConfig() component.Config {
	return &Config{
		URLs:              []string{nats.DefaultURL},
		FilterSubject:     "apm.traces.>",
		ConnectTimeout:    5 * time.Second,
		DownstreamTimeout: 30 * time.Second,
		NakDelay:          5 * time.Second,
		PullMaxMessages:   32,
	}
}

func createTracesReceiver(
	_ context.Context,
	settings receiver.Settings,
	configuration component.Config,
	next consumer.Traces,
) (receiver.Traces, error) {
	meter := settings.MeterProvider.Meter("github.com/bk-lite/apm-collector/receiver/natsjetstreamreceiver")
	deliveryACKs, err := meter.Int64Counter("bklite.apm.nats.delivery_acks", metric.WithDescription("Trace messages synchronously acknowledged"))
	if err != nil {
		return nil, err
	}
	deliveryRetries, err := meter.Int64Counter("bklite.apm.nats.delivery_retries", metric.WithDescription("Trace messages negatively acknowledged for retry"))
	if err != nil {
		return nil, err
	}
	poisonMessages, err := meter.Int64Counter("bklite.apm.nats.poison_messages", metric.WithDescription("Invalid trace transport messages terminated"))
	if err != nil {
		return nil, err
	}
	ackFailures, err := meter.Int64Counter("bklite.apm.nats.ack_failures", metric.WithDescription("Synchronous JetStream ACK failures"))
	if err != nil {
		return nil, err
	}
	return &tracesReceiver{
		cfg:             configuration.(*Config),
		next:            next,
		logger:          settings.Logger,
		deliveryACKs:    deliveryACKs,
		deliveryRetries: deliveryRetries,
		poisonMessages:  poisonMessages,
		ackFailures:     ackFailures,
	}, nil
}

package farorumreceiver

import (
	"context"
	"fmt"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/receiver"
)

var receiverType = component.MustNewType("faro")

var receiverRegistry = newSharedRegistry()

// NewFactory returns a collector factory that shares one HTTP listener across
// its logs and traces signal registrations.
func NewFactory() receiver.Factory {
	return receiver.NewFactory(
		receiverType,
		func() component.Config { return defaultConfig() },
		receiver.WithLogs(createLogsReceiver, component.StabilityLevelAlpha),
		receiver.WithTraces(createTracesReceiver, component.StabilityLevelAlpha),
	)
}

func createLogsReceiver(
	_ context.Context,
	settings receiver.Settings,
	config component.Config,
	next consumer.Logs,
) (receiver.Logs, error) {
	cfg, ok := config.(*Config)
	if !ok {
		return nil, fmt.Errorf("invalid farorum config type %T", config)
	}
	shared, err := receiverRegistry.getOrAdd(cfg, settings)
	if err != nil {
		return nil, err
	}
	shared.receiver.registerLogs(next)
	return shared, nil
}

func createTracesReceiver(
	_ context.Context,
	settings receiver.Settings,
	config component.Config,
	next consumer.Traces,
) (receiver.Traces, error) {
	cfg, ok := config.(*Config)
	if !ok {
		return nil, fmt.Errorf("invalid farorum config type %T", config)
	}
	shared, err := receiverRegistry.getOrAdd(cfg, settings)
	if err != nil {
		return nil, err
	}
	shared.receiver.registerTraces(next)
	return shared, nil
}

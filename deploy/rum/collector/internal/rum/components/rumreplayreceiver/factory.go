package rumreplayreceiver

import (
	"context"
	"fmt"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/receiver"
)

var receiverType = component.MustNewType("rum_replay")

// NewFactory exposes the Replay ingress as a standard logs receiver.
func NewFactory() receiver.Factory {
	return receiver.NewFactory(
		receiverType,
		func() component.Config { return defaultConfig() },
		receiver.WithLogs(createLogsReceiver, component.StabilityLevelAlpha),
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
		return nil, fmt.Errorf("invalid rumreplay config type %T", config)
	}
	return newReplayReceiver(cfg, &settings, next)
}

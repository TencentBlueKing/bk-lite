package rumsessionprocessor

import (
	"context"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/processor"
	"go.opentelemetry.io/collector/processor/processorhelper"
)

var typeStr = component.MustNewType("rumsession")

func NewFactory() processor.Factory {
	return processor.NewFactory(
		typeStr,
		func() component.Config { return defaultConfig() },
		processor.WithLogs(createLogsProcessor, component.StabilityLevelAlpha),
	)
}

func createLogsProcessor(
	ctx context.Context,
	set processor.Settings,
	raw component.Config,
	next consumer.Logs,
) (processor.Logs, error) {
	cfg := raw.(*Config)
	store, err := newRedisSessionStore(cfg)
	if err != nil {
		return nil, err
	}
	sessionizer := newSessionizer(store)
	return processorhelper.NewLogs(
		ctx,
		set,
		raw,
		next,
		sessionizer.processLogs,
		processorhelper.WithCapabilities(consumer.Capabilities{MutatesData: true}),
		processorhelper.WithStart(store.start),
		processorhelper.WithShutdown(store.shutdown),
	)
}

package traceguardprocessor

import (
	"context"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.opentelemetry.io/collector/processor"
	"go.opentelemetry.io/collector/processor/processorhelper"
	"go.uber.org/zap"
)

var componentType = component.MustNewType("trace_guard")

func NewFactory() processor.Factory {
	return processor.NewFactory(
		componentType,
		createDefaultConfig,
		processor.WithTraces(createTracesProcessor, component.StabilityLevelDevelopment),
	)
}

func createDefaultConfig() component.Config {
	return &Config{
		MaxResourceAttrs:  64,
		MaxScopeAttrs:     32,
		MaxSpanAttrs:      100,
		MaxEventAttrs:     32,
		MaxLinkAttrs:      32,
		MaxAttributeRunes: 4096,
	}
}

func createTracesProcessor(
	ctx context.Context,
	settings processor.Settings,
	configuration component.Config,
	next consumer.Traces,
) (processor.Traces, error) {
	cfg := configuration.(*Config)
	return processorhelper.NewTraces(
		ctx,
		settings,
		cfg,
		next,
		func(ctx context.Context, tracesData ptrace.Traces) (ptrace.Traces, error) {
			result := sanitizeTraces(tracesData, cfg)
			if result.DroppedResourceSpans > 0 {
				settings.Logger.Warn(
					"dropped resource spans with invalid APM catalog identity",
					zap.Int("dropped_resource_spans", result.DroppedResourceSpans),
				)
			}
			return tracesData, nil
		},
		processorhelper.WithCapabilities(consumer.Capabilities{MutatesData: true}),
	)
}

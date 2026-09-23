package main

import (
	"github.com/bk-lite/rum-collector/internal/rum/components/farorumreceiver"
	"github.com/bk-lite/rum-collector/internal/rum/components/rumreplayexporter"
	"github.com/bk-lite/rum-collector/internal/rum/components/rumreplayreceiver"
	"github.com/bk-lite/rum-collector/internal/rum/components/rumsessionprocessor"
	"github.com/bk-lite/rum-collector/internal/rum/components/rumvictoriaexporter"
	"github.com/open-telemetry/opentelemetry-collector-contrib/extension/healthcheckextension"
	"github.com/open-telemetry/opentelemetry-collector-contrib/extension/storage/filestorage"
	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/connector"
	"go.opentelemetry.io/collector/exporter"
	"go.opentelemetry.io/collector/extension"
	"go.opentelemetry.io/collector/otelcol"
	"go.opentelemetry.io/collector/processor"
	"go.opentelemetry.io/collector/processor/batchprocessor"
	"go.opentelemetry.io/collector/processor/memorylimiterprocessor"
	"go.opentelemetry.io/collector/receiver"
	otelconftelemetry "go.opentelemetry.io/collector/service/telemetry/otelconftelemetry"
)

// components registers the RUM gateway factories used by otel/rum.gateway*.yaml.
func components() (otelcol.Factories, error) {
	var err error
	factories := otelcol.Factories{Telemetry: otelconftelemetry.NewFactory()}

	factories.Extensions, err = otelcol.MakeFactoryMap[extension.Factory](
		healthcheckextension.NewFactory(),
		filestorage.NewFactory(),
	)
	if err != nil {
		return otelcol.Factories{}, err
	}

	factories.Receivers, err = otelcol.MakeFactoryMap[receiver.Factory](
		farorumreceiver.NewFactory(),
		rumreplayreceiver.NewFactory(),
	)
	if err != nil {
		return otelcol.Factories{}, err
	}

	factories.Processors, err = otelcol.MakeFactoryMap[processor.Factory](
		memorylimiterprocessor.NewFactory(),
		batchprocessor.NewFactory(),
		rumsessionprocessor.NewFactory(),
	)
	if err != nil {
		return otelcol.Factories{}, err
	}

	factories.Exporters, err = otelcol.MakeFactoryMap[exporter.Factory](
		rumvictoriaexporter.NewFactory(),
		rumreplayexporter.NewFactory(),
	)
	if err != nil {
		return otelcol.Factories{}, err
	}

	factories.Connectors, err = otelcol.MakeFactoryMap[connector.Factory]()
	if err != nil {
		return otelcol.Factories{}, err
	}

	_ = component.StabilityLevelBeta
	return factories, nil
}

package main

import (
	"os"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/confmap"
	"go.opentelemetry.io/collector/confmap/provider/envprovider"
	"go.opentelemetry.io/collector/confmap/provider/fileprovider"
	"go.opentelemetry.io/collector/confmap/provider/yamlprovider"
	"go.opentelemetry.io/collector/otelcol"
)

var version = "0.1.0-rum"

func main() {
	settings := otelcol.CollectorSettings{
		BuildInfo: component.BuildInfo{
			Command:     "bklite-rum-gateway",
			Description: "BK-Lite RUM Faro/Replay gateway",
			Version:     version,
		},
		Factories: components,
		ConfigProviderSettings: otelcol.ConfigProviderSettings{
			ResolverSettings: confmap.ResolverSettings{
				ProviderFactories: []confmap.ProviderFactory{
					envprovider.NewFactory(),
					fileprovider.NewFactory(),
					yamlprovider.NewFactory(),
				},
			},
		},
	}
	if err := run(settings); err != nil {
		os.Exit(1)
	}
}

func runInteractive(settings otelcol.CollectorSettings) error {
	return otelcol.NewCommand(settings).Execute()
}

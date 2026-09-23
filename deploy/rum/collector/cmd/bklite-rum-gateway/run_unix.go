//go:build !windows

package main

import "go.opentelemetry.io/collector/otelcol"

func run(settings otelcol.CollectorSettings) error {
	return runInteractive(settings)
}

package rumvictoriaexporter

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestConfigRequiresAnEndpoint(t *testing.T) {
	cfg := defaultConfig()
	require.ErrorContains(t, cfg.Validate(), "logs_endpoint or traces_endpoint")
	cfg.LogsEndpoint = "http://victoria-logs:9428/insert/opentelemetry/v1/logs"
	require.NoError(t, cfg.Validate())
	cfg.LogsEndpoint = ""
	cfg.TracesEndpoint = "http://victoria-traces:10428/insert/opentelemetry/v1/traces"
	require.NoError(t, cfg.Validate())
	cfg.MaxQueueAge = 0
	require.ErrorContains(t, cfg.Validate(), "max_queue_age")
	cfg.MaxQueueAge = 15 * 24 * time.Hour
	require.ErrorContains(t, cfg.Validate(), "max_queue_age")
}

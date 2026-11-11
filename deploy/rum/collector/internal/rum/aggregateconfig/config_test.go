package aggregateconfig

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
	"gopkg.in/yaml.v3"
)

func TestGatewayConfigsLockTheAggregatePipeline(t *testing.T) {
	for _, name := range []string{"rum.gateway.yaml", "rum.gateway.dev.yaml"} {
		t.Run(name, func(t *testing.T) {
			root := load(t, name)
			pipelines := pipelinesOf(t, root)
			logs := pipeline(t, pipelines, "logs/rum")
			require.Equal(t, []any{"faro/rum"}, logs["receivers"])
			require.Equal(t, []any{"memory_limiter", "rumsession"}, logs["processors"])
			require.Equal(t, []any{"rum_victoria/rum", "forward/rum_agg"}, logs["exporters"])
			aggLogs := pipeline(t, pipelines, "logs/rum_agg")
			require.Equal(t, []any{"forward/rum_agg"}, aggLogs["receivers"])
			require.Equal(t, []any{"rumroutecap"}, aggLogs["processors"])
			require.Equal(t, []any{"signal_to_metrics/rum"}, aggLogs["exporters"])
			require.NotContains(t, aggLogs["processors"], "memory_limiter")
			metrics := pipeline(t, pipelines, "metrics/rum_agg")
			require.Equal(t, []any{"signal_to_metrics/rum"}, metrics["receivers"])
			require.Equal(t, []any{"batch/rum_agg", "deltatocumulative/rum"}, metrics["processors"])
			require.Equal(t, []any{"prometheus_remote_write/rum_agg"}, metrics["exporters"])
			require.NotContains(t, metrics["processors"], "memory_limiter")

			service := mapOf(t, root, "service")
			telemetry := mapOf(t, service, "telemetry")
			resource := mapOf(t, telemetry, "resource")
			attributes := resource["attributes"].([]any)
			require.Equal(t, "service.instance.id", attributes[0].(map[string]any)["name"])
			require.Equal(t, "${env:RUM_AGG_SHARD}", attributes[0].(map[string]any)["value"])

			exporters := mapOf(t, root, "exporters")
			remoteWrite := mapOf(t, exporters, "prometheus_remote_write/rum_agg")
			require.Equal(t, "${env:AGG_VICTORIAMETRICS_WRITE_URL}", remoteWrite["endpoint"])
			require.NotContains(t, remoteWrite["endpoint"], "VICTORIAMETRICS_HOST")
			labels := mapOf(t, remoteWrite, "external_labels")
			require.Equal(t, "${env:RUM_AGG_SHARD}", labels["shard"])
			queue := mapOf(t, remoteWrite, "remote_write_queue")
			require.Equal(t, false, queue["enabled"])
			retry := mapOf(t, remoteWrite, "retry_on_failure")
			require.Equal(t, false, retry["enabled"])
			require.Equal(t, false, mapOf(t, remoteWrite, "target_info")["enabled"])
			require.Equal(t, true, remoteWrite["disable_scope_info"])

			delta := mapOf(t, mapOf(t, root, "processors"), "deltatocumulative/rum")
			require.Equal(t, "${env:RUM_AGG_MAX_STREAMS:-420000}", delta["max_streams"])

			connectors := mapOf(t, root, "connectors")
			signal := mapOf(t, connectors, "signal_to_metrics/rum")
			require.Equal(t, "ignore", signal["error_mode"])
			logsMetrics := signal["logs"].([]any)
			require.Len(t, logsMetrics, 7)
			names := map[string]map[string]any{}
			for _, item := range logsMetrics {
				metric := item.(map[string]any)
				names[metric["name"].(string)] = metric
			}
			require.Contains(t, names["rum.views"]["conditions"].([]any)[0], `log.attributes["rum.event.type"] == "view"`)
			require.NotContains(t, names["rum.views"]["conditions"].([]any)[0], "UnixNano")
			require.Contains(t, names["rum.js_errors"]["conditions"].([]any)[0], `log.attributes["rum.event.type"] == "error"`)
			require.Equal(t, "ms", names["rum.web_vital.lcp"]["unit"])
			require.Equal(t, []float64{100, 250, 500, 1000, 2500, 4000, 8000, 16000}, numbers(t, histogram(t, names["rum.web_vital.lcp"])["buckets"]))
			require.Equal(t, []float64{50, 100, 200, 500, 1000, 2500}, numbers(t, histogram(t, names["rum.web_vital.inp"])["buckets"]))
			require.Equal(t, []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1}, numbers(t, histogram(t, names["rum.web_vital.cls"])["buckets"]))
			require.Equal(t, []float64{100, 250, 500, 1000, 1800, 3000, 6000, 12000}, numbers(t, histogram(t, names["rum.web_vital.fcp"])["buckets"]))
			require.Equal(t, []float64{50, 100, 200, 400, 800, 1800, 4000}, numbers(t, histogram(t, names["rum.web_vital.ttfb"])["buckets"]))
			require.NotContains(t, names, "rum.aggregate.late_events")
			for _, metric := range names {
				attributes := metric["attributes"].([]any)
				keys := map[string]bool{}
				for _, attribute := range attributes {
					keys[attribute.(map[string]any)["key"].(string)] = true
				}
				require.True(t, keys["rum.aggregate.route"])
				require.False(t, keys["rum.view.name"])
				require.False(t, keys["rum.user.id"])
				require.False(t, keys["rum.session.id"])
				require.False(t, keys["rum.page.url"])
			}
		})
	}
}

func TestIngestConfigOmitsTheAggregateBranch(t *testing.T) {
	body, err := os.ReadFile(filepath.Join(repoOtel(), "rum.gateway.ingest.yaml"))
	require.NoError(t, err)
	text := string(body)
	require.NotContains(t, text, "signal_to_metrics")
	require.NotContains(t, text, "prometheusremotewrite")
	require.NotContains(t, text, "prometheus_remote_write")
	require.NotContains(t, text, "rumroutecap")
	root := load(t, "rum.gateway.ingest.yaml")
	logs := pipeline(t, pipelinesOf(t, root), "logs/rum")
	require.Equal(t, []any{"rum_victoria/rum"}, logs["exporters"])
}

func TestAuthConfigStaysOutOfTheMainFile(t *testing.T) {
	main := load(t, "rum.gateway.yaml")
	require.NotContains(t, main, "basicauth/agg")
	auth := load(t, "rum.gateway.auth.yaml")
	extension := mapOf(t, mapOf(t, auth, "extensions"), "basicauth/agg")
	client := mapOf(t, extension, "client_auth")
	require.Equal(t, "${env:AGG_VICTORIAMETRICS_USER}", client["username"])
	require.Equal(t, "${env:AGG_VICTORIAMETRICS_PASSWORD}", client["password"])
	remoteWrite := mapOf(t, mapOf(t, auth, "exporters"), "prometheus_remote_write/rum_agg")
	require.Equal(t, "basicauth/agg", mapOf(t, remoteWrite, "auth")["authenticator"])
}

func repoOtel() string {
	return filepath.Join("..", "..", "..", "otel")
}

func load(t *testing.T, name string) map[string]any {
	t.Helper()
	body, err := os.ReadFile(filepath.Join(repoOtel(), name))
	require.NoError(t, err)
	var root map[string]any
	require.NoError(t, yaml.Unmarshal(body, &root))
	return root
}

func pipelinesOf(t *testing.T, root map[string]any) map[string]any {
	t.Helper()
	return mapOf(t, mapOf(t, root, "service"), "pipelines")
}

func pipeline(t *testing.T, pipelines map[string]any, name string) map[string]any {
	t.Helper()
	value, ok := pipelines[name]
	require.True(t, ok, name)
	typed, ok := value.(map[string]any)
	require.True(t, ok, name)
	return typed
}

func mapOf(t *testing.T, parent map[string]any, key string) map[string]any {
	t.Helper()
	value, ok := parent[key]
	require.Truef(t, ok, "missing %s", key)
	typed, ok := value.(map[string]any)
	require.Truef(t, ok, "%s is not a map", key)
	return typed
}

func histogram(t *testing.T, metric map[string]any) map[string]any {
	t.Helper()
	return mapOf(t, metric, "histogram")
}

func numbers(t *testing.T, value any) []float64 {
	t.Helper()
	items, ok := value.([]any)
	require.True(t, ok)
	out := make([]float64, 0, len(items))
	for _, item := range items {
		switch typed := item.(type) {
		case int:
			out = append(out, float64(typed))
		case int64:
			out = append(out, float64(typed))
		case float64:
			out = append(out, typed)
		default:
			t.Fatalf("bucket %T is not numeric", item)
		}
	}
	return out
}

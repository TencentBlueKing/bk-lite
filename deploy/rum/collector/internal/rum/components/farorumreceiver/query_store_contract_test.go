package farorumreceiver

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	faro "github.com/grafana/faro/pkg/go"
	victoria "github.com/bk-lite/rum-collector/internal/victorialogscontract"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
)

func TestFaroIngestAttrsAreQueryableByVictoriaStore(t *testing.T) {
	now := time.Date(2026, 8, 29, 12, 0, 0, 0, time.UTC)
	payload := faro.Payload{
		Events: []faro.Event{{Name: faroEventViewChanged, Timestamp: now}},
	}
	payload.Meta.App.Name = "storefront"
	payload.Meta.App.Environment = "production"
	payload.Meta.App.Release = "2026.08.29"
	payload.Meta.Session.ID = "session-live-1"
	payload.Meta.SDK.Version = "1.4.0"

	logs := translateOrdinary(payload, ingestMetadata{
		tenantID:    "core",
		application: "storefront",
		batchID:     "batch-1",
		observedAt:  now,
	}, defaultConfig())
	require.Greater(t, logs.LogRecordCount(), 0)

	row := flattenFirstFaroRecord(t, logs)
	require.Equal(t, "view", row["rum.event.type"])
	require.Equal(t, "storefront", row["rum.application"])
	require.NotContains(t, row, "rumcore.event.type")
	require.NotContains(t, row, "rumcore.application")

	var gotQuery string
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })
	mux.HandleFunc("/select/logsql/query", func(w http.ResponseWriter, r *http.Request) {
		require.NoError(t, r.ParseForm())
		gotQuery = r.Form.Get("query")
		require.NoError(t, json.NewEncoder(w).Encode(row))
	})
	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)

	store, err := victoria.Open(victoria.Config{LogsEndpoint: server.URL, TracesEndpoint: server.URL})
	require.NoError(t, err)
	rows, _, err := store.ApplicationsPage(t.Context(), now.Add(-10*time.Minute), now.Add(time.Minute), "core", []string{"storefront"})
	require.NoError(t, err)
	require.Contains(t, gotQuery, `"rum.event.type":*`)
	require.Contains(t, gotQuery, `"rum.application":in("storefront")`)
	require.NotContains(t, gotQuery, "rumcore.event.type")
	require.Len(t, rows, 1)
	require.Equal(t, "storefront", rows[0].Application)
	require.Equal(t, uint64(1), rows[0].Sessions)
	require.Equal(t, uint64(1), rows[0].Views)
}

func flattenFirstFaroRecord(t *testing.T, logs plog.Logs) map[string]string {
	t.Helper()
	require.Greater(t, logs.ResourceLogs().Len(), 0)
	rl := logs.ResourceLogs().At(0)
	require.Greater(t, rl.ScopeLogs().Len(), 0)
	sl := rl.ScopeLogs().At(0)
	require.Greater(t, sl.LogRecords().Len(), 0)
	rec := sl.LogRecords().At(0)
	row := map[string]string{
		"_time": rec.Timestamp().AsTime().UTC().Format(time.RFC3339Nano),
		"_msg":  rec.Body().AsString(),
	}
	putAttrs(row, rl.Resource().Attributes())
	putAttrs(row, rec.Attributes())
	return row
}

func putAttrs(row map[string]string, attrs pcommon.Map) {
	attrs.Range(func(k string, v pcommon.Value) bool {
		switch v.Type() {
		case pcommon.ValueTypeStr:
			row[k] = v.Str()
		case pcommon.ValueTypeBool:
			if v.Bool() {
				row[k] = "true"
			} else {
				row[k] = "false"
			}
		case pcommon.ValueTypeInt:
			row[k] = strconv.FormatInt(v.Int(), 10)
		case pcommon.ValueTypeDouble:
			row[k] = strconv.FormatFloat(v.Double(), 'f', -1, 64)
		}
		return true
	})
}

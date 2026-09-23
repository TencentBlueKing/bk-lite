package maintainer

import (
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func TestBeginErasurePostsFilterNotQuery(t *testing.T) {
	t.Parallel()

	var sawFilter, sawQuery bool
	var filterValue string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, "/delete/active_tasks"):
			w.WriteHeader(http.StatusOK)
			_, _ = io.WriteString(w, "[]")
		case strings.HasSuffix(r.URL.Path, "/delete/run_task"):
			_ = r.ParseForm()
			if r.Form.Get("filter") != "" {
				sawFilter = true
				filterValue = r.Form.Get("filter")
			}
			if r.Form.Get("query") != "" {
				sawQuery = true
			}
			w.WriteHeader(http.StatusOK)
			_, _ = io.WriteString(w, `{"task_id":"1"}`)
		default:
			http.NotFound(w, r)
		}
	}))
	t.Cleanup(server.Close)

	store, err := NewVictoriaWarehouse(VictoriaWarehouseConfig{
		LogsEndpoint:   server.URL,
		TracesEndpoint: server.URL,
	})
	if err != nil {
		t.Fatalf("NewVictoriaWarehouse: %v", err)
	}
	if err := store.Start(t.Context()); err != nil {
		t.Fatalf("Start: %v", err)
	}
	err = store.BeginErasure(t.Context(), ErasureTask{
		Application: "local-demo",
		Identities: []Identity{{
			Kind:    "user",
			Version: "v1",
			Digest:  strings.Repeat("a", 64),
		}},
	})
	if err != nil {
		t.Fatalf("BeginErasure: %v", err)
	}
	if !sawFilter {
		t.Fatal("expected delete/run_task to receive form field filter")
	}
	if sawQuery {
		t.Fatal("delete/run_task must not send obsolete form field query")
	}
	want := `"rum.erasure.user_key":"` + strings.Repeat("a", 64) + `"`
	if filterValue != want {
		t.Fatalf("filter=%q want %q", filterValue, want)
	}
	if _, err := url.ParseQuery("filter=" + url.QueryEscape(filterValue)); err != nil {
		t.Fatalf("filter must be form-encodable: %v", err)
	}
}

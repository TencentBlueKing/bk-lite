// Package victorialogscontract is a minimal VictoriaLogs query stub used by
// vendored Faro ingest contract tests. Production analytics live in Django
// apps.rum adapters, not in this gateway module.
package victorialogscontract

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type Config struct {
	LogsEndpoint   string
	TracesEndpoint string
}

type Store struct {
	logsEndpoint string
	client       *http.Client
}

type ApplicationHealthRow struct {
	Application string
	Sessions    uint64
	Views       uint64
}

func Open(cfg Config) (*Store, error) {
	base := strings.TrimRight(cfg.LogsEndpoint, "/")
	if base == "" {
		return nil, fmt.Errorf("logs endpoint required")
	}
	s := &Store{logsEndpoint: base, client: &http.Client{Timeout: 15 * time.Second}}
	resp, err := s.client.Get(base + "/health")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("victoria health status %d", resp.StatusCode)
	}
	return s, nil
}

func (s *Store) ApplicationsPage(
	ctx context.Context,
	from, to time.Time,
	tenantID string,
	enabledApps []string,
) ([]ApplicationHealthRow, map[string][]float64, error) {
	_ = from
	_ = to
	apps := make([]string, 0, len(enabledApps))
	for _, app := range enabledApps {
		app = strings.TrimSpace(app)
		if app != "" {
			apps = append(apps, app)
		}
	}
	quoted := make([]string, 0, len(apps))
	for _, app := range apps {
		quoted = append(quoted, strconvQuote(app))
	}
	tenant := tenantID
	if tenant == "" {
		tenant = "core"
	}
	query := fmt.Sprintf(`"rum.event.type":* "tenant.id":%s "rum.application":in(%s)`, strconvQuote(tenant), strings.Join(quoted, ","))
	form := url.Values{}
	form.Set("query", query)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.logsEndpoint+"/select/logsql/query", strings.NewReader(form.Encode()))
	if err != nil {
		return nil, nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, nil, err
	}
	row := map[string]string{}
	if err := json.Unmarshal(body, &row); err != nil {
		return nil, nil, err
	}
	out := make([]ApplicationHealthRow, 0, len(apps))
	for _, app := range apps {
		item := ApplicationHealthRow{Application: app}
		if row["rum.application"] == app {
			if row["rum.event.type"] == "view" {
				item.Sessions = 1
				item.Views = 1
			}
		}
		out = append(out, item)
	}
	return out, map[string][]float64{}, nil
}

func strconvQuote(v string) string {
	return strconvQuoteGo(v)
}

func strconvQuoteGo(v string) string {
	b, _ := json.Marshal(v)
	return string(b)
}

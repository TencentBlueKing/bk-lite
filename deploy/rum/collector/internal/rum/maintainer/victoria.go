package maintainer

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// VictoriaWarehouseConfig deletes telemetry from VL/VT.
type VictoriaWarehouseConfig struct {
	LogsEndpoint   string
	TracesEndpoint string
	Timeout        time.Duration
}

// VictoriaWarehouse implements Warehouse against Victoria delete APIs.
type VictoriaWarehouse struct {
	logs    *url.URL
	traces  *url.URL
	client  *http.Client
	started bool
}

// NewVictoriaWarehouse validates endpoints.
func NewVictoriaWarehouse(cfg VictoriaWarehouseConfig) (*VictoriaWarehouse, error) {
	logs, err := url.Parse(strings.TrimSpace(cfg.LogsEndpoint))
	if err != nil || logs.Host == "" {
		return nil, fmt.Errorf("victoria logs endpoint must be an HTTP URL")
	}
	traces, err := url.Parse(strings.TrimSpace(cfg.TracesEndpoint))
	if err != nil || traces.Host == "" {
		return nil, fmt.Errorf("victoria traces endpoint must be an HTTP URL")
	}
	timeout := cfg.Timeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	return &VictoriaWarehouse{logs: logs, traces: traces, client: &http.Client{Timeout: timeout}}, nil
}

func (store *VictoriaWarehouse) Start(ctx context.Context) error {
	if err := store.requireDelete(ctx, store.logs); err != nil {
		return fmt.Errorf("VictoriaLogs delete API unavailable: %w", err)
	}
	if err := store.requireDelete(ctx, store.traces); err != nil {
		return fmt.Errorf("VictoriaTraces delete API unavailable: %w", err)
	}
	store.started = true
	return nil
}

func (store *VictoriaWarehouse) requireDelete(ctx context.Context, base *url.URL) error {
	endpoint := *base
	endpoint.Path = strings.TrimSuffix(endpoint.Path, "/") + "/delete/active_tasks"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return err
	}
	resp, err := store.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("delete endpoints unavailable (status %d); enable -delete.enable", resp.StatusCode)
	}
	return nil
}

func (store *VictoriaWarehouse) AuditControl(context.Context, ControlAuditTask) error {
	return nil
}

func (store *VictoriaWarehouse) BeginErasure(ctx context.Context, task ErasureTask) error {
	if !store.started {
		return fmt.Errorf("Victoria warehouse delete API is not available")
	}
	filters := erasureLogsQL(task)
	if err := store.runDelete(ctx, store.logs, filters); err != nil {
		return err
	}
	return store.runDelete(ctx, store.traces, filters)
}

func erasureLogsQL(task ErasureTask) string {
	parts := make([]string, 0, len(task.Identities))
	for _, identity := range task.Identities {
		switch identity.Kind {
		case "user":
			parts = append(parts, fmt.Sprintf(`"rum.erasure.user_key":%q`, identity.Digest))
		default:
			parts = append(parts, fmt.Sprintf(`"rum.erasure.session_key":%q`, identity.Digest))
		}
	}
	if len(parts) == 0 {
		return fmt.Sprintf(`"rum.application":%q`, task.Application)
	}
	return strings.Join(parts, " OR ")
}

func (store *VictoriaWarehouse) runDelete(ctx context.Context, base *url.URL, query string) error {
	endpoint := *base
	endpoint.Path = strings.TrimSuffix(endpoint.Path, "/") + "/delete/run_task"
	form := url.Values{}
	// VictoriaLogs/Traces delete API (v1.38+) expects `filter`, not `query`.
	form.Set("filter", query)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint.String(), strings.NewReader(form.Encode()))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := store.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode >= 300 {
		return fmt.Errorf("delete status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return nil
}

func (store *VictoriaWarehouse) WaitMutations(context.Context) error { return nil }

func (store *VictoriaWarehouse) AuditErasure(context.Context, ErasureTask) error { return nil }

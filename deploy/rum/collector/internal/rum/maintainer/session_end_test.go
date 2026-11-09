package maintainer

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	rumstate "github.com/bk-lite/rum-collector/internal/rum/state"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func TestScanWritesDueSessionAndSkipsOneStillInsideIdle(t *testing.T) {
	client := testRedis(t)
	start := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	last := start.Add(time.Minute)
	dueKey := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	freshKey := "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	emptyRouteKey := "cccccccccccccccccccccccccccccccc"
	seedSnapshot(t, client, dueKey, start, last, last, "/checkout", "user-sentinel")
	seedSnapshot(t, client, freshKey, start, last, last.Add(14*time.Minute), "/fresh", "fresh-user")
	seedSnapshot(t, client, emptyRouteKey, start, start, start, "", "")

	inserts := &insertCapture{}
	server := inserts.server(t)
	scanner, logs := testScanner(t, client, server.URL)
	err := scanner.Scan(t.Context(), last.Add(15*time.Minute))
	require.NoError(t, err)

	bodies := inserts.bodies()
	require.Equal(t, 1, inserts.calls())
	require.Len(t, bodies, 1)
	require.Equal(t, "/insert/jsonline", inserts.paths()[0])
	require.Equal(t, "application/stream+json", inserts.contentTypes()[0])

	byKey := map[string]map[string]any{}
	for _, decoded := range decodeJSONLines(t, bodies[0]) {
		byKey[decoded["rum.session.key"].(string)] = decoded
	}
	require.Len(t, byKey, 2)
	due := byKey[dueKey]
	require.Equal(t, "2026-07-27T00:01:00Z", due["_time"])
	require.Equal(t, "session_end", due["rum.event.type"])
	require.Equal(t, "storefront", due["rum.application"])
	require.Equal(t, "core", due["tenant.id"])
	require.Equal(t, "prod", due["rum.environment"])
	require.Equal(t, float64(start.UnixMilli()), due["rum.session.started_at_ms"])
	require.Equal(t, float64(60_000), due["rum.session.duration_ms"])
	require.Equal(t, float64(4), due["rum.session.event_count"])
	require.Equal(t, float64(2), due["rum.session.view_count"])
	require.Equal(t, float64(1), due["rum.session.error_count"])
	require.Equal(t, "/checkout", due["rum.view.name"])
	require.Equal(t, "1.2.3", due["rum.release"])
	require.Equal(t, "user-sentinel", due["rum.user.id"])
	require.Equal(t, "human", due["rum.traffic.class"])
	require.Equal(t, "erase-user-sentinel", due["rum.erasure.user_key"])
	require.Equal(t, "erase-session-sentinel", due["rum.erasure.session_key"])

	emptyRoute := byKey[emptyRouteKey]
	require.Equal(t, "2026-07-27T00:00:00Z", emptyRoute["_time"])
	require.Equal(t, float64(0), emptyRoute["rum.session.duration_ms"])
	_, hasRoute := emptyRoute["rum.view.name"]
	require.False(t, hasRoute)
	_, hasUser := emptyRoute["rum.user.id"]
	require.False(t, hasUser)

	require.Equal(t, float64(last.Add(14*time.Minute).UnixMilli()), mustScore(t, client, freshKey))
	_, err = client.Exists(t.Context(), rumstate.SessionEndedKey(dueKey)).Result()
	require.NoError(t, err)
	require.Zero(t, mustExists(t, client, rumstate.SessionEndedKey(dueKey)))
	require.Zero(t, mustExists(t, client, rumstate.SessionEndedKey(emptyRouteKey)))
	require.Equal(t, 1, mustExists(t, client, rumstate.SessionEndedKey(freshKey)))
	require.Error(t, scoreErr(t, client, dueKey))

	text := logs.String()
	require.NotContains(t, text, "user-sentinel")
	require.NotContains(t, text, dueKey)
	require.NotContains(t, text, "erase-user-sentinel")
	require.Contains(t, text, `"msg":"event=rum_session_end_written"`)
	require.Contains(t, text, `"written":2`)
	require.NotContains(t, text, "event=rum_session_end_lost")
}

func TestScanSelectsMaxLengthSessionWhenIndexScoreIsDue(t *testing.T) {
	client := testRedis(t)
	start := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	last := start.Add(3*time.Hour + 50*time.Minute)
	score := start.Add(3*time.Hour + 45*time.Minute)
	key := "dddddddddddddddddddddddddddddddd"
	seedSnapshot(t, client, key, start, last, score, "/checkout", "user-1")

	inserts := &insertCapture{}
	server := inserts.server(t)
	scanner, _ := testScanner(t, client, server.URL)
	require.NoError(t, scanner.Scan(t.Context(), start.Add(4*time.Hour-time.Millisecond)))
	require.Empty(t, inserts.bodies())
	require.Equal(t, float64(score.UnixMilli()), mustScore(t, client, key))

	require.NoError(t, scanner.Scan(t.Context(), start.Add(4*time.Hour)))
	bodies := inserts.bodies()
	require.Len(t, bodies, 1)
	decoded := decodeJSONLine(t, bodies[0])
	require.Equal(t, "2026-07-27T03:50:00Z", decoded["_time"])
	require.Equal(t, float64(last.Sub(start).Milliseconds()), decoded["rum.session.duration_ms"])
	require.Zero(t, mustExists(t, client, rumstate.SessionEndedKey(key)))
}

func TestScanRetriesFailedInsertThenRemovesTheIndex(t *testing.T) {
	client := testRedis(t)
	start := time.Date(2026, 7, 27, 1, 0, 0, 0, time.UTC)
	key := "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
	seedSnapshot(t, client, key, start, start, start, "/checkout", "user-sentinel")
	inserts := &insertCapture{failFirst: 1, failBody: "response-body-sentinel"}
	server := inserts.server(t)
	scanner, logs := testScanner(t, client, server.URL)
	now := start.Add(15 * time.Minute)

	require.NoError(t, scanner.Scan(t.Context(), now))
	require.Equal(t, float64(start.UnixMilli()), mustScore(t, client, key))
	require.Equal(t, 1, mustExists(t, client, rumstate.SessionEndedKey(key)))
	require.NotContains(t, logs.String(), "response-body-sentinel")
	require.NotContains(t, logs.String(), key)
	require.NotContains(t, logs.String(), "user-sentinel")
	require.Contains(t, logs.String(), `"msg":"event=rum_session_end_write_failed"`)
	require.Contains(t, logs.String(), `"failed_stage":"insert"`)
	require.Contains(t, logs.String(), `"error_type":"insert_status"`)
	require.Contains(t, logs.String(), `"status":500`)
	require.Contains(t, logs.String(), `"failed":1`)

	require.NoError(t, scanner.Scan(t.Context(), now))
	require.Len(t, inserts.bodies(), 1)
	require.Equal(t, key, decodeJSONLine(t, inserts.bodies()[0])["rum.session.key"])
	require.Error(t, scoreErr(t, client, key))
	require.Zero(t, mustExists(t, client, rumstate.SessionEndedKey(key)))
	require.Contains(t, logs.String(), `"msg":"event=rum_session_end_written"`)
}

func TestScanDropsMissingSnapshotAndCountsItLost(t *testing.T) {
	client := testRedis(t)
	metrics := NewOperationalMetrics(&fakeOperationHealth{}, &fakeReplayHealth{})
	missingKey := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	badKey := "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	badMember := "leak-this-member-sentinel"
	old := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	require.NoError(t, client.ZAdd(t.Context(), rumstate.SessionActivityIndexKey, redis.Z{Score: float64(old.UnixMilli()), Member: missingKey}).Err())
	require.NoError(t, client.ZAdd(t.Context(), rumstate.SessionActivityIndexKey, redis.Z{Score: float64(old.UnixMilli()), Member: badKey}).Err())
	require.NoError(t, client.ZAdd(t.Context(), rumstate.SessionActivityIndexKey, redis.Z{Score: float64(old.UnixMilli()), Member: badMember}).Err())
	require.NoError(t, client.HSet(t.Context(), rumstate.SessionEndedKey(badKey), "key", badKey, "first", "nope", "user", "user-do-not-log").Err())

	inserts := &insertCapture{}
	server := inserts.server(t)
	logger, logs := jsonLogger()
	scanner := NewSessionEndScanner(client, mustWriter(t, server.URL), metrics.SessionEndLost(), logger)
	require.NoError(t, scanner.Scan(t.Context(), old.Add(time.Hour)))

	require.Empty(t, inserts.bodies())
	require.Equal(t, float64(3), testutil.ToFloat64(metrics.SessionEndLost()))
	gathered, err := metrics.registry.Gather()
	require.NoError(t, err)
	var found bool
	for _, family := range gathered {
		if family.GetName() == sessionEndLostMetric {
			found = true
		}
	}
	require.True(t, found)
	require.Error(t, scoreErr(t, client, missingKey))
	require.Error(t, scoreErr(t, client, badKey))
	require.Error(t, scoreErr(t, client, badMember))
	require.Zero(t, mustExists(t, client, rumstate.SessionEndedKey(badKey)))
	text := logs.String()
	require.NotContains(t, text, missingKey)
	require.NotContains(t, text, badKey)
	require.NotContains(t, text, badMember)
	require.NotContains(t, text, "user-do-not-log")
	require.Contains(t, text, `"msg":"event=rum_session_end_lost"`)
	require.Contains(t, text, `"lost":3`)
	require.Contains(t, text, `"failed_stage":"load_snapshot"`)
}

func TestScanDrainsMoreThanOneBatchInOneRound(t *testing.T) {
	client := testRedis(t)
	start := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	total := sessionEndBatch + 1
	for index := 0; index < total; index++ {
		key := fmt.Sprintf("%032x", index)
		at := start.Add(time.Duration(index) * time.Millisecond)
		seedSnapshot(t, client, key, at, at, at, "/checkout", "batch-user-sentinel")
	}
	inserts := &insertCapture{}
	server := inserts.server(t)
	scanner, logs := testScanner(t, client, server.URL)
	require.NoError(t, scanner.Scan(t.Context(), start.Add(time.Hour)))

	require.Equal(t, 2, inserts.calls())
	bodies := inserts.bodies()
	require.Len(t, bodies, 2)
	require.Len(t, decodeJSONLines(t, bodies[0]), sessionEndBatch)
	require.Len(t, decodeJSONLines(t, bodies[1]), 1)
	require.Zero(t, mustCard(t, client))
	require.Zero(t, mustExists(t, client, rumstate.SessionEndedKey(fmt.Sprintf("%032x", 0))))
	require.Zero(t, mustExists(t, client, rumstate.SessionEndedKey(fmt.Sprintf("%032x", sessionEndBatch))))
	text := logs.String()
	require.Equal(t, 1, strings.Count(text, `"msg":"event=rum_session_end_written"`))
	require.Contains(t, text, fmt.Sprintf(`"written":%d`, total))
	require.NotContains(t, text, "batch-user-sentinel")
}

func TestScanLeavesTheBatchAndStopsWhenInsertFails(t *testing.T) {
	client := testRedis(t)
	start := time.Date(2026, 7, 27, 2, 0, 0, 0, time.UTC)
	total := sessionEndBatch + 50
	for index := 0; index < total; index++ {
		key := fmt.Sprintf("%032x", index)
		at := start.Add(time.Duration(index) * time.Millisecond)
		seedSnapshot(t, client, key, at, at, at, "/checkout", "retry-user-sentinel")
	}
	inserts := &insertCapture{failFirst: 1, failBody: "response-body-sentinel"}
	server := inserts.server(t)
	scanner, logs := testScanner(t, client, server.URL)
	require.NoError(t, scanner.Scan(t.Context(), start.Add(time.Hour)))

	require.Equal(t, 1, inserts.calls())
	require.Empty(t, inserts.bodies())
	require.Equal(t, total, mustCard(t, client))
	require.Equal(t, 1, mustExists(t, client, rumstate.SessionEndedKey(fmt.Sprintf("%032x", 0))))
	require.Equal(t, float64(start.Add(time.Duration(total-1)*time.Millisecond).UnixMilli()), mustScore(t, client, fmt.Sprintf("%032x", total-1)))
	text := logs.String()
	require.Equal(t, 1, strings.Count(text, `"msg":"event=rum_session_end_write_failed"`))
	require.Contains(t, text, fmt.Sprintf(`"failed":%d`, sessionEndBatch))
	require.NotContains(t, text, "event=rum_session_end_written")
	require.NotContains(t, text, "response-body-sentinel")
	require.NotContains(t, text, "retry-user-sentinel")
	require.NotContains(t, text, fmt.Sprintf("%032x", 0))
}

func TestScanContinuesAfterAFullBatchOfMissingSnapshots(t *testing.T) {
	client := testRedis(t)
	start := time.Date(2026, 7, 27, 3, 0, 0, 0, time.UTC)
	for index := 0; index < sessionEndBatch; index++ {
		key := fmt.Sprintf("%032x", index)
		require.NoError(t, client.ZAdd(t.Context(), rumstate.SessionActivityIndexKey, redis.Z{
			Score:  float64(start.UnixMilli()),
			Member: key,
		}).Err())
	}
	goodKey := fmt.Sprintf("%032x", sessionEndBatch)
	seedSnapshot(t, client, goodKey, start, start, start.Add(time.Millisecond), "/checkout", "kept-user-sentinel")
	inserts := &insertCapture{}
	server := inserts.server(t)
	scanner, logs := testScanner(t, client, server.URL)
	require.NoError(t, scanner.Scan(t.Context(), start.Add(time.Hour)))

	require.Equal(t, 1, inserts.calls())
	bodies := inserts.bodies()
	require.Len(t, bodies, 1)
	lines := decodeJSONLines(t, bodies[0])
	require.Len(t, lines, 1)
	require.Equal(t, goodKey, lines[0]["rum.session.key"])
	require.Zero(t, mustCard(t, client))
	text := logs.String()
	require.Contains(t, text, fmt.Sprintf(`"lost":%d`, sessionEndBatch))
	require.Contains(t, text, `"written":1`)
	require.NotContains(t, text, "kept-user-sentinel")
}

func TestScanStopsBeforeWritingWhenTheBudgetIsSpent(t *testing.T) {
	client := testRedis(t)
	start := time.Date(2026, 7, 27, 4, 0, 0, 0, time.UTC)
	key := "ffffffffffffffffffffffffffffffff"
	seedSnapshot(t, client, key, start, start, start, "/checkout", "budget-user-sentinel")
	inserts := &insertCapture{}
	server := inserts.server(t)
	scanner, logs := testScanner(t, client, server.URL)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	require.NoError(t, scanner.Scan(ctx, start.Add(time.Hour)))
	require.Zero(t, inserts.calls())
	require.Equal(t, float64(start.UnixMilli()), mustScore(t, client, key))
	require.Equal(t, 1, mustExists(t, client, rumstate.SessionEndedKey(key)))
	require.NotContains(t, logs.String(), "event=rum_session_end_written")
	require.NotContains(t, logs.String(), "budget-user-sentinel")
}

func TestErasureFilterDeletesSessionEndRecord(t *testing.T) {
	store := &lineStore{}
	server := httptest.NewServer(store.handler())
	t.Cleanup(server.Close)
	writer := mustWriter(t, server.URL)
	match := sampleSnapshot("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "erase-user-sentinel", "erase-session-sentinel")
	decoy := sampleSnapshot("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "other-user", "other-session")
	require.NoError(t, writer.Insert(t.Context(), mustBody(t, match)))
	require.NoError(t, writer.Insert(t.Context(), mustBody(t, decoy)))
	view := `{"_time":"2026-07-27T00:01:00Z","rum.event.type":"view","rum.application":"storefront","rum.session.key":"cccccccccccccccccccccccccccccccc"}` + "\n"
	resp, err := http.Post(server.URL+"/insert/jsonline", "application/stream+json", strings.NewReader(view))
	require.NoError(t, err)
	_, _ = io.Copy(io.Discard, resp.Body)
	resp.Body.Close()
	require.Equal(t, http.StatusOK, resp.StatusCode)

	warehouse, err := NewVictoriaWarehouse(VictoriaWarehouseConfig{LogsEndpoint: server.URL, TracesEndpoint: server.URL})
	require.NoError(t, err)
	require.NoError(t, warehouse.Start(t.Context()))
	require.NoError(t, warehouse.BeginErasure(t.Context(), ErasureTask{
		Application: "storefront",
		Identities: []Identity{
			{Kind: "user", Digest: "erase-user-sentinel"},
			{Kind: "session", Digest: "erase-session-sentinel"},
		},
	}))

	remaining := store.joined()
	require.NotContains(t, remaining, "erase-session-sentinel")
	require.NotContains(t, remaining, "erase-user-sentinel")
	require.Contains(t, remaining, "other-session")
	require.Contains(t, remaining, "cccccccccccccccccccccccccccccccc")
	require.Contains(t, remaining, `"rum.event.type":"view"`)
	require.Contains(t, remaining, `"rum.event.type":"session_end"`)
}

func TestScanFailureLogKeepsCauseAndDropsSessionMaterial(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&buf, nil))
	sessionKey := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	logScanFailure(logger, fmt.Errorf("dial tcp 127.0.0.1:6379: connection refused key %s redis://user:secret@redis:6379/1", sessionKey))
	var record map[string]any
	require.NoError(t, json.Unmarshal(bytes.TrimSpace(buf.Bytes()), &record))
	require.Equal(t, "event=rum_session_end_scan_failed", record["msg"])
	require.Equal(t, "scan", record["failed_stage"])
	require.NotEmpty(t, record["error_type"])
	require.Contains(t, record["error"], "connection refused")
	require.NotContains(t, buf.String(), sessionKey)
	require.NotContains(t, buf.String(), "secret")
}

func TestRunLogsScanFailureAndReturnsWhenCanceled(t *testing.T) {
	server := miniredis.RunT(t)
	addr := server.Addr()
	server.Close()
	client := redis.NewClient(&redis.Options{Addr: addr, MaxRetries: -1, DialTimeout: 100 * time.Millisecond, ReadTimeout: 100 * time.Millisecond})
	t.Cleanup(func() { _ = client.Close() })
	ctx, cancel := context.WithCancel(t.Context())
	timer := time.AfterFunc(2*time.Second, cancel)
	t.Cleanup(func() {
		timer.Stop()
		cancel()
	})
	var buf bytes.Buffer
	logger := slog.New(&cancelOnMessage{
		Handler: slog.NewJSONHandler(&buf, nil),
		cancel:  cancel,
		message: "event=rum_session_end_scan_failed",
	})
	scanner := NewSessionEndScanner(client, mustWriter(t, "http://127.0.0.1:9"), prometheusCounter(t), logger)
	require.NoError(t, scanner.Run(ctx))
	var record map[string]any
	require.NoError(t, json.Unmarshal(bytes.TrimSpace(buf.Bytes()), &record))
	require.Equal(t, "event=rum_session_end_scan_failed", record["msg"])
	require.Equal(t, "scan", record["failed_stage"])
	require.NotEmpty(t, record["error_type"])
	require.Contains(t, fmt.Sprint(record["error"]), "connect")
}

func TestSessionRedisURLIsRequired(t *testing.T) {
	_, err := NewSessionRedis(RedisConfig{})
	require.ErrorContains(t, err, "session Redis URL is required")
}

type insertCapture struct {
	mu           sync.Mutex
	recorded     [][]byte
	recordedPath []string
	recordedType []string
	failFirst    int
	failBody     string
	seen         int
}

func (capture *insertCapture) server(t *testing.T) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		capture.mu.Lock()
		capture.seen++
		fail := capture.seen <= capture.failFirst
		capture.mu.Unlock()
		if fail {
			http.Error(w, capture.failBody, http.StatusInternalServerError)
			return
		}
		capture.mu.Lock()
		capture.recorded = append(capture.recorded, append([]byte(nil), body...))
		capture.recordedPath = append(capture.recordedPath, r.URL.Path)
		capture.recordedType = append(capture.recordedType, r.Header.Get("Content-Type"))
		capture.mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)
	return server
}

func (capture *insertCapture) calls() int {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	return capture.seen
}

func (capture *insertCapture) bodies() [][]byte {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	return append([][]byte(nil), capture.recorded...)
}

func (capture *insertCapture) paths() []string {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	return append([]string(nil), capture.recordedPath...)
}

func (capture *insertCapture) contentTypes() []string {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	return append([]string(nil), capture.recordedType...)
}

type lineStore struct {
	mu    sync.Mutex
	lines []string
}

func (store *lineStore) handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, "/delete/active_tasks"):
			w.WriteHeader(http.StatusOK)
			_, _ = io.WriteString(w, "[]")
		case strings.HasSuffix(r.URL.Path, "/insert/jsonline"):
			body, _ := io.ReadAll(io.LimitReader(r.Body, 1<<20))
			store.mu.Lock()
			for _, line := range strings.Split(string(body), "\n") {
				if strings.TrimSpace(line) != "" {
					store.lines = append(store.lines, line)
				}
			}
			store.mu.Unlock()
			w.WriteHeader(http.StatusOK)
		case strings.HasSuffix(r.URL.Path, "/delete/run_task"):
			_ = r.ParseForm()
			filter := r.Form.Get("filter")
			parts := strings.Split(filter, " OR ")
			store.mu.Lock()
			kept := make([]string, 0, len(store.lines))
			for _, line := range store.lines {
				hit := false
				for _, part := range parts {
					if strings.Contains(line, strings.TrimSpace(part)) {
						hit = true
						break
					}
				}
				if !hit {
					kept = append(kept, line)
				}
			}
			store.lines = kept
			store.mu.Unlock()
			w.WriteHeader(http.StatusOK)
			_, _ = io.WriteString(w, `{"task_id":"1"}`)
		default:
			http.NotFound(w, r)
		}
	})
}

func (store *lineStore) joined() string {
	store.mu.Lock()
	defer store.mu.Unlock()
	return strings.Join(store.lines, "\n")
}

func testRedis(t *testing.T) *redis.Client {
	t.Helper()
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func testScanner(t *testing.T, client *redis.Client, endpoint string) (*SessionEndScanner, *bytes.Buffer) {
	t.Helper()
	logger, logs := jsonLogger()
	return NewSessionEndScanner(client, mustWriter(t, endpoint), prometheusCounter(t), logger), logs
}

func jsonLogger() (*slog.Logger, *bytes.Buffer) {
	var buf bytes.Buffer
	return slog.New(slog.NewJSONHandler(&buf, nil)), &buf
}

func mustWriter(t *testing.T, endpoint string) *SessionLogWriter {
	t.Helper()
	writer, err := NewSessionLogWriter(endpoint, time.Second)
	require.NoError(t, err)
	return writer
}

func prometheusCounter(t *testing.T) lostCounter {
	t.Helper()
	return NewOperationalMetrics(&fakeOperationHealth{}, &fakeReplayHealth{}).SessionEndLost()
}

func seedSnapshot(t *testing.T, client *redis.Client, key string, first, last time.Time, score time.Time, route, user string) {
	t.Helper()
	require.NoError(t, client.ZAdd(t.Context(), rumstate.SessionActivityIndexKey, redis.Z{
		Score:  float64(score.UnixMilli()),
		Member: key,
	}).Err())
	require.NoError(t, client.HSet(t.Context(), rumstate.SessionEndedKey(key), map[string]string{
		"key":             key,
		"first":           fmt.Sprint(first.UnixMilli()),
		"last":            fmt.Sprint(last.UnixMilli()),
		"traffic":         "human",
		"events":          "4",
		"views":           "2",
		"errors":          "1",
		"route":           route,
		"version":         "1.2.3",
		"user":            user,
		"env":             "prod",
		"erasure_user":    "erase-user-sentinel",
		"erasure_session": "erase-session-sentinel",
		"tenant":          "core",
		"application":     "storefront",
	}).Err())
}

func sampleSnapshot(key, user, session string) sessionSnapshot {
	start := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	return sessionSnapshot{
		SessionKey:     key,
		FirstMS:        start.UnixMilli(),
		LastMS:         start.Add(time.Minute).UnixMilli(),
		Traffic:        "human",
		Events:         4,
		Views:          2,
		Errors:         1,
		Route:          "/checkout",
		Version:        "1.2.3",
		User:           "user-1",
		Environment:    "prod",
		ErasureUser:    user,
		ErasureSession: session,
		Tenant:         "core",
		Application:    "storefront",
	}
}

func mustBody(t *testing.T, snap sessionSnapshot) []byte {
	t.Helper()
	body, err := sessionEndBody(snap)
	require.NoError(t, err)
	return body
}

func decodeJSONLine(t *testing.T, body []byte) map[string]any {
	t.Helper()
	lines := decodeJSONLines(t, body)
	require.Len(t, lines, 1)
	return lines[0]
}

func decodeJSONLines(t *testing.T, body []byte) []map[string]any {
	t.Helper()
	var decoded []map[string]any
	for _, line := range bytes.Split(bytes.TrimSpace(body), []byte("\n")) {
		if len(bytes.TrimSpace(line)) == 0 {
			continue
		}
		var item map[string]any
		require.NoError(t, json.Unmarshal(line, &item))
		decoded = append(decoded, item)
	}
	return decoded
}

func mustScore(t *testing.T, client *redis.Client, member string) float64 {
	t.Helper()
	score, err := client.ZScore(t.Context(), rumstate.SessionActivityIndexKey, member).Result()
	require.NoError(t, err)
	return score
}

func scoreErr(t *testing.T, client *redis.Client, member string) error {
	t.Helper()
	_, err := client.ZScore(t.Context(), rumstate.SessionActivityIndexKey, member).Result()
	return err
}

func mustCard(t *testing.T, client *redis.Client) int {
	t.Helper()
	count, err := client.ZCard(t.Context(), rumstate.SessionActivityIndexKey).Result()
	require.NoError(t, err)
	return int(count)
}

func mustExists(t *testing.T, client *redis.Client, key string) int {
	t.Helper()
	count, err := client.Exists(t.Context(), key).Result()
	require.NoError(t, err)
	return int(count)
}

type cancelOnMessage struct {
	slog.Handler
	cancel  context.CancelFunc
	message string
	once    sync.Once
}

func (handler *cancelOnMessage) Handle(ctx context.Context, record slog.Record) error {
	err := handler.Handler.Handle(ctx, record)
	if record.Message == handler.message {
		handler.once.Do(handler.cancel)
	}
	return err
}

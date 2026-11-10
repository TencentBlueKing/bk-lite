package rumsessionprocessor

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/maintainer"
	"github.com/stretchr/testify/require"
)

func TestMaintainerWritesTheSnapshotStoredByLua(t *testing.T) {
	store := newLuaStore(t)
	start := time.Date(2026, 7, 27, 2, 0, 0, 0, time.UTC)
	sessionKey := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	_, err := store.assign(t.Context(), countedAssignment("ops:rum:v2:session:bridge", start, sessionKey, "/checkout", "1.2.3", "user-1", "prod", 1, 1, 0))
	require.NoError(t, err)
	_, err = store.assign(t.Context(), countedAssignment("ops:rum:v2:session:bridge", start.Add(time.Second), "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "/other", "9.9.9", "user-2", "dev", 1, 0, 1))
	require.NoError(t, err)

	var mu sync.Mutex
	var bodies [][]byte
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		mu.Lock()
		bodies = append(bodies, append([]byte(nil), body...))
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)
	writer, err := maintainer.NewSessionLogWriter(server.URL, time.Second)
	require.NoError(t, err)
	scanner := maintainer.NewSessionEndScanner(store.client, writer, nil, nil)

	require.NoError(t, scanner.Scan(t.Context(), start.Add(time.Second).Add(15*time.Minute-time.Millisecond)))
	mu.Lock()
	require.Empty(t, bodies)
	mu.Unlock()

	require.NoError(t, scanner.Scan(t.Context(), start.Add(time.Second).Add(15*time.Minute)))
	mu.Lock()
	defer mu.Unlock()
	require.Len(t, bodies, 1)
	var decoded map[string]any
	require.NoError(t, json.Unmarshal(bodies[0], &decoded))
	require.Equal(t, "2026-07-27T02:00:01Z", decoded["_time"])
	require.Equal(t, "session_end", decoded["rum.event.type"])
	require.Equal(t, sessionKey, decoded["rum.session.key"])
	require.Equal(t, "storefront", decoded["rum.application"])
	require.Equal(t, "core", decoded["tenant.id"])
	require.Equal(t, "prod", decoded["rum.environment"])
	require.Equal(t, "/checkout", decoded["rum.view.name"])
	require.Equal(t, "1.2.3", decoded["rum.release"])
	require.Equal(t, "user-1", decoded["rum.user.id"])
	require.Equal(t, "human", decoded["rum.traffic.class"])
	require.Equal(t, "erase-user-1", decoded["rum.erasure.user_key"])
	require.Equal(t, "erase-session-1", decoded["rum.erasure.session_key"])
	require.Equal(t, float64(2), decoded["rum.session.event_count"])
	require.Equal(t, float64(1), decoded["rum.session.view_count"])
	require.Equal(t, float64(1), decoded["rum.session.error_count"])
	require.Equal(t, float64(1000), decoded["rum.session.duration_ms"])
}

func TestResumeAfterWriteDoesNotEmitTheClosedSessionAgain(t *testing.T) {
	store := newLuaStore(t)
	start := time.Date(2026, 7, 27, 4, 0, 0, 0, time.UTC)
	stateKey := "ops:rum:v2:session:resume"
	firstKey := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	nextKey := "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	_, err := store.assign(t.Context(), countedAssignment(stateKey, start, firstKey, "/checkout", "1.2.3", "user-1", "prod", 1, 1, 0))
	require.NoError(t, err)

	var mu sync.Mutex
	var bodies [][]byte
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		mu.Lock()
		bodies = append(bodies, append([]byte(nil), body...))
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)
	writer, err := maintainer.NewSessionLogWriter(server.URL, time.Second)
	require.NoError(t, err)
	scanner := maintainer.NewSessionEndScanner(store.client, writer, nil, nil)

	due := start.Add(15 * time.Minute)
	require.NoError(t, scanner.Scan(t.Context(), due))
	_, err = store.assign(t.Context(), countedAssignment(stateKey, due.Add(time.Minute), nextKey, "/home", "2.0.0", "user-2", "staging", 1, 1, 0))
	require.NoError(t, err)
	require.NoError(t, scanner.Scan(t.Context(), due.Add(2*time.Minute)))

	mu.Lock()
	defer mu.Unlock()
	require.Len(t, bodies, 1)
	var decoded map[string]any
	require.NoError(t, json.Unmarshal(bodies[0], &decoded))
	require.Equal(t, firstKey, decoded["rum.session.key"])
	require.Empty(t, redisHash(t, store, "ops:rum:v2:ended:"+firstKey))
	require.Equal(t, float64(due.Add(time.Minute).UnixMilli()), redisScore(t, store, nextKey))
}

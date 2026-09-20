package rumsessionprocessor

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
)

type memoryStore struct {
	mu      sync.Mutex
	records map[string]sessionState
	fail    bool
}

func (store *memoryStore) assign(_ context.Context, input assignment) (assignedSession, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.fail {
		return assignedSession{}, errors.New("redis unavailable")
	}
	if store.records == nil {
		store.records = map[string]sessionState{}
	}
	state := store.records[input.StateKey]
	state, rolled := advanceSession(state, input.ObservedAt, input.CandidateKey, input.TrafficClass)
	store.records[input.StateKey] = state
	return assignedSession{SessionKey: state.SessionKey, TrafficClass: state.TrafficClass, Rolled: rolled}, nil
}

func TestAdvanceSessionRollsAtIdleAndAbsoluteBoundaries(t *testing.T) {
	start := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	state, rolled := advanceSession(sessionState{}, start, "00000000000000000000000000000001", "human")
	require.True(t, rolled)
	require.Equal(t, "00000000000000000000000000000001", state.SessionKey)

	state, rolled = advanceSession(state, start.Add(15*time.Minute-time.Nanosecond), "00000000000000000000000000000002", "human")
	require.False(t, rolled)
	require.Equal(t, "00000000000000000000000000000001", state.SessionKey)

	state, rolled = advanceSession(state, start.Add(30*time.Minute-2*time.Nanosecond), "00000000000000000000000000000003", "human")
	require.False(t, rolled)

	state, rolled = advanceSession(state, start.Add(45*time.Minute), "00000000000000000000000000000004", "human")
	require.True(t, rolled)
	require.Equal(t, "00000000000000000000000000000004", state.SessionKey)

	longState, _ := advanceSession(sessionState{}, start, "10000000000000000000000000000001", "human")
	for index := 1; index < 16; index++ {
		longState, rolled = advanceSession(longState, start.Add(time.Duration(index)*14*time.Minute), "unused", "human")
		require.False(t, rolled)
	}
	longState, rolled = advanceSession(longState, start.Add(4*time.Hour), "10000000000000000000000000000002", "human")
	require.True(t, rolled)
	require.Equal(t, "10000000000000000000000000000002", longState.SessionKey)
}

func TestConcurrentAssignmentsProduceOneAuthoritativeKey(t *testing.T) {
	store := &memoryStore{}
	processor := newSessionizer(store)
	logs := makeOrdinaryLogs("tenant-a", "storefront", "erase-session-a", "human", time.Now().UTC())

	const workers = 32
	keys := make(chan string, workers)
	var wait sync.WaitGroup
	for range workers {
		wait.Add(1)
		go func() {
			defer wait.Done()
			copy := plog.NewLogs()
			logs.CopyTo(copy)
			processed, err := processor.processLogs(t.Context(), copy)
			require.NoError(t, err)
			keys <- recordAttribute(processed, "rum.session.key")
		}()
	}
	wait.Wait()
	close(keys)

	var first string
	for key := range keys {
		require.Regexp(t, `^[0-9a-f]{32}$`, key)
		if first == "" {
			first = key
		}
		require.Equal(t, first, key)
	}
}

func TestOrdinaryAndReplayShareSessionKeyAndTrafficClass(t *testing.T) {
	store := &memoryStore{}
	processor := newSessionizer(store)
	observed := time.Now().UTC()

	ordinary, err := processor.processLogs(t.Context(), makeOrdinaryLogs("tenant-a", "storefront", "erase-session-a", "synthetic", observed))
	require.NoError(t, err)
	replay, err := processor.processLogs(t.Context(), makeReplayLogs("tenant-a", "storefront", "erase-session-a", observed.Add(time.Minute)))
	require.NoError(t, err)

	require.Equal(t, recordAttribute(ordinary, "rum.session.key"), recordAttribute(replay, "rum.replay.session_key"))
	require.Equal(t, "synthetic", resourceAttribute(replay, "rum.traffic.class"))
}

func TestProcessorFailsClosedWhenAuthoritativeStoreIsUnavailable(t *testing.T) {
	processor := newSessionizer(&memoryStore{fail: true})
	_, err := processor.processLogs(t.Context(), makeOrdinaryLogs("tenant-a", "storefront", "erase-session-a", "human", time.Now().UTC()))
	require.ErrorContains(t, err, "authoritative RUM session")
}

func makeOrdinaryLogs(tenant, application, erasureKey, traffic string, observed time.Time) plog.Logs {
	logs := plog.NewLogs()
	resource := logs.ResourceLogs().AppendEmpty()
	resource.Resource().Attributes().PutStr("tenant.id", tenant)
	resource.Resource().Attributes().PutStr("rum.traffic.class", traffic)
	record := resource.ScopeLogs().AppendEmpty().LogRecords().AppendEmpty()
	record.SetObservedTimestamp(pcommon.NewTimestampFromTime(observed))
	record.Attributes().PutStr("rum.application", application)
	record.Attributes().PutStr("rum.erasure.session_key", erasureKey)
	return logs
}

func makeReplayLogs(tenant, application, erasureKey string, observed time.Time) plog.Logs {
	logs := plog.NewLogs()
	resource := logs.ResourceLogs().AppendEmpty()
	resource.Resource().Attributes().PutStr("tenant.id", tenant)
	record := resource.ScopeLogs().AppendEmpty().LogRecords().AppendEmpty()
	record.SetObservedTimestamp(pcommon.NewTimestampFromTime(observed))
	record.Attributes().PutStr("rum.replay.application", application)
	record.Attributes().PutStr("rum.erasure.session_key", erasureKey)
	return logs
}

func recordAttribute(logs plog.Logs, key string) string {
	value, _ := logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().Get(key)
	return value.Str()
}

func resourceAttribute(logs plog.Logs, key string) string {
	value, _ := logs.ResourceLogs().At(0).Resource().Attributes().Get(key)
	return value.Str()
}

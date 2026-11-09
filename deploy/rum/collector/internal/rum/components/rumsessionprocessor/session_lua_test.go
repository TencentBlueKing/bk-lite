package rumsessionprocessor

import (
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/pdata/plog"
)

func TestSessionRollStartsCountsAtZeroAndKeepsFirstValues(t *testing.T) {
	store := newLuaStore(t)
	stateKey := "ops:rum:v2:session:roll"
	t0 := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	firstKey := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	secondKey := "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	thirdKey := "cccccccccccccccccccccccccccccccc"

	_, err := store.assign(t.Context(), countedAssignment(stateKey, t0, firstKey, "/checkout", "1.2.3", "", "", 1, 1, 0))
	require.NoError(t, err)
	second := countedAssignment(stateKey, t0.Add(time.Second), secondKey, "/other", "9.9.9", "user-1", "prod", 1, 0, 1)
	second.ErasureUserKey = "erase-user-2"
	second.ErasureSessionKey = "erase-session-2"
	second.Tenant = "other"
	second.Application = "other-app"
	_, err = store.assign(t.Context(), second)
	require.NoError(t, err)

	live := redisHash(t, store, stateKey)
	require.Equal(t, firstKey, live["key"])
	require.Equal(t, "2", live["events"])
	require.Equal(t, "1", live["views"])
	require.Equal(t, "1", live["errors"])
	require.Equal(t, "/checkout", live["route"])
	require.Equal(t, "1.2.3", live["version"])
	require.Equal(t, "user-1", live["user"])
	require.Equal(t, "prod", live["env"])
	require.Equal(t, "erase-user-1", live["erasure_user"])
	require.Equal(t, "erase-session-1", live["erasure_session"])
	require.Equal(t, "core", live["tenant"])
	require.Equal(t, "storefront", live["application"])
	require.Equal(t, float64(t0.Add(time.Second).UnixMilli()), redisScore(t, store, firstKey))

	rollAt := t0.Add(time.Second).Add(15 * time.Minute)
	rolled, err := store.assign(t.Context(), countedAssignment(stateKey, rollAt, thirdKey, "/home", "2.0.0", "user-2", "staging", 1, 1, 0))
	require.NoError(t, err)
	require.True(t, rolled.Rolled)
	require.Equal(t, thirdKey, rolled.SessionKey)
	require.Equal(t, firstKey, rolled.ClosedKey)
	require.Equal(t, int64(1), rolled.EventCount)
	require.Equal(t, int64(1), rolled.ViewCount)
	require.Equal(t, int64(0), rolled.ErrorCount)

	snap := redisHash(t, store, "ops:rum:v2:ended:"+firstKey)
	require.Equal(t, firstKey, snap["key"])
	require.Equal(t, "2", snap["events"])
	require.Equal(t, "1", snap["views"])
	require.Equal(t, "1", snap["errors"])
	require.Equal(t, "/checkout", snap["route"])
	require.Equal(t, "1.2.3", snap["version"])
	require.Equal(t, "user-1", snap["user"])
	require.Equal(t, "prod", snap["env"])
	require.Equal(t, "erase-user-1", snap["erasure_user"])
	require.Equal(t, "erase-session-1", snap["erasure_session"])
	require.Equal(t, "core", snap["tenant"])
	require.Equal(t, "storefront", snap["application"])
	require.Equal(t, "human", snap["traffic"])
	require.Equal(t, strconv.FormatInt(t0.UnixMilli(), 10), snap["first"])
	require.Equal(t, strconv.FormatInt(t0.Add(time.Second).UnixMilli(), 10), snap["last"])
	require.Equal(t, 5*time.Hour, redisPTTL(t, store, "ops:rum:v2:ended:"+firstKey))

	live = redisHash(t, store, stateKey)
	require.Equal(t, thirdKey, live["key"])
	require.Equal(t, "1", live["events"])
	require.Equal(t, "1", live["views"])
	require.Equal(t, "0", live["errors"])
	require.Equal(t, "/home", live["route"])
	require.Equal(t, "2.0.0", live["version"])
	require.Equal(t, "user-2", live["user"])
	require.Equal(t, "staging", live["env"])
	require.Equal(t, 5*time.Hour, redisPTTL(t, store, stateKey))
	require.Equal(t, float64(t0.Add(time.Second).UnixMilli()), redisScore(t, store, firstKey))
	require.Equal(t, float64(rollAt.UnixMilli()), redisScore(t, store, thirdKey))
}

func TestSessionIndexUsesLastSeenUntilMaxLengthIsSooner(t *testing.T) {
	store := newLuaStore(t)
	stateKey := "ops:rum:v2:session:max-score"
	start := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	sessionKey := "dddddddddddddddddddddddddddddddd"
	_, err := store.assign(t.Context(), countedAssignment(stateKey, start, sessionKey, "/checkout", "1.2.3", "user-1", "prod", 1, 1, 0))
	require.NoError(t, err)
	// Keep the session inside the 15 minute idle gap until it nears the 4 hour cap.
	for step := 1; step <= 22; step++ {
		at := start.Add(time.Duration(step) * 10 * time.Minute)
		kept, err := store.assign(t.Context(), countedAssignment(stateKey, at, "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "/ignored", "9.9.9", "other", "dev", 1, 0, 0))
		require.NoError(t, err)
		require.False(t, kept.Rolled)
		require.Equal(t, sessionKey, kept.SessionKey)
	}

	early := start.Add(3*time.Hour + 44*time.Minute)
	_, err = store.assign(t.Context(), countedAssignment(stateKey, early, "ffffffffffffffffffffffffffffffff", "/ignored", "9.9.9", "other", "dev", 1, 0, 0))
	require.NoError(t, err)
	require.Equal(t, float64(early.UnixMilli()), redisScore(t, store, sessionKey))

	// 03:50 is past 03:45 (start + 4h - 15m). The index score moves back to 03:45
	// so a "last activity at least 15 minutes ago" query selects this session at 04:00.
	// The hash still stores the real last activity time.
	later := start.Add(3*time.Hour + 50*time.Minute)
	_, err = store.assign(t.Context(), countedAssignment(stateKey, later, "99999999999999999999999999999999", "/ignored", "9.9.9", "other", "dev", 1, 0, 0))
	require.NoError(t, err)
	require.Equal(t, sessionKey, redisHash(t, store, stateKey)["key"])
	require.Equal(t, float64(time.Date(2026, 7, 27, 3, 45, 0, 0, time.UTC).UnixMilli()), redisScore(t, store, sessionKey))
	require.Equal(t, strconv.FormatInt(later.UnixMilli(), 10), redisHash(t, store, stateKey)["last"])
}

func TestSessionBoundariesStayAtFifteenMinutesAndFourHours(t *testing.T) {
	store := newLuaStore(t)
	start := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	firstKey := "11111111111111111111111111111111"
	opened, err := store.assign(t.Context(), countedAssignment("ops:rum:v2:session:idle", start, firstKey, "/checkout", "1", "user", "prod", 1, 0, 0))
	require.NoError(t, err)
	require.True(t, opened.Rolled)

	kept, err := store.assign(t.Context(), countedAssignment("ops:rum:v2:session:idle", start.Add(15*time.Minute-time.Millisecond), "22222222222222222222222222222222", "/other", "2", "other", "dev", 1, 0, 0))
	require.NoError(t, err)
	require.False(t, kept.Rolled)
	require.Equal(t, firstKey, kept.SessionKey)
	require.Equal(t, int64(2), kept.EventCount)

	rolled, err := store.assign(t.Context(), countedAssignment("ops:rum:v2:session:idle", start.Add(30*time.Minute-time.Millisecond), "33333333333333333333333333333333", "/new", "3", "new", "prod", 1, 0, 0))
	require.NoError(t, err)
	require.True(t, rolled.Rolled)
	require.Equal(t, "33333333333333333333333333333333", rolled.SessionKey)
	require.Equal(t, firstKey, rolled.ClosedKey)
	require.Equal(t, "2", redisHash(t, store, "ops:rum:v2:ended:"+firstKey)["events"])
	require.Equal(t, int64(1), rolled.EventCount)

	longKey := "44444444444444444444444444444444"
	longState := "ops:rum:v2:session:max"
	_, err = store.assign(t.Context(), countedAssignment(longState, start, longKey, "/checkout", "1", "user", "prod", 1, 0, 0))
	require.NoError(t, err)
	at := start
	hops := 0
	for at.Add(15*time.Minute - time.Millisecond).Before(start.Add(4 * time.Hour)) {
		at = at.Add(15*time.Minute - time.Millisecond)
		hops++
		step, err := store.assign(t.Context(), countedAssignment(longState, at, "55555555555555555555555555555555", "/other", "2", "other", "dev", 1, 0, 0))
		require.NoError(t, err)
		require.False(t, step.Rolled)
		require.Equal(t, longKey, step.SessionKey)
	}
	require.GreaterOrEqual(t, hops, 16)
	require.Less(t, at.Sub(start), 4*time.Hour)
	require.Less(t, start.Add(4*time.Hour).Sub(at), 15*time.Minute)
	capped, err := store.assign(t.Context(), countedAssignment(longState, start.Add(4*time.Hour), "66666666666666666666666666666666", "/after", "3", "after", "prod", 1, 0, 0))
	require.NoError(t, err)
	require.True(t, capped.Rolled)
	require.Equal(t, "66666666666666666666666666666666", capped.SessionKey)
	require.Equal(t, longKey, capped.ClosedKey)
	require.Equal(t, "/checkout", redisHash(t, store, "ops:rum:v2:ended:"+longKey)["route"])
	require.Equal(t, int64(1), capped.EventCount)
}

func TestReplayLogsDoNotAccumulateSessionCounts(t *testing.T) {
	store := newLuaStore(t)
	processor := newSessionizer(store)
	observed := time.Date(2026, 7, 27, 1, 0, 0, 0, time.UTC)

	ordinary := makeOrdinaryLogs("core", "storefront", "erase-session-1", "human", observed)
	decorateRum(ordinary, "view", "/checkout", "1.2.3", "user-1", "prod", "erase-user-1")
	processed, err := processor.processLogs(t.Context(), ordinary)
	require.NoError(t, err)
	sessionKey := recordAttribute(processed, "rum.session.key")

	errorLog := makeOrdinaryLogs("core", "storefront", "erase-session-1", "human", observed.Add(time.Second))
	decorateRum(errorLog, "error", "/other", "9.9.9", "user-2", "dev", "erase-user-2")
	_, err = processor.processLogs(t.Context(), errorLog)
	require.NoError(t, err)

	replay := makeReplayLogs("core", "storefront", "erase-session-1", observed.Add(2*time.Second))
	replayRecord := replay.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	replayRecord.Attributes().PutStr("rum.event.type", "view")
	replayRecord.Attributes().PutStr("rum.view.name", "/replay")
	replayRecord.Attributes().PutStr("rum.release", "replay-version")
	replayRecord.Attributes().PutStr("rum.user.id", "replay-user")
	replayRecord.Attributes().PutStr("rum.environment", "replay-env")
	replayed, err := processor.processLogs(t.Context(), replay)
	require.NoError(t, err)
	require.Equal(t, sessionKey, recordAttribute(replayed, "rum.replay.session_key"))

	live := redisHash(t, store, stateKey("core", "storefront", "erase-session-1"))
	require.Equal(t, sessionKey, live["key"])
	require.Equal(t, "2", live["events"])
	require.Equal(t, "1", live["views"])
	require.Equal(t, "1", live["errors"])
	require.Equal(t, "/checkout", live["route"])
	require.Equal(t, "1.2.3", live["version"])
	require.Equal(t, "user-1", live["user"])
	require.Equal(t, "prod", live["env"])
	require.Equal(t, strconv.FormatInt(observed.Add(2*time.Second).UnixMilli(), 10), live["last"])
}

func newLuaStore(t *testing.T) *redisSessionStore {
	t.Helper()
	server := miniredis.RunT(t)
	password := strings.Repeat("p", 32)
	server.RequireAuth(password)
	cfg := defaultConfig()
	cfg.RedisURL = "redis://:" + password + "@" + server.Addr()
	require.NoError(t, cfg.Validate())
	store, err := newRedisSessionStore(cfg)
	require.NoError(t, err)
	t.Cleanup(func() { _ = store.shutdown(t.Context()) })
	return store
}

func countedAssignment(stateKey string, observed time.Time, candidate, route, version, user, environment string, events, views, errors int64) assignment {
	return assignment{
		StateKey:          stateKey,
		ObservedAt:        observed,
		CandidateKey:      candidate,
		TrafficClass:      "human",
		EventDelta:        events,
		ViewDelta:         views,
		ErrorDelta:        errors,
		Route:             route,
		Version:           version,
		User:              user,
		Environment:       environment,
		ErasureUserKey:    "erase-user-1",
		ErasureSessionKey: "erase-session-1",
		Tenant:            "core",
		Application:       "storefront",
	}
}

func decorateRum(logs plog.Logs, eventType, route, version, user, environment, erasureUser string) {
	attrs := logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes()
	attrs.PutStr("rum.event.type", eventType)
	attrs.PutStr("rum.view.name", route)
	attrs.PutStr("rum.release", version)
	attrs.PutStr("rum.user.id", user)
	attrs.PutStr("rum.environment", environment)
	attrs.PutStr("rum.erasure.user_key", erasureUser)
}

func redisHash(t *testing.T, store *redisSessionStore, key string) map[string]string {
	t.Helper()
	values, err := store.client.HGetAll(t.Context(), key).Result()
	require.NoError(t, err)
	return values
}

func redisScore(t *testing.T, store *redisSessionStore, member string) float64 {
	t.Helper()
	score, err := store.client.ZScore(t.Context(), "ops:rum:v2:session:activity", member).Result()
	require.NoError(t, err)
	return score
}

func redisPTTL(t *testing.T, store *redisSessionStore, key string) time.Duration {
	t.Helper()
	ttl, err := store.client.PTTL(t.Context(), key).Result()
	require.NoError(t, err)
	return ttl
}

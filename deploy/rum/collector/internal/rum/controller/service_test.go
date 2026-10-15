package controller

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func TestRetiredApplicationSubjects(t *testing.T) {
	service, _ := newTestService(t)
	for _, subject := range []string{
		SubjectApplicationApply,
		SubjectApplicationRotate,
		SubjectApplicationRetire,
		SubjectApplicationDisable,
	} {
		response := handleResponse(t, service, subject, requestBytes(t, "req-retired", "idem-retired", nil, map[string]any{}))
		require.NotNil(t, response.Error)
		require.Equal(t, ErrorInvalidArgument, response.Error.Code)
		require.Equal(t, "subject retired", response.Error.Message)
	}
}

func TestProjectionApplyIgnoresStaleRevision(t *testing.T) {
	service, client := newTestService(t)
	first := handleResponse(t, service, SubjectProjectionApply, requestBytes(t, "req-project", "idem-project", nil, projectionPayload("storefront", "browser-key-current", 2, true)))
	require.Nil(t, first.Error)
	require.Equal(t, int64(2), first.Revision)
	require.NoError(t, client.HSet(t.Context(), "ops:rum:v2:app:storefront", "last_accepted_at", 1700, "last_stored_at", 1701).Err())
	require.NoError(t, client.SAdd(t.Context(), "ops:rum:v2:app:storefront:key_material", "browser-key-current").Err())

	stale := handleResponse(t, service, SubjectProjectionApply, requestBytes(t, "req-stale", "idem-stale", nil, projectionPayload("storefront", "browser-key-current", 2, false)))
	require.Nil(t, stale.Error)
	require.Equal(t, "stale", stale.Data.(map[string]any)["status"])
	state, err := service.store.GetApplication(t.Context(), "storefront")
	require.NoError(t, err)
	require.True(t, state.Enabled)
	require.Equal(t, int64(2), state.Revision)
	require.Equal(t, []string{"browser-key-current"}, client.SMembers(t.Context(), "ops:rum:v2:app:storefront:key_material").Val())

	applied := handleResponse(t, service, SubjectProjectionApply, requestBytes(t, "req-next", "idem-next", nil, projectionPayload("storefront", "browser-key-next-0001", 3, false)))
	require.Nil(t, applied.Error)
	require.Equal(t, int64(3), applied.Revision)
	state, err = service.store.GetApplication(t.Context(), "storefront")
	require.NoError(t, err)
	require.False(t, state.Enabled)
	require.Equal(t, int64(1700), state.LastAcceptedAt)
	require.Equal(t, int64(1701), state.LastStoredAt)
	require.Equal(t, []string{ingress.KeyDigest("browser-key-next-0001")}, state.BrowserKeyDigests)
	require.Empty(t, client.SMembers(t.Context(), "ops:rum:v2:app:storefront:key_material").Val())
}

func TestProjectionReconcileDeletesExtrasAndReportsGaps(t *testing.T) {
	service, client := newTestService(t)
	applyProjection(t, service, "storefront", "browser-key-current", 1)
	applyProjection(t, service, "legacy", "browser-key-current", 1)
	require.NoError(t, client.Set(t.Context(), "ops:rum:v2:erasure:fence:v9:"+strings.Repeat("ab", 32), "1", 0).Err())

	response := handleResponse(t, service, SubjectProjectionReconcile, requestBytes(t, "req-reconcile", "idem-reconcile", nil, ProjectionReconcilePayload{
		Applications: []ProjectionRevision{
			{Application: "storefront", Revision: 4},
			{Application: "catalog", Revision: 1},
		},
		Fences: []ProjectionFence{{
			Application: "storefront",
			Identities:  []ErasureIdentity{{Kind: "user", Value: "user-42"}},
		}},
	}))
	require.Nil(t, response.Error)
	require.Equal(t, []any{"catalog", "storefront"}, response.Data.(map[string]any)["staleApplications"])
	require.Equal(t, int64(0), client.Exists(t.Context(), "ops:rum:v2:app:legacy").Val())
	require.Equal(t, int64(1), client.Exists(t.Context(), "ops:rum:v2:app:storefront").Val())
	require.Equal(t, int64(0), client.Exists(t.Context(), "ops:rum:v2:erasure:fence:v9:"+strings.Repeat("ab", 32)).Val())
	require.NotEmpty(t, client.Keys(t.Context(), "ops:rum:v2:erasure:fence:*").Val())
}

func TestProjectionReconcileForceOverwritesAheadRevision(t *testing.T) {
	service, client := newTestService(t)
	applyProjection(t, service, "storefront", "browser-key-current", 5)
	require.NoError(t, client.SAdd(t.Context(), "ops:rum:v2:app:storefront:key_material", "browser-key-current").Err())

	reported := handleResponse(t, service, SubjectProjectionReconcile, requestBytes(t, "req-ahead", "idem-ahead", nil, ProjectionReconcilePayload{
		Applications: []ProjectionRevision{{Application: "storefront", Revision: 2}},
	}))
	require.Nil(t, reported.Error)
	require.Equal(t, []any{"storefront"}, reported.Data.(map[string]any)["staleApplications"])
	require.Equal(t, "5", client.HGet(t.Context(), "ops:rum:v2:app:storefront", "revision").Val())

	older := projectionPayload("storefront", "browser-key-current", 2, true)
	rejected := handleResponse(t, service, SubjectProjectionApply, requestBytes(t, "req-older", "idem-older", nil, older))
	require.Nil(t, rejected.Error)
	require.Equal(t, "stale", rejected.Data.(map[string]any)["status"])
	require.Equal(t, "5", client.HGet(t.Context(), "ops:rum:v2:app:storefront", "revision").Val())

	forced := older
	forced.Force = true
	forced.BrowserKeyDigests = []string{ingress.KeyDigest("browser-key-next-0001")}
	applied := handleResponse(t, service, SubjectProjectionApply, requestBytes(t, "req-force", "idem-force", nil, forced))
	require.Nil(t, applied.Error)
	require.Equal(t, int64(2), applied.Revision)
	require.Equal(t, "2", client.HGet(t.Context(), "ops:rum:v2:app:storefront", "revision").Val())
	require.Empty(t, client.SMembers(t.Context(), "ops:rum:v2:app:storefront:key_material").Val())
	require.Equal(t, []string{ingress.KeyDigest("browser-key-next-0001")}, client.SMembers(t.Context(), "ops:rum:v2:app:storefront:keys").Val())
}

func TestProjectionReconcileKeepsAppsWhenCatalogIsEmpty(t *testing.T) {
	service, client := newTestService(t)
	applyProjection(t, service, "legacy", "browser-key-current", 4)

	response := handleResponse(t, service, SubjectProjectionReconcile, requestBytes(t, "req-empty", "idem-empty", nil, ProjectionReconcilePayload{}))
	require.Nil(t, response.Error)
	require.Empty(t, response.Data.(map[string]any)["staleApplications"])
	require.Equal(t, int64(1), client.Exists(t.Context(), "ops:rum:v2:app:legacy").Val())
	require.Equal(t, "4", client.HGet(t.Context(), "ops:rum:v2:app:legacy", "revision").Val())
}

func TestFenceReleaseDeletesKeys(t *testing.T) {
	service, client := newTestService(t)
	applyProjection(t, service, "storefront", "browser-key-current", 1)
	expected := int64(1)
	submitted := handleResponse(t, service, SubjectErasureSubmit, requestBytes(t, "req-erase", "idem-erase", &expected, ErasureSubmitPayload{
		Application: "storefront",
		Identities:  []ErasureIdentity{{Kind: "user", Value: "user-42"}},
	}))
	require.Nil(t, submitted.Error)
	require.NotEmpty(t, client.Keys(t.Context(), "ops:rum:v2:erasure:fence:*").Val())

	released := handleResponse(t, service, SubjectErasureFenceRelease, requestBytes(t, "req-release", "idem-release", nil, ErasureSubmitPayload{
		Application: "storefront",
		Identities:  []ErasureIdentity{{Kind: "user", Value: "user-42"}},
	}))
	require.Nil(t, released.Error)
	require.Empty(t, client.Keys(t.Context(), "ops:rum:v2:erasure:fence:*").Val())
}

func TestApplicationListReturnsFullKeysAndEvidenceMarkers(t *testing.T) {
	service, client := newTestService(t)
	applyApplication(t, service)

	now := int64(1754388000)
	require.NoError(t, client.HSet(
		t.Context(),
		"ops:rum:v2:app:storefront",
		"last_accepted_at",
		now,
		"last_stored_at",
		now+1,
	).Err())

	list := handleResponse(
		t,
		service,
		SubjectApplicationList,
		requestBytes(t, "req-list", "idem-list", nil, struct{}{}),
	)
	require.Nil(t, list.Error)
	rows, ok := list.Data.([]any)
	require.True(t, ok)
	require.Len(t, rows, 1)
	row := rows[0].(map[string]any)
	require.Equal(t, "storefront", row["application"])
	keys, ok := row["browserKeys"].([]any)
	require.True(t, ok)
	require.Empty(t, keys)
	digests, ok := row["browserKeyDigests"].([]any)
	require.True(t, ok)
	require.Equal(t, []any{ingress.KeyDigest("browser-key-current")}, digests)
	require.Equal(t, float64(now), row["lastAcceptedAt"])
	require.Equal(t, float64(now+1), row["lastStoredAt"])

	get := handleResponse(
		t,
		service,
		SubjectApplicationGet,
		requestBytes(t, "req-get", "idem-get", nil, ApplicationPayload{Application: "storefront"}),
	)
	require.Nil(t, get.Error)
	view, ok := get.Data.(map[string]any)
	require.True(t, ok)
	keys, ok = view["browserKeys"].([]any)
	require.True(t, ok)
	require.Empty(t, keys)

	state, err := service.store.GetApplication(t.Context(), "storefront")
	require.NoError(t, err)
	require.Empty(t, state.BrowserKeys)
	require.Equal(t, []string{ingress.KeyDigest("browser-key-current")}, state.BrowserKeyDigests)
	require.Equal(t, now, state.LastAcceptedAt)
	require.Equal(t, now+1, state.LastStoredAt)
	require.Empty(t, client.SMembers(t.Context(), "ops:rum:v2:app:storefront:key_material").Val())
}

func TestApplicationListFiltersSubKeysAndReplacesKeyMaterialOnApply(t *testing.T) {
	service, client := newTestService(t)
	applyApplication(t, service)
	require.NoError(t, client.SAdd(t.Context(), "ops:rum:v2:app:storefront:key_material", "browser-key-current").Err())
	response := handleResponse(
		t,
		service,
		SubjectProjectionApply,
		requestBytes(t, "req-replace", "idem-replace", nil, projectionPayload("storefront", "browser-key-next-0001", 2, true)),
	)
	require.Nil(t, response.Error)
	require.Empty(t, client.SMembers(t.Context(), "ops:rum:v2:app:storefront:key_material").Val())

	list := handleResponse(
		t,
		service,
		SubjectApplicationList,
		requestBytes(t, "req-list", "idem-list", nil, struct{}{}),
	)
	require.Nil(t, list.Error)
	rows, ok := list.Data.([]any)
	require.True(t, ok)
	require.Len(t, rows, 1)
	require.Equal(t, "storefront", rows[0].(map[string]any)["application"])
}

func TestErasureSubmissionStoresOnlyHashesAndSurvivesNATSIndependently(t *testing.T) {
	service, client := newTestService(t)
	applyApplication(t, service)
	expected := int64(1)
	response := handleResponse(
		t,
		service,
		SubjectErasureSubmit,
		requestBytes(t, "req-erase", "idem-erase", &expected, ErasureSubmitPayload{
			Application: "storefront",
			Identities: []ErasureIdentity{
				{Kind: "user", Value: "user-42"},
				{Kind: "session", Value: "session-7"},
			},
		}),
	)
	require.Nil(t, response.Error)
	require.NotEmpty(t, response.OperationID)

	operation, err := service.store.GetOperation(t.Context(), response.OperationID)
	require.NoError(t, err)
	require.Equal(t, "pending", operation.Status)
	require.Equal(t, "erasure", operation.Type)

	stream, err := client.XRangeN(t.Context(), ErasureStreamKey, "-", "+", 1).Result()
	require.NoError(t, err)
	require.Len(t, stream, 1)
	serialized, err := json.Marshal(stream[0].Values)
	require.NoError(t, err)
	require.NotContains(t, string(serialized), "user-42")
	require.NotContains(t, string(serialized), "session-7")
	require.Contains(t, string(serialized), response.OperationID)

	for _, key := range client.Keys(t.Context(), "ops:rum:v2:erasure:fence:*").Val() {
		require.Greater(t, client.TTL(t.Context(), key).Val(), 16*24*time.Hour)
		_, err := client.ZScore(t.Context(), key, "fence").Result()
		require.NoError(t, err)
	}
}

func newTestService(t *testing.T) (*Service, *redis.Client) {
	t.Helper()
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	store := newStoreWithClient(client, StoreConfig{
		CommandTTL:          24 * time.Hour,
		FenceTTL:            17 * 24 * time.Hour,
		CurrentHMACSecret:   "current-erasure-secret-at-least-32-bytes",
		CurrentHMACVersion:  "v1",
		PreviousHMACSecret:  "previous-erasure-secret-at-least-32-bytes",
		PreviousHMACVersion: "v0",
		Now: func() time.Time {
			return time.Date(2026, 8, 5, 10, 0, 0, 0, time.UTC)
		},
		NewOperationID: func() string { return "op-fixed-01" },
	})
	service, err := NewService(store, "tenant-a")
	require.NoError(t, err)
	return service, client
}

func requestBytes(t *testing.T, requestID, idempotencyKey string, expected *int64, payload any) []byte {
	t.Helper()
	raw, err := json.Marshal(payload)
	require.NoError(t, err)
	encoded, err := json.Marshal(RequestEnvelope{
		APIVersion:       APIVersion,
		RequestID:        requestID,
		IdempotencyKey:   idempotencyKey,
		ExpectedRevision: expected,
		Actor:            "operator@example.test",
		Payload:          raw,
	})
	require.NoError(t, err)
	return encoded
}

func handleResponse(t *testing.T, service *Service, subject string, request []byte) ResponseEnvelope {
	t.Helper()
	raw := service.Handle(t.Context(), subject, request)
	var response ResponseEnvelope
	require.NoError(t, json.Unmarshal(raw, &response))
	require.NotEmpty(t, response.RequestID)
	return response
}

func applyApplication(t *testing.T, service *Service) {
	t.Helper()
	applyProjection(t, service, "storefront", "browser-key-current", 1)
}

func applyProjection(t *testing.T, service *Service, name, browserKey string, revision int64) {
	t.Helper()
	response := handleResponse(
		t,
		service,
		SubjectProjectionApply,
		requestBytes(t, "req-seed-"+name, "idem-seed-"+name, nil, projectionPayload(name, browserKey, revision, true)),
	)
	require.Nil(t, response.Error)
}

func projectionPayload(name, browserKey string, revision int64, enabled bool) ProjectionApplyPayload {
	return ProjectionApplyPayload{
		Application:       name,
		TenantID:          "tenant-a",
		OrgID:             "org-1",
		Enabled:           enabled,
		Revision:          revision,
		BrowserKeyDigests: []string{ingress.KeyDigest(browserKey)},
		Origins:           []string{"https://app.example.test"},
		Budgets: Budgets{
			RequestsPerMinute:          100,
			CompressedBytesPerMinute:   1_000_000,
			DecompressedBytesPerMinute: 4_000_000,
			EventsPerMinute:            1_000,
		},
	}
}

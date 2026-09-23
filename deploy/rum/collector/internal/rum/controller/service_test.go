package controller

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func TestApplicationCommandsAreRevisionedDurableAndIdempotent(t *testing.T) {
	service, client, durableCalls := newTestService(t)
	apply := ApplicationApplyPayload{
		Application: "storefront",
		OrgID:       "org-1",
		Enabled:     true,
		BrowserKeys: []string{"browser-key-current"},
		Origins:     []string{"https://app.example.test"},
		Budgets: Budgets{
			RequestsPerMinute:          100,
			CompressedBytesPerMinute:   1_000_000,
			DecompressedBytesPerMinute: 4_000_000,
			EventsPerMinute:            1_000,
		},
	}
	expected := int64(0)
	request := requestBytes(t, "req-apply-1", "idem-apply-1", &expected, apply)

	first := handleResponse(t, service, SubjectApplicationApply, request)
	require.Nil(t, first.Error)
	require.Equal(t, int64(1), first.Revision)
	require.Equal(t, 1, *durableCalls)

	state, err := service.store.GetApplication(t.Context(), "storefront")
	require.NoError(t, err)
	require.Equal(t, int64(1), state.Revision)
	require.Len(t, state.BrowserKeyDigests, 1)
	require.NotContains(t, state.BrowserKeyDigests[0], "browser-key-current")

	retryRequest := requestBytes(t, "req-apply-retry", "idem-apply-1", &expected, apply)
	retry := handleResponse(t, service, SubjectApplicationApply, retryRequest)
	require.Nil(t, retry.Error)
	require.Equal(t, "req-apply-retry", retry.RequestID)
	require.Equal(t, int64(1), retry.Revision)
	require.Equal(t, 2, *durableCalls)
	require.Equal(t, int64(1), client.XLen(t.Context(), ControlAuditStreamKey).Val())

	conflicting := apply
	conflicting.Enabled = false
	conflict := handleResponse(
		t,
		service,
		SubjectApplicationApply,
		requestBytes(t, "req-conflict", "idem-apply-1", &expected, conflicting),
	)
	require.Equal(t, ErrorIdempotencyConflict, conflict.Error.Code)

	require.Equal(t, "1", client.HGet(t.Context(), "ops:rum:v2:app:storefront", "revision").Val())
	require.Greater(t, client.TTL(t.Context(), "ops:rum:v2:commands:idem-apply-1").Val(), 23*time.Hour)
}

func TestApplicationApplyRejectsOrganizationTakeover(t *testing.T) {
	service, client, _ := newTestService(t)
	apply := applyApplicationPayload("storefront", "browser-key-current", []string{"https://app.example.test"})
	expected := int64(0)
	first := handleResponse(t, service, SubjectApplicationApply, requestBytes(t, "req-apply-org", "idem-apply-org", &expected, apply))
	require.Nil(t, first.Error)
	require.Equal(t, "org-1", client.HGet(t.Context(), "ops:rum:v2:app:storefront", "org_id").Val())

	// Another organization must not take over the deployment-wide name: the
	// apply is rejected before keys, origins, or admission state change.
	takeover := apply
	takeover.OrgID = "org-2"
	takeover.BrowserKeys = []string{"browser-key-hostile"}
	expectedNext := int64(1)
	rejected := handleResponse(t, service, SubjectApplicationApply, requestBytes(t, "req-apply-takeover", "idem-apply-takeover", &expectedNext, takeover))
	require.NotNil(t, rejected.Error)
	require.Equal(t, ErrorOrgConflict, rejected.Error.Code)
	require.Equal(t, "org-1", rejected.Error.Fields["existingOrg"])

	state, err := service.store.GetApplication(t.Context(), "storefront")
	require.NoError(t, err)
	require.Equal(t, "org-1", state.OrgID)
	require.Len(t, state.BrowserKeys, 1)
	require.Contains(t, state.BrowserKeys, "browser-key-current")

	// The owning organization can still re-apply normally.
	second := handleResponse(t, service, SubjectApplicationApply, requestBytes(t, "req-apply-ok", "idem-apply-ok", &expectedNext, apply))
	require.Nil(t, second.Error)
	require.Equal(t, int64(2), second.Revision)
}

func TestApplicationRotationRetirementAndDisableAreAtomic(t *testing.T) {
	service, client, durableCalls := newTestService(t)
	applyApplication(t, service)

	expected := int64(1)
	rotatePayload := ApplicationRotatePayload{
		Application: "storefront",
		BrowserKey:  "browser-key-next-0001",
	}
	rotate := handleResponse(
		t,
		service,
		SubjectApplicationRotate,
		requestBytes(t, "req-rotate", "idem-rotate", &expected, rotatePayload),
	)
	require.Nil(t, rotate.Error)
	require.Equal(t, int64(2), rotate.Revision)
	require.Equal(t, 2, *durableCalls)

	retry := handleResponse(
		t,
		service,
		SubjectApplicationRotate,
		requestBytes(t, "req-rotate-retry", "idem-rotate", &expected, rotatePayload),
	)
	require.Nil(t, retry.Error)
	require.Equal(t, "req-rotate-retry", retry.RequestID)
	require.Equal(t, int64(2), retry.Revision)
	require.Equal(t, 3, *durableCalls)
	require.Equal(t, int64(2), client.XLen(t.Context(), ControlAuditStreamKey).Val())

	conflictingRetry := handleResponse(
		t,
		service,
		SubjectApplicationRotate,
		requestBytes(t, "req-rotate-conflict", "idem-rotate", &expected, ApplicationRotatePayload{
			Application: "storefront",
			BrowserKey:  "browser-key-different-0001",
		}),
	)
	require.Equal(t, ErrorIdempotencyConflict, conflictingRetry.Error.Code)
	require.Equal(t, 3, *durableCalls)

	state, err := service.store.GetApplication(t.Context(), "storefront")
	require.NoError(t, err)
	require.Len(t, state.BrowserKeyDigests, 2)

	expected = 2
	third := handleResponse(
		t,
		service,
		SubjectApplicationRotate,
		requestBytes(t, "req-third", "idem-third", &expected, ApplicationRotatePayload{
			Application: "storefront",
			BrowserKey:  "browser-key-third-0001",
		}),
	)
	require.Equal(t, ErrorInvalidArgument, third.Error.Code)

	expected = 2
	retire := handleResponse(
		t,
		service,
		SubjectApplicationRetire,
		requestBytes(t, "req-retire", "idem-retire", &expected, ApplicationRetirePayload{
			Application: "storefront",
			BrowserKey:  "browser-key-current",
		}),
	)
	require.Nil(t, retire.Error)
	require.Equal(t, int64(3), retire.Revision)

	expected = 2
	stale := handleResponse(
		t,
		service,
		SubjectApplicationDisable,
		requestBytes(t, "req-stale", "idem-stale", &expected, ApplicationPayload{Application: "storefront"}),
	)
	require.Equal(t, ErrorRevisionConflict, stale.Error.Code)
	require.Equal(t, "3", stale.Error.Fields["actualRevision"])

	expected = 3
	disabled := handleResponse(
		t,
		service,
		SubjectApplicationDisable,
		requestBytes(t, "req-disable", "idem-disable", &expected, ApplicationPayload{Application: "storefront"}),
	)
	require.Nil(t, disabled.Error)
	require.Equal(t, int64(4), disabled.Revision)
	state, err = service.store.GetApplication(t.Context(), "storefront")
	require.NoError(t, err)
	require.False(t, state.Enabled)
}

func TestApplicationListReturnsFullKeysAndEvidenceMarkers(t *testing.T) {
	service, client, _ := newTestService(t)
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
	require.Equal(t, []any{"browser-key-current"}, keys)
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
	require.Equal(t, []any{"browser-key-current"}, keys)

	state, err := service.store.GetApplication(t.Context(), "storefront")
	require.NoError(t, err)
	require.Equal(t, []string{"browser-key-current"}, state.BrowserKeys)
	require.Len(t, state.BrowserKeyDigests, 1)
	require.NotContains(t, state.BrowserKeyDigests[0], "browser-key-current")
	require.Equal(t, now, state.LastAcceptedAt)
	require.Equal(t, now+1, state.LastStoredAt)

	require.Equal(t, []string{"browser-key-current"}, client.SMembers(
		t.Context(),
		"ops:rum:v2:app:storefront:key_material",
	).Val())
}

func TestApplicationListFiltersSubKeysAndReplacesKeyMaterialOnApply(t *testing.T) {
	service, client, _ := newTestService(t)
	applyApplication(t, service)

	replaced := applyApplicationPayload("storefront", "browser-key-next-0001", []string{"https://app.example.test"})
	expected := int64(1)
	response := handleResponse(
		t,
		service,
		SubjectApplicationApply,
		requestBytes(t, "req-replace", "idem-replace", &expected, replaced),
	)
	require.Nil(t, response.Error)

	require.Equal(t, []string{"browser-key-next-0001"}, client.SMembers(
		t.Context(),
		"ops:rum:v2:app:storefront:key_material",
	).Val())

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
	service, client, _ := newTestService(t)
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

func newTestService(t *testing.T) (*Service, *redis.Client, *int) {
	t.Helper()
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	durableCalls := 0
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
	store.waitDurable = func(context.Context) error {
		durableCalls++
		return nil
	}
	service, err := NewService(store, "tenant-a")
	require.NoError(t, err)
	return service, client, &durableCalls
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
	expected := int64(0)
	response := handleResponse(
		t,
		service,
		SubjectApplicationApply,
		requestBytes(
			t,
			"req-seed",
			"idem-seed",
			&expected,
			applyApplicationPayload("storefront", "browser-key-current", []string{"https://app.example.test"}),
		),
	)
	require.Nil(t, response.Error)
}

func applyApplicationPayload(name, browserKey string, origins []string) ApplicationApplyPayload {
	return ApplicationApplyPayload{
		Application: name,
		OrgID:       "org-1",
		Enabled:     true,
		BrowserKeys: []string{browserKey},
		Origins:     origins,
		Budgets: Budgets{
			RequestsPerMinute:          100,
			CompressedBytesPerMinute:   1_000_000,
			DecompressedBytesPerMinute: 4_000_000,
			EventsPerMinute:            1_000,
		},
	}
}

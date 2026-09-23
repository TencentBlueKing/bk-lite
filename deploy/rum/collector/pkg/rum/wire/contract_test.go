package wire

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestControlSubjectsAreVersionedAndIsolated(t *testing.T) {
	require.Equal(t, "rum.v1.control.application.apply", SubjectApplicationApply)
	require.Equal(t, "rum.v1.control.application.get", SubjectApplicationGet)
	require.Equal(t, "rum.v1.control.application.rotate", SubjectApplicationRotate)
	require.Equal(t, "rum.v1.control.application.retire", SubjectApplicationRetire)
	require.Equal(t, "rum.v1.control.application.disable", SubjectApplicationDisable)
	require.Equal(t, "rum.v1.control.erasure.submit", SubjectErasureSubmit)
	require.Equal(t, "rum.v1.control.reconcile.submit", SubjectReconcileSubmit)
	require.Equal(t, "rum.v1.control.operation.get", SubjectOperationGet)
	require.Equal(t, "rum.v1.control.status.get", SubjectStatusGet)
	for _, subject := range AllSubjects {
		require.Contains(t, subject, "rum.v1.control.")
		require.NotContains(t, subject, "agents.v1.")
		require.NotContains(t, subject, "otel.v1.")
	}
}

func TestDecodeRequestRequiresStrictVersionedEnvelope(t *testing.T) {
	valid := []byte(`{
		"apiVersion":"rum.control/v1",
		"requestId":"req-01",
		"idempotencyKey":"idem-01",
		"expectedRevision":3,
		"actor":"operator@example.test",
		"payload":{"application":"storefront"}
	}`)
	request, err := DecodeRequest(valid)
	require.NoError(t, err)
	require.Equal(t, APIVersion, request.APIVersion)
	require.Equal(t, int64(3), *request.ExpectedRevision)

	for name, mutate := range map[string]func(map[string]any){
		"wrong version":           func(value map[string]any) { value["apiVersion"] = "rum.control/v2" },
		"missing request id":      func(value map[string]any) { delete(value, "requestId") },
		"missing idempotency key": func(value map[string]any) { delete(value, "idempotencyKey") },
		"missing actor":           func(value map[string]any) { delete(value, "actor") },
		"unknown field":           func(value map[string]any) { value["tenant"] = "spoofed" },
	} {
		t.Run(name, func(t *testing.T) {
			var value map[string]any
			require.NoError(t, json.Unmarshal(valid, &value))
			mutate(value)
			encoded, err := json.Marshal(value)
			require.NoError(t, err)
			_, err = DecodeRequest(encoded)
			require.Error(t, err)
		})
	}
}

func TestApplicationPayloadRejectsImplicitBudgetsAndUnsafeOrigins(t *testing.T) {
	payload := ApplicationApplyPayload{
		Application: "storefront",
		OrgID:       "org-1",
		Enabled:     true,
		BrowserKeys: []string{"browser-key-at-least-sixteen"},
		Origins:     []string{"https://app.example.test"},
		Budgets: Budgets{
			RequestsPerMinute:          100,
			CompressedBytesPerMinute:   1_000_000,
			DecompressedBytesPerMinute: 4_000_000,
			EventsPerMinute:            1_000,
		},
	}
	require.NoError(t, payload.Validate())

	withoutOrg := payload
	withoutOrg.OrgID = ""
	require.ErrorContains(t, withoutOrg.Validate(), "organization")

	withoutBudget := payload
	withoutBudget.Budgets.EventsPerMinute = 0
	require.ErrorContains(t, withoutBudget.Validate(), "budgets")

	wildcardOrigin := payload
	wildcardOrigin.Origins = []string{"https://*.example.test"}
	require.ErrorContains(t, wildcardOrigin.Validate(), "origin")

	tooManyKeys := payload
	tooManyKeys.BrowserKeys = []string{
		"browser-key-at-least-sixteen-a",
		"browser-key-at-least-sixteen-b",
		"browser-key-at-least-sixteen-c",
	}
	require.ErrorContains(t, tooManyKeys.Validate(), "browser keys")

	duplicateKeys := payload
	duplicateKeys.BrowserKeys = []string{
		"browser-key-at-least-sixteen",
		"browser-key-at-least-sixteen",
	}
	require.ErrorContains(t, duplicateKeys.Validate(), "unique")

	duplicateOrigins := payload
	duplicateOrigins.Origins = []string{
		"https://app.example.test",
		"https://app.example.test",
	}
	require.ErrorContains(t, duplicateOrigins.Validate(), "unique")

	tooLongApplication := payload
	tooLongApplication.Application = strings.Repeat("a", 81)
	require.ErrorContains(t, tooLongApplication.Validate(), "application")
}

func TestFingerprintIgnoresRequestIDButBindsSubjectActorAndPayload(t *testing.T) {
	expected := int64(4)
	first := RequestEnvelope{
		APIVersion:       APIVersion,
		RequestID:        "req-1",
		IdempotencyKey:   "idem-1",
		ExpectedRevision: &expected,
		Actor:            "operator@example.test",
		Payload:          json.RawMessage(`{"application":"storefront"}`),
	}
	second := first
	second.RequestID = "req-2"
	require.Equal(t, Fingerprint(SubjectApplicationDisable, first), Fingerprint(SubjectApplicationDisable, second))

	second.Actor = "other@example.test"
	require.NotEqual(t, Fingerprint(SubjectApplicationDisable, first), Fingerprint(SubjectApplicationDisable, second))
	require.NotEqual(t, Fingerprint(SubjectApplicationGet, first), Fingerprint(SubjectApplicationDisable, first))
}

func TestResponseEnvelopeUsesFixedErrorCodes(t *testing.T) {
	for _, code := range []ErrorCode{
		ErrorInvalidArgument,
		ErrorNotFound,
		ErrorRevisionConflict,
		ErrorIdempotencyConflict,
		ErrorForbidden,
		ErrorUnavailable,
		ErrorInternal,
	} {
		response := ErrorResponse("req-1", code, "failed", map[string]string{"field": "reason"})
		encoded, err := json.Marshal(response)
		require.NoError(t, err)
		require.Contains(t, string(encoded), `"code":"`+string(code)+`"`)
	}
}

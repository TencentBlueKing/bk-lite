package farorumreceiver

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"

	faro "github.com/grafana/faro/pkg/go"
	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"github.com/bk-lite/rum-collector/internal/rumprivacy"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/consumer/consumertest"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.opentelemetry.io/collector/receiver/receivertest"
)

var fixedObservedAt = time.Date(2026, 7, 15, 10, 0, 0, 0, time.UTC)

const testIdentityHMACSecret = "test-rum-erasure-hmac-secret-at-least-32-bytes"
const testBrowserKey = "core-rum-browser-e2e"
const testTenantID = "tenant-a"
const testCredentialLookup = "b21d328cf994d78f"

func TestConfigRequiresIdentitySecretAndAdmissionRedis(t *testing.T) {
	cfg := defaultConfig()
	require.ErrorContains(t, cfg.Validate(), "identity_hmac_secret")

	cfg.IdentityHMACSecret = testIdentityHMACSecret
	require.ErrorContains(t, cfg.Validate(), "admission_redis_url")

	cfg.AdmissionRedisURL = "redis://rum-admission:test-secret-password-at-least-32-chars@127.0.0.1:6379"
	require.NoError(t, cfg.Validate())

	cfg.IdentityHMACPrevious = "short"
	require.ErrorContains(t, cfg.Validate(), "identity_hmac_previous_secret")
}

func TestCollectChecksCurrentAndPreviousErasureFenceIdentities(t *testing.T) {
	r, _, _ := newTestReceiver(t)
	r.cfg.IdentityHMACPrevious = "previous-rum-erasure-hmac-secret-at-least-32-bytes"
	r.cfg.IdentityHMACPrevVer = "v0"

	fences := r.identityFences("user", "user-42")

	require.Len(t, fences, 2)
	require.Equal(t, []string{"v1", "v0"}, []string{fences[0].Version, fences[1].Version})
	require.NotEqual(t, fences[0].Digest, fences[1].Digest)
}

func TestFactoryIsRegistrableAndSharesSignals(t *testing.T) {
	factory := NewFactory()
	require.Equal(t, "faro", factory.Type().String())

	cfg := factory.CreateDefaultConfig().(*Config)
	cfg.Endpoint = "127.0.0.1:0"
	cfg.IdentityHMACSecret = testIdentityHMACSecret
	cfg.AdmissionRedisURL = "redis://rum-admission:test-secret-password-at-least-32-chars@127.0.0.1:1"
	settings := receivertest.NewNopSettings(factory.Type())

	logsReceiver, err := factory.CreateLogs(t.Context(), settings, cfg, new(consumertest.LogsSink))
	require.NoError(t, err)
	tracesReceiver, err := factory.CreateTraces(t.Context(), settings, cfg, new(consumertest.TracesSink))
	require.NoError(t, err)
	require.Same(t, logsReceiver, tracesReceiver)

	require.NoError(t, logsReceiver.Shutdown(t.Context()))
	require.NoError(t, tracesReceiver.Shutdown(t.Context()))
}

func TestCollectRejectsMissingBrowserKey(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	body := []byte(`{"meta":{"app":{"name":"storefront"}},"events":[{"name":"view_changed"}]}`)
	headers := validHeaders()
	delete(headers, headerAPIKey)

	response := performCollect(r, body, headers)
	require.Equal(t, http.StatusUnauthorized, response.Code)
	require.Empty(t, logsSink.AllLogs())
	require.Empty(t, tracesSink.AllTraces())
}

func TestCollectRejectsUnknownApplicationFailClosed(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	body := []byte(`{"meta":{"app":{"name":"not-registered"}},"events":[{"name":"view_changed"}]}`)
	headers := validHeaders()
	headers[headerApplication] = "not-registered"

	response := performCollect(r, body, headers)

	require.Equal(t, http.StatusForbidden, response.Code)
	require.Empty(t, logsSink.AllLogs())
	require.Empty(t, tracesSink.AllTraces())
}

func TestCollectAcceptsOneFaroBatchWithOrdinaryAndTraceSignals(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	payload := faro.Payload{
		Events: []faro.Event{{Name: "view_changed", Timestamp: fixedObservedAt}},
		Traces: &faro.Traces{Traces: oneSpanTrace("client-tenant")},
	}
	payload.Meta.App.Name = "storefront"
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, logsSink.AllLogs(), 1)
	require.Len(t, tracesSink.AllTraces(), 1)
}

func TestCollectOptionsPublishesFixedBrowserCORSContract(t *testing.T) {
	r, _, _ := newTestReceiver(t)
	request := httptest.NewRequest(http.MethodOptions, collectPath, nil)
	response := httptest.NewRecorder()

	r.handleCollect(response, request)

	require.Equal(t, http.StatusNoContent, response.Code)
	require.Equal(t, "*", response.Header().Get("Access-Control-Allow-Origin"))
	require.Equal(t, "POST, OPTIONS", response.Header().Get("Access-Control-Allow-Methods"))
	require.Equal(
		t,
		"Content-Type, Content-Encoding, X-API-Key, X-RUM-Application, X-RUM-Batch-Id",
		response.Header().Get("Access-Control-Allow-Headers"),
	)
	require.Empty(t, response.Header().Get("Access-Control-Allow-Credentials"))
}

func TestCollectMapsBrowserUserAgentOntoResource(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{
			"app":{"name":"storefront"},
			"browser":{"name":"Chrome","version":"126.0.0","userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36","os":"Mac OS 14.5","language":"en-US","mobile":false}
		},
		"events":[{"name":"view_changed","timestamp":"2026-07-15T10:00:00Z"}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, logsSink.AllLogs(), 1)
	resource := logsSink.AllLogs()[0].ResourceLogs().At(0).Resource().Attributes()
	ua, ok := resource.Get("user_agent.original")
	require.True(t, ok)
	require.Contains(t, ua.Str(), "Chrome/126.0.0.0")
}

func TestCollectBindsTrustedCredentialApplicationAndAcceptedParseEvidence(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{"meta":{"app":{"name":"storefront"}},"events":[{"name":"view_changed","timestamp":"2026-07-15T10:00:00Z"}]}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, logsSink.AllLogs(), 1)
	logs := logsSink.AllLogs()[0]
	resource := logs.ResourceLogs().At(0).Resource().Attributes()
	lookup, ok := resource.Get("rum.credential.lookup_id")
	require.True(t, ok)
	require.Equal(t, testCredentialLookup, lookup.Str())
	require.Equal(t, 2, logs.ResourceLogs().At(0).ScopeLogs().Len())
	require.Eventually(t, func() bool {
		return hasParseEvidence(logsSink.AllLogs(), "accepted", "ok")
	}, time.Second, 10*time.Millisecond)
}

func TestCollectRejectsApplicationMismatchBeforeWritingAnyTelemetry(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	body := []byte(`{"meta":{"app":{"name":"admin"}},"events":[{"name":"view_changed","attributes":{"secret":"must-not-leave"}}]}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusBadRequest, response.Code)
	require.Empty(t, logsSink.AllLogs())
	require.Empty(t, tracesSink.AllTraces())
}

func TestCollectRejectsMalformedPayloadBeforeWritingAnyTelemetry(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	response := performCollect(r, []byte(`{"meta":`), validHeaders())

	require.Equal(t, http.StatusBadRequest, response.Code)
	require.Empty(t, logsSink.AllLogs())
	require.Empty(t, tracesSink.AllTraces())
}

func TestParseEvidenceCarriesServerAcceptedAtForFenceIngress(t *testing.T) {
	logs := newParseEvidence(ingestMetadata{
		tenantID:     "tenant-a",
		application:  "storefront",
		requestClass: "ordinary",
		observedAt:   fixedObservedAt,
	}, "rejected", "invalid_payload")
	attrs := logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes()

	require.Equal(t, fixedObservedAt.UnixNano(), mustIntAttribute(t, attrs, "rum.accepted_at_unix_nano"))
}

func TestCollectSanitizesCanonicalEventAndProducesStableIDGolden(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta": {
			"app": {"name":"storefront","environment":"production","release":"2026.07.15"},
			"page": {"url":"https://shop.example/customers/123456?token=secret#card"},
			"session": {"id":"session-1"},
			"user": {"id":"user-42","email":"buyer@example.com","username":"buyer"},
			"view": {"name":"checkout"}
		},
		"events": [{
			"name":"unknown.widget",
			"domain":"browser",
			"timestamp":"2026-07-15T10:00:00Z",
			"attributes":{"safe":"ok","Authorization":"Bearer secret","email":"buyer@example.com","cookie":"sid=secret"}
		}]
	}`)

	first := performCollect(r, body, validHeaders())
	second := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, first.Code)
	require.Equal(t, http.StatusAccepted, second.Code)
	require.Len(t, logsSink.AllLogs(), 2)

	firstLog := logsSink.AllLogs()[0]
	secondLog := logsSink.AllLogs()[1]
	require.Equal(t, eventID("tenant-a", "storefront", "batch-7", 0), logAttribute(t, firstLog, "rum.event.id"))
	require.Equal(t, logAttribute(t, firstLog, "rum.event.id"), logAttribute(t, secondLog, "rum.event.id"))
	require.Equal(t, "1784109600000000000", logAttribute(t, firstLog, "rum.observed.timestamp_unix_nano"))

	snapshot := canonicalLogSnapshot(t, firstLog)
	want, err := os.ReadFile("testdata/canonical_event.golden.json")
	require.NoError(t, err)
	require.JSONEq(t, string(want), string(snapshot))
	require.NotContains(t, string(snapshot), "secret")
	require.NotContains(t, string(snapshot), "buyer@example.com")
	require.NotContains(t, string(snapshot), "username")
	require.NotContains(t, string(snapshot), `"safe"`)
	require.Contains(t, string(snapshot), "https://shop.example/customers/:id")
}

func TestCollectOrdinaryEventIdentityIncludesAuthoritativeApplication(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	storefront := []byte(`{"meta":{"app":{"name":"storefront"}},"events":[{"name":"view_changed"}]}`)
	admin := []byte(`{"meta":{"app":{"name":"admin"}},"events":[{"name":"view_changed"}]}`)

	storefrontHeaders := validHeaders()
	adminHeaders := validHeaders()
	adminHeaders[headerApplication] = "admin"

	require.Equal(t, http.StatusAccepted, performCollect(r, storefront, storefrontHeaders).Code)
	require.Equal(t, http.StatusAccepted, performCollect(r, admin, adminHeaders).Code)
	require.Len(t, logsSink.AllLogs(), 2)
	storefrontID := logAttribute(t, logsSink.AllLogs()[0], "rum.event.id")
	adminID := logAttribute(t, logsSink.AllLogs()[1], "rum.event.id")
	require.Equal(t, eventID("tenant-a", "storefront", "batch-7", 0), storefrontID)
	require.Equal(t, eventID("tenant-a", "admin", "batch-7", 0), adminID)
	require.NotEqual(t, storefrontID, adminID)
}

func TestCollectAddsServerAcceptedAtAndErasureKeys(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{"app":{"name":"storefront"},"session":{"id":"session-1"},"user":{"id":"user-42"}},
		"events":[{"name":"session_start","timestamp":"2026-07-15T10:00:00Z"}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	attrs := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes()
	require.Equal(t, fixedObservedAt.UnixNano(), mustIntAttribute(t, attrs, "rum.accepted_at_unix_nano"))
	require.Equal(t, "v1", mustStringAttribute(t, attrs, "rum.erasure.key_version"))
	require.Equal(t, "a1d9afadac79412aba5fda15c64a1ff6d3ccf412b5fe0152d7b05823e99c8f4d", mustStringAttribute(t, attrs, "rum.erasure.user_key"))
	require.Equal(t, "a1d9afadac79412aba5fda15c64a1ff6d3ccf412b5fe0152d7b05823e99c8f4d", mustStringAttribute(t, attrs, "rum.user.id"))
	require.Equal(t, "97060f42ec713d31159721df0b7a3d01297eb91b69dfe89ce53764f60fba4445", mustStringAttribute(t, attrs, "rum.erasure.session_key"))
	require.NotContains(t, mustStringAttribute(t, attrs, "rum.user.id"), "user-42")
}

func TestCollectClampsUntrustedTimestamp(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{"meta":{"app":{"name":"storefront"}},"events":[{"name":"session_start","timestamp":"2026-07-16T10:00:00Z"}]}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	logs := logsSink.AllLogs()
	require.Len(t, logs, 1)
	record := logs[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	require.Equal(t, fixedObservedAt.UnixNano(), record.Timestamp().AsTime().UnixNano())
	value, ok := record.Attributes().Get("rum.timestamp.clamped")
	require.True(t, ok)
	require.True(t, value.Bool())
}

func TestStructuredDiagnosticSanitizersKeepSafeStructureWithoutLeakingCanaries(t *testing.T) {
	message := sanitizeErrorMessage(
		`ChunkLoadError: Loading chunk "orders-550e8400-e29b-41d4-a716-446655440000" failed for https://buyer@example.com/api/orders/918273645?token=eyJhbGciOiJIUzI1NiJ9.payload.signature`,
	)
	require.Equal(t, diagnosticTemplate, message.Kind)
	require.Contains(t, message.Value, "ChunkLoadError")
	require.Contains(t, message.Value, "orders-:id")
	require.Contains(t, message.Value, "https://example.com/api/orders/:id")

	networkURL := sanitizeNetworkURL("https://buyer@example.com/api/orders/918273645/items/550e8400-e29b-41d4-a716-446655440000?authorization=Bearer-secret#buyer")
	require.Equal(t, "https://example.com/api/orders/:id/items/:id", networkURL)

	selector := sanitizeWebVitalSelector(`main#customer-918273645.checkout.container > article:nth-child(3) img[src="https://buyer@example.com/avatar"]`)
	require.Equal(t, "main.checkout.container > article img", selector.Value)
	require.Equal(t, diagnosticTemplate, selector.Kind)

	label := sanitizeDeveloperLabel("生产环境/release@2026.07+canary", 128)
	require.Equal(t, "生产环境/release@2026.07+canary", label)

	encoded := strings.Join([]string{message.Value, networkURL, selector.Value, label}, "\n")
	for _, canary := range []string{
		"buyer@example.com",
		"918273645",
		"550e8400-e29b-41d4-a716-446655440000",
		"eyJhbGciOiJIUzI1NiJ9",
		"Bearer-secret",
		"customer-918273645",
	} {
		require.NotContains(t, encoded, canary)
	}
}

func TestUnrecognizedFreeTextFallsBackToFingerprint(t *testing.T) {
	message := sanitizeErrorMessage("张三在上海购买了红色商品并要求送到公司前台")
	require.Equal(t, diagnosticFingerprint, message.Kind)
	require.Regexp(t, `^message:[0-9a-f]{16}$`, message.Value)

	selector := sanitizeWebVitalSelector(`张三的结账按钮`)
	require.Equal(t, diagnosticFingerprint, selector.Kind)
	require.Regexp(t, `^selector:[0-9a-f]{16}$`, selector.Value)

	label := sanitizeDeveloperLabel("authorization=Bearer must-not-leave", 128)
	require.Regexp(t, `^label:[0-9a-f]{16}$`, label)
	require.NotContains(t, label, "must-not-leave")
}

func TestPathSegmentSanitizerUnifiesRouteAndNetworkURL(t *testing.T) {
	require.Equal(t,
		"https://cdn.example.test/assets/checkout.min.js",
		sanitizeNetworkURL("https://cdn.example.test/assets/checkout.min.js?v=7#x"),
	)
	require.Equal(t,
		"https://shop.example.test/结账/确认",
		sanitizeNetworkURL("https://shop.example.test/%E7%BB%93%E8%B4%A6/%E7%A1%AE%E8%AE%A4?token=secret"),
	)
	require.Equal(t, "/结账/确认", sanitizeRoutePath("/%E7%BB%93%E8%B4%A6/%E7%A1%AE%E8%AE%A4"))
	require.Equal(t, "/orders/:id/items/:id", sanitizeRoutePath("/orders/918273645/items/550e8400-e29b-41d4-a716-446655440000"))
	require.Equal(t,
		"https://api.example.test/orders/:id",
		sanitizeNetworkURL("https://api.example.test/orders/918273645?token=secret"),
	)
}

func TestCustomErrorSubclassKeepsReadableTemplate(t *testing.T) {
	message := sanitizeErrorMessage(`PaymentError: charge failed for order "ORD-123456" at https://pay.example/orders/918273645?token=secret`)
	require.Equal(t, diagnosticTemplate, message.Kind)
	require.Contains(t, message.Value, "PaymentError")
	require.Contains(t, message.Value, "https://pay.example/orders/:id")
	require.NotContains(t, message.Value, "918273645")
	require.NotContains(t, message.Value, "token=secret")

	dom := sanitizeErrorMessage(`DOMException: The operation was aborted.`)
	require.Equal(t, diagnosticTemplate, dom.Kind)
	require.Contains(t, dom.Value, "DOMException")

	// Faro console instrumentation prefix must not force a fingerprint fallback.
	fromConsole := sanitizeErrorMessage(`console.error: CheckoutError: payment declined for order #10086`)
	require.Equal(t, diagnosticTemplate, fromConsole.Kind)
	require.Contains(t, fromConsole.Value, "CheckoutError: payment declined")
	require.NotContains(t, fromConsole.Value, "console.error")
}

func TestPhonePatternDoesNotRedactShortDates(t *testing.T) {
	message := sanitizeErrorMessage(`TypeError: failed on 2024-01-15 for build 42`)
	require.Equal(t, diagnosticTemplate, message.Kind)
	require.Contains(t, message.Value, "2024-01-15")
	require.Contains(t, message.Value, "build 42")
}

func TestSanitizeTraceSpanNameKeepsSafeLabels(t *testing.T) {
	require.Equal(t, "documentLoad", sanitizeTraceSpanName("documentLoad"))
	require.Equal(t, "GET https://shop.example/cart/:id", sanitizeTraceSpanName("GET https://shop.example/cart/42?token=x"))
	require.Equal(t, "browser.span", sanitizeTraceSpanName("checkout buyer@example.com"))
	require.Equal(t, "browser.span", sanitizeTraceSpanName("token=secret-span"))
}

func TestTrafficClassificationSeparatesVisitorsFromAutomation(t *testing.T) {
	require.Equal(t, trafficHuman, classifyTraffic("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36"))
	require.Equal(t, trafficCrawler, classifyTraffic("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"))
	require.Equal(t, trafficSynthetic, classifyTraffic("Mozilla/5.0 HeadlessChrome/126.0 Playwright/1.45"))
	require.Equal(t, trafficUnknown, classifyTraffic(""))
}

func TestErrorGroupKeyIgnoresRedactedDynamicParameters(t *testing.T) {
	first := stableErrorGroupKey(
		"storefront",
		"ChunkLoadError",
		sanitizeErrorMessage(`ChunkLoadError: Loading chunk "orders-123456" failed`),
		"",
		"asset:abc",
	)
	second := stableErrorGroupKey(
		"storefront",
		"ChunkLoadError",
		sanitizeErrorMessage(`ChunkLoadError: Loading chunk "orders-987654" failed`),
		"",
		"asset:abc",
	)
	require.Equal(t, first, second)
	require.Regexp(t, `^[0-9a-f]{64}$`, first)

	clientFingerprint := stableErrorGroupKey("storefront", "TypeError", sanitizeErrorMessage("ignored"), "faro-stable-key", "")
	require.Equal(t, privacyLabel("error-group", "faro-stable-key"), clientFingerprint)
}

func TestSanitizeEventContextAllowListsOfficialFaroResourceFields(t *testing.T) {
	context := sanitizeEventContext("faro.performance.resource", map[string]string{
		"name":           "https://api.example.test/users/123456?token=secret#profile",
		"initiatorType":  "fetch",
		"responseStatus": "200",
		"duration":       "42",
		"transferSize":   "512",
		"cacheHitStatus": "fullLoad",
		"protocol":       "h2",
		"method":         "POST",
		"customerName":   "Must Not Leave",
		"resource_type":  "attacker-alias",
	}, defaultConfig())

	require.Equal(t, map[string]string{
		"cacheHitStatus": "fullLoad",
		"duration":       "42",
		"initiatorType":  "fetch",
		"name":           "https://api.example.test/users/:id",
		"protocol":       "h2",
		"responseStatus": "200",
		"transferSize":   "512",
	}, context)
}

func TestSanitizeContextDropsUnknownFieldsAndKeepsSafeDOMSelectorStructure(t *testing.T) {
	context := sanitizeMeasurementContext("web-vitals", map[string]string{
		"element":         "#checkout-form input[name=email]",
		"rating":          "needs-improvement",
		"customerName":    "Ada Lovelace",
		"authorization":   "Bearer secret",
		"navigation_type": "navigate",
	}, defaultConfig())

	require.Equal(t, "input", context["element"])
	require.Equal(t, "needs-improvement", context["rating"])
	require.Equal(t, "navigate", context["navigation_type"])
	require.NotContains(t, context, "customerName")
	require.NotContains(t, context, "authorization")
}

func TestCollectPreservesTypedFaroINPAttributionForProductQueries(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{"app":{"name":"storefront"},"view":{"name":"/checkout"}},
		"measurements":[{
			"type":"web-vitals",
			"values":{
				"inp":780,
				"input_delay":90,
				"processing_duration":540,
				"presentation_delay":150,
				"interaction_time":4210,
				"next_paint_time":4990,
				"customer_input":123
			},
			"context":{
				"interaction_target":"button.checkout",
				"interaction_type":"pointer",
				"customerName":"Must Not Leave"
			}
		}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	record := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	require.Equal(t, "vital", mustStringAttribute(t, record.Attributes(), "rum.event.type"))
	require.Equal(t, "template", mustStringAttribute(t, record.Attributes(), "rum.vital.target_kind"))

	var canonical struct {
		Type    string             `json:"type"`
		Values  map[string]float64 `json:"values"`
		Context map[string]string  `json:"context"`
	}
	require.NoError(t, json.Unmarshal([]byte(record.Body().Str()), &canonical))
	require.Equal(t, "web-vitals", canonical.Type)
	require.Equal(t, map[string]float64{
		"inp":                 780,
		"input_delay":         90,
		"interaction_time":    4210,
		"next_paint_time":     4990,
		"presentation_delay":  150,
		"processing_duration": 540,
	}, canonical.Values)
	require.Equal(t, map[string]string{
		"interaction_target": "button.checkout",
		"interaction_type":   "pointer",
	}, canonical.Context)
}

func TestSanitizeSecurityPolicyViolationRemovesSecretsAndDynamicPathSegments(t *testing.T) {
	context := sanitizeEventContext("securitypolicyviolation", map[string]string{
		"blockedURI":         "https://cdn.example.test/accounts/+86-138-0013-8000/avatar.png?token=secret#profile",
		"documentURI":        "https://shop.example.test/orders/550e8400-e29b-41d4-a716-446655440000?email=buyer@example.com",
		"effectiveDirective": "script-src",
		"sample":             "Bearer must-not-leave",
	}, defaultConfig())

	require.Equal(t, "https://cdn.example.test/accounts/:id/avatar.png", context["blockedURI"])
	require.Equal(t, "https://shop.example.test/orders/:id", context["documentURI"])
	require.Equal(t, "script-src", context["effectiveDirective"])
	require.NotContains(t, context, "sample")
}

func TestFrameAssetFingerprintMatchesSourceMapUploadContract(t *testing.T) {
	require.Equal(
		t,
		"asset:9ab0ce4d26f7d0ad959edd4b45878c1b",
		rumprivacy.AssetFingerprint("https://cdn.example.test/assets/checkout.min.js?v=7#x"),
	)
	require.Equal(
		t,
		"asset:9ab0ce4d26f7d0ad959edd4b45878c1b",
		rumprivacy.AssetFingerprint("/assets/checkout.min.js"),
	)
	require.Empty(t, rumprivacy.AssetFingerprint("javascript:alert(1)"))
	require.Empty(t, rumprivacy.AssetFingerprint("../main.js"))
}

func TestCollectHashesFreeTextAndURLPathInsteadOfPersistingPII(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta": {
			"app":{"name":"storefront"},
			"view":{"name":"Alice Smith"},
			"page":{"url":"https://shop.example.test/users/918273645?token=secret"}
		},
		"exceptions":[{
			"type":"TypeError",
			"value":"Alice Smith +86-138-0013-8000 4111-1111-1111-1111 Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature",
			"fingerprint":"buyer@example.test",
			"stacktrace":{"frames":[{"filename":"https://cdn.example/app/users/alice.js?token=secret","function":"Alice Smith","module":"customer-alice"}]}
		}],
		"logs":[{"level":"error","message":"张三 card 4111111111111111 token-without-delimiter"}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	encoded, err := (&plog.JSONMarshaler{}).MarshalLogs(logsSink.AllLogs()[0])
	require.NoError(t, err)
	snapshot := string(encoded)
	for _, canary := range []string{
		"Alice", "Smith", "张三", "138-0013-8000", "4111-1111-1111-1111", "4111111111111111",
		"eyJhbGciOiJIUzI1NiJ9", "buyer@example.test", "customer-alice", "token-without-delimiter",
		"918273645", "token=secret",
	} {
		require.NotContains(t, snapshot, canary)
	}
	require.Contains(t, snapshot, "https://shop.example.test/users/:id")
	require.Contains(t, snapshot, "message:")
	require.Contains(t, snapshot, "label:")
}

func TestSanitizeValuesDropsNonFiniteAndSensitiveMeasurements(t *testing.T) {
	values := sanitizeValues(map[string]float64{
		"lcp":       123.4,
		"email":     1,
		"overflow":  math.Inf(1),
		"notNumber": math.NaN(),
	}, 8)

	require.Equal(t, map[string]float64{"lcp": 123.4}, values)
}

func TestCollectMapsOfficialFaroResourceFieldsWithoutTrustingClientMethod(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{"app":{"name":"storefront"}},
		"events":[{"name":"faro.performance.resource","attributes":{
			"name":"https://api.example.test/users/123456?token=secret#profile",
			"initiatorType":"fetch","responseStatus":"200","duration":"42",
			"transferSize":"512","cacheHitStatus":"fullLoad","protocol":"h2","method":"POST"
		}}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	record := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	attrs := record.Attributes()
	require.Equal(t, "https://api.example.test/users/:id", mustStringAttribute(t, attrs, "rum.network.url"))
	require.Equal(t, "fetch", mustStringAttribute(t, attrs, "rum.network.initiator"))
	require.Equal(t, "200", mustStringAttribute(t, attrs, "rum.network.status"))
	require.Equal(t, "42", mustStringAttribute(t, attrs, "rum.network.duration"))
	require.Equal(t, "512", mustStringAttribute(t, attrs, "rum.network.size"))
	require.Equal(t, "fullLoad", mustStringAttribute(t, attrs, "rum.network.cache"))
	require.Equal(t, "h2", mustStringAttribute(t, attrs, "rum.network.protocol"))
	require.NotContains(t, attrs.AsRaw(), "rum.network.method")
}

func TestCanonicalMappingCoversEverySupportedOrdinaryType(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{"app":{"name":"storefront"}},
		"events":[
			{"name":"session_start"},
			{"name":"session_resume"},
			{"name":"session_extend"},
			{"name":"view_changed"},
			{"name":"faro.user.action","action":{"id":"a-1","name":"checkout"}},
			{"name":"faro.performance.resource"},
			{"name":"other.custom"}
		],
		"exceptions":[{"type":"TypeError","value":"failed","timestamp":"2026-07-15T10:00:00Z"}],
		"logs":[{"level":"warning","message":"slow","timestamp":"2026-07-15T10:00:00Z"}],
		"measurements":[{"type":"web-vitals","values":{"lcp":123},"timestamp":"2026-07-15T10:00:00Z"}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, logsSink.AllLogs(), 1)
	records := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords()
	require.Equal(t, 10, records.Len())
	want := []string{"session", "session", "session", "view", "action", "network", "custom", "error", "console", "vital"}
	for index, eventType := range want {
		value, ok := records.At(index).Attributes().Get("rum.event.type")
		require.True(t, ok)
		require.Equal(t, eventType, value.Str())
	}
}

func TestExactFaroSDKGoldenCorpusTranslatesAcrossTheGoBoundary(t *testing.T) {
	fixture, err := os.ReadFile("testdata/faro-2.8.2-golden.json")
	require.NoError(t, err)
	var corpus struct {
		GeneratedBy string          `json:"generatedBy"`
		Ordinary    json.RawMessage `json:"ordinary"`
		Traces      json.RawMessage `json:"traces"`
	}
	require.NoError(t, json.Unmarshal(fixture, &corpus))
	require.Equal(t, "@grafana/faro-web-sdk@2.8.2", corpus.GeneratedBy)

	r, logsSink, tracesSink := newTestReceiver(t)
	r.ingress = newFakeKeyAuthorizer(map[string]string{
		"checkout": testBrowserKey,
	})
	ordinaryHeaders := validHeadersForClass("ordinary")
	ordinaryHeaders[headerApplication] = "checkout"
	ordinaryHeaders[headerBatchID] = "golden-ordinary"
	response := performCollect(r, corpus.Ordinary, ordinaryHeaders)
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, logsSink.AllLogs(), 1)
	records := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords()
	require.Equal(t, 4, records.Len())
	wantTypes := []string{"view", "error", "console", "vital"}
	for index, eventType := range wantTypes {
		require.Equal(t, eventType, mustStringAttribute(t, records.At(index).Attributes(), "rum.event.type"))
	}
	require.Equal(t, "warn", records.At(2).SeverityText())
	require.Equal(t, plog.SeverityNumberWarn, records.At(2).SeverityNumber())
	require.Equal(t, "checkout", mustStringAttribute(t, records.At(0).Attributes(), "rum.context.route"))
	require.Equal(t, "view-change", mustStringAttribute(t, records.At(0).Attributes(), "rum.context.navigation_type"))

	traceHeaders := validHeadersForClass("traces")
	traceHeaders[headerApplication] = "checkout"
	traceHeaders[headerBatchID] = "golden-traces"
	traceResponse := performCollect(r, corpus.Traces, traceHeaders)
	require.Equal(t, http.StatusAccepted, traceResponse.Code)
	require.Len(t, tracesSink.AllTraces(), 1)
	span := tracesSink.AllTraces()[0].ResourceSpans().At(0).ScopeSpans().At(0).Spans().At(0)
	require.Equal(t, "GET /checkout", span.Name())
	require.Equal(t, "00112233445566778899aabbccddeeff", span.TraceID().String())
	require.Equal(t, "0011223344556677", span.SpanID().String())
}

func TestCollectPromotesExactFaroViewAndNavigationFieldsForClickHouse(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{
			"app":{"name":"storefront"},
			"view":{"name":"checkout"}
		},
		"events":[
			{"name":"view_changed","attributes":{"fromView":"cart","toView":"checkout"}},
			{"name":"faro.navigation","attributes":{
				"fromUrl":"https://shop.example.test/cart/42?token=secret",
				"toUrl":"https://shop.example.test/checkout/42?token=secret",
				"sameDocument":"true",
				"duration":"137.5"
			}}
		]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	records := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords()
	require.Equal(t, 2, records.Len())

	viewAttrs := records.At(0).Attributes()
	require.Equal(t, "checkout", mustStringAttribute(t, viewAttrs, "rum.view.name"))
	require.Equal(t, "checkout", mustStringAttribute(t, viewAttrs, "rum.context.route"))
	require.Equal(t, "view-change", mustStringAttribute(t, viewAttrs, "rum.context.navigation_type"))

	navigationAttrs := records.At(1).Attributes()
	require.Equal(t, "checkout", mustStringAttribute(t, navigationAttrs, "rum.context.route"))
	require.Equal(t, "same-document", mustStringAttribute(t, navigationAttrs, "rum.context.navigation_type"))
	require.Equal(t, "137.5", mustStringAttribute(t, navigationAttrs, "rum.context.loading_time_ms"))
	require.Equal(
		t,
		"https://shop.example.test/checkout/:id",
		mustStringAttribute(t, navigationAttrs, "rum.context.toUrl"),
	)
}

func TestCollectKeepsStaticPageRouteReadable(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{
			"app":{"name":"storefront"},
			"view":{"name":"https://shop.example.test/pricing"},
			"page":{"url":"https://shop.example.test/pricing?campaign=summer#plans"}
		},
		"events":[{"name":"view_changed","attributes":{"toView":"https://shop.example.test/pricing"}}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	attrs := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes()
	require.Equal(t, "/pricing", mustStringAttribute(t, attrs, "rum.view.name"))
	require.Equal(t, "/pricing", mustStringAttribute(t, attrs, "rum.context.route"))
	require.Equal(
		t,
		"https://shop.example.test/pricing",
		mustStringAttribute(t, attrs, "rum.page.url"),
	)
}

func TestCollectRedactsSensitiveRouteSegmentsWithoutLosingPageIdentity(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{"app":{"name":"storefront"},"view":{"name":"/customers/alice@example.test"}},
		"events":[{"name":"view_changed","attributes":{"toView":"/customers/alice@example.test"}}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	attrs := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes()
	require.Equal(t, "/customers/:id", mustStringAttribute(t, attrs, "rum.view.name"))
	require.Equal(t, "/customers/:id", mustStringAttribute(t, attrs, "rum.context.route"))
	require.NotContains(t, attrs.AsRaw(), "alice@example.test")
}

func TestCollectNormalizesOpaqueRouteIdentifiers(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{"app":{"name":"storefront"},"view":{"name":"/orders/550e8400-e29b-41d4-a716-446655440000/items/42"}},
		"events":[{"name":"view_changed","attributes":{"toView":"/orders/550e8400-e29b-41d4-a716-446655440000/items/42"}}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	attrs := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes()
	require.Equal(t, "/orders/:id/items/:id", mustStringAttribute(t, attrs, "rum.view.name"))
	require.Equal(t, "/orders/:id/items/:id", mustStringAttribute(t, attrs, "rum.context.route"))
}

func TestCollectNormalizesLongOpaqueRouteIdentifiers(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{"app":{"name":"storefront"},"view":{"name":"/sessions/01J5Q7MZ5T7Y2W9K3N6R8H4C1B/assets/bf255944a683a8c7"}},
		"events":[{"name":"view_changed","attributes":{"toView":"/sessions/01J5Q7MZ5T7Y2W9K3N6R8H4C1B/assets/bf255944a683a8c7"}}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	attrs := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes()
	require.Equal(t, "/sessions/:id/assets/:id", mustStringAttribute(t, attrs, "rum.context.route"))
}

func TestCollectRedactsEncodedRouteSeparators(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{"app":{"name":"storefront"},"view":{"name":"/customers/alice%2F42/profile"}},
		"events":[{"name":"view_changed","attributes":{"toView":"/customers/alice%2F42/profile"}}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	attrs := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes()
	require.Equal(t, "/customers/:text/profile", mustStringAttribute(t, attrs, "rum.context.route"))
	require.NotContains(t, attrs.AsRaw(), "alice/42")
}

func TestCollectPromotesExactFaroUserActionFieldsForClickHouse(t *testing.T) {
	r, logsSink, _ := newTestReceiver(t)
	body := []byte(`{
		"meta":{"app":{"name":"storefront"}},
		"events":[{"name":"faro.user.action","action":{"id":"action-1","name":"Checkout"},"attributes":{
			"userActionTrigger":"pointerdown",
			"userActionDuration":"42.75",
			"userActionStartTime":"1000",
			"userActionEndTime":"1042.75"
		}}]
	}`)

	response := performCollect(r, body, validHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	attrs := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes()
	require.Equal(t, "pointerdown", mustStringAttribute(t, attrs, "rum.action.trigger"))
	require.Equal(t, "42.75", mustStringAttribute(t, attrs, "rum.action.duration_ms"))
	require.NotContains(t, attrs.AsRaw(), "rum.context.trigger")
	require.NotContains(t, attrs.AsRaw(), "rum.context.duration_ms")
}

func TestCollectOverridesClientTenantOnTraces(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	payload := faro.Payload{Traces: &faro.Traces{Traces: oneSpanTrace("client-tenant")}}
	payload.Meta.App.Name = "storefront"
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	headers := validHeadersForClass("traces")
	response := performCollect(r, body, headers)
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, tracesSink.AllTraces(), 1)
	resource := tracesSink.AllTraces()[0].ResourceSpans().At(0).Resource()
	tenant, ok := resource.Attributes().Get("tenant.id")
	require.True(t, ok)
	require.Equal(t, "tenant-a", tenant.Str())
	lookup, ok := resource.Attributes().Get("rum.credential.lookup_id")
	require.True(t, ok)
	require.Equal(t, testCredentialLookup, lookup.Str())
	require.Eventually(t, func() bool {
		return hasParseEvidence(logsSink.AllLogs(), "accepted", "ok")
	}, time.Second, 10*time.Millisecond)
}

func TestCollectTraceRequiresStableBatchID(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	payload := faro.Payload{Traces: &faro.Traces{Traces: oneSpanTrace("client-tenant")}}
	payload.Meta.App.Name = "storefront"
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	for name, mutate := range map[string]func(map[string]string){
		"missing": func(headers map[string]string) { delete(headers, headerBatchID) },
		"invalid": func(headers map[string]string) { headers[headerBatchID] = "invalid batch id" },
	} {
		t.Run(name, func(t *testing.T) {
			headers := validHeadersForClass("traces")
			mutate(headers)
			response := performCollect(r, body, headers)
			require.Equal(t, http.StatusBadRequest, response.Code)
		})
	}
	requireParseEvidence(t, logsSink.AllLogs(), "rejected", "invalid_batch_id")
	require.Empty(t, tracesSink.AllTraces())
}

func TestCollectDoesNotAcknowledgeMixedBatchWhenLogsQueueRejectsIt(t *testing.T) {
	logsConsumer, err := consumer.NewLogs(func(context.Context, plog.Logs) error {
		return errors.New("logs queue full")
	})
	require.NoError(t, err)
	tracesSink := new(consumertest.TracesSink)
	factory := NewFactory()
	settings := receivertest.NewNopSettings(factory.Type())
	cfg := defaultConfig()
	cfg.IdentityHMACSecret = testIdentityHMACSecret
	cfg.TenantID = testTenantID
	cfg.AdmissionRedisURL = "redis://rum-admission:test-secret-password-at-least-32-chars@127.0.0.1:6379"
	r, err := newFaroReceiver(cfg, &settings)
	require.NoError(t, err)
	r.ingress = newFakeKeyAuthorizer(map[string]string{"storefront": testBrowserKey})
	r.nextLogs = logsConsumer
	r.nextTraces = tracesSink
	r.now = func() time.Time { return fixedObservedAt }

	payload := faro.Payload{
		Events: []faro.Event{{Name: "view_changed", Timestamp: fixedObservedAt}},
		Traces: &faro.Traces{Traces: oneSpanTrace("client-tenant")},
	}
	payload.Meta.App.Name = "storefront"
	payload.Meta.Session.ID = "session-1"
	payload.Meta.User.ID = "user-42"
	body, err := json.Marshal(payload)
	require.NoError(t, err)
	headers := validHeaders()

	response := performCollect(r, body, headers)

	require.Equal(t, http.StatusServiceUnavailable, response.Code)
	require.Empty(t, tracesSink.AllTraces())
}

func TestCollectWritesTraceCorrelationAndErasureFenceAttributesOnEverySpan(t *testing.T) {
	r, _, tracesSink := newTestReceiver(t)
	traces := oneSpanTrace("client-tenant")
	appendTestSpan(traces.ResourceSpans().At(0).ScopeSpans().At(0).Spans(), "second", 2)
	payload := faro.Payload{Traces: &faro.Traces{Traces: traces}}
	payload.Meta.App.Name = "storefront"
	payload.Meta.Session.ID = "session-1"
	payload.Meta.User.ID = "user-42"
	body, err := json.Marshal(payload)
	require.NoError(t, err)
	headers := validHeadersForClass("traces")

	response := performCollect(r, body, headers)
	require.Equal(t, http.StatusAccepted, response.Code)
	spans := tracesSink.AllTraces()[0].ResourceSpans().At(0).ScopeSpans().At(0).Spans()
	require.Equal(t, 2, spans.Len())
	for index := 0; index < spans.Len(); index++ {
		attrs := spans.At(index).Attributes()
		require.Equal(t, traceIngestID("tenant-a", "storefront", "batch-7", index), mustStringAttribute(t, attrs, "rum.ingest.id"))
		require.Equal(t, "session-1", mustStringAttribute(t, attrs, "rum.session.id"))
		require.Equal(t, "a1d9afadac79412aba5fda15c64a1ff6d3ccf412b5fe0152d7b05823e99c8f4d", mustStringAttribute(t, attrs, "rum.user.id"))
		require.Equal(t, fixedObservedAt.UnixNano(), mustIntAttribute(t, attrs, "rum.accepted_at_unix_nano"))
		require.Equal(t, "v1", mustStringAttribute(t, attrs, "rum.erasure.key_version"))
		require.Equal(t, "a1d9afadac79412aba5fda15c64a1ff6d3ccf412b5fe0152d7b05823e99c8f4d", mustStringAttribute(t, attrs, "rum.erasure.user_key"))
		require.Equal(t, "97060f42ec713d31159721df0b7a3d01297eb91b69dfe89ce53764f60fba4445", mustStringAttribute(t, attrs, "rum.erasure.session_key"))
	}
}

func TestCollectClampsUntrustedTraceAndEventTimestampsToTheAdmissionClock(t *testing.T) {
	r, _, tracesSink := newTestReceiver(t)
	traces := oneSpanTrace("client-tenant")
	span := traces.ResourceSpans().At(0).ScopeSpans().At(0).Spans().At(0)
	span.SetStartTimestamp(pcommon.NewTimestampFromTime(fixedObservedAt.Add(-time.Hour)))
	span.SetEndTimestamp(pcommon.NewTimestampFromTime(fixedObservedAt.Add(time.Hour)))
	event := span.Events().AppendEmpty()
	event.SetTimestamp(pcommon.NewTimestampFromTime(fixedObservedAt.Add(2 * time.Hour)))
	payload := faro.Payload{Traces: &faro.Traces{Traces: traces}}
	payload.Meta.App.Name = "storefront"
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	response := performCollect(r, body, validHeadersForClass("traces"))

	require.Equal(t, http.StatusAccepted, response.Code)
	exported := tracesSink.AllTraces()[0].ResourceSpans().At(0).ScopeSpans().At(0).Spans().At(0)
	require.Equal(t, fixedObservedAt, exported.StartTimestamp().AsTime())
	require.Equal(t, fixedObservedAt, exported.EndTimestamp().AsTime())
	require.Equal(t, fixedObservedAt, exported.Events().At(0).Timestamp().AsTime())
	clamped, ok := exported.Attributes().Get("rum.timestamp.clamped")
	require.True(t, ok)
	require.True(t, clamped.Bool())
}

func TestCollectRejectsTraceWithoutStableTraceAndSpanIdentifiers(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	traces := oneSpanTrace("client-tenant")
	span := traces.ResourceSpans().At(0).ScopeSpans().At(0).Spans().At(0)
	span.SetTraceID(pcommon.NewTraceIDEmpty())
	payload := faro.Payload{Traces: &faro.Traces{Traces: traces}}
	payload.Meta.App.Name = "storefront"
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	response := performCollect(r, body, validHeadersForClass("traces"))

	require.Equal(t, http.StatusBadRequest, response.Code)
	require.Empty(t, tracesSink.AllTraces())
	requireParseEvidence(t, logsSink.AllLogs(), "rejected", "invalid_payload")
}

func TestCollectTraceRetryReusesServerDerivedSpanIdentity(t *testing.T) {
	r, _, tracesSink := newTestReceiver(t)
	traces := oneSpanTrace("client-tenant")
	appendTestSpan(traces.ResourceSpans().At(0).ScopeSpans().At(0).Spans(), "second", 2)
	payload := faro.Payload{Traces: &faro.Traces{Traces: traces}}
	payload.Meta.App.Name = "storefront"
	body, err := json.Marshal(payload)
	require.NoError(t, err)
	headers := validHeadersForClass("traces")

	require.Equal(t, http.StatusAccepted, performCollect(r, body, headers).Code)
	require.Equal(t, http.StatusAccepted, performCollect(r, body, headers).Code)
	require.Len(t, tracesSink.AllTraces(), 2)

	first := tracesSink.AllTraces()[0].ResourceSpans().At(0).ScopeSpans().At(0).Spans()
	second := tracesSink.AllTraces()[1].ResourceSpans().At(0).ScopeSpans().At(0).Spans()
	require.Equal(t, 2, first.Len())
	require.Equal(t, first.Len(), second.Len())
	for index := 0; index < first.Len(); index++ {
		firstID := mustStringAttribute(t, first.At(index).Attributes(), "rum.ingest.id")
		secondID := mustStringAttribute(t, second.At(index).Attributes(), "rum.ingest.id")
		require.Equal(t, traceIngestID("tenant-a", "storefront", "batch-7", index), firstID)
		require.Equal(t, firstID, secondID)
	}
	require.NotEqual(
		t,
		mustStringAttribute(t, first.At(0).Attributes(), "rum.ingest.id"),
		mustStringAttribute(t, first.At(1).Attributes(), "rum.ingest.id"),
	)
}

func TestCollectSanitizesUntrustedTraceContentBeforeExport(t *testing.T) {
	r, _, tracesSink := newTestReceiver(t)
	traces := oneSpanTrace("client-tenant")
	resource := traces.ResourceSpans().At(0).Resource()
	resource.Attributes().PutStr("authorization", "Bearer resource-canary")
	resource.Attributes().PutStr("service.name", "attacker-service")
	span := traces.ResourceSpans().At(0).ScopeSpans().At(0).Spans().At(0)
	span.SetName("documentLoad")
	span.Attributes().PutStr("authorization", "Bearer span-canary")
	span.Attributes().PutStr("url.full", "https://buyer:password@shop.example/cart/42?token=query-canary#secret")
	span.Attributes().PutStr("http.request.method", "GET")
	span.Attributes().PutInt("http.response.status_code", 200)
	span.Attributes().PutStr("custom.payload", "custom-canary")
	span.Status().SetMessage("status-canary")
	event := span.Events().AppendEmpty()
	event.SetName("exception buyer@example.com")
	event.Attributes().PutStr("exception.message", "event-canary")
	link := span.Links().AppendEmpty()
	link.Attributes().PutStr("cookie", "link-canary")

	payload := faro.Payload{Traces: &faro.Traces{Traces: traces}}
	payload.Meta.App.Name = "storefront"
	payload.Meta.App.Environment = "production"
	payload.Meta.App.Release = "2026.07.15"
	payload.Meta.Session.ID = "session-1"
	body, err := json.Marshal(payload)
	require.NoError(t, err)
	headers := validHeadersForClass("traces")

	response := performCollect(r, body, headers)

	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, tracesSink.AllTraces(), 1)
	encoded, err := (&ptrace.JSONMarshaler{}).MarshalTraces(tracesSink.AllTraces()[0])
	require.NoError(t, err)
	snapshot := string(encoded)
	for _, canary := range []string{
		"client-tenant", "resource-canary", "attacker-service", "buyer@example.com",
		"password", "query-canary", "span-canary", "custom-canary", "status-canary",
		"event-canary", "link-canary",
	} {
		require.NotContains(t, snapshot, canary)
	}
	require.Contains(t, snapshot, "storefront")
	require.Contains(t, snapshot, "documentLoad")
	require.Contains(t, snapshot, "http.request.method")
	require.Contains(t, snapshot, "http.response.status_code")
}

func TestCollectRejectsTraceAttributeBombBeforeExport(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	traces := oneSpanTrace("client-tenant")
	attrs := traces.ResourceSpans().At(0).ScopeSpans().At(0).Spans().At(0).Attributes()
	for index := 0; index <= maxTraceAttributesPerSpan; index++ {
		attrs.PutStr("custom."+strconv.Itoa(index), "value")
	}
	payload := faro.Payload{Traces: &faro.Traces{Traces: traces}}
	payload.Meta.App.Name = "storefront"
	body, err := json.Marshal(payload)
	require.NoError(t, err)
	headers := validHeadersForClass("traces")

	response := performCollect(r, body, headers)

	require.Equal(t, http.StatusRequestEntityTooLarge, response.Code)
	requireParseEvidence(t, logsSink.AllLogs(), "rejected", "payload_too_large")
	require.Empty(t, tracesSink.AllTraces())
}

func TestDecodeBodyEnforcesCompressedDecompressedAndDepthLimits(t *testing.T) {
	cfg := defaultConfig()
	cfg.MaxCompressedBytes = 64
	cfg.MaxDecompressedBytes = 128
	cfg.MaxJSONDepth = 4

	_, err := decodeFaroBody(strings.NewReader(strings.Repeat("x", 65)), "", cfg)
	require.ErrorIs(t, err, ErrPayloadTooLarge)

	compressed := gzipBytes(t, []byte(`{"events":[{"name":"`+strings.Repeat("a", 128)+`"}]}`))
	_, err = decodeFaroBody(bytes.NewReader(compressed), "gzip", cfg)
	require.ErrorIs(t, err, ErrPayloadTooLarge)

	cfg.MaxCompressedBytes = 1024
	cfg.MaxDecompressedBytes = 1024
	_, err = decodeFaroBody(strings.NewReader(`{"a":{"b":{"c":{"d":{"e":1}}}}}`), "", cfg)
	require.ErrorIs(t, err, ErrInvalidPayload)

	cfg.MaxJSONDepth = 32
	cfg.MaxCompressedBytes = 2048
	cfg.MaxDecompressedBytes = 8192
	cfg.MaxCompressionRatio = 2
	compressed = gzipBytes(t, []byte(`{"logs":[{"message":"`+strings.Repeat("a", 4096)+`"}]}`))
	_, err = decodeFaroBody(bytes.NewReader(compressed), "gzip", cfg)
	require.ErrorIs(t, err, ErrPayloadTooLarge)
}

func TestCollectRejectsReplayAndTooManyItems(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)
	r.cfg.MaxItems = 1

	replay := performCollect(r, []byte(`{"meta":{"app":{"name":"storefront"}},"events":[{"name":"faro.session_recording.segment"}]}`), validHeaders())
	require.Equal(t, http.StatusBadRequest, replay.Code)

	tooMany := performCollect(r, []byte(`{"meta":{"app":{"name":"storefront"}},"events":[{"name":"a"},{"name":"b"}]}`), validHeaders())
	require.Equal(t, http.StatusRequestEntityTooLarge, tooMany.Code)

	traces := oneSpanTrace("client-tenant")
	appendTestSpan(traces.ResourceSpans().At(0).ScopeSpans().At(0).Spans(), "second", 2)
	tracePayload := faro.Payload{Traces: &faro.Traces{Traces: traces}}
	tracePayload.Meta.App.Name = "storefront"
	traceBody, err := json.Marshal(tracePayload)
	require.NoError(t, err)
	traceHeaders := validHeadersForClass("traces")
	delete(traceHeaders, headerBatchID)
	tooManyTraces := performCollect(r, traceBody, traceHeaders)
	require.Equal(t, http.StatusRequestEntityTooLarge, tooManyTraces.Code)
	requireNoCanonicalLogs(t, logsSink.AllLogs())
	require.Empty(t, tracesSink.AllTraces())
}

func TestCollectAcceptsOfficialReplayLifecycleEventsButRejectsReplayData(t *testing.T) {
	r, logsSink, tracesSink := newTestReceiver(t)

	lifecycle := performCollect(r, []byte(`{
		"meta":{"app":{"name":"storefront"}},
		"events":[
			{"name":"faro.session_recording.started"},
			{"name":"faro.session_recording.paused"},
			{"name":"faro.session_recording.resumed"}
		]
	}`), validHeaders())
	require.Equal(t, http.StatusAccepted, lifecycle.Code)
	require.Len(t, logsSink.AllLogs(), 1)
	records := logsSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords()
	require.Equal(t, 3, records.Len())
	for index := 0; index < records.Len(); index++ {
		require.Equal(t, "custom", mustStringAttribute(t, records.At(index).Attributes(), "rum.event.type"))
	}

	replayData := performCollect(r, []byte(`{
		"meta":{"app":{"name":"storefront"}},
		"events":[{"name":"faro.session_recording.event","attributes":{"event":"{}"}}]
	}`), validHeaders())
	require.Equal(t, http.StatusBadRequest, replayData.Code)
	require.Empty(t, tracesSink.AllTraces())
}

func FuzzDecodeFaroBody(f *testing.F) {
	f.Add([]byte(`{"events":[{"name":"seed"}]}`), "")
	f.Add(gzipSeed([]byte(`{"logs":[{"message":"seed","timestamp":"2026-07-15T10:00:00Z"}]}`)), "gzip")
	f.Add([]byte(`{"traces":{"resourceSpans":[]},"events":[{"name":"mixed"}]}`), "")

	cfg := defaultConfig()
	cfg.IdentityHMACSecret = testIdentityHMACSecret
	cfg.AdmissionRedisURL = "redis://rum-admission:test-secret-password-at-least-32-chars@127.0.0.1:6379"
	cfg.MaxCompressedBytes = 4096
	cfg.MaxDecompressedBytes = 8192
	f.Fuzz(func(t *testing.T, body []byte, encoding string) {
		if len(body) > 5000 {
			t.Skip()
		}
		_, _ = decodeFaroBody(bytes.NewReader(body), encoding, cfg)
	})
}

func FuzzStructuredDiagnosticSanitizersDoNotLeakDynamicValues(f *testing.F) {
	f.Add([]byte("customer-918273645"))
	f.Add([]byte("buyer@example.com"))
	f.Add([]byte(`{"authorization":"Bearer secret"}`))

	f.Fuzz(func(t *testing.T, input []byte) {
		digest := sha256.Sum256(input)
		token := hex.EncodeToString(digest[:])
		message := sanitizeErrorMessage(`TypeError: failed for "` + token + `"`)
		networkURL := sanitizeNetworkURL("https://api.example/orders?authorization=" + token)
		selector := sanitizeWebVitalSelector(`main[data-customer="` + token + `"] button`)

		serialized := strings.Join([]string{message.Value, networkURL, selector.Value}, "\n")
		require.NotContains(t, serialized, token)
	})
}

func newTestReceiver(t *testing.T) (*faroReceiver, *consumertest.LogsSink, *consumertest.TracesSink) {
	t.Helper()
	factory := NewFactory()
	settings := receivertest.NewNopSettings(factory.Type())
	cfg := defaultConfig()
	cfg.IdentityHMACSecret = testIdentityHMACSecret
	cfg.TenantID = testTenantID
	cfg.AdmissionRedisURL = "redis://rum-admission:test-secret-password-at-least-32-chars@127.0.0.1:6379"
	logsSink := new(consumertest.LogsSink)
	tracesSink := new(consumertest.TracesSink)
	r, err := newFaroReceiver(cfg, &settings)
	require.NoError(t, err)
	r.ingress = newFakeKeyAuthorizer(map[string]string{
		"storefront": testBrowserKey,
		"admin":      testBrowserKey,
	})
	r.nextLogs = logsSink
	r.nextTraces = tracesSink
	r.now = func() time.Time { return fixedObservedAt }
	return r, logsSink, tracesSink
}

// fakeKeyAuthorizer is a test double for ingressAdmission that avoids a
// real Redis dependency. An empty store rejects every application (fail-closed).
type fakeKeyAuthorizer struct {
	keys map[string]string
	err  error
}

func newFakeKeyAuthorizer(keys map[string]string) *fakeKeyAuthorizer {
	return &fakeKeyAuthorizer{keys: keys}
}

func (f *fakeKeyAuthorizer) Admit(_ context.Context, request ingress.Request) (ingress.Decision, error) {
	if f.err != nil {
		return ingress.Decision{}, f.err
	}
	want, ok := f.keys[request.Application]
	if !ok || want != request.BrowserKey {
		return ingress.Decision{Reason: ingress.RejectBrowserKey}, nil
	}
	return ingress.Decision{Allowed: true, TenantID: testTenantID, Revision: 1}, nil
}

func (f *fakeKeyAuthorizer) Start(context.Context) error    { return nil }
func (f *fakeKeyAuthorizer) Shutdown(context.Context) error { return nil }

func validHeaders() map[string]string {
	return validHeadersForClass("")
}

func validHeadersForClass(_ string) map[string]string {
	return map[string]string{
		headerAPIKey:      testBrowserKey,
		headerApplication: "storefront",
		headerBatchID:     "batch-7",
		"Origin":          "https://app.example.test",
		"Content-Type":    "application/json",
	}
}

func performCollect(r *faroReceiver, body []byte, headers map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, collectPath, bytes.NewReader(body))
	for name, value := range headers {
		req.Header.Set(name, value)
	}
	response := httptest.NewRecorder()
	r.handleCollect(response, req)
	return response
}

func eventID(tenant, application, batch string, ordinal int) string {
	sum := sha256.Sum256([]byte(tenant + "\x00" + application + "\x00" + batch + "\x00" + strconv.Itoa(ordinal)))
	return hex.EncodeToString(sum[:])
}

func traceIngestID(tenant, application, batch string, ordinal int) string {
	sum := sha256.Sum256([]byte(tenant + "\x00" + application + "\x00" + batch + "\x00trace\x00" + strconv.Itoa(ordinal)))
	return hex.EncodeToString(sum[:])
}

func logAttribute(t *testing.T, logs plog.Logs, key string) string {
	t.Helper()
	record := logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	value, ok := record.Attributes().Get(key)
	require.True(t, ok, "missing log attribute %s", key)
	return value.Str()
}

func mustStringAttribute(t *testing.T, attrs pcommon.Map, key string) string {
	t.Helper()
	value, ok := attrs.Get(key)
	require.True(t, ok, "missing attribute %s", key)
	require.Equal(t, pcommon.ValueTypeStr, value.Type())
	return value.Str()
}

func mustIntAttribute(t *testing.T, attrs pcommon.Map, key string) int64 {
	t.Helper()
	value, ok := attrs.Get(key)
	require.True(t, ok, "missing attribute %s", key)
	require.Equal(t, pcommon.ValueTypeInt, value.Type())
	return value.Int()
}

func canonicalLogSnapshot(t *testing.T, logs plog.Logs) []byte {
	t.Helper()
	resourceLogs := logs.ResourceLogs().At(0)
	scopeLogs := resourceLogs.ScopeLogs().At(0)
	record := scopeLogs.LogRecords().At(0)
	keys := []string{
		"rum.accepted_at_unix_nano", "rum.application", "rum.environment",
		"rum.erasure.key_version", "rum.erasure.session_key", "rum.erasure.user_key", "rum.event.id", "rum.event.type", "rum.page.url",
		"rum.release", "rum.session.id", "rum.timestamp.clamped", "rum.user.id", "rum.view.name",
	}
	attrs := map[string]any{}
	for _, key := range keys {
		if value, ok := record.Attributes().Get(key); ok {
			attrs[key] = value.AsRaw()
		}
	}
	body := map[string]any{}
	require.NoError(t, json.Unmarshal([]byte(record.Body().Str()), &body))
	tenant, ok := resourceLogs.Resource().Attributes().Get("tenant.id")
	require.True(t, ok)
	snapshot := map[string]any{
		"scope":    scopeLogs.Scope().Name(),
		"resource": map[string]any{"tenant.id": tenant.Str()},
		"record":   attrs,
		"body":     body,
	}
	encoded, err := json.Marshal(snapshot)
	require.NoError(t, err)
	return encoded
}

func requireParseEvidence(t *testing.T, batches []plog.Logs, outcome, reason string) {
	t.Helper()
	require.True(t, hasParseEvidence(batches, outcome, reason), "missing %s parse evidence", outcome)
}

func hasParseEvidence(batches []plog.Logs, outcome, reason string) bool {
	for _, logs := range batches {
		resources := logs.ResourceLogs()
		for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
			scopes := resources.At(resourceIndex).ScopeLogs()
			for scopeIndex := 0; scopeIndex < scopes.Len(); scopeIndex++ {
				scope := scopes.At(scopeIndex)
				if scope.Scope().Name() != parseEvidenceScopeName {
					continue
				}
				if scope.LogRecords().Len() != 1 {
					continue
				}
				attrs := scope.LogRecords().At(0).Attributes()
				actualOutcome, ok := attrs.Get("rum.evidence.outcome")
				if !ok || actualOutcome.Str() != outcome {
					continue
				}
				actualReason, ok := attrs.Get("rum.evidence.reason")
				if ok && actualReason.Str() == reason {
					return true
				}
			}
		}
	}
	return false
}

func requireNoCanonicalLogs(t *testing.T, batches []plog.Logs) {
	t.Helper()
	for _, logs := range batches {
		resources := logs.ResourceLogs()
		for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
			scopes := resources.At(resourceIndex).ScopeLogs()
			for scopeIndex := 0; scopeIndex < scopes.Len(); scopeIndex++ {
				require.NotEqual(t, ordinaryScopeName, scopes.At(scopeIndex).Scope().Name())
			}
		}
	}
}

func logsJSON(t *testing.T, batches []plog.Logs) string {
	t.Helper()
	encoded, err := (&plog.JSONMarshaler{}).MarshalLogs(batches[0])
	require.NoError(t, err)
	return string(encoded)
}

func oneSpanTrace(clientTenant string) ptrace.Traces {
	traces := ptrace.NewTraces()
	resourceSpans := traces.ResourceSpans().AppendEmpty()
	resourceSpans.Resource().Attributes().PutStr("tenant.id", clientTenant)
	span := resourceSpans.ScopeSpans().AppendEmpty().Spans().AppendEmpty()
	span.SetName("GET /cart")
	span.SetTraceID(pcommon.TraceID{1})
	span.SetSpanID(pcommon.SpanID{1})
	span.SetStartTimestamp(1)
	span.SetEndTimestamp(2)
	return traces
}

func appendTestSpan(spans ptrace.SpanSlice, name string, id byte) {
	span := spans.AppendEmpty()
	span.SetName(name)
	span.SetTraceID(pcommon.TraceID{id})
	span.SetSpanID(pcommon.SpanID{id})
	span.SetStartTimestamp(1)
	span.SetEndTimestamp(2)
}

func gzipBytes(t *testing.T, body []byte) []byte {
	t.Helper()
	var buffer bytes.Buffer
	writer := gzip.NewWriter(&buffer)
	_, err := writer.Write(body)
	require.NoError(t, err)
	require.NoError(t, writer.Close())
	return buffer.Bytes()
}

func gzipSeed(body []byte) []byte {
	var buffer bytes.Buffer
	writer := gzip.NewWriter(&buffer)
	_, _ = writer.Write(body)
	_ = writer.Close()
	return buffer.Bytes()
}

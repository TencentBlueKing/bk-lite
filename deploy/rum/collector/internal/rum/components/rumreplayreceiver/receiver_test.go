package rumreplayreceiver

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/client"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/consumer/consumertest"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/receiver/receivertest"
)

var replayObservedAt = time.Date(2026, 7, 15, 10, 0, 1, 0, time.UTC)

const testReplayIdentityHMACSecret = "test-rum-replay-identity-hmac-secret-at-least-32-bytes"
const testReplayBrowserKey = "core-rum-browser-e2e"
const testReplayTenantID = "tenant-a"
const testReplayCredentialLookup = "b21d328cf994d78f"

type testEnvelope struct {
	SchemaVersion   int               `json:"schema_version"`
	Application     string            `json:"application"`
	Environment     string            `json:"environment"`
	Release         string            `json:"release"`
	SessionID       string            `json:"session_id"`
	UserID          string            `json:"user_id,omitempty"`
	PageID          string            `json:"page_id"`
	RecordingID     string            `json:"recording_id"`
	SegmentID       string            `json:"segment_id"`
	Sequence        int64             `json:"sequence"`
	StartedAt       string            `json:"started_at"`
	EndedAt         string            `json:"ended_at"`
	HasFullSnapshot bool              `json:"has_full_snapshot"`
	EventCount      int               `json:"event_count"`
	ChecksumSHA256  string            `json:"checksum_sha256,omitempty"`
	Events          []json.RawMessage `json:"events"`
}

func TestFactoryIsRegistrable(t *testing.T) {
	factory := NewFactory()
	require.Equal(t, "rum_replay", factory.Type().String())
	cfg := factory.CreateDefaultConfig().(*Config)
	cfg.Endpoint = "127.0.0.1:0"
	cfg.IdentityHMACSecret = testReplayIdentityHMACSecret
	cfg.AdmissionRedisURL = "redis://rum-admission:test-secret-password-at-least-32-chars@127.0.0.1:1"
	receiver, err := factory.CreateLogs(
		t.Context(),
		receivertest.NewNopSettings(factory.Type()),
		cfg,
		new(consumertest.LogsSink),
	)
	require.NoError(t, err)
	require.NoError(t, receiver.Shutdown(t.Context()))
}

func TestReplayConfigRequiresIdentitySecretAndAdmissionRedis(t *testing.T) {
	cfg := defaultConfig()
	require.ErrorContains(t, cfg.Validate(), "identity_hmac_secret")

	cfg.IdentityHMACSecret = testReplayIdentityHMACSecret
	require.ErrorContains(t, cfg.Validate(), "admission_redis_url")

	cfg.AdmissionRedisURL = "redis://rum-admission:test-secret-password-at-least-32-chars@127.0.0.1:6379"
	require.NoError(t, cfg.Validate())

	cfg.IdentityHMACPrevious = "short"
	require.ErrorContains(t, cfg.Validate(), "identity_hmac_previous_secret")
}

func TestReplayChecksCurrentAndPreviousErasureFenceIdentities(t *testing.T) {
	r, _ := newReplayTestReceiver(t)
	r.cfg.IdentityHMACPrevious = "previous-rum-replay-hmac-secret-at-least-32-bytes"
	r.cfg.IdentityHMACPrevVer = "v0"

	fences := r.identityFences("session", "session-1")

	require.Len(t, fences, 2)
	require.Equal(t, []string{"v1", "v0"}, []string{fences[0].Version, fences[1].Version})
	require.NotEqual(t, fences[0].Digest, fences[1].Digest)
}

func TestReplayRejectsMissingKeyAndUnknownApplicationFailClosed(t *testing.T) {
	tests := []struct {
		name   string
		status int
		mutate func(map[string]string)
	}{
		{name: "missing key", status: http.StatusUnauthorized, mutate: func(headers map[string]string) {
			delete(headers, headerAPIKey)
		}},
		{name: "wrong key", status: http.StatusForbidden, mutate: func(headers map[string]string) {
			headers[headerAPIKey] = "wrong-key"
		}},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			r, sink := newReplayTestReceiver(t)
			headers := validReplayHeaders()
			test.mutate(headers)
			response := performReplay(r, gzipJSON(t, signedTestEnvelope(t)), headers)
			require.Equal(t, test.status, response.Code)
			require.Empty(t, sink.AllLogs())
		})
	}
}

func TestReplayRejectsUnknownApplicationFailClosed(t *testing.T) {
	r, sink := newReplayTestReceiver(t)
	envelope := signedTestEnvelope(t)
	envelope.Application = "not-registered"
	resignTestEnvelope(t, &envelope)
	headers := validReplayHeaders()
	headers[headerApplication] = envelope.Application

	response := performReplay(r, gzipJSON(t, envelope), headers)

	require.Equal(t, http.StatusForbidden, response.Code)
	require.Empty(t, sink.AllLogs())
}

func TestReplayAcceptsValidEnvelopeAndEmitsCompressedCarrierGolden(t *testing.T) {
	r, sink := newReplayTestReceiver(t)
	input := signedTestEnvelope(t)
	response := performReplay(r, gzipJSON(t, input), validReplayHeaders())

	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, sink.AllLogs(), 1)
	logs := sink.AllLogs()[0]
	snapshot := carrierSnapshot(t, logs)
	want, err := os.ReadFile("testdata/carrier.golden.json")
	require.NoError(t, err)
	require.JSONEq(t, string(want), string(snapshot))

	record := logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	compressed := record.Body().Bytes().AsRaw()
	require.Equal(t, []byte{0x1f, 0x8b}, compressed[:2])
	decoded := gunzip(t, compressed)
	var stored testEnvelope
	require.NoError(t, json.Unmarshal(decoded, &stored))
	wantStored := input
	wantStored.UserID = ""
	wantStored.Events[0] = json.RawMessage(`{"data":{"height":900,"href":"about:blank","width":1440},"timestamp":1784109595000,"type":4}`)
	wantStored.SegmentID = stored.SegmentID
	wantStored.ChecksumSHA256 = stored.ChecksumSHA256
	require.Equal(t, wantStored, stored)
	require.NotEqual(t, input.SegmentID, stored.SegmentID)
	require.NotEqual(t, input.ChecksumSHA256, stored.ChecksumSHA256)
}

func TestReplayExplicitUserIdentityPersistsOnlyErasureKeys(t *testing.T) {
	r, sink := newReplayTestReceiver(t)
	input := signedTestEnvelope(t)
	response := performReplay(r, gzipJSON(t, input), validReplayHeaders())

	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, sink.AllLogs(), 1)
	record := sink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	stored := string(gunzip(t, record.Body().Bytes().AsRaw()))
	require.NotContains(t, stored, input.UserID)
	require.NotContains(t, stored, "user_id")
	attrs := record.Attributes()
	userKey, ok := attrs.Get("rum.erasure.user_key")
	require.True(t, ok)
	require.Equal(t, "db0d9cde8ecfa9bcf525c05ede5a7650ca982745c293b5290931109fb361f1b2", userKey.Str())
	sessionKey, ok := attrs.Get("rum.erasure.session_key")
	require.True(t, ok)
	require.Equal(t, "d4f765e8a1b630aadf93f372cebd34da2398c7d9e379743369781901276b9a74", sessionKey.Str())
	acceptedAt, ok := attrs.Get("rum.accepted_at_unix_nano")
	require.True(t, ok)
	require.Equal(t, replayObservedAt.UnixNano(), acceptedAt.Int())
	keyVersion, ok := attrs.Get("rum.erasure.key_version")
	require.True(t, ok)
	require.Equal(t, "v1", keyVersion.Str())
}

func TestReplayAcceptsAnonymousSessionWithDomainSeparatedErasureKey(t *testing.T) {
	r, sink := newReplayTestReceiver(t)
	input := signedTestEnvelope(t)
	input.UserID = ""
	resignTestEnvelope(t, &input)

	response := performReplay(r, gzipJSON(t, input), validReplayHeaders())

	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, sink.AllLogs(), 1)
	record := sink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	stored := string(gunzip(t, record.Body().Bytes().AsRaw()))
	require.NotContains(t, stored, "user_id")
	userKey, ok := record.Attributes().Get("rum.erasure.user_key")
	require.True(t, ok)
	require.Equal(t, "4bc120846b15db65cd97db9a015b98774aa6dc43d0ed0fba7d50ebc14f33bb44", userKey.Str())
	require.NotEqual(t, "db0d9cde8ecfa9bcf525c05ede5a7650ca982745c293b5290931109fb361f1b2", userKey.Str())
}

func TestFaroTransportGoldenEnvelopeIsAcceptedWithoutContractTranslation(t *testing.T) {
	r, sink := newReplayTestReceiver(t)
	r.ingress = newFakeReplayKeyAuthorizer(map[string]string{"checkout": testReplayBrowserKey})
	r.now = func() time.Time { return time.Unix(1, 0).UTC() }
	canonical, err := os.ReadFile("testdata/faro_transport_envelope.golden.json")
	require.NoError(t, err)
	canonical = bytes.TrimSpace(canonical)
	headers := validReplayHeaders()
	headers[headerFaroSessionID] = "session-01"
	headers[headerApplication] = "checkout"

	response := performReplayBytes(r, gzipRaw(t, canonical), headers)
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, sink.AllLogs(), 1)
	stored := sink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Body().Bytes().AsRaw()
	require.NotEqual(t, canonical, gunzip(t, stored))
	require.NotContains(t, string(gunzip(t, stored)), "token=a&next=<checkout>")
}

func TestReplayAcceptsFaroISOStringAtWholeSecond(t *testing.T) {
	r, sink := newReplayTestReceiver(t)
	envelope := signedTestEnvelope(t)
	envelope.StartedAt = "2026-07-15T09:59:55.000Z"
	envelope.EndedAt = "2026-07-15T09:59:55.000Z"
	resignTestEnvelope(t, &envelope)

	response := performReplay(r, gzipJSON(t, envelope), validReplayHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, sink.AllLogs(), 1)
}

func TestReplayPropagatesOnlyTrustedTenantAndGeoMetadata(t *testing.T) {
	var captured client.Info
	var capturedLogs plog.Logs
	next, err := consumer.NewLogs(func(ctx context.Context, logs plog.Logs) error {
		captured = client.FromContext(ctx)
		capturedLogs = logs
		return nil
	})
	require.NoError(t, err)
	r := newReceiverWithConsumer(t, next)
	headers := validReplayHeaders()
	headers[headerGeoCountry] = "CN"
	headers[headerGeoCity] = "Shanghai"
	headers["X-Authorization"] = "must-not-propagate"

	response := performReplay(r, gzipJSON(t, signedTestEnvelope(t)), headers)
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Equal(t, []string{"tenant-a"}, captured.Metadata.Get(headerTenantID))
	require.Equal(t, []string{testReplayCredentialLookup}, captured.Metadata.Get(headerCredentialLookup))
	require.Equal(t, []string{"storefront"}, captured.Metadata.Get(headerApplication))
	require.Equal(t, []string{"replay"}, captured.Metadata.Get(headerRequestClass))
	require.Equal(t, []string{"CN"}, captured.Metadata.Get(headerGeoCountry))
	require.Equal(t, []string{"Shanghai"}, captured.Metadata.Get(headerGeoCity))
	require.Empty(t, captured.Metadata.Get("X-API-Key"))
	require.Empty(t, captured.Metadata.Get("X-Authorization"))
	resource := capturedLogs.ResourceLogs().At(0).Resource().Attributes()
	country, ok := resource.Get("geo.country.iso_code")
	require.True(t, ok)
	require.Equal(t, "CN", country.Str())
	city, ok := resource.Get("geo.locality.name")
	require.True(t, ok)
	require.Equal(t, "Shanghai", city.Str())
	_, hasOldCountry := resource.Get("geo.country")
	_, hasOldCity := resource.Get("geo.city")
	require.False(t, hasOldCountry)
	require.False(t, hasOldCity)
}

func TestReplayRequiresMediaTypeAndGzip(t *testing.T) {
	r, sink := newReplayTestReceiver(t)
	body := gzipJSON(t, signedTestEnvelope(t))

	wrongType := validReplayHeaders()
	wrongType["Content-Type"] = "application/json"
	require.Equal(t, http.StatusBadRequest, performReplay(r, body, wrongType).Code)

	missingGzip := validReplayHeaders()
	delete(missingGzip, "Content-Encoding")
	require.Equal(t, http.StatusBadRequest, performReplay(r, body, missingGzip).Code)
	require.Empty(t, sink.AllLogs())
}

func TestReplayRequiresHeaderApplicationToMatchEnvelope(t *testing.T) {
	r, sink := newReplayTestReceiver(t)
	r.ingress = newFakeReplayKeyAuthorizer(map[string]string{
		"storefront": testReplayBrowserKey,
		"admin":      testReplayBrowserKey,
	})
	body := gzipJSON(t, signedTestEnvelope(t))

	wrongApplication := validReplayHeaders()
	wrongApplication[headerApplication] = "admin"
	require.Equal(t, http.StatusBadRequest, performReplay(r, body, wrongApplication).Code)
	require.Empty(t, sink.AllLogs())
}

func TestReplayOptionsPublishesFixedBrowserCORSContract(t *testing.T) {
	r, _ := newReplayTestReceiver(t)
	request := httptest.NewRequest(http.MethodOptions, replayPath, nil)
	response := httptest.NewRecorder()

	r.handleReplay(response, request)

	require.Equal(t, http.StatusNoContent, response.Code)
	require.Equal(t, "*", response.Header().Get("Access-Control-Allow-Origin"))
	require.Equal(t, "POST, OPTIONS", response.Header().Get("Access-Control-Allow-Methods"))
	require.Equal(
		t,
		"Content-Type, Content-Encoding, X-API-Key, X-Faro-Session-Id, X-RUM-Application, X-RUM-Batch-Id",
		response.Header().Get("Access-Control-Allow-Headers"),
	)
	require.Empty(t, response.Header().Get("Access-Control-Allow-Credentials"))
}

func TestReplayRejectsChecksumMismatchAndUnknownFields(t *testing.T) {
	r, sink := newReplayTestReceiver(t)
	envelope := signedTestEnvelope(t)
	envelope.ChecksumSHA256 = strings.Repeat("0", 64)
	require.Equal(t, http.StatusBadRequest, performReplay(r, gzipJSON(t, envelope), validReplayHeaders()).Code)

	canonical, err := json.Marshal(signedTestEnvelope(t))
	require.NoError(t, err)
	withUnknown := bytes.Replace(canonical, []byte(`{"schema_version":1`), []byte(`{"schema_version":1,"tenant":"spoofed"`), 1)
	require.Equal(t, http.StatusBadRequest, performReplayBytes(r, gzipRaw(t, withUnknown), validReplayHeaders()).Code)
	require.Empty(t, sink.AllLogs())
}

func TestReplayPreservesOrdinaryTextAndSanitizesSensitiveRrwebContentBeforeCarrier(t *testing.T) {
	events := []json.RawMessage{
		json.RawMessage(`{
			"type": 4,
			"timestamp": 1784109595000,
			"data": {"href": "https://shop.example.test/private?token=meta-secret", "width": 1440, "height": 900}
		}`),
		json.RawMessage(`{
			"type": 2,
			"timestamp": 1784109595000,
			"data": {
				"node": {
					"type": 0,
					"id": 1,
					"childNodes": [{
						"type": 2,
						"id": 2,
						"tagName": "form",
						"attributes": {
							"action": "https://alice:password@example.test/checkout?token=url-secret#fragment-secret",
							"alt": "alt-secret",
							"aria-label": "aria-secret",
							"class": "checkout-form",
							"data-user": "data-secret",
							"placeholder": "placeholder-secret",
							"rr_dataURL": "data:image/png;base64,canvas-snapshot-secret",
							"rr_src": "https://dave:password@example.test/frame?token=rr-src-secret#rr-src-fragment",
							"title": "title-secret",
							"value": "value-secret"
						},
						"childNodes": [
							{"type": 3, "id": 3, "textContent": "full-snapshot-secret"},
							{
								"type": 2,
								"id": 4,
								"tagName": "img",
								"attributes": {"src": "https://bob:password@cdn.example.test/image.png?signature=image-secret#image-fragment"},
								"childNodes": []
							}
						]
					}]
				},
				"initialOffset": {"top": 0, "left": 0}
			}
		}`),
		json.RawMessage(`{
			"type": 3,
			"timestamp": 1784109595001,
			"data": {
				"source": 0,
				"texts": [
					{"id": 3, "value": "mutation-text-secret https://docs.example.test/help"},
					{"id": 7, "value": ".avatar{background:u\\72l(https://egress.invalid/a.png)}"}
				],
				"attributes": [{
					"id": 2,
					"attributes": {
						"href": "https://carol:password@example.test/account?token=mutation-url-secret#mutation-fragment",
						"data-account": "mutation-data-secret",
						"value": "mutation-attribute-secret"
					}
				}],
				"removes": [],
				"adds": [{
					"parentId": 2,
					"nextId": null,
					"node": {"type": 3, "id": 5, "textContent": "added-node-secret"}
				}]
			}
		}`),
		json.RawMessage(`{
			"type": 3,
			"timestamp": 1784109595002,
			"data": {"source": 5, "id": 6, "text": "input-secret", "isChecked": false, "userTriggered": true}
		}`),
	}
	input := signedEnvelopeForEvents(t, events, true)
	r, sink := newReplayTestReceiver(t)
	body := gzipJSON(t, input)
	_, decodeErr := decodeReplay(bytes.NewReader(body), r.cfg, replayObservedAt)
	require.NoError(t, decodeErr)

	response := performReplay(r, body, validReplayHeaders())
	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, sink.AllLogs(), 1)
	record := sink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	storedBytes := gunzip(t, record.Body().Bytes().AsRaw())
	storedText := string(storedBytes)

	for _, secret := range []string{
		"alice", "bob", "carol", "password", "url-secret", "fragment-secret",
		"alt-secret", "aria-secret", "data-secret", "placeholder-secret", "title-secret",
		"value-secret", "image-secret", "image-fragment",
		"mutation-url-secret", "mutation-fragment",
		"meta-secret", "mutation-data-secret", "mutation-attribute-secret", "input-secret",
		"canvas-snapshot-secret", "dave", "rr-src-secret", "rr-src-fragment",
		"egress.invalid",
	} {
		require.NotContains(t, storedText, secret)
	}
	for _, readableText := range []string{
		"full-snapshot-secret", "mutation-text-secret https://docs.example.test/help", "added-node-secret",
	} {
		require.Contains(t, storedText, readableText)
	}
	for _, requestPrimitive := range []string{
		`"action"`, `"src"`, `"rr_src"`, "shop.example.test", "cdn.example.test",
	} {
		require.NotContains(t, storedText, requestPrimitive)
	}
	require.Contains(t, storedText, `"href":"about:blank"`)

	var stored testEnvelope
	require.NoError(t, json.Unmarshal(storedBytes, &stored))
	require.NotEqual(t, input.SegmentID, stored.SegmentID)
	require.NotEqual(t, input.ChecksumSHA256, stored.ChecksumSHA256)
	require.Regexp(t, checksumPattern, stored.SegmentID)
	require.Regexp(t, checksumPattern, stored.ChecksumSHA256)
	wantChecksum := stored.ChecksumSHA256
	resignTestEnvelope(t, &stored)
	require.Equal(t, wantChecksum, stored.ChecksumSHA256)

	secondReceiver, secondSink := newReplayTestReceiver(t)
	secondResponse := performReplay(secondReceiver, gzipJSON(t, input), validReplayHeaders())
	require.Equal(t, http.StatusAccepted, secondResponse.Code)
	secondRecord := secondSink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	require.Equal(t, record.Body().Bytes().AsRaw(), secondRecord.Body().Bytes().AsRaw())
}

func TestReplayTransformsExecutableElementsAndDropsRequestCapableAttributes(t *testing.T) {
	raw := json.RawMessage(`{
		"type": 2,
		"id": 1,
		"tagName": "iframe",
		"isCustom": true,
		"attributes": {
			"src": "https://beacon.invalid/frame",
			"srcdoc": "<img src=https://beacon.invalid/nested>",
			"onload": "fetch('https://beacon.invalid/script')",
			"style": "background:url(https://beacon.invalid/style)",
			"class": "customer-alice",
			"title": "Alice"
		},
		"childNodes": []
	}`)

	node, err := sanitizeSerializedNode(raw, 0)
	require.NoError(t, err)
	encoded, err := json.Marshal(node)
	require.NoError(t, err)
	require.JSONEq(t, `{
		"type": 2,
		"id": 1,
		"tagName": "div",
		"isCustom": false,
		"attributes": {},
		"childNodes": []
	}`, string(encoded))
	require.NotContains(t, string(encoded), "beacon.invalid")
	require.NotContains(t, string(encoded), "Alice")
}

func TestReplayTransformsNetworkCapableHTMLCarriers(t *testing.T) {
	for _, tagName := range []string{"audio", "form", "img", "picture", "video"} {
		t.Run(tagName, func(t *testing.T) {
			raw, err := json.Marshal(map[string]any{
				"type":       2,
				"id":         1,
				"tagName":    tagName,
				"attributes": map[string]any{},
				"childNodes": []any{},
			})
			require.NoError(t, err)

			node, err := sanitizeSerializedNode(raw, 0)
			require.NoError(t, err)
			encoded, err := json.Marshal(node)
			require.NoError(t, err)
			require.Contains(t, string(encoded), `"tagName":"div"`)
			require.NotContains(t, string(encoded), `"tagName":"`+tagName+`"`)
		})
	}
}

// rrweb inlineStylesheet 把同源 CSS 写在 <link _cssText>；collector 必须转成 <style>
// 并保留净化后的 CSS，否则回放零外联壳下会整页无样式。
func TestReplayPreservesInlinedLinkStylesheet(t *testing.T) {
	raw, err := json.Marshal(map[string]any{
		"type":    2,
		"id":      1,
		"tagName": "link",
		"attributes": map[string]any{
			"rel":      "stylesheet",
			"href":     "https://cdn.example/app.css",
			"_cssText": ".hero{display:flex;gap:8px;color:#123;background:linear-gradient(90deg,#fff,#eee);transition:opacity .2s}",
		},
		"childNodes": []any{},
	})
	require.NoError(t, err)

	node, err := sanitizeSerializedNode(raw, 0)
	require.NoError(t, err)
	encoded, err := json.Marshal(node)
	require.NoError(t, err)

	require.Contains(t, string(encoded), `"tagName":"style"`)
	require.Contains(t, string(encoded), ".hero{display:flex")
	require.Contains(t, string(encoded), "linear-gradient(90deg,#fff,#eee)")
	require.Contains(t, string(encoded), "transition:opacity .2s")
	require.NotContains(t, string(encoded), "cdn.example")
	require.NotContains(t, string(encoded), `"href"`)
	require.NotContains(t, string(encoded), `"rel"`)
}

// 晚加载 stylesheet：快照时 link 尚无 _cssText，仍须转成空 style 保留节点 id，
// 后续 attribute mutation 才能把 _cssText 写回同一节点。
func TestReplayConvertsEmptyLinkToStyleForLateCssMutation(t *testing.T) {
	raw, err := json.Marshal(map[string]any{
		"type":       2,
		"id":         42,
		"tagName":    "link",
		"attributes": map[string]any{"rel": "stylesheet", "href": "https://cdn.example/late.css"},
		"childNodes": []any{},
	})
	require.NoError(t, err)

	node, err := sanitizeSerializedNode(raw, 0)
	require.NoError(t, err)
	encoded, err := json.Marshal(node)
	require.NoError(t, err)
	require.JSONEq(t, `{
		"type": 2,
		"id": 42,
		"tagName": "style",
		"attributes": {},
		"childNodes": []
	}`, string(encoded))
}

func TestReplayMetaURLCannotBecomeAReplayBaseURL(t *testing.T) {
	data, err := sanitizeMetaEvent(json.RawMessage(`{
		"href":"https://customer.example/users/alice?token=secret#profile",
		"width":1280,
		"height":720
	}`))
	require.NoError(t, err)
	require.Equal(t, map[string]any{
		"height": json.Number("720"),
		"href":   "about:blank",
		"width":  json.Number("1280"),
	}, data)
}

func TestReplayAcceptsGrafanaRrwebCustomElementDefineEvent(t *testing.T) {
	event := json.RawMessage(`{
		"type": 3,
		"timestamp": 1784109595000,
		"data": {"source": 16, "define": {"name": "weops-widget"}}
	}`)
	r, sink := newReplayTestReceiver(t)
	envelope := signedEnvelopeForEvents(t, []json.RawMessage{event}, false)

	response := performReplay(r, gzipJSON(t, envelope), validReplayHeaders())

	require.Equal(t, http.StatusAccepted, response.Code)
	require.Len(t, sink.AllLogs(), 1)
	storedBytes := gunzip(t, sink.AllLogs()[0].ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Body().Bytes().AsRaw())
	var stored testEnvelope
	require.NoError(t, json.Unmarshal(storedBytes, &stored))
	require.Len(t, stored.Events, 1)
	require.JSONEq(t, `{
		"type": 3,
		"timestamp": 1784109595000,
		"data": {"source": 16, "define": {"name": "weops-widget"}}
	}`, string(stored.Events[0]))
}

func TestReplayCustomElementDefineEventUsesStrictShapeAndNameBounds(t *testing.T) {
	maximumName := "a-" + strings.Repeat("b", maxCustomElementNameLength-2)
	accepted, err := sanitizeIncrementalSnapshot(json.RawMessage(`{"source":16,"define":{"name":"` + maximumName + `"}}`))
	require.NoError(t, err)
	require.Equal(t, map[string]any{
		"define": map[string]any{"name": maximumName},
		"source": int64(16),
	}, accepted)

	tests := []struct {
		name string
		data json.RawMessage
	}{
		{name: "missing definition", data: json.RawMessage(`{"source":16}`)},
		{name: "non-object definition", data: json.RawMessage(`{"source":16,"define":"weops-widget"}`)},
		{name: "missing name", data: json.RawMessage(`{"source":16,"define":{}}`)},
		{name: "non-string name", data: json.RawMessage(`{"source":16,"define":{"name":42}}`)},
		{name: "name without custom-element hyphen", data: json.RawMessage(`{"source":16,"define":{"name":"widget"}}`)},
		{name: "uppercase name", data: json.RawMessage(`{"source":16,"define":{"name":"Weops-widget"}}`)},
		{name: "name exceeds bound", data: json.RawMessage(`{"source":16,"define":{"name":"a-` + strings.Repeat("b", maxCustomElementNameLength-1) + `"}}`)},
		{name: "unknown definition field", data: json.RawMessage(`{"source":16,"define":{"name":"weops-widget","constructor":"secret"}}`)},
		{name: "unknown event field", data: json.RawMessage(`{"source":16,"define":{"name":"weops-widget"},"options":{"extends":"secret"}}`)},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			_, err := sanitizeIncrementalSnapshot(test.data)
			require.Error(t, err)
		})
	}
}

func TestReplayRejectsOpaqueHighRiskRrwebEvents(t *testing.T) {
	tests := []struct {
		name  string
		event json.RawMessage
	}{
		{name: "custom event", event: json.RawMessage(`{"type":5,"timestamp":1784109595000,"data":{"tag":"leak","payload":"secret"}}`)},
		{name: "plugin event", event: json.RawMessage(`{"type":6,"timestamp":1784109595000,"data":{"plugin":"leak","payload":"secret"}}`)},
		{name: "asset event", event: json.RawMessage(`{"type":7,"timestamp":1784109595000,"data":{"url":"https://example.test/secret","payload":"secret"}}`)},
		{name: "canvas source", event: json.RawMessage(`{"type":3,"timestamp":1784109595000,"data":{"source":9,"id":1,"commands":[{"property":"drawImage","args":["secret"]}]}}`)},
		{name: "font source", event: json.RawMessage(`{"type":3,"timestamp":1784109595000,"data":{"source":10,"family":"secret","fontSource":"secret","buffer":false}}`)},
		{name: "log source", event: json.RawMessage(`{"type":3,"timestamp":1784109595000,"data":{"source":11,"payload":["secret"]}}`)},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			r, sink := newReplayTestReceiver(t)
			envelope := signedEnvelopeForEvents(t, []json.RawMessage{test.event}, false)
			response := performReplay(r, gzipJSON(t, envelope), validReplayHeaders())
			require.Equal(t, http.StatusBadRequest, response.Code)
			require.Empty(t, sink.AllLogs())
		})
	}
}

func TestReplayValidatesRrwebEventFactsAgainstEnvelope(t *testing.T) {
	validMeta := json.RawMessage(`{
		"type": 4,
		"timestamp": 1784109595000,
		"data": {"href": "https://customer.example/private", "width": 1280, "height": 720}
	}`)
	validFullSnapshot := json.RawMessage(`{
		"type": 2,
		"timestamp": 1784109595000,
		"data": {"node": {"type": 0, "id": 1, "childNodes": []}, "initialOffset": {"top": 0, "left": 0}}
	}`)
	tests := []struct {
		name   string
		mutate func(*testEnvelope)
	}{
		{name: "started_at differs from minimum event timestamp", mutate: func(envelope *testEnvelope) {
			envelope.StartedAt = "2026-07-15T09:59:54Z"
		}},
		{name: "ended_at differs from maximum event timestamp", mutate: func(envelope *testEnvelope) {
			envelope.EndedAt = "2026-07-15T09:59:56Z"
		}},
		{name: "has_full_snapshot is false despite event", mutate: func(envelope *testEnvelope) {
			envelope.HasFullSnapshot = false
		}},
		{name: "event timestamp is fractional", mutate: func(envelope *testEnvelope) {
			envelope.Events[1] = json.RawMessage(`{"type":2,"timestamp":1784109595000.5,"data":{"node":{"type":0,"id":1,"childNodes":[]},"initialOffset":{"top":0,"left":0}}}`)
		}},
		{name: "event type is not an integer", mutate: func(envelope *testEnvelope) {
			envelope.Events[1] = json.RawMessage(`{"type":"2","timestamp":1784109595000,"data":{}}`)
		}},
		{name: "unknown event field", mutate: func(envelope *testEnvelope) {
			envelope.Events[1] = json.RawMessage(`{"type":2,"timestamp":1784109595000,"data":{"node":{"type":0,"id":1,"childNodes":[]},"initialOffset":{"top":0,"left":0}},"rawSecret":"secret"}`)
		}},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			r, sink := newReplayTestReceiver(t)
			envelope := signedEnvelopeForEvents(t, []json.RawMessage{validMeta, validFullSnapshot}, true)
			test.mutate(&envelope)
			resignTestEnvelope(t, &envelope)
			response := performReplay(r, gzipJSON(t, envelope), validReplayHeaders())
			require.Equal(t, http.StatusBadRequest, response.Code)
			require.Empty(t, sink.AllLogs())
		})
	}
}

func TestReplaySequenceZeroRequiresOrderedMetaAndFullSnapshotBootstrap(t *testing.T) {
	meta := json.RawMessage(`{
		"type": 4,
		"timestamp": 1784109595000,
		"data": {"href": "https://customer.example/private?secret=value", "width": 1280, "height": 720}
	}`)
	fullSnapshot := json.RawMessage(`{
		"type": 2,
		"timestamp": 1784109595002,
		"data": {"node": {"type": 0, "id": 1, "childNodes": []}, "initialOffset": {"top": 0, "left": 0}}
	}`)
	earlyFullSnapshot := json.RawMessage(`{
		"type": 2,
		"timestamp": 1784109595000,
		"data": {"node": {"type": 0, "id": 1, "childNodes": []}, "initialOffset": {"top": 0, "left": 0}}
	}`)
	lateMeta := json.RawMessage(`{
		"type": 4,
		"timestamp": 1784109595002,
		"data": {"href": "https://customer.example/private?secret=value", "width": 1280, "height": 720}
	}`)
	prefixIncremental := json.RawMessage(`{
		"type": 3,
		"timestamp": 1784109595000,
		"data": {"source": 5, "id": 6, "text": "", "isChecked": false, "userTriggered": true}
	}`)
	middleMeta := json.RawMessage(`{
		"type": 4,
		"timestamp": 1784109595001,
		"data": {"href": "https://customer.example/private?secret=value", "width": 1280, "height": 720}
	}`)
	middleIncremental := json.RawMessage(`{
		"type": 3,
		"timestamp": 1784109595001,
		"data": {"source": 5, "id": 6, "text": "", "isChecked": false, "userTriggered": true}
	}`)

	valid := signedEnvelopeForEvents(t, []json.RawMessage{meta, fullSnapshot}, true)
	valid.Sequence = 0
	resignTestEnvelope(t, &valid)
	validReceiver, validSink := newReplayTestReceiver(t)
	validResponse := performReplay(validReceiver, gzipJSON(t, valid), validReplayHeaders())
	require.Equal(t, http.StatusAccepted, validResponse.Code)
	require.Len(t, validSink.AllLogs(), 1)

	tests := []struct {
		name            string
		events          []json.RawMessage
		hasFullSnapshot bool
	}{
		{name: "missing meta", events: []json.RawMessage{earlyFullSnapshot}, hasFullSnapshot: true},
		{name: "missing full snapshot", events: []json.RawMessage{meta}, hasFullSnapshot: false},
		{name: "full snapshot before meta", events: []json.RawMessage{earlyFullSnapshot, lateMeta}, hasFullSnapshot: true},
		{name: "incremental before bootstrap", events: []json.RawMessage{prefixIncremental, middleMeta, fullSnapshot}, hasFullSnapshot: true},
		{name: "event between bootstrap pair", events: []json.RawMessage{meta, middleIncremental, fullSnapshot}, hasFullSnapshot: true},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			envelope := signedEnvelopeForEvents(t, test.events, test.hasFullSnapshot)
			envelope.Sequence = 0
			resignTestEnvelope(t, &envelope)
			r, sink := newReplayTestReceiver(t)

			response := performReplay(r, gzipJSON(t, envelope), validReplayHeaders())

			require.Equal(t, http.StatusBadRequest, response.Code)
			require.Empty(t, sink.AllLogs())
		})
	}
}

func TestReplayValidatesVersionIdentityTimesCountAndSessionHeader(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*testEnvelope, map[string]string)
	}{
		{name: "version", mutate: func(e *testEnvelope, _ map[string]string) { e.SchemaVersion = 2 }},
		{name: "application", mutate: func(e *testEnvelope, _ map[string]string) { e.Application = "" }},
		{name: "id", mutate: func(e *testEnvelope, _ map[string]string) { e.SegmentID = "bad/id" }},
		{name: "sequence overflow", mutate: func(e *testEnvelope, _ map[string]string) { e.Sequence = 1 << 32 }},
		{name: "time order", mutate: func(e *testEnvelope, _ map[string]string) { e.EndedAt = "2026-07-15T09:00:00Z" }},
		{name: "far future", mutate: func(e *testEnvelope, _ map[string]string) {
			e.StartedAt = "2100-01-01T00:00:00Z"
			e.EndedAt = "2100-01-01T00:00:01Z"
		}},
		{name: "older than 24 hours", mutate: func(e *testEnvelope, _ map[string]string) {
			e.StartedAt = "2026-07-14T09:59:59Z"
			e.EndedAt = "2026-07-14T10:00:00Z"
		}},
		{name: "segment longer than 5 minutes", mutate: func(e *testEnvelope, _ map[string]string) {
			e.StartedAt = "2026-07-15T09:50:00Z"
			e.EndedAt = "2026-07-15T09:55:01Z"
		}},
		{name: "event count", mutate: func(e *testEnvelope, _ map[string]string) { e.EventCount = 3 }},
		{name: "session header", mutate: func(_ *testEnvelope, h map[string]string) { h[headerFaroSessionID] = "other-session" }},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			r, sink := newReplayTestReceiver(t)
			envelope := signedTestEnvelope(t)
			headers := validReplayHeaders()
			test.mutate(&envelope, headers)
			resignTestEnvelope(t, &envelope)
			response := performReplay(r, gzipJSON(t, envelope), headers)
			require.Equal(t, http.StatusBadRequest, response.Code)
			require.Empty(t, sink.AllLogs())
		})
	}
}

func TestReplayEnforcesCompressedDecompressedRatioEventAndDepthLimits(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*Config, *testEnvelope)
	}{
		{name: "compressed", mutate: func(c *Config, _ *testEnvelope) { c.MaxCompressedBytes = 16 }},
		{name: "decompressed", mutate: func(c *Config, _ *testEnvelope) { c.MaxDecompressedBytes = 128 }},
		{name: "ratio", mutate: func(c *Config, e *testEnvelope) {
			c.MaxCompressionRatio = 1
			e.Events = []json.RawMessage{json.RawMessage(`{"type":2,"data":"` + strings.Repeat("a", 4096) + `"}`)}
			e.EventCount = 1
		}},
		{name: "event count", mutate: func(c *Config, _ *testEnvelope) { c.MaxEvents = 0 }},
		{name: "event bytes", mutate: func(c *Config, _ *testEnvelope) { c.MaxEventBytes = 8 }},
		{name: "depth", mutate: func(c *Config, e *testEnvelope) {
			c.MaxJSONDepth = 4
			e.Events = []json.RawMessage{json.RawMessage(`{"a":{"b":{"c":{"d":1}}}}`)}
			e.EventCount = 1
		}},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			r, sink := newReplayTestReceiver(t)
			envelope := signedTestEnvelope(t)
			test.mutate(r.cfg, &envelope)
			resignTestEnvelope(t, &envelope)
			response := performReplay(r, gzipJSON(t, envelope), validReplayHeaders())
			require.Equal(t, http.StatusRequestEntityTooLarge, response.Code)
			require.Empty(t, sink.AllLogs())
		})
	}
}

func FuzzDecodeReplay(f *testing.F) {
	seed := signedTestEnvelopeNoTest(f)
	f.Add(gzipJSONNoTest(seed))
	f.Add([]byte("not gzip"))
	f.Add(gzipRawNoTest([]byte(`{"schema_version":1,"events":[]}`)))
	cfg := defaultConfig()
	cfg.MaxCompressedBytes = 8192
	cfg.MaxDecompressedBytes = 16384
	f.Fuzz(func(t *testing.T, body []byte) {
		if len(body) > 9000 {
			t.Skip()
		}
		_, _ = decodeReplay(bytes.NewReader(body), cfg, replayObservedAt)
	})
}

func newReplayTestReceiver(t *testing.T) (*replayReceiver, *consumertest.LogsSink) {
	t.Helper()
	sink := new(consumertest.LogsSink)
	return newReceiverWithConsumer(t, sink), sink
}

func newReceiverWithConsumer(t *testing.T, next consumer.Logs) *replayReceiver {
	t.Helper()
	settings := receivertest.NewNopSettings(receiverType)
	cfg := defaultConfig()
	cfg.IdentityHMACSecret = testReplayIdentityHMACSecret
	cfg.TenantID = testReplayTenantID
	cfg.AdmissionRedisURL = "redis://rum-admission:test-secret-password-at-least-32-chars@127.0.0.1:6379"
	r, err := newReplayReceiver(cfg, &settings, next)
	require.NoError(t, err)
	r.ingress = newFakeReplayKeyAuthorizer(map[string]string{"storefront": testReplayBrowserKey})
	r.now = func() time.Time { return replayObservedAt }
	return r
}

// fakeReplayKeyAuthorizer is a test double for ingressAdmission that avoids
// a real Redis dependency. An empty store rejects every application.
type fakeReplayKeyAuthorizer struct {
	keys map[string]string
	err  error
}

func newFakeReplayKeyAuthorizer(keys map[string]string) *fakeReplayKeyAuthorizer {
	return &fakeReplayKeyAuthorizer{keys: keys}
}

func (f *fakeReplayKeyAuthorizer) Admit(_ context.Context, request ingress.Request) (ingress.Decision, error) {
	if f.err != nil {
		return ingress.Decision{}, f.err
	}
	want, ok := f.keys[request.Application]
	if !ok || want != request.BrowserKey {
		return ingress.Decision{Reason: ingress.RejectBrowserKey}, nil
	}
	return ingress.Decision{Allowed: true, TenantID: testReplayTenantID, Revision: 1}, nil
}

func (f *fakeReplayKeyAuthorizer) Start(context.Context) error    { return nil }
func (f *fakeReplayKeyAuthorizer) Shutdown(context.Context) error { return nil }

func validReplayHeaders() map[string]string {
	return map[string]string{
		headerAPIKey:        testReplayBrowserKey,
		headerApplication:   "storefront",
		headerBatchID:       "batch-7",
		headerFaroSessionID: "session-1",
		"Origin":            "https://app.example.test",
		"Content-Type":      replayContentType,
		"Content-Encoding":  "gzip",
	}
}

func performReplay(r *replayReceiver, body []byte, headers map[string]string) *httptest.ResponseRecorder {
	return performReplayBytes(r, body, headers)
}

func performReplayBytes(r *replayReceiver, body []byte, headers map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, replayPath, bytes.NewReader(body))
	for name, value := range headers {
		req.Header.Set(name, value)
	}
	response := httptest.NewRecorder()
	r.handleReplay(response, req)
	return response
}

func signedTestEnvelope(t testing.TB) testEnvelope {
	t.Helper()
	envelope := signedTestEnvelopeNoTest(t)
	require.Regexp(t, checksumPattern, envelope.ChecksumSHA256)
	require.Regexp(t, checksumPattern, envelope.SegmentID)
	return envelope
}

func signedTestEnvelopeNoTest(_ testing.TB) testEnvelope {
	envelope := testEnvelope{
		SchemaVersion:   1,
		Application:     "storefront",
		Environment:     "production",
		Release:         "2026.07.15",
		SessionID:       "session-1",
		UserID:          "user-42",
		PageID:          "page-1",
		RecordingID:     "recording-1",
		SegmentID:       "client-segment-1",
		Sequence:        3,
		StartedAt:       "2026-07-15T09:59:55Z",
		EndedAt:         "2026-07-15T09:59:55Z",
		HasFullSnapshot: true,
		EventCount:      2,
		Events: []json.RawMessage{
			json.RawMessage(`{"data":{"height":900,"href":"https://shop.example.test/private?token=secret","width":1440},"timestamp":1784109595000,"type":4}`),
			json.RawMessage(`{"data":{"initialOffset":{"left":0,"top":0},"node":{"childNodes":[],"id":1,"type":0}},"timestamp":1784109595000,"type":2}`),
		},
	}
	signTestEnvelopeNoTest(&envelope)
	return envelope
}

func signedEnvelopeForEvents(t testing.TB, events []json.RawMessage, hasFullSnapshot bool) testEnvelope {
	t.Helper()
	envelope := testEnvelope{
		SchemaVersion:   1,
		Application:     "storefront",
		Environment:     "production",
		Release:         "2026.07.15",
		SessionID:       "session-1",
		UserID:          "user-42",
		PageID:          "page-1",
		RecordingID:     "recording-1",
		SegmentID:       "client-segment-1",
		Sequence:        3,
		StartedAt:       "2026-07-15T09:59:55Z",
		EndedAt:         "2026-07-15T09:59:55Z",
		HasFullSnapshot: hasFullSnapshot,
		EventCount:      len(events),
		Events:          events,
	}
	if len(events) > 1 {
		envelope.EndedAt = "2026-07-15T09:59:55.002Z"
	}
	signTestEnvelopeNoTest(&envelope)
	return envelope
}

func resignTestEnvelope(t testing.TB, envelope *testEnvelope) {
	t.Helper()
	resignTestEnvelopeNoTest(envelope)
}

func resignTestEnvelopeNoTest(envelope *testEnvelope) {
	envelope.ChecksumSHA256 = ""
	encoded, _ := json.Marshal(envelope)
	var canonical replayEnvelope
	_ = json.Unmarshal(encoded, &canonical)
	material, _ := canonicalEnvelope(canonical, false)
	sum := sha256.Sum256(material)
	envelope.ChecksumSHA256 = hex.EncodeToString(sum[:])
}

func signTestEnvelopeNoTest(envelope *testEnvelope) {
	canonicalEvents := make([]json.RawMessage, len(envelope.Events))
	for index, raw := range envelope.Events {
		value, _ := decodeJSONValue(raw)
		canonicalEvents[index], _ = json.Marshal(value)
	}
	eventMaterial, _ := json.Marshal(canonicalEvents)
	eventDigest := sha256.Sum256(eventMaterial)
	segmentMaterial, _ := json.Marshal(map[string]any{
		"application": envelope.Application,
		"eventDigest": hex.EncodeToString(eventDigest[:]),
		"recordingId": envelope.RecordingID,
		"sequence":    envelope.Sequence,
		"sessionId":   envelope.SessionID,
	})
	segmentDigest := sha256.Sum256(segmentMaterial)
	envelope.SegmentID = hex.EncodeToString(segmentDigest[:])
	resignTestEnvelopeNoTest(envelope)
}

func gzipJSON(t testing.TB, envelope testEnvelope) []byte {
	t.Helper()
	body, err := json.Marshal(envelope)
	require.NoError(t, err)
	return gzipRaw(t, body)
}

func gzipJSONNoTest(envelope testEnvelope) []byte {
	body, _ := json.Marshal(envelope)
	return gzipRawNoTest(body)
}

func gzipRaw(t testing.TB, body []byte) []byte {
	t.Helper()
	var buffer bytes.Buffer
	writer := gzip.NewWriter(&buffer)
	_, err := writer.Write(body)
	require.NoError(t, err)
	require.NoError(t, writer.Close())
	return buffer.Bytes()
}

func gzipRawNoTest(body []byte) []byte {
	var buffer bytes.Buffer
	writer := gzip.NewWriter(&buffer)
	_, _ = writer.Write(body)
	_ = writer.Close()
	return buffer.Bytes()
}

func gunzip(t testing.TB, body []byte) []byte {
	t.Helper()
	reader, err := gzip.NewReader(bytes.NewReader(body))
	require.NoError(t, err)
	decoded, err := io.ReadAll(reader)
	require.NoError(t, err)
	require.NoError(t, reader.Close())
	return decoded
}

func carrierSnapshot(t *testing.T, logs plog.Logs) []byte {
	t.Helper()
	resourceLogs := logs.ResourceLogs().At(0)
	scopeLogs := resourceLogs.ScopeLogs().At(0)
	record := scopeLogs.LogRecords().At(0)
	keys := []string{
		"rum.accepted_at_unix_nano", "rum.erasure.key_version", "rum.erasure.session_key", "rum.erasure.user_key",
		"rum.replay.application", "rum.replay.checksum_sha256", "rum.replay.event_count",
		"rum.replay.has_full_snapshot", "rum.replay.recording.id", "rum.replay.schema.version",
		"rum.replay.segment.id", "rum.replay.sequence", "rum.replay.session.id",
	}
	attrs := map[string]any{}
	for _, key := range keys {
		value, ok := record.Attributes().Get(key)
		require.True(t, ok, "missing attr %s", key)
		attrs[key] = value.AsRaw()
	}
	tenant, ok := resourceLogs.Resource().Attributes().Get("tenant.id")
	require.True(t, ok)
	snapshot := map[string]any{
		"scope":        scopeLogs.Scope().Name(),
		"resource":     map[string]any{"tenant.id": tenant.Str()},
		"record":       attrs,
		"body_is_gzip": bytes.HasPrefix(record.Body().Bytes().AsRaw(), []byte{0x1f, 0x8b}),
	}
	encoded, err := json.Marshal(snapshot)
	require.NoError(t, err)
	return encoded
}

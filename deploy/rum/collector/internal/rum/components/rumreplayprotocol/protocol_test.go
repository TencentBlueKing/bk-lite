package rumreplayprotocol

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"
)

func TestStoredEnvelopeCanonicalBytesAreSharedAcrossCollectorModules(t *testing.T) {
	event := json.RawMessage([]byte(`{"type":2,"timestamp":1,"data":{"line":"` + "\u2028\u2029" + `","cssText":"main > span::before { content: \"<>&\"; }"}}`))
	envelope := StoredEnvelope{
		SchemaVersion:   1,
		Application:     "checkout",
		Environment:     "production",
		Release:         "2026.07.16",
		SessionID:       "session-1",
		PageID:          "page-1",
		RecordingID:     "recording-1",
		SegmentID:       "segment-1",
		Sequence:        0,
		StartedAt:       "1970-01-01T00:00:00.001Z",
		EndedAt:         "1970-01-01T00:00:00.001Z",
		HasFullSnapshot: true,
		EventCount:      1,
		Events:          []json.RawMessage{event},
	}

	signed, canonical, err := SignStoredEnvelope(envelope)
	if err != nil {
		t.Fatalf("sign stored envelope: %v", err)
	}
	if bytes.Contains(canonical, []byte(`\u003c`)) || bytes.Contains(canonical, []byte(`\u003e`)) || bytes.Contains(canonical, []byte(`\u0026`)) {
		t.Fatalf("HTML characters must remain literal: %s", canonical)
	}
	if !bytes.Equal(signed.Events[0], []byte(`{"data":{"cssText":"main > span::before { content: \"<>&\"; }","line":"\u2028\u2029"},"timestamp":1,"type":2}`)) {
		t.Fatalf("signed envelope must expose canonical event bytes: %s", signed.Events[0])
	}
	want := []byte(`{"schema_version":1,"application":"checkout","environment":"production","release":"2026.07.16","session_id":"session-1","page_id":"page-1","recording_id":"recording-1","segment_id":"segment-1","sequence":0,"started_at":"1970-01-01T00:00:00.001Z","ended_at":"1970-01-01T00:00:00.001Z","has_full_snapshot":true,"event_count":1,"checksum_sha256":"84b4da4996582d8ec8150186bd31c7a81ae6b78a3ac480f2361d90720b811973","events":[{"data":{"cssText":"main > span::before { content: \"<>&\"; }","line":"\u2028\u2029"},"timestamp":1,"type":2}]}`)
	if !bytes.Equal(canonical, want) {
		t.Fatalf("canonical bytes drifted\n got: %s\nwant: %s", canonical, want)
	}

	parsed, err := ParseStoredEnvelope(canonical)
	if err != nil {
		t.Fatalf("parse signed canonical envelope: %v", err)
	}
	if parsed.Envelope.ChecksumSHA256 != signed.ChecksumSHA256 || !bytes.Equal(parsed.Canonical, canonical) {
		t.Fatalf("parse/sign contract drift: %#v", parsed)
	}
}

func TestTypeScriptReplayGoldenUsesTheSharedStoredEnvelopeContract(t *testing.T) {
	body, err := os.ReadFile("../rumreplayreceiver/testdata/faro_transport_envelope.golden.json")
	if err != nil {
		t.Fatalf("read TypeScript transport golden: %v", err)
	}
	body = bytes.TrimSpace(body)
	parsed, err := ParseStoredEnvelope(body)
	if err != nil {
		t.Fatalf("parse TypeScript transport golden: %v", err)
	}
	if !bytes.Equal(parsed.Canonical, body) {
		t.Fatalf("TypeScript transport golden is not byte-exact canonical JSON")
	}
}

// Package rumreplayprotocol owns the byte-level Replay carrier contract shared
// by the public receiver and durable exporter. Keep policy validation in those
// components; this package only defines the stored wire model, canonical JSON,
// and checksum parse/verify rules that must never drift between them.
package rumreplayprotocol

import (
	"bytes"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"regexp"
)

var (
	ErrInvalidStoredEnvelope = errors.New("invalid stored Replay envelope")
	checksumPattern          = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

// StoredEnvelope is the only persisted Replay envelope wire model. It
// intentionally has no user_id: raw user identity must be erased at the public
// receiver boundary before a carrier enters the durable queue.
type StoredEnvelope struct {
	SchemaVersion   int               `json:"schema_version"`
	Application     string            `json:"application"`
	Environment     string            `json:"environment"`
	Release         string            `json:"release"`
	SessionID       string            `json:"session_id"`
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

type ParsedStoredEnvelope struct {
	Envelope         StoredEnvelope
	Canonical        []byte
	ChecksumMaterial []byte
}

// CanonicalJSON matches @weops/faro-transport: encoding/json key and number
// ordering, literal HTML characters, deterministic U+2028/U+2029 escapes, and
// no Encoder.Encode trailing newline.
func CanonicalJSON(value any) ([]byte, error) {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(buffer.Bytes(), []byte("\n")), nil
}

// CanonicalizeEvents parses every event with UseNumber before encoding it. This
// prevents float conversion and makes map-key ordering identical on both sides
// of the durable queue boundary.
func CanonicalizeEvents(events []json.RawMessage) ([]json.RawMessage, error) {
	canonicalEvents := make([]json.RawMessage, len(events))
	for index, raw := range events {
		var event any
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.UseNumber()
		if err := decoder.Decode(&event); err != nil {
			return nil, fmt.Errorf("%w: malformed rrweb event", ErrInvalidStoredEnvelope)
		}
		if err := requireEOF(decoder); err != nil {
			return nil, err
		}
		canonical, err := CanonicalJSON(event)
		if err != nil {
			return nil, fmt.Errorf("%w: canonicalize rrweb event", ErrInvalidStoredEnvelope)
		}
		canonicalEvents[index] = canonical
	}
	return canonicalEvents, nil
}

func CanonicalStoredEnvelope(envelope StoredEnvelope, includeChecksum bool) ([]byte, error) {
	canonicalEvents, err := CanonicalizeEvents(envelope.Events)
	if err != nil {
		return nil, err
	}
	envelope.Events = canonicalEvents
	if !includeChecksum {
		envelope.ChecksumSHA256 = ""
	}
	canonical, err := CanonicalJSON(envelope)
	if err != nil {
		return nil, fmt.Errorf("%w: canonicalize envelope", ErrInvalidStoredEnvelope)
	}
	return canonical, nil
}

func SignStoredEnvelope(envelope StoredEnvelope) (StoredEnvelope, []byte, error) {
	canonicalEvents, err := CanonicalizeEvents(envelope.Events)
	if err != nil {
		return StoredEnvelope{}, nil, err
	}
	envelope.Events = canonicalEvents
	envelope.ChecksumSHA256 = ""
	material, err := CanonicalStoredEnvelope(envelope, false)
	if err != nil {
		return StoredEnvelope{}, nil, err
	}
	digest := sha256.Sum256(material)
	envelope.ChecksumSHA256 = hex.EncodeToString(digest[:])
	canonical, err := CanonicalStoredEnvelope(envelope, true)
	if err != nil {
		return StoredEnvelope{}, nil, err
	}
	return envelope, canonical, nil
}

func ParseStoredEnvelope(body []byte) (ParsedStoredEnvelope, error) {
	var envelope StoredEnvelope
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&envelope); err != nil {
		return ParsedStoredEnvelope{}, fmt.Errorf("%w: malformed JSON", ErrInvalidStoredEnvelope)
	}
	if err := requireEOF(decoder); err != nil {
		return ParsedStoredEnvelope{}, err
	}
	if !checksumPattern.MatchString(envelope.ChecksumSHA256) {
		return ParsedStoredEnvelope{}, fmt.Errorf("%w: invalid checksum", ErrInvalidStoredEnvelope)
	}
	canonical, err := CanonicalStoredEnvelope(envelope, true)
	if err != nil {
		return ParsedStoredEnvelope{}, err
	}
	if !bytes.Equal(body, canonical) {
		return ParsedStoredEnvelope{}, fmt.Errorf("%w: non-canonical JSON", ErrInvalidStoredEnvelope)
	}
	material, err := CanonicalStoredEnvelope(envelope, false)
	if err != nil {
		return ParsedStoredEnvelope{}, err
	}
	if !VerifyChecksum(envelope.ChecksumSHA256, material) {
		return ParsedStoredEnvelope{}, fmt.Errorf("%w: checksum mismatch", ErrInvalidStoredEnvelope)
	}
	return ParsedStoredEnvelope{
		Envelope:         envelope,
		Canonical:        canonical,
		ChecksumMaterial: material,
	}, nil
}

func VerifyChecksum(encodedChecksum string, material []byte) bool {
	if !checksumPattern.MatchString(encodedChecksum) {
		return false
	}
	want, err := hex.DecodeString(encodedChecksum)
	if err != nil {
		return false
	}
	digest := sha256.Sum256(material)
	return subtle.ConstantTimeCompare(digest[:], want) == 1
}

func requireEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return fmt.Errorf("%w: trailing JSON", ErrInvalidStoredEnvelope)
	}
	return nil
}

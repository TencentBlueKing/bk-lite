package rumreplayreceiver

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"regexp"
	"strings"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/components/rumreplayprotocol"
)

var (
	ErrReplayTooLarge       = errors.New("Replay payload exceeds receiver limits")
	ErrInvalidReplay        = errors.New("invalid Replay envelope")
	replayIDPattern         = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)
	credentialLookupPattern = regexp.MustCompile(`^[0-9a-f]{16}$`)
	rumApplicationPattern   = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$`)
	checksumPattern         = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

const (
	maxReplayPastAge  = 24 * time.Hour
	maxReplayFuture   = 5 * time.Minute
	maxReplayDuration = 5 * time.Minute
)

type replayEnvelope struct {
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

type decodedReplay struct {
	envelope          rumreplayprotocol.StoredEnvelope
	startedAt         time.Time
	endedAt           time.Time
	compressed        []byte
	uncompressedBytes int
	userID            string
}

func decodeReplay(body io.Reader, cfg *Config, observedAt time.Time) (decodedReplay, error) {
	compressed, err := readBounded(body, cfg.MaxCompressedBytes)
	if err != nil {
		return decodedReplay{}, err
	}
	reader, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		return decodedReplay{}, fmt.Errorf("%w: malformed gzip", ErrInvalidReplay)
	}
	decompressed, err := readBounded(reader, cfg.MaxDecompressedBytes)
	closeErr := reader.Close()
	if err != nil {
		return decodedReplay{}, err
	}
	if closeErr != nil {
		return decodedReplay{}, fmt.Errorf("%w: malformed gzip trailer", ErrInvalidReplay)
	}
	if len(compressed) == 0 || float64(len(decompressed))/float64(len(compressed)) > cfg.MaxCompressionRatio {
		return decodedReplay{}, ErrReplayTooLarge
	}
	if len(decompressed) == 0 || exceedsJSONDepth(decompressed, cfg.MaxJSONDepth) {
		return decodedReplay{}, ErrReplayTooLarge
	}

	var envelope replayEnvelope
	decoder := json.NewDecoder(bytes.NewReader(decompressed))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&envelope); err != nil {
		return decodedReplay{}, fmt.Errorf("%w: malformed JSON", ErrInvalidReplay)
	}
	if err := requireJSONEOF(decoder); err != nil {
		return decodedReplay{}, err
	}
	startedAt, endedAt, err := validateEnvelope(envelope, cfg, observedAt)
	if err != nil {
		return decodedReplay{}, err
	}

	material, err := canonicalEnvelope(envelope, false)
	if err != nil {
		return decodedReplay{}, err
	}
	if !rumreplayprotocol.VerifyChecksum(envelope.ChecksumSHA256, material) {
		return decodedReplay{}, fmt.Errorf("%w: checksum mismatch", ErrInvalidReplay)
	}

	userID := envelope.UserID
	envelope, err = sanitizeReplayEnvelope(envelope, startedAt, endedAt)
	if err != nil {
		return decodedReplay{}, err
	}

	storedEnvelope, canonical, err := rumreplayprotocol.SignStoredEnvelope(toStoredEnvelope(envelope))
	if err != nil {
		return decodedReplay{}, fmt.Errorf("%w: stored envelope canonicalization failed", ErrInvalidReplay)
	}
	stored, err := deterministicGzip(canonical)
	if err != nil {
		return decodedReplay{}, fmt.Errorf("%w: gzip failed", ErrInvalidReplay)
	}
	if int64(len(stored)) > cfg.MaxCompressedBytes {
		return decodedReplay{}, ErrReplayTooLarge
	}
	return decodedReplay{
		envelope:          storedEnvelope,
		startedAt:         startedAt,
		endedAt:           endedAt,
		compressed:        stored,
		uncompressedBytes: len(canonical),
		userID:            userID,
	}, nil
}

func validateEnvelope(envelope replayEnvelope, cfg *Config, observedAt time.Time) (time.Time, time.Time, error) {
	if envelope.SchemaVersion != 1 {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: unsupported schema version", ErrInvalidReplay)
	}
	if !validLabel(envelope.Application, 256) || !validOptionalLabel(envelope.Environment, 128) || !validOptionalLabel(envelope.Release, 256) {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: invalid application metadata", ErrInvalidReplay)
	}
	for _, value := range []string{envelope.SessionID, envelope.PageID, envelope.RecordingID, envelope.SegmentID} {
		if !replayIDPattern.MatchString(value) {
			return time.Time{}, time.Time{}, fmt.Errorf("%w: invalid identity", ErrInvalidReplay)
		}
	}
	if envelope.UserID != "" && !replayIDPattern.MatchString(envelope.UserID) {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: invalid user identity", ErrInvalidReplay)
	}
	if envelope.Sequence < 0 || envelope.Sequence > math.MaxUint32 {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: invalid sequence", ErrInvalidReplay)
	}
	if envelope.EventCount <= 0 || envelope.EventCount != len(envelope.Events) {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: event count mismatch", ErrInvalidReplay)
	}
	if envelope.EventCount > cfg.MaxEvents {
		return time.Time{}, time.Time{}, ErrReplayTooLarge
	}
	for _, event := range envelope.Events {
		if len(event) == 0 || len(event) > cfg.MaxEventBytes {
			return time.Time{}, time.Time{}, ErrReplayTooLarge
		}
	}
	if !checksumPattern.MatchString(envelope.ChecksumSHA256) {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: invalid checksum", ErrInvalidReplay)
	}
	startedAt, err := time.Parse(time.RFC3339Nano, envelope.StartedAt)
	if err != nil || !strings.HasSuffix(envelope.StartedAt, "Z") {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: invalid started_at", ErrInvalidReplay)
	}
	endedAt, err := time.Parse(time.RFC3339Nano, envelope.EndedAt)
	if err != nil || !strings.HasSuffix(envelope.EndedAt, "Z") || endedAt.Before(startedAt) {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: invalid ended_at", ErrInvalidReplay)
	}
	if observedAt.IsZero() {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: invalid observed time", ErrInvalidReplay)
	}
	observedAt = observedAt.UTC()
	earliest := observedAt.Add(-maxReplayPastAge)
	latest := observedAt.Add(maxReplayFuture)
	if startedAt.Before(earliest) || endedAt.Before(earliest) || startedAt.After(latest) || endedAt.After(latest) {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: Replay time outside observed window", ErrInvalidReplay)
	}
	if endedAt.Sub(startedAt) > maxReplayDuration {
		return time.Time{}, time.Time{}, fmt.Errorf("%w: Replay segment duration exceeds limit", ErrInvalidReplay)
	}
	return startedAt, endedAt, nil
}

func canonicalEnvelope(envelope replayEnvelope, includeChecksum bool) ([]byte, error) {
	canonicalEvents, err := rumreplayprotocol.CanonicalizeEvents(envelope.Events)
	if err != nil {
		return nil, fmt.Errorf("%w: malformed rrweb event", ErrInvalidReplay)
	}
	envelope.Events = canonicalEvents
	if !includeChecksum {
		envelope.ChecksumSHA256 = ""
	}
	encoded, err := rumreplayprotocol.CanonicalJSON(envelope)
	if err != nil {
		return nil, fmt.Errorf("%w: canonicalization failed", ErrInvalidReplay)
	}
	return encoded, nil
}

func toStoredEnvelope(envelope replayEnvelope) rumreplayprotocol.StoredEnvelope {
	return rumreplayprotocol.StoredEnvelope{
		SchemaVersion:   envelope.SchemaVersion,
		Application:     envelope.Application,
		Environment:     envelope.Environment,
		Release:         envelope.Release,
		SessionID:       envelope.SessionID,
		PageID:          envelope.PageID,
		RecordingID:     envelope.RecordingID,
		SegmentID:       envelope.SegmentID,
		Sequence:        envelope.Sequence,
		StartedAt:       envelope.StartedAt,
		EndedAt:         envelope.EndedAt,
		HasFullSnapshot: envelope.HasFullSnapshot,
		EventCount:      envelope.EventCount,
		ChecksumSHA256:  envelope.ChecksumSHA256,
		Events:          envelope.Events,
	}
}

func deterministicGzip(body []byte) ([]byte, error) {
	var buffer bytes.Buffer
	writer := gzip.NewWriter(&buffer)
	writer.Header.ModTime = time.Time{}
	writer.Header.OS = 255
	if _, err := writer.Write(body); err != nil {
		return nil, err
	}
	if err := writer.Close(); err != nil {
		return nil, err
	}
	return buffer.Bytes(), nil
}

func readBounded(reader io.Reader, limit int64) ([]byte, error) {
	data, err := io.ReadAll(io.LimitReader(reader, limit+1))
	if err != nil {
		return nil, fmt.Errorf("%w: body read failed", ErrInvalidReplay)
	}
	if int64(len(data)) > limit {
		return nil, ErrReplayTooLarge
	}
	return data, nil
}

func requireJSONEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return fmt.Errorf("%w: trailing JSON", ErrInvalidReplay)
	}
	return nil
}

func exceedsJSONDepth(data []byte, maxDepth int) bool {
	depth := 0
	inString := false
	escaped := false
	for _, char := range data {
		if inString {
			if escaped {
				escaped = false
				continue
			}
			if char == '\\' {
				escaped = true
			} else if char == '"' {
				inString = false
			}
			continue
		}
		switch char {
		case '"':
			inString = true
		case '{', '[':
			depth++
			if depth > maxDepth {
				return true
			}
		case '}', ']':
			depth--
			if depth < 0 {
				return false
			}
		}
	}
	return false
}

func validLabel(value string, max int) bool {
	return value != "" && value == strings.TrimSpace(value) && len(value) <= max && !strings.ContainsAny(value, "\r\n\x00")
}

func validOptionalLabel(value string, max int) bool {
	return value == "" || validLabel(value, max)
}

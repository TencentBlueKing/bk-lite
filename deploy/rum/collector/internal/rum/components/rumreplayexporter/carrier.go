package rumreplayexporter

import (
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"math"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/components/rumreplayprotocol"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
)

const (
	replayScopeName             = "weops.rum.replay.segment"
	maxCarrierCompressedBytes   = int64(1 << 20)
	maxCarrierUncompressedBytes = int64(4 << 20)
)

var (
	carrierIDPattern      = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)
	carrierHashPattern    = regexp.MustCompile(`^[0-9a-f]{64}$`)
	carrierLookupPattern  = regexp.MustCompile(`^[0-9a-f]{16}$`)
	carrierVersionPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$`)
	productSessionPattern = regexp.MustCompile(`^[0-9a-f]{32}$`)
)

type replaySegment struct {
	Object ObjectWrite
	Index  ReplayIndex
}

func extractReplaySegments(logs plog.Logs) ([]replaySegment, error) {
	segments := make([]replaySegment, 0, logs.LogRecordCount())
	logicalChecksums := make(map[string]string)
	resourceLogs := logs.ResourceLogs()
	for resourceIndex := 0; resourceIndex < resourceLogs.Len(); resourceIndex++ {
		resource := resourceLogs.At(resourceIndex)
		tenantID, err := requiredString(resource.Resource().Attributes(), "tenant.id")
		if err != nil || !carrierIDPattern.MatchString(tenantID) {
			return nil, fmt.Errorf("%w: invalid authoritative tenant", ErrInvalidCarrier)
		}
		credentialLookup, err := requiredString(resource.Resource().Attributes(), "rum.credential.lookup_id")
		if err != nil || !carrierLookupPattern.MatchString(credentialLookup) {
			return nil, fmt.Errorf("%w: invalid authoritative credential lookup", ErrInvalidCarrier)
		}
		scopeLogs := resource.ScopeLogs()
		for scopeIndex := 0; scopeIndex < scopeLogs.Len(); scopeIndex++ {
			scope := scopeLogs.At(scopeIndex)
			if scope.Scope().Name() != replayScopeName {
				return nil, fmt.Errorf("%w: unexpected scope", ErrInvalidCarrier)
			}
			records := scope.LogRecords()
			for recordIndex := 0; recordIndex < records.Len(); recordIndex++ {
				segment, err := extractReplaySegment(tenantID, credentialLookup, records.At(recordIndex))
				if err != nil {
					return nil, err
				}
				logicalKey := segment.Index.LogicalKey()
				if checksum, ok := logicalChecksums[logicalKey]; ok {
					if checksum != segment.Index.ChecksumSHA256 {
						return nil, ErrChecksumConflict
					}
					continue
				}
				logicalChecksums[logicalKey] = segment.Index.ChecksumSHA256
				segments = append(segments, segment)
			}
		}
	}
	if len(segments) == 0 {
		return nil, fmt.Errorf("%w: empty batch", ErrInvalidCarrier)
	}
	return segments, nil
}

func extractReplaySegment(tenantID, credentialLookup string, record plog.LogRecord) (replaySegment, error) {
	if record.Body().Type() != pcommon.ValueTypeBytes {
		return replaySegment{}, fmt.Errorf("%w: body must be bytes", ErrInvalidCarrier)
	}
	compressed := append([]byte(nil), record.Body().Bytes().AsRaw()...)
	if len(compressed) < 2 || compressed[0] != 0x1f || compressed[1] != 0x8b || int64(len(compressed)) > maxCarrierCompressedBytes {
		return replaySegment{}, fmt.Errorf("%w: body must be bounded gzip", ErrInvalidCarrier)
	}
	uncompressed, err := gunzipBounded(compressed, maxCarrierUncompressedBytes)
	if err != nil {
		return replaySegment{}, err
	}
	parsed, err := rumreplayprotocol.ParseStoredEnvelope(uncompressed)
	if err != nil {
		return replaySegment{}, fmt.Errorf("%w: %v", ErrInvalidCarrier, err)
	}
	envelope := parsed.Envelope

	attrs := record.Attributes()
	schemaVersion, err := requiredInt(attrs, "rum.replay.schema.version")
	if err != nil || schemaVersion != 1 || envelope.SchemaVersion != 1 {
		return replaySegment{}, fmt.Errorf("%w: schema version mismatch", ErrInvalidCarrier)
	}
	application, err := requiredString(attrs, "rum.replay.application")
	if err != nil || application != envelope.Application || !validCarrierLabel(application, 256) {
		return replaySegment{}, fmt.Errorf("%w: application mismatch", ErrInvalidCarrier)
	}
	environment, err := optionalString(attrs, "rum.replay.environment")
	if err != nil || environment != envelope.Environment {
		return replaySegment{}, fmt.Errorf("%w: environment mismatch", ErrInvalidCarrier)
	}
	release, err := optionalString(attrs, "rum.replay.release")
	if err != nil || release != envelope.Release {
		return replaySegment{}, fmt.Errorf("%w: release mismatch", ErrInvalidCarrier)
	}
	sessionID, err := matchingID(attrs, "rum.replay.session.id", envelope.SessionID)
	if err != nil {
		return replaySegment{}, err
	}
	productSessionKey, err := requiredString(attrs, "rum.replay.session_key")
	if err != nil || !productSessionPattern.MatchString(productSessionKey) {
		return replaySegment{}, fmt.Errorf("%w: invalid authoritative session key", ErrInvalidCarrier)
	}
	pageID, err := matchingID(attrs, "rum.replay.page.id", envelope.PageID)
	if err != nil {
		return replaySegment{}, err
	}
	recordingID, err := matchingID(attrs, "rum.replay.recording.id", envelope.RecordingID)
	if err != nil {
		return replaySegment{}, err
	}
	segmentID, err := matchingID(attrs, "rum.replay.segment.id", envelope.SegmentID)
	if err != nil {
		return replaySegment{}, err
	}
	sequence, err := requiredInt(attrs, "rum.replay.sequence")
	if err != nil || sequence < 0 || sequence > math.MaxUint32 || sequence != envelope.Sequence {
		return replaySegment{}, fmt.Errorf("%w: sequence mismatch", ErrInvalidCarrier)
	}
	startedAtRaw, err := requiredString(attrs, "rum.replay.started_at")
	if err != nil || startedAtRaw != envelope.StartedAt {
		return replaySegment{}, fmt.Errorf("%w: started_at mismatch", ErrInvalidCarrier)
	}
	endedAtRaw, err := requiredString(attrs, "rum.replay.ended_at")
	if err != nil || endedAtRaw != envelope.EndedAt {
		return replaySegment{}, fmt.Errorf("%w: ended_at mismatch", ErrInvalidCarrier)
	}
	startedAt, err := time.Parse(time.RFC3339Nano, startedAtRaw)
	if err != nil || !strings.HasSuffix(startedAtRaw, "Z") {
		return replaySegment{}, fmt.Errorf("%w: invalid started_at", ErrInvalidCarrier)
	}
	endedAt, err := time.Parse(time.RFC3339Nano, endedAtRaw)
	if err != nil || !strings.HasSuffix(endedAtRaw, "Z") || endedAt.Before(startedAt) {
		return replaySegment{}, fmt.Errorf("%w: invalid ended_at", ErrInvalidCarrier)
	}
	if record.Timestamp() == 0 || !record.Timestamp().AsTime().Equal(startedAt) {
		return replaySegment{}, fmt.Errorf("%w: record timestamp mismatch", ErrInvalidCarrier)
	}
	eventCount, err := requiredInt(attrs, "rum.replay.event_count")
	if err != nil || eventCount <= 0 || eventCount > math.MaxUint32 || eventCount != int64(envelope.EventCount) || envelope.EventCount != len(envelope.Events) {
		return replaySegment{}, fmt.Errorf("%w: event count mismatch", ErrInvalidCarrier)
	}
	hasFullSnapshot, err := requiredBool(attrs, "rum.replay.has_full_snapshot")
	if err != nil || hasFullSnapshot != envelope.HasFullSnapshot {
		return replaySegment{}, fmt.Errorf("%w: snapshot flag mismatch", ErrInvalidCarrier)
	}
	checksum, err := requiredString(attrs, "rum.replay.checksum_sha256")
	if err != nil || !carrierHashPattern.MatchString(checksum) || checksum != envelope.ChecksumSHA256 {
		return replaySegment{}, fmt.Errorf("%w: checksum attribute mismatch", ErrInvalidCarrier)
	}
	compressedBytes, err := requiredInt(attrs, "rum.replay.compressed_bytes")
	if err != nil || compressedBytes != int64(len(compressed)) {
		return replaySegment{}, fmt.Errorf("%w: compressed size mismatch", ErrInvalidCarrier)
	}
	uncompressedBytes, err := requiredInt(attrs, "rum.replay.uncompressed_bytes")
	if err != nil || uncompressedBytes != int64(len(uncompressed)) {
		return replaySegment{}, fmt.Errorf("%w: uncompressed size mismatch", ErrInvalidCarrier)
	}
	if record.ObservedTimestamp() == 0 {
		return replaySegment{}, fmt.Errorf("%w: missing observed timestamp", ErrInvalidCarrier)
	}
	acceptedAtRaw, err := requiredInt(attrs, "rum.accepted_at_unix_nano")
	if err != nil || acceptedAtRaw <= 0 || uint64(acceptedAtRaw) != uint64(record.ObservedTimestamp()) {
		return replaySegment{}, fmt.Errorf("%w: invalid accepted-at fence timestamp", ErrInvalidCarrier)
	}
	userKey, err := requiredString(attrs, "rum.erasure.user_key")
	if err != nil || !carrierHashPattern.MatchString(userKey) {
		return replaySegment{}, fmt.Errorf("%w: invalid erasure user key", ErrInvalidCarrier)
	}
	sessionKey, err := requiredString(attrs, "rum.erasure.session_key")
	if err != nil || !carrierHashPattern.MatchString(sessionKey) {
		return replaySegment{}, fmt.Errorf("%w: invalid erasure session key", ErrInvalidCarrier)
	}

	keyVersion, err := requiredString(attrs, "rum.erasure.key_version")
	if err != nil || !carrierVersionPattern.MatchString(keyVersion) {
		return replaySegment{}, fmt.Errorf("%w: invalid erasure key version", ErrInvalidCarrier)
	}

	tenantHash := sha256.Sum256([]byte(tenantID))
	applicationHash := sha256.Sum256([]byte(application))
	recordingHash := sha256.Sum256([]byte(recordingID))
	sequenceHash := sha256.Sum256([]byte(strings.Join([]string{
		"weops.rum.replay.sequence.v1",
		tenantID,
		application,
		sessionID,
		recordingID,
		strconv.FormatInt(sequence, 10),
	}, "\x00")))
	base := strings.Join([]string{
		"v1",
		hex.EncodeToString(tenantHash[:]),
		userKey,
		sessionKey,
		hex.EncodeToString(applicationHash[:]),
		hex.EncodeToString(recordingHash[:]),
	}, "/")
	logicalPrefix := base + "/" + hex.EncodeToString(sequenceHash[:]) + "-"
	objectKey := logicalPrefix + checksum + ".json.gz"
	index := ReplayIndex{
		TenantID:           tenantID,
		CredentialLookupID: credentialLookup,
		Application:        application,
		Environment:        environment,
		Release:            release,
		SessionID:          sessionID,
		SessionKey:         productSessionKey,
		PageID:             pageID,
		RecordingID:        recordingID,
		SegmentID:          segmentID,
		Sequence:           uint32(sequence),
		StartTime:          clickHouseTime(startedAt),
		EndTime:            clickHouseTime(endedAt),
		EventCount:         uint32(eventCount),
		CompressedBytes:    uint64(compressedBytes),
		UncompressedBytes:  uint64(uncompressedBytes),
		HasFullSnapshot:    boolByte(hasFullSnapshot),
		ChecksumSHA256:     checksum,
		ObjectKey:          objectKey,
		Status:             "pending",
		ErasureKeyVersion:  keyVersion,
		ErasureUserKey:     userKey,
		ErasureSessionKey:  sessionKey,
		AcceptedAtUnixNano: uint64(acceptedAtRaw),
		Version:            uint64(record.ObservedTimestamp()),
	}
	return replaySegment{
		Object: ObjectWrite{
			Bucket:          defaultReplayBucket,
			LogicalPrefix:   logicalPrefix,
			Key:             objectKey,
			ChecksumSHA256:  checksum,
			Body:            compressed,
			ContentType:     "application/octet-stream",
			ContentEncoding: "",
			Metadata: map[string]string{
				"sha256":                checksum,
				"accepted-at-unix-nano": fmt.Sprintf("%d", acceptedAtRaw),
				"erasure-key-version":   keyVersion,
			},
		},
		Index: index,
	}, nil
}

func gunzipBounded(compressed []byte, limit int64) ([]byte, error) {
	reader, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		return nil, fmt.Errorf("%w: malformed gzip", ErrInvalidCarrier)
	}
	body, err := io.ReadAll(io.LimitReader(reader, limit+1))
	closeErr := reader.Close()
	if err != nil || closeErr != nil || int64(len(body)) > limit {
		return nil, fmt.Errorf("%w: invalid or oversized gzip", ErrInvalidCarrier)
	}
	return body, nil
}

func requiredString(attrs pcommon.Map, key string) (string, error) {
	value, ok := attrs.Get(key)
	if !ok || value.Type() != pcommon.ValueTypeStr || value.Str() == "" {
		return "", fmt.Errorf("%w: missing string attribute", ErrInvalidCarrier)
	}
	return value.Str(), nil
}

func optionalString(attrs pcommon.Map, key string) (string, error) {
	value, ok := attrs.Get(key)
	if !ok {
		return "", nil
	}
	if value.Type() != pcommon.ValueTypeStr {
		return "", fmt.Errorf("%w: invalid optional string attribute", ErrInvalidCarrier)
	}
	return value.Str(), nil
}

func requiredInt(attrs pcommon.Map, key string) (int64, error) {
	value, ok := attrs.Get(key)
	if !ok || value.Type() != pcommon.ValueTypeInt {
		return 0, fmt.Errorf("%w: missing integer attribute", ErrInvalidCarrier)
	}
	return value.Int(), nil
}

func requiredBool(attrs pcommon.Map, key string) (bool, error) {
	value, ok := attrs.Get(key)
	if !ok || value.Type() != pcommon.ValueTypeBool {
		return false, fmt.Errorf("%w: missing boolean attribute", ErrInvalidCarrier)
	}
	return value.Bool(), nil
}

func matchingID(attrs pcommon.Map, key, envelopeValue string) (string, error) {
	value, err := requiredString(attrs, key)
	if err != nil || value != envelopeValue || !carrierIDPattern.MatchString(value) {
		return "", fmt.Errorf("%w: identity mismatch", ErrInvalidCarrier)
	}
	return value, nil
}

func validCarrierLabel(value string, max int) bool {
	return value != "" && value == strings.TrimSpace(value) && len(value) <= max && !strings.ContainsAny(value, "\r\n\x00")
}

func clickHouseTime(value time.Time) string {
	return value.UTC().Format("2006-01-02 15:04:05.000")
}

func boolByte(value bool) uint8 {
	if value {
		return 1
	}
	return 0
}

// Package replayindex is the Redis-backed Replay segment index shared by
// the collector exporter, maintainer, and the RUM product read path.
package replayindex

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	indexTTL           = 14 * 24 * time.Hour
	sessionKeyTTL      = 14 * 24 * time.Hour
	reconAuditTTL      = 30 * 24 * time.Hour
	reconAuditKey      = "ops:rum:v2:replay:recon:runs"
	pendingStatus      = "pending"
	readyStatus        = "ready"
	tombstoneStatus    = "tombstone"
	inconsistentStatus = "inconsistent"
)

// Index is one Replay segment slot.
type Index struct {
	TenantID           string `json:"tenant_id"`
	CredentialLookupID string `json:"CredentialLookupId"`
	Application        string `json:"Application"`
	Environment        string `json:"Environment"`
	Release            string `json:"Release"`
	SessionID          string `json:"SessionId"`
	SessionKey         string `json:"SessionKey"`
	PageID             string `json:"PageId"`
	RecordingID        string `json:"RecordingId"`
	SegmentID          string `json:"SegmentId"`
	Sequence           uint32 `json:"Sequence"`
	StartTime          string `json:"StartTime"`
	EndTime            string `json:"EndTime"`
	EventCount         uint32 `json:"EventCount"`
	CompressedBytes    uint64 `json:"CompressedBytes"`
	UncompressedBytes  uint64 `json:"UncompressedBytes"`
	HasFullSnapshot    uint8  `json:"HasFullSnapshot"`
	ChecksumSHA256     string `json:"ChecksumSHA256"`
	ObjectKey          string `json:"ObjectKey"`
	Status             string `json:"Status"`
	ErasureKeyVersion  string `json:"ErasureKeyVersion"`
	ErasureUserKey     string `json:"ErasureUserKey"`
	ErasureSessionKey  string `json:"ErasureSessionKey"`
	AcceptedAtUnixNano uint64 `json:"AcceptedAtUnixNano"`
	Version            uint64 `json:"Version"`
}

// ProductSessionID prefers the product session key when present.
func (row Index) ProductSessionID() string {
	if strings.TrimSpace(row.SessionKey) != "" {
		return row.SessionKey
	}
	return row.SessionID
}

func slotKey(application, session, recording string, sequence uint32) string {
	return fmt.Sprintf("ops:rum:v2:replay:idx:%s:%s:%s:%d", application, session, recording, sequence)
}

func sessionSetKey(application, session string) string {
	return fmt.Sprintf("ops:rum:v2:replay:sess:%s:%s", application, session)
}

func objectKey(object string) string {
	return "ops:rum:v2:replay:obj:" + object
}

func appZSetKey(application string) string {
	return "ops:rum:v2:replay:app:" + application
}

func erasureSetKey(version, digest string) string {
	return fmt.Sprintf("ops:rum:v2:replay:erasure:%s:%s", version, digest)
}

// Store is a Redis index implementation.
type Store struct {
	client redis.UniversalClient
	now    func() time.Time
}

// NewStore wraps an existing Redis client.
func NewStore(client redis.UniversalClient) *Store {
	return &Store{client: client, now: time.Now}
}

// Ping checks connectivity.
func (store *Store) Ping(ctx context.Context) error {
	return store.client.Ping(ctx).Err()
}

// Close releases the client.
func (store *Store) Close() error {
	if store == nil || store.client == nil {
		return nil
	}
	return store.client.Close()
}

// EnsureOutcome matches the exporter index contract.
type EnsureOutcome uint8

const (
	EnsureUnknown EnsureOutcome = iota
	EnsureCreated
	EnsureReused
	EnsureAlreadyReady
)

// BeginPending records a pending slot.
func (store *Store) BeginPending(ctx context.Context, row Index) (EnsureOutcome, error) {
	row.Status = pendingStatus
	return store.write(ctx, row, false)
}

// PublishReady marks the slot ready.
func (store *Store) PublishReady(ctx context.Context, row Index) (EnsureOutcome, error) {
	row.Status = readyStatus
	return store.write(ctx, row, true)
}

// Tombstone marks the slot deleted.
func (store *Store) Tombstone(ctx context.Context, row Index) error {
	row.Status = tombstoneStatus
	_, err := store.write(ctx, row, true)
	return err
}

func (store *Store) write(ctx context.Context, row Index, overwrite bool) (EnsureOutcome, error) {
	session := row.ProductSessionID()
	if row.Application == "" || session == "" || row.RecordingID == "" || row.ObjectKey == "" {
		return EnsureUnknown, errors.New("replay index row is incomplete")
	}
	if row.Version == 0 {
		row.Version = row.AcceptedAtUnixNano
	}
	key := slotKey(row.Application, session, row.RecordingID, row.Sequence)
	existing, err := store.client.Get(ctx, key).Bytes()
	if err != nil && !errors.Is(err, redis.Nil) {
		return EnsureUnknown, err
	}
	if err == nil {
		var current Index
		if unmarshalErr := json.Unmarshal(existing, &current); unmarshalErr == nil {
			if current.Status == readyStatus && row.Status == pendingStatus {
				return EnsureAlreadyReady, nil
			}
			if current.Status == row.Status && !overwrite {
				return EnsureReused, nil
			}
		}
	}
	payload, err := json.Marshal(row)
	if err != nil {
		return EnsureUnknown, err
	}
	pipe := store.client.TxPipeline()
	pipe.Set(ctx, key, payload, indexTTL)
	if row.Status != tombstoneStatus {
		pipe.SAdd(ctx, sessionSetKey(row.Application, session), key)
		pipe.Expire(ctx, sessionSetKey(row.Application, session), sessionKeyTTL)
		pipe.Set(ctx, objectKey(row.ObjectKey), key, indexTTL)
		pipe.ZAdd(ctx, appZSetKey(row.Application), redis.Z{Score: float64(row.AcceptedAtUnixNano), Member: key})
		pipe.Expire(ctx, appZSetKey(row.Application), sessionKeyTTL)
		if row.ErasureKeyVersion != "" && row.ErasureUserKey != "" {
			pipe.SAdd(ctx, erasureSetKey(row.ErasureKeyVersion, row.ErasureUserKey), row.ObjectKey)
			pipe.Expire(ctx, erasureSetKey(row.ErasureKeyVersion, row.ErasureUserKey), indexTTL)
		}
		if row.ErasureKeyVersion != "" && row.ErasureSessionKey != "" {
			pipe.SAdd(ctx, erasureSetKey(row.ErasureKeyVersion, row.ErasureSessionKey), row.ObjectKey)
			pipe.Expire(ctx, erasureSetKey(row.ErasureKeyVersion, row.ErasureSessionKey), indexTTL)
		}
	} else {
		pipe.SRem(ctx, sessionSetKey(row.Application, session), key)
		pipe.Del(ctx, objectKey(row.ObjectKey))
		pipe.ZRem(ctx, appZSetKey(row.Application), key)
	}
	if _, err := pipe.Exec(ctx); err != nil {
		return EnsureUnknown, err
	}
	if errors.Is(err, redis.Nil) || existing == nil {
		return EnsureCreated, nil
	}
	return EnsureReused, nil
}

// Manifest returns ready segments for a session.
func (store *Store) Manifest(ctx context.Context, application, sessionID string) ([]Index, error) {
	keys, err := store.client.SMembers(ctx, sessionSetKey(application, sessionID)).Result()
	if err != nil {
		return nil, err
	}
	if len(keys) == 0 {
		return []Index{}, nil
	}
	values, err := store.client.MGet(ctx, keys...).Result()
	if err != nil {
		return nil, err
	}
	out := make([]Index, 0, len(values))
	for _, value := range values {
		raw, ok := value.(string)
		if !ok || raw == "" {
			continue
		}
		var row Index
		if err := json.Unmarshal([]byte(raw), &row); err != nil {
			continue
		}
		out = append(out, row)
	}
	return out, nil
}

// HasReady reports whether the session has any ready segment.
func (store *Store) HasReady(ctx context.Context, application, sessionID string) (bool, error) {
	rows, err := store.Manifest(ctx, application, sessionID)
	if err != nil {
		return false, err
	}
	for _, row := range rows {
		if row.Status == readyStatus {
			return true, nil
		}
	}
	return false, nil
}

// HasObject reports a non-tombstone index for the object key.
func (store *Store) HasObject(ctx context.Context, object string) (bool, error) {
	key, err := store.client.Get(ctx, objectKey(object)).Result()
	if errors.Is(err, redis.Nil) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	raw, err := store.client.Get(ctx, key).Bytes()
	if errors.Is(err, redis.Nil) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	var row Index
	if err := json.Unmarshal(raw, &row); err != nil {
		return false, err
	}
	return row.Status != tombstoneStatus, nil
}

// ObjectsForErasure lists object keys for the given identity digests.
func (store *Store) ObjectsForErasure(ctx context.Context, version string, digests []string) ([]string, error) {
	seen := map[string]struct{}{}
	var out []string
	for _, digest := range digests {
		members, err := store.client.SMembers(ctx, erasureSetKey(version, digest)).Result()
		if err != nil {
			return nil, err
		}
		for _, member := range members {
			if _, ok := seen[member]; ok {
				continue
			}
			seen[member] = struct{}{}
			out = append(out, member)
		}
	}
	return out, nil
}

// ScanCursor pages application index slots by accepted-at.
type ScanCursor struct {
	AcceptedAtUnixNano uint64
	SegmentID          string
}

// ListCandidates returns pending/ready rows before the cutoff, after cursor.
func (store *Store) ListCandidates(ctx context.Context, application string, before time.Time, cursor ScanCursor, limit uint64) ([]Index, error) {
	if limit == 0 {
		limit = 100
	}
	max := strconv.FormatUint(uint64(before.UnixNano()), 10)
	keys, err := store.client.ZRangeByScore(ctx, appZSetKey(application), &redis.ZRangeBy{
		Min: "-inf", Max: max, Offset: 0, Count: int64(limit * 8),
	}).Result()
	if err != nil {
		return nil, err
	}
	out := make([]Index, 0, limit)
	for _, key := range keys {
		raw, err := store.client.Get(ctx, key).Bytes()
		if errors.Is(err, redis.Nil) {
			continue
		}
		if err != nil {
			return nil, err
		}
		var row Index
		if err := json.Unmarshal(raw, &row); err != nil {
			continue
		}
		if row.Status != pendingStatus && row.Status != readyStatus {
			continue
		}
		if row.AcceptedAtUnixNano < cursor.AcceptedAtUnixNano ||
			(row.AcceptedAtUnixNano == cursor.AcceptedAtUnixNano && row.SegmentID <= cursor.SegmentID) {
			continue
		}
		out = append(out, row)
		if uint64(len(out)) == limit {
			break
		}
	}
	return out, nil
}

// SetStatus updates a row's status in place.
func (store *Store) SetStatus(ctx context.Context, row Index, status string) error {
	row.Status = status
	row.Version = uint64(store.now().UTC().UnixNano())
	_, err := store.write(ctx, row, true)
	return err
}

// CountPending returns pending rows older than cutoff.
func (store *Store) CountPending(ctx context.Context, before time.Time) (int64, error) {
	// Dev/lab cardinality is small; SCAN is acceptable for the health gauge.
	var cursor uint64
	var count int64
	cutoff := uint64(before.UnixNano())
	for {
		var keys []string
		var err error
		keys, cursor, err = store.client.Scan(ctx, cursor, "ops:rum:v2:replay:idx:*", 200).Result()
		if err != nil {
			return 0, err
		}
		for _, key := range keys {
			raw, err := store.client.Get(ctx, key).Bytes()
			if err != nil {
				continue
			}
			var row Index
			if json.Unmarshal(raw, &row) != nil {
				continue
			}
			if row.Status == pendingStatus && row.AcceptedAtUnixNano < cutoff {
				count++
			}
		}
		if cursor == 0 {
			return count, nil
		}
	}
}

// AuditReconciliation persists a short-lived health sample in Redis.
func (store *Store) AuditReconciliation(ctx context.Context, runID, application, status string, checked, repaired, conflicts, orphans uint64) error {
	payload, err := json.Marshal(map[string]any{
		"run_id": runID, "application": application, "status": status,
		"checked": checked, "repaired": repaired, "conflicts": conflicts, "orphans": orphans,
		"finished_at": store.now().UTC().Unix(),
	})
	if err != nil {
		return err
	}
	pipe := store.client.TxPipeline()
	pipe.LPush(ctx, reconAuditKey, payload)
	pipe.LTrim(ctx, reconAuditKey, 0, 99)
	pipe.Expire(ctx, reconAuditKey, reconAuditTTL)
	_, err = pipe.Exec(ctx)
	return err
}

// ReconciliationHealth returns last run time and recent conflicts.
func (store *Store) ReconciliationHealth(ctx context.Context, since time.Time) (time.Time, uint64, error) {
	items, err := store.client.LRange(ctx, reconAuditKey, 0, 99).Result()
	if err != nil {
		return time.Time{}, 0, err
	}
	var last int64
	var conflicts uint64
	sinceUnix := since.UTC().Unix()
	for _, item := range items {
		var row struct {
			Conflicts  uint64 `json:"conflicts"`
			FinishedAt int64  `json:"finished_at"`
		}
		if json.Unmarshal([]byte(item), &row) != nil {
			continue
		}
		if row.FinishedAt > last {
			last = row.FinishedAt
		}
		if row.FinishedAt >= sinceUnix {
			conflicts += row.Conflicts
		}
	}
	if last <= 0 {
		return time.Time{}, conflicts, nil
	}
	return time.Unix(last, 0).UTC(), conflicts, nil
}

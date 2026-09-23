package maintainer

import (
	"context"
	"fmt"
	"net/url"
	"strings"
	"time"

	"github.com/bk-lite/rum-collector/pkg/rum/replayindex"
	"github.com/redis/go-redis/v9"
)

// RedisIndexConfig opens the maintainer Replay index identity.
type RedisIndexConfig struct {
	URL          string
	PasswordFile string
}

// RedisIndexStore is the maintainer view of replayindex.Store.
type RedisIndexStore struct {
	inner *replayindex.Store
}

// NewRedisIndexStore opens Redis with the rum-replay-index-maintainer identity.
func NewRedisIndexStore(cfg RedisIndexConfig) (*RedisIndexStore, error) {
	parsed, err := url.Parse(strings.TrimSpace(cfg.URL))
	if err != nil || parsed.Host == "" || (parsed.Scheme != "redis" && parsed.Scheme != "rediss") {
		return nil, fmt.Errorf("replay index redis-url must be redis:// or rediss://")
	}
	if parsed.User == nil || parsed.User.Username() != "rum-replay-index-maintainer" {
		return nil, fmt.Errorf("replay index redis-url must use rum-replay-index-maintainer")
	}
	options, err := redis.ParseURL(cfg.URL)
	if err != nil {
		return nil, err
	}
	if file := strings.TrimSpace(cfg.PasswordFile); file != "" {
		password, err := readCredentialFile(file)
		if err != nil {
			return nil, err
		}
		options.Password = password
	}
	return &RedisIndexStore{inner: replayindex.NewStore(redis.NewClient(options))}, nil
}

func (store *RedisIndexStore) Start(ctx context.Context) error {
	return store.inner.Ping(ctx)
}

func (store *RedisIndexStore) Close() error { return store.inner.Close() }

func (store *RedisIndexStore) ReplayObjectsForErasure(ctx context.Context, task ErasureTask) ([]string, error) {
	var keys []string
	byVersion := map[string][]string{}
	for _, identity := range task.Identities {
		byVersion[identity.Version] = append(byVersion[identity.Version], identity.Digest)
	}
	for version, digests := range byVersion {
		found, err := store.inner.ObjectsForErasure(ctx, version, digests)
		if err != nil {
			return nil, err
		}
		keys = append(keys, found...)
	}
	return keys, nil
}

func (store *RedisIndexStore) ListReplayCandidates(ctx context.Context, application string, before time.Time, cursor ReplayScanCursor, limit uint64) ([]ReplayIndex, error) {
	rows, err := store.inner.ListCandidates(ctx, application, before, replayindex.ScanCursor{
		AcceptedAtUnixNano: cursor.AcceptedAtUnixNano, SegmentID: cursor.SegmentID,
	}, limit)
	if err != nil {
		return nil, err
	}
	out := make([]ReplayIndex, 0, len(rows))
	for _, row := range rows {
		out = append(out, ReplayIndex(row))
	}
	return out, nil
}

func (store *RedisIndexStore) SetReplayStatus(ctx context.Context, index ReplayIndex, status string) error {
	return store.inner.SetStatus(ctx, replayindex.Index(index), status)
}

func (store *RedisIndexStore) HasReplayIndex(ctx context.Context, objectKey string) (bool, error) {
	return store.inner.HasObject(ctx, objectKey)
}

func (store *RedisIndexStore) AuditReconciliation(ctx context.Context, runID, application, status string, checked, repaired, conflicts, orphans uint64) error {
	return store.inner.AuditReconciliation(ctx, runID, application, status, checked, repaired, conflicts, orphans)
}

func (store *RedisIndexStore) CountReplayPending(ctx context.Context, before time.Time) (int64, error) {
	return store.inner.CountPending(ctx, before)
}

func (store *RedisIndexStore) ReconciliationHealth(ctx context.Context, since time.Time) (time.Time, uint64, error) {
	return store.inner.ReconciliationHealth(ctx, since)
}

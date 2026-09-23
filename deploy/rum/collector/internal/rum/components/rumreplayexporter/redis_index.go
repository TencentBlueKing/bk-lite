package rumreplayexporter

import (
	"context"
	"fmt"

	"github.com/bk-lite/rum-collector/pkg/rum/replayindex"
	"github.com/redis/go-redis/v9"
)

type redisIndexStore struct {
	inner *replayindex.Store
}

func newRedisIndexStore(cfg *Config) (*redisIndexStore, error) {
	options, err := redisClientOptions(cfg)
	if err != nil {
		return nil, err
	}
	return &redisIndexStore{inner: replayindex.NewStore(redis.NewClient(options))}, nil
}

func (store *redisIndexStore) Start(ctx context.Context) error {
	if err := store.inner.Ping(ctx); err != nil {
		return fmt.Errorf("ping Replay index Redis: %w", err)
	}
	return nil
}

func (store *redisIndexStore) Shutdown(context.Context) error {
	return store.inner.Close()
}

func toIndex(row ReplayIndex) replayindex.Index {
	return replayindex.Index{
		TenantID:           row.TenantID,
		CredentialLookupID: row.CredentialLookupID,
		Application:        row.Application,
		Environment:        row.Environment,
		Release:            row.Release,
		SessionID:          row.SessionID,
		SessionKey:         row.SessionKey,
		PageID:             row.PageID,
		RecordingID:        row.RecordingID,
		SegmentID:          row.SegmentID,
		Sequence:           row.Sequence,
		StartTime:          row.StartTime,
		EndTime:            row.EndTime,
		EventCount:         row.EventCount,
		CompressedBytes:    row.CompressedBytes,
		UncompressedBytes:  row.UncompressedBytes,
		HasFullSnapshot:    row.HasFullSnapshot,
		ChecksumSHA256:     row.ChecksumSHA256,
		ObjectKey:          row.ObjectKey,
		Status:             row.Status,
		ErasureKeyVersion:  row.ErasureKeyVersion,
		ErasureUserKey:     row.ErasureUserKey,
		ErasureSessionKey:  row.ErasureSessionKey,
		AcceptedAtUnixNano: row.AcceptedAtUnixNano,
		Version:            row.Version,
	}
}

func mapOutcome(outcome replayindex.EnsureOutcome) EnsureOutcome {
	switch outcome {
	case replayindex.EnsureCreated:
		return EnsureCreated
	case replayindex.EnsureReused:
		return EnsureReused
	case replayindex.EnsureAlreadyReady:
		return EnsureAlreadyReady
	default:
		return EnsureUnknown
	}
}

func (store *redisIndexStore) BeginPending(ctx context.Context, row ReplayIndex) (EnsureOutcome, error) {
	if err := validateReplayIndex(row); err != nil {
		return EnsureUnknown, err
	}
	outcome, err := store.inner.BeginPending(ctx, toIndex(row))
	return mapOutcome(outcome), err
}

func (store *redisIndexStore) PublishReady(ctx context.Context, row ReplayIndex) (EnsureOutcome, error) {
	if err := validateReplayIndex(row); err != nil {
		return EnsureUnknown, err
	}
	outcome, err := store.inner.PublishReady(ctx, toIndex(row))
	return mapOutcome(outcome), err
}

func (store *redisIndexStore) Tombstone(ctx context.Context, row ReplayIndex) error {
	if err := validateReplayIndex(row); err != nil {
		return err
	}
	return store.inner.Tombstone(ctx, toIndex(row))
}

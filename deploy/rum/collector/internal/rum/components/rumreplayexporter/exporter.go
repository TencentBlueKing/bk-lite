package rumreplayexporter

import (
	"context"
	"errors"
	"strconv"
	"time"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer/consumererror"
	"go.opentelemetry.io/collector/pdata/plog"
)

type replayExporter struct {
	objects        ObjectStore
	indexes        IndexStore
	leases         LeaseStore
	bucket         string
	now            func() time.Time
	maxQueueAge    time.Duration
	observeAgeDrop func(context.Context, replayAgeDrop)
}

type replayAgeDrop struct {
	Reason string
	Count  int
}

func (exporter *replayExporter) Start(ctx context.Context, _ component.Host) error {
	if exporter.leases == nil {
		return errors.New("Replay exporter requires a lease store")
	}
	if err := exporter.leases.Start(ctx); err != nil {
		return err
	}
	if err := exporter.objects.Start(ctx); err != nil {
		_ = exporter.leases.Shutdown(ctx)
		return err
	}
	if err := exporter.indexes.Start(ctx); err != nil {
		_ = exporter.objects.Shutdown(ctx)
		_ = exporter.leases.Shutdown(ctx)
		return err
	}
	return nil
}

func (exporter *replayExporter) Shutdown(ctx context.Context) error {
	return errors.Join(
		exporter.indexes.Shutdown(ctx),
		exporter.objects.Shutdown(ctx),
		exporter.leases.Shutdown(ctx),
	)
}

func (exporter *replayExporter) pushLogs(ctx context.Context, logs plog.Logs) error {
	if deadline, ok := ctx.Deadline(); !ok || time.Until(deadline) > exporterOperationTimeout {
		bounded, cancel := context.WithTimeout(ctx, exporterOperationTimeout)
		defer cancel()
		ctx = bounded
	}

	segments, err := extractReplaySegments(logs)
	if err != nil {
		return consumererror.NewPermanent(err)
	}
	live := segments[:0]
	expired := 0
	for _, segment := range segments {
		if exporter.acceptedAtExpired(segment.Index.AcceptedAtUnixNano) {
			expired++
			continue
		}
		live = append(live, segment)
	}
	if expired > 0 && exporter.observeAgeDrop != nil {
		exporter.observeAgeDrop(ctx, replayAgeDrop{Reason: "expired", Count: expired})
	}
	segments = live
	bucket := exporter.bucket
	if bucket == "" {
		bucket = defaultReplayBucket
	}
	for _, segment := range segments {
		segment.Object.Bucket = bucket
		if err := exporter.pushSegment(ctx, segment); err != nil {
			return err
		}
	}
	return nil
}

func (exporter *replayExporter) pushSegment(ctx context.Context, segment replaySegment) (result error) {
	if exporter.leases == nil {
		return errors.New("Replay exporter requires a lease store")
	}
	sequenceToken, state, err := exporter.leases.AcquireSequence(ctx, segment.Index)
	if err != nil {
		return classifyStoreError(err)
	}
	defer func() {
		if releaseErr := exporter.releaseLease(ctx, sequenceToken); releaseErr != nil {
			result = errors.Join(result, releaseErr)
		}
	}()

	canonicalizeAcceptedAt(&segment, state.AcceptedAtUnixNano)

	pending := segment.Index
	pending.Status = "pending"
	_, err = exporter.indexes.BeginPending(ctx, pending)
	if err != nil {
		return classifyStoreError(err)
	}
	if exporter.acceptedAtExpired(segment.Index.AcceptedAtUnixNano) {
		if exporter.observeAgeDrop != nil {
			exporter.observeAgeDrop(ctx, replayAgeDrop{Reason: "expired", Count: 1})
		}
		return classifyStoreError(exporter.cleanupPending(ctx, sequenceToken, segment))
	}

	if !state.ObjectStored {
		if _, err := exporter.objects.Ensure(ctx, segment.Object); err != nil {
			return classifyStoreError(errors.Join(err, exporter.cleanupPending(ctx, sequenceToken, segment)))
		}
		if err := exporter.leases.MarkObjectStored(ctx, sequenceToken); err != nil {
			return errors.Join(err, exporter.cleanupPending(ctx, sequenceToken, segment))
		}
	} else if err := exporter.leases.Renew(ctx, sequenceToken); err != nil {
		return errors.Join(err, exporter.cleanupPending(ctx, sequenceToken, segment))
	}

	ready := segment.Index
	ready.Status = "ready"
	if _, err := exporter.indexes.PublishReady(ctx, ready); err != nil {
		// A failed publish may have committed despite the transport error. Keep the
		// object and pending row for an idempotent retry or reconciliation; never
		// re-Ensure after a ready row may be visible.
		return classifyStoreError(err)
	}
	return nil
}

func (exporter *replayExporter) acceptedAtExpired(acceptedAt uint64) bool {
	now := time.Now()
	if exporter.now != nil {
		now = exporter.now()
	}
	maxAge := exporter.maxQueueAge
	if maxAge <= 0 {
		maxAge = maxReplayQueueAge
	}
	deadline := time.Unix(0, int64(acceptedAt)).UTC().Add(maxAge)
	return !now.UTC().Before(deadline)
}

func canonicalizeAcceptedAt(segment *replaySegment, acceptedAt uint64) {
	segment.Index.AcceptedAtUnixNano = acceptedAt
	segment.Object.Metadata["accepted-at-unix-nano"] = strconv.FormatUint(acceptedAt, 10)
}

func (exporter *replayExporter) releaseLease(parent context.Context, token leaseToken) error {
	ctx, cancel := context.WithTimeout(context.WithoutCancel(parent), leaseReleaseTimeout)
	defer cancel()
	return exporter.leases.Release(ctx, token)
}

func (exporter *replayExporter) cleanupPending(
	parent context.Context,
	token leaseToken,
	segment replaySegment,
) error {
	ctx, cancel := context.WithTimeout(context.WithoutCancel(parent), pendingCleanupTimeout)
	defer cancel()
	pending := segment.Index
	pending.Status = "pending"
	return errors.Join(
		exporter.leases.ClearObjectStored(ctx, token),
		exporter.indexes.Tombstone(ctx, pending),
	)
}

func classifyStoreError(err error) error {
	if errors.Is(err, ErrChecksumConflict) ||
		errors.Is(err, ErrErasureFenced) ||
		errors.Is(err, ErrInvalidCarrier) {
		return consumererror.NewPermanent(err)
	}
	return err
}

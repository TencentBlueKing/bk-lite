package maintainer

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
)

type ReplayIndexStore interface {
	ListReplayCandidates(context.Context, string, time.Time, ReplayScanCursor, uint64) ([]ReplayIndex, error)
	SetReplayStatus(context.Context, ReplayIndex, string) error
	HasReplayIndex(context.Context, string) (bool, error)
	AuditReconciliation(context.Context, string, string, string, uint64, uint64, uint64, uint64) error
}

type ReplayObjectStore interface {
	Stat(context.Context, string) (ObjectState, error)
	DeleteAllVersions(context.Context, string) error
	ListAfter(context.Context, string, func(string, time.Time) error) error
}

type ReconcileState interface {
	Complete(context.Context, string) error
	Retry(context.Context, string, error) error
	Fail(context.Context, string, error) error
	ReconcileCursor(context.Context) (string, error)
	SetReconcileCursor(context.Context, string) error
	ReplayScanCursor(context.Context, string) (ReplayScanCursor, error)
	SetReplayScanCursor(context.Context, string, ReplayScanCursor) error
	Applications(context.Context) ([]string, error)
}

type ReplayScanCursor struct {
	AcceptedAtUnixNano uint64
	SegmentID          string
}

type Reconciler struct {
	indexes     ReplayIndexStore
	objects     ReplayObjectStore
	state       ReconcileState
	now         func() time.Time
	newRunID    func() string
	orphanGrace time.Duration
	pageSize    uint64
	indexEpoch  time.Time
}

func NewReconciler(indexes ReplayIndexStore, objects ReplayObjectStore, state ReconcileState, epoch time.Time) (*Reconciler, error) {
	if epoch.IsZero() {
		return nil, errors.New("replay_index_epoch is required")
	}
	return &Reconciler{
		indexes:     indexes,
		objects:     objects,
		state:       state,
		now:         time.Now,
		newRunID:    uuid.NewString,
		orphanGrace: time.Hour,
		pageSize:    1000,
		indexEpoch:  epoch.UTC(),
	}, nil
}

func (reconciler *Reconciler) RunOperation(ctx context.Context, task ReconcileTask) error {
	conflicts, err := reconciler.reconcileApplication(ctx, task.Application)
	if err != nil {
		_ = reconciler.state.Retry(ctx, task.OperationID, err)
		return err
	}
	if conflicts > 0 {
		cause := fmt.Errorf("%w: %d conflicting Replay records", ErrReplayConflict, conflicts)
		if err := reconciler.state.Fail(ctx, task.OperationID, cause); err != nil {
			return err
		}
		return nil
	}
	return reconciler.state.Complete(ctx, task.OperationID)
}

func (reconciler *Reconciler) RunScheduled(ctx context.Context) error {
	applications, err := reconciler.state.Applications(ctx)
	if err != nil {
		return err
	}
	var joined error
	for _, application := range applications {
		_, err := reconciler.reconcileApplication(ctx, application)
		joined = errors.Join(joined, err)
	}
	status := "completed"
	if joined != nil {
		status = "failed"
	}
	heartbeatErr := reconciler.indexes.AuditReconciliation(
		ctx,
		reconciler.newRunID(),
		"",
		status,
		0,
		0,
		0,
		0,
	)
	return errors.Join(joined, heartbeatErr)
}

func (reconciler *Reconciler) RunOrphanScan(ctx context.Context) error {
	cursor, err := reconciler.state.ReconcileCursor(ctx)
	if err != nil {
		return err
	}
	cutoff := reconciler.now().UTC().Add(-reconciler.orphanGrace)
	var checked, orphans uint64
	last := cursor
	err = reconciler.objects.ListAfter(ctx, cursor, func(key string, modifiedAt time.Time) error {
		last = key
		checked++
		if modifiedAt.After(cutoff) {
			return reconciler.state.SetReconcileCursor(ctx, last)
		}
		if modifiedAt.UTC().Before(reconciler.indexEpoch) {
			return reconciler.state.SetReconcileCursor(ctx, last)
		}
		exists, err := reconciler.indexes.HasReplayIndex(ctx, key)
		if err != nil {
			return err
		}
		if !exists {
			if err := reconciler.objects.DeleteAllVersions(ctx, key); err != nil {
				return err
			}
			orphans++
		}
		return reconciler.state.SetReconcileCursor(ctx, last)
	})
	status := "completed"
	if err != nil {
		status = "failed"
	} else {
		err = reconciler.state.SetReconcileCursor(ctx, "")
	}
	auditErr := reconciler.indexes.AuditReconciliation(
		ctx,
		reconciler.newRunID(),
		"",
		status,
		checked,
		0,
		0,
		orphans,
	)
	return errors.Join(err, auditErr)
}

func (reconciler *Reconciler) reconcileApplication(ctx context.Context, application string) (uint64, error) {
	now := reconciler.now().UTC()
	cursor, err := reconciler.state.ReplayScanCursor(ctx, application)
	if err != nil {
		return 0, err
	}
	indexes, err := reconciler.indexes.ListReplayCandidates(
		ctx,
		application,
		now.Add(-2*time.Minute),
		cursor,
		reconciler.pageSize,
	)
	if err != nil {
		return 0, err
	}
	var checked, repaired, conflicts uint64
	var joined error
	for _, index := range indexes {
		checked++
		object, err := reconciler.objects.Stat(ctx, index.ObjectKey)
		if err != nil {
			joined = errors.Join(joined, err)
			continue
		}
		action, err := DecideReplayAction(now, index.Record(), object)
		if errors.Is(err, ErrReplayConflict) {
			conflicts++
			continue
		}
		if err != nil {
			joined = errors.Join(joined, err)
			continue
		}
		if action == ActionNone {
			continue
		}
		if err := reconciler.indexes.SetReplayStatus(ctx, index, string(action)); err != nil {
			joined = errors.Join(joined, err)
			continue
		}
		repaired++
	}
	nextCursor := ReplayScanCursor{}
	if uint64(len(indexes)) == reconciler.pageSize && len(indexes) > 0 {
		last := indexes[len(indexes)-1]
		nextCursor = ReplayScanCursor{
			AcceptedAtUnixNano: last.AcceptedAtUnixNano,
			SegmentID:          last.SegmentID,
		}
	}
	if err := reconciler.state.SetReplayScanCursor(ctx, application, nextCursor); err != nil {
		joined = errors.Join(joined, err)
	}
	status := "completed"
	if joined != nil {
		status = "failed"
	} else if conflicts > 0 {
		status = "attention"
	}
	auditErr := reconciler.indexes.AuditReconciliation(
		ctx,
		reconciler.newRunID(),
		application,
		status,
		checked,
		repaired,
		conflicts,
		0,
	)
	return conflicts, errors.Join(joined, auditErr)
}

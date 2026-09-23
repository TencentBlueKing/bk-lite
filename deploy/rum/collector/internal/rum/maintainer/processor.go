package maintainer

import (
	"context"
	"errors"
	"fmt"
	"time"
)

var ErrReplayConflict = errors.New("Replay object and index identity conflict")

type Identity struct {
	Kind    string `json:"kind"`
	Version string `json:"version"`
	Digest  string `json:"digest"`
}

type ErasureTask struct {
	OperationID string
	Application string
	Actor       string
	Identities  []Identity
}

type ReplayRecord struct {
	TenantID           string
	Application        string
	SessionID          string
	RecordingID        string
	Sequence           uint32
	Status             string
	UpdatedAt          time.Time
	ChecksumSHA256     string
	ObjectKey          string
	AcceptedAtUnixNano uint64
	ErasureKeyVersion  string
	Version            uint64
}

type ObjectState struct {
	Exists             bool
	ChecksumSHA256     string
	AcceptedAtUnixNano uint64
	ErasureKeyVersion  string
}

type ReconcileAction string

const (
	ActionNone         ReconcileAction = ""
	ActionReady        ReconcileAction = "ready"
	ActionTombstone    ReconcileAction = "tombstone"
	ActionInconsistent ReconcileAction = "inconsistent"
)

// Warehouse deletes telemetry only. Replay object keys come from Redis.
type Warehouse interface {
	BeginErasure(context.Context, ErasureTask) error
	WaitMutations(context.Context) error
	AuditErasure(context.Context, ErasureTask) error
}

// ReplayObjectIndex looks up Replay object keys for erasure.
type ReplayObjectIndex interface {
	ReplayObjectsForErasure(context.Context, ErasureTask) ([]string, error)
}

type ObjectStore interface {
	DeleteAllVersions(context.Context, string) error
}

type OperationStore interface {
	PersistErasureObjects(context.Context, string, []string) ([]string, error)
	Complete(context.Context, string) error
	Retry(context.Context, string, error) error
}

type ErasureBarrier interface {
	WaitForErasureLeases(context.Context, []Identity) error
}

type ControlAuditTask struct {
	RequestID   string
	Actor       string
	Action      string
	Application string
	Revision    int64
	CreatedAt   string
}

type ControlAuditor interface {
	AuditControl(context.Context, ControlAuditTask) error
}

type Processor struct {
	indexes    ReplayObjectIndex
	warehouse  Warehouse
	objects    ObjectStore
	operations OperationStore
}

func (processor *Processor) AuditControl(ctx context.Context, task ControlAuditTask) error {
	auditor, ok := processor.warehouse.(ControlAuditor)
	if !ok {
		return nil
	}
	return auditor.AuditControl(ctx, task)
}

func NewProcessor(indexes ReplayObjectIndex, warehouse Warehouse, objects ObjectStore, operations OperationStore) *Processor {
	return &Processor{indexes: indexes, warehouse: warehouse, objects: objects, operations: operations}
}

func (processor *Processor) Erase(ctx context.Context, task ErasureTask) error {
	barrier, ok := processor.operations.(ErasureBarrier)
	if !ok {
		return processor.retry(ctx, task.OperationID, errors.New("operation store does not provide the erasure lease barrier"))
	}
	if err := barrier.WaitForErasureLeases(ctx, task.Identities); err != nil {
		return processor.retry(ctx, task.OperationID, err)
	}
	objectKeys, err := processor.indexes.ReplayObjectsForErasure(ctx, task)
	if err != nil {
		return processor.retry(ctx, task.OperationID, err)
	}
	objectKeys, err = processor.operations.PersistErasureObjects(ctx, task.OperationID, objectKeys)
	if err != nil {
		return processor.retry(ctx, task.OperationID, err)
	}
	if err := processor.warehouse.BeginErasure(ctx, task); err != nil {
		return processor.retry(ctx, task.OperationID, err)
	}
	for _, objectKey := range objectKeys {
		if err := processor.objects.DeleteAllVersions(ctx, objectKey); err != nil {
			return processor.retry(ctx, task.OperationID, err)
		}
	}
	if err := processor.warehouse.WaitMutations(ctx); err != nil {
		return processor.retry(ctx, task.OperationID, err)
	}
	if err := processor.warehouse.AuditErasure(ctx, task); err != nil {
		return processor.retry(ctx, task.OperationID, err)
	}
	if err := processor.operations.Complete(ctx, task.OperationID); err != nil {
		return processor.retry(ctx, task.OperationID, err)
	}
	return nil
}

func (processor *Processor) retry(ctx context.Context, operationID string, cause error) error {
	if processor.operations != nil {
		cause = errors.Join(cause, processor.operations.Retry(ctx, operationID, cause))
	}
	return cause
}

func DecideReplayAction(now time.Time, record ReplayRecord, object ObjectState) (ReconcileAction, error) {
	if object.Exists {
		if record.ChecksumSHA256 != object.ChecksumSHA256 ||
			(object.AcceptedAtUnixNano != 0 && record.AcceptedAtUnixNano != object.AcceptedAtUnixNano) ||
			(object.ErasureKeyVersion != "" && record.ErasureKeyVersion != object.ErasureKeyVersion) {
			return ActionNone, fmt.Errorf("%w for %s", ErrReplayConflict, record.ObjectKey)
		}
		if record.Status == "pending" {
			return ActionReady, nil
		}
		return ActionNone, nil
	}
	age := now.UTC().Sub(record.UpdatedAt.UTC())
	switch record.Status {
	case "pending":
		if age > 15*time.Minute {
			return ActionTombstone, nil
		}
	case "ready":
		return ActionInconsistent, nil
	}
	return ActionNone, nil
}

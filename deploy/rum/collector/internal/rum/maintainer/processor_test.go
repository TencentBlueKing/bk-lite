package maintainer

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	rumstate "github.com/bk-lite/rum-collector/internal/rum/state"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func TestErasureDeletesIndexesObjectsAndWaitsBeforeCompletingOperation(t *testing.T) {
	recorder := &callRecorder{}
	warehouse := &fakeWarehouse{
		recorder: recorder,
		objects:  []string{"tenant/app/replay-a.json.gz", "tenant/app/replay-b.json.gz"},
	}
	objects := &fakeObjects{recorder: recorder}
	operations := &fakeOperations{recorder: recorder}
	processor := NewProcessor(warehouse, warehouse, objects, operations)
	task := ErasureTask{
		OperationID: "op-erase-1",
		Application: "storefront",
		Identities: []Identity{
			{Kind: "user", Version: "v1", Digest: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
		},
	}

	err := processor.Erase(t.Context(), task)

	require.NoError(t, err)
	require.Equal(t, []string{
		"operations.wait_erasure_leases",
		"warehouse.list_replay_objects",
		"operations.persist_erasure_objects",
		"warehouse.begin_erasure",
		"objects.delete:tenant/app/replay-a.json.gz",
		"objects.delete:tenant/app/replay-b.json.gz",
		"warehouse.wait_mutations",
		"warehouse.audit_erasure",
		"operations.complete",
	}, recorder.calls)
}

func TestErasureNeverCompletesWhenMutationOrObjectDeletionFails(t *testing.T) {
	for name, configure := range map[string]func(*fakeWarehouse, *fakeObjects){
		"warehouse": func(warehouse *fakeWarehouse, _ *fakeObjects) {
			warehouse.err = errors.New("warehouse unavailable")
		},
		"minio": func(_ *fakeWarehouse, objects *fakeObjects) {
			objects.err = errors.New("MinIO unavailable")
		},
	} {
		t.Run(name, func(t *testing.T) {
			recorder := &callRecorder{}
			warehouse := &fakeWarehouse{recorder: recorder, objects: []string{"replay.json.gz"}}
			objects := &fakeObjects{recorder: recorder}
			operations := &fakeOperations{recorder: recorder}
			configure(warehouse, objects)
			processor := NewProcessor(warehouse, warehouse, objects, operations)

			err := processor.Erase(t.Context(), ErasureTask{
				OperationID: "op-erase-1",
				Application: "storefront",
				Identities: []Identity{{
					Kind:    "session",
					Version: "v1",
					Digest:  "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
				}},
			})

			require.Error(t, err)
			require.NotContains(t, recorder.calls, "operations.complete")
			require.Contains(t, recorder.calls, "operations.retry")
		})
	}
}

func TestErasureBarrierWaitsForInFlightGatewayLease(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	now := time.Now().UTC()
	state := &RedisState{client: client, now: func() time.Time { return now }}
	identity := Identity{Version: "v1", Digest: strings.Repeat("a", 64)}
	key := ingress.ErasureFenceKey(identity.Version, identity.Digest)
	require.NoError(t, client.ZAdd(t.Context(), key,
		redis.Z{Score: 0, Member: "fence"},
		redis.Z{Score: float64(now.Add(time.Minute).UnixMilli()), Member: "gateway:active"},
	).Err())

	done := make(chan error, 1)
	go func() {
		done <- state.WaitForErasureLeases(t.Context(), []Identity{identity})
	}()
	select {
	case err := <-done:
		t.Fatalf("barrier returned while the exporter lease was active: %v", err)
	case <-time.After(150 * time.Millisecond):
	}

	require.NoError(t, client.ZRem(t.Context(), key, "gateway:active").Err())
	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(time.Second):
		t.Fatal("barrier did not unblock after the exporter lease was released")
	}
}

func TestErasureReplayObjectPlanSurvivesIndexDeletionAndRetry(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	state := &RedisState{client: client, now: time.Now}
	operationID := "op-erasure-retry"
	require.NoError(t, client.HSet(
		t.Context(),
		rumstate.OperationKeyPrefix+operationID,
		"operation_id",
		operationID,
	).Err())

	first, err := state.PersistErasureObjects(t.Context(), operationID, []string{
		"tenant/app/replay-b.json.gz",
		"tenant/app/replay-a.json.gz",
		"tenant/app/replay-a.json.gz",
	})
	require.NoError(t, err)
	require.Equal(t, []string{
		"tenant/app/replay-a.json.gz",
		"tenant/app/replay-b.json.gz",
	}, first)

	afterIndexDeletion, err := state.PersistErasureObjects(t.Context(), operationID, nil)
	require.NoError(t, err)
	require.Equal(t, first, afterIndexDeletion)
}

func TestMaintainerRetriesItsPendingMessageWithoutProcessRestart(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	state := &RedisState{client: client, consumer: "maintainer-test", now: time.Now}
	require.NoError(t, state.Start(t.Context()))

	identities, err := json.Marshal([]Identity{{
		Kind:    "session",
		Version: "v1",
		Digest:  strings.Repeat("a", 64),
	}})
	require.NoError(t, err)
	messageID, err := client.XAdd(t.Context(), &redis.XAddArgs{
		Stream: rumstate.ErasureStreamKey,
		Values: map[string]any{
			"operation_id": "op-retry",
			"application":  "storefront",
			"actor":        "test",
			"identities":   string(identities),
		},
	}).Result()
	require.NoError(t, err)
	require.NotEmpty(t, messageID)
	_, err = client.XReadGroup(t.Context(), &redis.XReadGroupArgs{
		Group:    maintainerGroup,
		Consumer: state.consumer,
		Streams:  []string{rumstate.ErasureStreamKey, ">"},
		Count:    1,
		Block:    -1,
	}).Result()
	require.NoError(t, err)

	recorder := &callRecorder{}
	wh := &fakeWarehouse{recorder: recorder}
	processor := NewProcessor(
		wh,
		wh,
		&fakeObjects{recorder: recorder},
		&fakeOperations{recorder: recorder},
	)
	require.NoError(t, state.retryOwnPending(t.Context(), processor, &Reconciler{}))

	require.Zero(t, client.XLen(t.Context(), rumstate.ErasureStreamKey).Val())
	require.Contains(t, recorder.calls, "operations.complete")
}

func TestReplayReconciliationRepairsOnlySafeStates(t *testing.T) {
	now := time.Date(2026, 8, 5, 10, 0, 0, 0, time.UTC)
	cases := []struct {
		name       string
		record     ReplayRecord
		object     ObjectState
		wantAction ReconcileAction
		wantErr    error
	}{
		{
			name: "pending object matches",
			record: ReplayRecord{
				Status:         "pending",
				UpdatedAt:      now.Add(-3 * time.Minute),
				ChecksumSHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				ObjectKey:      "matching.json.gz",
			},
			object: ObjectState{
				Exists:         true,
				ChecksumSHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			},
			wantAction: ActionReady,
		},
		{
			name: "young pending remains pending",
			record: ReplayRecord{
				Status:    "pending",
				UpdatedAt: now.Add(-3 * time.Minute),
				ObjectKey: "missing.json.gz",
			},
			wantAction: ActionNone,
		},
		{
			name: "old pending without object tombstones",
			record: ReplayRecord{
				Status:    "pending",
				UpdatedAt: now.Add(-16 * time.Minute),
				ObjectKey: "missing.json.gz",
			},
			wantAction: ActionTombstone,
		},
		{
			name: "ready without object is inconsistent",
			record: ReplayRecord{
				Status:    "ready",
				UpdatedAt: now.Add(-3 * time.Minute),
				ObjectKey: "missing.json.gz",
			},
			wantAction: ActionInconsistent,
		},
		{
			name: "checksum conflict stops automatic repair",
			record: ReplayRecord{
				Status:         "pending",
				UpdatedAt:      now.Add(-3 * time.Minute),
				ChecksumSHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				ObjectKey:      "conflict.json.gz",
			},
			object: ObjectState{
				Exists:         true,
				ChecksumSHA256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
			},
			wantErr: ErrReplayConflict,
		},
	}

	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			action, err := DecideReplayAction(now, test.record, test.object)
			require.ErrorIs(t, err, test.wantErr)
			require.Equal(t, test.wantAction, action)
		})
	}
}

type callRecorder struct {
	calls []string
}

func (recorder *callRecorder) add(call string) {
	recorder.calls = append(recorder.calls, call)
}

type fakeWarehouse struct {
	recorder *callRecorder
	objects  []string
	err      error
}

func (fake *fakeWarehouse) ReplayObjectsForErasure(context.Context, ErasureTask) ([]string, error) {
	fake.recorder.add("warehouse.list_replay_objects")
	if fake.err != nil {
		return nil, fake.err
	}
	return fake.objects, nil
}

func (fake *fakeWarehouse) BeginErasure(context.Context, ErasureTask) error {
	fake.recorder.add("warehouse.begin_erasure")
	return fake.err
}

func (fake *fakeWarehouse) WaitMutations(context.Context) error {
	fake.recorder.add("warehouse.wait_mutations")
	return fake.err
}

func (fake *fakeWarehouse) AuditErasure(context.Context, ErasureTask) error {
	fake.recorder.add("warehouse.audit_erasure")
	return fake.err
}

type fakeObjects struct {
	recorder *callRecorder
	err      error
}

func (fake *fakeObjects) DeleteAllVersions(_ context.Context, key string) error {
	fake.recorder.add("objects.delete:" + key)
	return fake.err
}

type fakeOperations struct {
	recorder  *callRecorder
	persisted []string
}

func (fake *fakeOperations) WaitForErasureLeases(context.Context, []Identity) error {
	fake.recorder.add("operations.wait_erasure_leases")
	return nil
}

func (fake *fakeOperations) Complete(context.Context, string) error {
	fake.recorder.add("operations.complete")
	return nil
}

func (fake *fakeOperations) PersistErasureObjects(_ context.Context, _ string, keys []string) ([]string, error) {
	fake.recorder.add("operations.persist_erasure_objects")
	if fake.persisted == nil {
		fake.persisted = append([]string(nil), keys...)
	}
	return append([]string(nil), fake.persisted...), nil
}

func (fake *fakeOperations) Retry(_ context.Context, _ string, _ error) error {
	fake.recorder.add("operations.retry")
	return nil
}

package maintainer

import (
	"context"
	"sort"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func TestReplayReconciliationCursorPreventsStableReadyRowsFromStarvingLaterRows(t *testing.T) {
	now := time.Date(2026, 8, 5, 10, 0, 0, 0, time.UTC)
	indexes := &pagedReplayIndexes{
		rows: []ReplayIndex{
			replayIndexForCursor("segment-a", now.Add(-5*time.Minute)),
			replayIndexForCursor("segment-b", now.Add(-4*time.Minute)),
			replayIndexForCursor("segment-c", now.Add(-3*time.Minute)),
		},
	}
	objects := &pagedReplayObjects{seen: make([]string, 0, 3)}
	state := &pagedReconcileState{
		applications: []string{"storefront"},
		cursors:      make(map[string]ReplayScanCursor),
	}
	reconciler, err := NewReconciler(indexes, objects, state, time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC))
	require.NoError(t, err)
	reconciler.now = func() time.Time { return now }
	reconciler.pageSize = 2

	require.NoError(t, reconciler.RunScheduled(t.Context()))
	require.Equal(t, []string{"segment-a", "segment-b"}, objects.seen)
	require.Equal(t, ReplayScanCursor{
		AcceptedAtUnixNano: indexes.rows[1].AcceptedAtUnixNano,
		SegmentID:          "segment-b",
	}, state.cursors["storefront"])

	require.NoError(t, reconciler.RunScheduled(t.Context()))
	require.Equal(t, []string{"segment-a", "segment-b", "segment-c"}, objects.seen)
	require.Equal(t, ReplayScanCursor{}, state.cursors["storefront"])
	require.Equal(t, []uint64{2, 0, 1, 0}, indexes.auditChecked)
}

func TestNewReconcilerRejectsZeroEpoch(t *testing.T) {
	_, err := NewReconciler(&missingReplayIndexes{}, &epochObjects{}, &pagedReconcileState{}, time.Time{})
	require.Error(t, err)
}

func TestOrphanScanRespectsIndexEpoch(t *testing.T) {
	epoch := time.Date(2026, 8, 18, 0, 0, 0, 0, time.UTC)
	indexes := &missingReplayIndexes{}
	objects := &epochObjects{
		items: []epochObject{
			{key: "old.json.gz", modified: epoch.Add(-time.Hour)},
			{key: "new.json.gz", modified: epoch.Add(2 * time.Hour)},
		},
	}
	state := &pagedReconcileState{applications: []string{"storefront"}, cursors: map[string]ReplayScanCursor{}}
	reconciler, err := NewReconciler(indexes, objects, state, epoch)
	require.NoError(t, err)
	reconciler.now = func() time.Time { return epoch.Add(3 * time.Hour) }
	require.NoError(t, reconciler.RunOrphanScan(t.Context()))
	require.Equal(t, []string{"new.json.gz"}, objects.deleted)
}

type epochObject struct {
	key      string
	modified time.Time
}

type epochObjects struct {
	items   []epochObject
	deleted []string
}

func (store *epochObjects) Stat(context.Context, string) (ObjectState, error) {
	return ObjectState{}, nil
}

func (store *epochObjects) DeleteAllVersions(_ context.Context, key string) error {
	store.deleted = append(store.deleted, key)
	return nil
}

func (store *epochObjects) ListAfter(_ context.Context, _ string, fn func(string, time.Time) error) error {
	for _, item := range store.items {
		if err := fn(item.key, item.modified); err != nil {
			return err
		}
	}
	return nil
}

type missingReplayIndexes struct{}

func (*missingReplayIndexes) ListReplayCandidates(context.Context, string, time.Time, ReplayScanCursor, uint64) ([]ReplayIndex, error) {
	return nil, nil
}
func (*missingReplayIndexes) SetReplayStatus(context.Context, ReplayIndex, string) error { return nil }
func (*missingReplayIndexes) HasReplayIndex(context.Context, string) (bool, error) {
	return false, nil
}
func (*missingReplayIndexes) AuditReconciliation(context.Context, string, string, string, uint64, uint64, uint64, uint64) error {
	return nil
}

func TestRedisReplayScanCursorRoundTripAndReset(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	state := &RedisState{client: client, now: time.Now}
	want := ReplayScanCursor{AcceptedAtUnixNano: 1234, SegmentID: "segment-a"}

	require.NoError(t, state.SetReplayScanCursor(t.Context(), "storefront", want))
	got, err := state.ReplayScanCursor(t.Context(), "storefront")
	require.NoError(t, err)
	require.Equal(t, want, got)

	require.NoError(t, state.SetReplayScanCursor(t.Context(), "storefront", ReplayScanCursor{}))
	got, err = state.ReplayScanCursor(t.Context(), "storefront")
	require.NoError(t, err)
	require.Equal(t, ReplayScanCursor{}, got)
}

func replayIndexForCursor(segmentID string, acceptedAt time.Time) ReplayIndex {
	return ReplayIndex{
		Application:        "storefront",
		SegmentID:          segmentID,
		Status:             "ready",
		ObjectKey:          "core/storefront/" + segmentID + ".json.gz",
		ChecksumSHA256:     "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		AcceptedAtUnixNano: uint64(acceptedAt.UnixNano()),
	}
}

type pagedReplayIndexes struct {
	rows         []ReplayIndex
	auditChecked []uint64
}

func (store *pagedReplayIndexes) ListReplayCandidates(
	_ context.Context,
	_ string,
	before time.Time,
	cursor ReplayScanCursor,
	limit uint64,
) ([]ReplayIndex, error) {
	rows := append([]ReplayIndex(nil), store.rows...)
	sort.Slice(rows, func(left, right int) bool {
		if rows[left].AcceptedAtUnixNano == rows[right].AcceptedAtUnixNano {
			return rows[left].SegmentID < rows[right].SegmentID
		}
		return rows[left].AcceptedAtUnixNano < rows[right].AcceptedAtUnixNano
	})
	result := make([]ReplayIndex, 0, limit)
	for _, row := range rows {
		if row.AcceptedAtUnixNano >= uint64(before.UnixNano()) {
			continue
		}
		if row.AcceptedAtUnixNano < cursor.AcceptedAtUnixNano ||
			(row.AcceptedAtUnixNano == cursor.AcceptedAtUnixNano && row.SegmentID <= cursor.SegmentID) {
			continue
		}
		result = append(result, row)
		if uint64(len(result)) == limit {
			break
		}
	}
	return result, nil
}

func (*pagedReplayIndexes) SetReplayStatus(context.Context, ReplayIndex, string) error {
	return nil
}

func (*pagedReplayIndexes) HasReplayIndex(context.Context, string) (bool, error) {
	return true, nil
}

func (store *pagedReplayIndexes) AuditReconciliation(
	_ context.Context,
	_, _, _ string,
	checked, _, _, _ uint64,
) error {
	store.auditChecked = append(store.auditChecked, checked)
	return nil
}

type pagedReplayObjects struct {
	seen []string
}

func (store *pagedReplayObjects) Stat(_ context.Context, key string) (ObjectState, error) {
	store.seen = append(store.seen, key[len("core/storefront/"):len(key)-len(".json.gz")])
	return ObjectState{
		Exists:         true,
		ChecksumSHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	}, nil
}

func (*pagedReplayObjects) DeleteAllVersions(context.Context, string) error {
	return nil
}

func (*pagedReplayObjects) ListAfter(context.Context, string, func(string, time.Time) error) error {
	return nil
}

type pagedReconcileState struct {
	applications []string
	cursors      map[string]ReplayScanCursor
}

func (*pagedReconcileState) Complete(context.Context, string) error {
	return nil
}

func (*pagedReconcileState) Retry(context.Context, string, error) error {
	return nil
}

func (*pagedReconcileState) Fail(context.Context, string, error) error {
	return nil
}

func (*pagedReconcileState) ReconcileCursor(context.Context) (string, error) {
	return "", nil
}

func (*pagedReconcileState) SetReconcileCursor(context.Context, string) error {
	return nil
}

func (state *pagedReconcileState) ReplayScanCursor(_ context.Context, application string) (ReplayScanCursor, error) {
	return state.cursors[application], nil
}

func (state *pagedReconcileState) SetReplayScanCursor(
	_ context.Context,
	application string,
	cursor ReplayScanCursor,
) error {
	state.cursors[application] = cursor
	return nil
}

func (state *pagedReconcileState) Applications(context.Context) ([]string, error) {
	return append([]string(nil), state.applications...), nil
}

package replayindex

import (
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func testStore(t *testing.T) *Store {
	t.Helper()
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return NewStore(client)
}

func sampleRow() Index {
	return Index{
		TenantID:           "core",
		Application:        "storefront",
		SessionID:          "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		SessionKey:         "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		RecordingID:        "rec-1",
		SegmentID:          "seg-1",
		Sequence:           0,
		StartTime:          "2026-08-18T00:00:00.000Z",
		EndTime:            "2026-08-18T00:00:01.000Z",
		EventCount:         3,
		ChecksumSHA256:     "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		ObjectKey:          "v1/obj.json.gz",
		ErasureKeyVersion:  "v1",
		ErasureUserKey:     "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
		ErasureSessionKey:  "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
		AcceptedAtUnixNano: 1_700_000_000_000_000_000,
	}
}

func TestReadyManifestListsSession(t *testing.T) {
	store := testStore(t)
	row := sampleRow()
	_, err := store.BeginPending(t.Context(), row)
	require.NoError(t, err)
	_, err = store.PublishReady(t.Context(), row)
	require.NoError(t, err)

	rows, err := store.Manifest(t.Context(), "storefront", row.SessionKey)
	require.NoError(t, err)
	require.Len(t, rows, 1)
	require.Equal(t, readyStatus, rows[0].Status)
	require.Equal(t, row.ObjectKey, rows[0].ObjectKey)

	has, err := store.HasReady(t.Context(), "storefront", row.SessionKey)
	require.NoError(t, err)
	require.True(t, has)
	hasObj, err := store.HasObject(t.Context(), row.ObjectKey)
	require.NoError(t, err)
	require.True(t, hasObj)
}

func TestErasureLookupUsesIdentitySets(t *testing.T) {
	store := testStore(t)
	row := sampleRow()
	_, err := store.PublishReady(t.Context(), row)
	require.NoError(t, err)
	keys, err := store.ObjectsForErasure(t.Context(), "v1", []string{row.ErasureUserKey})
	require.NoError(t, err)
	require.Equal(t, []string{row.ObjectKey}, keys)
}

func TestTombstoneDropsObjectLookup(t *testing.T) {
	store := testStore(t)
	row := sampleRow()
	_, err := store.PublishReady(t.Context(), row)
	require.NoError(t, err)
	require.NoError(t, store.Tombstone(t.Context(), row))
	has, err := store.HasObject(t.Context(), row.ObjectKey)
	require.NoError(t, err)
	require.False(t, has)
}

func TestListCandidatesRespectsCursor(t *testing.T) {
	store := testStore(t)
	first := sampleRow()
	second := sampleRow()
	second.SegmentID = "seg-2"
	second.Sequence = 1
	second.AcceptedAtUnixNano = first.AcceptedAtUnixNano + 10
	second.ObjectKey = "v1/obj-2.json.gz"
	_, err := store.PublishReady(t.Context(), first)
	require.NoError(t, err)
	_, err = store.PublishReady(t.Context(), second)
	require.NoError(t, err)

	before := time.Unix(0, int64(second.AcceptedAtUnixNano+1))
	page, err := store.ListCandidates(t.Context(), "storefront", before, ScanCursor{}, 1)
	require.NoError(t, err)
	require.Len(t, page, 1)
	page, err = store.ListCandidates(t.Context(), "storefront", before, ScanCursor{
		AcceptedAtUnixNano: page[0].AcceptedAtUnixNano,
		SegmentID:          page[0].SegmentID,
	}, 10)
	require.NoError(t, err)
	require.Len(t, page, 1)
	require.Equal(t, "seg-2", page[0].SegmentID)
}

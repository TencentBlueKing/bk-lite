package rumreplayexporter

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"github.com/bk-lite/rum-collector/pkg/rum/replayindex"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/consumer/consumererror"
	"go.opentelemetry.io/collector/exporter/exportertest"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
)

var exporterObservedAt = time.Date(2026, 7, 15, 10, 0, 1, 123000000, time.UTC)

type testStoredEnvelope struct {
	SchemaVersion   int               `json:"schema_version"`
	Application     string            `json:"application"`
	Environment     string            `json:"environment"`
	Release         string            `json:"release"`
	SessionID       string            `json:"session_id"`
	PageID          string            `json:"page_id"`
	RecordingID     string            `json:"recording_id"`
	SegmentID       string            `json:"segment_id"`
	Sequence        int64             `json:"sequence"`
	StartedAt       string            `json:"started_at"`
	EndedAt         string            `json:"ended_at"`
	HasFullSnapshot bool              `json:"has_full_snapshot"`
	EventCount      int               `json:"event_count"`
	ChecksumSHA256  string            `json:"checksum_sha256,omitempty"`
	Events          []json.RawMessage `json:"events"`
}

func TestFactoryAndConfigEnforcePersistentBoundedConsumers(t *testing.T) {
	factory := NewFactory()
	require.Equal(t, "rum_replay", factory.Type().String())
	cfg := factory.CreateDefaultConfig().(*Config)
	require.True(t, cfg.QueueSettings.HasValue())
	queue := cfg.QueueSettings.Get()
	require.Greater(t, queue.NumConsumers, 1)
	require.NotNil(t, queue.StorageID)
	require.Equal(t, "file_storage/rum_replay", queue.StorageID.String())
	require.Equal(t, "redis://rum-replay-exporter:rum-replay-exporter-dev-secret-000003@rum-redis:6379", cfg.RedisURL)
	require.Equal(t, maxReplayQueueAge, cfg.MaxQueueAge)

	cfg.MinIOAccessKey = "access"
	cfg.MinIOSecretKey = "secret"
	require.NoError(t, cfg.Validate())
	storageID := queue.StorageID
	queue.NumConsumers = 0
	require.ErrorContains(t, cfg.Validate(), "at least one consumer")
	queue.NumConsumers = 4
	queue.StorageID = nil
	require.ErrorContains(t, cfg.Validate(), "persistent storage")
	queue.StorageID = storageID
	cfg.MaxQueueAge = maxReplayQueueAge + time.Nanosecond
	require.ErrorContains(t, cfg.Validate(), "at most 336h")
}

func TestFactoryCreatesCollectorLogsExporterWithoutDialingBackends(t *testing.T) {
	factory := NewFactory()
	cfg := factory.CreateDefaultConfig().(*Config)
	cfg.MinIOAccessKey = "access"
	cfg.MinIOSecretKey = "secret"

	created, err := factory.CreateLogs(t.Context(), exportertest.NewNopSettings(factory.Type()), cfg)
	require.NoError(t, err)
	require.NotNil(t, created)
}

func TestExportWritesObjectBeforeReadyIndexGolden(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	exporter := newReplayExporterForTest(objects, indexes)

	require.NoError(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")))
	require.Equal(t, []string{"acquire-sequence", "pending", "object", "renew-sequence", "ready", "release-sequence"}, order)
	require.Len(t, objects.writes, 1, "ready publish must never be followed by a second Ensure")
	require.Len(t, indexes.rows, 2)
	require.Equal(t, "pending", indexes.rows[0].Status)
	require.Equal(t, "ready", indexes.rows[1].Status)
	require.Equal(t, "0123456789abcdef", indexes.rows[1].CredentialLookupID)
	require.Equal(t, "v1", indexes.rows[1].ErasureKeyVersion)
	require.Equal(t, "7a1ec0a93a488672fa688467cca5f726b497ee9b1617d939aed8fa55184d001e", indexes.rows[1].ErasureUserKey)
	require.Equal(t, "0f0e559e116a50807396091832543e48d120a58a63bc305568dd7332b08c7f22", indexes.rows[1].ErasureSessionKey)
	require.Equal(t, uint64(exporterObservedAt.UnixNano()), indexes.rows[1].AcceptedAtUnixNano)
	require.Equal(t, []byte{0x1f, 0x8b}, objects.writes[0].Body[:2])
	require.NotContains(t, objects.writes[0].Key, "tenant-a")
	require.NotContains(t, objects.writes[0].Key, "session-1")
	require.NotContains(t, objects.writes[0].Key, "recording-1")
	require.True(t, strings.HasPrefix(objects.writes[0].Key, "v1/80a707af7dc77ee1228f9127180f3964835e5beb4c4ab0d812f0fe7593579b3a/7a1ec0a93a488672fa688467cca5f726b497ee9b1617d939aed8fa55184d001e/"))

	snapshot := map[string]any{
		"object": map[string]any{
			"bucket":           objects.writes[0].Bucket,
			"key":              objects.writes[0].Key,
			"content_type":     objects.writes[0].ContentType,
			"content_encoding": objects.writes[0].ContentEncoding,
			"metadata":         objects.writes[0].Metadata,
		},
		"index": indexSnapshot(indexes.rows[1]),
	}
	encoded, err := json.Marshal(snapshot)
	require.NoError(t, err)
	want, err := os.ReadFile("testdata/object_index.golden.json")
	require.NoError(t, err)
	require.JSONEq(t, string(want), string(encoded))
}

func TestExportReleasesLeasesWithIndependentBoundedContexts(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	ctx, cancel := context.WithCancel(t.Context())
	indexes.afterEnsure = func(ReplayIndex) { cancel() }
	exporter := newReplayExporterForTest(objects, indexes)

	require.NoError(t, exporter.pushLogs(ctx, validCarrier(t, "original")))
	leases := exporter.leases.(*fakeLeaseStore)
	require.Equal(t, []error{nil}, leases.releaseContextErrors)
	require.Len(t, leases.releaseDeadlines, 1)
	for _, deadline := range leases.releaseDeadlines {
		require.WithinDuration(t, time.Now().Add(2*time.Second), deadline, time.Second)
	}
	require.Empty(t, leases.held)
}

func TestExportAcceptsReceiverCanonicalLiteralHTMLCharacters(t *testing.T) {
	logs := validCarrier(t, "original")
	rewriteCarrierEnvelopeWithCanonicalJSON(t, logs, func(envelope *testStoredEnvelope) {
		envelope.Events = []json.RawMessage{json.RawMessage(
			`{"data":{"node":{"attributes":{"_cssText":".parent>.child{color:red}"}}},"timestamp":123,"type":2}`,
		)}
		envelope.EventCount = len(envelope.Events)
	})
	order := []string{}
	exporter := newReplayExporterForTest(newFakeObjectStore(&order), newFakeIndexStore(&order))

	require.NoError(t, exporter.pushLogs(t.Context(), logs))
}

func TestExportAcceptsAnonymousSessionErasureHashWithoutRawIdentity(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	exporter := newReplayExporterForTest(objects, indexes)
	anonymousUserKey := "f1a9f831e26149c0feaaeec09e371dfbf6a69ea592040f4aa00fe1d4bcc8cc28"

	require.NoError(t, exporter.pushLogs(t.Context(), carrierForIdentity(
		t,
		anonymousUserKey,
		"0f0e559e116a50807396091832543e48d120a58a63bc305568dd7332b08c7f22",
		"session-1",
	)))
	require.Len(t, indexes.rows, 2)
	require.Equal(t, anonymousUserKey, indexes.rows[1].ErasureUserKey)
	require.Contains(t, objects.writes[0].Key, "/"+anonymousUserKey+"/")
	require.NotContains(t, objects.writes[0].Key, "anonymous-session")
}

func TestBarrierCPendingThenObjectFailureTombstonesWithoutGatewayDelete(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	objects.failOnce = errors.New("s3 unavailable")
	indexes := newFakeIndexStore(&order)
	exporter := newReplayExporterForTest(objects, indexes)

	require.ErrorContains(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")), "s3 unavailable")
	require.Equal(t, []string{
		"acquire-sequence", "pending", "object", "tombstone", "release-sequence",
	}, order)
	require.Empty(t, objects.objects)
	for _, state := range indexes.indexes {
		require.Equal(t, "tombstone", state.status)
	}
}

func TestCleanupPendingUsesIndependentBoundedContextAfterParentCancellation(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	ctx, cancel := context.WithCancel(t.Context())
	objects.afterEnsure = func(ObjectWrite) { cancel() }
	exporter := newReplayExporterForTest(objects, indexes)
	exporter.leases.(*fakeLeaseStore).renewErr = errors.New("redis disconnected")

	err := exporter.pushLogs(ctx, validCarrier(t, "original"))
	require.ErrorContains(t, err, "redis disconnected")
	require.Equal(t, []error{nil}, indexes.tombstoneContextErrors)
	require.Len(t, indexes.tombstoneDeadlines, 1)
	require.WithinDuration(t, time.Now().Add(2*time.Second), indexes.tombstoneDeadlines[0], time.Second)
	require.Len(t, objects.objects, 1, "the Maintainer owns orphan object deletion")
	for _, state := range indexes.indexes {
		require.Equal(t, "tombstone", state.status)
	}
}

func TestBarrierFRenewFailureFailsClosedAndLeavesCleanupToMaintainer(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	exporter := newReplayExporterForTest(objects, indexes)
	exporter.leases.(*fakeLeaseStore).renewErr = errors.New("redis disconnected")

	err := exporter.pushLogs(t.Context(), validCarrier(t, "original"))
	require.ErrorContains(t, err, "redis disconnected")
	require.Equal(t, []string{
		"acquire-sequence", "pending", "object", "renew-sequence", "tombstone", "release-sequence",
	}, order)
	require.Len(t, objects.objects, 1)
	for _, state := range indexes.indexes {
		require.Equal(t, "tombstone", state.status)
	}
}

func TestExportAmbiguousReadyPublishRetriesWithoutReensuringObject(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	indexes.failReadyAfterCommit = errors.New("clickhouse response lost")
	exporter := newReplayExporterForTest(objects, indexes)
	carrier := validCarrier(t, "original")

	require.ErrorContains(t, exporter.pushLogs(t.Context(), carrier), "response lost")
	require.NoError(t, exporter.pushLogs(t.Context(), carrier))
	require.Equal(t, []string{
		"acquire-sequence", "pending", "object", "renew-sequence", "ready", "release-sequence",
		"acquire-sequence", "pending", "renew-sequence", "ready", "release-sequence",
	}, order)
	require.Equal(t, EnsureCreated, objects.outcomes[0])
	require.Len(t, objects.outcomes, 1)
	require.Len(t, objects.objects, 1)
	require.Len(t, indexes.indexes, 1)
}

func TestExportNeverReensuresObjectAfterReadyIndex(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	indexes.afterEnsure = func(row ReplayIndex) {
		objects.deleteLogicalPrefix(row.ObjectKey[:strings.LastIndex(row.ObjectKey, row.ChecksumSHA256)])
	}
	exporter := newReplayExporterForTest(objects, indexes)

	require.NoError(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")))
	require.Equal(t, []string{"acquire-sequence", "pending", "object", "renew-sequence", "ready", "release-sequence"}, order)
	require.Len(t, objects.writes, 1)
	require.Empty(t, objects.objects, "an erase after ready must not be resurrected")
}

func TestExportSameChecksumIsIdempotentAndDifferentChecksumConflicts(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	exporter := newReplayExporterForTest(objects, indexes)

	require.NoError(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")))
	require.NoError(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")))
	require.Len(t, objects.objects, 1)
	require.Len(t, indexes.indexes, 1)

	changedIdentity := validCarrier(t, "original")
	changedAttrs := firstRecord(changedIdentity).Attributes()
	changedAttrs.PutStr("rum.erasure.key_version", "v2")
	changedAttrs.PutStr("rum.erasure.user_key", strings.Repeat("a", 64))
	changedAttrs.PutStr("rum.erasure.session_key", strings.Repeat("b", 64))
	err := exporter.pushLogs(t.Context(), changedIdentity)
	require.ErrorIs(t, err, ErrChecksumConflict)
	require.True(t, consumererror.IsPermanent(err))
	require.Len(t, objects.objects, 1, "a ready logical slot cannot change storage or erasure identity")
	require.Len(t, indexes.indexes, 1)

	err = exporter.pushLogs(t.Context(), validCarrier(t, "different"))
	require.ErrorIs(t, err, ErrChecksumConflict)
	require.True(t, consumererror.IsPermanent(err))
	require.Len(t, objects.objects, 1)
	require.Len(t, indexes.indexes, 1)
}

func TestPendingRetryReusesFirstAcceptedAtAcrossFenceObjectAndReady(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	indexes.failReadyOnce = errors.New("ClickHouse unavailable before ready commit")
	exporter := newReplayExporterForTest(objects, indexes)

	require.ErrorContains(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")), "ClickHouse unavailable")
	secondAcceptedAt := exporterObservedAt.Add(time.Hour)
	retry := validCarrier(t, "original")
	record := firstRecord(retry)
	record.SetObservedTimestamp(pcommon.NewTimestampFromTime(secondAcceptedAt))
	record.Attributes().PutInt("rum.accepted_at_unix_nano", secondAcceptedAt.UnixNano())
	require.NoError(t, exporter.pushLogs(t.Context(), retry))

	require.Len(t, objects.writes, 1, "the durable Redis object marker prevents a retry PUT")
	require.Equal(t,
		strconv.FormatInt(exporterObservedAt.UnixNano(), 10),
		objects.writes[len(objects.writes)-1].Metadata["accepted-at-unix-nano"],
	)
	require.Equal(t, uint64(exporterObservedAt.UnixNano()), indexes.rows[len(indexes.rows)-1].AcceptedAtUnixNano)
}

func TestExportDropsExpiredQueueItemBeforeAnyStorageSideEffect(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	exporter := newReplayExporterForTest(objects, indexes)
	exporter.now = func() time.Time { return exporterObservedAt.Add(maxReplayQueueAge) }
	var observed replayAgeDrop
	exporter.observeAgeDrop = func(_ context.Context, drop replayAgeDrop) { observed = drop }

	require.NoError(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")))
	require.Empty(t, order)
	require.Empty(t, objects.writes)
	require.Empty(t, indexes.rows)
	require.Equal(t, replayAgeDrop{Reason: "expired", Count: 1}, observed)
}

func TestPendingRetryCannotResetCanonicalAcceptedAtDeadline(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	indexes.failReadyOnce = errors.New("ClickHouse unavailable before ready commit")
	exporter := newReplayExporterForTest(objects, indexes)
	exporter.now = func() time.Time { return exporterObservedAt.Add(time.Second) }

	require.ErrorContains(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")), "ClickHouse unavailable")
	require.Len(t, objects.objects, 1)

	secondAcceptedAt := exporterObservedAt.Add(time.Hour)
	retry := validCarrier(t, "original")
	record := firstRecord(retry)
	record.SetObservedTimestamp(pcommon.NewTimestampFromTime(secondAcceptedAt))
	record.Attributes().PutInt("rum.accepted_at_unix_nano", secondAcceptedAt.UnixNano())
	exporter.now = func() time.Time { return exporterObservedAt.Add(maxReplayQueueAge) }
	var observed replayAgeDrop
	exporter.observeAgeDrop = func(_ context.Context, drop replayAgeDrop) { observed = drop }

	require.NoError(t, exporter.pushLogs(t.Context(), retry))
	require.Len(t, objects.objects, 1, "expired orphan cleanup belongs to the Maintainer")
	require.Equal(t, "tombstone", indexes.indexes[indexes.rows[0].LogicalKey()].status)
	require.Equal(t, replayAgeDrop{Reason: "expired", Count: 1}, observed)
	for _, row := range indexes.rows {
		require.NotEqual(t, "ready", row.Status)
		require.Equal(t, uint64(exporterObservedAt.UnixNano()), row.AcceptedAtUnixNano)
	}
}

func TestExportRejectsPendingReuseWithChangedErasureIdentity(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	indexes.failReadyOnce = errors.New("ClickHouse unavailable")
	exporter := newReplayExporterForTest(objects, indexes)

	require.ErrorContains(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")), "ClickHouse unavailable")
	require.Len(t, objects.objects, 1)

	retry := validCarrier(t, "original")
	attrs := firstRecord(retry).Attributes()
	attrs.PutStr("rum.erasure.user_key", strings.Repeat("a", 64))
	attrs.PutStr("rum.erasure.session_key", strings.Repeat("b", 64))
	err := exporter.pushLogs(t.Context(), retry)

	require.ErrorIs(t, err, ErrChecksumConflict)
	require.True(t, consumererror.IsPermanent(err))
	require.Len(t, objects.objects, 1, "a logical slot cannot fan out to a second erasure object key")
}

func TestExportRejectsDifferentPayloadAndSegmentIDForSameLogicalSequence(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	exporter := newReplayExporterForTest(objects, indexes)

	require.NoError(t, exporter.pushLogs(t.Context(), validCarrier(t, "original")))
	conflicting := validCarrier(t, "different")
	rewriteCarrierEnvelope(t, conflicting, func(envelope *testStoredEnvelope) {
		envelope.SegmentID = "segment-conflict"
	})

	err := exporter.pushLogs(t.Context(), conflicting)
	require.ErrorIs(t, err, ErrChecksumConflict)
	require.True(t, consumererror.IsPermanent(err))
	require.Len(t, objects.objects, 1, "a conflicting logical sequence must not write a second object")
	require.Len(t, indexes.indexes, 1, "the sequence identity, not segment id, is the index key")
}

func TestExportRejectsUntrustedCarrierBeforeAnyStorageSideEffect(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(plog.Logs)
	}{
		{name: "scope", mutate: func(logs plog.Logs) { logs.ResourceLogs().At(0).ScopeLogs().At(0).Scope().SetName("other") }},
		{name: "tenant", mutate: func(logs plog.Logs) { logs.ResourceLogs().At(0).Resource().Attributes().Remove("tenant.id") }},
		{name: "credential lookup", mutate: func(logs plog.Logs) {
			logs.ResourceLogs().At(0).Resource().Attributes().Remove("rum.credential.lookup_id")
		}},
		{name: "body", mutate: func(logs plog.Logs) {
			logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Body().SetStr("not bytes")
		}},
		{name: "checksum attr", mutate: func(logs plog.Logs) {
			logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().PutStr("rum.replay.checksum_sha256", strings.Repeat("0", 64))
		}},
		{name: "compressed size", mutate: func(logs plog.Logs) {
			logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().PutInt("rum.replay.compressed_bytes", 1)
		}},
		{name: "erasure user key", mutate: func(logs plog.Logs) {
			logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().Remove("rum.erasure.user_key")
		}},
		{name: "erasure session key", mutate: func(logs plog.Logs) {
			logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().Remove("rum.erasure.session_key")
		}},
		{name: "erasure key version", mutate: func(logs plog.Logs) {
			logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().Remove("rum.erasure.key_version")
		}},
		{name: "accepted at", mutate: func(logs plog.Logs) {
			logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0).Attributes().PutInt("rum.accepted_at_unix_nano", 1)
		}},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			order := []string{}
			objects := newFakeObjectStore(&order)
			indexes := newFakeIndexStore(&order)
			exporter := newReplayExporterForTest(objects, indexes)
			logs := validCarrier(t, "original")
			test.mutate(logs)
			err := exporter.pushLogs(t.Context(), logs)
			require.Error(t, err)
			require.True(t, consumererror.IsPermanent(err))
			require.Empty(t, order)
		})
	}
}

func TestExportRejectsNonCanonicalReplayTimestampsBeforeStorage(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	exporter := newReplayExporterForTest(objects, indexes)
	logs := validCarrier(t, "original")
	rewriteCarrierEnvelope(t, logs, func(envelope *testStoredEnvelope) {
		envelope.StartedAt = "2026-07-15T11:59:55+02:00"
		envelope.EndedAt = "2026-07-15T12:00:00+02:00"
	})

	err := exporter.pushLogs(t.Context(), logs)
	require.Error(t, err)
	require.True(t, consumererror.IsPermanent(err))
	require.Empty(t, order)
}

func TestExportAcceptsBrowserISOMillisecondsWithTrailingZero(t *testing.T) {
	order := []string{}
	objects := newFakeObjectStore(&order)
	indexes := newFakeIndexStore(&order)
	exporter := newReplayExporterForTest(objects, indexes)
	logs := validCarrier(t, "original")
	rewriteCarrierEnvelope(t, logs, func(envelope *testStoredEnvelope) {
		envelope.StartedAt = "2026-07-15T09:59:55.090Z"
		envelope.EndedAt = "2026-07-15T10:00:00.100Z"
	})
	firstRecord(logs).SetTimestamp(
		pcommon.NewTimestampFromTime(time.Date(2026, 7, 15, 9, 59, 55, 90_000_000, time.UTC)),
	)

	require.NoError(t, exporter.pushLogs(t.Context(), logs))
	require.Len(t, objects.objects, 1)
	require.Len(t, indexes.indexes, 1)
}

func TestBarrierISameUserIsSerializedAndDifferentUsersRunInParallel(t *testing.T) {
	t.Run("same user", func(t *testing.T) {
		order := []string{}
		objects := newFakeObjectStore(&order)
		indexes := newFakeIndexStore(&order)
		objects.block = make(chan struct{})
		objects.entered = make(chan struct{}, 2)
		exporter := newReplayExporterForTest(objects, indexes)
		firstDone := make(chan error, 1)
		go func() {
			firstDone <- exporter.pushLogs(context.Background(), validCarrier(t, "original"))
		}()
		<-objects.entered

		err := exporter.pushLogs(t.Context(), validCarrier(t, "original"))
		require.ErrorIs(t, err, ErrLeaseUnavailable)
		close(objects.block)
		require.NoError(t, <-firstDone)
		require.Equal(t, int32(1), objects.maxConcurrent.Load())
	})

	t.Run("different users", func(t *testing.T) {
		order := []string{}
		objects := newFakeObjectStore(&order)
		indexes := newFakeIndexStore(&order)
		objects.block = make(chan struct{})
		objects.entered = make(chan struct{}, 2)
		exporter := newReplayExporterForTest(objects, indexes)
		first := validCarrier(t, "original")
		second := carrierForIdentity(
			t,
			strings.Repeat("b", 64),
			strings.Repeat("c", 64),
			"session-2",
		)
		done := make(chan error, 2)
		go func() { done <- exporter.pushLogs(context.Background(), first) }()
		go func() { done <- exporter.pushLogs(context.Background(), second) }()
		<-objects.entered
		<-objects.entered
		require.Equal(t, int32(2), objects.maxConcurrent.Load())
		close(objects.block)
		require.NoError(t, <-done)
		require.NoError(t, <-done)
	})

	t.Run("different users same logical sequence", func(t *testing.T) {
		order := []string{}
		objects := newFakeObjectStore(&order)
		indexes := newFakeIndexStore(&order)
		objects.block = make(chan struct{})
		objects.entered = make(chan struct{}, 2)
		exporter := newReplayExporterForTest(objects, indexes)
		first := validCarrier(t, "original")
		conflicting := validCarrier(t, "different")
		rewriteCarrierEnvelope(t, conflicting, func(envelope *testStoredEnvelope) {
			envelope.SegmentID = "segment-conflict"
		})
		attrs := firstRecord(conflicting).Attributes()
		attrs.PutStr("rum.erasure.user_key", strings.Repeat("b", 64))
		attrs.PutStr("rum.erasure.session_key", strings.Repeat("c", 64))

		firstDone := make(chan error, 1)
		go func() { firstDone <- exporter.pushLogs(context.Background(), first) }()
		<-objects.entered
		err := exporter.pushLogs(t.Context(), conflicting)
		require.ErrorIs(t, err, ErrLeaseUnavailable)
		close(objects.block)
		require.NoError(t, <-firstDone)

		err = exporter.pushLogs(t.Context(), conflicting)
		require.ErrorIs(t, err, ErrChecksumConflict)
		require.True(t, consumererror.IsPermanent(err))
		require.Equal(t, int32(1), objects.maxConcurrent.Load())
		require.Len(t, objects.objects, 1)
		require.Len(t, indexes.indexes, 1)
	})
}

func TestRedisIndexStorePendingReadyTombstone(t *testing.T) {
	server := miniredis.RunT(t)
	store := &redisIndexStore{inner: replayindex.NewStore(redis.NewClient(&redis.Options{Addr: server.Addr()}))}
	row := expectedIndexRow(t, "original")

	_, err := store.BeginPending(t.Context(), row)
	require.NoError(t, err)
	_, err = store.PublishReady(t.Context(), row)
	require.NoError(t, err)
	require.NoError(t, store.Tombstone(t.Context(), row))
}

func TestRedisLeaseOwnsCanonicalIdentityObjectStateAndErasureFence(t *testing.T) {
	server := miniredis.RunT(t)
	store := &redisLeaseStore{client: redis.NewClient(&redis.Options{Addr: server.Addr()})}
	row := expectedIndexRow(t, "original")
	now := time.Now().UTC().Truncate(time.Millisecond)
	row.AcceptedAtUnixNano = uint64(now.UnixNano())
	row.Version = row.AcceptedAtUnixNano

	token, state, err := store.AcquireSequence(t.Context(), row)
	require.NoError(t, err)
	require.Equal(t, row.AcceptedAtUnixNano, state.AcceptedAtUnixNano)
	require.False(t, state.ObjectStored)
	require.NotContains(t, token.Key, row.TenantID)
	require.NotContains(t, token.Key, row.SessionID)
	for _, key := range token.FenceKeys {
		require.Equal(t, int64(1), store.client.ZCount(t.Context(), key, "1", "+inf").Val())
	}

	_, _, err = store.AcquireSequence(t.Context(), row)
	require.ErrorIs(t, err, ErrLeaseUnavailable)
	require.NoError(t, store.MarkObjectStored(t.Context(), token))
	require.NoError(t, store.Release(t.Context(), token))
	for _, key := range token.FenceKeys {
		require.Zero(t, store.client.ZCount(t.Context(), key, "1", "+inf").Val())
	}

	retry := row
	retry.AcceptedAtUnixNano = uint64(now.Add(time.Hour).UnixNano())
	retry.Version = retry.AcceptedAtUnixNano
	retryToken, retryState, err := store.AcquireSequence(t.Context(), retry)
	require.NoError(t, err)
	require.Equal(t, row.AcceptedAtUnixNano, retryState.AcceptedAtUnixNano)
	require.True(t, retryState.ObjectStored)
	require.NoError(t, store.Release(t.Context(), retryToken))

	conflicting := row
	conflicting.ChecksumSHA256 = strings.Repeat("f", 64)
	_, _, err = store.AcquireSequence(t.Context(), conflicting)
	require.ErrorIs(t, err, ErrChecksumConflict)

	require.NoError(t, store.client.ZAdd(
		t.Context(),
		ingress.ErasureFenceKey(row.ErasureKeyVersion, row.ErasureUserKey),
		redis.Z{Score: 0, Member: "fence"},
	).Err())
	_, _, err = store.AcquireSequence(t.Context(), row)
	require.ErrorIs(t, err, ErrErasureFenced)
}

func TestMinIOReuseRejectsDifferentAcceptedAtMetadata(t *testing.T) {
	segment, err := extractReplaySegments(validCarrier(t, "original"))
	require.NoError(t, err)
	write := segment[0].Object
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.Method == http.MethodGet {
			response.Header().Set("Content-Type", "application/xml")
			_, _ = response.Write([]byte(`<?xml version="1.0" encoding="UTF-8"?>` +
				`<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">` +
				`<Name>rum-replay</Name><Prefix>` + write.LogicalPrefix + `</Prefix><KeyCount>1</KeyCount>` +
				`<MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated><Contents><Key>` + write.Key +
				`</Key><Size>` + strconv.Itoa(len(write.Body)) + `</Size></Contents></ListBucketResult>`))
			return
		}
		require.Equal(t, http.MethodHead, request.Method)
		response.Header().Set("Content-Length", strconv.Itoa(len(write.Body)))
		response.Header().Set("Content-Type", write.ContentType)
		response.Header().Set("ETag", `"stored"`)
		response.Header().Set("Last-Modified", "Wed, 15 Jul 2026 10:00:01 GMT")
		response.Header().Set("X-Amz-Meta-Sha256", write.ChecksumSHA256)
		response.Header().Set("X-Amz-Meta-Accepted-At-Unix-Nano", "1")
		response.Header().Set("X-Amz-Meta-Erasure-Key-Version", write.Metadata["erasure-key-version"])
		response.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	cfg := defaultConfig()
	cfg.MinIOEndpoint = strings.TrimPrefix(server.URL, "http://")
	cfg.MinIOAccessKey = "access"
	cfg.MinIOSecretKey = "secret"
	store, err := newMinIOObjectStore(cfg)
	require.NoError(t, err)

	_, err = store.Ensure(t.Context(), write)
	require.ErrorIs(t, err, ErrChecksumConflict)
}

func TestMinIOPutIsConditionalBinaryAndHasNoContentEncoding(t *testing.T) {
	var putHeaders http.Header
	var putBody []byte
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.Method == http.MethodGet && request.URL.Query().Has("location") {
			response.Header().Set("Content-Type", "application/xml")
			_, _ = response.Write([]byte(`<LocationConstraint xmlns="http://s3.amazonaws.com/doc/2006-03-01/"></LocationConstraint>`))
			return
		}
		if request.Method == http.MethodHead {
			response.WriteHeader(http.StatusNotFound)
			return
		}
		require.Equal(t, http.MethodPut, request.Method)
		putHeaders = request.Header.Clone()
		putBody, _ = io.ReadAll(request.Body)
		response.Header().Set("ETag", `"stored"`)
		response.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	cfg := defaultConfig()
	cfg.MinIOEndpoint = strings.TrimPrefix(server.URL, "http://")
	cfg.MinIOAccessKey = "access"
	cfg.MinIOSecretKey = "secret"
	store, err := newMinIOObjectStore(cfg)
	require.NoError(t, err)
	segment, err := extractReplaySegments(validCarrier(t, "original"))
	require.NoError(t, err)
	write := segment[0].Object
	outcome, err := store.Ensure(t.Context(), write)
	require.NoError(t, err)
	require.Equal(t, EnsureCreated, outcome)
	decodedPutBody := putBody
	contentEncoding := strings.ToLower(putHeaders.Get("Content-Encoding"))
	if !bytes.HasPrefix(putBody, []byte{0x1f, 0x8b}) {
		decodedPutBody = decodeAWSChunked(t, putBody)
	}
	require.Equal(t, write.Body, decodedPutBody)
	require.Equal(t, "application/octet-stream", putHeaders.Get("Content-Type"))
	require.NotContains(t, contentEncoding, "gzip")
	require.Equal(t, "*", putHeaders.Get("If-None-Match"))
	require.Equal(t, write.ChecksumSHA256, putHeaders.Get("X-Amz-Meta-Sha256"))
}

func decodeAWSChunked(t testing.TB, raw []byte) []byte {
	t.Helper()
	decoded := make([]byte, 0, len(raw))
	for len(raw) > 0 {
		lineEnd := bytes.Index(raw, []byte("\r\n"))
		require.GreaterOrEqual(t, lineEnd, 0)
		line := string(raw[:lineEnd])
		sizeHex, _, _ := strings.Cut(line, ";")
		size, err := strconv.ParseInt(sizeHex, 16, 64)
		require.NoError(t, err)
		raw = raw[lineEnd+2:]
		if size == 0 {
			return decoded
		}
		require.GreaterOrEqual(t, len(raw), int(size)+2)
		decoded = append(decoded, raw[:size]...)
		require.Equal(t, []byte("\r\n"), raw[size:size+2])
		raw = raw[size+2:]
	}
	t.Fatal("aws-chunked body was missing its terminal zero chunk")
	return nil
}

func FuzzExtractReplaySegments(f *testing.F) {
	seed := carrierNoTest("original")
	marshaler := &plog.ProtoMarshaler{}
	encoded, _ := marshaler.MarshalLogs(seed)
	f.Add(encoded)
	f.Add([]byte("not protobuf"))
	f.Fuzz(func(t *testing.T, data []byte) {
		if len(data) > 1<<20 {
			t.Skip()
		}
		logs, err := (&plog.ProtoUnmarshaler{}).UnmarshalLogs(data)
		if err != nil {
			return
		}
		_, _ = extractReplaySegments(logs)
	})
}

type fakeObjectStore struct {
	mu            sync.Mutex
	order         *[]string
	objects       map[string]string
	writes        []ObjectWrite
	outcomes      []EnsureOutcome
	failOnce      error
	afterEnsure   func(ObjectWrite)
	block         chan struct{}
	entered       chan struct{}
	concurrent    atomic.Int32
	maxConcurrent atomic.Int32
}

var fakeOrderMu sync.Mutex

func appendFakeOrder(order *[]string, entry string) {
	fakeOrderMu.Lock()
	defer fakeOrderMu.Unlock()
	*order = append(*order, entry)
}

func (store *fakeObjectStore) deleteLogicalPrefix(prefix string) {
	store.mu.Lock()
	defer store.mu.Unlock()
	delete(store.objects, prefix)
}

func newFakeObjectStore(order *[]string) *fakeObjectStore {
	return &fakeObjectStore{order: order, objects: map[string]string{}}
}

func (store *fakeObjectStore) Start(context.Context) error    { return nil }
func (store *fakeObjectStore) Shutdown(context.Context) error { return nil }

func (store *fakeObjectStore) Ensure(_ context.Context, write ObjectWrite) (EnsureOutcome, error) {
	current := store.concurrent.Add(1)
	defer store.concurrent.Add(-1)
	for {
		maximum := store.maxConcurrent.Load()
		if current <= maximum || store.maxConcurrent.CompareAndSwap(maximum, current) {
			break
		}
	}
	if store.entered != nil {
		store.entered <- struct{}{}
	}
	if store.block != nil {
		<-store.block
	}

	store.mu.Lock()
	defer store.mu.Unlock()
	appendFakeOrder(store.order, "object")
	store.writes = append(store.writes, write)
	if store.afterEnsure != nil {
		store.afterEnsure(write)
	}
	if store.failOnce != nil {
		err := store.failOnce
		store.failOnce = nil
		return EnsureUnknown, err
	}
	if checksum, ok := store.objects[write.LogicalPrefix]; ok {
		if checksum != write.ChecksumSHA256 {
			return EnsureUnknown, ErrChecksumConflict
		}
		store.outcomes = append(store.outcomes, EnsureReused)
		return EnsureReused, nil
	}
	store.objects[write.LogicalPrefix] = write.ChecksumSHA256
	store.outcomes = append(store.outcomes, EnsureCreated)
	return EnsureCreated, nil
}

type fakeIndexStore struct {
	mu                     sync.Mutex
	order                  *[]string
	indexes                map[string]fakeIndexState
	rows                   []ReplayIndex
	failOnce               error
	failReadyOnce          error
	failReadyAfterCommit   error
	failTombstoneOnce      error
	afterEnsure            func(ReplayIndex)
	tombstoneContextErrors []error
	tombstoneDeadlines     []time.Time
}

type fakeIndexState struct {
	checksum          string
	segment           string
	objectKey         string
	erasureVersion    string
	erasureUserKey    string
	erasureSessionKey string
	acceptedAt        uint64
	status            string
	version           uint64
}

func newFakeIndexStore(order *[]string) *fakeIndexStore {
	return &fakeIndexStore{order: order, indexes: map[string]fakeIndexState{}}
}

func (store *fakeIndexStore) Start(context.Context) error    { return nil }
func (store *fakeIndexStore) Shutdown(context.Context) error { return nil }

func (store *fakeIndexStore) ResolveAcceptedAt(_ context.Context, row ReplayIndex) (uint64, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	state, ok := store.indexes[row.LogicalKey()]
	if !ok {
		return row.AcceptedAtUnixNano, nil
	}
	if !fakeIndexIdentityMatches(state, row) || state.acceptedAt == 0 {
		return 0, ErrChecksumConflict
	}
	return state.acceptedAt, nil
}

func (store *fakeIndexStore) BeginPending(_ context.Context, row ReplayIndex) (EnsureOutcome, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	appendFakeOrder(store.order, "pending")
	if store.failOnce != nil {
		err := store.failOnce
		store.failOnce = nil
		return EnsureUnknown, err
	}
	key := row.LogicalKey()
	if state, ok := store.indexes[key]; ok {
		if !fakeIndexIdentityMatches(state, row) {
			return EnsureUnknown, ErrChecksumConflict
		}
		if state.status == "ready" {
			return EnsureAlreadyReady, nil
		}
		if state.status == "pending" {
			return EnsureReused, nil
		}
		row.AcceptedAtUnixNano = state.acceptedAt
		row.Version = state.version + 1
	}
	row.Status = "pending"
	store.rows = append(store.rows, row)
	store.indexes[key] = fakeIndexStateFromRow(row)
	return EnsureCreated, nil
}

func (store *fakeIndexStore) PublishReady(_ context.Context, row ReplayIndex) (EnsureOutcome, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	appendFakeOrder(store.order, "ready")
	if store.failReadyOnce != nil {
		err := store.failReadyOnce
		store.failReadyOnce = nil
		return EnsureUnknown, err
	}
	key := row.LogicalKey()
	state, ok := store.indexes[key]
	if !ok {
		return EnsureUnknown, errors.New("pending missing")
	}
	if !fakeIndexIdentityMatches(state, row) {
		return EnsureUnknown, ErrChecksumConflict
	}
	if state.acceptedAt != row.AcceptedAtUnixNano {
		return EnsureUnknown, ErrChecksumConflict
	}
	if state.status == "ready" {
		return EnsureReused, nil
	}
	row.Status = "ready"
	if row.Version <= state.version {
		row.Version = state.version + 1
	}
	store.rows = append(store.rows, row)
	store.indexes[key] = fakeIndexStateFromRow(row)
	if store.afterEnsure != nil {
		store.afterEnsure(row)
	}
	if store.failReadyAfterCommit != nil {
		err := store.failReadyAfterCommit
		store.failReadyAfterCommit = nil
		return EnsureUnknown, err
	}
	return EnsureCreated, nil
}

func (store *fakeIndexStore) Tombstone(ctx context.Context, row ReplayIndex) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	appendFakeOrder(store.order, "tombstone")
	store.tombstoneContextErrors = append(store.tombstoneContextErrors, ctx.Err())
	if deadline, ok := ctx.Deadline(); ok {
		store.tombstoneDeadlines = append(store.tombstoneDeadlines, deadline)
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if store.failTombstoneOnce != nil {
		err := store.failTombstoneOnce
		store.failTombstoneOnce = nil
		return err
	}
	key := row.LogicalKey()
	state, ok := store.indexes[key]
	if !ok || state.status == "tombstone" {
		return nil
	}
	if !fakeIndexIdentityMatches(state, row) {
		return ErrChecksumConflict
	}
	if state.acceptedAt != row.AcceptedAtUnixNano {
		return ErrChecksumConflict
	}
	row.Status = "tombstone"
	row.Version = state.version + 1
	store.rows = append(store.rows, row)
	store.indexes[key] = fakeIndexStateFromRow(row)
	return nil
}

func fakeIndexStateFromRow(row ReplayIndex) fakeIndexState {
	return fakeIndexState{
		checksum:          row.ChecksumSHA256,
		segment:           row.SegmentID,
		objectKey:         row.ObjectKey,
		erasureVersion:    row.ErasureKeyVersion,
		erasureUserKey:    row.ErasureUserKey,
		erasureSessionKey: row.ErasureSessionKey,
		acceptedAt:        row.AcceptedAtUnixNano,
		status:            row.Status,
		version:           row.Version,
	}
}

func fakeIndexIdentityMatches(state fakeIndexState, row ReplayIndex) bool {
	return state.checksum == row.ChecksumSHA256 &&
		state.segment == row.SegmentID &&
		state.objectKey == row.ObjectKey &&
		state.erasureVersion == row.ErasureKeyVersion &&
		state.erasureUserKey == row.ErasureUserKey &&
		state.erasureSessionKey == row.ErasureSessionKey
}

type fakeLeaseStore struct {
	mu                   sync.Mutex
	order                *[]string
	held                 map[string]string
	states               map[string]fakeLeaseState
	renewErr             error
	releaseErr           error
	releaseContextErrors []error
	releaseDeadlines     []time.Time
}

type fakeLeaseState struct {
	fingerprint  string
	acceptedAt   uint64
	objectStored bool
}

func newFakeLeaseStore(order *[]string) *fakeLeaseStore {
	return &fakeLeaseStore{
		order:  order,
		held:   map[string]string{},
		states: map[string]fakeLeaseState{},
	}
}

func (store *fakeLeaseStore) Start(context.Context) error    { return nil }
func (store *fakeLeaseStore) Shutdown(context.Context) error { return nil }

func (store *fakeLeaseStore) AcquireSequence(
	_ context.Context,
	row ReplayIndex,
) (leaseToken, leaseState, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	appendFakeOrder(store.order, "acquire-sequence")
	key, err := sequenceLeaseKey(row)
	if err != nil {
		return leaseToken{}, leaseState{}, err
	}
	if _, exists := store.held[key]; exists {
		return leaseToken{}, leaseState{}, ErrLeaseUnavailable
	}
	fingerprint, err := replayIdentityFingerprint(row)
	if err != nil {
		return leaseToken{}, leaseState{}, err
	}
	state, exists := store.states[key]
	if exists && state.fingerprint != fingerprint {
		return leaseToken{}, leaseState{}, ErrChecksumConflict
	}
	if !exists {
		state = fakeLeaseState{fingerprint: fingerprint, acceptedAt: row.AcceptedAtUnixNano}
		store.states[key] = state
	}
	owner := strings.Repeat("a", 64)
	store.held[key] = owner
	return leaseToken{
			Key:   key,
			Owner: owner,
			FenceKeys: []string{
				ingress.ErasureFenceKey(row.ErasureKeyVersion, row.ErasureUserKey),
				ingress.ErasureFenceKey(row.ErasureKeyVersion, row.ErasureSessionKey),
			},
		}, leaseState{
			AcceptedAtUnixNano: state.acceptedAt,
			ObjectStored:       state.objectStored,
		}, nil
}

func (store *fakeLeaseStore) Renew(_ context.Context, token leaseToken) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	appendFakeOrder(store.order, leaseOrderEntry("renew", token))
	if store.renewErr != nil {
		return store.renewErr
	}
	if store.held[token.Key] != token.Owner {
		return ErrLeaseLost
	}
	return nil
}

func (store *fakeLeaseStore) MarkObjectStored(_ context.Context, token leaseToken) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	appendFakeOrder(store.order, leaseOrderEntry("renew", token))
	if store.renewErr != nil {
		return store.renewErr
	}
	if store.held[token.Key] != token.Owner {
		return ErrLeaseLost
	}
	state := store.states[token.Key]
	state.objectStored = true
	store.states[token.Key] = state
	return nil
}

func (store *fakeLeaseStore) ClearObjectStored(_ context.Context, token leaseToken) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.held[token.Key] != token.Owner {
		return ErrLeaseLost
	}
	state := store.states[token.Key]
	state.objectStored = false
	store.states[token.Key] = state
	return nil
}

func (store *fakeLeaseStore) Release(ctx context.Context, token leaseToken) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	appendFakeOrder(store.order, leaseOrderEntry("release", token))
	store.releaseContextErrors = append(store.releaseContextErrors, ctx.Err())
	if deadline, ok := ctx.Deadline(); ok {
		store.releaseDeadlines = append(store.releaseDeadlines, deadline)
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if store.releaseErr != nil {
		return store.releaseErr
	}
	if store.held[token.Key] != token.Owner {
		return ErrLeaseLost
	}
	delete(store.held, token.Key)
	return nil
}

func leaseOrderEntry(operation string, token leaseToken) string {
	if strings.HasPrefix(token.Key, "ops:rum:erase-lock:v1:") {
		return operation + "-erasure"
	}
	return operation + "-sequence"
}

func newReplayExporterForTest(objects ObjectStore, indexes IndexStore) *replayExporter {
	order := objects.(*fakeObjectStore).order
	return &replayExporter{
		objects: objects,
		indexes: indexes,
		leases:  newFakeLeaseStore(order),
		now:     func() time.Time { return exporterObservedAt.Add(time.Minute) },
	}
}

func validCarrier(t testing.TB, variant string) plog.Logs {
	t.Helper()
	logs := carrierNoTest(variant)
	if variant == "original" {
		checksum, _ := firstRecord(logs).Attributes().Get("rum.replay.checksum_sha256")
		require.Equal(t, "7f378c30f2f30f1dd52627544dac502140e558dad584b9ad6df800f34977bdc3", checksum.Str())
	}
	return logs
}

func carrierNoTest(variant string) plog.Logs {
	events := []json.RawMessage{json.RawMessage(`{"data":{"id":1},"timestamp":123,"type":2}`)}
	if variant == "different" {
		events = []json.RawMessage{json.RawMessage(`{"data":{"id":2},"timestamp":123,"type":2}`)}
	}
	envelope := testStoredEnvelope{
		SchemaVersion:   1,
		Application:     "storefront",
		Environment:     "production",
		Release:         "2026.07.15",
		SessionID:       "session-1",
		PageID:          "page-1",
		RecordingID:     "recording-1",
		SegmentID:       "segment-1",
		Sequence:        3,
		StartedAt:       "2026-07-15T09:59:55Z",
		EndedAt:         "2026-07-15T10:00:00Z",
		HasFullSnapshot: true,
		EventCount:      1,
		Events:          events,
	}
	envelope.ChecksumSHA256 = checksumTestEnvelope(envelope)
	uncompressed, _ := json.Marshal(envelope)
	compressed := gzipNoTest(uncompressed)

	logs := plog.NewLogs()
	resourceLogs := logs.ResourceLogs().AppendEmpty()
	resourceLogs.Resource().Attributes().PutStr("tenant.id", "tenant-a")
	resourceLogs.Resource().Attributes().PutStr("rum.credential.lookup_id", "0123456789abcdef")
	scopeLogs := resourceLogs.ScopeLogs().AppendEmpty()
	scopeLogs.Scope().SetName(replayScopeName)
	record := scopeLogs.LogRecords().AppendEmpty()
	record.SetObservedTimestamp(pcommon.NewTimestampFromTime(exporterObservedAt))
	record.SetTimestamp(pcommon.NewTimestampFromTime(time.Date(2026, 7, 15, 9, 59, 55, 0, time.UTC)))
	record.Body().SetEmptyBytes().FromRaw(compressed)
	attrs := record.Attributes()
	attrs.PutInt("rum.replay.schema.version", 1)
	attrs.PutStr("rum.replay.application", envelope.Application)
	attrs.PutStr("rum.replay.environment", envelope.Environment)
	attrs.PutStr("rum.replay.release", envelope.Release)
	attrs.PutStr("rum.replay.session.id", envelope.SessionID)
	attrs.PutStr("rum.replay.session_key", "0123456789abcdef0123456789abcdef")
	attrs.PutStr("rum.replay.page.id", envelope.PageID)
	attrs.PutStr("rum.replay.recording.id", envelope.RecordingID)
	attrs.PutStr("rum.replay.segment.id", envelope.SegmentID)
	attrs.PutInt("rum.replay.sequence", envelope.Sequence)
	attrs.PutStr("rum.replay.started_at", envelope.StartedAt)
	attrs.PutStr("rum.replay.ended_at", envelope.EndedAt)
	attrs.PutBool("rum.replay.has_full_snapshot", envelope.HasFullSnapshot)
	attrs.PutInt("rum.replay.event_count", int64(envelope.EventCount))
	attrs.PutStr("rum.replay.checksum_sha256", envelope.ChecksumSHA256)
	attrs.PutInt("rum.replay.compressed_bytes", int64(len(compressed)))
	attrs.PutInt("rum.replay.uncompressed_bytes", int64(len(uncompressed)))
	attrs.PutInt("rum.accepted_at_unix_nano", exporterObservedAt.UnixNano())
	attrs.PutStr("rum.erasure.key_version", "v1")
	attrs.PutStr("rum.erasure.user_key", "7a1ec0a93a488672fa688467cca5f726b497ee9b1617d939aed8fa55184d001e")
	attrs.PutStr("rum.erasure.session_key", "0f0e559e116a50807396091832543e48d120a58a63bc305568dd7332b08c7f22")
	return logs
}

func checksumTestEnvelope(envelope testStoredEnvelope) string {
	envelope.ChecksumSHA256 = ""
	material, _ := json.Marshal(envelope)
	sum := sha256.Sum256(material)
	return hex.EncodeToString(sum[:])
}

func gzipNoTest(body []byte) []byte {
	var buffer bytes.Buffer
	writer := gzip.NewWriter(&buffer)
	writer.Header.ModTime = time.Time{}
	writer.Header.OS = 255
	_, _ = writer.Write(body)
	_ = writer.Close()
	return buffer.Bytes()
}

func firstRecord(logs plog.Logs) plog.LogRecord {
	return logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
}

func rewriteCarrierEnvelope(t testing.TB, logs plog.Logs, mutate func(*testStoredEnvelope)) {
	t.Helper()
	record := firstRecord(logs)
	reader, err := gzip.NewReader(bytes.NewReader(record.Body().Bytes().AsRaw()))
	require.NoError(t, err)
	uncompressed, err := io.ReadAll(reader)
	require.NoError(t, err)
	require.NoError(t, reader.Close())
	var envelope testStoredEnvelope
	require.NoError(t, json.Unmarshal(uncompressed, &envelope))
	mutate(&envelope)
	envelope.ChecksumSHA256 = checksumTestEnvelope(envelope)
	uncompressed, err = json.Marshal(envelope)
	require.NoError(t, err)
	compressed := gzipNoTest(uncompressed)
	record.Body().SetEmptyBytes().FromRaw(compressed)
	attrs := record.Attributes()
	attrs.PutStr("rum.replay.application", envelope.Application)
	attrs.PutStr("rum.replay.environment", envelope.Environment)
	attrs.PutStr("rum.replay.release", envelope.Release)
	attrs.PutStr("rum.replay.session.id", envelope.SessionID)
	attrs.PutStr("rum.replay.page.id", envelope.PageID)
	attrs.PutStr("rum.replay.recording.id", envelope.RecordingID)
	attrs.PutStr("rum.replay.segment.id", envelope.SegmentID)
	attrs.PutInt("rum.replay.sequence", envelope.Sequence)
	attrs.PutInt("rum.replay.event_count", int64(envelope.EventCount))
	attrs.PutBool("rum.replay.has_full_snapshot", envelope.HasFullSnapshot)
	attrs.PutStr("rum.replay.started_at", envelope.StartedAt)
	attrs.PutStr("rum.replay.ended_at", envelope.EndedAt)
	attrs.PutStr("rum.replay.checksum_sha256", envelope.ChecksumSHA256)
	attrs.PutInt("rum.replay.compressed_bytes", int64(len(compressed)))
	attrs.PutInt("rum.replay.uncompressed_bytes", int64(len(uncompressed)))
}

func rewriteCarrierEnvelopeWithCanonicalJSON(
	t testing.TB,
	logs plog.Logs,
	mutate func(*testStoredEnvelope),
) {
	t.Helper()
	record := firstRecord(logs)
	reader, err := gzip.NewReader(bytes.NewReader(record.Body().Bytes().AsRaw()))
	require.NoError(t, err)
	uncompressed, err := io.ReadAll(reader)
	require.NoError(t, err)
	require.NoError(t, reader.Close())
	var envelope testStoredEnvelope
	require.NoError(t, json.Unmarshal(uncompressed, &envelope))
	mutate(&envelope)
	envelope.ChecksumSHA256 = ""
	material, err := marshalTestCanonicalJSON(envelope)
	require.NoError(t, err)
	sum := sha256.Sum256(material)
	envelope.ChecksumSHA256 = hex.EncodeToString(sum[:])
	uncompressed, err = marshalTestCanonicalJSON(envelope)
	require.NoError(t, err)
	compressed := gzipNoTest(uncompressed)
	record.Body().SetEmptyBytes().FromRaw(compressed)
	attrs := record.Attributes()
	attrs.PutInt("rum.replay.event_count", int64(envelope.EventCount))
	attrs.PutStr("rum.replay.checksum_sha256", envelope.ChecksumSHA256)
	attrs.PutInt("rum.replay.compressed_bytes", int64(len(compressed)))
	attrs.PutInt("rum.replay.uncompressed_bytes", int64(len(uncompressed)))
}

func marshalTestCanonicalJSON(value any) ([]byte, error) {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(buffer.Bytes(), []byte("\n")), nil
}

func carrierForIdentity(t testing.TB, userKey, sessionKey, sessionID string) plog.Logs {
	t.Helper()
	logs := validCarrier(t, "original")
	rewriteCarrierEnvelope(t, logs, func(envelope *testStoredEnvelope) {
		envelope.SessionID = sessionID
		envelope.RecordingID = "recording-" + sessionID
	})
	attrs := firstRecord(logs).Attributes()
	attrs.PutStr("rum.erasure.user_key", userKey)
	attrs.PutStr("rum.erasure.session_key", sessionKey)
	return logs
}

func expectedIndexRow(t testing.TB, variant string) ReplayIndex {
	t.Helper()
	segments, err := extractReplaySegments(validCarrier(t, variant))
	require.NoError(t, err)
	require.Len(t, segments, 1)
	return segments[0].Index
}

func indexSnapshot(row ReplayIndex) map[string]any {
	return map[string]any{
		"tenant_id":          row.TenantID,
		"CredentialLookupId": row.CredentialLookupID,
		"Application":        row.Application,
		"Environment":        row.Environment,
		"Release":            row.Release,
		"SessionId":          row.SessionID,
		"SessionKey":         row.SessionKey,
		"PageId":             row.PageID,
		"RecordingId":        row.RecordingID,
		"SegmentId":          row.SegmentID,
		"Sequence":           row.Sequence,
		"EventCount":         row.EventCount,
		"HasFullSnapshot":    row.HasFullSnapshot,
		"ChecksumSHA256":     row.ChecksumSHA256,
		"ObjectKey":          row.ObjectKey,
		"Status":             row.Status,
		"ErasureKeyVersion":  row.ErasureKeyVersion,
		"ErasureUserKey":     row.ErasureUserKey,
		"ErasureSessionKey":  row.ErasureSessionKey,
		"AcceptedAtUnixNano": row.AcceptedAtUnixNano,
	}
}

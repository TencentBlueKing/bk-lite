package rumgate

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/pdata/plog/plogotlp"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.opentelemetry.io/collector/pdata/ptrace/ptraceotlp"
)

var firstAcceptedAt = time.Date(2026, 7, 15, 10, 0, 0, 123_000_000, time.UTC)

func TestLogsAbsoluteDeadlineSurvivesRepeatedQueueSerialization(t *testing.T) {
	beforeDeadline := roundTripLogs(t, roundTripLogs(t, logsAt(firstAcceptedAt)))
	result := filterLogsByAcceptedAt(beforeDeadline, firstAcceptedAt.Add(MaxPersistentQueueAge-time.Nanosecond))
	require.Equal(t, ageFilterResult{Kept: 1}, result)
	require.Equal(t, 1, beforeDeadline.LogRecordCount())

	atDeadline := roundTripLogs(t, roundTripLogs(t, logsAt(firstAcceptedAt)))
	result = filterLogsByAcceptedAt(atDeadline, firstAcceptedAt.Add(MaxPersistentQueueAge))
	require.Equal(t, ageFilterResult{Expired: 1}, result)
	require.Zero(t, atDeadline.LogRecordCount())
}

func TestTracesAbsoluteDeadlineSurvivesRepeatedQueueSerialization(t *testing.T) {
	beforeDeadline := roundTripTraces(t, roundTripTraces(t, tracesAt(firstAcceptedAt)))
	result := filterTracesByAcceptedAt(beforeDeadline, firstAcceptedAt.Add(MaxPersistentQueueAge-time.Nanosecond))
	require.Equal(t, ageFilterResult{Kept: 1}, result)
	require.Equal(t, 1, beforeDeadline.SpanCount())

	atDeadline := roundTripTraces(t, roundTripTraces(t, tracesAt(firstAcceptedAt)))
	result = filterTracesByAcceptedAt(atDeadline, firstAcceptedAt.Add(MaxPersistentQueueAge))
	require.Equal(t, ageFilterResult{Expired: 1}, result)
	require.Zero(t, atDeadline.SpanCount())
}

func TestAgeGateFailsClosedWhenAcceptedAtIsMissingOrInvalid(t *testing.T) {
	logs := logsAt(firstAcceptedAt)
	record := logs.ResourceLogs().At(0).ScopeLogs().At(0).LogRecords().At(0)
	record.Attributes().Remove(acceptedAtAttribute)
	require.Equal(t, ageFilterResult{Invalid: 1}, filterLogsByAcceptedAt(logs, firstAcceptedAt))
	require.Zero(t, logs.LogRecordCount())

	traces := tracesAt(firstAcceptedAt)
	span := traces.ResourceSpans().At(0).ScopeSpans().At(0).Spans().At(0)
	span.Attributes().PutStr(acceptedAtAttribute, "not-an-integer")
	require.Equal(t, ageFilterResult{Invalid: 1}, filterTracesByAcceptedAt(traces, firstAcceptedAt))
	require.Zero(t, traces.SpanCount())
}

func TestLogsGateForwardsOnlyLiveItemsAndReportsLowCardinalityDrops(t *testing.T) {
	now := firstAcceptedAt.Add(MaxPersistentQueueAge)
	logs := plog.NewLogs()
	records := logs.ResourceLogs().AppendEmpty().ScopeLogs().AppendEmpty().LogRecords()
	records.AppendEmpty().Attributes().PutInt(acceptedAtAttribute, firstAcceptedAt.UnixNano())
	records.AppendEmpty().Attributes().PutInt(acceptedAtAttribute, now.Add(-time.Hour).UnixNano())
	records.AppendEmpty()
	next := &capturingLogsConsumer{}
	var observedSignal string
	var observed ageFilterResult
	gate := LogsAgeGate{
		next:   next,
		fences: &fakeFenceManager{},
		now:    func() time.Time { return now },
		maxAge: MaxPersistentQueueAge,
		observe: func(_ context.Context, signal string, result ageFilterResult) {
			observedSignal, observed = signal, result
		},
	}

	require.NoError(t, gate.PushLogs(t.Context(), logs))
	require.Equal(t, 1, next.calls)
	require.Equal(t, 1, next.last.LogRecordCount())
	require.Equal(t, "logs", observedSignal)
	require.Equal(t, ageFilterResult{Kept: 1, Expired: 1, Invalid: 1}, observed)
}

func TestTracesGateDoesNotCallDownstreamWhenEverySpanExpired(t *testing.T) {
	next := &capturingTracesConsumer{}
	var observed ageFilterResult
	gate := TracesAgeGate{
		next:   next,
		fences: &fakeFenceManager{},
		now:    func() time.Time { return firstAcceptedAt.Add(MaxPersistentQueueAge) },
		maxAge: MaxPersistentQueueAge,
		observe: func(_ context.Context, signal string, result ageFilterResult) {
			require.Equal(t, "traces", signal)
			observed = result
		},
	}

	require.NoError(t, gate.PushTraces(t.Context(), tracesAt(firstAcceptedAt)))
	require.Zero(t, next.calls)
	require.Equal(t, ageFilterResult{Expired: 1}, observed)
}

func TestLogsGateDropsFencedIdentityAndKeepsUnrelatedTelemetry(t *testing.T) {
	now := firstAcceptedAt.Add(time.Minute)
	logs := plog.NewLogs()
	records := logs.ResourceLogs().AppendEmpty().ScopeLogs().AppendEmpty().LogRecords()
	fenced := records.AppendEmpty()
	addFenceAttributes(fenced.Attributes(), strings.Repeat("a", 64), strings.Repeat("b", 64))
	fenced.Attributes().PutInt(acceptedAtAttribute, firstAcceptedAt.UnixNano())
	allowed := records.AppendEmpty()
	addFenceAttributes(allowed.Attributes(), strings.Repeat("c", 64), strings.Repeat("d", 64))
	allowed.Attributes().PutInt(acceptedAtAttribute, firstAcceptedAt.UnixNano())
	next := &capturingLogsConsumer{}
	manager := &fakeFenceManager{fencedDigest: strings.Repeat("a", 64)}
	var observed ageFilterResult
	gate := LogsAgeGate{
		next: next, fences: manager, now: func() time.Time { return now }, maxAge: MaxPersistentQueueAge,
		observe: func(_ context.Context, _ string, result ageFilterResult) { observed = result },
	}

	require.NoError(t, gate.PushLogs(t.Context(), logs))
	require.Equal(t, 1, next.last.LogRecordCount())
	require.Equal(t, ageFilterResult{Kept: 1, Fenced: 1}, observed)
	require.Equal(t, 1, manager.releases)
}

type capturingLogsConsumer struct {
	calls int
	last  plog.Logs
}

func (*capturingLogsConsumer) Capabilities() consumer.Capabilities {
	return consumer.Capabilities{MutatesData: false}
}

func (consumer *capturingLogsConsumer) ConsumeLogs(_ context.Context, logs plog.Logs) error {
	consumer.calls++
	consumer.last = logs
	return nil
}

type capturingTracesConsumer struct {
	calls int
}

func (*capturingTracesConsumer) Capabilities() consumer.Capabilities {
	return consumer.Capabilities{MutatesData: false}
}

func (consumer *capturingTracesConsumer) ConsumeTraces(context.Context, ptrace.Traces) error {
	consumer.calls++
	return nil
}

func logsAt(acceptedAt time.Time) plog.Logs {
	logs := plog.NewLogs()
	record := logs.ResourceLogs().AppendEmpty().ScopeLogs().AppendEmpty().LogRecords().AppendEmpty()
	record.Attributes().PutInt(acceptedAtAttribute, acceptedAt.UnixNano())
	return logs
}

func tracesAt(acceptedAt time.Time) ptrace.Traces {
	traces := ptrace.NewTraces()
	span := traces.ResourceSpans().AppendEmpty().ScopeSpans().AppendEmpty().Spans().AppendEmpty()
	span.Attributes().PutInt(acceptedAtAttribute, acceptedAt.UnixNano())
	return traces
}

func roundTripLogs(t *testing.T, logs plog.Logs) plog.Logs {
	t.Helper()
	wire, err := plogotlp.NewExportRequestFromLogs(logs).MarshalProto()
	require.NoError(t, err)
	request := plogotlp.NewExportRequest()
	require.NoError(t, request.UnmarshalProto(wire))
	return request.Logs()
}

func roundTripTraces(t *testing.T, traces ptrace.Traces) ptrace.Traces {
	t.Helper()
	wire, err := ptraceotlp.NewExportRequestFromTraces(traces).MarshalProto()
	require.NoError(t, err)
	request := ptraceotlp.NewExportRequest()
	require.NoError(t, request.UnmarshalProto(wire))
	return request.Traces()
}

type fakeFenceManager struct {
	fencedDigest string
	releases     int
}

func (*fakeFenceManager) Start(context.Context) error    { return nil }
func (*fakeFenceManager) Shutdown(context.Context) error { return nil }

func (manager *fakeFenceManager) Acquire(
	_ context.Context,
	identities []ingress.FenceIdentity,
) (ingress.LeaseHandle, error) {
	for _, identity := range identities {
		if identity.Digest == manager.fencedDigest {
			return nil, ingress.ErrErasureFenced
		}
	}
	return fakeFenceLease{release: func() { manager.releases++ }}, nil
}

type fakeFenceLease struct {
	release func()
}

func (lease fakeFenceLease) Release(context.Context) error {
	if lease.release == nil {
		return errors.New("missing release callback")
	}
	lease.release()
	return nil
}

func addFenceAttributes(attrs pcommon.Map, user, session string) {
	attrs.PutStr(erasureVersionAttribute, "v1")
	attrs.PutStr(erasureUserAttribute, user)
	attrs.PutStr(erasureSessionAttribute, session)
}

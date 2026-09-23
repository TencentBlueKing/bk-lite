package rumgate

import (
	"context"
	"errors"
	"regexp"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.uber.org/zap"
)

const (
	erasureVersionAttribute = "rum.erasure.key_version"
	erasureUserAttribute    = "rum.erasure.user_key"
	erasureSessionAttribute = "rum.erasure.session_key"
	fenceReleaseTimeout     = 2 * time.Second
)

var (
	erasureVersionPattern = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,32}$`)
	erasureDigestPattern  = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

// AgeFilterObserver records queue-age drops.
type AgeFilterObserver func(context.Context, string, ageFilterResult)

// LogsAgeGate applies the shared RUM age/fence/marker gate to logs.
type LogsAgeGate struct {
	next    consumer.Logs
	fences  ingress.LeaseManager
	marker  StoredMarker
	logger  *zap.Logger
	now     func() time.Time
	maxAge  time.Duration
	observe AgeFilterObserver
}

// NewLogsAgeGate wires the shared logs gate.
func NewLogsAgeGate(
	next consumer.Logs,
	fences ingress.LeaseManager,
	marker StoredMarker,
	logger *zap.Logger,
	now func() time.Time,
	maxAge time.Duration,
	observe AgeFilterObserver,
) *LogsAgeGate {
	return &LogsAgeGate{
		next: next, fences: fences, marker: marker, logger: logger, now: now, maxAge: maxAge, observe: observe,
	}
}

func (gate *LogsAgeGate) Start(ctx context.Context, host component.Host) error {
	if gate.fences == nil {
		return errors.New("RUM logs gate requires erasure fence leases")
	}
	if gate.marker != nil {
		if err := gate.marker.Start(ctx); err != nil {
			return err
		}
	}
	if err := gate.fences.Start(ctx); err != nil {
		return err
	}
	if err := gate.next.(component.Component).Start(ctx, host); err != nil {
		_ = gate.fences.Shutdown(ctx)
		return err
	}
	return nil
}

func (gate *LogsAgeGate) Shutdown(ctx context.Context) error {
	var shutdownErr error
	if gate.marker != nil {
		shutdownErr = errors.Join(shutdownErr, gate.marker.Shutdown(ctx))
	}
	return errors.Join(
		shutdownErr,
		gate.next.(component.Component).Shutdown(ctx),
		gate.fences.Shutdown(ctx),
	)
}

func (gate *LogsAgeGate) PushLogs(ctx context.Context, logs plog.Logs) (resultErr error) {
	result := filterLogsByAcceptedAtWithMaxAge(logs, gate.now(), gate.maxAge)
	leases, err := gate.acquireLogLeases(ctx, logs, &result)
	if err != nil {
		return err
	}
	defer func() {
		resultErr = errors.Join(resultErr, releaseFenceLeases(ctx, leases))
	}()
	gate.observeResult(ctx, "logs", result)
	if result.Kept == 0 {
		return nil
	}
	if err := gate.next.ConsumeLogs(ctx, logs); err != nil {
		return err
	}
	if gate.marker != nil {
		gate.marker.Record(ctx, applicationsFromLogs(logs))
	}
	return nil
}

func (gate *LogsAgeGate) acquireLogLeases(
	ctx context.Context,
	logs plog.Logs,
	result *ageFilterResult,
) ([]ingress.LeaseHandle, error) {
	if gate.fences == nil {
		return nil, errors.New("RUM logs gate requires erasure fence leases")
	}
	var leases []ingress.LeaseHandle
	var acquireErr error
	resources := logs.ResourceLogs()
	for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
		scopes := resources.At(resourceIndex).ScopeLogs()
		for scopeIndex := 0; scopeIndex < scopes.Len(); scopeIndex++ {
			records := scopes.At(scopeIndex).LogRecords()
			records.RemoveIf(func(record plog.LogRecord) bool {
				if acquireErr != nil {
					return false
				}
				lease, state, err := gate.acquireAttributes(ctx, record.Attributes())
				switch {
				case err != nil:
					acquireErr = err
					return false
				case state == fenceInvalid:
					result.Invalid++
					result.Kept--
					return true
				case state == fenceRejected:
					result.Fenced++
					result.Kept--
					return true
				case lease != nil:
					leases = append(leases, lease)
				}
				return false
			})
		}
		scopes.RemoveIf(func(scope plog.ScopeLogs) bool { return scope.LogRecords().Len() == 0 })
	}
	resources.RemoveIf(func(resource plog.ResourceLogs) bool { return resource.ScopeLogs().Len() == 0 })
	if acquireErr != nil {
		return nil, errors.Join(acquireErr, releaseFenceLeases(ctx, leases))
	}
	return leases, nil
}

// TracesAgeGate applies the shared RUM age/fence/marker gate to traces.
type TracesAgeGate struct {
	next    consumer.Traces
	fences  ingress.LeaseManager
	marker  StoredMarker
	logger  *zap.Logger
	now     func() time.Time
	maxAge  time.Duration
	observe AgeFilterObserver
}

// NewTracesAgeGate wires the shared traces gate.
func NewTracesAgeGate(
	next consumer.Traces,
	fences ingress.LeaseManager,
	marker StoredMarker,
	logger *zap.Logger,
	now func() time.Time,
	maxAge time.Duration,
	observe AgeFilterObserver,
) *TracesAgeGate {
	return &TracesAgeGate{
		next: next, fences: fences, marker: marker, logger: logger, now: now, maxAge: maxAge, observe: observe,
	}
}

func (gate *TracesAgeGate) Start(ctx context.Context, host component.Host) error {
	if gate.fences == nil {
		return errors.New("RUM traces gate requires erasure fence leases")
	}
	if gate.marker != nil {
		if err := gate.marker.Start(ctx); err != nil {
			return err
		}
	}
	if err := gate.fences.Start(ctx); err != nil {
		return err
	}
	if err := gate.next.(component.Component).Start(ctx, host); err != nil {
		_ = gate.fences.Shutdown(ctx)
		return err
	}
	return nil
}

func (gate *TracesAgeGate) Shutdown(ctx context.Context) error {
	var shutdownErr error
	if gate.marker != nil {
		shutdownErr = errors.Join(shutdownErr, gate.marker.Shutdown(ctx))
	}
	return errors.Join(
		shutdownErr,
		gate.next.(component.Component).Shutdown(ctx),
		gate.fences.Shutdown(ctx),
	)
}

func (gate *TracesAgeGate) PushTraces(ctx context.Context, traces ptrace.Traces) (resultErr error) {
	result := filterTracesByAcceptedAtWithMaxAge(traces, gate.now(), gate.maxAge)
	leases, err := gate.acquireTraceLeases(ctx, traces, &result)
	if err != nil {
		return err
	}
	defer func() {
		resultErr = errors.Join(resultErr, releaseFenceLeases(ctx, leases))
	}()
	gate.observeResult(ctx, "traces", result)
	if result.Kept == 0 {
		return nil
	}
	if err := gate.next.ConsumeTraces(ctx, traces); err != nil {
		return err
	}
	if gate.marker != nil {
		gate.marker.Record(ctx, applicationsFromTraces(traces))
	}
	return nil
}

func (gate *TracesAgeGate) acquireTraceLeases(
	ctx context.Context,
	traces ptrace.Traces,
	result *ageFilterResult,
) ([]ingress.LeaseHandle, error) {
	if gate.fences == nil {
		return nil, errors.New("RUM traces gate requires erasure fence leases")
	}
	var leases []ingress.LeaseHandle
	var acquireErr error
	resources := traces.ResourceSpans()
	for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
		scopes := resources.At(resourceIndex).ScopeSpans()
		for scopeIndex := 0; scopeIndex < scopes.Len(); scopeIndex++ {
			spans := scopes.At(scopeIndex).Spans()
			spans.RemoveIf(func(span ptrace.Span) bool {
				if acquireErr != nil {
					return false
				}
				lease, state, err := gate.acquireAttributes(ctx, span.Attributes())
				switch {
				case err != nil:
					acquireErr = err
					return false
				case state == fenceInvalid:
					result.Invalid++
					result.Kept--
					return true
				case state == fenceRejected:
					result.Fenced++
					result.Kept--
					return true
				case lease != nil:
					leases = append(leases, lease)
				}
				return false
			})
		}
		scopes.RemoveIf(func(scope ptrace.ScopeSpans) bool { return scope.Spans().Len() == 0 })
	}
	resources.RemoveIf(func(resource ptrace.ResourceSpans) bool { return resource.ScopeSpans().Len() == 0 })
	if acquireErr != nil {
		return nil, errors.Join(acquireErr, releaseFenceLeases(ctx, leases))
	}
	return leases, nil
}

type fenceDisposition uint8

const (
	fenceAllowed fenceDisposition = iota
	fenceRejected
	fenceInvalid
)

func (gate *LogsAgeGate) acquireAttributes(
	ctx context.Context,
	attrs pcommon.Map,
) (ingress.LeaseHandle, fenceDisposition, error) {
	return acquireAttributeLease(ctx, gate.fences, attrs)
}

func (gate *TracesAgeGate) acquireAttributes(
	ctx context.Context,
	attrs pcommon.Map,
) (ingress.LeaseHandle, fenceDisposition, error) {
	return acquireAttributeLease(ctx, gate.fences, attrs)
}

func acquireAttributeLease(
	ctx context.Context,
	manager ingress.LeaseManager,
	attrs pcommon.Map,
) (ingress.LeaseHandle, fenceDisposition, error) {
	version, versionOK := stringAttribute(attrs, erasureVersionAttribute)
	user, userOK := stringAttribute(attrs, erasureUserAttribute)
	session, sessionOK := stringAttribute(attrs, erasureSessionAttribute)
	if !versionOK && !userOK && !sessionOK {
		return nil, fenceAllowed, nil
	}
	if !versionOK ||
		!userOK ||
		!sessionOK ||
		!erasureVersionPattern.MatchString(version) ||
		!erasureDigestPattern.MatchString(user) ||
		!erasureDigestPattern.MatchString(session) {
		return nil, fenceInvalid, nil
	}
	lease, err := manager.Acquire(ctx, []ingress.FenceIdentity{
		{Version: version, Digest: user},
		{Version: version, Digest: session},
	})
	if errors.Is(err, ingress.ErrErasureFenced) {
		return nil, fenceRejected, nil
	}
	if err != nil {
		return nil, fenceAllowed, err
	}
	return lease, fenceAllowed, nil
}

func stringAttribute(attrs pcommon.Map, name string) (string, bool) {
	value, ok := attrs.Get(name)
	if !ok || value.Type() != pcommon.ValueTypeStr || value.Str() == "" {
		return "", false
	}
	return value.Str(), true
}

func releaseFenceLeases(parent context.Context, leases []ingress.LeaseHandle) error {
	if len(leases) == 0 {
		return nil
	}
	ctx, cancel := context.WithTimeout(context.WithoutCancel(parent), fenceReleaseTimeout)
	defer cancel()
	var result error
	for _, lease := range leases {
		result = errors.Join(result, lease.Release(ctx))
	}
	return result
}

func (gate *LogsAgeGate) observeResult(ctx context.Context, signal string, result ageFilterResult) {
	if gate.observe != nil && (result.Expired > 0 || result.Invalid > 0 || result.Fenced > 0) {
		gate.observe(ctx, signal, result)
	}
}

func (gate *TracesAgeGate) observeResult(ctx context.Context, signal string, result ageFilterResult) {
	if gate.observe != nil && (result.Expired > 0 || result.Invalid > 0 || result.Fenced > 0) {
		gate.observe(ctx, signal, result)
	}
}

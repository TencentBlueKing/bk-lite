package rumgate

import (
	"time"

	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/pdata/ptrace"
)

const (
	acceptedAtAttribute   = "rum.accepted_at_unix_nano"
	MaxPersistentQueueAge = 14 * 24 * time.Hour
)

type ageFilterResult struct {
	Kept    int
	Expired int
	Invalid int
	Fenced  int
}

func filterLogsByAcceptedAt(logs plog.Logs, now time.Time) ageFilterResult {
	return filterLogsByAcceptedAtWithMaxAge(logs, now, MaxPersistentQueueAge)
}

func filterLogsByAcceptedAtWithMaxAge(logs plog.Logs, now time.Time, maxAge time.Duration) ageFilterResult {
	result := ageFilterResult{}
	resources := logs.ResourceLogs()
	for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
		scopes := resources.At(resourceIndex).ScopeLogs()
		for scopeIndex := 0; scopeIndex < scopes.Len(); scopeIndex++ {
			records := scopes.At(scopeIndex).LogRecords()
			records.RemoveIf(func(record plog.LogRecord) bool {
				state := acceptedAtState(record.Attributes(), now, maxAge)
				result.add(state)
				return state != acceptedAtKept
			})
		}
		scopes.RemoveIf(func(scope plog.ScopeLogs) bool { return scope.LogRecords().Len() == 0 })
	}
	resources.RemoveIf(func(resource plog.ResourceLogs) bool { return resource.ScopeLogs().Len() == 0 })
	return result
}

func filterTracesByAcceptedAt(traces ptrace.Traces, now time.Time) ageFilterResult {
	return filterTracesByAcceptedAtWithMaxAge(traces, now, MaxPersistentQueueAge)
}

func filterTracesByAcceptedAtWithMaxAge(traces ptrace.Traces, now time.Time, maxAge time.Duration) ageFilterResult {
	result := ageFilterResult{}
	resources := traces.ResourceSpans()
	for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
		scopes := resources.At(resourceIndex).ScopeSpans()
		for scopeIndex := 0; scopeIndex < scopes.Len(); scopeIndex++ {
			spans := scopes.At(scopeIndex).Spans()
			spans.RemoveIf(func(span ptrace.Span) bool {
				state := acceptedAtState(span.Attributes(), now, maxAge)
				result.add(state)
				return state != acceptedAtKept
			})
		}
		scopes.RemoveIf(func(scope ptrace.ScopeSpans) bool { return scope.Spans().Len() == 0 })
	}
	resources.RemoveIf(func(resource ptrace.ResourceSpans) bool { return resource.ScopeSpans().Len() == 0 })
	return result
}

type acceptedAtDisposition uint8

const (
	acceptedAtKept acceptedAtDisposition = iota
	acceptedAtExpired
	acceptedAtInvalid
)

func acceptedAtState(attrs pcommon.Map, now time.Time, maxAge time.Duration) acceptedAtDisposition {
	value, ok := attrs.Get(acceptedAtAttribute)
	if !ok || value.Type() != pcommon.ValueTypeInt || value.Int() <= 0 || maxAge <= 0 {
		return acceptedAtInvalid
	}
	deadline := time.Unix(0, value.Int()).UTC().Add(maxAge)
	if !now.UTC().Before(deadline) {
		return acceptedAtExpired
	}
	return acceptedAtKept
}

func (result *ageFilterResult) add(state acceptedAtDisposition) {
	switch state {
	case acceptedAtKept:
		result.Kept++
	case acceptedAtExpired:
		result.Expired++
	case acceptedAtInvalid:
		result.Invalid++
	}
}

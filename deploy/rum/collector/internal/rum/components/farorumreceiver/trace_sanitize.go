package farorumreceiver

import (
	"regexp"
	"strings"

	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/ptrace"
)

const (
	maxTraceResourceSpans     = 64
	maxTraceScopeSpans        = 128
	maxTraceResourceAttrs     = 64
	maxTraceScopeAttrs        = 32
	maxTraceAttributesPerSpan = 64
	maxTraceEventsPerSpan     = 32
	maxTraceLinksPerSpan      = 32
	traceScopeName            = "weops.rum.faro.tracing"
)

var (
	safeTraceValuePattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$`)
)

var traceStringAttributes = map[string]struct{}{
	"component":                {},
	"error.type":               {},
	"http.flavor":              {},
	"network.protocol.name":    {},
	"network.protocol.version": {},
}

var traceNumericAttributes = map[string]struct{}{
	"http.request.body.size":    {},
	"http.response.body.size":   {},
	"http.response.status_code": {},
	"http.status_code":          {},
	"server.port":               {},
}

type safeTraceAttribute struct {
	key       string
	valueType pcommon.ValueType
	stringVal string
	intVal    int64
	doubleVal float64
	boolVal   bool
}

func sanitizeTraceData(traces ptrace.Traces, cfg *Config) error {
	resourceSpans := traces.ResourceSpans()
	if resourceSpans.Len() > maxTraceResourceSpans {
		return ErrPayloadTooLarge
	}
	totalScopes := 0
	totalAuxItems := 0
	for resourceIndex := 0; resourceIndex < resourceSpans.Len(); resourceIndex++ {
		resourceSpan := resourceSpans.At(resourceIndex)
		if resourceSpan.Resource().Attributes().Len() > maxTraceResourceAttrs {
			return ErrPayloadTooLarge
		}
		resourceSpan.Resource().Attributes().Clear()
		resourceSpan.SetSchemaUrl("")

		scopeSpans := resourceSpan.ScopeSpans()
		totalScopes += scopeSpans.Len()
		if totalScopes > maxTraceScopeSpans {
			return ErrPayloadTooLarge
		}
		for scopeIndex := 0; scopeIndex < scopeSpans.Len(); scopeIndex++ {
			scopeSpan := scopeSpans.At(scopeIndex)
			scope := scopeSpan.Scope()
			if scope.Attributes().Len() > maxTraceScopeAttrs {
				return ErrPayloadTooLarge
			}
			scope.Attributes().Clear()
			scope.SetName(traceScopeName)
			scope.SetVersion("1")
			scope.SetDroppedAttributesCount(0)
			scopeSpan.SetSchemaUrl("")

			spans := scopeSpan.Spans()
			for spanIndex := 0; spanIndex < spans.Len(); spanIndex++ {
				span := spans.At(spanIndex)
				if span.TraceID().IsEmpty() || span.SpanID().IsEmpty() {
					return ErrInvalidPayload
				}
				if span.Attributes().Len() > maxTraceAttributesPerSpan ||
					span.Events().Len() > maxTraceEventsPerSpan ||
					span.Links().Len() > maxTraceLinksPerSpan {
					return ErrPayloadTooLarge
				}
				totalAuxItems += span.Events().Len() + span.Links().Len()
				if totalAuxItems > cfg.MaxItems {
					return ErrPayloadTooLarge
				}
				sanitizeTraceSpan(span)
			}
		}
	}
	return nil
}

func sanitizeTraceSpan(span ptrace.Span) {
	span.SetName(sanitizeTraceSpanName(span.Name()))
	span.TraceState().FromRaw("")
	span.Status().SetMessage("")
	span.SetDroppedAttributesCount(0)
	span.SetDroppedEventsCount(0)
	span.SetDroppedLinksCount(0)
	sanitizeTraceAttributes(span.Attributes())

	events := span.Events()
	for index := 0; index < events.Len(); index++ {
		event := events.At(index)
		if event.Name() == "exception" {
			event.SetName("exception")
		} else {
			event.SetName("browser.event")
		}
		event.Attributes().Clear()
		event.SetDroppedAttributesCount(0)
	}
	links := span.Links()
	for index := 0; index < links.Len(); index++ {
		link := links.At(index)
		link.Attributes().Clear()
		link.TraceState().FromRaw("")
		link.SetDroppedAttributesCount(0)
	}
}

func sanitizeTraceAttributes(attrs pcommon.Map) {
	kept := make([]safeTraceAttribute, 0, attrs.Len())
	attrs.Range(func(key string, value pcommon.Value) bool {
		if sanitized, ok := sanitizedTraceAttribute(key, value); ok {
			kept = append(kept, sanitized)
		}
		return true
	})
	attrs.Clear()
	for _, attr := range kept {
		switch attr.valueType {
		case pcommon.ValueTypeStr:
			attrs.PutStr(attr.key, attr.stringVal)
		case pcommon.ValueTypeInt:
			attrs.PutInt(attr.key, attr.intVal)
		case pcommon.ValueTypeDouble:
			attrs.PutDouble(attr.key, attr.doubleVal)
		case pcommon.ValueTypeBool:
			attrs.PutBool(attr.key, attr.boolVal)
		}
	}
}

func sanitizedTraceAttribute(key string, value pcommon.Value) (safeTraceAttribute, bool) {
	result := safeTraceAttribute{key: key, valueType: value.Type()}
	switch key {
	case "http.request.method", "http.method":
		if value.Type() != pcommon.ValueTypeStr {
			return safeTraceAttribute{}, false
		}
		method := strings.ToUpper(strings.TrimSpace(value.Str()))
		if !allowedHTTPMethod(method) {
			return safeTraceAttribute{}, false
		}
		result.stringVal = method
		return result, true
	case "url.full", "url.original", "http.url", "http.target", "url.path", "http.route":
		if value.Type() != pcommon.ValueTypeStr {
			return safeTraceAttribute{}, false
		}
		result.stringVal = sanitizeTraceURL(value.Str())
		return result, result.stringVal != ""
	}
	if _, ok := traceStringAttributes[key]; ok {
		if value.Type() != pcommon.ValueTypeStr {
			return safeTraceAttribute{}, false
		}
		sanitized := sanitizeText(strings.TrimSpace(value.Str()), 128)
		if !safeTraceValuePattern.MatchString(sanitized) {
			return safeTraceAttribute{}, false
		}
		result.stringVal = sanitized
		return result, true
	}
	if _, ok := traceNumericAttributes[key]; !ok {
		return safeTraceAttribute{}, false
	}
	switch value.Type() {
	case pcommon.ValueTypeInt:
		result.intVal = value.Int()
	case pcommon.ValueTypeDouble:
		result.doubleVal = value.Double()
	case pcommon.ValueTypeBool:
		result.boolVal = value.Bool()
	default:
		return safeTraceAttribute{}, false
	}
	return result, true
}

func allowedHTTPMethod(value string) bool {
	switch value {
	case "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS":
		return true
	default:
		return false
	}
}

func sanitizeTraceSpanName(value string) string {
	trimmed := strings.TrimSpace(value)
	parts := strings.Fields(trimmed)
	if len(parts) == 2 && allowedHTTPMethod(strings.ToUpper(parts[0])) {
		if target := sanitizeTraceURL(parts[1]); target != "" {
			return strings.ToUpper(parts[0]) + " " + target
		}
	}
	// 安全开发者标签保留可读名；含凭据 / 邮箱等才丢弃为 browser.span。
	if label := sanitizeDeveloperLabel(trimmed, 128); label != "" && !strings.HasPrefix(label, "label:") {
		return label
	}
	return "browser.span"
}

func sanitizeTraceURL(raw string) string {
	return sanitizeNetworkURL(raw)
}

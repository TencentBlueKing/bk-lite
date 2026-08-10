package traceguardprocessor

import (
	"regexp"
	"strings"

	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/ptrace"
)

var sensitiveKeyPattern = regexp.MustCompile(`(?i)(^|[._-])(authorization|cookie|password|passwd|pwd|secret|token|api[-_]?key|private[-_]?key)([._-]|$)`)

var forbiddenPayloadKeys = map[string]struct{}{
	"body":               {},
	"http.request.body":  {},
	"http.response.body": {},
	"request.body":       {},
	"response.body":      {},
	"url.full":           {},
	"url.path":           {},
	"url.query":          {},
	"url.fragment":       {},
	"http.url":           {},
	"http.target":        {},
}

var protectedResourceKeys = map[string]struct{}{
	"service.namespace":      {},
	"service.name":           {},
	"service.instance.id":    {},
	"service.version":        {},
	"deployment.environment": {},
}

var catalogIdentityLimits = map[string]int{
	"service.namespace":      256,
	"service.name":           256,
	"service.instance.id":    512,
	"service.version":        256,
	"deployment.environment": 256,
}

type SanitizeResult struct {
	DroppedResourceSpans int
}

func shouldDeleteAttribute(key string) bool {
	if strings.HasPrefix(key, "bk.") || sensitiveKeyPattern.MatchString(key) {
		return true
	}
	_, forbidden := forbiddenPayloadKeys[key]
	return forbidden
}

func truncateValue(value pcommon.Value, maxRunes int) {
	switch value.Type() {
	case pcommon.ValueTypeStr:
		value.SetStr(truncateString(value.Str(), maxRunes))
	case pcommon.ValueTypeMap:
		value.Map().Range(func(_ string, child pcommon.Value) bool {
			truncateValue(child, maxRunes)
			return true
		})
	case pcommon.ValueTypeSlice:
		for index := 0; index < value.Slice().Len(); index++ {
			truncateValue(value.Slice().At(index), maxRunes)
		}
	}
}

func truncateString(value string, maxRunes int) string {
	runes := []rune(value)
	if len(runes) <= maxRunes {
		return value
	}
	return string(runes[:maxRunes])
}

func sanitizeAttributes(attributes pcommon.Map, maxAttrs, maxRunes int, protected map[string]struct{}) {
	attributes.RemoveIf(func(key string, _ pcommon.Value) bool { return shouldDeleteAttribute(key) })
	attributes.Range(func(_ string, value pcommon.Value) bool {
		truncateValue(value, maxRunes)
		return true
	})
	if attributes.Len() <= maxAttrs {
		return
	}
	protectedCount := 0
	for key := range protected {
		if _, ok := attributes.Get(key); ok {
			protectedCount++
		}
	}
	remaining := maxAttrs - protectedCount
	attributes.RemoveIf(func(key string, _ pcommon.Value) bool {
		if _, ok := protected[key]; ok {
			return false
		}
		if remaining > 0 {
			remaining--
			return false
		}
		return true
	})
}

func sanitizeSpanName(name string, maxRunes int) string {
	if query := strings.IndexByte(name, '?'); query >= 0 {
		name = name[:query]
	}
	if fragment := strings.IndexByte(name, '#'); fragment >= 0 {
		name = name[:fragment]
	}
	return truncateString(name, maxRunes)
}

func hasValidCatalogIdentity(attributes pcommon.Map) bool {
	for key, limit := range catalogIdentityLimits {
		value, ok := attributes.Get(key)
		if !ok {
			if key == "service.name" {
				return false
			}
			continue
		}
		if value.Type() != pcommon.ValueTypeStr || len([]rune(value.Str())) > limit {
			return false
		}
		if key == "service.name" && strings.TrimSpace(value.Str()) == "" {
			return false
		}
	}
	return true
}

func sanitizeTraces(tracesData ptrace.Traces, cfg *Config) SanitizeResult {
	result := SanitizeResult{}
	tracesData.ResourceSpans().RemoveIf(func(resourceSpans ptrace.ResourceSpans) bool {
		if hasValidCatalogIdentity(resourceSpans.Resource().Attributes()) {
			return false
		}
		result.DroppedResourceSpans++
		return true
	})
	for resourceIndex := 0; resourceIndex < tracesData.ResourceSpans().Len(); resourceIndex++ {
		resourceSpans := tracesData.ResourceSpans().At(resourceIndex)
		sanitizeAttributes(
			resourceSpans.Resource().Attributes(),
			cfg.MaxResourceAttrs-1,
			cfg.MaxAttributeRunes,
			protectedResourceKeys,
		)
		resourceSpans.Resource().Attributes().PutStr("bk.cloud_region.id", cfg.CloudRegionID)
		for scopeIndex := 0; scopeIndex < resourceSpans.ScopeSpans().Len(); scopeIndex++ {
			scopeSpans := resourceSpans.ScopeSpans().At(scopeIndex)
			sanitizeAttributes(scopeSpans.Scope().Attributes(), cfg.MaxScopeAttrs, cfg.MaxAttributeRunes, nil)
			for spanIndex := 0; spanIndex < scopeSpans.Spans().Len(); spanIndex++ {
				span := scopeSpans.Spans().At(spanIndex)
				span.SetName(sanitizeSpanName(span.Name(), cfg.MaxAttributeRunes))
				sanitizeAttributes(span.Attributes(), cfg.MaxSpanAttrs, cfg.MaxAttributeRunes, nil)
				for eventIndex := 0; eventIndex < span.Events().Len(); eventIndex++ {
					sanitizeAttributes(
						span.Events().At(eventIndex).Attributes(),
						cfg.MaxEventAttrs,
						cfg.MaxAttributeRunes,
						nil,
					)
				}
				for linkIndex := 0; linkIndex < span.Links().Len(); linkIndex++ {
					sanitizeAttributes(
						span.Links().At(linkIndex).Attributes(),
						cfg.MaxLinkAttrs,
						cfg.MaxAttributeRunes,
						nil,
					)
				}
			}
		}
	}
	return result
}

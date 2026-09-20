package farorumreceiver

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"math"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	faro "github.com/grafana/faro/pkg/go"
	"github.com/bk-lite/rum-collector/internal/rum/authority"
	"github.com/bk-lite/rum-collector/internal/rumprivacy"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/pdata/ptrace"
)

const (
	ordinaryScopeName      = "weops.rum.faro"
	parseEvidenceScopeName = "weops.rum.faro.ingest_evidence"
)

var (
	contextKeyPattern       = regexp.MustCompile(`^[A-Za-z0-9_.:-]+$`)
	stableIDPattern         = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)
	emailPattern            = regexp.MustCompile(`(?i)[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}`)
	secretTextPattern       = regexp.MustCompile(`(?i)(authorization|cookie|password|token|secret)\s*[:=]\s*[^\s,;]+`)
	safeContextTokenPattern = regexp.MustCompile(`^[A-Za-z0-9._:/-]{1,128}$`)
	routeNumericIDPattern   = regexp.MustCompile(`^[0-9]+$`)
	routeUUIDPattern        = regexp.MustCompile(`(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
	routeHexIDPattern       = regexp.MustCompile(`(?i)^[0-9a-f]{16,64}$`)
	routeULIDPattern        = regexp.MustCompile(`(?i)^[0-9A-HJKMNP-TV-Z]{26}$`)
)

type ingestMetadata struct {
	tenantID            string
	credentialLookup    string
	application         string
	browserKey          string
	origin              string
	requestClass        string
	batchID             string
	geoCountry          string
	geoCity             string
	observedAt          time.Time
	identityHMACSecret  string
	identityHMACVersion string
}

func translateOrdinary(payload faro.Payload, metadata ingestMetadata, cfg *Config) plog.Logs {
	logs := plog.NewLogs()
	resourceLogs := logs.ResourceLogs().AppendEmpty()
	resourceAttrs := resourceLogs.Resource().Attributes()
	resourceAttrs.PutStr("tenant.id", metadata.tenantID)
	resourceAttrs.PutStr("rum.credential.lookup_id", metadata.credentialLookup)
	putString(resourceAttrs, "geo.country.iso_code", metadata.geoCountry, 2)
	putString(resourceAttrs, "geo.locality.name", metadata.geoCity, 128)
	// rum_sessions_mv / rum_views_mv 读 user_agent.original；不落则设备/浏览器恒空。
	putString(resourceAttrs, "user_agent.original", payload.Meta.Browser.UserAgent, 512)
	resourceAttrs.PutStr("rum.traffic.class", classifyTraffic(payload.Meta.Browser.UserAgent))

	scopeLogs := resourceLogs.ScopeLogs().AppendEmpty()
	scopeLogs.Scope().SetName(ordinaryScopeName)
	scopeLogs.Scope().SetVersion("1")
	records := scopeLogs.LogRecords()
	ordinal := 0

	for _, event := range payload.Events {
		record := records.AppendEmpty()
		eventType := classifyEvent(event)
		populateCommon(record, payload.Meta, metadata, event.Timestamp, event.Trace, "event", eventType, ordinal)
		populateEvent(record, event, eventType, cfg)
		ordinal++
	}
	for _, exception := range payload.Exceptions {
		record := records.AppendEmpty()
		populateCommon(record, payload.Meta, metadata, exception.Timestamp, exception.Trace, "exception", "error", ordinal)
		populateException(record, exception, cfg)
		ordinal++
	}
	for _, log := range payload.Logs {
		record := records.AppendEmpty()
		populateCommon(record, payload.Meta, metadata, log.Timestamp, log.Trace, "log", "console", ordinal)
		populateLog(record, log, cfg)
		ordinal++
	}
	for _, measurement := range payload.Measurements {
		record := records.AppendEmpty()
		eventType := "custom"
		if strings.EqualFold(measurement.Type, "web-vitals") {
			eventType = "vital"
		}
		populateCommon(record, payload.Meta, metadata, measurement.Timestamp, measurement.Trace, "measurement", eventType, ordinal)
		populateMeasurement(record, measurement, eventType, cfg)
		ordinal++
	}

	return logs
}

func newParseEvidence(metadata ingestMetadata, outcome, reason string) plog.Logs {
	logs := plog.NewLogs()
	resourceLogs := logs.ResourceLogs().AppendEmpty()
	populateEvidenceResource(resourceLogs.Resource().Attributes(), metadata)
	appendParseEvidenceScope(resourceLogs, metadata, outcome, reason)
	return logs
}

func appendParseEvidence(logs plog.Logs, metadata ingestMetadata, outcome, reason string) {
	resourceLogs := logs.ResourceLogs()
	if resourceLogs.Len() == 0 {
		resource := resourceLogs.AppendEmpty()
		populateEvidenceResource(resource.Resource().Attributes(), metadata)
		appendParseEvidenceScope(resource, metadata, outcome, reason)
		return
	}
	resource := resourceLogs.At(0)
	populateEvidenceResource(resource.Resource().Attributes(), metadata)
	appendParseEvidenceScope(resource, metadata, outcome, reason)
}

func populateEvidenceResource(attrs pcommon.Map, metadata ingestMetadata) {
	attrs.PutStr("tenant.id", metadata.tenantID)
	attrs.PutStr("rum.credential.lookup_id", metadata.credentialLookup)
	putString(attrs, "geo.country.iso_code", metadata.geoCountry, 2)
	putString(attrs, "geo.locality.name", metadata.geoCity, 128)
}

func appendParseEvidenceScope(resourceLogs plog.ResourceLogs, metadata ingestMetadata, outcome, reason string) {
	scopeLogs := resourceLogs.ScopeLogs().AppendEmpty()
	scopeLogs.Scope().SetName(parseEvidenceScopeName)
	scopeLogs.Scope().SetVersion("1")
	record := scopeLogs.LogRecords().AppendEmpty()
	record.SetTimestamp(pcommon.NewTimestampFromTime(metadata.observedAt))
	record.SetObservedTimestamp(pcommon.NewTimestampFromTime(metadata.observedAt))
	record.Body().SetStr("{}")
	attrs := record.Attributes()
	attrs.PutStr("rum.event.id", parseEvidenceID(metadata, outcome, reason))
	attrs.PutStr("rum.event.type", "ingest_evidence")
	attrs.PutStr("rum.application", metadata.application)
	attrs.PutStr("rum.observed.timestamp_unix_nano", strconv.FormatInt(metadata.observedAt.UnixNano(), 10))
	attrs.PutInt("rum.accepted_at_unix_nano", metadata.observedAt.UnixNano())
	attrs.PutStr("rum.evidence.stage", "parse")
	attrs.PutStr("rum.evidence.outcome", outcome)
	attrs.PutStr("rum.evidence.reason", reason)
	attrs.PutStr("rum.evidence.request_class", metadata.requestClass)
}

func parseEvidenceID(metadata ingestMetadata, outcome, reason string) string {
	material := strings.Join([]string{
		metadata.tenantID,
		metadata.credentialLookup,
		metadata.application,
		metadata.requestClass,
		metadata.batchID,
		outcome,
		reason,
		strconv.FormatInt(metadata.observedAt.UnixNano(), 10),
	}, "\x00")
	sum := sha256.Sum256([]byte(material))
	return hex.EncodeToString(sum[:])
}

func classifyEvent(event faro.Event) string {
	switch event.Name {
	case faroEventSessionStart, faroEventSessionResume, faroEventSessionExtend:
		return "session"
	case faroEventViewChanged, "faro.navigation":
		return "view"
	case "faro.user.action":
		if strings.TrimSpace(event.Action.Name) != "" {
			return "action"
		}
		return "custom"
	case "faro.performance.resource":
		return "network"
	default:
		return "custom"
	}
}

func populateCommon(
	record plog.LogRecord,
	meta faro.Meta,
	metadata ingestMetadata,
	timestamp time.Time,
	trace faro.TraceContext,
	kind string,
	eventType string,
	ordinal int,
) {
	record.SetObservedTimestamp(pcommon.NewTimestampFromTime(metadata.observedAt))
	eventTime, clamped := clampTimestamp(timestamp, metadata.observedAt)
	record.SetTimestamp(pcommon.NewTimestampFromTime(eventTime))

	attrs := record.Attributes()
	attrs.PutInt("rum.schema.version", 1)
	attrs.PutStr("rum.event.id", canonicalEventID(metadata.tenantID, metadata.application, metadata.batchID, ordinal))
	attrs.PutStr("rum.kind", kind)
	attrs.PutStr("rum.event.type", eventType)
	attrs.PutBool("rum.timestamp.clamped", clamped)
	attrs.PutStr("rum.observed.timestamp_unix_nano", strconv.FormatInt(metadata.observedAt.UnixNano(), 10))
	putString(attrs, "rum.application", meta.App.Name, 256)
	putString(attrs, "rum.environment", sanitizeDeveloperLabel(meta.App.Environment, 128), 128)
	release := meta.App.Release
	if release == "" {
		release = meta.App.Version
	}
	putString(attrs, "rum.release", sanitizeDeveloperLabel(release, 256), 256)
	putString(attrs, "rum.session.id", safeStableID(meta.Session.ID), 128)
	putString(attrs, "rum.view.id", safeStableID(meta.Page.ID), 128)
	viewName := sanitizeRoute(meta.View.Name)
	putString(attrs, "rum.view.name", viewName, 256)
	putString(attrs, "rum.context.route", viewName, 2048)
	putString(attrs, "rum.page.url", sanitizeURL(meta.Page.URL), 2048)
	putString(attrs, "rum.user.id", pseudonymousUserID(metadata, meta.User.ID), 64)
	putErasureAttributes(attrs, metadata, meta.User.ID, meta.Session.ID)
	putString(attrs, "rum.sdk.name", sanitizeDeveloperLabel(meta.SDK.Name, 128), 128)
	putString(attrs, "rum.sdk.version", sanitizeDeveloperLabel(meta.SDK.Version, 64), 64)
	putString(attrs, "rum.trace.id", normalizedTraceID(trace.TraceID), 32)
	putString(attrs, "rum.span.id", normalizedSpanID(trace.SpanID), 16)
	setRecordTrace(record, trace)
}

func populateEvent(record plog.LogRecord, event faro.Event, eventType string, cfg *Config) {
	attrs := record.Attributes()
	putString(attrs, "rum.event.name", sanitizeDeveloperLabel(event.Name, 256), 256)
	putString(attrs, "rum.event.domain", sanitizeDeveloperLabel(event.Domain, 128), 128)
	context := sanitizeEventContext(event.Name, event.Attributes, cfg)
	putContextAttrs(attrs, context)
	if eventType == "view" {
		promoteViewAttributes(attrs, event.Name, context)
	}

	body := map[string]any{
		"name":       sanitizeDeveloperLabel(event.Name, 256),
		"domain":     sanitizeDeveloperLabel(event.Domain, 128),
		"attributes": context,
	}
	if event.Action.ID != "" || event.Action.Name != "" || event.Action.ParentID != "" {
		action := map[string]string{
			"id":        safeStableID(event.Action.ID),
			"name":      sanitizeDeveloperLabel(event.Action.Name, 256),
			"parent_id": safeStableID(event.Action.ParentID),
		}
		body["action"] = compactStringMap(action)
		if eventType == "action" {
			putString(attrs, "rum.action.id", action["id"], 128)
			putString(attrs, "rum.action.name", action["name"], 256)
			putString(attrs, "rum.action.parent.id", action["parent_id"], 128)
			putString(attrs, "rum.action.trigger", context["userActionTrigger"], 128)
			putString(attrs, "rum.action.duration_ms", context["userActionDuration"], 64)
		}
	}
	if eventType == "network" {
		promoteNetworkAttributes(attrs, context)
	}
	setBody(record, body)
}

func populateException(record plog.LogRecord, exception faro.Exception, cfg *Config) {
	attrs := record.Attributes()
	errorType := sanitizeDeveloperLabel(exception.Type, 256)
	errorMessage := sanitizeErrorMessage(exception.Value)
	errorFingerprint := privacyLabel("fingerprint", exception.Fingerprint)
	keyFrame := ""
	if exception.Stacktrace != nil && len(exception.Stacktrace.Frames) > 0 {
		keyFrame = rumprivacy.AssetFingerprint(exception.Stacktrace.Frames[0].Filename)
	}
	application := ""
	if value, ok := attrs.Get("rum.application"); ok {
		application = value.Str()
	}
	errorGroupKey := stableErrorGroupKey(
		application,
		errorType,
		errorMessage,
		exception.Fingerprint,
		keyFrame,
	)
	putString(attrs, "rum.error.type", errorType, 256)
	putString(attrs, "rum.error.message", errorMessage.Value, 1024)
	putString(attrs, "rum.error.message_kind", string(errorMessage.Kind), 16)
	putString(attrs, "rum.error.fingerprint", errorFingerprint, 64)
	putString(attrs, "rum.error.group_key", errorGroupKey, 64)
	attrs.PutBool("rum.error.fatal", exception.Fatal)
	context := sanitizeTechnicalContext(map[string]string(exception.Context), cfg)
	putContextAttrs(attrs, context)
	body := map[string]any{
		"type":        errorType,
		"value":       errorMessage.Value,
		"messageKind": string(errorMessage.Kind),
		"fingerprint": errorFingerprint,
		"groupKey":    errorGroupKey,
		"fatal":       exception.Fatal,
		"context":     context,
	}
	if exception.Stacktrace != nil {
		frames := make([]map[string]any, 0, min(len(exception.Stacktrace.Frames), 32))
		for index, frame := range exception.Stacktrace.Frames {
			if index == 32 {
				break
			}
			frames = append(frames, map[string]any{
				"filename": rumprivacy.AssetFingerprint(frame.Filename),
				"function": safeJSSymbol(frame.Function),
				"module":   privacyLabel("module", frame.Module),
				"line":     frame.Lineno,
				"column":   frame.Colno,
			})
		}
		body["frames"] = frames
	}
	setBody(record, body)
}

func populateLog(record plog.LogRecord, log faro.Log, cfg *Config) {
	level := strings.ToLower(string(log.LogLevel))
	if level == "warning" {
		level = "warn"
	}
	record.SetSeverityText(level)
	switch level {
	case "error":
		record.SetSeverityNumber(plog.SeverityNumberError)
	case "warn":
		record.SetSeverityNumber(plog.SeverityNumberWarn)
	case "info", "log":
		record.SetSeverityNumber(plog.SeverityNumberInfo)
	case "debug":
		record.SetSeverityNumber(plog.SeverityNumberDebug)
	case "trace":
		record.SetSeverityNumber(plog.SeverityNumberTrace)
	}
	message := privacyLabel("message", log.Message)
	attrs := record.Attributes()
	putString(attrs, "rum.console.level", level, 16)
	putString(attrs, "rum.console.message", message, 2048)
	putString(attrs, "rum.console.message_kind", string(diagnosticFingerprint), 16)
	context := sanitizeTechnicalContext(map[string]string(log.Context), cfg)
	putContextAttrs(attrs, context)
	setBody(record, map[string]any{"level": level, "message": message, "messageKind": diagnosticFingerprint, "context": context})
}

func populateMeasurement(record plog.LogRecord, measurement faro.Measurement, eventType string, cfg *Config) {
	attrs := record.Attributes()
	measurementType := sanitizeDeveloperLabel(measurement.Type, 128)
	putString(attrs, "rum.measurement.type", measurementType, 128)
	context := sanitizeMeasurementContext(measurement.Type, map[string]string(measurement.Context), cfg)
	putContextAttrs(attrs, context)
	values := sanitizeMeasurementValues(measurementType, measurement.Values, cfg.MaxContextEntries)
	if eventType == "vital" {
		for _, key := range []string{"element", "interaction_target", "largest_shift_target"} {
			if raw := measurement.Context[key]; raw != "" {
				target := sanitizeWebVitalSelector(raw)
				putString(attrs, "rum.vital.target_kind", string(target.Kind), 16)
				break
			}
		}
		for name, value := range values {
			attrs.PutDouble("rum.vital."+strings.ToLower(name), value)
		}
	}
	setBody(record, map[string]any{"type": measurementType, "values": values, "context": context})
}

func putContextAttrs(attrs pcommon.Map, context map[string]string) {
	for key, value := range context {
		attrs.PutStr("rum.context."+key, value)
	}
}

func promoteNetworkAttributes(attrs pcommon.Map, context map[string]string) {
	for source, target := range map[string]string{
		"name":           "url",
		"initiatorType":  "initiator",
		"responseStatus": "status",
		"duration":       "duration",
		"transferSize":   "size",
		"cacheHitStatus": "cache",
		"protocol":       "protocol",
	} {
		value, ok := context[source]
		if !ok {
			continue
		}
		putString(attrs, "rum.network."+target, value, 2048)
	}
}

func promoteViewAttributes(attrs pcommon.Map, eventName string, context map[string]string) {
	route := ""
	if current, ok := attrs.Get("rum.context.route"); ok {
		route = current.Str()
	}

	switch eventName {
	case faroEventViewChanged:
		if context["toView"] != "" {
			route = context["toView"]
		}
		putString(attrs, "rum.context.navigation_type", "view-change", 32)
	case "faro.navigation":
		if route == "" {
			route = context["toUrl"]
		}
		switch context["sameDocument"] {
		case "true":
			putString(attrs, "rum.context.navigation_type", "same-document", 32)
		case "false":
			putString(attrs, "rum.context.navigation_type", "document", 32)
		}
		putString(attrs, "rum.context.loading_time_ms", context["duration"], 64)
	}

	putString(attrs, "rum.context.route", route, 2048)
}

type contextValueKind uint8

const (
	contextToken contextValueKind = iota
	contextNumber
	contextURL
	contextRoute
	contextSelector
	contextStableID
)

var resourceContextFields = map[string]contextValueKind{
	"cacheHitStatus": contextToken, "decodedBodySize": contextNumber, "dnsLookupTime": contextNumber,
	"duration": contextNumber, "encodedBodySize": contextNumber, "faroNavigationId": contextStableID,
	"faroPreviousNavigationId": contextStableID, "fetchTime": contextNumber, "httpHost": contextToken,
	"initiatorType": contextToken, "name": contextURL, "protocol": contextToken,
	"redirectTime": contextNumber, "renderBlockingStatus": contextToken, "requestTime": contextNumber,
	"responseStatus": contextNumber, "responseTime": contextNumber, "serviceWorkerTime": contextNumber,
	"tcpHandshakeTime": contextNumber, "tlsNegotiationTime": contextNumber, "transferSize": contextNumber,
	"ttfb": contextNumber, "visibilityState": contextToken,
}

var navigationContextFields = func() map[string]contextValueKind {
	fields := make(map[string]contextValueKind, len(resourceContextFields)+6)
	for key, kind := range resourceContextFields {
		fields[key] = kind
	}
	for _, key := range []string{
		"documentParsingTime", "domContentLoadHandlerTime", "domProcessingTime", "onLoadTime", "pageLoadTime",
	} {
		fields[key] = contextNumber
	}
	fields["type"] = contextToken
	return fields
}()

var webVitalContextFields = map[string]contextValueKind{
	"element": contextSelector, "id": contextStableID, "interaction_target": contextSelector,
	"interaction_type": contextToken, "largest_shift_target": contextSelector, "load_state": contextToken,
	"navigation_entry_id": contextStableID, "navigation_type": contextToken, "rating": contextToken,
}

var webVitalValueFields = map[string]struct{}{
	"cache_duration": {}, "cls": {}, "connection_duration": {}, "delta": {}, "dns_duration": {},
	"element_render_delay": {}, "fcp": {}, "first_byte_to_fcp": {}, "inp": {}, "input_delay": {},
	"interaction_time": {}, "largest_shift_time": {}, "largest_shift_value": {}, "lcp": {},
	"next_paint_time": {}, "presentation_delay": {}, "processing_duration": {}, "request_duration": {},
	"resource_load_delay": {}, "resource_load_duration": {}, "time_to_first_byte": {}, "ttfb": {},
	"waiting_duration": {},
}

func sanitizeEventContext(eventName string, context map[string]string, cfg *Config) map[string]string {
	var allowed map[string]contextValueKind
	switch eventName {
	case "faro.performance.resource":
		allowed = resourceContextFields
	case "faro.performance.navigation":
		allowed = navigationContextFields
	case "faro.navigation":
		allowed = map[string]contextValueKind{
			"duration": contextNumber, "fromUrl": contextURL, "sameDocument": contextToken, "toUrl": contextURL,
		}
	case faroEventViewChanged:
		allowed = map[string]contextValueKind{"fromView": contextRoute, "toView": contextRoute}
	case "faro.user.action":
		allowed = map[string]contextValueKind{
			"userActionDuration": contextNumber, "userActionEndTime": contextNumber,
			"userActionImportance": contextToken, "userActionName": contextRoute,
			"userActionStartTime": contextNumber, "userActionTrigger": contextToken,
		}
	case "securitypolicyviolation":
		allowed = map[string]contextValueKind{
			"blockedURI": contextURL, "columnNumber": contextNumber, "disposition": contextToken,
			"documentURI": contextURL, "effectiveDirective": contextToken, "lineNumber": contextNumber,
			"referrer": contextURL, "sourceFile": contextURL, "statusCode": contextNumber,
			"violatedDirective": contextToken,
		}
	default:
		return map[string]string{}
	}
	return sanitizeAllowlistedContext(context, allowed, cfg)
}

func sanitizeMeasurementContext(measurementType string, context map[string]string, cfg *Config) map[string]string {
	if !strings.EqualFold(strings.TrimSpace(measurementType), "web-vitals") {
		return map[string]string{}
	}
	return sanitizeAllowlistedContext(context, webVitalContextFields, cfg)
}

func sanitizeTechnicalContext(context map[string]string, cfg *Config) map[string]string {
	return sanitizeAllowlistedContext(context, map[string]contextValueKind{
		"category": contextToken, "code": contextToken, "component": contextToken,
		"operation": contextToken, "source": contextToken,
	}, cfg)
}

func sanitizeAllowlistedContext(
	context map[string]string,
	allowed map[string]contextValueKind,
	cfg *Config,
) map[string]string {
	keys := make([]string, 0, len(context))
	for key := range context {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	result := make(map[string]string, min(len(keys), cfg.MaxContextEntries))
	for _, key := range keys {
		if len(result) == cfg.MaxContextEntries {
			break
		}
		trimmedKey := strings.TrimSpace(key)
		kind, allowedKey := allowed[trimmedKey]
		if !allowedKey || trimmedKey == "" || len(trimmedKey) > cfg.MaxContextKeyBytes || !contextKeyPattern.MatchString(trimmedKey) || sensitiveKey(trimmedKey) {
			continue
		}
		value, ok := sanitizeContextValue(context[key], kind, cfg.MaxContextValueBytes)
		if !ok {
			continue
		}
		result[trimmedKey] = value
	}
	return result
}

func sanitizeContextValue(value string, kind contextValueKind, limit int) (string, bool) {
	value = strings.TrimSpace(value)
	switch kind {
	case contextURL:
		value = sanitizeNetworkURL(value)
	case contextRoute:
		value = sanitizeRoute(value)
	case contextSelector:
		value = sanitizeWebVitalSelector(value).Value
	case contextStableID:
		value = safeStableID(value)
	case contextNumber:
		number, err := strconv.ParseFloat(value, 64)
		if err != nil || math.IsNaN(number) || math.IsInf(number, 0) {
			return "", false
		}
		value = strconv.FormatFloat(number, 'f', -1, 64)
	case contextToken:
		value = sanitizeText(value, min(limit, 128))
		if !safeContextTokenPattern.MatchString(value) {
			return "", false
		}
	}
	return truncateUTF8(value, limit), value != ""
}

func sensitiveKey(key string) bool {
	normalized := strings.ToLower(strings.NewReplacer("-", "_", ".", "_").Replace(key))
	for _, denied := range []string{
		"authorization", "cookie", "password", "passwd", "token", "secret", "email", "username",
		"phone", "mobile_number", "first_name", "last_name", "full_name", "person_name", "input", "innerhtml",
	} {
		if strings.Contains(normalized, denied) {
			return true
		}
	}
	return normalized == "value" || strings.HasSuffix(normalized, "_value") || normalized == "text"
}

func sanitizeValues(values map[string]float64, limit int) map[string]float64 {
	keys := make([]string, 0, len(values))
	for key := range values {
		if contextKeyPattern.MatchString(key) && !sensitiveKey(key) {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	if len(keys) > limit {
		keys = keys[:limit]
	}
	result := make(map[string]float64, len(keys))
	for _, key := range keys {
		value := values[key]
		if math.IsNaN(value) || math.IsInf(value, 0) {
			continue
		}
		result[key] = value
	}
	return result
}

func sanitizeMeasurementValues(measurementType string, values map[string]float64, limit int) map[string]float64 {
	if !strings.EqualFold(strings.TrimSpace(measurementType), "web-vitals") {
		return sanitizeValues(values, limit)
	}
	keys := make([]string, 0, len(values))
	for key := range values {
		if _, allowed := webVitalValueFields[key]; allowed {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	if len(keys) > limit {
		keys = keys[:limit]
	}
	result := make(map[string]float64, len(keys))
	for _, key := range keys {
		value := values[key]
		if math.IsNaN(value) || math.IsInf(value, 0) {
			continue
		}
		result[key] = value
	}
	return result
}

func canonicalEventID(tenantID, application, batchID string, ordinal int) string {
	sum := sha256.Sum256([]byte(tenantID + "\x00" + application + "\x00" + batchID + "\x00" + strconv.Itoa(ordinal)))
	return hex.EncodeToString(sum[:])
}

func canonicalTraceIngestID(tenantID, application, batchID string, ordinal int) string {
	sum := sha256.Sum256([]byte(tenantID + "\x00" + application + "\x00" + batchID + "\x00trace\x00" + strconv.Itoa(ordinal)))
	return hex.EncodeToString(sum[:])
}

func clampTimestamp(timestamp, observed time.Time) (time.Time, bool) {
	if timestamp.IsZero() || timestamp.After(observed.Add(5*time.Minute)) || timestamp.Before(observed.Add(-5*time.Minute)) {
		return observed, true
	}
	return timestamp, false
}

func sanitizeURL(raw string) string {
	return sanitizeTraceURL(raw)
}

func sanitizeURLPath(path string) string {
	return sanitizeTraceURL(path)
}

func sanitizeRoute(raw string) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return ""
	}
	if !strings.Contains(trimmed, "/") && !strings.Contains(trimmed, "://") {
		return safeTechnicalLabel(trimmed, 256)
	}
	parsed, err := url.Parse(trimmed)
	if err != nil || (parsed.IsAbs() && parsed.Scheme != "http" && parsed.Scheme != "https") {
		return ""
	}
	path := parsed.EscapedPath()
	if path == "" {
		path = "/"
	}
	return sanitizeRoutePath(path)
}

func sanitizeRoutePath(path string) string {
	if path == "" || path == "/" {
		return "/"
	}
	segments := strings.Split(strings.Trim(path, "/"), "/")
	for index, segment := range segments {
		decoded, err := url.PathUnescape(segment)
		if err != nil {
			segments[index] = ":text"
			continue
		}
		segments[index] = sanitizePathSegment(decoded)
	}
	return truncateUTF8("/"+strings.Join(segments, "/"), 256)
}

func isOpaqueRouteID(segment string) bool {
	return routeNumericIDPattern.MatchString(segment) ||
		routeUUIDPattern.MatchString(segment) ||
		routeHexIDPattern.MatchString(segment) ||
		routeULIDPattern.MatchString(segment)
}

func safeTechnicalLabel(value string, limit int) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	value = truncateUTF8(value, limit)
	if safeContextTokenPattern.MatchString(value) {
		return value
	}
	return privacyLabel("label", value)
}

func privacyLabel(prefix, value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	digest := sha256.Sum256([]byte(prefix + "\x00" + value))
	return prefix + ":" + hex.EncodeToString(digest[:8])
}

func sanitizeText(value string, limit int) string {
	value = emailPattern.ReplaceAllString(value, "[redacted]")
	value = secretTextPattern.ReplaceAllString(value, "$1=[redacted]")
	return truncateUTF8(value, limit)
}

func safeStableID(value string) string {
	value = strings.TrimSpace(value)
	if !stableIDPattern.MatchString(value) {
		return ""
	}
	return value
}

func normalizedTraceID(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	decoded, err := hex.DecodeString(value)
	if err != nil || len(decoded) != 16 {
		return ""
	}
	return value
}

func normalizedSpanID(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	decoded, err := hex.DecodeString(value)
	if err != nil || len(decoded) != 8 {
		return ""
	}
	return value
}

func setRecordTrace(record plog.LogRecord, trace faro.TraceContext) {
	traceValue := normalizedTraceID(trace.TraceID)
	if traceValue != "" {
		decoded, _ := hex.DecodeString(traceValue)
		var traceID pcommon.TraceID
		copy(traceID[:], decoded)
		record.SetTraceID(traceID)
	}
	spanValue := normalizedSpanID(trace.SpanID)
	if spanValue != "" {
		decoded, _ := hex.DecodeString(spanValue)
		var spanID pcommon.SpanID
		copy(spanID[:], decoded)
		record.SetSpanID(spanID)
	}
}

func overrideTraceMetadata(traces ptrace.Traces, metadata ingestMetadata, meta faro.Meta) {
	resourceSpans := traces.ResourceSpans()
	ordinal := 0
	for index := 0; index < resourceSpans.Len(); index++ {
		attrs := resourceSpans.At(index).Resource().Attributes()
		attrs.PutStr("tenant.id", metadata.tenantID)
		attrs.PutStr("rum.credential.lookup_id", metadata.credentialLookup)
		attrs.PutStr("service.name", metadata.application)
		putString(attrs, "geo.country.iso_code", metadata.geoCountry, 2)
		putString(attrs, "geo.locality.name", metadata.geoCity, 128)
		putString(attrs, "rum.application", metadata.application, 256)
		putString(attrs, "deployment.environment.name", safeTechnicalLabel(meta.App.Environment, 128), 128)
		release := meta.App.Release
		if release == "" {
			release = meta.App.Version
		}
		putString(attrs, "service.version", safeTechnicalLabel(release, 256), 256)
		putString(attrs, "rum.session.id", safeStableID(meta.Session.ID), 128)
		putString(attrs, "rum.page.url", sanitizeTraceURL(meta.Page.URL), 2048)
		putString(attrs, "rum.user.id", pseudonymousUserID(metadata, meta.User.ID), 64)
		scopeSpans := resourceSpans.At(index).ScopeSpans()
		for scopeIndex := 0; scopeIndex < scopeSpans.Len(); scopeIndex++ {
			spans := scopeSpans.At(scopeIndex).Spans()
			for spanIndex := 0; spanIndex < spans.Len(); spanIndex++ {
				span := spans.At(spanIndex)
				clamped := clampTraceTimestamps(span, metadata.observedAt)
				spanAttrs := span.Attributes()
				spanAttrs.PutStr("rum.ingest.id", canonicalTraceIngestID(metadata.tenantID, metadata.application, metadata.batchID, ordinal))
				spanAttrs.PutBool("rum.timestamp.clamped", clamped)
				putString(spanAttrs, "rum.session.id", safeStableID(meta.Session.ID), 128)
				putString(spanAttrs, "rum.user.id", pseudonymousUserID(metadata, meta.User.ID), 64)
				putErasureAttributes(spanAttrs, metadata, meta.User.ID, meta.Session.ID)
				ordinal++
			}
		}
	}
}

func clampTraceTimestamps(span ptrace.Span, observedAt time.Time) bool {
	start, startClamped := clampTimestamp(span.StartTimestamp().AsTime(), observedAt)
	end, endClamped := clampTimestamp(span.EndTimestamp().AsTime(), observedAt)
	if end.Before(start) {
		end = start
		endClamped = true
	}
	span.SetStartTimestamp(pcommon.NewTimestampFromTime(start))
	span.SetEndTimestamp(pcommon.NewTimestampFromTime(end))

	eventsClamped := false
	events := span.Events()
	for index := 0; index < events.Len(); index++ {
		event := events.At(index)
		timestamp, clamped := clampTimestamp(event.Timestamp().AsTime(), observedAt)
		event.SetTimestamp(pcommon.NewTimestampFromTime(timestamp))
		eventsClamped = eventsClamped || clamped
	}
	return startClamped || endClamped || eventsClamped
}

func putErasureAttributes(attrs pcommon.Map, metadata ingestMetadata, rawUserID, rawSessionID string) {
	attrs.PutInt("rum.accepted_at_unix_nano", metadata.observedAt.UnixNano())
	attrs.PutStr("rum.erasure.key_version", metadata.identityHMACVersion)
	putString(
		attrs,
		"rum.erasure.user_key",
		authority.DeriveIdentityKey(
			metadata.identityHMACSecret,
			"user",
			metadata.tenantID,
			authority.UserIdentityMaterial(safeStableID(rawUserID), safeStableID(rawSessionID)),
		),
		64,
	)
	putString(
		attrs,
		"rum.erasure.session_key",
		authority.DeriveIdentityKey(metadata.identityHMACSecret, "session", metadata.tenantID, safeStableID(rawSessionID)),
		64,
	)
}

func pseudonymousUserID(metadata ingestMetadata, rawUserID string) string {
	return authority.DeriveIdentityKey(
		metadata.identityHMACSecret,
		"user",
		metadata.tenantID,
		safeStableID(rawUserID),
	)
}

func putString(attrs pcommon.Map, key, value string, limit int) {
	value = truncateUTF8(strings.TrimSpace(value), limit)
	if value != "" {
		attrs.PutStr(key, value)
	}
}

func setBody(record plog.LogRecord, body map[string]any) {
	encoded, err := json.Marshal(body)
	if err != nil {
		record.Body().SetStr(`{"error":"body serialization failed"}`)
		return
	}
	record.Body().SetStr(string(encoded))
}

func compactStringMap(values map[string]string) map[string]string {
	result := make(map[string]string, len(values))
	for key, value := range values {
		if value != "" {
			result[key] = value
		}
	}
	return result
}

func truncateUTF8(value string, limit int) string {
	if limit <= 0 || len(value) <= limit {
		return value
	}
	value = value[:limit]
	for !utf8.ValidString(value) {
		_, size := utf8.DecodeLastRuneInString(value)
		if size == 0 {
			return ""
		}
		value = value[:len(value)-size]
	}
	return value
}

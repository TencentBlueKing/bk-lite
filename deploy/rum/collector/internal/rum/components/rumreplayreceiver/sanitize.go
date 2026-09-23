package rumreplayreceiver

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/bk-lite/rum-collector/internal/rum/components/rumreplayprotocol"
)

const (
	redactedReplayText         = "[redacted]"
	maxSafeJSONInteger         = int64(1<<53 - 1)
	maxNodeDepth               = 64
	maxCustomElementNameLength = 64
)

var (
	attributeNamePattern     = regexp.MustCompile(`^[A-Za-z_:][A-Za-z0-9_.:-]{0,127}$`)
	tagNamePattern           = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9:_-]{0,63}$`)
	documentNamePattern      = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9:_-]{0,63}$`)
	customElementNamePattern = regexp.MustCompile(`^[a-z][a-z0-9._-]*-[a-z0-9._-]*$`)
	rrDimensionPattern       = regexp.MustCompile(`^[0-9]+(?:\.[0-9]+)?px$`)
)

var safeReplayElementTags = map[string]struct{}{
	"a": {}, "article": {}, "aside": {}, "b": {}, "blockquote": {}, "body": {},
	"br": {}, "button": {}, "canvas": {}, "caption": {}, "code": {}, "col": {}, "colgroup": {},
	"dd": {}, "details": {}, "dialog": {}, "div": {}, "dl": {}, "dt": {}, "em": {}, "fieldset": {},
	"figcaption": {}, "figure": {}, "footer": {}, "h1": {}, "h2": {}, "h3": {}, "h4": {},
	"h5": {}, "h6": {}, "head": {}, "header": {}, "hr": {}, "html": {}, "i": {}, "input": {},
	"label": {}, "legend": {}, "li": {}, "main": {}, "mark": {}, "nav": {}, "ol": {}, "optgroup": {},
	"option": {}, "p": {}, "pre": {}, "progress": {}, "s": {}, "section": {}, "select": {},
	"small": {}, "span": {}, "strong": {}, "sub": {}, "summary": {}, "sup": {}, "table": {}, "tbody": {},
	"style": {}, "td": {}, "textarea": {}, "tfoot": {}, "th": {}, "thead": {}, "time": {}, "tr": {}, "u": {}, "ul": {},
}

var safeReplayAttributes = map[string]struct{}{
	"autofocus": {}, "checked": {}, "colspan": {}, "controls": {}, "dir": {}, "disabled": {},
	"height": {}, "hidden": {}, "lang": {}, "loop": {}, "max": {}, "maxlength": {}, "min": {},
	"minlength": {}, "multiple": {}, "open": {}, "readonly": {}, "required": {}, "reversed": {},
	"role": {}, "rowspan": {}, "selected": {}, "size": {}, "step": {}, "type": {}, "width": {},
}

type sanitizedEventFacts struct {
	events                 []json.RawMessage
	firstTimestamp         int64
	lastTimestamp          int64
	hasFullSnapshot        bool
	fullSnapshotCount      int
	firstMetaIndex         int
	firstFullSnapshotIndex int
}

func sanitizeReplayEnvelope(
	envelope replayEnvelope,
	startedAt time.Time,
	endedAt time.Time,
) (replayEnvelope, error) {
	facts, err := sanitizeRRWebEvents(envelope.Events)
	if err != nil {
		return replayEnvelope{}, err
	}
	if startedAt.Nanosecond()%int(time.Millisecond) != 0 || startedAt.UnixMilli() != facts.firstTimestamp {
		return replayEnvelope{}, fmt.Errorf("%w: started_at does not match Replay events", ErrInvalidReplay)
	}
	if endedAt.Nanosecond()%int(time.Millisecond) != 0 || endedAt.UnixMilli() != facts.lastTimestamp {
		return replayEnvelope{}, fmt.Errorf("%w: ended_at does not match Replay events", ErrInvalidReplay)
	}
	if envelope.HasFullSnapshot != facts.hasFullSnapshot {
		return replayEnvelope{}, fmt.Errorf("%w: full snapshot marker mismatch", ErrInvalidReplay)
	}
	if facts.hasFullSnapshot &&
		(facts.firstMetaIndex != 0 || facts.firstFullSnapshotIndex != 1 || facts.fullSnapshotCount != 1) {
		return replayEnvelope{}, fmt.Errorf(
			"%w: checkpoint requires exactly one FullSnapshot after the leading Meta event",
			ErrInvalidReplay,
		)
	}
	if envelope.Sequence == 0 && !facts.hasFullSnapshot {
		return replayEnvelope{}, fmt.Errorf(
			"%w: sequence zero requires a Meta and FullSnapshot checkpoint",
			ErrInvalidReplay,
		)
	}

	envelope.Events = facts.events
	// 原始终端用户标识只用于在接收边界派生合规 fence key，绝不进入持久队列或对象。
	envelope.UserID = ""
	eventMaterial, err := rumreplayprotocol.CanonicalJSON(envelope.Events)
	if err != nil {
		return replayEnvelope{}, fmt.Errorf("%w: event canonicalization failed", ErrInvalidReplay)
	}
	eventDigest := sha256.Sum256(eventMaterial)
	segmentMaterial, err := rumreplayprotocol.CanonicalJSON(map[string]any{
		"application": envelope.Application,
		"eventDigest": hex.EncodeToString(eventDigest[:]),
		"recordingId": envelope.RecordingID,
		"sequence":    envelope.Sequence,
		"sessionId":   envelope.SessionID,
	})
	if err != nil {
		return replayEnvelope{}, fmt.Errorf("%w: segment identity failed", ErrInvalidReplay)
	}
	segmentDigest := sha256.Sum256(segmentMaterial)
	envelope.SegmentID = hex.EncodeToString(segmentDigest[:])
	envelope.ChecksumSHA256 = ""
	return envelope, nil
}

func sanitizeRRWebEvents(events []json.RawMessage) (sanitizedEventFacts, error) {
	facts := sanitizedEventFacts{
		events:                 make([]json.RawMessage, 0, len(events)),
		firstTimestamp:         math.MaxInt64,
		firstMetaIndex:         -1,
		firstFullSnapshotIndex: -1,
	}
	previousTimestamp := int64(-1)
	for index, raw := range events {
		object, err := decodeJSONObject(raw)
		if err != nil {
			return sanitizedEventFacts{}, err
		}
		if err := rejectUnknownFields(object, "type", "data", "timestamp", "delay"); err != nil {
			return sanitizedEventFacts{}, err
		}
		eventType, err := requiredInteger(object, "type", 0, 7)
		if err != nil {
			return sanitizedEventFacts{}, err
		}
		timestamp, err := requiredInteger(object, "timestamp", 0, maxSafeJSONInteger)
		if err != nil {
			return sanitizedEventFacts{}, err
		}
		if previousTimestamp > timestamp {
			return sanitizedEventFacts{}, fmt.Errorf("%w: Replay timestamps are not ordered", ErrInvalidReplay)
		}
		previousTimestamp = timestamp

		dataRaw, ok := object["data"]
		if !ok || bytes.Equal(bytes.TrimSpace(dataRaw), []byte("null")) {
			return sanitizedEventFacts{}, fmt.Errorf("%w: rrweb event data is required", ErrInvalidReplay)
		}
		data, err := sanitizeEventData(int(eventType), dataRaw)
		if err != nil {
			return sanitizedEventFacts{}, err
		}
		sanitized := map[string]any{
			"data":      data,
			"timestamp": timestamp,
			"type":      eventType,
		}
		if delayRaw, ok := object["delay"]; ok {
			delay, err := decodeInteger(delayRaw, 0, maxSafeJSONInteger)
			if err != nil {
				return sanitizedEventFacts{}, fmt.Errorf("%w: invalid rrweb delay", ErrInvalidReplay)
			}
			sanitized["delay"] = delay
		}
		encoded, err := rumreplayprotocol.CanonicalJSON(sanitized)
		if err != nil {
			return sanitizedEventFacts{}, fmt.Errorf("%w: rrweb event canonicalization failed", ErrInvalidReplay)
		}
		facts.events = append(facts.events, encoded)
		if timestamp < facts.firstTimestamp {
			facts.firstTimestamp = timestamp
		}
		if timestamp > facts.lastTimestamp {
			facts.lastTimestamp = timestamp
		}
		if eventType == 2 {
			facts.hasFullSnapshot = true
			facts.fullSnapshotCount++
			if facts.firstFullSnapshotIndex < 0 {
				facts.firstFullSnapshotIndex = index
			}
		}
		if eventType == 4 && facts.firstMetaIndex < 0 {
			facts.firstMetaIndex = index
		}
	}
	return facts, nil
}

func sanitizeEventData(eventType int, raw json.RawMessage) (any, error) {
	switch eventType {
	case 0, 1:
		object, err := decodeJSONObject(raw)
		if err != nil {
			return nil, err
		}
		if len(object) != 0 {
			return nil, fmt.Errorf("%w: invalid rrweb lifecycle event", ErrInvalidReplay)
		}
		return map[string]any{}, nil
	case 2:
		return sanitizeFullSnapshot(raw)
	case 3:
		return sanitizeIncrementalSnapshot(raw)
	case 4:
		return sanitizeMetaEvent(raw)
	case 5, 6, 7:
		return nil, fmt.Errorf("%w: opaque rrweb event type is forbidden", ErrInvalidReplay)
	default:
		return nil, fmt.Errorf("%w: unsupported rrweb event type", ErrInvalidReplay)
	}
}

func sanitizeFullSnapshot(raw json.RawMessage) (any, error) {
	object, err := decodeJSONObject(raw)
	if err != nil {
		return nil, err
	}
	if err := rejectUnknownFields(object, "node", "initialOffset"); err != nil {
		return nil, err
	}
	nodeRaw, ok := object["node"]
	if !ok {
		return nil, fmt.Errorf("%w: full snapshot node is required", ErrInvalidReplay)
	}
	node, err := sanitizeSerializedNode(nodeRaw, 0)
	if err != nil {
		return nil, err
	}
	offsetRaw, ok := object["initialOffset"]
	if !ok {
		return nil, fmt.Errorf("%w: full snapshot offset is required", ErrInvalidReplay)
	}
	offset, err := decodeJSONObject(offsetRaw)
	if err != nil {
		return nil, err
	}
	if err := rejectUnknownFields(offset, "top", "left"); err != nil {
		return nil, err
	}
	top, err := requiredFiniteNumber(offset, "top")
	if err != nil {
		return nil, err
	}
	left, err := requiredFiniteNumber(offset, "left")
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"initialOffset": map[string]any{"left": left, "top": top},
		"node":          node,
	}, nil
}

func sanitizeMetaEvent(raw json.RawMessage) (any, error) {
	object, err := decodeJSONObject(raw)
	if err != nil {
		return nil, err
	}
	if err := rejectUnknownFields(object, "href", "width", "height"); err != nil {
		return nil, err
	}
	_, err = requiredString(object, "href")
	if err != nil {
		return nil, err
	}
	width, err := requiredFiniteNumber(object, "width")
	if err != nil {
		return nil, err
	}
	height, err := requiredFiniteNumber(object, "height")
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"height": height,
		"href":   "about:blank",
		"width":  width,
	}, nil
}

func sanitizeIncrementalSnapshot(raw json.RawMessage) (any, error) {
	object, err := decodeJSONObject(raw)
	if err != nil {
		return nil, err
	}
	source, err := requiredInteger(object, "source", 0, 16)
	if err != nil {
		return nil, err
	}
	switch source {
	case 0:
		return sanitizeMutationData(object)
	case 1, 6, 12:
		return sanitizePositionData(object, source)
	case 2:
		return sanitizeMouseInteractionData(object)
	case 3:
		return sanitizeScrollData(object)
	case 4:
		return sanitizeViewportData(object)
	case 5:
		return sanitizeInputData(object)
	case 7:
		return sanitizeMediaData(object)
	case 8:
		return sanitizeStyleSheetRuleData(object)
	case 9, 10, 11:
		return nil, fmt.Errorf("%w: high-risk rrweb incremental source is forbidden", ErrInvalidReplay)
	case 13:
		return sanitizeStyleDeclarationData(object)
	case 14:
		return sanitizeSelectionData(object)
	case 15:
		return sanitizeAdoptedStyleSheetData(object)
	case 16:
		return sanitizeCustomElementData(object)
	default:
		return nil, fmt.Errorf("%w: unsupported rrweb incremental source", ErrInvalidReplay)
	}
}

func sanitizeCustomElementData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "define"); err != nil {
		return nil, err
	}
	defineRaw, ok := object["define"]
	if !ok {
		return nil, fmt.Errorf("%w: custom-element definition is required", ErrInvalidReplay)
	}
	define, err := decodeJSONObject(defineRaw)
	if err != nil {
		return nil, err
	}
	if err := rejectUnknownFields(define, "name"); err != nil {
		return nil, err
	}
	name, err := requiredString(define, "name")
	if err != nil || len(name) > maxCustomElementNameLength || !customElementNamePattern.MatchString(name) {
		return nil, fmt.Errorf("%w: invalid custom-element name", ErrInvalidReplay)
	}
	return map[string]any{
		"define": map[string]any{"name": name},
		"source": int64(16),
	}, nil
}

func sanitizeSerializedNode(raw json.RawMessage, depth int) (any, error) {
	if depth > maxNodeDepth {
		return nil, fmt.Errorf("%w: rrweb node depth exceeds limit", ErrInvalidReplay)
	}
	object, err := decodeJSONObject(raw)
	if err != nil {
		return nil, err
	}
	nodeType, err := requiredInteger(object, "type", 0, 5)
	if err != nil {
		return nil, err
	}
	id, err := requiredInteger(object, "id", 1, maxSafeJSONInteger)
	if err != nil {
		return nil, err
	}
	output := map[string]any{"id": id, "type": nodeType}
	for _, name := range []string{"rootId"} {
		if value, ok := object[name]; ok {
			parsed, err := decodeInteger(value, 1, maxSafeJSONInteger)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid rrweb node identity", ErrInvalidReplay)
			}
			output[name] = parsed
		}
	}
	for _, name := range []string{"isShadowHost", "isShadow"} {
		if value, ok := object[name]; ok {
			parsed, err := decodeBool(value)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid rrweb node marker", ErrInvalidReplay)
			}
			output[name] = parsed
		}
	}
	common := []string{"type", "id", "rootId", "isShadowHost", "isShadow"}
	switch nodeType {
	case 0:
		if err := rejectUnknownFields(object, append(common, "childNodes", "compatMode")...); err != nil {
			return nil, err
		}
		children, err := sanitizeChildNodes(object, depth)
		if err != nil {
			return nil, err
		}
		output["childNodes"] = children
		if rawCompat, ok := object["compatMode"]; ok {
			compatMode, err := decodeString(rawCompat)
			if err != nil || (compatMode != "CSS1Compat" && compatMode != "BackCompat") {
				return nil, fmt.Errorf("%w: invalid document compatibility mode", ErrInvalidReplay)
			}
			output["compatMode"] = compatMode
		}
	case 1:
		if err := rejectUnknownFields(object, append(common, "name", "publicId", "systemId")...); err != nil {
			return nil, err
		}
		name, err := requiredString(object, "name")
		if err != nil || !documentNamePattern.MatchString(name) {
			return nil, fmt.Errorf("%w: invalid document type", ErrInvalidReplay)
		}
		if _, err := requiredString(object, "publicId"); err != nil {
			return nil, err
		}
		if _, err := requiredString(object, "systemId"); err != nil {
			return nil, err
		}
		output["name"] = name
		output["publicId"] = ""
		output["systemId"] = ""
	case 2:
		if err := rejectUnknownFields(object, append(common, "tagName", "attributes", "childNodes", "isSVG", "needBlock", "isCustom")...); err != nil {
			return nil, err
		}
		tagName, err := requiredString(object, "tagName")
		if err != nil || !tagNamePattern.MatchString(tagName) {
			return nil, fmt.Errorf("%w: invalid element tag", ErrInvalidReplay)
		}
		isSVG := strings.EqualFold(tagName, "svg")
		if value, ok := object["isSVG"]; ok {
			isSVG, err = decodeBool(value)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid element marker", ErrInvalidReplay)
			}
		}
		// rrweb inlineStylesheet 把同源 CSS 写进 <link _cssText>；晚加载则先落空 link 再
		// 用 attribute mutation 补 _cssText。两层都必须转成 <style> 才能保留样式，且仍剥
		// 离 href 等网络载体（sanitizeAttributes）。无 _cssText 的空 link 也转成 style，
		// 保留节点 id，供后续 mutation 写入。
		var safeTag bool
		if !isSVG && strings.EqualFold(tagName, "link") {
			tagName = "style"
			safeTag = true
		} else {
			tagName, safeTag, isSVG = sanitizeReplayElementTag(tagName, isSVG)
		}
		attributesRaw, ok := object["attributes"]
		if !ok {
			return nil, fmt.Errorf("%w: element attributes are required", ErrInvalidReplay)
		}
		attributes, err := sanitizeAttributes(attributesRaw)
		if err != nil {
			return nil, err
		}
		if !safeTag {
			attributes = map[string]any{}
		}
		children, err := sanitizeChildNodes(object, depth)
		if err != nil {
			return nil, err
		}
		output["tagName"] = tagName
		output["attributes"] = attributes
		output["childNodes"] = children
		if isSVG {
			output["isSVG"] = true
		} else if _, ok := object["isSVG"]; ok {
			output["isSVG"] = false
		}
		if value, ok := object["needBlock"]; ok {
			parsed, err := decodeBool(value)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid element marker", ErrInvalidReplay)
			}
			output["needBlock"] = parsed
		}
		if value, ok := object["isCustom"]; ok {
			parsed, err := decodeBool(value)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid element marker", ErrInvalidReplay)
			}
			if !safeTag || isSVG {
				parsed = false
			}
			output["isCustom"] = parsed
		}
	case 3:
		if err := rejectUnknownFields(object, append(common, "textContent", "isStyle")...); err != nil {
			return nil, err
		}
		text, err := requiredString(object, "textContent")
		if err != nil {
			return nil, err
		}
		isStyle := false
		if marker, ok := object["isStyle"]; ok {
			isStyle, err = decodeBool(marker)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid style marker", ErrInvalidReplay)
			}
			output["isStyle"] = isStyle
		}
		if isStyle {
			output["textContent"] = sanitizeStylesheetCSS(text)
		} else if nodeType == 3 {
			readable, err := preserveReplayText(text)
			if err != nil {
				return nil, err
			}
			output["textContent"] = readable
		} else {
			output["textContent"] = maskReplayText(text)
		}
	case 4, 5:
		if err := rejectUnknownFields(object, append(common, "textContent")...); err != nil {
			return nil, err
		}
		text, err := requiredString(object, "textContent")
		if err != nil {
			return nil, err
		}
		output["textContent"] = maskReplayText(text)
	}
	return output, nil
}

func sanitizeChildNodes(object map[string]json.RawMessage, depth int) ([]any, error) {
	raw, ok := object["childNodes"]
	if !ok {
		return nil, fmt.Errorf("%w: rrweb childNodes are required", ErrInvalidReplay)
	}
	children, err := decodeJSONArray(raw)
	if err != nil {
		return nil, err
	}
	output := make([]any, 0, len(children))
	for _, child := range children {
		sanitized, err := sanitizeSerializedNode(child, depth+1)
		if err != nil {
			return nil, err
		}
		output = append(output, sanitized)
	}
	return output, nil
}

func sanitizeAttributes(raw json.RawMessage) (map[string]any, error) {
	attributes, err := decodeJSONObject(raw)
	if err != nil {
		return nil, err
	}
	output := make(map[string]any, len(attributes))
	for name, rawValue := range attributes {
		if !attributeNamePattern.MatchString(name) {
			return nil, fmt.Errorf("%w: invalid rrweb attribute name", ErrInvalidReplay)
		}
		lowerName := strings.ToLower(name)
		if isSensitiveAttribute(lowerName) || isRequestCapableAttribute(lowerName) || lowerName == "srcset" {
			continue
		}
		switch lowerName {
		case "class":
			value, keep, err := sanitizeReplayClass(rawValue)
			if err != nil {
				return nil, err
			}
			if keep {
				output["class"] = value
			}
			continue
		case "style":
			value, keep, err := sanitizeReplayStyle(rawValue)
			if err != nil {
				return nil, err
			}
			if keep {
				output["style"] = value
			}
			continue
		case "_csstext":
			value, keep, err := sanitizeReplayCSSText(rawValue)
			if err != nil {
				return nil, err
			}
			if keep {
				output["_cssText"] = value
			}
			continue
		}
		if _, recognized := canonicalSVGAttributeNames[lowerName]; recognized {
			canonicalName, value, keep, err := sanitizeSVGAttribute(lowerName, rawValue)
			if err != nil {
				return nil, err
			}
			if keep {
				output[canonicalName] = value
			}
			continue
		}
		if strings.HasPrefix(lowerName, "rr_") {
			value, keep, err := sanitizeRRAttribute(lowerName, rawValue)
			if err != nil {
				return nil, err
			}
			if keep {
				output[name] = value
			}
			continue
		}
		if _, ok := safeReplayAttributes[lowerName]; !ok {
			continue
		}
		value, err := decodeJSONValue(rawValue)
		if err != nil {
			return nil, err
		}
		switch typed := value.(type) {
		case nil, bool, json.Number:
			output[name] = typed
		case string:
			if len(typed) > 4096 || strings.ContainsAny(typed, "\r\n\x00") {
				return nil, fmt.Errorf("%w: invalid rrweb attribute value", ErrInvalidReplay)
			}
			output[name] = typed
		default:
			// rrweb may encode CSSOM attributes as nested objects. They are omitted
			// because opaque strings are not safe at the public ingestion boundary.
			continue
		}
	}
	return output, nil
}

func isSensitiveAttribute(name string) bool {
	return name == "value" || name == "placeholder" || name == "title" || name == "alt" ||
		name == "rr_dataurl" || strings.HasPrefix(name, "aria") || strings.HasPrefix(name, "data-")
}

func isRequestCapableAttribute(name string) bool {
	if strings.HasPrefix(name, "on") {
		return true
	}
	switch name {
	case "href", "src", "action", "formaction", "poster", "xlink:href", "rr_src", "background", "data",
		"srcdoc", "ping", "content", "http-equiv", "codebase", "archive", "manifest", "icon", "profile",
		"xmlns", "xmlns:xlink", "integrity", "nonce", "crossorigin", "referrerpolicy", "sandbox", "allow":
		return true
	default:
		return false
	}
}

func sanitizeRRAttribute(name string, raw json.RawMessage) (any, bool, error) {
	switch name {
	case "rr_mediastate":
		value, err := decodeString(raw)
		if err != nil || (value != "played" && value != "paused") {
			return nil, false, fmt.Errorf("%w: invalid rrweb media state", ErrInvalidReplay)
		}
		return value, true, nil
	case "rr_open_mode":
		value, err := decodeString(raw)
		if err != nil || (value != "modal" && value != "non-modal") {
			return nil, false, fmt.Errorf("%w: invalid rrweb dialog mode", ErrInvalidReplay)
		}
		return value, true, nil
	case "rr_mediacurrenttime", "rr_mediaplaybackrate", "rr_mediavolume", "rr_scrollleft", "rr_scrolltop":
		value, err := decodeFiniteNumber(raw)
		if err != nil {
			return nil, false, fmt.Errorf("%w: invalid rrweb numeric attribute", ErrInvalidReplay)
		}
		return value, true, nil
	case "rr_mediamuted", "rr_medialoop":
		value, err := decodeBool(raw)
		if err != nil {
			return nil, false, fmt.Errorf("%w: invalid rrweb media marker", ErrInvalidReplay)
		}
		return value, true, nil
	case "rr_width", "rr_height":
		value, err := decodeString(raw)
		if err != nil || len(value) > 64 || !rrDimensionPattern.MatchString(value) {
			return nil, false, fmt.Errorf("%w: invalid rrweb element dimension", ErrInvalidReplay)
		}
		return value, true, nil
	default:
		return nil, false, nil
	}
}

func maskReplayText(value string) string {
	if value == "" {
		return ""
	}
	return redactedReplayText
}

func preserveReplayText(value string) (string, error) {
	if len(value) > 1024*1024 || !utf8.ValidString(value) {
		return "", fmt.Errorf("%w: replay text is invalid", ErrInvalidReplay)
	}
	return value, nil
}

func sanitizeMutationData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "texts", "attributes", "removes", "adds", "isAttachIframe"); err != nil {
		return nil, err
	}
	textsRaw, err := requiredArray(object, "texts")
	if err != nil {
		return nil, err
	}
	texts := make([]any, 0, len(textsRaw))
	for _, raw := range textsRaw {
		entry, err := decodeJSONObject(raw)
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownFields(entry, "id", "value"); err != nil {
			return nil, err
		}
		id, err := requiredInteger(entry, "id", 1, maxSafeJSONInteger)
		if err != nil {
			return nil, err
		}
		valueRaw, ok := entry["value"]
		if !ok {
			return nil, fmt.Errorf("%w: mutation text value is required", ErrInvalidReplay)
		}
		var value any
		if bytes.Equal(bytes.TrimSpace(valueRaw), []byte("null")) {
			value = nil
		} else {
			text, err := decodeString(valueRaw)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid mutation text", ErrInvalidReplay)
			}
			value, err = preserveReplayText(text)
			if err != nil {
				return nil, err
			}
			if containsCSSRequestSyntax(value.(string)) {
				value = maskReplayText(text)
			}
		}
		texts = append(texts, map[string]any{"id": id, "value": value})
	}

	attributesRaw, err := requiredArray(object, "attributes")
	if err != nil {
		return nil, err
	}
	attributes := make([]any, 0, len(attributesRaw))
	for _, raw := range attributesRaw {
		entry, err := decodeJSONObject(raw)
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownFields(entry, "id", "attributes"); err != nil {
			return nil, err
		}
		id, err := requiredInteger(entry, "id", 1, maxSafeJSONInteger)
		if err != nil {
			return nil, err
		}
		valuesRaw, ok := entry["attributes"]
		if !ok {
			return nil, fmt.Errorf("%w: mutation attributes are required", ErrInvalidReplay)
		}
		values, err := sanitizeAttributes(valuesRaw)
		if err != nil {
			return nil, err
		}
		attributes = append(attributes, map[string]any{"attributes": values, "id": id})
	}

	removesRaw, err := requiredArray(object, "removes")
	if err != nil {
		return nil, err
	}
	removes := make([]any, 0, len(removesRaw))
	for _, raw := range removesRaw {
		entry, err := decodeJSONObject(raw)
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownFields(entry, "parentId", "id", "isShadow"); err != nil {
			return nil, err
		}
		parentID, err := requiredInteger(entry, "parentId", 1, maxSafeJSONInteger)
		if err != nil {
			return nil, err
		}
		id, err := requiredInteger(entry, "id", 1, maxSafeJSONInteger)
		if err != nil {
			return nil, err
		}
		output := map[string]any{"id": id, "parentId": parentID}
		if marker, ok := entry["isShadow"]; ok {
			isShadow, err := decodeBool(marker)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid mutation shadow marker", ErrInvalidReplay)
			}
			output["isShadow"] = isShadow
		}
		removes = append(removes, output)
	}

	addsRaw, err := requiredArray(object, "adds")
	if err != nil {
		return nil, err
	}
	adds := make([]any, 0, len(addsRaw))
	for _, raw := range addsRaw {
		entry, err := decodeJSONObject(raw)
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownFields(entry, "parentId", "previousId", "nextId", "node"); err != nil {
			return nil, err
		}
		parentID, err := requiredInteger(entry, "parentId", 1, maxSafeJSONInteger)
		if err != nil {
			return nil, err
		}
		nextRaw, ok := entry["nextId"]
		if !ok {
			return nil, fmt.Errorf("%w: mutation nextId is required", ErrInvalidReplay)
		}
		nextID, err := decodeNullableInteger(nextRaw, -1, maxSafeJSONInteger)
		if err != nil {
			return nil, err
		}
		nodeRaw, ok := entry["node"]
		if !ok {
			return nil, fmt.Errorf("%w: added rrweb node is required", ErrInvalidReplay)
		}
		node, err := sanitizeSerializedNode(nodeRaw, 0)
		if err != nil {
			return nil, err
		}
		output := map[string]any{"nextId": nextID, "node": node, "parentId": parentID}
		if previousRaw, ok := entry["previousId"]; ok {
			previousID, err := decodeNullableInteger(previousRaw, -1, maxSafeJSONInteger)
			if err != nil {
				return nil, err
			}
			output["previousId"] = previousID
		}
		adds = append(adds, output)
	}

	output := map[string]any{
		"adds":       adds,
		"attributes": attributes,
		"removes":    removes,
		"source":     int64(0),
		"texts":      texts,
	}
	if marker, ok := object["isAttachIframe"]; ok {
		isAttachIframe, err := decodeBool(marker)
		if err != nil {
			return nil, fmt.Errorf("%w: invalid iframe mutation marker", ErrInvalidReplay)
		}
		output["isAttachIframe"] = isAttachIframe
	}
	return output, nil
}

func sanitizeInputData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "id", "text", "isChecked", "userTriggered"); err != nil {
		return nil, err
	}
	id, err := requiredInteger(object, "id", 1, maxSafeJSONInteger)
	if err != nil {
		return nil, err
	}
	text, err := requiredString(object, "text")
	if err != nil {
		return nil, err
	}
	isChecked, err := requiredBool(object, "isChecked")
	if err != nil {
		return nil, err
	}
	output := map[string]any{
		"id":        id,
		"isChecked": isChecked,
		"source":    int64(5),
		"text":      maskReplayText(text),
	}
	if marker, ok := object["userTriggered"]; ok {
		userTriggered, err := decodeBool(marker)
		if err != nil {
			return nil, fmt.Errorf("%w: invalid input marker", ErrInvalidReplay)
		}
		output["userTriggered"] = userTriggered
	}
	return output, nil
}

func sanitizePositionData(object map[string]json.RawMessage, source int64) (any, error) {
	if err := rejectUnknownFields(object, "source", "positions"); err != nil {
		return nil, err
	}
	rawPositions, err := requiredArray(object, "positions")
	if err != nil {
		return nil, err
	}
	positions := make([]any, 0, len(rawPositions))
	for _, raw := range rawPositions {
		position, err := decodeJSONObject(raw)
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownFields(position, "x", "y", "id", "timeOffset"); err != nil {
			return nil, err
		}
		x, err := requiredFiniteNumber(position, "x")
		if err != nil {
			return nil, err
		}
		y, err := requiredFiniteNumber(position, "y")
		if err != nil {
			return nil, err
		}
		id, err := requiredInteger(position, "id", 1, maxSafeJSONInteger)
		if err != nil {
			return nil, err
		}
		timeOffset, err := requiredFiniteNumber(position, "timeOffset")
		if err != nil {
			return nil, err
		}
		positions = append(positions, map[string]any{"id": id, "timeOffset": timeOffset, "x": x, "y": y})
	}
	return map[string]any{"positions": positions, "source": source}, nil
}

func sanitizeMouseInteractionData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "type", "id", "x", "y", "pointerType"); err != nil {
		return nil, err
	}
	interactionType, err := requiredInteger(object, "type", 0, 10)
	if err != nil {
		return nil, err
	}
	id, err := requiredInteger(object, "id", 1, maxSafeJSONInteger)
	if err != nil {
		return nil, err
	}
	output := map[string]any{"id": id, "source": int64(2), "type": interactionType}
	if err := copyOptionalFiniteNumber(object, output, "x"); err != nil {
		return nil, err
	}
	if err := copyOptionalFiniteNumber(object, output, "y"); err != nil {
		return nil, err
	}
	if raw, ok := object["pointerType"]; ok {
		pointerType, err := decodeInteger(raw, 0, 2)
		if err != nil {
			return nil, fmt.Errorf("%w: invalid pointer type", ErrInvalidReplay)
		}
		output["pointerType"] = pointerType
	}
	return output, nil
}

func sanitizeScrollData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "id", "x", "y"); err != nil {
		return nil, err
	}
	id, err := requiredInteger(object, "id", 1, maxSafeJSONInteger)
	if err != nil {
		return nil, err
	}
	x, err := requiredFiniteNumber(object, "x")
	if err != nil {
		return nil, err
	}
	y, err := requiredFiniteNumber(object, "y")
	if err != nil {
		return nil, err
	}
	return map[string]any{"id": id, "source": int64(3), "x": x, "y": y}, nil
}

func sanitizeViewportData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "width", "height"); err != nil {
		return nil, err
	}
	width, err := requiredFiniteNumber(object, "width")
	if err != nil {
		return nil, err
	}
	height, err := requiredFiniteNumber(object, "height")
	if err != nil {
		return nil, err
	}
	return map[string]any{"height": height, "source": int64(4), "width": width}, nil
}

func sanitizeMediaData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "type", "id", "currentTime", "volume", "muted", "loop", "playbackRate"); err != nil {
		return nil, err
	}
	interactionType, err := requiredInteger(object, "type", 0, 4)
	if err != nil {
		return nil, err
	}
	id, err := requiredInteger(object, "id", 1, maxSafeJSONInteger)
	if err != nil {
		return nil, err
	}
	output := map[string]any{"id": id, "source": int64(7), "type": interactionType}
	for _, name := range []string{"currentTime", "volume", "playbackRate"} {
		if err := copyOptionalFiniteNumber(object, output, name); err != nil {
			return nil, err
		}
	}
	for _, name := range []string{"muted", "loop"} {
		if raw, ok := object[name]; ok {
			value, err := decodeBool(raw)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid media marker", ErrInvalidReplay)
			}
			output[name] = value
		}
	}
	return output, nil
}

func sanitizeSelectionData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "ranges"); err != nil {
		return nil, err
	}
	rawRanges, err := requiredArray(object, "ranges")
	if err != nil {
		return nil, err
	}
	ranges := make([]any, 0, len(rawRanges))
	for _, raw := range rawRanges {
		rangeObject, err := decodeJSONObject(raw)
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownFields(rangeObject, "start", "startOffset", "end", "endOffset"); err != nil {
			return nil, err
		}
		output := map[string]any{}
		for _, name := range []string{"start", "startOffset", "end", "endOffset"} {
			value, err := requiredInteger(rangeObject, name, 0, maxSafeJSONInteger)
			if err != nil {
				return nil, err
			}
			output[name] = value
		}
		ranges = append(ranges, output)
	}
	return map[string]any{"ranges": ranges, "source": int64(14)}, nil
}

func sanitizeStyleSheetRuleData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "id", "styleId", "removes", "adds", "replace", "replaceSync"); err != nil {
		return nil, err
	}
	output := map[string]any{"source": int64(8)}
	if err := copyOptionalInteger(object, output, "id", 1, maxSafeJSONInteger); err != nil {
		return nil, err
	}
	if err := copyOptionalInteger(object, output, "styleId", 1, maxSafeJSONInteger); err != nil {
		return nil, err
	}
	if raw, ok := object["removes"]; ok {
		entries, err := decodeJSONArray(raw)
		if err != nil {
			return nil, err
		}
		removes := make([]any, 0, len(entries))
		for _, entryRaw := range entries {
			entry, err := decodeJSONObject(entryRaw)
			if err != nil {
				return nil, err
			}
			if err := rejectUnknownFields(entry, "index"); err != nil {
				return nil, err
			}
			indexRaw, ok := entry["index"]
			if !ok {
				return nil, fmt.Errorf("%w: stylesheet index is required", ErrInvalidReplay)
			}
			index, err := sanitizeStyleIndex(indexRaw)
			if err != nil {
				return nil, err
			}
			removes = append(removes, map[string]any{"index": index})
		}
		output["removes"] = removes
	}
	if raw, ok := object["adds"]; ok {
		entries, err := decodeJSONArray(raw)
		if err != nil {
			return nil, err
		}
		adds := make([]any, 0, len(entries))
		for _, entryRaw := range entries {
			entry, err := decodeJSONObject(entryRaw)
			if err != nil {
				return nil, err
			}
			if err := rejectUnknownFields(entry, "rule", "index"); err != nil {
				return nil, err
			}
			rule, err := requiredString(entry, "rule")
			if err != nil {
				return nil, err
			}
			sanitizedRule, keep := sanitizeSingleCSSRule(rule)
			outputEntry := map[string]any{"rule": sanitizedRule}
			if indexRaw, ok := entry["index"]; ok {
				index, err := sanitizeStyleIndex(indexRaw)
				if err != nil {
					return nil, err
				}
				outputEntry["index"] = index
			}
			if keep {
				adds = append(adds, outputEntry)
			}
		}
		output["adds"] = adds
	}
	for _, name := range []string{"replace", "replaceSync"} {
		if raw, ok := object[name]; ok {
			value, err := decodeString(raw)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid stylesheet replacement", ErrInvalidReplay)
			}
			output[name] = sanitizeStylesheetCSS(value)
		}
	}
	return output, nil
}

func sanitizeStyleDeclarationData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "id", "styleId", "index", "set", "remove"); err != nil {
		return nil, err
	}
	output := map[string]any{"source": int64(13)}
	if err := copyOptionalInteger(object, output, "id", 1, maxSafeJSONInteger); err != nil {
		return nil, err
	}
	if err := copyOptionalInteger(object, output, "styleId", 1, maxSafeJSONInteger); err != nil {
		return nil, err
	}
	indexRaw, ok := object["index"]
	if !ok {
		return nil, fmt.Errorf("%w: style declaration index is required", ErrInvalidReplay)
	}
	index, err := sanitizeIntegerArray(indexRaw)
	if err != nil {
		return nil, err
	}
	output["index"] = index
	if raw, ok := object["set"]; ok {
		set, err := decodeJSONObject(raw)
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownFields(set, "property", "value", "priority"); err != nil {
			return nil, err
		}
		property, err := requiredString(set, "property")
		if err != nil {
			return nil, err
		}
		valueRaw, ok := set["value"]
		if !ok {
			return nil, fmt.Errorf("%w: style value is required", ErrInvalidReplay)
		}
		var value string
		if !bytes.Equal(bytes.TrimSpace(valueRaw), []byte("null")) {
			value, err = decodeString(valueRaw)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid style value", ErrInvalidReplay)
			}
		}
		priority := ""
		if rawPriority, ok := set["priority"]; ok && !bytes.Equal(bytes.TrimSpace(rawPriority), []byte("null")) {
			priority, err = decodeString(rawPriority)
			if err != nil {
				return nil, fmt.Errorf("%w: invalid style priority", ErrInvalidReplay)
			}
		}
		if !bytes.Equal(bytes.TrimSpace(valueRaw), []byte("null")) {
			property, value, priority, keep := sanitizeCSSDeclaration(property, value, priority)
			if keep {
				output["set"] = map[string]any{
					"priority": priority,
					"property": property,
					"value":    value,
				}
			}
		}
	}
	if raw, ok := object["remove"]; ok {
		remove, err := decodeJSONObject(raw)
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownFields(remove, "property"); err != nil {
			return nil, err
		}
		property, err := requiredString(remove, "property")
		if err != nil {
			return nil, err
		}
		if property, keep := normalizeReplayCSSProperty(property); keep {
			output["remove"] = map[string]any{"property": property}
		}
	}
	return output, nil
}

func sanitizeAdoptedStyleSheetData(object map[string]json.RawMessage) (any, error) {
	if err := rejectUnknownFields(object, "source", "id", "styles", "styleIds"); err != nil {
		return nil, err
	}
	id, err := requiredInteger(object, "id", 1, maxSafeJSONInteger)
	if err != nil {
		return nil, err
	}
	styleIDsRaw, err := requiredArray(object, "styleIds")
	if err != nil {
		return nil, err
	}
	styleIDs := make([]any, 0, len(styleIDsRaw))
	for _, raw := range styleIDsRaw {
		value, err := decodeInteger(raw, 1, maxSafeJSONInteger)
		if err != nil {
			return nil, err
		}
		styleIDs = append(styleIDs, value)
	}
	output := map[string]any{"id": id, "source": int64(15), "styleIds": styleIDs}
	if raw, ok := object["styles"]; ok {
		stylesRaw, err := decodeJSONArray(raw)
		if err != nil {
			return nil, err
		}
		styles := make([]any, 0, len(stylesRaw))
		for _, rawStyle := range stylesRaw {
			style, err := decodeJSONObject(rawStyle)
			if err != nil {
				return nil, err
			}
			if err := rejectUnknownFields(style, "styleId", "rules"); err != nil {
				return nil, err
			}
			styleID, err := requiredInteger(style, "styleId", 1, maxSafeJSONInteger)
			if err != nil {
				return nil, err
			}
			rulesRaw, err := requiredArray(style, "rules")
			if err != nil {
				return nil, err
			}
			rules := make([]any, 0, len(rulesRaw))
			for _, ruleRaw := range rulesRaw {
				rule, err := decodeJSONObject(ruleRaw)
				if err != nil {
					return nil, err
				}
				if err := rejectUnknownFields(rule, "rule", "index"); err != nil {
					return nil, err
				}
				ruleText, err := requiredString(rule, "rule")
				if err != nil {
					return nil, err
				}
				sanitizedRule, keep := sanitizeSingleCSSRule(ruleText)
				outputRule := map[string]any{"rule": sanitizedRule}
				if indexRaw, ok := rule["index"]; ok {
					index, err := sanitizeStyleIndex(indexRaw)
					if err != nil {
						return nil, err
					}
					outputRule["index"] = index
				}
				if keep {
					rules = append(rules, outputRule)
				}
			}
			styles = append(styles, map[string]any{"rules": rules, "styleId": styleID})
		}
		output["styles"] = styles
	}
	return output, nil
}

func sanitizeStyleIndex(raw json.RawMessage) (any, error) {
	if value, err := decodeInteger(raw, 0, maxSafeJSONInteger); err == nil {
		return value, nil
	}
	return sanitizeIntegerArray(raw)
}

func sanitizeIntegerArray(raw json.RawMessage) ([]any, error) {
	values, err := decodeJSONArray(raw)
	if err != nil {
		return nil, err
	}
	output := make([]any, 0, len(values))
	for _, rawValue := range values {
		value, err := decodeInteger(rawValue, 0, maxSafeJSONInteger)
		if err != nil {
			return nil, err
		}
		output = append(output, value)
	}
	return output, nil
}

func decodeJSONObject(raw json.RawMessage) (map[string]json.RawMessage, error) {
	var object map[string]json.RawMessage
	decoder := json.NewDecoder(bytes.NewReader(raw))
	if err := decoder.Decode(&object); err != nil || object == nil {
		return nil, fmt.Errorf("%w: rrweb object is malformed", ErrInvalidReplay)
	}
	if err := requireJSONEOF(decoder); err != nil {
		return nil, err
	}
	return object, nil
}

func decodeJSONArray(raw json.RawMessage) ([]json.RawMessage, error) {
	var array []json.RawMessage
	decoder := json.NewDecoder(bytes.NewReader(raw))
	if err := decoder.Decode(&array); err != nil || array == nil {
		return nil, fmt.Errorf("%w: rrweb array is malformed", ErrInvalidReplay)
	}
	if err := requireJSONEOF(decoder); err != nil {
		return nil, err
	}
	return array, nil
}

func decodeJSONValue(raw json.RawMessage) (any, error) {
	var value any
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		return nil, fmt.Errorf("%w: rrweb value is malformed", ErrInvalidReplay)
	}
	if err := requireJSONEOF(decoder); err != nil {
		return nil, err
	}
	return value, nil
}

func rejectUnknownFields(object map[string]json.RawMessage, allowed ...string) error {
	allowedSet := make(map[string]struct{}, len(allowed))
	for _, name := range allowed {
		allowedSet[name] = struct{}{}
	}
	for name := range object {
		if _, ok := allowedSet[name]; !ok {
			return fmt.Errorf("%w: unknown rrweb field %q", ErrInvalidReplay, name)
		}
	}
	return nil
}

func requiredArray(object map[string]json.RawMessage, name string) ([]json.RawMessage, error) {
	raw, ok := object[name]
	if !ok {
		return nil, fmt.Errorf("%w: rrweb field %q is required", ErrInvalidReplay, name)
	}
	return decodeJSONArray(raw)
}

func requiredInteger(object map[string]json.RawMessage, name string, minimum, maximum int64) (int64, error) {
	raw, ok := object[name]
	if !ok {
		return 0, fmt.Errorf("%w: rrweb field %q is required", ErrInvalidReplay, name)
	}
	value, err := decodeInteger(raw, minimum, maximum)
	if err != nil {
		return 0, fmt.Errorf("%w: rrweb field %q must be an integer", ErrInvalidReplay, name)
	}
	return value, nil
}

func decodeInteger(raw json.RawMessage, minimum, maximum int64) (int64, error) {
	var number json.Number
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&number); err != nil {
		return 0, err
	}
	if err := requireJSONEOF(decoder); err != nil {
		return 0, err
	}
	value, err := number.Int64()
	if err != nil || value < minimum || value > maximum {
		return 0, fmt.Errorf("integer outside bounds")
	}
	return value, nil
}

func decodeNullableInteger(raw json.RawMessage, minimum, maximum int64) (any, error) {
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return nil, nil
	}
	value, err := decodeInteger(raw, minimum, maximum)
	if err != nil {
		return nil, fmt.Errorf("%w: invalid nullable rrweb identity", ErrInvalidReplay)
	}
	return value, nil
}

func requiredFiniteNumber(object map[string]json.RawMessage, name string) (json.Number, error) {
	raw, ok := object[name]
	if !ok {
		return "", fmt.Errorf("%w: rrweb field %q is required", ErrInvalidReplay, name)
	}
	value, err := decodeFiniteNumber(raw)
	if err != nil {
		return "", fmt.Errorf("%w: rrweb field %q must be finite", ErrInvalidReplay, name)
	}
	return value, nil
}

func decodeFiniteNumber(raw json.RawMessage) (json.Number, error) {
	var number json.Number
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&number); err != nil {
		return "", err
	}
	if err := requireJSONEOF(decoder); err != nil {
		return "", err
	}
	value, err := number.Float64()
	if err != nil || math.IsNaN(value) || math.IsInf(value, 0) {
		return "", fmt.Errorf("number is not finite")
	}
	return number, nil
}

func requiredString(object map[string]json.RawMessage, name string) (string, error) {
	raw, ok := object[name]
	if !ok {
		return "", fmt.Errorf("%w: rrweb field %q is required", ErrInvalidReplay, name)
	}
	value, err := decodeString(raw)
	if err != nil {
		return "", fmt.Errorf("%w: rrweb field %q must be a string", ErrInvalidReplay, name)
	}
	return value, nil
}

func decodeString(raw json.RawMessage) (string, error) {
	var value string
	decoder := json.NewDecoder(bytes.NewReader(raw))
	if err := decoder.Decode(&value); err != nil {
		return "", err
	}
	if err := requireJSONEOF(decoder); err != nil {
		return "", err
	}
	return value, nil
}

func requiredBool(object map[string]json.RawMessage, name string) (bool, error) {
	raw, ok := object[name]
	if !ok {
		return false, fmt.Errorf("%w: rrweb field %q is required", ErrInvalidReplay, name)
	}
	value, err := decodeBool(raw)
	if err != nil {
		return false, fmt.Errorf("%w: rrweb field %q must be a boolean", ErrInvalidReplay, name)
	}
	return value, nil
}

func decodeBool(raw json.RawMessage) (bool, error) {
	var value bool
	decoder := json.NewDecoder(bytes.NewReader(raw))
	if err := decoder.Decode(&value); err != nil {
		return false, err
	}
	if err := requireJSONEOF(decoder); err != nil {
		return false, err
	}
	return value, nil
}

func copyOptionalFiniteNumber(object map[string]json.RawMessage, output map[string]any, name string) error {
	raw, ok := object[name]
	if !ok {
		return nil
	}
	value, err := decodeFiniteNumber(raw)
	if err != nil {
		return fmt.Errorf("%w: rrweb field %q must be finite", ErrInvalidReplay, name)
	}
	output[name] = value
	return nil
}

func copyOptionalInteger(
	object map[string]json.RawMessage,
	output map[string]any,
	name string,
	minimum int64,
	maximum int64,
) error {
	raw, ok := object[name]
	if !ok {
		return nil
	}
	value, err := decodeInteger(raw, minimum, maximum)
	if err != nil {
		return fmt.Errorf("%w: rrweb field %q must be an integer", ErrInvalidReplay, name)
	}
	output[name] = value
	return nil
}

package rumreplayreceiver

import (
	"bytes"
	"encoding/json"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

const (
	maxReplayClassBytes  = 2 * 1024
	maxReplayClassTokens = 64
	maxReplayClassToken  = 128
	maxSVGValueBytes     = 16 * 1024
)

var safeSVGTags = map[string]string{
	"circle":         "circle",
	"clippath":       "clipPath",
	"defs":           "defs",
	"ellipse":        "ellipse",
	"g":              "g",
	"line":           "line",
	"lineargradient": "linearGradient",
	"path":           "path",
	"polygon":        "polygon",
	"polyline":       "polyline",
	"radialgradient": "radialGradient",
	"rect":           "rect",
	"stop":           "stop",
	"svg":            "svg",
	"text":           "text",
	"tspan":          "tspan",
}

var canonicalSVGAttributeNames = map[string]string{
	"alignment-baseline":  "alignment-baseline",
	"cx":                  "cx",
	"cy":                  "cy",
	"d":                   "d",
	"dominant-baseline":   "dominant-baseline",
	"dx":                  "dx",
	"dy":                  "dy",
	"fill":                "fill",
	"fill-opacity":        "fill-opacity",
	"fill-rule":           "fill-rule",
	"font-family":         "font-family",
	"font-size":           "font-size",
	"font-style":          "font-style",
	"font-weight":         "font-weight",
	"gradienttransform":   "gradientTransform",
	"gradientunits":       "gradientUnits",
	"height":              "height",
	"lengthadjust":        "lengthAdjust",
	"offset":              "offset",
	"opacity":             "opacity",
	"paint-order":         "paint-order",
	"pathlength":          "pathLength",
	"points":              "points",
	"preserveaspectratio": "preserveAspectRatio",
	"r":                   "r",
	"rx":                  "rx",
	"ry":                  "ry",
	"shape-rendering":     "shape-rendering",
	"spreadmethod":        "spreadMethod",
	"stop-color":          "stop-color",
	"stop-opacity":        "stop-opacity",
	"stroke":              "stroke",
	"stroke-dasharray":    "stroke-dasharray",
	"stroke-dashoffset":   "stroke-dashoffset",
	"stroke-linecap":      "stroke-linecap",
	"stroke-linejoin":     "stroke-linejoin",
	"stroke-miterlimit":   "stroke-miterlimit",
	"stroke-opacity":      "stroke-opacity",
	"stroke-width":        "stroke-width",
	"text-anchor":         "text-anchor",
	"textlength":          "textLength",
	"transform":           "transform",
	"transform-origin":    "transform-origin",
	"vector-effect":       "vector-effect",
	"viewbox":             "viewBox",
	"visibility":          "visibility",
	"width":               "width",
	"x":                   "x",
	"x1":                  "x1",
	"x2":                  "x2",
	"y":                   "y",
	"y1":                  "y1",
	"y2":                  "y2",
}

var svgPaintProperties = map[string]struct{}{
	"alignment-baseline": {}, "dominant-baseline": {}, "fill": {}, "fill-opacity": {},
	"fill-rule": {}, "font-family": {}, "font-size": {}, "font-style": {}, "font-weight": {},
	"opacity": {}, "paint-order": {}, "shape-rendering": {}, "stop-color": {}, "stop-opacity": {},
	"stroke": {}, "stroke-dasharray": {}, "stroke-dashoffset": {}, "stroke-linecap": {},
	"stroke-linejoin": {}, "stroke-miterlimit": {}, "stroke-opacity": {}, "stroke-width": {},
	"text-anchor": {}, "transform-origin": {}, "vector-effect": {}, "visibility": {},
}

var svgLengthAttributes = map[string]struct{}{
	"cx": {}, "cy": {}, "dx": {}, "dy": {}, "height": {}, "offset": {}, "pathlength": {},
	"r": {}, "rx": {}, "ry": {}, "textlength": {}, "width": {}, "x": {}, "x1": {},
	"x2": {}, "y": {}, "y1": {}, "y2": {},
}

func sanitizeReplayClass(raw json.RawMessage) (any, bool, error) {
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return nil, true, nil
	}
	value, err := decodeString(raw)
	if err != nil {
		return nil, false, nil
	}
	if len(value) == 0 || len(value) > maxReplayClassBytes || !utf8.ValidString(value) {
		return nil, false, nil
	}
	for _, r := range value {
		if unicode.IsControl(r) || !unicode.IsPrint(r) {
			return nil, false, nil
		}
	}
	tokens := strings.Fields(value)
	if len(tokens) == 0 || len(tokens) > maxReplayClassTokens {
		return nil, false, nil
	}
	for _, token := range tokens {
		if len(token) == 0 || len(token) > maxReplayClassToken {
			return nil, false, nil
		}
	}
	normalized := strings.Join(tokens, " ")
	if len(normalized) > maxReplayClassBytes {
		return nil, false, nil
	}
	return normalized, true, nil
}

func sanitizeReplayStyle(raw json.RawMessage) (any, bool, error) {
	trimmed := bytes.TrimSpace(raw)
	if bytes.Equal(trimmed, []byte("null")) {
		return nil, true, nil
	}
	if len(trimmed) == 0 {
		return nil, false, nil
	}
	if trimmed[0] == '"' {
		value, err := decodeString(raw)
		if err != nil {
			return nil, false, err
		}
		return sanitizeInlineCSS(value), true, nil
	}
	if trimmed[0] != '{' {
		return nil, false, nil
	}
	object, err := decodeJSONObject(raw)
	if err != nil {
		return nil, false, err
	}
	output := make(map[string]any, len(object))
	for rawProperty, rawValue := range object {
		property, ok := normalizeReplayCSSProperty(rawProperty)
		if !ok {
			continue
		}
		value, keep := sanitizeReplayStyleValue(property, rawValue)
		if keep {
			output[property] = value
		}
	}
	return output, true, nil
}

func sanitizeReplayStyleValue(property string, raw json.RawMessage) (any, bool) {
	trimmed := bytes.TrimSpace(raw)
	if bytes.Equal(trimmed, []byte("false")) {
		return false, true
	}
	if len(trimmed) == 0 {
		return nil, false
	}
	if trimmed[0] == '"' {
		value, err := decodeString(raw)
		if err != nil {
			return nil, false
		}
		_, normalized, _, ok := sanitizeCSSDeclaration(property, value, "")
		return normalized, ok
	}
	if trimmed[0] != '[' {
		return nil, false
	}
	values, err := decodeJSONArray(raw)
	if err != nil || len(values) != 2 {
		return nil, false
	}
	value, err := decodeString(values[0])
	if err != nil {
		return nil, false
	}
	priority, err := decodeString(values[1])
	if err != nil {
		return nil, false
	}
	_, normalized, normalizedPriority, ok := sanitizeCSSDeclaration(property, value, priority)
	if !ok {
		return nil, false
	}
	return []any{normalized, normalizedPriority}, true
}

func sanitizeReplayCSSText(raw json.RawMessage) (any, bool, error) {
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return nil, true, nil
	}
	value, err := decodeString(raw)
	if err != nil {
		return nil, false, nil
	}
	return sanitizeStylesheetCSS(value), true, nil
}

func sanitizeReplayElementTag(tagName string, isSVG bool) (string, bool, bool) {
	lowerName := strings.ToLower(tagName)
	if isSVG || lowerName == "svg" {
		if canonical, ok := safeSVGTags[lowerName]; ok {
			return canonical, true, true
		}
		return "g", false, true
	}
	if _, ok := safeReplayElementTags[lowerName]; ok {
		return lowerName, true, false
	}
	return "div", false, false
}

func sanitizeSVGAttribute(name string, raw json.RawMessage) (string, any, bool, error) {
	canonical, recognized := canonicalSVGAttributeNames[name]
	if !recognized {
		return "", nil, false, nil
	}
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return canonical, nil, true, nil
	}
	value, err := decodeString(raw)
	if err != nil || len(value) == 0 || len(value) > maxSVGValueBytes || !utf8.ValidString(value) {
		return "", nil, false, nil
	}

	switch name {
	case "d":
		if !validSVGPath(value) {
			return "", nil, false, nil
		}
		return canonical, value, true, nil
	case "points":
		if count, ok := validSVGNumberSequence(value, true); !ok || count < 4 || count%2 != 0 {
			return "", nil, false, nil
		}
		return canonical, normalizeSVGSpaces(value), true, nil
	case "viewbox":
		if count, ok := validSVGNumberSequence(value, false); !ok || count != 4 {
			return "", nil, false, nil
		}
		return canonical, normalizeSVGSpaces(value), true, nil
	case "preserveaspectratio":
		if !validPreserveAspectRatio(value) {
			return "", nil, false, nil
		}
		return canonical, strings.Join(strings.Fields(value), " "), true, nil
	case "gradienttransform", "transform":
		_, normalized, _, ok := sanitizeCSSDeclaration("transform", value, "")
		if !ok {
			return "", nil, false, nil
		}
		return canonical, normalized, true, nil
	case "gradientunits":
		if value != "userSpaceOnUse" && value != "objectBoundingBox" {
			return "", nil, false, nil
		}
		return canonical, value, true, nil
	case "spreadmethod":
		if value != "pad" && value != "reflect" && value != "repeat" {
			return "", nil, false, nil
		}
		return canonical, value, true, nil
	case "lengthadjust":
		if value != "spacing" && value != "spacingAndGlyphs" {
			return "", nil, false, nil
		}
		return canonical, value, true, nil
	}

	if _, ok := svgLengthAttributes[name]; ok {
		if count, valid := validSVGNumberSequence(value, true); !valid || count != 1 {
			return "", nil, false, nil
		}
		return canonical, strings.TrimSpace(value), true, nil
	}
	if _, ok := svgPaintProperties[name]; ok {
		_, normalized, _, valid := sanitizeCSSDeclaration(name, value, "")
		if !valid {
			return "", nil, false, nil
		}
		return canonical, normalized, true, nil
	}
	return "", nil, false, nil
}

func validSVGPath(value string) bool {
	if len(value) == 0 || len(value) > maxSVGValueBytes || !utf8.ValidString(value) {
		return false
	}
	hasCommand := false
	for _, r := range value {
		switch {
		case strings.ContainsRune("MmZzLlHhVvCcSsQqTtAa", r):
			hasCommand = true
		case '0' <= r && r <= '9', r == ' ', r == '\t', r == '\n', r == '\r', r == '\f',
			r == ',', r == '+', r == '-', r == '.', r == 'e', r == 'E':
		default:
			return false
		}
	}
	return hasCommand
}

func validSVGNumberSequence(value string, allowPercent bool) (int, bool) {
	count := 0
	for index := 0; index < len(value); {
		for index < len(value) && isSVGSeparator(value[index]) {
			index++
		}
		if index == len(value) {
			break
		}
		start := index
		if value[index] == '+' || value[index] == '-' {
			index++
		}
		digits := 0
		for index < len(value) && '0' <= value[index] && value[index] <= '9' {
			index++
			digits++
		}
		if index < len(value) && value[index] == '.' {
			index++
			for index < len(value) && '0' <= value[index] && value[index] <= '9' {
				index++
				digits++
			}
		}
		if digits == 0 {
			return 0, false
		}
		if index < len(value) && (value[index] == 'e' || value[index] == 'E') {
			index++
			if index < len(value) && (value[index] == '+' || value[index] == '-') {
				index++
			}
			exponentDigits := 0
			for index < len(value) && '0' <= value[index] && value[index] <= '9' {
				index++
				exponentDigits++
			}
			if exponentDigits == 0 {
				return 0, false
			}
		}
		if allowPercent && index < len(value) && value[index] == '%' {
			index++
		}
		number := strings.TrimSuffix(value[start:index], "%")
		parsed, err := strconv.ParseFloat(number, 64)
		if err != nil || parsed != parsed || parsed > 1.7976931348623157e+308 || parsed < -1.7976931348623157e+308 {
			return 0, false
		}
		count++
		if index < len(value) && !isSVGSeparator(value[index]) && value[index] != '+' && value[index] != '-' {
			return 0, false
		}
	}
	return count, count > 0
}

func validPreserveAspectRatio(value string) bool {
	parts := strings.Fields(value)
	if len(parts) == 0 || len(parts) > 3 {
		return false
	}
	index := 0
	if parts[index] == "defer" {
		index++
	}
	if index >= len(parts) {
		return false
	}
	alignment := parts[index]
	index++
	if alignment != "none" && !isSVGAlignment(alignment) {
		return false
	}
	if index < len(parts) {
		if alignment == "none" || parts[index] != "meet" && parts[index] != "slice" {
			return false
		}
		index++
	}
	return index == len(parts)
}

func isSVGAlignment(value string) bool {
	switch value {
	case "xMinYMin", "xMidYMin", "xMaxYMin", "xMinYMid", "xMidYMid", "xMaxYMid",
		"xMinYMax", "xMidYMax", "xMaxYMax":
		return true
	default:
		return false
	}
}

func normalizeSVGSpaces(value string) string {
	return strings.Join(strings.FieldsFunc(value, func(r rune) bool {
		return unicode.IsSpace(r) || r == ','
	}), " ")
}

func isSVGSeparator(value byte) bool {
	return value == ' ' || value == '\t' || value == '\n' || value == '\r' || value == '\f' || value == ','
}

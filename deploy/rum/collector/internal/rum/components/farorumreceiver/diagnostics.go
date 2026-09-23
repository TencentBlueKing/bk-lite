package farorumreceiver

import (
	"crypto/sha256"
	"encoding/hex"
	"net/url"
	"regexp"
	"strings"
	"unicode"
)

type diagnosticKind string

const (
	diagnosticTemplate    diagnosticKind = "template"
	diagnosticFingerprint diagnosticKind = "fingerprint"

	trafficHuman     = "human"
	trafficUnknown   = "unknown"
	trafficCrawler   = "crawler"
	trafficSynthetic = "synthetic"
)

type sanitizedDiagnostic struct {
	Value string
	Kind  diagnosticKind
}

var (
	// *Error / *Exception 前缀进入模板通道；自由文本仍回落 fingerprint。
	knownErrorTemplatePattern = regexp.MustCompile(`(?i)^(?:uncaught\s+)?(?:[A-Za-z][A-Za-z0-9_$]*)?(?:Error|Exception)\s*:`)
	knownBrowserErrorPattern  = regexp.MustCompile(`(?i)^(?:loading (?:css )?chunk\b|failed to fetch\b|script error\.?$|resizeobserver loop\b|non-error promise rejection\b)`)
	jwtPattern                = regexp.MustCompile(`\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b`)
	cardOrLongNumberPattern   = regexp.MustCompile(`\b(?:\d[ -]?){9,19}\b`)
	// 明确 +国家码，或连续 10–15 位本地号；避免日期 / 短订单号误伤。
	phonePattern             = regexp.MustCompile(`(?:\+\d{1,3}(?:[-.\s]?\d{1,4}){2,5}|\b\d{10,15}\b)`)
	longHexPattern           = regexp.MustCompile(`(?i)\b[0-9a-f]{16,}\b`)
	uuidAnywherePattern      = regexp.MustCompile(`(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b`)
	embeddedDynamicIDPattern = regexp.MustCompile(`(?i)(?:[0-9]{6,}|[0-9a-f]{16,}|[0-9a-f]{8}-[0-9a-f-]{27,})`)
	quotedValuePattern       = regexp.MustCompile(`(["'])([^"'\r\n]{1,160})(["'])`)
	httpURLPattern           = regexp.MustCompile(`https?://[^\s"'<>]+`)
	cssAttributePattern      = regexp.MustCompile(`\[[^\]\r\n]{1,256}\]`)
	cssIDPattern             = regexp.MustCompile(`#[A-Za-z_][A-Za-z0-9_-]*`)
	cssOrdinalPattern        = regexp.MustCompile(`(?i):(?:nth-(?:child|of-type)|first-child|last-child)\([^)]*\)|:(?:first-child|last-child)`)
	cssTokenPattern          = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,63}$`)
	crawlerUAPattern         = regexp.MustCompile(`(?i)(?:googlebot|bingbot|baiduspider|yandexbot|duckduckbot|slurp|facebookexternalhit|twitterbot|applebot|crawler|spider|bot\b)`)
	syntheticUAPattern       = regexp.MustCompile(`(?i)(?:headlesschrome|lighthouse|playwright|selenium|webdriver|webpagetest|puppeteer|k6-browser|synthetic)`)
)

func sanitizeErrorMessage(raw string) sanitizedDiagnostic {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return sanitizedDiagnostic{}
	}
	// Faro console instrumentation prefixes messages with "console.error: ", which
	// would otherwise fail the *Error: template gate and fall back to fingerprint.
	trimmed = stripConsoleErrorPrefix(trimmed)
	if !knownErrorTemplatePattern.MatchString(trimmed) && !knownBrowserErrorPattern.MatchString(trimmed) {
		return sanitizedDiagnostic{Value: privacyLabel("message", trimmed), Kind: diagnosticFingerprint}
	}

	value := httpURLPattern.ReplaceAllStringFunc(trimmed, sanitizeNetworkURL)
	value = secretTextPattern.ReplaceAllString(value, "$1=[redacted]")
	value = jwtPattern.ReplaceAllString(value, ":secret")
	value = emailPattern.ReplaceAllString(value, ":email")
	value = quotedValuePattern.ReplaceAllStringFunc(value, func(quoted string) string {
		if len(quoted) < 2 {
			return quoted
		}
		content := embeddedDynamicIDPattern.ReplaceAllString(quoted[1:len(quoted)-1], ":id")
		sanitized := sanitizeDeveloperLabel(content, 128)
		if strings.HasPrefix(sanitized, "label:") {
			sanitized = ":text"
		}
		return quoted[:1] + sanitized + quoted[len(quoted)-1:]
	})
	value = uuidAnywherePattern.ReplaceAllString(value, ":id")
	value = longHexPattern.ReplaceAllString(value, ":id")
	value = cardOrLongNumberPattern.ReplaceAllString(value, ":id")
	value = phonePattern.ReplaceAllStringFunc(value, func(candidate string) string {
		digits := 0
		for _, r := range candidate {
			if unicode.IsDigit(r) {
				digits++
			}
		}
		if digits >= 10 {
			return ":id"
		}
		return candidate
	})
	return sanitizedDiagnostic{Value: truncateUTF8(value, 1024), Kind: diagnosticTemplate}
}

func stripConsoleErrorPrefix(value string) string {
	const prefix = "console.error:"
	if len(value) < len(prefix) {
		return value
	}
	if strings.EqualFold(value[:len(prefix)], prefix) {
		return strings.TrimSpace(value[len(prefix):])
	}
	return value
}

// sanitizePathSegment 对页面 / 网络 / Trace URL 与 route 共用同一套段级规则：
// 动态标识 → :id，可读静态段（含 Unicode 与 name.ext）保留，其余不安全段 → :text。
func sanitizePathSegment(decoded string) string {
	if decoded == "" || strings.ContainsAny(decoded, `/\`) {
		return ":text"
	}
	if isOpaqueRouteID(decoded) ||
		emailPattern.MatchString(decoded) ||
		secretTextPattern.MatchString(decoded) ||
		jwtPattern.MatchString(decoded) ||
		cardOrLongNumberPattern.MatchString(decoded) {
		return ":id"
	}
	for _, r := range decoded {
		if unicode.IsLetter(r) || unicode.IsNumber(r) || strings.ContainsRune("@+._:/-", r) {
			continue
		}
		return ":text"
	}
	return truncateUTF8(decoded, 64)
}

func sanitizeNetworkURL(raw string) string {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || (parsed.IsAbs() && parsed.Scheme != "http" && parsed.Scheme != "https") {
		return ""
	}
	parsed.User = nil
	parsed.RawQuery = ""
	parsed.ForceQuery = false
	parsed.Fragment = ""
	segments := strings.Split(strings.Trim(parsed.EscapedPath(), "/"), "/")
	if len(segments) == 1 && segments[0] == "" {
		parsed.Path = "/"
		parsed.RawPath = ""
		return truncateUTF8(parsed.String(), 2048)
	}
	for index, segment := range segments {
		decoded, decodeErr := url.PathUnescape(segment)
		if decodeErr != nil {
			segments[index] = ":text"
			continue
		}
		segments[index] = sanitizePathSegment(decoded)
	}
	path := "/" + strings.Join(segments, "/")
	// 直接拼接 path，避免 url.URL.String() 把可读 Unicode 静态段再 percent-encode。
	if parsed.Scheme != "" && parsed.Host != "" {
		return truncateUTF8(parsed.Scheme+"://"+parsed.Host+path, 2048)
	}
	return truncateUTF8(path, 2048)
}

func sanitizeWebVitalSelector(raw string) sanitizedDiagnostic {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return sanitizedDiagnostic{}
	}
	if strings.ContainsAny(trimmed, "\r\n{};") || !regexp.MustCompile(`[A-Za-z]`).MatchString(trimmed) {
		return sanitizedDiagnostic{Value: privacyLabel("selector", trimmed), Kind: diagnosticFingerprint}
	}
	value := cssAttributePattern.ReplaceAllString(trimmed, "")
	value = cssIDPattern.ReplaceAllString(value, "")
	value = cssOrdinalPattern.ReplaceAllString(value, "")
	parts := strings.Fields(value)
	for index, part := range parts {
		if part == ">" || part == "+" || part == "~" {
			continue
		}
		tokens := strings.Split(part, ".")
		if !cssTokenPattern.MatchString(tokens[0]) {
			return sanitizedDiagnostic{Value: privacyLabel("selector", trimmed), Kind: diagnosticFingerprint}
		}
		kept := []string{strings.ToLower(tokens[0])}
		for _, token := range tokens[1:] {
			if cssTokenPattern.MatchString(token) && !embeddedDynamicIDPattern.MatchString(token) {
				kept = append(kept, token)
			}
		}
		parts[index] = strings.Join(kept, ".")
	}
	result := strings.Join(parts, " ")
	if result == "" {
		return sanitizedDiagnostic{Value: privacyLabel("selector", trimmed), Kind: diagnosticFingerprint}
	}
	return sanitizedDiagnostic{Value: truncateUTF8(result, 512), Kind: diagnosticTemplate}
}

func sanitizeDeveloperLabel(raw string, limit int) string {
	value := strings.TrimSpace(raw)
	if value == "" {
		return ""
	}
	if emailPattern.MatchString(value) || secretTextPattern.MatchString(value) || jwtPattern.MatchString(value) || cardOrLongNumberPattern.MatchString(value) {
		return privacyLabel("label", value)
	}
	for _, r := range value {
		if unicode.IsLetter(r) || unicode.IsNumber(r) || strings.ContainsRune("@+._:/-", r) {
			continue
		}
		return privacyLabel("label", value)
	}
	return truncateUTF8(value, limit)
}

func safeJSSymbol(raw string) string {
	value := strings.TrimSpace(raw)
	if value == "" || len(value) > 256 || !regexp.MustCompile(`^[A-Za-z_$][A-Za-z0-9_$.<>:/\-\[\]]*$`).MatchString(value) {
		return ""
	}
	if emailPattern.MatchString(value) || secretTextPattern.MatchString(value) {
		return privacyLabel("symbol", value)
	}
	return value
}

func stableErrorGroupKey(application, errorType string, message sanitizedDiagnostic, clientFingerprint, keyFrame string) string {
	if value := strings.TrimSpace(clientFingerprint); value != "" {
		return privacyLabel("error-group", value)
	}
	material := strings.Join([]string{application, errorType, string(message.Kind), message.Value, keyFrame}, "\x00")
	digest := sha256.Sum256([]byte(material))
	return hex.EncodeToString(digest[:])
}

func classifyTraffic(userAgent string) string {
	userAgent = strings.TrimSpace(userAgent)
	switch {
	case userAgent == "":
		return trafficUnknown
	case syntheticUAPattern.MatchString(userAgent):
		return trafficSynthetic
	case crawlerUAPattern.MatchString(userAgent):
		return trafficCrawler
	default:
		return trafficHuman
	}
}

package main

import (
	"strconv"
	"strings"
)

type healthMetrics struct {
	Up          int
	Duration    float64
	ExitCode    int
	ParseErrors int
	Truncated   int
}

func renderPrometheus(userStdout []byte, maxBytes, maxSeries int, health healthMetrics) string {
	normalized, parseErrors, truncated := normalizeUserMetrics(userStdout, maxBytes, maxSeries)
	if parseErrors > health.ParseErrors {
		health.ParseErrors = parseErrors
	}
	if truncated {
		health.Truncated = 1
	}

	var b strings.Builder
	if normalized != "" {
		b.WriteString(normalized)
		if !strings.HasSuffix(normalized, "\n") {
			b.WriteByte('\n')
		}
	}
	writeGauge(&b, "bklite_script_up", float64(health.Up))
	writeGauge(&b, "bklite_script_duration_seconds", health.Duration)
	writeGauge(&b, "bklite_script_exit_code", float64(health.ExitCode))
	writeGauge(&b, "bklite_script_parse_errors", float64(health.ParseErrors))
	writeGauge(&b, "bklite_script_truncated", float64(health.Truncated))
	return b.String()
}

func writeGauge(b *strings.Builder, name string, value float64) {
	b.WriteString("# TYPE ")
	b.WriteString(name)
	b.WriteString(" gauge\n")
	b.WriteString(name)
	b.WriteByte(' ')
	b.WriteString(formatValue(value))
	b.WriteByte('\n')
}

func formatValue(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}

func normalizeUserMetrics(raw []byte, maxBytes, maxSeries int) (string, int, bool) {
	text := string(raw)
	if maxBytes > 0 && len(text) > maxBytes {
		text = text[:maxBytes]
	}
	truncated := maxBytes > 0 && len(raw) > maxBytes

	types := map[string]string{}
	var series []string
	seen := map[string]struct{}{}
	parseErrors := 0
	seriesCount := 0

	for _, line := range strings.Split(text, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		if strings.HasPrefix(trimmed, "#") {
			name, metricType, ok := parseTypeLine(trimmed)
			if ok {
				types[name] = metricType
			}
			continue
		}
		name, identity, ok := parseSampleLine(trimmed)
		if !ok {
			parseErrors++
			continue
		}
		if _, exists := seen[identity]; exists {
			continue
		}
		if seriesCount >= maxSeries {
			truncated = true
			continue
		}
		seen[identity] = struct{}{}
		series = append(series, trimmed)
		seriesCount++
		if _, exists := types[name]; !exists {
			types[name] = "gauge"
		}
	}

	var b strings.Builder
	writtenTypes := map[string]struct{}{}
	for _, sample := range series {
		name, _, _ := parseSampleLine(sample)
		if _, done := writtenTypes[name]; !done {
			metricType := types[name]
			if metricType == "" {
				metricType = "gauge"
			}
			b.WriteString("# TYPE ")
			b.WriteString(name)
			b.WriteByte(' ')
			b.WriteString(metricType)
			b.WriteByte('\n')
			writtenTypes[name] = struct{}{}
		}
		b.WriteString(sample)
		b.WriteByte('\n')
	}
	return strings.TrimSuffix(b.String(), "\n"), parseErrors, truncated
}

func parseTypeLine(line string) (string, string, bool) {
	rest := strings.TrimSpace(strings.TrimPrefix(line, "#"))
	fields := strings.Fields(rest)
	if len(fields) < 3 || !strings.EqualFold(fields[0], "TYPE") {
		return "", "", false
	}
	return fields[1], fields[2], true
}

func parseSampleLine(line string) (name, identity string, ok bool) {
	if strings.HasPrefix(line, "#") {
		return "", "", false
	}
	namePart := line
	labels := ""
	if i := strings.IndexByte(line, '{'); i >= 0 {
		end := strings.LastIndexByte(line, '}')
		if end <= i {
			return "", "", false
		}
		namePart = line[:i]
		labels = line[i : end+1]
		line = strings.TrimSpace(line[end+1:])
	} else {
		fields := strings.Fields(line)
		if len(fields) < 2 {
			return "", "", false
		}
		namePart = fields[0]
		line = strings.Join(fields[1:], " ")
	}
	namePart = strings.TrimSpace(namePart)
	if !isMetricName(namePart) {
		return "", "", false
	}
	valueFields := strings.Fields(line)
	if len(valueFields) < 1 || len(valueFields) > 2 {
		return "", "", false
	}
	if !isMetricValue(valueFields[0]) {
		return "", "", false
	}
	return namePart, namePart + labels, true
}

func isMetricName(name string) bool {
	if name == "" {
		return false
	}
	for i, r := range name {
		ok := (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || r == '_' || r == ':'
		if i > 0 {
			ok = ok || (r >= '0' && r <= '9')
		}
		if !ok {
			return false
		}
	}
	return true
}

func isMetricValue(value string) bool {
	switch strings.ToLower(value) {
	case "nan", "+inf", "-inf", "inf":
		return true
	}
	_, err := strconv.ParseFloat(value, 64)
	return err == nil
}

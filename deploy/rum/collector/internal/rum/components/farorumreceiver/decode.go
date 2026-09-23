package farorumreceiver

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"

	faro "github.com/grafana/faro/pkg/go"
)

var (
	ErrPayloadTooLarge = errors.New("payload exceeds receiver limits")
	ErrInvalidPayload  = errors.New("invalid Faro payload")
)

type signalKind uint8

const (
	signalUnknown  signalKind = 0
	signalOrdinary signalKind = 1 << iota
	signalTraces
)

const (
	faroEventSessionStart  = "session_start"
	faroEventSessionResume = "session_resume"
	faroEventSessionExtend = "session_extend"
	faroEventViewChanged   = "view_changed"

	faroEventReplayData    = "faro.session_recording.event"
	faroEventReplayStarted = "faro.session_recording.started"
	faroEventReplayPaused  = "faro.session_recording.paused"
	faroEventReplayResumed = "faro.session_recording.resumed"
)

func decodeFaroBody(body io.Reader, contentEncoding string, cfg *Config) (faro.Payload, error) {
	payload, _, err := decodeFaroBodyWithFacts(body, contentEncoding, cfg)
	return payload, err
}

type bodyFacts struct {
	compressedBytes   int64
	decompressedBytes int64
}

func decodeFaroBodyWithFacts(body io.Reader, contentEncoding string, cfg *Config) (faro.Payload, bodyFacts, error) {
	compressed, err := readBounded(body, cfg.MaxCompressedBytes)
	if err != nil {
		return faro.Payload{}, bodyFacts{}, err
	}

	var decoded []byte
	switch strings.ToLower(strings.TrimSpace(contentEncoding)) {
	case "":
		if int64(len(compressed)) > cfg.MaxDecompressedBytes {
			return faro.Payload{}, bodyFacts{}, ErrPayloadTooLarge
		}
		decoded = compressed
	case "gzip":
		reader, gzipErr := gzip.NewReader(bytes.NewReader(compressed))
		if gzipErr != nil {
			return faro.Payload{}, bodyFacts{}, fmt.Errorf("%w: invalid gzip stream", ErrInvalidPayload)
		}
		decoded, err = readBounded(reader, cfg.MaxDecompressedBytes)
		closeErr := reader.Close()
		if err != nil {
			return faro.Payload{}, bodyFacts{}, err
		}
		if closeErr != nil {
			return faro.Payload{}, bodyFacts{}, fmt.Errorf("%w: invalid gzip trailer", ErrInvalidPayload)
		}
		if len(compressed) == 0 || float64(len(decoded))/float64(len(compressed)) > cfg.MaxCompressionRatio {
			return faro.Payload{}, bodyFacts{}, ErrPayloadTooLarge
		}
	default:
		return faro.Payload{}, bodyFacts{}, fmt.Errorf("%w: unsupported content encoding", ErrInvalidPayload)
	}

	if len(decoded) == 0 || exceedsJSONDepth(decoded, cfg.MaxJSONDepth) {
		return faro.Payload{}, bodyFacts{}, ErrInvalidPayload
	}

	var payload faro.Payload
	if err := json.Unmarshal(decoded, &payload); err != nil {
		return faro.Payload{}, bodyFacts{}, fmt.Errorf("%w: malformed JSON", ErrInvalidPayload)
	}
	return payload, bodyFacts{
		compressedBytes:   int64(len(compressed)),
		decompressedBytes: int64(len(decoded)),
	}, nil
}

func readBounded(reader io.Reader, limit int64) ([]byte, error) {
	limited := io.LimitReader(reader, limit+1)
	data, err := io.ReadAll(limited)
	if err != nil {
		return nil, fmt.Errorf("%w: body read failed", ErrInvalidPayload)
	}
	if int64(len(data)) > limit {
		return nil, ErrPayloadTooLarge
	}
	return data, nil
}

func exceedsJSONDepth(data []byte, maxDepth int) bool {
	depth := 0
	inString := false
	escaped := false
	for _, char := range data {
		if inString {
			if escaped {
				escaped = false
				continue
			}
			switch char {
			case '\\':
				escaped = true
			case '"':
				inString = false
			}
			continue
		}
		switch char {
		case '"':
			inString = true
		case '{', '[':
			depth++
			if depth > maxDepth {
				return true
			}
		case '}', ']':
			depth--
			if depth < 0 {
				return true
			}
		}
	}
	return depth != 0 || inString
}

func classifyPayload(payload faro.Payload, maxItems int) (signalKind, error) {
	ordinaryCount := len(payload.Events) + len(payload.Exceptions) + len(payload.Logs) + len(payload.Measurements)
	spanCount := 0
	if payload.Traces != nil {
		spanCount = payload.Traces.SpanCount()
	}
	if ordinaryCount+spanCount > maxItems {
		return signalUnknown, ErrPayloadTooLarge
	}
	signals := signalUnknown
	if payload.Traces != nil {
		if spanCount == 0 {
			return signalUnknown, ErrInvalidPayload
		}
		signals |= signalTraces
	}
	if ordinaryCount > 0 {
		signals |= signalOrdinary
	}
	if signals == signalUnknown {
		return signalUnknown, ErrInvalidPayload
	}
	for _, event := range payload.Events {
		if event.Name == faroEventReplayData ||
			(strings.HasPrefix(event.Name, "faro.session_recording.") && !isReplayLifecycleEvent(event.Name)) {
			return signalUnknown, ErrInvalidPayload
		}
	}
	return signals, nil
}

func isReplayLifecycleEvent(name string) bool {
	switch name {
	case faroEventReplayStarted, faroEventReplayPaused, faroEventReplayResumed:
		return true
	default:
		return false
	}
}

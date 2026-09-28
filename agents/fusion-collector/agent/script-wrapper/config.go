package main

import (
	"os"
	"runtime"
	"strconv"
	"strings"
	"time"
)

const (
	defaultTimeout      = 10 * time.Second
	defaultMaxSeries    = 50
	defaultMaxBytes     = 256 * 1024
	defaultMemoryBytes  = 256 * 1024 * 1024
	envPrefixParam      = "BK_PARAM_"
	envConfigID         = "BK_SCRIPT_CONFIG_ID"
	envInstanceID       = "BK_SCRIPT_INSTANCE_ID"
	envTimeout          = "BK_SCRIPT_TIMEOUT"
	envUser             = "BK_SCRIPT_USER"
	envAllowRoot        = "BK_SCRIPT_ALLOW_ROOT"
	envBody             = "BK_SCRIPT_BODY"
	envInterpreter      = "BK_SCRIPT_INTERPRETER"
	envMaxSeries        = "BK_SCRIPT_MAX_SERIES"
	envMaxBytes         = "BK_SCRIPT_MAX_BYTES"
	envMemoryBytes      = "BK_SCRIPT_MEMORY_BYTES"
	envRoot             = "BK_SCRIPT_ROOT"
	linuxCollectorRoot  = "/opt/fusion-collectors"
	windowsCollectorRoot = `C:\fusion-collectors`
)

type config struct {
	ConfigID    string
	InstanceID  string
	Timeout     time.Duration
	User        string
	AllowRoot   bool
	Body        string
	Interpreter string
	MaxSeries   int
	MaxBytes    int
	MemoryBytes uint64
	Root        string
	ParamEnv    []string
}

func loadConfig() config {
	cfg := config{
		ConfigID:    sanitizeID(os.Getenv(envConfigID)),
		InstanceID:  strings.TrimSpace(os.Getenv(envInstanceID)),
		Timeout:     parseDurationSeconds(os.Getenv(envTimeout), defaultTimeout),
		User:        strings.TrimSpace(os.Getenv(envUser)),
		AllowRoot:   parseBool(os.Getenv(envAllowRoot)),
		Body:        unresolvedToEmpty(os.Getenv(envBody)),
		Interpreter: unresolvedToEmpty(os.Getenv(envInterpreter)),
		MaxSeries:   parsePositiveInt(os.Getenv(envMaxSeries), defaultMaxSeries),
		MaxBytes:    parsePositiveInt(os.Getenv(envMaxBytes), defaultMaxBytes),
		MemoryBytes: uint64(parsePositiveInt(os.Getenv(envMemoryBytes), defaultMemoryBytes)),
		Root:        strings.TrimSpace(os.Getenv(envRoot)),
	}
	if cfg.Root == "" {
		if runtime.GOOS == "windows" {
			cfg.Root = windowsCollectorRoot
		} else {
			cfg.Root = linuxCollectorRoot
		}
	}
	cfg.ParamEnv = collectParamEnv()
	return cfg
}

func collectParamEnv() []string {
	var params []string
	for _, item := range os.Environ() {
		if strings.HasPrefix(item, envPrefixParam) {
			params = append(params, item)
		}
	}
	return params
}

func unresolvedToEmpty(value string) string {
	value = strings.TrimSpace(value)
	if value == "" || strings.HasPrefix(value, "${") {
		return ""
	}
	return value
}

func parseBool(value string) bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func parsePositiveInt(value string, fallback int) int {
	n, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil || n <= 0 {
		return fallback
	}
	return n
}

func parseDurationSeconds(value string, fallback time.Duration) time.Duration {
	n, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil || n <= 0 {
		return fallback
	}
	return time.Duration(n) * time.Second
}

func sanitizeID(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	var b strings.Builder
	for _, r := range value {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '.' || r == '_' || r == '-' {
			b.WriteRune(r)
		} else {
			b.WriteByte('_')
		}
	}
	out := b.String()
	if out == "" {
		return "unknown"
	}
	return out
}

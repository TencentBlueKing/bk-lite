package main

import (
	"fmt"
	"os"
	"time"
)

func main() {
	started := time.Now()
	cfg := loadConfig()
	health := healthMetrics{ExitCode: -1}
	var userOut []byte

	defer func() {
		if recovered := recover(); recovered != nil {
			health.Up = 0
			health.ExitCode = -1
		}
		health.Duration = time.Since(started).Seconds()
		_, _ = os.Stdout.WriteString(renderPrometheus(userOut, cfg.MaxBytes, cfg.MaxSeries, health))
		os.Exit(0)
	}()

	if cfg.ConfigID == "" {
		fmt.Fprintln(os.Stderr, "script wrapper: missing config id")
		return
	}
	if cfg.Body == "" {
		fmt.Fprintln(os.Stderr, "script wrapper: missing script body")
		return
	}

	lock, err := acquireLock(cfg)
	if err != nil {
		fmt.Fprintln(os.Stderr, "script wrapper: instance already running")
		return
	}
	defer lock.Close()

	scriptPath, err := writeScript(cfg)
	if err != nil {
		fmt.Fprintln(os.Stderr, "script wrapper: failed to materialize script")
		return
	}

	result := runScript(cfg, scriptPath)
	userOut = result.Stdout
	health.ExitCode = result.ExitCode
	if result.Timeout {
		health.ExitCode = 124
	}
	if result.Truncated {
		health.Truncated = 1
	}
	if result.ExitCode == 0 && !result.Timeout {
		health.Up = 1
	}
}

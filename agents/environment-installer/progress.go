package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
)

type installerProgress struct {
	output       io.Writer
	line         []byte
	discard      bool
	currentStage string
	failedStage  string
	failedCode   int
}

func (progress *installerProgress) Write(content []byte) (int, error) {
	for _, value := range content {
		if value == '\n' {
			if !progress.discard {
				progress.consume(progress.line)
			}
			progress.line = progress.line[:0]
			progress.discard = false
		} else if !progress.discard {
			if len(progress.line) >= 64*1024 {
				progress.line = progress.line[:0]
				progress.discard = true
			} else {
				progress.line = append(progress.line, value)
			}
		}
	}
	return len(content), nil
}

func (progress *installerProgress) consume(line []byte) {
	prefix := []byte("BKINSTALL_EVENT ")
	if !bytes.HasPrefix(line, prefix) {
		return
	}
	var event struct {
		Step   string `json:"step"`
		Status string `json:"status"`
	}
	if json.Unmarshal(line[len(prefix):], &event) != nil {
		return
	}
	stages := map[string]struct {
		stage string
		code  int
	}{
		"fetch_session": {"session", 30}, "clock_check": {"preflight", 10},
		"prepare_directories": {"install", 40}, "download_package": {"download", 30},
		"extract_package": {"extract", 40}, "stop_service": {"install", 40},
		"configure_runtime": {"install", 40}, "run_package_installer": {"install", 40},
	}
	safe, ok := stages[event.Step]
	if !ok {
		return
	}
	if event.Status == "running" && progress.currentStage != safe.stage {
		progress.currentStage = safe.stage
		if progress.output != nil {
			_, _ = fmt.Fprintf(progress.output, "Installer stage: %s\n", safe.stage)
		}
	}
	if event.Status == "failed" {
		progress.failedStage = safe.stage
		progress.failedCode = safe.code
	}
}

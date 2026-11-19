package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestInstallerProgressOnlyEmitsKnownStages(t *testing.T) {
	var output bytes.Buffer
	progress := installerProgress{output: &output}
	for _, part := range []string{
		"raw secret-sentinel\nBKINSTALL_EV",
		"ENT {\"step\":\"download_package\",\"status\":\"running\",\"message\":\"secret-sentinel\"}\n",
		"BKINSTALL_EVENT {\"step\":\"download_package\",\"status\":\"failed\",\"error\":\"secret-sentinel\"}\n",
		"BKINSTALL_EVENT {\"step\":\"secret-sentinel\",\"status\":\"failed\"}\n",
	} {
		if _, err := progress.Write([]byte(part)); err != nil {
			t.Fatal(err)
		}
	}
	if strings.Contains(output.String(), "secret-sentinel") {
		t.Fatal("raw installer output leaked")
	}
	if progress.failedStage != "download" || progress.failedCode != 30 {
		t.Fatal("failed stage lost")
	}
	if !strings.Contains(output.String(), "download") {
		t.Fatal("safe progress missing")
	}
}

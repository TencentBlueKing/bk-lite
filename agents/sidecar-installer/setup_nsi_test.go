package main

import (
	"os"
	"strings"
	"testing"
)

func TestWindowsGUIRunsWorkerOutsideInstallationDirectory(t *testing.T) {
	content, err := os.ReadFile("setup.nsi")
	if err != nil {
		t.Fatalf("read setup.nsi: %v", err)
	}
	script := string(content)

	if strings.Contains(script, `"$INSTDIR\setup-worker.exe" --url`) {
		t.Fatal("GUI installer must not run the worker from the transactional installation directory")
	}
	if strings.Count(script, `"$PLUGINSDIR\setup-worker.exe" --url-file`) != 2 {
		t.Fatal("GUI fetch and install phases must both run the worker from the isolated plugin directory")
	}
	if strings.Contains(script, `--url "$ConfigURL"`) || strings.Contains(script, `DetailPrint "URL: $ConfigURL"`) || strings.Contains(script, `"ConfigURL" "$ConfigURL"`) {
		t.Fatal("GUI installer must not expose or persist the one-time installer session URL")
	}
}

func TestNSISTargetBuildsEmbeddedPrerequisites(t *testing.T) {
	content, err := os.ReadFile("Makefile")
	if err != nil {
		t.Fatalf("read Makefile: %v", err)
	}
	if !strings.Contains(string(content), "nsis: icons worker") {
		t.Fatal("nsis target must build its icon and setup-worker prerequisites")
	}
}

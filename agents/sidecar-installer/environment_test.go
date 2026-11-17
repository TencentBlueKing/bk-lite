package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPackageDigestRejectsModifiedArchive(t *testing.T) {
	path := filepath.Join(t.TempDir(), "package.zip")
	data := []byte("approved archive")
	os.WriteFile(path, data, 0600)
	digest := sha256.Sum256(data)
	expected := hex.EncodeToString(digest[:])
	if err := verifyPackageDigest(path, expected); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(path, []byte("changed archive"), 0600)
	if err := verifyPackageDigest(path, expected); err == nil {
		t.Fatal("changed archive accepted")
	}
}

func TestEnvironmentLinuxConfigUsesStrictTLSAndInstallationReceipt(t *testing.T) {
	dir := t.TempDir()
	cfg := &Config{ServerURL: "https://platform.example/node", APIToken: "secret", NodeID: "node-a", NodeName: "host-a", ZoneID: "1", GroupID: "2", InstallDir: dir,
		Package: PackageConfig{CPUArchitecture: "x86_64", SHA256: strings.Repeat("a", 64)}, EnvironmentInstallID: "install-a", Storage: StorageConfig{NATSTLSCA: "test-nats-ca"}}
	if err := writeEnvironmentLinuxConfig(cfg); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(filepath.Join(dir, "sidecar.yml"))
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{"tls_skip_verify: false", "environment_install:install-a", "environment_package_sha256:" + strings.Repeat("a", 64)} {
		if !strings.Contains(string(raw), expected) {
			t.Errorf("missing %s", expected)
		}
	}
	ca, caErr := os.ReadFile(filepath.Join(dir, "certs", "nats-ca.crt"))
	if caErr != nil || string(ca) != "test-nats-ca" {
		t.Fatal("NATS CA missing from installed component runtime")
	}
	info, _ := os.Stat(filepath.Join(dir, "sidecar.yml"))
	if info.Mode().Perm() != 0600 {
		t.Fatal("config must be root private")
	}
}

func TestEnvironmentStagingFailurePreservesInstalledFiles(t *testing.T) {
	parent := t.TempDir()
	target := filepath.Join(parent, "controller")
	os.Mkdir(target, 0700)
	os.WriteFile(filepath.Join(target, "sentinel"), []byte("old"), 0600)
	cfg := &Config{InstallDir: target, NodeID: "node-a", EnvironmentInstallID: "install-a"}
	stopped := false
	_, err := prepareEnvironmentLinuxPackage("unused", cfg, func() error { stopped = true; return nil }, func(_ string, destination string) (int, error) {
		os.WriteFile(filepath.Join(destination, "partial"), []byte("broken"), 0600)
		return 0, fmt.Errorf("archive damaged")
	})
	if err == nil || stopped {
		t.Fatal("bad archive altered service")
	}
	if data, _ := os.ReadFile(filepath.Join(target, "sentinel")); string(data) != "old" {
		t.Fatal("old files changed")
	}
}

func TestEnvironmentStagingPublishesOnlyOwnedInstallation(t *testing.T) {
	target := filepath.Join(t.TempDir(), "controller")
	cfg := &Config{InstallDir: target, NodeID: "node-a", EnvironmentInstallID: "install-a"}
	extractPackage := func(_ string, destination string) (int, error) {
		return 1, os.WriteFile(filepath.Join(destination, "install.sh"), []byte("# BK_LITE_CONFIG_PREPARED"), 0700)
	}
	stopped := 0
	stop := func() error { stopped++; return nil }
	if _, err := prepareEnvironmentLinuxPackage("unused", cfg, stop, extractPackage); err != nil {
		t.Fatal(err)
	}
	if raw, _ := os.ReadFile(filepath.Join(target, "node-id")); string(raw) != "node-a" {
		t.Fatal("missing staged identity")
	}
	if _, err := prepareEnvironmentLinuxPackage("unused", cfg, stop, extractPackage); err != nil {
		t.Fatal(err)
	}
	if stopped != 2 {
		t.Fatal("expected one service transition per publish")
	}
	cfg.NodeID = "other-node"
	if _, err := prepareEnvironmentLinuxPackage("unused", cfg, stop, extractPackage); err == nil {
		t.Fatal("took over another node")
	}
	if stopped != 2 {
		t.Fatal("stopped an unowned service")
	}
}

func TestPrivateSessionRequestKeepsTokenOutOfURL(t *testing.T) {
	request, err := privateSessionRequest("https://platform.example/api/v1/node_mgmt/open_api/installer/session?token=secret-sentinel")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(request.URL.String(), "secret-sentinel") || request.Header.Get("X-Installation-Token") != "secret-sentinel" {
		t.Fatal("private session token exposed or lost")
	}
}

func TestEnvironmentStopFailureRetainsStageAndInstalledFiles(t *testing.T) {
	target := filepath.Join(t.TempDir(), "controller")
	if err := os.Mkdir(target, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(target, ".environment-node-id"), []byte("node-a"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(target, "sentinel"), []byte("old"), 0600); err != nil {
		t.Fatal(err)
	}
	cfg := &Config{InstallDir: target, NodeID: "node-a", EnvironmentInstallID: "install-a"}
	stopErr := errors.New("service stop failed")
	_, err := prepareLinuxPackageForConfig("unused", cfg, func() error { return stopErr }, func(_ string, destination string) (int, error) {
		return 1, os.WriteFile(filepath.Join(destination, "install.sh"), []byte("# BK_LITE_CONFIG_PREPARED"), 0700)
	}, nil)
	var phase *linuxPackagePhaseError
	if !errors.As(err, &phase) || phase.step != "stop_service" || !errors.Is(err, stopErr) {
		t.Fatalf("service failure stage lost: %v", err)
	}
	if data, _ := os.ReadFile(filepath.Join(target, "sentinel")); string(data) != "old" {
		t.Fatal("installed files changed after stop failure")
	}
}

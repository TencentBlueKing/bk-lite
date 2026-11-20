package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

func verifyPackageDigest(path, expected string) error {
	if len(expected) != 64 {
		return fmt.Errorf("package SHA256 required")
	}
	file, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("cannot read downloaded package")
	}
	defer file.Close()
	hash := sha256.New()
	if _, err = io.Copy(hash, file); err != nil {
		return fmt.Errorf("cannot hash downloaded package")
	}
	if hex.EncodeToString(hash.Sum(nil)) != expected {
		return fmt.Errorf("package SHA256 mismatch")
	}
	return nil
}

func writeEnvironmentLinuxConfig(cfg *Config) error {
	return writeEnvironmentLinuxConfigTo(cfg, cfg.InstallDir)
}

func writeEnvironmentLinuxConfigTo(cfg *Config, outputDir string) error {
	if strings.TrimSpace(cfg.Storage.NATSTLSCA) != "" {
		certDir := filepath.Join(outputDir, "certs")
		if err := os.MkdirAll(certDir, 0755); err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(certDir, "nats-ca.crt"), []byte(cfg.Storage.NATSTLSCA), 0600); err != nil {
			return err
		}
	}
	q := strconv.Quote
	config := fmt.Sprintf(`server_url: %s
server_api_token: %s
node_id: %s
node_name: %s
update_interval: 10
tls_skip_verify: false
send_status: true
list_log_files: []
cache_path: %s
log_path: %s
collector_configuration_directory: %s
collector_validation_timeout: "1m"
collector_shutdown_timeout: "10s"
tags: [%s, %s, %s, %s, %s]
collector_binaries_accesslist:
  - %s
  - %s
`, q(cfg.ServerURL), q(cfg.APIToken), q("file:"+filepath.Join(cfg.InstallDir, "node-id")), q(cfg.NodeName),
		q(filepath.Join(cfg.InstallDir, "cache")), q(filepath.Join(cfg.InstallDir, "log")), q(filepath.Join(cfg.InstallDir, "generated")),
		q("zone:"+cfg.ZoneID), q("group:"+cfg.GroupID), q("cpu_architecture:"+cfg.Package.CPUArchitecture),
		q("environment_install:"+cfg.EnvironmentInstallID), q("environment_package_sha256:"+cfg.Package.SHA256),
		q(filepath.Join(cfg.InstallDir, "bin", "*")), q(filepath.Join(cfg.InstallDir, "bin", "*", "*")))
	return os.WriteFile(filepath.Join(outputDir, "sidecar.yml"), []byte(config), 0600)
}

func prepareLinuxPackageForConfig(zipPath string, cfg *Config, stop func() error, extractPackage func(string, string) (int, error), progress installerProgressFunc) (int, error) {
	if cfg.EnvironmentInstallID != "" {
		return prepareEnvironmentLinuxPackage(zipPath, cfg, stop, extractPackage)
	}
	return prepareLinuxPackageWithProgress(zipPath, cfg.InstallDir, stop, extractPackage, progress)
}

func prepareEnvironmentLinuxPackage(zipPath string, cfg *Config, stop func() error, extractPackage func(string, string) (int, error)) (int, error) {
	target := filepath.Clean(cfg.InstallDir)
	if !filepath.IsAbs(target) || target == string(os.PathSeparator) {
		return 0, fmt.Errorf("unsafe installation directory")
	}
	stage, err := os.MkdirTemp(filepath.Dir(target), ".environment-stage-")
	if err != nil {
		return 0, err
	}
	defer os.RemoveAll(stage)
	count, err := extractPackage(zipPath, stage)
	if err != nil {
		return 0, err
	}
	script, err := os.ReadFile(filepath.Join(stage, "install.sh"))
	if err != nil || !bytes.Contains(script, []byte("BK_LITE_CONFIG_PREPARED")) {
		return 0, fmt.Errorf("controller package does not support environment installation")
	}
	if err := writeEnvironmentLinuxConfigTo(cfg, stage); err != nil {
		return 0, err
	}
	if err := os.WriteFile(filepath.Join(stage, "node-id"), []byte(cfg.NodeID), 0600); err != nil {
		return 0, err
	}
	if err := os.WriteFile(filepath.Join(stage, ".environment-node-id"), []byte(cfg.NodeID), 0600); err != nil {
		return 0, err
	}
	owned := func(path string) bool {
		info, err := os.Lstat(path)
		if err != nil || !info.IsDir() {
			return false
		}
		content, err := os.ReadFile(filepath.Join(path, ".environment-node-id"))
		return err == nil && strings.TrimSpace(string(content)) == cfg.NodeID
	}
	backup := target + ".environment-previous"
	if _, err := os.Lstat(backup); err == nil {
		if !owned(backup) {
			return 0, fmt.Errorf("unowned recovery directory")
		}
		if _, err := os.Lstat(target); err == nil {
			if !owned(target) {
				return 0, fmt.Errorf("unowned controller directory")
			}
			if err := stop(); err != nil {
				return 0, &linuxPackagePhaseError{step: "stop_service", err: err}
			}
			if err := os.RemoveAll(target); err != nil {
				return 0, err
			}
		} else if !errors.Is(err, os.ErrNotExist) {
			return 0, err
		}
		if err := os.Rename(backup, target); err != nil {
			return 0, err
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return 0, err
	}
	exists := false
	if _, err := os.Lstat(target); err == nil {
		if !owned(target) {
			return 0, fmt.Errorf("existing controller requires explicit takeover")
		}
		exists = true
	} else if !errors.Is(err, os.ErrNotExist) {
		return 0, err
	}
	if err := stop(); err != nil {
		return 0, &linuxPackagePhaseError{step: "stop_service", err: err}
	}
	if exists {
		if err := os.Rename(target, backup); err != nil {
			return 0, err
		}
	}
	if err := os.Rename(stage, target); err != nil {
		if exists {
			if restoreErr := os.Rename(backup, target); restoreErr != nil {
				return 0, fmt.Errorf("installation publish and recovery failed")
			}
		}
		return 0, err
	}
	if exists {
		if err := os.RemoveAll(backup); err != nil {
			return 0, err
		}
	}
	return count, nil
}

func privateSessionRequest(rawURL string) (*http.Request, error) {
	parsed, err := url.Parse(rawURL)
	if err != nil || parsed.Scheme != "https" || parsed.User != nil || parsed.Path != "/api/v1/node_mgmt/open_api/installer/session" {
		return nil, fmt.Errorf("invalid private session URL")
	}
	token := parsed.Query().Get("token")
	if token == "" {
		return nil, fmt.Errorf("session token required")
	}
	query := parsed.Query()
	query.Del("token")
	parsed.RawQuery = query.Encode()
	request, err := http.NewRequest(http.MethodGet, parsed.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("invalid private session request")
	}
	request.Header.Set("X-Installation-Token", token)
	return request, nil
}

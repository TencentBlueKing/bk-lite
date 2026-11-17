//go:build linux

package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"
)

const stateDir = "/var/lib/bklite-environment-installer"
const controllerDir = "/opt/fusion-collectors"

type failure struct {
	code           int
	stage, message string
}

func (f *failure) Error() string                 { return f.message }
func fail(code int, stage, message string) error { return &failure{code, stage, message} }

func main() {
	code := 0
	status, err := run()
	if err != nil {
		code = 40
		result := map[string]any{"status": "failed", "stage": "install", "error_code": 40, "message": "installation failed", "retryable": false}
		var typed *failure
		if errors.As(err, &typed) {
			code = typed.code
			result["stage"] = typed.stage
			result["error_code"] = typed.code
			result["message"] = typed.message
			result["retryable"] = typed.code == 30 || typed.code == 50 || typed.code == 70
		}
		for key, value := range status {
			result[key] = value
		}
		status = result
	}
	_ = json.NewEncoder(os.Stdout).Encode(status)
	os.Exit(code)
}

func run() (status map[string]any, runErr error) {
	if len(os.Args) != 1 {
		return nil, fail(10, "preflight", "this environment package accepts no arguments")
	}
	if os.Geteuid() != 0 || runtime.GOARCH != "amd64" {
		return nil, fail(10, "preflight", "Linux x86_64 and root required")
	}
	executable, err := os.Executable()
	if err != nil {
		return nil, fail(10, "bundle", "cannot locate bundle")
	}
	manifest, installer, err := loadBundle(executable)
	if err != nil {
		return nil, fail(10, "bundle", err.Error())
	}
	expiry, err := time.Parse(time.RFC3339, manifest.ExpiresAt)
	if err != nil || !time.Now().Before(expiry) || manifest.GrantID == "" || manifest.Team < 1 || len(manifest.PackageSHA256) != 64 || manifest.RequiredFreeBytes == 0 || manifest.TimeoutSeconds < 30 || manifest.TimeoutSeconds > 3600 {
		return nil, fail(20, "bundle", "invalid or expired installation manifest")
	}
	client, err := newAPIClient(manifest)
	if err != nil {
		return nil, fail(10, "preflight", err.Error())
	}
	for _, command := range []string{"systemctl", "bash", "sed", "cp", "chmod", "mkdir", "rm", "cat"} {
		if _, err := exec.LookPath(command); err != nil {
			return nil, fail(10, "preflight", "missing required command: "+command)
		}
	}
	if _, err := os.Stat("/run/systemd/system"); err != nil {
		return nil, fail(10, "preflight", "systemd is not available")
	}
	var fs syscall.Statfs_t
	if syscall.Statfs("/opt", &fs) != nil || fs.Bavail*uint64(fs.Bsize) < manifest.RequiredFreeBytes {
		return nil, fail(10, "preflight", "insufficient free space in /opt")
	}
	if err := os.MkdirAll(stateDir, 0700); err != nil {
		return nil, fail(10, "preflight", "cannot create private state directory")
	}
	info, err := os.Lstat(stateDir)
	if err != nil || !info.IsDir() || info.Mode().Perm() != 0700 {
		return nil, fail(10, "preflight", "unsafe state directory permissions")
	}
	lock, err := os.OpenFile(filepath.Join(stateDir, "install.lock"), os.O_CREATE|os.O_RDWR|syscall.O_NOFOLLOW, 0600)
	if err != nil {
		return nil, fail(60, "lock", "cannot acquire installation lock")
	}
	defer lock.Close()
	if syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB) != nil {
		return nil, fail(60, "lock", "another installation is running")
	}
	defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	_, stateErr := os.Stat(filepath.Join(stateDir, "state.json"))
	_, dirErr := os.Lstat(controllerDir)
	serviceOutput, _ := exec.Command("systemctl", "show", "--property=LoadState", "bk-sidecar.service").Output()
	serviceExists := strings.TrimSpace(string(serviceOutput)) != "LoadState=not-found"
	if os.IsNotExist(stateErr) && (dirErr == nil || serviceExists) {
		return nil, fail(60, "preflight", "existing controller requires explicit takeover; installation stopped")
	}
	machine, err := machineIdentity()
	if err != nil {
		return nil, fail(10, "identity", "cannot establish host identity")
	}
	ip, err := managementIP(manifest)
	if err != nil {
		return nil, fail(10, "identity", err.Error())
	}
	hostname, err := os.Hostname()
	if err != nil || len(hostname) > 100 || strings.ContainsAny(hostname, "\r\n") {
		return nil, fail(10, "identity", "invalid host name")
	}
	state, err := loadOrCreateState(stateDir, manifest.GrantID, machine, ip, hostname)
	if err != nil {
		return nil, fail(60, "identity", "stored identity is invalid or belongs to another host/environment")
	}
	if state.IP != ip {
		return nil, fail(60, "identity", "management address changed; explicit recovery required")
	}
	if node, err := os.ReadFile(filepath.Join(controllerDir, "node-id")); err == nil && strings.TrimSpace(string(node)) != state.NodeID {
		return nil, fail(60, "identity", "existing controller has another node identity")
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	ctx, cancel := context.WithTimeout(ctx, time.Duration(manifest.TimeoutSeconds)*time.Second)
	defer cancel()
	fmt.Fprintln(os.Stderr, "Requesting environment installation")
	result, err := client.call(ctx, "environment-install", map[string]any{"request_id": state.RequestID, "node_id": state.NodeID, "ip": state.IP, "node_name": state.NodeName, "os": "linux", "cpu_architecture": "x86_64"})
	if err != nil {
		return nil, fail(operationFailureCode(err), "request", err.Error())
	}
	if result.InstallID == "" || result.NodeID != state.NodeID || result.PackageSHA256 != manifest.PackageSHA256 || result.PackageVersion != manifest.PackageVersion {
		return nil, fail(20, "request", "installation response does not match signed environment")
	}
	state.InstallID = result.InstallID
	defer func() {
		if runErr == nil {
			return
		}
		if status == nil {
			status = map[string]any{}
		}
		status["package_id"] = manifest.GrantID
		status["install_id"] = state.InstallID
		status["node_id"] = state.NodeID
		var typed *failure
		if errors.As(runErr, &typed) {
			reportContext, finish := context.WithTimeout(context.Background(), 5*time.Second)
			defer finish()
			_, _ = client.call(reportContext, "environment-install-status", map[string]any{"install_id": state.InstallID, "report": map[string]any{"stage": typed.stage, "error_code": typed.code}})
		}
	}()
	if err := saveState(stateDir, state); err != nil {
		return nil, fail(40, "identity", "cannot save installation record")
	}
	already := state.Phase == "registered"
	if err := registeredControllerState(result.Status, controllerActive(state.NodeID)); err != nil {
		return nil, err
	}
	if !controllerActive(state.NodeID) && result.Status != "registered" {
		if err := sameSessionOrigin(manifest.PlatformURL, result.ConfigURL); err != nil {
			return nil, fail(20, "session", "invalid session destination")
		}
		work, err := os.MkdirTemp("/opt", ".environment-install-")
		if err != nil {
			return nil, fail(40, "install", "cannot create installer workspace")
		}
		defer os.RemoveAll(work)
		binary := filepath.Join(work, "setup-worker")
		configFile := filepath.Join(work, "session-url")
		if os.WriteFile(binary, installer, 0700) != nil || os.WriteFile(configFile, []byte(result.ConfigURL), 0600) != nil {
			return nil, fail(40, "install", "cannot prepare installer")
		}
		command := exec.CommandContext(ctx, binary, "--url-file", configFile, "--private-session-token", "--require-https", "--install-dir", controllerDir)
		command.Env = os.Environ()
		if manifest.PlatformCA != "" {
			ca := filepath.Join(work, "platform-ca.crt")
			if os.WriteFile(ca, []byte(manifest.PlatformCA), 0600) != nil {
				return nil, fail(40, "install", "cannot prepare CA")
			}
			command.Env = append(command.Env, "SSL_CERT_FILE="+ca, "BK_LITE_PLATFORM_CA_FILE="+ca)
		}
		// Only known stage enums are forwarded; message/error bodies remain private.
		progress := &installerProgress{output: os.Stderr}
		command.Stdout = progress
		command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
		command.Cancel = func() error {
			if command.Process == nil {
				return nil
			}
			return syscall.Kill(-command.Process.Pid, syscall.SIGKILL)
		}
		state.Phase = "installing"
		if saveState(stateDir, state) != nil {
			return nil, fail(40, "install", "cannot record installation start")
		}
		fmt.Fprintln(os.Stderr, "Installing verified controller package")
		installErr := command.Run()
		if progress.failedStage != "" {
			return nil, fail(progress.failedCode, progress.failedStage, "official installer failed during "+progress.failedStage+"; retry keeps the node identity")
		}
		if installErr != nil {
			return nil, fail(40, "install", "official installer failed; inspect local service state before retry")
		}
		state.Phase = "awaiting_registration"
		if saveState(stateDir, state) != nil {
			return nil, fail(40, "install", "cannot record installation outcome")
		}
	}
	fmt.Fprintln(os.Stderr, "Waiting for the platform to confirm a fresh heartbeat")
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	var lastRegistered *InstallResult
	var lastConfirmedAt time.Time
	for {
		registered, err := client.call(ctx, "environment-install-status", map[string]any{"install_id": state.InstallID})
		if err != nil && operationFailureCode(err) != 30 {
			return nil, fail(operationFailureCode(err), "registration", err.Error())
		}
		if err == nil && registered.Status == "registered" && registered.NodeID == state.NodeID && registered.PackageVersion == manifest.PackageVersion && controllerActive(state.NodeID) {
			lastRegistered = &registered
			lastConfirmedAt = time.Now()
			if state.Phase != "registered" {
				state.Phase = "registered"
				if saveState(stateDir, state) != nil {
					return nil, fail(40, "result", "cannot save registered state")
				}
			}
			if requiredComponentsHealthy(manifest.RequiredComponents, registered.Components) {
				_, _ = client.call(ctx, "environment-install-status", map[string]any{"install_id": state.InstallID, "report": map[string]any{"stage": "complete", "error_code": 0}})
				status := "installed"
				if already {
					status = "already_installed"
				}
				return map[string]any{"package_id": manifest.GrantID, "install_id": state.InstallID, "node_id": state.NodeID, "status": status, "stage": "complete", "error_code": 0, "retryable": false, "controller_version": manifest.PackageVersion, "registration": "success", "last_seen": registered.LastSeen, "components": registered.Components}, nil
			}
		} else if err == nil {
			lastRegistered = nil
		}
		select {
		case <-ctx.Done():
			if lastRegistered != nil && time.Since(lastConfirmedAt) < 2*time.Minute && controllerActive(state.NodeID) {
				return map[string]any{"registration": "success", "controller_version": manifest.PackageVersion, "components": lastRegistered.Components}, fail(70, "components", "required components are not healthy; registration retained")
			}
			return nil, fail(50, "registration", "fresh platform registration and local service health not confirmed; identity retained for retry")
		case <-ticker.C:
		}
	}
}

func registeredControllerState(platformStatus string, active bool) error {
	if platformStatus == "registered" && !active {
		return fail(60, "preflight", "registered controller is inactive or its identity is missing; restore the existing bk-sidecar service before retry; no files were replaced")
	}
	return nil
}

func controllerActive(nodeID string) bool {
	node, err := os.ReadFile(filepath.Join(controllerDir, "node-id"))
	return err == nil && strings.TrimSpace(string(node)) == nodeID && exec.Command("systemctl", "is-active", "--quiet", "bk-sidecar.service").Run() == nil
}

func machineIdentity() (string, error) {
	machine, err := os.ReadFile("/etc/machine-id")
	if err != nil || len(strings.TrimSpace(string(machine))) == 0 {
		return "", errors.New("missing machine identity")
	}
	hardware, _ := os.ReadFile("/sys/class/dmi/id/product_uuid")
	digest := sha256.Sum256(append(machine, hardware...))
	return hex.EncodeToString(digest[:]), nil
}

func managementIP(manifest Manifest) (string, error) {
	if manifest.ManagementCIDR != "" {
		_, subnet, err := net.ParseCIDR(manifest.ManagementCIDR)
		if err != nil {
			return "", errors.New("invalid management network")
		}
		addresses, err := net.InterfaceAddrs()
		if err != nil {
			return "", errors.New("cannot enumerate local addresses")
		}
		candidates := map[string]bool{}
		for _, address := range addresses {
			ip, _, _ := net.ParseCIDR(address.String())
			if ip.To4() != nil && !ip.IsLoopback() && subnet.Contains(ip) {
				candidates[ip.String()] = true
			}
		}
		if len(candidates) != 1 {
			return "", errors.New("management network must select exactly one IPv4 address")
		}
		for ip := range candidates {
			return ip, nil
		}
	}
	parsed, _ := url.Parse(manifest.PlatformURL)
	routeContext, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	remotes, err := net.DefaultResolver.LookupIP(routeContext, "ip4", parsed.Hostname())
	if err != nil {
		return "", errors.New("cannot resolve platform IPv4 addresses")
	}
	port := parsed.Port()
	if port == "" {
		port = "443"
	}
	return routeManagementIP(remotes, func(remote net.IP) (net.IP, error) {
		dialer := net.Dialer{Timeout: 5 * time.Second}
		connection, err := dialer.DialContext(routeContext, "udp4", net.JoinHostPort(remote.String(), port))
		if err != nil {
			return nil, errors.New("cannot determine platform route")
		}
		defer connection.Close()
		return connection.LocalAddr().(*net.UDPAddr).IP, nil
	})
}

func sameSessionOrigin(platform, session string) error {
	base, _ := url.Parse(platform)
	target, err := url.Parse(session)
	if err != nil || target.Scheme != "https" || target.Host != base.Host || target.User != nil || target.Path != "/api/v1/node_mgmt/open_api/installer/session" || target.Query().Get("token") == "" || target.Fragment != "" {
		return errors.New("invalid session origin")
	}
	return nil
}

func routeManagementIP(remotes []net.IP, localAddress func(net.IP) (net.IP, error)) (string, error) {
	candidates := map[string]bool{}
	for _, remote := range remotes {
		if remote.To4() == nil {
			continue
		}
		local, err := localAddress(remote)
		if err != nil {
			return "", err
		}
		if local.To4() == nil || local.IsLoopback() || local.IsUnspecified() {
			return "", errors.New("route selected an invalid management address")
		}
		candidates[local.String()] = true
	}
	if len(candidates) != 1 {
		return "", errors.New("platform routes are ambiguous; select a management network")
	}
	for ip := range candidates {
		return ip, nil
	}
	return "", errors.New("cannot determine management address")
}

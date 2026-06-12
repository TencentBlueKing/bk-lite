package main

import (
	"archive/zip"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
)

// objectStoreMaxWait 是 JetStream Object Store 每个 chunk 投递的最大等待时间。
// 默认值 5s 在弱网或大包场景下容易触发 "read pipe: i/o timeout"（Issue #2985）。
const objectStoreMaxWait = 60 * time.Second

type Config struct {
	ServerURL  string        `json:"server_url"`
	APIToken   string        `json:"api_token"`
	NodeID     string        `json:"node_id"`
	NodeName   string        `json:"node_name"`
	ZoneID     string        `json:"zone_id"`
	GroupID    string        `json:"group_id"`
	OS         string        `json:"os"`
	InstallDir string        `json:"install_dir"`
	Package    PackageConfig `json:"package"`
	Storage    StorageConfig `json:"storage"`
}

type PackageConfig struct {
	ID              int    `json:"id"`
	OS              string `json:"os"`
	CPUArchitecture string `json:"cpu_architecture"`
	Object          string `json:"object"`
	Version         string `json:"version"`
	Name            string `json:"name"`
	FileKey         string `json:"file_key"`
}

type StorageConfig struct {
	Bucket       string `json:"bucket"`
	FileKey      string `json:"file_key"`
	FileName     string `json:"file_name"`
	NATSServers  string `json:"nats_servers"`
	NATSUsername string `json:"nats_username"`
	NATSPassword string `json:"nats_password"`
	NATSProtocol string `json:"nats_protocol"`
	NATSTLSCA    string `json:"nats_tls_ca"`
}

type InstallerEvent struct {
	Step            string `json:"step"`
	Status          string `json:"status"`
	Message         string `json:"message,omitempty"`
	Progress        *int   `json:"progress,omitempty"`
	Downloaded      int64  `json:"downloaded_bytes,omitempty"`
	Total           int64  `json:"total_bytes,omitempty"`
	Timestamp       string `json:"timestamp"`
	Error           string `json:"error,omitempty"`
	ErrorType       string `json:"error_type,omitempty"`
	Bucket          string `json:"bucket,omitempty"`
	FileKey         string `json:"file_key,omitempty"`
	FileName        string `json:"file_name,omitempty"`
	PackageName     string `json:"package_name,omitempty"`
	CPUArchitecture string `json:"cpu_architecture,omitempty"`
	InstallDir      string `json:"install_dir,omitempty"`
	TargetPath      string `json:"target_path,omitempty"`
	ExitCode        *int   `json:"exit_code,omitempty"`
}

type EventOptions struct {
	ErrorType       string
	Bucket          string
	FileKey         string
	FileName        string
	PackageName     string
	CPUArchitecture string
	InstallDir      string
	TargetPath      string
	ExitCode        *int
}

var (
	configURL  = flag.String("url", "", "Configuration URL")
	installDir = flag.String("install-dir", "", "Installation directory")
	skipTLS    = flag.Bool("skip-tls", true, "Skip TLS certificate verification")
	fetchOnly  = flag.Bool("fetch-only", false, "Only fetch and display config")
)

func main() {
	flag.Parse()

	if *configURL == "" {
		fatal("--url is required")
	}

	client := newHTTPClient(*skipTLS)

	if *fetchOnly {
		cfg, err := fetchConfig(client, *configURL)
		if err != nil {
			fatal("Fetch failed: %v", err)
		}
		printConfig(cfg)
		return
	}

	run(client)
}

func run(client *http.Client) {
	log("Collector Sidecar Setup")
	log("=======================")

	log("[1/6] Fetching configuration...")
	emitEvent("fetch_session", "running", "Fetching installer session", nil, 0, 0, "")
	cfg, err := fetchConfig(client, *configURL)
	if err != nil {
		fatalStep("fetch_session", "Fetch failed: %v", err)
	}
	emitEvent("fetch_session", "success", "Installer session fetched", intPtr(100), 0, 0, "")
	log("      Node: %s", cfg.NodeID)

	if *installDir != "" {
		cfg.InstallDir = *installDir
	}
	if cfg.InstallDir == "" {
		cfg.InstallDir = `C:\fusion-collectors`
	}
	cfg.InstallDir = filepath.Clean(cfg.InstallDir)

	// Ensure install directory is absolute path (required by collector-sidecar)
	if !filepath.IsAbs(cfg.InstallDir) {
		absPath, err := filepath.Abs(cfg.InstallDir)
		if err != nil {
			fatal("Failed to resolve absolute path for install dir: %v", err)
		}
		cfg.InstallDir = absPath
	}

	log("[2/6] Preparing directories...")
	emitEvent("prepare_directories", "running", "Preparing directories", nil, 0, 0, "")
	if err := prepareDirs(cfg.InstallDir); err != nil {
		fatalStep("prepare_directories", "Failed: %v", err)
	}
	emitEvent("prepare_directories", "success", "Directories prepared", intPtr(100), 0, 0, "")

	if cfg.Storage.FileKey != "" {
		log("[3/6] Downloading package...")
		emitEventWithOptions("download_package", "running", "Downloading controller package", intPtr(0), 0, 0, "", downloadEventOptions(cfg))
		zipPath, err := downloadFromStorage(&cfg.Storage)
		if err != nil {
			downloadOptions := downloadEventOptions(cfg)
			if downloadOptions != nil {
				downloadOptions.ErrorType = classifyDownloadError(err)
			}
			fatalStepWithOptions("download_package", "Download failed: %v", err, downloadOptions)
		}
		emitEventWithOptions("download_package", "success", "Controller package downloaded", intPtr(100), 0, 0, "", downloadEventOptions(cfg))

		log("[4/6] Extracting files...")
		emitEventWithOptions("extract_package", "running", "Extracting controller package", intPtr(0), 0, 0, "", &EventOptions{InstallDir: cfg.InstallDir, PackageName: firstNonEmpty(cfg.Package.Name, cfg.Storage.FileName), CPUArchitecture: cfg.Package.CPUArchitecture})
		n, err := extract(zipPath, cfg.InstallDir)
		if err != nil {
			targetPath := extractTargetPath(err)
			fatalStepWithOptions("extract_package", "Extract failed: %v", err, &EventOptions{
				ErrorType:       classifyExtractError(err),
				InstallDir:      cfg.InstallDir,
				TargetPath:      targetPath,
				PackageName:     firstNonEmpty(cfg.Package.Name, cfg.Storage.FileName),
				CPUArchitecture: cfg.Package.CPUArchitecture,
			})
		}
		os.Remove(zipPath)
		log("      Extracted %d files", n)
		emitEventWithOptions("extract_package", "success", fmt.Sprintf("Extracted %d files", n), intPtr(100), 0, 0, "", &EventOptions{InstallDir: cfg.InstallDir, PackageName: firstNonEmpty(cfg.Package.Name, cfg.Storage.FileName), CPUArchitecture: cfg.Package.CPUArchitecture})
	} else {
		log("[3/6] No storage package, skipping...")
		log("[4/6] No extraction needed...")
	}

	log("[5/6] Writing configuration...")
	emitEvent("configure_runtime", "running", "Configuring installer runtime", nil, 0, 0, "")
	if isLinux(cfg.OS) {
		log("      Linux package mode, skipping generated sidecar.yml")
	} else {
		if err := writeConfig(cfg); err != nil {
			fatalStep("configure_runtime", "Config write failed: %v", err)
		}
	}
	emitEvent("configure_runtime", "success", "Installer runtime configured", intPtr(100), 0, 0, "")

	log("[6/6] Registering service...")
	emitEventWithOptions("run_package_installer", "running", "Running package installer", nil, 0, 0, "", &EventOptions{InstallDir: cfg.InstallDir, CPUArchitecture: cfg.Package.CPUArchitecture})
	if isLinux(cfg.OS) {
		if err := runLinuxInstaller(cfg); err != nil {
			fatalStepWithOptions("run_package_installer", "Linux install failed: %v", err, eventOptionsForExecError(err, &EventOptions{InstallDir: cfg.InstallDir, CPUArchitecture: cfg.Package.CPUArchitecture}))
		}
	} else {
		if err := registerService(cfg.InstallDir); err != nil {
			fatalStepWithOptions("run_package_installer", "Service registration failed: %v", err, eventOptionsForExecError(err, &EventOptions{InstallDir: cfg.InstallDir, CPUArchitecture: cfg.Package.CPUArchitecture}))
		}
	}
	emitEventWithOptions("run_package_installer", "success", "Package installer finished", intPtr(100), 0, 0, "", &EventOptions{InstallDir: cfg.InstallDir, CPUArchitecture: cfg.Package.CPUArchitecture})

	log("")
	log("Installation complete!")
	emitEvent("complete", "success", "Installation complete", intPtr(100), 0, 0, "")
}

func log(format string, args ...interface{}) {
	fmt.Printf(format+"\n", args...)
	os.Stdout.Sync()
}

func emitEvent(step, status, message string, progress *int, downloaded, total int64, errMsg string) {
	emitEventWithOptions(step, status, message, progress, downloaded, total, errMsg, nil)
}

func emitEventWithOptions(step, status, message string, progress *int, downloaded, total int64, errMsg string, options *EventOptions) {
	event := InstallerEvent{
		Step:       step,
		Status:     status,
		Message:    message,
		Progress:   progress,
		Downloaded: downloaded,
		Total:      total,
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		Error:      errMsg,
	}
	if options != nil {
		event.ErrorType = strings.TrimSpace(options.ErrorType)
		event.Bucket = strings.TrimSpace(options.Bucket)
		event.FileKey = strings.TrimSpace(options.FileKey)
		event.FileName = strings.TrimSpace(options.FileName)
		event.PackageName = strings.TrimSpace(options.PackageName)
		event.CPUArchitecture = strings.TrimSpace(options.CPUArchitecture)
		event.InstallDir = strings.TrimSpace(options.InstallDir)
		event.TargetPath = strings.TrimSpace(options.TargetPath)
		event.ExitCode = options.ExitCode
	}
	payload, err := json.Marshal(event)
	if err != nil {
		fmt.Printf("BKINSTALL_EVENT %s\n", fmt.Sprintf(`{"step":"%s","status":"%s","message":"%s"}`, step, status, message))
	} else {
		fmt.Printf("BKINSTALL_EVENT %s\n", string(payload))
	}
	os.Stdout.Sync()
}

func intPtr(v int) *int {
	return &v
}

func fatal(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, "ERROR: "+format+"\n", args...)
	os.Exit(1)
}

func fatalStep(step, format string, err error) {
	fatalStepWithOptions(step, format, err, nil)
}

func fatalStepWithOptions(step, format string, err error, options *EventOptions) {
	msg := fmt.Sprintf(format, err)
	emitEventWithOptions(step, "failed", msg, nil, 0, 0, msg, options)
	fatal("%s", msg)
}

func intValuePtr(v int) *int {
	return &v
}

func classifyDownloadError(err error) string {
	if err == nil {
		return ""
	}
	message := strings.ToLower(err.Error())
	switch {
	case strings.Contains(message, "object not found") || strings.Contains(message, "get object failed"):
		return "object_missing"
	case strings.Contains(message, "open object store failed") && strings.Contains(message, "not found"):
		return "bucket_missing"
	case strings.Contains(message, "authorization") || strings.Contains(message, "authentication") || strings.Contains(message, "access denied"):
		return "auth"
	case strings.Contains(message, "connect nats failed") || strings.Contains(message, "connection refused") || strings.Contains(message, "network is unreachable"):
		return "connection"
	// 服务端 installer_schema 仅识别 timeout/connection 等枚举值，
	// i/o timeout 归类为 timeout 以保证 failure summary 与 retriable 标记正确
	case strings.Contains(message, "read pipe") || strings.Contains(message, "i/o timeout"):
		return "timeout"
	default:
		return ""
	}
}

func classifyExtractError(err error) string {
	if err == nil {
		return ""
	}
	message := strings.ToLower(err.Error())
	switch {
	case strings.Contains(message, "text file busy"):
		return "file_busy"
	case strings.Contains(message, "permission denied") || strings.Contains(message, "operation not permitted"):
		return "permission"
	case strings.Contains(message, "no space left on device"):
		return "disk"
	case strings.Contains(message, "invalid") || strings.Contains(message, "unexpected eof") || strings.Contains(message, "corrupt"):
		return "package_invalid"
	default:
		return ""
	}
}

func classifyInstallError(err error) string {
	if err == nil {
		return ""
	}
	message := strings.ToLower(err.Error())
	switch {
	case strings.Contains(message, "permission denied") || strings.Contains(message, "operation not permitted"):
		return "permission"
	case strings.Contains(message, "exec format error"):
		return "arch_mismatch"
	default:
		return ""
	}
}

func downloadEventOptions(cfg *Config) *EventOptions {
	if cfg == nil {
		return nil
	}
	return &EventOptions{
		Bucket:          cfg.Storage.Bucket,
		FileKey:         firstNonEmpty(cfg.Storage.FileKey, cfg.Package.FileKey),
		FileName:        cfg.Storage.FileName,
		PackageName:     firstNonEmpty(cfg.Package.Name, cfg.Storage.FileName),
		CPUArchitecture: cfg.Package.CPUArchitecture,
		InstallDir:      cfg.InstallDir,
	}
}

func extractTargetPath(err error) string {
	if err == nil {
		return ""
	}
	matcher := regexp.MustCompile(`open\s+([^:]+):\s+text file busy`)
	match := matcher.FindStringSubmatch(err.Error())
	if len(match) == 2 {
		return strings.TrimSpace(match[1])
	}
	return ""
}

func eventOptionsForExecError(err error, options *EventOptions) *EventOptions {
	base := &EventOptions{}
	if options != nil {
		*base = *options
	}
	base.ErrorType = firstNonEmpty(base.ErrorType, classifyInstallError(err))
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		base.ExitCode = intValuePtr(exitErr.ExitCode())
	}
	return base
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func newHTTPClient(skipTLS bool) *http.Client {
	tr := &http.Transport{}
	if skipTLS {
		tr.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	}
	return &http.Client{Transport: tr, Timeout: 120 * time.Second}
}

func fetchConfig(client *http.Client, url string) (*Config, error) {
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	var cfg Config
	if err := json.NewDecoder(resp.Body).Decode(&cfg); err != nil {
		return nil, fmt.Errorf("invalid JSON: %v", err)
	}

	if cfg.ZoneID == "" {
		cfg.ZoneID = "1"
	}
	if cfg.GroupID == "" {
		cfg.GroupID = "1"
	}
	if cfg.NodeName == "" {
		cfg.NodeName = cfg.NodeID
	}
	if cfg.OS == "" {
		cfg.OS = "windows"
	}
	return &cfg, nil
}

func isLinux(osName string) bool {
	return strings.EqualFold(strings.TrimSpace(osName), "linux")
}

func runLinuxInstaller(cfg *Config) error {
	installScript := filepath.Join(cfg.InstallDir, "install.sh")
	if _, err := os.Stat(installScript); err != nil {
		return fmt.Errorf("install.sh not found at %s", installScript)
	}
	if err := os.Chmod(installScript, 0755); err != nil {
		return err
	}
	cmd := exec.Command(
		installScript,
		cfg.ServerURL,
		cfg.APIToken,
		cfg.ZoneID,
		cfg.GroupID,
		cfg.NodeName,
		cfg.NodeID,
		cfg.Package.CPUArchitecture,
	)
	cmd.Dir = cfg.InstallDir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func printConfig(cfg *Config) {
	mask := func(s string) string {
		if len(s) <= 8 {
			return "****"
		}
		return s[:4] + "****" + s[len(s)-4:]
	}
	fmt.Printf("Server URL:   %s\r\n", cfg.ServerURL)
	fmt.Printf("Node ID:      %s\r\n", cfg.NodeID)
	fmt.Printf("Node Name:    %s\r\n", cfg.NodeName)
	fmt.Printf("Zone ID:      %s\r\n", cfg.ZoneID)
	fmt.Printf("Group ID:     %s\r\n", cfg.GroupID)
	if cfg.APIToken != "" {
		fmt.Printf("API Token:    %s\r\n", mask(cfg.APIToken))
	}
	if cfg.Storage.FileKey != "" {
		fmt.Printf("Package Key:  %s\r\n", cfg.Storage.FileKey)
	}
}

func downloadFromStorage(storage *StorageConfig) (string, error) {
	if strings.TrimSpace(storage.NATSServers) == "" {
		return "", fmt.Errorf("missing nats_servers")
	}
	if strings.TrimSpace(storage.Bucket) == "" {
		return "", fmt.Errorf("missing bucket")
	}
	if strings.TrimSpace(storage.FileKey) == "" {
		return "", fmt.Errorf("missing file_key")
	}

	serverURL := normalizeNATSURL(storage.NATSProtocol, storage.NATSServers)
	options := []nats.Option{}
	if storage.NATSUsername != "" {
		options = append(options, nats.UserInfo(storage.NATSUsername, storage.NATSPassword))
	}
	if strings.EqualFold(strings.TrimSpace(storage.NATSProtocol), "tls") {
		tlsConfig := &tls.Config{}
		if *skipTLS {
			tlsConfig.InsecureSkipVerify = true
		} else if strings.TrimSpace(storage.NATSTLSCA) != "" {
			pool := x509.NewCertPool()
			if !pool.AppendCertsFromPEM([]byte(storage.NATSTLSCA)) {
				return "", fmt.Errorf("invalid nats_tls_ca PEM content")
			}
			tlsConfig.RootCAs = pool
		}
		options = append(options, nats.Secure(tlsConfig))
	}

	nc, err := nats.Connect(serverURL, options...)
	if err != nil {
		return "", fmt.Errorf("connect nats failed: %w", err)
	}
	defer nc.Close()

	js, err := nc.JetStream(nats.MaxWait(objectStoreMaxWait))
	if err != nil {
		return "", fmt.Errorf("create jetstream context failed: %w", err)
	}

	store, err := js.ObjectStore(storage.Bucket)
	if err != nil {
		return "", fmt.Errorf("open object store failed: %w", err)
	}

	obj, err := store.Get(storage.FileKey)
	if err != nil {
		return "", fmt.Errorf("get object failed: %w", err)
	}
	defer obj.Close()

	meta, _ := store.GetInfo(storage.FileKey)
	totalSize := int64(0)
	if meta != nil {
		totalSize = int64(meta.Size)
	}

	tmp := filepath.Join(os.TempDir(), fmt.Sprintf("sidecar-%d.zip", time.Now().UnixNano()))
	f, err := os.Create(tmp)
	if err != nil {
		return "", err
	}
	defer f.Close()

	if totalSize > 0 {
		pw := &progressWriter{total: totalSize, desc: "Downloading", step: "download_package"}
		_, err = io.Copy(f, io.TeeReader(obj, pw))
		if err == nil && pw.lastPct < 100 {
			emitEvent("download_package", "running", "Downloading", intPtr(100), totalSize, totalSize, "")
		}
	} else {
		_, err = io.Copy(f, obj)
	}
	if err != nil {
		os.Remove(tmp)
		return "", err
	}

	return tmp, nil
}

func normalizeNATSURL(protocol, servers string) string {
	trimmed := strings.TrimSpace(servers)
	if strings.Contains(trimmed, "://") {
		return trimmed
	}
	proto := strings.TrimSpace(protocol)
	if proto == "" {
		proto = "nats"
	}
	return fmt.Sprintf("%s://%s", proto, trimmed)
}

func prepareDirs(base string) error {
	dirs := []string{"", "bin", "cache", "logs", "generated"}
	for _, d := range dirs {
		if err := os.MkdirAll(filepath.Join(base, d), 0755); err != nil {
			return err
		}
	}
	return nil
}

type progressWriter struct {
	total      int64
	downloaded int64
	lastPct    int
	desc       string
	step       string
}

func (pw *progressWriter) Write(p []byte) (int, error) {
	n := len(p)
	pw.downloaded += int64(n)
	if pw.total > 0 {
		pct := int(pw.downloaded * 100 / pw.total)
		if pct/5 > pw.lastPct/5 {
			log("      %s... %d%%", pw.desc, pct)
			emitEvent(pw.step, "running", pw.desc, intPtr(pct), pw.downloaded, pw.total, "")
			pw.lastPct = pct
		}
	}
	return n, nil
}

func download(client *http.Client, url string) (string, error) {
	resp, err := client.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	tmp := filepath.Join(os.TempDir(), fmt.Sprintf("sidecar-%d.zip", time.Now().UnixNano()))
	f, err := os.Create(tmp)
	if err != nil {
		return "", err
	}

	if resp.ContentLength > 0 {
		log("      Downloading... 0%%")
		pw := &progressWriter{total: resp.ContentLength, desc: "Downloading", step: "download_package"}
		_, err = io.Copy(f, io.TeeReader(resp.Body, pw))
		if pw.lastPct < 100 {
			log("      Downloading... 100%%")
			emitEvent("download_package", "running", "Downloading", intPtr(100), resp.ContentLength, resp.ContentLength, "")
		}
	} else {
		_, err = io.Copy(f, resp.Body)
	}
	f.Close()

	if err != nil {
		os.Remove(tmp)
		return "", err
	}
	return tmp, nil
}

func extract(zipPath, dest string) (int, error) {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return 0, err
	}
	defer r.Close()

	stripPrefix := detectCommonPrefix(r.File)

	totalFiles := 0
	for _, f := range r.File {
		if !f.FileInfo().IsDir() {
			totalFiles++
		}
	}

	count := 0
	lastPct := 0
	if totalFiles > 0 {
		log("      Extracting... 0%%")
		emitEvent("extract_package", "running", "Extracting", intPtr(0), 0, int64(totalFiles), "")
	}
	destClean := filepath.Clean(dest) + string(os.PathSeparator)

	for _, f := range r.File {
		name := f.Name
		if stripPrefix != "" {
			name = strings.TrimPrefix(name, stripPrefix)
			if name == "" {
				continue
			}
		}

		target := filepath.Join(dest, name)
		if !strings.HasPrefix(filepath.Clean(target)+string(os.PathSeparator), destClean) {
			if filepath.Clean(target) != filepath.Clean(dest) {
				continue
			}
		}

		if f.FileInfo().IsDir() {
			os.MkdirAll(target, f.Mode())
			continue
		}

		os.MkdirAll(filepath.Dir(target), 0755)

		out, err := os.OpenFile(target, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
		if err != nil {
			return count, err
		}

		in, err := f.Open()
		if err != nil {
			out.Close()
			return count, err
		}

		_, err = io.Copy(out, in)
		in.Close()
		out.Close()
		if err != nil {
			return count, err
		}
		count++

		if totalFiles > 0 {
			pct := count * 100 / totalFiles
			if pct/5 > lastPct/5 {
				log("      Extracting... %d%%", pct)
				emitEvent("extract_package", "running", "Extracting", intPtr(pct), int64(count), int64(totalFiles), "")
				lastPct = pct
			}
		}
	}

	if totalFiles > 0 && lastPct < 100 {
		log("      Extracting... 100%%")
		emitEvent("extract_package", "running", "Extracting", intPtr(100), int64(totalFiles), int64(totalFiles), "")
	}

	return count, nil
}

// detectCommonPrefix finds a common top-level directory prefix if all files share one
func detectCommonPrefix(files []*zip.File) string {
	if len(files) == 0 {
		return ""
	}

	var prefix string
	for _, f := range files {
		name := f.Name
		// Get the first path component
		idx := strings.Index(name, "/")
		if idx == -1 {
			// File at root level, no common prefix
			return ""
		}
		firstDir := name[:idx+1] // include trailing slash

		if prefix == "" {
			prefix = firstDir
		} else if prefix != firstDir {
			// Different top-level directories, no common prefix
			return ""
		}
	}
	return prefix
}

func writeConfig(cfg *Config) error {
	escapePath := func(p string) string {
		return strings.ReplaceAll(p, `\`, `\\`)
	}
	installDir := escapePath(cfg.InstallDir)

	content := fmt.Sprintf(`server_url: "%s"
server_api_token: "%s"
node_id: "%s"
node_name: "%s"
update_interval: 10
tls_skip_verify: true
send_status: true
cache_path: "%s\\cache"
log_path: "%s\\logs"
collector_configuration_directory: "%s\\generated"
tags: ["zone:%s", "group:%s", "cpu_architecture:%s"]
collector_binaries_accesslist:
  - "%s\\bin\\*"
  - "%s\\bin\\*\\*"
`,
		cfg.ServerURL,
		cfg.APIToken,
		cfg.NodeID,
		cfg.NodeName,
		installDir, installDir, installDir,
		cfg.ZoneID, cfg.GroupID, cfg.Package.CPUArchitecture,
		installDir, installDir,
	)

	return os.WriteFile(filepath.Join(cfg.InstallDir, "sidecar.yml"), []byte(content), 0644)
}

func registerService(installDir string) error {
	exePath := filepath.Join(installDir, "collector-sidecar.exe")
	cfgPath := filepath.Join(installDir, "sidecar.yml")
	logPath := filepath.Join(installDir, "logs")

	if _, err := os.Stat(exePath); os.IsNotExist(err) {
		return fmt.Errorf("collector-sidecar.exe not found at %s", exePath)
	}

	if _, err := os.Stat(cfgPath); os.IsNotExist(err) {
		return fmt.Errorf("sidecar.yml not found at %s", cfgPath)
	}

	binPath := fmt.Sprintf(`"%s" -c "%s"`, exePath, cfgPath)

	exec.Command("sc.exe", "stop", "sidecar").Run()
	time.Sleep(time.Second)
	exec.Command("sc.exe", "delete", "sidecar").Run()
	time.Sleep(time.Second)

	out, err := exec.Command("sc.exe", "create", "sidecar",
		"binPath=", binPath,
		"start=", "auto",
		"DisplayName=", "Collector Sidecar",
	).CombinedOutput()
	if err != nil {
		return fmt.Errorf("sc create failed: %s\n\nTroubleshooting:\n  1. Run as Administrator\n  2. Check: sc.exe query sidecar\n  3. Manual delete: sc.exe delete sidecar", strings.TrimSpace(string(out)))
	}

	exec.Command("sc.exe", "description", "sidecar", "Collector Sidecar - Log and metric collector agent").Run()

	out, err = exec.Command("sc.exe", "start", "sidecar").CombinedOutput()
	if err != nil {
		return serviceStartError(string(out), exePath, cfgPath, logPath)
	}

	for i := 0; i < 10; i++ {
		time.Sleep(time.Second)
		out, _ := exec.Command("sc.exe", "query", "sidecar").Output()
		if strings.Contains(string(out), "RUNNING") {
			log("      Service is running")
			return nil
		}
	}

	out, _ = exec.Command("sc.exe", "query", "sidecar").Output()
	return serviceStartError(string(out), exePath, cfgPath, logPath)
}

func serviceStartError(scOutput, exePath, cfgPath, logPath string) error {
	return fmt.Errorf(`service failed to start

sc.exe output:
%s

Troubleshooting steps:
  1. Check service status:
     sc.exe query sidecar
     sc.exe qc sidecar

  2. Test executable directly:
     "%s" -c "%s"

  3. Check logs:
     dir "%s"

  4. Verify config file:
     type "%s"

  5. Check Windows Event Viewer:
     eventvwr.msc -> Windows Logs -> Application

  6. Manual service control:
     sc.exe stop sidecar
     sc.exe delete sidecar
     sc.exe create sidecar binPath= "..." start= auto`,
		strings.TrimSpace(scOutput), exePath, cfgPath, logPath, cfgPath)
}

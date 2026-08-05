package main

import (
	"archive/zip"
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
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

var (
	controllerPackageMaxDownloadBytes int64 = 4 * 1024 * 1024 * 1024
	controllerPackageMaxExpandedBytes int64 = 8 * 1024 * 1024 * 1024
	controllerPackageMaxFiles               = 100000
)

const windowsServiceTransitionAttempts = 30

type Config struct {
	ServerURL                string                 `json:"server_url"`
	APIToken                 string                 `json:"api_token"`
	NodeID                   string                 `json:"node_id"`
	NodeName                 string                 `json:"node_name"`
	ZoneID                   string                 `json:"zone_id"`
	GroupID                  string                 `json:"group_id"`
	OS                       string                 `json:"os"`
	InstallDir               string                 `json:"install_dir"`
	SkipTLSVerification      bool                   `json:"-"`
	RemoteTaskNodeID         int64                  `json:"-"`
	RemoteAttempt            int                    `json:"-"`
	RemoteExecutionID        string                 `json:"-"`
	RemoteDeadlineUnix       int64                  `json:"-"`
	RemoteLeaseValidator     func() error           `json:"-"`
	ClockValidation          *ClockValidationConfig `json:"clock_validation,omitempty"`
	Package                  PackageConfig          `json:"package"`
	Storage                  StorageConfig          `json:"storage"`
	sessionRequestStartedAt  time.Time
	sessionRequestFinishedAt time.Time
}

func (cfg *Config) UnmarshalJSON(data []byte) error {
	type configAlias Config
	var decoded configAlias
	if err := json.Unmarshal(data, &decoded); err != nil {
		return err
	}

	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return err
	}
	if raw, exists := fields["clock_validation"]; exists && string(bytes.TrimSpace(raw)) == "null" {
		return fmt.Errorf("clock_validation must not be null")
	}

	*cfg = Config(decoded)
	return nil
}

type ClockValidationConfig struct {
	ServerTimeUnixMS int64 `json:"server_time_unix_ms"`
	MaxSkewSeconds   int64 `json:"max_skew_seconds"`
}

type ClockSkewResult struct {
	NodeTime       time.Time
	ServerTime     time.Time
	OffsetSeconds  float64
	SkewSeconds    float64
	MaxSkewSeconds int64
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
	Step                string  `json:"step"`
	Status              string  `json:"status"`
	Message             string  `json:"message,omitempty"`
	Progress            *int    `json:"progress,omitempty"`
	Downloaded          int64   `json:"downloaded_bytes,omitempty"`
	Total               int64   `json:"total_bytes,omitempty"`
	Timestamp           string  `json:"timestamp"`
	StepIndex           int     `json:"step_index,omitempty"`
	StepTotal           int     `json:"step_total,omitempty"`
	Error               string  `json:"error,omitempty"`
	ErrorType           string  `json:"error_type,omitempty"`
	Bucket              string  `json:"bucket,omitempty"`
	FileKey             string  `json:"file_key,omitempty"`
	FileName            string  `json:"file_name,omitempty"`
	PackageName         string  `json:"package_name,omitempty"`
	CPUArchitecture     string  `json:"cpu_architecture,omitempty"`
	InstallDir          string  `json:"install_dir,omitempty"`
	TargetPath          string  `json:"target_path,omitempty"`
	ExitCode            *int    `json:"exit_code,omitempty"`
	NodeTime            string  `json:"node_time,omitempty"`
	ServerTime          string  `json:"server_time,omitempty"`
	ClockOffsetSeconds  float64 `json:"clock_offset_seconds,omitempty"`
	ClockSkewSeconds    float64 `json:"clock_skew_seconds,omitempty"`
	MaxClockSkewSeconds int64   `json:"max_clock_skew_seconds,omitempty"`
}

var installerStepSequence = []string{
	"fetch_session",
	"clock_check",
	"prepare_directories",
	"download_package",
	"extract_package",
	"configure_runtime",
	"run_package_installer",
	"complete",
}

func installerStepPosition(step string) (int, int) {
	for index, candidate := range installerStepSequence {
		if step == candidate {
			return index + 1, len(installerStepSequence)
		}
	}
	return 0, 0
}

type EventOptions struct {
	ErrorType           string
	Bucket              string
	FileKey             string
	FileName            string
	PackageName         string
	CPUArchitecture     string
	InstallDir          string
	TargetPath          string
	ExitCode            *int
	NodeTime            string
	ServerTime          string
	ClockOffsetSeconds  float64
	ClockSkewSeconds    float64
	MaxClockSkewSeconds int64
}

type progressPublisher interface {
	Publish(subject string, payload []byte) error
}

type progressFlusher interface {
	FlushTimeout(timeout time.Duration) error
}

type InstallerEventReporter struct {
	output      io.Writer
	subject     string
	executionID string
	publisher   progressPublisher
	pending     []string
}

var progressExecutionIDPattern = regexp.MustCompile(`^[0-9a-f]{32}$`)

func NewInstallerEventReporter(output io.Writer, subject, executionID string) (*InstallerEventReporter, error) {
	subject = strings.TrimSpace(subject)
	executionID = strings.TrimSpace(executionID)
	if output == nil {
		return nil, fmt.Errorf("event output is required")
	}
	if subject == "" && executionID == "" {
		return &InstallerEventReporter{output: output}, nil
	}
	if !progressExecutionIDPattern.MatchString(executionID) {
		return nil, fmt.Errorf("execution ID must be 32 lowercase hexadecimal characters")
	}
	expectedSubject := "installer.progress." + executionID
	if subject != expectedSubject {
		return nil, fmt.Errorf("progress subject must be %s", expectedSubject)
	}
	return &InstallerEventReporter{output: output, subject: subject, executionID: executionID}, nil
}

func (reporter *InstallerEventReporter) Attach(publisher progressPublisher) {
	reporter.publisher = publisher
	if publisher == nil {
		return
	}
	for _, line := range reporter.pending {
		reporter.publish(line)
	}
	reporter.pending = nil
}

func (reporter *InstallerEventReporter) Emit(event InstallerEvent) {
	if strings.TrimSpace(event.Timestamp) == "" {
		event.Timestamp = time.Now().UTC().Format(time.RFC3339)
	}
	payload, err := json.Marshal(event)
	if err != nil {
		payload = []byte(fmt.Sprintf(`{"step":%q,"status":%q,"message":%q}`, event.Step, event.Status, event.Message))
	}
	line := "BKINSTALL_EVENT " + string(payload)
	_, _ = fmt.Fprintln(reporter.output, line)
	if reporter.subject == "" {
		return
	}
	if reporter.publisher == nil {
		if len(reporter.pending) < 128 {
			reporter.pending = append(reporter.pending, line)
		}
		return
	}
	reporter.publish(line)
	if event.Status == "failed" || event.Step == "complete" {
		if flusher, ok := reporter.publisher.(progressFlusher); ok {
			_ = flusher.FlushTimeout(time.Second)
		}
	}
}

func (reporter *InstallerEventReporter) publish(line string) {
	envelope, err := json.Marshal(map[string]string{
		"execution_id": reporter.executionID,
		"stream":       "stdout",
		"line":         line,
		"timestamp":    time.Now().UTC().Format(time.RFC3339),
	})
	if err == nil {
		_ = reporter.publisher.Publish(reporter.subject, envelope)
	}
}

var installerEventReporter, _ = NewInstallerEventReporter(os.Stdout, "", "")

var (
	configURL         = flag.String("url", "", "Configuration URL")
	configURLFile     = flag.String("url-file", "", "Read the configuration URL from a file")
	installDir        = flag.String("install-dir", "", "Installation directory")
	skipTLS           = flag.Bool("skip-tls", false, "Skip TLS certificate verification")
	requireHTTPS      = flag.Bool("require-https", false, "Require HTTPS for configuration and server URLs")
	fetchOnly         = flag.Bool("fetch-only", false, "Only fetch and display config")
	progressSubject   = flag.String("progress-subject", "", "NATS subject for live installation events")
	executionID       = flag.String("execution-id", "", "Installation execution ID")
	taskNodeID        = flag.Int64("task-node-id", 0, "Controller task node ID used for remote execution fencing")
	executionAttempt  = flag.Int("attempt", 0, "Controller task attempt used for remote execution fencing")
	executionDeadline = flag.Int64("deadline-unix", 0, "Non-extendable remote execution deadline")
)

func main() {
	flag.Parse()
	reporter, err := NewInstallerEventReporter(os.Stdout, *progressSubject, *executionID)
	if err != nil {
		fatal("Invalid progress configuration: %v", err)
	}
	installerEventReporter = reporter

	resolvedConfigURL, err := resolveConfigURL(*configURL, *configURLFile)
	if err != nil {
		fatal("%v", err)
	}
	*configURL = resolvedConfigURL
	if *requireHTTPS {
		if err := validateHTTPSURL(*configURL); err != nil {
			fatal("Invalid configuration URL: %v", err)
		}
	}

	client := newHTTPClient(*skipTLS)
	if *requireHTTPS {
		client.CheckRedirect = func(request *http.Request, _ []*http.Request) error {
			return validateHTTPSURL(request.URL.String())
		}
	}

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

func resolveConfigURL(directURL, urlFile string) (string, error) {
	directURL = strings.TrimSpace(directURL)
	urlFile = strings.TrimSpace(urlFile)
	if directURL != "" && urlFile != "" {
		return "", fmt.Errorf("--url and --url-file cannot be used together")
	}
	if directURL != "" {
		return directURL, nil
	}
	if urlFile == "" {
		return "", fmt.Errorf("--url or --url-file is required")
	}
	content, err := os.ReadFile(urlFile)
	if err != nil {
		return "", fmt.Errorf("read configuration URL file: %w", err)
	}
	resolved := strings.TrimSpace(string(content))
	if resolved == "" {
		return "", fmt.Errorf("configuration URL file is empty")
	}
	return resolved, nil
}

func validateHTTPSURL(rawURL string) error {
	parsed, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return err
	}
	if !strings.EqualFold(parsed.Scheme, "https") || parsed.Host == "" {
		return fmt.Errorf("HTTPS URL is required")
	}
	return nil
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
	if *requireHTTPS {
		if err := validateHTTPSURL(cfg.ServerURL); err != nil {
			fatalStep("fetch_session", "Invalid server URL: %v", err)
		}
	}
	if *progressSubject != "" {
		progressConnection, progressErr := connectNATS(&cfg.Storage)
		if progressErr != nil {
			log("WARN: live installation progress unavailable: %v", progressErr)
		} else {
			installerEventReporter.Attach(progressConnection)
			defer progressConnection.Close()
		}
	}
	emitEvent("fetch_session", "success", "Installer session fetched", intPtr(100), 0, 0, "")
	if cfg.ClockValidation != nil {
		emitEvent("clock_check", "running", "Checking node and Server clocks", nil, 0, 0, "")
		clockResult, clockErr := validateClockSkew(cfg)
		if clockErr != nil {
			errorType := ""
			if clockResult != nil {
				errorType = "clock_skew"
			}
			fatalStepWithOptions("clock_check", "Clock check failed: %v", clockErr, clockEventOptions(clockResult, errorType))
		}
		emitEventWithOptions(
			"clock_check",
			"success",
			fmt.Sprintf("Node and Server clock skew is %.3f seconds", clockResult.SkewSeconds),
			intPtr(100),
			0,
			0,
			"",
			clockEventOptions(clockResult, ""),
		)
	}
	cfg.SkipTLSVerification = *skipTLS
	cfg.RemoteTaskNodeID = *taskNodeID
	cfg.RemoteAttempt = *executionAttempt
	cfg.RemoteExecutionID = *executionID
	cfg.RemoteDeadlineUnix = *executionDeadline
	if cfg.RemoteExecutionID != "" {
		cfg.RemoteLeaseValidator = func() error {
			if _, err := fetchConfig(client, *configURL); err != nil {
				return fmt.Errorf("validate active Windows remote installation lease: %w", err)
			}
			return nil
		}
	}
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
	if err := prepareInstallDirectories(cfg); err != nil {
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
		if !isLinux(cfg.OS) {
			log("[4/6] Staging and validating files...")
			emitEventWithOptions("extract_package", "running", "Staging controller package", intPtr(0), 0, 0, "", &EventOptions{InstallDir: cfg.InstallDir, PackageName: firstNonEmpty(cfg.Package.Name, cfg.Storage.FileName), CPUArchitecture: cfg.Package.CPUArchitecture})
			installErr := installWindowsPackage(cfg, zipPath, &scWindowsServiceController{})
			_ = os.Remove(zipPath)
			if installErr != nil {
				fatalStepWithOptions("run_package_installer", "Transactional Windows installation failed: %v", installErr, eventOptionsForExecError(installErr, &EventOptions{InstallDir: cfg.InstallDir, CPUArchitecture: cfg.Package.CPUArchitecture}))
			}
			emitEventWithOptions("extract_package", "success", "Controller package staged and activated", intPtr(100), 0, 0, "", &EventOptions{InstallDir: cfg.InstallDir, PackageName: firstNonEmpty(cfg.Package.Name, cfg.Storage.FileName), CPUArchitecture: cfg.Package.CPUArchitecture})
			emitEvent("configure_runtime", "success", "Installer runtime configured", intPtr(100), 0, 0, "")
			emitEventWithOptions("run_package_installer", "success", "Package installer finished", intPtr(100), 0, 0, "", &EventOptions{InstallDir: cfg.InstallDir, CPUArchitecture: cfg.Package.CPUArchitecture})
			log("")
			log("Installation complete!")
			emitEvent("complete", "success", "Installation complete", intPtr(100), 0, 0, "")
			return
		}

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
	stepIndex, stepTotal := installerStepPosition(step)
	event := InstallerEvent{
		Step:       step,
		Status:     status,
		Message:    message,
		Progress:   progress,
		Downloaded: downloaded,
		Total:      total,
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		StepIndex:  stepIndex,
		StepTotal:  stepTotal,
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
		event.NodeTime = strings.TrimSpace(options.NodeTime)
		event.ServerTime = strings.TrimSpace(options.ServerTime)
		event.ClockOffsetSeconds = options.ClockOffsetSeconds
		event.ClockSkewSeconds = options.ClockSkewSeconds
		event.MaxClockSkewSeconds = options.MaxClockSkewSeconds
	}
	if installerEventReporter.subject == "" {
		// Keep the historical stdout seam replaceable by tests and embedders.
		installerEventReporter.output = os.Stdout
	}
	installerEventReporter.Emit(event)
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

func validateClockSkew(cfg *Config) (*ClockSkewResult, error) {
	if cfg == nil || cfg.ClockValidation == nil {
		return nil, nil
	}
	validation := cfg.ClockValidation
	if validation.ServerTimeUnixMS <= 0 || validation.MaxSkewSeconds <= 0 {
		return nil, fmt.Errorf("invalid clock validation contract")
	}
	if cfg.sessionRequestStartedAt.IsZero() || cfg.sessionRequestFinishedAt.IsZero() || cfg.sessionRequestFinishedAt.Before(cfg.sessionRequestStartedAt) {
		return nil, fmt.Errorf("invalid installer session timing")
	}

	nodeTime := cfg.sessionRequestStartedAt.Add(cfg.sessionRequestFinishedAt.Sub(cfg.sessionRequestStartedAt) / 2)
	serverTime := time.UnixMilli(validation.ServerTimeUnixMS)
	offsetMillis := nodeTime.UnixMilli() - validation.ServerTimeUnixMS
	skewMillis := offsetMillis
	if skewMillis < 0 {
		skewMillis = -skewMillis
	}
	result := &ClockSkewResult{
		NodeTime:       nodeTime,
		ServerTime:     serverTime,
		OffsetSeconds:  float64(offsetMillis) / 1000,
		SkewSeconds:    float64(skewMillis) / 1000,
		MaxSkewSeconds: validation.MaxSkewSeconds,
	}
	if skewMillis <= validation.MaxSkewSeconds*1000 {
		return result, nil
	}

	direction := "ahead of"
	if offsetMillis < 0 {
		direction = "behind"
	}
	return result, fmt.Errorf(
		"node clock is %.3f seconds %s Server; maximum allowed skew is %d seconds; synchronize the node clock with NTP and retry",
		result.SkewSeconds,
		direction,
		validation.MaxSkewSeconds,
	)
}

func clockEventOptions(result *ClockSkewResult, errorType string) *EventOptions {
	if result == nil {
		return &EventOptions{ErrorType: errorType}
	}
	return &EventOptions{
		ErrorType:           errorType,
		NodeTime:            result.NodeTime.UTC().Format(time.RFC3339Nano),
		ServerTime:          result.ServerTime.UTC().Format(time.RFC3339Nano),
		ClockOffsetSeconds:  result.OffsetSeconds,
		ClockSkewSeconds:    result.SkewSeconds,
		MaxClockSkewSeconds: result.MaxSkewSeconds,
	}
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
	case strings.Contains(message, "previous installation retained"):
		return "manual_recovery_required"
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
	requestStartedAt := time.Now()
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %v", err)
	}

	var cfg Config
	if err := json.Unmarshal(body, &cfg); err != nil {
		return nil, fmt.Errorf("invalid JSON: %v", err)
	}
	requestFinishedAt := time.Now()

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
	cfg.sessionRequestStartedAt = requestStartedAt
	cfg.sessionRequestFinishedAt = requestFinishedAt
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

	apiTokenArg, apiTokenEnv, cleanup, err := linuxInstallerAPITokenInputs(cfg.InstallDir, cfg.APIToken)
	if err != nil {
		return err
	}
	defer cleanup()

	cmd := exec.Command(
		installScript,
		cfg.ServerURL,
		apiTokenArg,
		cfg.ZoneID,
		cfg.GroupID,
		cfg.NodeName,
		cfg.NodeID,
		cfg.Package.CPUArchitecture,
	)
	if apiTokenEnv != "" {
		cmd.Env = append(os.Environ(), apiTokenEnv)
	}
	cmd.Dir = cfg.InstallDir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func linuxInstallerAPITokenInputs(installDir, apiToken string) (string, string, func(), error) {
	cleanup := func() {}
	if apiToken == "" {
		return "", "", cleanup, nil
	}

	file, err := os.CreateTemp(installDir, ".server-api-token-*")
	if err != nil {
		return "", "", cleanup, fmt.Errorf("create API token file: %w", err)
	}
	tokenFile := file.Name()
	cleanup = func() {
		_ = os.Remove(tokenFile)
	}
	defer func() {
		_ = file.Close()
	}()

	if err := file.Chmod(0600); err != nil {
		cleanup()
		return "", "", cleanup, fmt.Errorf("restrict API token file: %w", err)
	}
	if _, err := file.WriteString(apiToken); err != nil {
		cleanup()
		return "", "", cleanup, fmt.Errorf("write API token file: %w", err)
	}
	if err := file.Close(); err != nil {
		cleanup()
		return "", "", cleanup, fmt.Errorf("close API token file: %w", err)
	}

	return "", "BK_LITE_SERVER_API_TOKEN_FILE=" + tokenFile, cleanup, nil
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

func connectNATS(storage *StorageConfig) (*nats.Conn, error) {
	if strings.TrimSpace(storage.NATSServers) == "" {
		return nil, fmt.Errorf("missing nats_servers")
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
				return nil, fmt.Errorf("invalid nats_tls_ca PEM content")
			}
			tlsConfig.RootCAs = pool
		}
		options = append(options, nats.Secure(tlsConfig))
	}

	nc, err := nats.Connect(serverURL, options...)
	if err != nil {
		return nil, fmt.Errorf("connect nats failed: %w", err)
	}
	return nc, nil
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

	nc, err := connectNATS(storage)
	if err != nil {
		return "", err
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
	if totalSize > controllerPackageMaxDownloadBytes {
		return "", fmt.Errorf("controller package exceeds download size limit: %d > %d", totalSize, controllerPackageMaxDownloadBytes)
	}

	tmp := filepath.Join(os.TempDir(), fmt.Sprintf("sidecar-%d.zip", time.Now().UnixNano()))
	f, err := os.Create(tmp)
	if err != nil {
		return "", err
	}
	defer f.Close()

	limitedObject := io.LimitReader(obj, controllerPackageMaxDownloadBytes+1)
	var downloaded int64
	if totalSize > 0 {
		pw := &progressWriter{total: totalSize, desc: "Downloading", step: "download_package"}
		downloaded, err = io.Copy(f, io.TeeReader(limitedObject, pw))
		if err == nil && pw.lastPct < 100 {
			emitEvent("download_package", "running", "Downloading", intPtr(100), totalSize, totalSize, "")
		}
	} else {
		downloaded, err = io.Copy(f, limitedObject)
	}
	if downloaded > controllerPackageMaxDownloadBytes {
		err = fmt.Errorf("controller package exceeds download size limit: %d", controllerPackageMaxDownloadBytes)
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

func prepareInstallDirectories(cfg *Config) error {
	if isLinux(cfg.OS) {
		return prepareDirs(cfg.InstallDir)
	}
	installDir := filepath.Clean(cfg.InstallDir)
	if installDir == "." || installDir == string(os.PathSeparator) {
		return fmt.Errorf("unsafe Windows installation directory: %s", installDir)
	}
	return nil
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
	if resp.ContentLength > controllerPackageMaxDownloadBytes {
		return "", fmt.Errorf("controller package exceeds download size limit: %d > %d", resp.ContentLength, controllerPackageMaxDownloadBytes)
	}

	tmp := filepath.Join(os.TempDir(), fmt.Sprintf("sidecar-%d.zip", time.Now().UnixNano()))
	f, err := os.Create(tmp)
	if err != nil {
		return "", err
	}

	limitedBody := io.LimitReader(resp.Body, controllerPackageMaxDownloadBytes+1)
	var downloaded int64
	if resp.ContentLength > 0 {
		log("      Downloading... 0%%")
		pw := &progressWriter{total: resp.ContentLength, desc: "Downloading", step: "download_package"}
		downloaded, err = io.Copy(f, io.TeeReader(limitedBody, pw))
		if pw.lastPct < 100 {
			log("      Downloading... 100%%")
			emitEvent("download_package", "running", "Downloading", intPtr(100), resp.ContentLength, resp.ContentLength, "")
		}
	} else {
		downloaded, err = io.Copy(f, limitedBody)
	}
	if downloaded > controllerPackageMaxDownloadBytes {
		err = fmt.Errorf("controller package exceeds download size limit: %d", controllerPackageMaxDownloadBytes)
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
	var expandedSize int64
	for _, f := range r.File {
		if !f.FileInfo().IsDir() {
			totalFiles++
			if totalFiles > controllerPackageMaxFiles {
				return 0, fmt.Errorf("controller package contains too many files: %d > %d", totalFiles, controllerPackageMaxFiles)
			}
			if f.UncompressedSize64 > uint64(controllerPackageMaxExpandedBytes-expandedSize) {
				return 0, fmt.Errorf("controller package expanded size exceeds limit: %d bytes", controllerPackageMaxExpandedBytes)
			}
			expandedSize += int64(f.UncompressedSize64)
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
	return writeConfigTo(cfg, cfg.InstallDir)
}

func writeConfigTo(cfg *Config, outputDir string) error {
	escapePath := func(p string) string {
		return strings.ReplaceAll(p, `\`, `\\`)
	}
	installDir := escapePath(cfg.InstallDir)

	content := fmt.Sprintf(`server_url: "%s"
server_api_token: "%s"
node_id: "%s"
node_name: "%s"
update_interval: 10
tls_skip_verify: %t
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
		cfg.SkipTLSVerification,
		installDir, installDir, installDir,
		cfg.ZoneID, cfg.GroupID, cfg.Package.CPUArchitecture,
		installDir, installDir,
	)

	configPath := filepath.Join(outputDir, "sidecar.yml")
	if err := os.WriteFile(configPath, []byte(content), 0600); err != nil {
		return err
	}
	return restrictSensitiveFile(configPath)
}

type windowsServiceController interface {
	Stop() (bool, error)
	Start(installDir string, serviceExisted bool) error
	Remove() error
}

type scWindowsServiceController struct{}

func (controller *scWindowsServiceController) Stop() (bool, error) {
	queryOutput, queryErr := exec.Command("sc.exe", "query", "sidecar").CombinedOutput()
	if queryErr != nil {
		if strings.Contains(string(queryOutput), "1060") || strings.Contains(strings.ToLower(string(queryOutput)), "does not exist") {
			return false, nil
		}
		return false, fmt.Errorf("sc query failed: %s", strings.TrimSpace(string(queryOutput)))
	}
	_ = exec.Command("sc.exe", "stop", "sidecar").Run()
	for attempt := 0; attempt < windowsServiceTransitionAttempts; attempt++ {
		output, _ := exec.Command("sc.exe", "query", "sidecar").CombinedOutput()
		if strings.Contains(string(output), "STOPPED") {
			return true, nil
		}
		time.Sleep(time.Second)
	}
	return true, fmt.Errorf("sidecar service did not stop within %d seconds", windowsServiceTransitionAttempts)
}

func (controller *scWindowsServiceController) Start(installDir string, serviceExisted bool) error {
	if !serviceExisted {
		return registerService(installDir)
	}
	return startWindowsService(installDir)
}

func (controller *scWindowsServiceController) Remove() error {
	deleteOutput, deleteErr := exec.Command("sc.exe", "delete", "sidecar").CombinedOutput()
	if deleteErr != nil {
		if strings.Contains(string(deleteOutput), "1060") || strings.Contains(strings.ToLower(string(deleteOutput)), "does not exist") {
			return nil
		}
		return fmt.Errorf("sc delete failed: %s", strings.TrimSpace(string(deleteOutput)))
	}
	return nil
}

var windowsRuntimeDirectories = []string{"cache", "logs", "generated"}

const (
	windowsActivationPendingMarker   = ".bklite-activation-pending"
	windowsActivationCommittedMarker = ".bklite-activation-committed"
)

func moveWindowsRuntimeData(backupDir, installDir string) ([]string, error) {
	moved := []string{}
	for _, name := range windowsRuntimeDirectories {
		source := filepath.Join(backupDir, name)
		if _, err := os.Stat(source); os.IsNotExist(err) {
			continue
		} else if err != nil {
			return moved, err
		}
		target := filepath.Join(installDir, name)
		if err := os.RemoveAll(target); err != nil {
			return moved, err
		}
		if err := os.Rename(source, target); err != nil {
			return moved, err
		}
		moved = append(moved, name)
	}
	return moved, nil
}

func restoreWindowsRuntimeData(installDir, backupDir string, moved []string) error {
	for index := len(moved) - 1; index >= 0; index-- {
		name := moved[index]
		source := filepath.Join(installDir, name)
		target := filepath.Join(backupDir, name)
		if err := os.RemoveAll(target); err != nil {
			return err
		}
		if err := os.Rename(source, target); err != nil {
			return err
		}
	}
	return nil
}

func restorePreviousWindowsInstallation(
	controller windowsServiceController,
	installDir string,
	backupDir string,
	installExisted bool,
	serviceExisted bool,
	movedRuntimeDirectories []string,
) error {
	if installExisted {
		if err := restoreWindowsRuntimeData(installDir, backupDir, movedRuntimeDirectories); err != nil {
			return fmt.Errorf("restore runtime data: %w", err)
		}
	}
	if err := os.RemoveAll(installDir); err != nil {
		return fmt.Errorf("remove failed installation: %w", err)
	}
	if installExisted {
		for _, marker := range []string{windowsActivationPendingMarker, windowsActivationCommittedMarker} {
			if err := os.Remove(filepath.Join(backupDir, marker)); err != nil && !os.IsNotExist(err) {
				return fmt.Errorf("remove activation marker: %w", err)
			}
		}
		if err := os.Rename(backupDir, installDir); err != nil {
			return fmt.Errorf("restore previous installation: %w", err)
		}
	}
	if serviceExisted && installExisted {
		if err := controller.Start(installDir, true); err != nil {
			return fmt.Errorf("restore previous service: %w", err)
		}
	}
	return nil
}

func cleanupActivatedWindowsBackup(backupDir string) {
	retainedDir := fmt.Sprintf("%s-retained-%d", backupDir, time.Now().UnixNano())
	if err := os.Rename(backupDir, retainedDir); err != nil {
		log("WARN: new service is running, but old installation backup could not be moved out of the recovery path: %v", err)
		return
	}
	if err := os.RemoveAll(retainedDir); err != nil {
		log("WARN: new service is running; old installation backup was retained at %s after cleanup failed: %v", retainedDir, err)
	}
}

func recoverInterruptedWindowsInstallation(
	controller windowsServiceController,
	installDir string,
	backupDir string,
	cfg *Config,
) error {
	backupInfo, err := os.Stat(backupDir)
	if err != nil {
		return fmt.Errorf("inspect interrupted installation backup: %w", err)
	}
	if !backupInfo.IsDir() {
		return fmt.Errorf("interrupted installation backup is not a directory: %s", backupDir)
	}
	if _, err := os.Stat(filepath.Join(backupDir, "collector-sidecar.exe")); err != nil {
		return fmt.Errorf("interrupted installation backup is invalid: %w", err)
	}
	serviceExisted, err := controller.Stop()
	if err != nil {
		if serviceExisted {
			if restartErr := controller.Start(installDir, true); restartErr != nil {
				return fmt.Errorf("stop service before interrupted installation recovery: %v; restart service: %w", err, restartErr)
			}
		}
		return fmt.Errorf("stop service before interrupted installation recovery: %w", err)
	}
	if cfg.RemoteLeaseValidator != nil {
		leaseErr := cfg.RemoteLeaseValidator()
		if leaseErr == nil {
			leaseErr = validateRemoteExecutionDeadline(cfg)
		}
		if leaseErr != nil {
			if serviceExisted {
				if restartErr := controller.Start(installDir, true); restartErr != nil {
					return fmt.Errorf("%v; restart service after recovery lease expiry: %w", leaseErr, restartErr)
				}
			}
			return leaseErr
		}
	}
	movedRuntimeDirectories := []string{}
	for _, name := range windowsRuntimeDirectories {
		source := filepath.Join(installDir, name)
		target := filepath.Join(backupDir, name)
		if _, sourceErr := os.Stat(source); sourceErr != nil {
			if os.IsNotExist(sourceErr) {
				continue
			}
			return sourceErr
		}
		if _, targetErr := os.Stat(target); os.IsNotExist(targetErr) {
			movedRuntimeDirectories = append(movedRuntimeDirectories, name)
		} else if targetErr != nil {
			return targetErr
		}
	}
	if err := restorePreviousWindowsInstallation(
		controller,
		installDir,
		backupDir,
		true,
		serviceExisted,
		movedRuntimeDirectories,
	); err != nil {
		return err
	}
	return fmt.Errorf("recovered previous Windows installation after an interrupted activation; retry installation")
}

type windowsInstallFence struct {
	TaskNodeID  int64  `json:"task_node_id"`
	Attempt     int    `json:"attempt"`
	ExecutionID string `json:"execution_id"`
}

func claimWindowsInstallFence(cfg *Config, installDir string) error {
	if cfg.RemoteTaskNodeID == 0 && cfg.RemoteAttempt == 0 && cfg.RemoteExecutionID == "" {
		return nil
	}
	if cfg.RemoteTaskNodeID <= 0 || cfg.RemoteAttempt <= 0 || cfg.RemoteExecutionID == "" {
		return fmt.Errorf("incomplete Windows remote installation fence")
	}
	if err := validateRemoteExecutionDeadline(cfg); err != nil {
		return err
	}
	current := windowsInstallFence{
		TaskNodeID:  cfg.RemoteTaskNodeID,
		Attempt:     cfg.RemoteAttempt,
		ExecutionID: cfg.RemoteExecutionID,
	}
	fencePath := installDir + ".bklite-install.fence"
	content, err := os.ReadFile(fencePath)
	if err == nil {
		var existing windowsInstallFence
		if unmarshalErr := json.Unmarshal(content, &existing); unmarshalErr != nil {
			return fmt.Errorf("read Windows installation fence: %w", unmarshalErr)
		}
		if current.TaskNodeID < existing.TaskNodeID ||
			(current.TaskNodeID == existing.TaskNodeID && current.Attempt <= existing.Attempt) {
			return fmt.Errorf(
				"stale Windows remote installation rejected: task node %d attempt %d is not newer than %d attempt %d",
				current.TaskNodeID,
				current.Attempt,
				existing.TaskNodeID,
				existing.Attempt,
			)
		}
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("read Windows installation fence: %w", err)
	}
	encoded, err := json.Marshal(current)
	if err != nil {
		return fmt.Errorf("encode Windows installation fence: %w", err)
	}
	if err := writeWindowsInstallFence(fencePath, append(encoded, '\n')); err != nil {
		return fmt.Errorf("write Windows installation fence: %w", err)
	}
	return nil
}

func validateRemoteExecutionDeadline(cfg *Config) error {
	if cfg.RemoteTaskNodeID == 0 && cfg.RemoteAttempt == 0 && cfg.RemoteExecutionID == "" {
		return nil
	}
	if cfg.RemoteDeadlineUnix <= 0 {
		return fmt.Errorf("missing Windows remote installation deadline")
	}
	if time.Now().Unix() >= cfg.RemoteDeadlineUnix {
		return fmt.Errorf("Windows remote installation deadline expired")
	}
	return nil
}

func writeWindowsInstallFence(fencePath string, content []byte) error {
	temporary, err := os.CreateTemp(filepath.Dir(fencePath), filepath.Base(fencePath)+".tmp-*")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Chmod(0600); err != nil {
		_ = temporary.Close()
		return err
	}
	if _, err := temporary.Write(content); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	return replaceFileAtomically(temporaryPath, fencePath)
}

// discardEmptyWindowsInstallDir removes an installation directory that exists but
// holds nothing. Launchers such as the NSIS GUI may create it before the worker
// runs; treating that empty directory as a previous installation would push a
// fresh install through the backup, rollback and service-restart path it does not
// need. A running installation always has files, so this never discards one.
func discardEmptyWindowsInstallDir(installDir string) error {
	entries, err := os.ReadDir(installDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	if len(entries) > 0 {
		return nil
	}
	if err := os.Remove(installDir); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

func installWindowsPackage(cfg *Config, zipPath string, controller windowsServiceController) error {
	installDir := filepath.Clean(cfg.InstallDir)
	stagingDir := installDir + ".bklite-staging"
	backupDir := installDir + ".bklite-backup"
	if installDir == "." || installDir == string(os.PathSeparator) {
		return fmt.Errorf("unsafe Windows installation directory: %s", installDir)
	}
	releaseInstallLock, err := acquireInstallLock(installDir)
	if err != nil {
		return fmt.Errorf("acquire Windows installation lock: %w", err)
	}
	defer releaseInstallLock()
	if err := claimWindowsInstallFence(cfg, installDir); err != nil {
		return err
	}
	if cfg.RemoteLeaseValidator != nil {
		if err := cfg.RemoteLeaseValidator(); err != nil {
			return err
		}
	}
	if _, err := os.Stat(backupDir); err == nil {
		committedMarker := filepath.Join(backupDir, windowsActivationCommittedMarker)
		pendingMarker := filepath.Join(backupDir, windowsActivationPendingMarker)
		if _, markerErr := os.Stat(committedMarker); markerErr == nil {
			cleanupActivatedWindowsBackup(backupDir)
			if _, cleanupErr := os.Stat(backupDir); cleanupErr == nil {
				return fmt.Errorf("committed Windows backup cleanup requires manual intervention: %s", backupDir)
			} else if !os.IsNotExist(cleanupErr) {
				return cleanupErr
			}
		} else if !os.IsNotExist(markerErr) {
			return markerErr
		} else if _, markerErr := os.Stat(pendingMarker); markerErr == nil {
			return recoverInterruptedWindowsInstallation(controller, installDir, backupDir, cfg)
		} else if !os.IsNotExist(markerErr) {
			return markerErr
		} else {
			return fmt.Errorf("Windows installation backup has no transaction marker and requires manual recovery: %s", backupDir)
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	if err := discardEmptyWindowsInstallDir(installDir); err != nil {
		return fmt.Errorf("discard empty installation directory: %w", err)
	}
	if err := os.RemoveAll(stagingDir); err != nil {
		return fmt.Errorf("clean staging directory: %w", err)
	}
	defer os.RemoveAll(stagingDir)
	if err := prepareDirs(stagingDir); err != nil {
		return fmt.Errorf("prepare staging directory: %w", err)
	}
	if _, err := extract(zipPath, stagingDir); err != nil {
		return fmt.Errorf("extract package to staging directory: %w", err)
	}
	if err := writeConfigTo(cfg, stagingDir); err != nil {
		return fmt.Errorf("write staged configuration: %w", err)
	}
	if _, err := os.Stat(filepath.Join(stagingDir, "collector-sidecar.exe")); err != nil {
		return fmt.Errorf("staged collector-sidecar.exe validation failed: %w", err)
	}
	if err := validateRemoteExecutionDeadline(cfg); err != nil {
		return err
	}
	if cfg.RemoteLeaseValidator != nil {
		if err := cfg.RemoteLeaseValidator(); err != nil {
			return err
		}
	}

	serviceExisted, err := controller.Stop()
	if err != nil {
		if serviceExisted {
			if restartErr := controller.Start(installDir, true); restartErr != nil {
				return fmt.Errorf("stop existing sidecar service: %v; restore service after stop failure: %w", err, restartErr)
			}
		}
		return fmt.Errorf("stop existing sidecar service: %w", err)
	}
	if cfg.RemoteLeaseValidator != nil {
		leaseErr := cfg.RemoteLeaseValidator()
		if leaseErr == nil {
			leaseErr = validateRemoteExecutionDeadline(cfg)
		}
		if leaseErr != nil {
			if serviceExisted {
				if restartErr := controller.Start(installDir, true); restartErr != nil {
					return fmt.Errorf("%v; restart existing service after lease expiry: %w", leaseErr, restartErr)
				}
			}
			return leaseErr
		}
	}
	installExisted := false
	if _, err := os.Stat(installDir); err == nil {
		installExisted = true
		pendingMarker := filepath.Join(installDir, windowsActivationPendingMarker)
		if err := os.WriteFile(pendingMarker, []byte("pending\n"), 0600); err != nil {
			markerErr := err
			if serviceExisted {
				if restartErr := controller.Start(installDir, true); restartErr != nil {
					return fmt.Errorf("write activation marker: %v; restart previous service: %w", markerErr, restartErr)
				}
			}
			return fmt.Errorf("write activation marker: %w", markerErr)
		}
		if err := os.Rename(installDir, backupDir); err != nil {
			backupErr := err
			removeMarkerErr := os.Remove(pendingMarker)
			if serviceExisted {
				if restartErr := controller.Start(installDir, true); restartErr != nil {
					return fmt.Errorf("backup existing installation: %v; restart previous service: %w", backupErr, restartErr)
				}
			}
			if removeMarkerErr != nil && !os.IsNotExist(removeMarkerErr) {
				return fmt.Errorf("backup existing installation: %v; remove activation marker: %w", backupErr, removeMarkerErr)
			}
			return fmt.Errorf("backup existing installation: %w", backupErr)
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	if err := os.Rename(stagingDir, installDir); err != nil {
		activationErr := err
		if restoreErr := restorePreviousWindowsInstallation(controller, installDir, backupDir, installExisted, serviceExisted, nil); restoreErr != nil {
			return fmt.Errorf("activate staged installation: %v; rollback: %w", activationErr, restoreErr)
		}
		return fmt.Errorf("activate staged installation: %w", activationErr)
	}
	movedRuntimeDirectories := []string{}
	if installExisted {
		movedRuntimeDirectories, err = moveWindowsRuntimeData(backupDir, installDir)
		if err != nil {
			preserveErr := err
			if restoreErr := restorePreviousWindowsInstallation(controller, installDir, backupDir, installExisted, serviceExisted, movedRuntimeDirectories); restoreErr != nil {
				return fmt.Errorf("preserve Windows runtime data: %v; rollback: %w", preserveErr, restoreErr)
			}
			return fmt.Errorf("preserve Windows runtime data: %w", preserveErr)
		}
	}

	if err := controller.Start(installDir, serviceExisted); err != nil {
		activationErr := err
		if _, stopErr := controller.Stop(); stopErr != nil {
			if _, retryStopErr := controller.Stop(); retryStopErr != nil {
				return fmt.Errorf(
					"activate new service: %v; stop failed service before rollback: %v; retry stop: %w; previous installation retained at %s for recovery",
					activationErr,
					stopErr,
					retryStopErr,
					backupDir,
				)
			}
		}
		if !serviceExisted {
			if removeServiceErr := controller.Remove(); removeServiceErr != nil {
				return fmt.Errorf("activate new service: %v; remove failed service before rollback: %w", activationErr, removeServiceErr)
			}
		}
		if restoreErr := restorePreviousWindowsInstallation(controller, installDir, backupDir, installExisted, serviceExisted, movedRuntimeDirectories); restoreErr != nil {
			return fmt.Errorf("activate new service: %v; rollback: %w", activationErr, restoreErr)
		}
		return fmt.Errorf("activate new service: %w", activationErr)
	}

	if installExisted {
		pendingMarker := filepath.Join(backupDir, windowsActivationPendingMarker)
		committedMarker := filepath.Join(backupDir, windowsActivationCommittedMarker)
		if err := os.Rename(pendingMarker, committedMarker); err != nil {
			commitErr := err
			if _, stopErr := controller.Stop(); stopErr != nil {
				return fmt.Errorf("commit Windows activation: %v; stop new service before rollback: %w", commitErr, stopErr)
			}
			if restoreErr := restorePreviousWindowsInstallation(controller, installDir, backupDir, true, serviceExisted, movedRuntimeDirectories); restoreErr != nil {
				return fmt.Errorf("commit Windows activation: %v; rollback: %w", commitErr, restoreErr)
			}
			return fmt.Errorf("commit Windows activation: %w", commitErr)
		}
		cleanupActivatedWindowsBackup(backupDir)
	}
	return nil
}

func registerService(installDir string) error {
	exePath := filepath.Join(installDir, "collector-sidecar.exe")
	cfgPath := filepath.Join(installDir, "sidecar.yml")

	if _, err := os.Stat(exePath); os.IsNotExist(err) {
		return fmt.Errorf("collector-sidecar.exe not found at %s", exePath)
	}

	if _, err := os.Stat(cfgPath); os.IsNotExist(err) {
		return fmt.Errorf("sidecar.yml not found at %s", cfgPath)
	}

	binPath := fmt.Sprintf(`"%s" -c "%s"`, exePath, cfgPath)

	out, err := exec.Command("sc.exe", "create", "sidecar",
		"binPath=", binPath,
		"start=", "auto",
		"DisplayName=", "Collector Sidecar",
	).CombinedOutput()
	if err != nil {
		return fmt.Errorf("sc create failed: %s\n\nTroubleshooting:\n  1. Run as Administrator\n  2. Check: sc.exe query sidecar\n  3. Manual delete: sc.exe delete sidecar", strings.TrimSpace(string(out)))
	}

	exec.Command("sc.exe", "description", "sidecar", "Collector Sidecar - Log and metric collector agent").Run()

	return startWindowsService(installDir)
}

func startWindowsService(installDir string) error {
	exePath := filepath.Join(installDir, "collector-sidecar.exe")
	cfgPath := filepath.Join(installDir, "sidecar.yml")
	logPath := filepath.Join(installDir, "logs")

	out, err := exec.Command("sc.exe", "start", "sidecar").CombinedOutput()
	if err != nil {
		return serviceStartError(string(out), exePath, cfgPath, logPath)
	}

	for i := 0; i < windowsServiceTransitionAttempts; i++ {
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

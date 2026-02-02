package main

import (
	"archive/zip"
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type Config struct {
	ServerURL   string `json:"server_url"`
	APIToken    string `json:"api_token"`
	NodeID      string `json:"node_id"`
	NodeName    string `json:"node_name"`
	ZoneID      string `json:"zone_id"`
	GroupID     string `json:"group_id"`
	DownloadURL string `json:"download_url"`
	InstallDir  string `json:"install_dir"`
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
	cfg, err := fetchConfig(client, *configURL)
	if err != nil {
		fatal("Fetch failed: %v", err)
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
	if err := prepareDirs(cfg.InstallDir); err != nil {
		fatal("Failed: %v", err)
	}

	if cfg.DownloadURL != "" {
		log("[3/6] Downloading package...")
		zipPath, err := download(client, cfg.DownloadURL)
		if err != nil {
			fatal("Download failed: %v", err)
		}

		log("[4/6] Extracting files...")
		n, err := extract(zipPath, cfg.InstallDir)
		if err != nil {
			fatal("Extract failed: %v", err)
		}
		os.Remove(zipPath)
		log("      Extracted %d files", n)
	} else {
		log("[3/6] No download URL, skipping...")
		log("[4/6] No extraction needed...")
	}

	log("[5/6] Writing configuration...")
	if err := writeConfig(cfg); err != nil {
		fatal("Config write failed: %v", err)
	}

	log("[6/6] Registering service...")
	if err := registerService(cfg.InstallDir); err != nil {
		fatal("Service registration failed: %v", err)
	}

	log("")
	log("Installation complete!")
}

func log(format string, args ...interface{}) {
	fmt.Printf(format+"\n", args...)
	os.Stdout.Sync()
}

func fatal(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, "ERROR: "+format+"\n", args...)
	os.Exit(1)
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
	return &cfg, nil
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
	if cfg.DownloadURL != "" {
		fmt.Printf("Download URL: %s\r\n", cfg.DownloadURL)
	}
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
}

func (pw *progressWriter) Write(p []byte) (int, error) {
	n := len(p)
	pw.downloaded += int64(n)
	if pw.total > 0 {
		pct := int(pw.downloaded * 100 / pw.total)
		if pct/10 > pw.lastPct/10 {
			log("      %s... %d%%", pw.desc, pct)
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
		pw := &progressWriter{total: resp.ContentLength, desc: "Downloading"}
		_, err = io.Copy(f, io.TeeReader(resp.Body, pw))
		if pw.lastPct < 100 {
			log("      Downloading... 100%%")
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
			if pct/10 > lastPct/10 {
				log("      Extracting... %d%%", pct)
				lastPct = pct
			}
		}
	}

	if totalFiles > 0 && lastPct < 100 {
		log("      Extracting... 100%%")
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
tags: ["zone:%s", "group:%s"]
collector_binaries_accesslist:
  - "%s\\bin\\*"
`,
		cfg.ServerURL,
		cfg.APIToken,
		cfg.NodeID,
		cfg.NodeName,
		installDir, installDir, installDir,
		cfg.ZoneID, cfg.GroupID,
		installDir,
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

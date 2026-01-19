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

	_, err = io.Copy(f, resp.Body)
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

	count := 0
	destClean := filepath.Clean(dest) + string(os.PathSeparator)

	for _, f := range r.File {
		target := filepath.Join(dest, f.Name)
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
	}
	return count, nil
}

func writeConfig(cfg *Config) error {
	content := fmt.Sprintf(`server_url: "%s"
server_api_token: "%s"
node_id: "%s"
node_name: "%s"
update_interval: 10
tls_skip_verify: false
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
		cfg.InstallDir, cfg.InstallDir, cfg.InstallDir,
		cfg.ZoneID, cfg.GroupID,
		cfg.InstallDir,
	)

	return os.WriteFile(filepath.Join(cfg.InstallDir, "sidecar.yml"), []byte(content), 0644)
}

func registerService(installDir string) error {
	exePath := filepath.Join(installDir, "collector-sidecar.exe")
	cfgPath := filepath.Join(installDir, "sidecar.yml")

	// Verify exe exists
	if _, err := os.Stat(exePath); os.IsNotExist(err) {
		return fmt.Errorf("collector-sidecar.exe not found at %s", exePath)
	}

	// Verify config exists
	if _, err := os.Stat(cfgPath); os.IsNotExist(err) {
		return fmt.Errorf("sidecar.yml not found at %s", cfgPath)
	}

	binPath := fmt.Sprintf(`"%s" -c "%s"`, exePath, cfgPath)

	// Stop existing service (ignore errors)
	exec.Command("sc.exe", "stop", "sidecar").Run()
	time.Sleep(time.Second)
	exec.Command("sc.exe", "delete", "sidecar").Run()
	time.Sleep(time.Second)

	// Create service
	out, err := exec.Command("sc.exe", "create", "sidecar",
		"binPath=", binPath,
		"start=", "auto",
		"DisplayName=", "Collector Sidecar",
	).CombinedOutput()
	if err != nil {
		return fmt.Errorf("sc create failed: %s", strings.TrimSpace(string(out)))
	}

	// Set description (ignore error)
	exec.Command("sc.exe", "description", "sidecar", "Collector Sidecar - Log and metric collector agent").Run()

	// Start service
	out, err = exec.Command("sc.exe", "start", "sidecar").CombinedOutput()
	if err != nil {
		return fmt.Errorf("sc start failed: %s", strings.TrimSpace(string(out)))
	}

	// Wait for service to be running
	for i := 0; i < 10; i++ {
		time.Sleep(time.Second)
		out, _ := exec.Command("sc.exe", "query", "sidecar").Output()
		if strings.Contains(string(out), "RUNNING") {
			log("      Service is running")
			return nil
		}
	}

	// Check final state
	out, _ = exec.Command("sc.exe", "query", "sidecar").Output()
	if strings.Contains(string(out), "STOPPED") {
		return fmt.Errorf("service failed to start (STOPPED)")
	}
	if strings.Contains(string(out), "FAILED") {
		return fmt.Errorf("service failed to start (FAILED)")
	}

	return fmt.Errorf("service did not reach RUNNING state within 10 seconds")
}

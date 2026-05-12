package main

import (
	"crypto/tls"
	"crypto/x509"
	"flag"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
	"gopkg.in/yaml.v3"

	"nats-executor/local"
	"nats-executor/logger"
	"nats-executor/ssh"
)

const version = "3.0.0"

var (
	subscribeLocalExecutor    = local.SubscribeLocalExecutor
	subscribeDownloadToLocal  = local.SubscribeDownloadToLocal
	subscribeUnzipToLocal     = local.SubscribeUnzipToLocal
	subscribeHealthCheck      = local.SubscribeHealthCheck
	subscribeSSHExecutor      = ssh.SubscribeSSHExecutor
	subscribeDownloadToRemote = ssh.SubscribeDownloadToRemote
	subscribeUploadToRemote   = ssh.SubscribeUploadToRemote
	connectNATS               = nats.Connect
	closeNATSConn             = func(nc *nats.Conn) { nc.Close() }
	loadConfigFn              = loadConfig
	buildNATSOptionsFn        = buildNATSOptions
	registerSubscriptionsFn   = registerSubscriptions
)

type Config struct {
	NATSUrls        string `yaml:"nats_urls"`
	NATSInstanceID  string `yaml:"nats_instanceId"`
	NatsConnTimeout int    `yaml:"nats_conn_timeout"`

	// TLS 配置（都先用 string，后面自己解析）
	TLSEnabled    string `yaml:"tls_enabled"`
	TLSHostname   string `yaml:"tls_hostname"`
	TLSCAFile     string `yaml:"tls_ca_file"`
	TLSCertFile   string `yaml:"tls_cert_file"`
	TLSKeyFile    string `yaml:"tls_key_file"`
	TLSSkipVerify string `yaml:"tls_skip_verify"`
}

func loadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}
	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}

	// 渲染所有 string 配置中的环境变量占位符，避免 TLS/实例 ID 等字段静默失效。
	cfg.NATSUrls = renderEnvVars(cfg.NATSUrls)
	cfg.NATSInstanceID = renderEnvVars(cfg.NATSInstanceID)
	cfg.TLSEnabled = renderEnvVars(cfg.TLSEnabled)
	cfg.TLSHostname = renderEnvVars(cfg.TLSHostname)
	cfg.TLSCAFile = renderEnvVars(cfg.TLSCAFile)
	cfg.TLSCertFile = renderEnvVars(cfg.TLSCertFile)
	cfg.TLSKeyFile = renderEnvVars(cfg.TLSKeyFile)
	cfg.TLSSkipVerify = renderEnvVars(cfg.TLSSkipVerify)

	return &cfg, nil
}

// renderEnvVars 渲染字符串中的环境变量占位符
// 支持 ${VAR_NAME} 和 $VAR_NAME 两种格式
func renderEnvVars(s string) string {
	if s == "" {
		return s
	}

	re := regexp.MustCompile(`\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)`)
	result := re.ReplaceAllStringFunc(s, func(match string) string {
		var varName string
		if strings.HasPrefix(match, "${") {
			varName = match[2 : len(match)-1]
		} else {
			varName = match[1:]
		}
		if envValue := os.Getenv(varName); envValue != "" {
			return envValue
		}
		// 如果环境变量不存在，保持原样
		logger.Warnf("environment variable %s not found, keeping placeholder", varName)
		return match
	})

	return result
}

// 判断是否是占位符（${xxx} 或 {{xxx}）
func isPlaceholder(v string) bool {
	return strings.HasPrefix(v, "${") || strings.HasPrefix(v, "{{")
}

// 解析 bool 类型
func parseBool(s string) bool {
	if s == "" || isPlaceholder(s) {
		return false
	}
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "true", "1", "yes", "on":
		return true
	default:
		return false
	}
}

// 解析 string 类型（占位符 -> ""）
func parseString(s string) string {
	if isPlaceholder(s) {
		return ""
	}
	return strings.TrimSpace(s)
}

func parseCLIArgs(args []string) (configPath string, showVersion bool, err error) {
	if len(args) > 0 && args[0] == "version" {
		return "", true, nil
	}

	fs := flag.NewFlagSet("nats-executor", flag.ContinueOnError)
	fs.SetOutput(io.Discard)

	config := fs.String("config", "", "Path to the config file (YAML format)")
	if err := fs.Parse(args); err != nil {
		return "", false, err
	}

	return *config, false, nil
}

func buildTLSConfig(cfg *Config) (*tls.Config, error) {
	tlsEnabled := parseBool(cfg.TLSEnabled)
	if !tlsEnabled {
		return nil, nil
	}

	tlsConfig := &tls.Config{
		InsecureSkipVerify: parseBool(cfg.TLSSkipVerify),
	}

	if tlsHostname := parseString(cfg.TLSHostname); tlsHostname != "" {
		tlsConfig.ServerName = tlsHostname
	}

	tlsCertFile := parseString(cfg.TLSCertFile)
	tlsKeyFile := parseString(cfg.TLSKeyFile)
	if tlsCertFile != "" && tlsKeyFile != "" {
		cert, err := tls.LoadX509KeyPair(tlsCertFile, tlsKeyFile)
		if err != nil {
			return nil, fmt.Errorf("failed to load client certificate: %w", err)
		}
		tlsConfig.Certificates = []tls.Certificate{cert}
	}

	if tlsCAFile := parseString(cfg.TLSCAFile); tlsCAFile != "" {
		caCert, err := os.ReadFile(tlsCAFile)
		if err != nil {
			return nil, fmt.Errorf("failed to read CA certificate file: %w", err)
		}
		caCertPool := x509.NewCertPool()
		if !caCertPool.AppendCertsFromPEM(caCert) {
			return nil, fmt.Errorf("failed to append CA certificate")
		}
		tlsConfig.RootCAs = caCertPool
	}

	return tlsConfig, nil
}

func buildNATSOptions(cfg *Config) ([]nats.Option, error) {
	opts := []nats.Option{
		nats.Name("nats-executor"),
		nats.Compression(true),
		nats.Timeout(time.Duration(cfg.NatsConnTimeout) * time.Second),
	}

	tlsConfig, err := buildTLSConfig(cfg)
	if err != nil {
		return nil, err
	}
	if tlsConfig != nil {
		opts = append(opts, nats.Secure(tlsConfig))
	}

	return opts, nil
}

func registerSubscriptions(nc *nats.Conn, instanceID string) {
	subscribeLocalExecutor(nc, &instanceID)
	subscribeDownloadToLocal(nc, &instanceID)
	subscribeUnzipToLocal(nc, &instanceID)
	subscribeHealthCheck(nc, &instanceID)

	subscribeSSHExecutor(nc, &instanceID)
	subscribeDownloadToRemote(nc, &instanceID)
	subscribeUploadToRemote(nc, &instanceID)
}

func run(args []string, stdout io.Writer, wait func()) error {
	configPath, showVersion, err := parseCLIArgs(args)
	if err != nil {
		return fmt.Errorf("failed to parse arguments: %w", err)
	}
	if showVersion {
		_, err := fmt.Fprintln(stdout, version)
		return err
	}

	if configPath == "" {
		return fmt.Errorf("please specify the config file path using --config")
	}

	cfg, err := loadConfigFn(configPath)
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	opts, err := buildNATSOptionsFn(cfg)
	if err != nil {
		return fmt.Errorf("failed to build NATS options: %w", err)
	}
	if parseBool(cfg.TLSEnabled) {
		logger.Info("TLS enabled for NATS connection")
	}

	nc, err := connectNATS(cfg.NATSUrls, opts...)
	if err != nil {
		return fmt.Errorf("failed to connect to NATS server: %w", err)
	}
	defer func() {
		if nc != nil {
			closeNATSConn(nc)
		}
	}()
	logger.Info("Connected to NATS server")

	registerSubscriptionsFn(nc, cfg.NATSInstanceID)

	logger.Infof("Waiting for messages... (log level: %s)", logger.GetLevel())
	wait()
	return nil
}

func main() {
	if err := run(os.Args[1:], os.Stdout, func() {
		select {}
	}); err != nil {
		logger.Fatal(err.Error())
	}
}

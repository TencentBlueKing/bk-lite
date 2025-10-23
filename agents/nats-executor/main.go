package main

import (
	"crypto/tls"
	"crypto/x509"
	"flag"
	"fmt"
	"log"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
	"gopkg.in/yaml.v3"

	"nats-executor/local"
	"nats-executor/ssh"
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

	// 渲染环境变量
	cfg.NATSUrls = renderEnvVars(cfg.NATSUrls)

	return &cfg, nil
}

// renderEnvVars 渲染字符串中的环境变量占位符
// 支持 ${VAR_NAME} 和 $VAR_NAME 两种格式
func renderEnvVars(s string) string {
	if s == "" {
		return s
	}

	// 匹配 ${VAR_NAME} 格式
	re := regexp.MustCompile(`\$\{([A-Za-z_][A-Za-z0-9_]*)\}`)
	result := re.ReplaceAllStringFunc(s, func(match string) string {
		// 提取变量名（去掉 ${ 和 }）
		varName := match[2 : len(match)-1]
		if envValue := os.Getenv(varName); envValue != "" {
			return envValue
		}
		// 如果环境变量不存在，保持原样
		log.Printf("Warning: environment variable %s not found, keeping placeholder", varName)
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

func main() {
	configPath := flag.String("config", "", "Path to the config file (YAML format)")
	flag.Parse()

	if *configPath == "" {
		log.Fatal("Please specify the config file path using --config")
	}

	cfg, err := loadConfig(*configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	//log.Printf("Connecting to NATS server at %s", cfg.NATSUrls)
	opts := []nats.Option{
		nats.Name("nats-executor"),
		nats.Compression(true),
		nats.Timeout(time.Duration(cfg.NatsConnTimeout) * time.Second),
	}

	// 解析 TLS 参数
	tlsEnabled := parseBool(cfg.TLSEnabled)
	tlsSkipVerify := parseBool(cfg.TLSSkipVerify)
	tlsHostname := parseString(cfg.TLSHostname)
	tlsCAFile := parseString(cfg.TLSCAFile)
	tlsCertFile := parseString(cfg.TLSCertFile)
	tlsKeyFile := parseString(cfg.TLSKeyFile)

	// 添加 TLS 配置
	if tlsEnabled {
		tlsConfig := &tls.Config{
			InsecureSkipVerify: tlsSkipVerify,
		}

		if tlsHostname != "" {
			tlsConfig.ServerName = tlsHostname
		}

		if tlsCertFile != "" && tlsKeyFile != "" {
			cert, err := tls.LoadX509KeyPair(tlsCertFile, tlsKeyFile)
			if err != nil {
				log.Fatalf("Failed to load client certificate: %v", err)
			}
			tlsConfig.Certificates = []tls.Certificate{cert}
		}

		if tlsCAFile != "" {
			caCert, err := os.ReadFile(tlsCAFile)
			if err != nil {
				log.Fatalf("Failed to read CA certificate file: %v", err)
			}
			caCertPool := x509.NewCertPool()
			if !caCertPool.AppendCertsFromPEM(caCert) {
				log.Fatalf("Failed to append CA certificate")
			}
			tlsConfig.RootCAs = caCertPool
		}

		opts = append(opts, nats.Secure(tlsConfig))
		log.Println("TLS enabled for NATS connection")
	}

	nc, err := nats.Connect(cfg.NATSUrls, opts...)
	if err != nil {
		log.Fatalf("Failed to connect to NATS server: %v", err)
	}
	defer nc.Close()
	log.Println("Connected to NATS server")

	// 注册各类订阅
	local.SubscribeLocalExecutor(nc, &cfg.NATSInstanceID)
	local.SubscribeDownloadToLocal(nc, &cfg.NATSInstanceID)
	local.SubscribeUnzipToLocal(nc, &cfg.NATSInstanceID)

	ssh.SubscribeSSHExecutor(nc, &cfg.NATSInstanceID)
	ssh.SubscribeDownloadToRemote(nc, &cfg.NATSInstanceID)
	ssh.SubscribeUploadToRemote(nc, &cfg.NATSInstanceID)

	log.Println("Waiting for messages...")
	select {}
}

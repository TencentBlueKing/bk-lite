package rumreplayexporter

import (
	"errors"
	"fmt"
	"net/url"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/config/configopaque"
	"go.opentelemetry.io/collector/config/configoptional"
	"go.opentelemetry.io/collector/config/configretry"
	"go.opentelemetry.io/collector/exporter/exporterhelper"
)

const (
	defaultReplayBucket      = "rum-replay"
	defaultMinIOEndpoint     = "minio:9000"
	defaultRedisURL          = "redis://rum-replay-exporter:rum-replay-exporter-dev-secret-000003@rum-redis:6379"
	exporterOperationTimeout = 15 * time.Second
	leaseReleaseTimeout      = 2 * time.Second
	pendingCleanupTimeout    = 2 * time.Second
	sequenceLeaseTTL         = 60 * time.Second
	sequenceStateTTL         = 17 * 24 * time.Hour
	maxReplayQueueAge        = 14 * 24 * time.Hour
)

var (
	bucketPattern      = regexp.MustCompile(`^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$`)
	redisSecretPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{32,256}$`)
)

// Config keeps the queue file-backed while Redis sequence leases linearize
// exporters per (session, recording, sequence) slot.
type Config struct {
	exporterhelper.TimeoutConfig `mapstructure:",squash"`
	configretry.BackOffConfig    `mapstructure:"retry_on_failure"`
	QueueSettings                configoptional.Optional[exporterhelper.QueueBatchConfig] `mapstructure:"sending_queue"`
	MaxQueueAge                  time.Duration                                            `mapstructure:"max_queue_age"`

	MinIOEndpoint  string              `mapstructure:"minio_endpoint"`
	MinIOAccessKey string              `mapstructure:"minio_access_key"`
	MinIOSecretKey configopaque.String `mapstructure:"minio_secret_key"`
	MinIOSecure    bool                `mapstructure:"minio_secure"`
	MinIOBucket    string              `mapstructure:"minio_bucket"`

	RedisURL          string `mapstructure:"redis_url"`
	RedisPasswordFile string `mapstructure:"redis_password_file"`
}

func defaultConfig() *Config {
	queue := exporterhelper.NewDefaultQueueConfig()
	queue.NumConsumers = 4
	queue.Batch = configoptional.None[exporterhelper.BatchConfig]()
	storageID := component.MustNewIDWithName("file_storage", "rum_replay")
	queue.StorageID = &storageID
	return &Config{
		TimeoutConfig: exporterhelper.TimeoutConfig{Timeout: exporterOperationTimeout},
		BackOffConfig: configretry.NewDefaultBackOffConfig(),
		QueueSettings: configoptional.Some(queue),
		MaxQueueAge:   maxReplayQueueAge,
		MinIOEndpoint: defaultMinIOEndpoint,
		MinIOBucket:   defaultReplayBucket,
		RedisURL:      defaultRedisURL,
	}
}

func (cfg *Config) Validate() error {
	var result error
	if err := cfg.TimeoutConfig.Validate(); err != nil {
		result = errors.Join(result, fmt.Errorf("invalid timeout: %w", err))
	}
	if cfg.TimeoutConfig.Timeout <= 0 || cfg.TimeoutConfig.Timeout > exporterOperationTimeout {
		result = errors.Join(result, fmt.Errorf("timeout must be positive and at most %s", exporterOperationTimeout))
	}
	if err := cfg.BackOffConfig.Validate(); err != nil {
		result = errors.Join(result, fmt.Errorf("invalid retry_on_failure: %w", err))
	}
	if cfg.MaxQueueAge <= 0 || cfg.MaxQueueAge > maxReplayQueueAge {
		result = errors.Join(result, fmt.Errorf("max_queue_age must be positive and at most %s", maxReplayQueueAge))
	}
	if _, _, err := parseMinIOEndpoint(cfg.MinIOEndpoint, cfg.MinIOSecure); err != nil {
		result = errors.Join(result, err)
	}
	if cfg.MinIOAccessKey == "" || cfg.MinIOSecretKey == "" {
		result = errors.Join(result, errors.New("MinIO credentials must not be empty"))
	}
	if !bucketPattern.MatchString(cfg.MinIOBucket) {
		result = errors.Join(result, errors.New("minio_bucket is invalid"))
	}
	redisURL, redisErr := url.Parse(strings.TrimSpace(cfg.RedisURL))
	if redisErr != nil || redisURL.Host == "" || (redisURL.Scheme != "redis" && redisURL.Scheme != "rediss") {
		result = errors.Join(result, errors.New("redis_url must be a redis:// or rediss:// URL"))
	} else {
		if redisURL.User == nil || redisURL.User.Username() != "rum-replay-exporter" {
			result = errors.Join(result, errors.New("redis_url must use the dedicated rum-replay-exporter ACL user"))
		}
		if redisURL.RawQuery != "" || redisURL.Fragment != "" {
			result = errors.Join(result, errors.New("redis_url must not contain query or fragment data"))
		}
		password, hasPassword := "", false
		if redisURL.User != nil {
			password, hasPassword = redisURL.User.Password()
		}
		passwordFile := strings.TrimSpace(cfg.RedisPasswordFile)
		if passwordFile != "" {
			if hasPassword {
				result = errors.Join(result, errors.New("redis_url must not embed a password when redis_password_file is set"))
			}
			if !filepath.IsAbs(passwordFile) || filepath.Clean(passwordFile) != passwordFile {
				result = errors.Join(result, errors.New("redis_password_file must be a clean absolute path"))
			}
		} else if !hasPassword || !redisSecretPattern.MatchString(password) {
			result = errors.Join(result, errors.New("development redis_url must include a 32-256 character URL-safe password"))
		}
	}
	if !cfg.QueueSettings.HasValue() {
		result = errors.Join(result, errors.New("sending_queue must be enabled"))
	} else {
		queue := cfg.QueueSettings.Get()
		if err := queue.Validate(); err != nil {
			result = errors.Join(result, fmt.Errorf("invalid sending_queue: %w", err))
		}
		if queue.NumConsumers < 1 {
			result = errors.Join(result, errors.New("sending_queue must have at least one consumer"))
		}
		if queue.StorageID == nil {
			result = errors.Join(result, errors.New("sending_queue requires persistent storage"))
		}
	}
	return result
}

func parseMinIOEndpoint(raw string, configuredSecure bool) (string, bool, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "", false, errors.New("minio_endpoint must not be empty")
	}
	if !strings.Contains(raw, "://") {
		parsed, err := url.Parse("//" + raw)
		if err != nil || parsed.Host == "" || parsed.Path != "" || parsed.RawQuery != "" || parsed.Fragment != "" {
			return "", false, errors.New("minio_endpoint must be a valid host:port")
		}
		return raw, configuredSecure, nil
	}
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Host == "" || (parsed.Path != "" && parsed.Path != "/") || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", false, errors.New("minio_endpoint must be a host:port or http(s) URL without a path")
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return "", false, errors.New("minio_endpoint URL must use http or https")
	}
	secure := parsed.Scheme == "https"
	if configuredSecure && !secure {
		return "", false, errors.New("minio_secure conflicts with an http endpoint")
	}
	return parsed.Host, secure, nil
}

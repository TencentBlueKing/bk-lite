package rumreplayreceiver

import (
	"errors"
	"strings"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/ingress"
)

const (
	defaultEndpoint             = "0.0.0.0:4320"
	defaultMaxCompressedBytes   = int64(1 << 20)
	defaultMaxDecompressedBytes = int64(4 << 20)
	defaultMaxCompressionRatio  = 100.0
	defaultMaxEvents            = 10000
	defaultMaxEventBytes        = 4 << 20
	defaultMaxJSONDepth         = 64
	defaultTenantID             = "core"
)

// Config duplicates all public-edge limits at the collector boundary.
type Config struct {
	Endpoint             string        `mapstructure:"endpoint"`
	TenantID             string        `mapstructure:"tenant_id"`
	IdentityHMACSecret   string        `mapstructure:"identity_hmac_secret"`
	IdentityHMACVersion  string        `mapstructure:"identity_hmac_version"`
	IdentityHMACPrevious string        `mapstructure:"identity_hmac_previous_secret"`
	IdentityHMACPrevVer  string        `mapstructure:"identity_hmac_previous_version"`
	AdmissionRedisURL    string        `mapstructure:"admission_redis_url"`
	AdmissionRedisPass   string        `mapstructure:"admission_redis_password_file"`
	MaxCompressedBytes   int64         `mapstructure:"max_compressed_bytes"`
	MaxDecompressedBytes int64         `mapstructure:"max_decompressed_bytes"`
	MaxCompressionRatio  float64       `mapstructure:"max_compression_ratio"`
	MaxEvents            int           `mapstructure:"max_events"`
	MaxEventBytes        int           `mapstructure:"max_event_bytes"`
	MaxJSONDepth         int           `mapstructure:"max_json_depth"`
	ReadHeaderTimeout    time.Duration `mapstructure:"read_header_timeout"`
	ReadTimeout          time.Duration `mapstructure:"read_timeout"`
	IdleTimeout          time.Duration `mapstructure:"idle_timeout"`
}

func defaultConfig() *Config {
	return &Config{
		Endpoint:             defaultEndpoint,
		TenantID:             defaultTenantID,
		IdentityHMACVersion:  "v1",
		MaxCompressedBytes:   defaultMaxCompressedBytes,
		MaxDecompressedBytes: defaultMaxDecompressedBytes,
		MaxCompressionRatio:  defaultMaxCompressionRatio,
		MaxEvents:            defaultMaxEvents,
		MaxEventBytes:        defaultMaxEventBytes,
		MaxJSONDepth:         defaultMaxJSONDepth,
		ReadHeaderTimeout:    5 * time.Second,
		ReadTimeout:          15 * time.Second,
		IdleTimeout:          30 * time.Second,
	}
}

func (cfg *Config) Validate() error {
	if cfg.Endpoint == "" {
		return errors.New("endpoint must not be empty")
	}
	if cfg.TenantID == "" || !replayIDPattern.MatchString(cfg.TenantID) {
		return errors.New("tenant_id must be a non-empty stable identifier")
	}
	if len(cfg.IdentityHMACSecret) < 32 {
		return errors.New("identity_hmac_secret must contain at least 32 bytes")
	}
	if !replayIDPattern.MatchString(cfg.IdentityHMACVersion) {
		return errors.New("identity_hmac_version must be a stable generation identifier")
	}
	if cfg.IdentityHMACPrevious != "" && len(cfg.IdentityHMACPrevious) < 32 {
		return errors.New("identity_hmac_previous_secret must be empty or contain at least 32 bytes")
	}
	if (cfg.IdentityHMACPrevious == "") != (cfg.IdentityHMACPrevVer == "") {
		return errors.New("identity_hmac_previous_secret and identity_hmac_previous_version must be configured together")
	}
	if cfg.IdentityHMACPrevVer != "" &&
		(!replayIDPattern.MatchString(cfg.IdentityHMACPrevVer) || cfg.IdentityHMACPrevVer == cfg.IdentityHMACVersion) {
		return errors.New("identity_hmac_previous_version must be a distinct stable generation identifier")
	}
	if strings.TrimSpace(cfg.AdmissionRedisURL) == "" {
		return errors.New("admission_redis_url is required")
	}
	if err := ingress.ValidateConfig(ingress.Config{
		RedisURL:          cfg.AdmissionRedisURL,
		RedisPasswordFile: cfg.AdmissionRedisPass,
	}); err != nil {
		return err
	}
	if cfg.MaxCompressedBytes <= 0 || cfg.MaxDecompressedBytes <= 0 {
		return errors.New("body limits must be positive")
	}
	if cfg.MaxDecompressedBytes < cfg.MaxCompressedBytes {
		return errors.New("decompressed limit must not be smaller than compressed limit")
	}
	if cfg.MaxCompressionRatio <= 1 {
		return errors.New("compression ratio limit must be greater than one")
	}
	if cfg.MaxEvents <= 0 || cfg.MaxEventBytes <= 0 || cfg.MaxJSONDepth <= 0 {
		return errors.New("event and JSON limits must be positive")
	}
	if cfg.ReadHeaderTimeout <= 0 || cfg.ReadTimeout <= 0 || cfg.IdleTimeout <= 0 {
		return errors.New("HTTP timeouts must be positive")
	}
	return nil
}

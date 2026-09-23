package farorumreceiver

import (
	"errors"
	"strings"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/ingress"
)

const (
	defaultEndpoint             = "0.0.0.0:4319"
	defaultMaxCompressedBytes   = int64(1 << 20)
	defaultMaxDecompressedBytes = int64(4 << 20)
	defaultMaxCompressionRatio  = 100.0
	defaultMaxItems             = 1000
	defaultMaxJSONDepth         = 32
	defaultMaxContextEntries    = 32
	defaultMaxContextKeyBytes   = 128
	defaultMaxContextValueBytes = 1024
	defaultTenantID             = "core"
)

// Config controls the platform-owned Faro ingress. Limits are duplicated at
// the receiver boundary so direct development traffic cannot bypass them.
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
	MaxItems             int           `mapstructure:"max_items"`
	MaxJSONDepth         int           `mapstructure:"max_json_depth"`
	MaxContextEntries    int           `mapstructure:"max_context_entries"`
	MaxContextKeyBytes   int           `mapstructure:"max_context_key_bytes"`
	MaxContextValueBytes int           `mapstructure:"max_context_value_bytes"`
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
		MaxItems:             defaultMaxItems,
		MaxJSONDepth:         defaultMaxJSONDepth,
		MaxContextEntries:    defaultMaxContextEntries,
		MaxContextKeyBytes:   defaultMaxContextKeyBytes,
		MaxContextValueBytes: defaultMaxContextValueBytes,
		ReadHeaderTimeout:    5 * time.Second,
		ReadTimeout:          15 * time.Second,
		IdleTimeout:          30 * time.Second,
	}
}

func (cfg *Config) Validate() error {
	if cfg.Endpoint == "" {
		return errors.New("endpoint must not be empty")
	}
	if cfg.TenantID == "" || !stableIDPattern.MatchString(cfg.TenantID) {
		return errors.New("tenant_id must be a non-empty stable identifier")
	}
	if len(cfg.IdentityHMACSecret) < 32 {
		return errors.New("identity_hmac_secret must contain at least 32 bytes")
	}
	if !stableIDPattern.MatchString(cfg.IdentityHMACVersion) {
		return errors.New("identity_hmac_version must be a stable generation identifier")
	}
	if cfg.IdentityHMACPrevious != "" && len(cfg.IdentityHMACPrevious) < 32 {
		return errors.New("identity_hmac_previous_secret must be empty or contain at least 32 bytes")
	}
	if (cfg.IdentityHMACPrevious == "") != (cfg.IdentityHMACPrevVer == "") {
		return errors.New("identity_hmac_previous_secret and identity_hmac_previous_version must be configured together")
	}
	if cfg.IdentityHMACPrevVer != "" &&
		(!stableIDPattern.MatchString(cfg.IdentityHMACPrevVer) || cfg.IdentityHMACPrevVer == cfg.IdentityHMACVersion) {
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
	if cfg.MaxItems <= 0 || cfg.MaxJSONDepth <= 0 {
		return errors.New("item and JSON depth limits must be positive")
	}
	if cfg.MaxContextEntries <= 0 || cfg.MaxContextKeyBytes <= 0 || cfg.MaxContextValueBytes <= 0 {
		return errors.New("context limits must be positive")
	}
	if cfg.ReadHeaderTimeout <= 0 || cfg.ReadTimeout <= 0 || cfg.IdleTimeout <= 0 {
		return errors.New("HTTP timeouts must be positive")
	}
	return nil
}

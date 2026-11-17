package rumroutecap

import (
	"errors"
	"net/url"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

const (
	maxRoutesPerApplication = 100
	otherRoute              = "其他"
	unknownRoute            = "unknown"
	aggregateRouteAttribute = "rum.aggregate.route"
	admissionTTL            = 35 * 24 * time.Hour
	overflowCacheTTL        = time.Minute
	overflowCacheLimit      = 1024
	overflowSweepInterval   = time.Minute
	redisCircuitOpenFor     = 5 * time.Second
	failureLogWindow        = 5 * time.Second
	redisTimeout            = 200 * time.Millisecond
	failureInstrument       = "core_rum_aggregate_route_redis_failures"
)

var (
	redisSecretPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{16,256}$`)
	shardPattern       = regexp.MustCompile(`^[A-Za-z0-9_.:-]{1,64}$`)
)

// Config is the aggregate route admission processor.
// Redis credentials come from redis_url or redis_password_file, never from code.
type Config struct {
	RedisURL          string `mapstructure:"redis_url"`
	RedisPasswordFile string `mapstructure:"redis_password_file"`
	// Shard is this gateway process's fixed writer identity. Remote write copies
	// it to the external label shard, and gateway telemetry uses the same value
	// as service.instance.id.
	Shard string `mapstructure:"shard"`
}

func defaultConfig() *Config {
	return &Config{}
}

func (cfg *Config) Validate() error {
	parsed, err := url.Parse(strings.TrimSpace(cfg.RedisURL))
	if err != nil || parsed.Host == "" || (parsed.Scheme != "redis" && parsed.Scheme != "rediss") {
		return errors.New("redis_url must be a redis:// or rediss:// URL")
	}
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return errors.New("redis_url must not contain query or fragment data")
	}
	password := ""
	hasPassword := false
	if parsed.User != nil {
		password, hasPassword = parsed.User.Password()
	}
	passwordFile := strings.TrimSpace(cfg.RedisPasswordFile)
	if passwordFile != "" {
		if hasPassword {
			return errors.New("redis_url must not embed a password when redis_password_file is set")
		}
		if !filepath.IsAbs(passwordFile) || filepath.Clean(passwordFile) != passwordFile {
			return errors.New("redis_password_file must be a clean absolute path")
		}
	} else if !hasPassword || !redisSecretPattern.MatchString(password) {
		return errors.New("development redis_url must include a 16-256 character URL-safe password")
	}
	if !shardPattern.MatchString(strings.TrimSpace(cfg.Shard)) {
		return errors.New("shard must be 1-64 characters from letters, digits, and . _ : -")
	}
	return nil
}

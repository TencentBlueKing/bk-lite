package rumsessionprocessor

import (
	"errors"
	"net/url"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

const (
	defaultRedisURL      = "redis://rum-sessionizer:rum-sessionizer-dev-secret-2026-000004@rum-redis:6379"
	defaultIdleTimeout   = 15 * time.Minute
	defaultMaximumLength = 4 * time.Hour
	defaultStateTTL      = 5 * time.Hour
	defaultAOFTimeout    = 2 * time.Second
)

var redisSecretPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{32,256}$`)

type Config struct {
	RedisURL          string        `mapstructure:"redis_url"`
	RedisPasswordFile string        `mapstructure:"redis_password_file"`
	IdleTimeout       time.Duration `mapstructure:"idle_timeout"`
	MaximumLength     time.Duration `mapstructure:"maximum_length"`
	StateTTL          time.Duration `mapstructure:"state_ttl"`
	AOFTimeout        time.Duration `mapstructure:"aof_timeout"`
}

func defaultConfig() *Config {
	return &Config{
		RedisURL:      defaultRedisURL,
		IdleTimeout:   defaultIdleTimeout,
		MaximumLength: defaultMaximumLength,
		StateTTL:      defaultStateTTL,
		AOFTimeout:    defaultAOFTimeout,
	}
}

func (cfg *Config) Validate() error {
	parsed, err := url.Parse(strings.TrimSpace(cfg.RedisURL))
	if err != nil || parsed.Host == "" || (parsed.Scheme != "redis" && parsed.Scheme != "rediss") {
		return errors.New("redis_url must be a redis:// or rediss:// URL")
	}
	if parsed.User == nil || parsed.User.Username() != "rum-sessionizer" {
		return errors.New("redis_url must use the dedicated rum-sessionizer ACL user")
	}
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return errors.New("redis_url must not contain query or fragment data")
	}
	password, hasPassword := parsed.User.Password()
	passwordFile := strings.TrimSpace(cfg.RedisPasswordFile)
	if passwordFile != "" {
		if hasPassword {
			return errors.New("redis_url must not embed a password when redis_password_file is set")
		}
		if !filepath.IsAbs(passwordFile) || filepath.Clean(passwordFile) != passwordFile {
			return errors.New("redis_password_file must be a clean absolute path")
		}
	} else if !hasPassword || !redisSecretPattern.MatchString(password) {
		return errors.New("development redis_url must include a 32-256 character URL-safe password")
	}
	if cfg.IdleTimeout != defaultIdleTimeout || cfg.MaximumLength != defaultMaximumLength {
		return errors.New("idle_timeout and maximum_length are fixed product session boundaries")
	}
	if cfg.StateTTL <= cfg.MaximumLength || cfg.AOFTimeout <= 0 {
		return errors.New("state_ttl must exceed maximum_length and aof_timeout must be positive")
	}
	return nil
}

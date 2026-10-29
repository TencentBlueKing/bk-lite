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

var redisSecretPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{16,256}$`)

type Config struct {
	RedisURL                string        `mapstructure:"redis_url"`
	RedisPasswordFile       string        `mapstructure:"redis_password_file"`
	RedisRequireACLIdentity bool          `mapstructure:"redis_require_acl_identity"`
	RedisACLUsername        string        `mapstructure:"redis_acl_username"`
	IdleTimeout             time.Duration `mapstructure:"idle_timeout"`
	MaximumLength           time.Duration `mapstructure:"maximum_length"`
	StateTTL                time.Duration `mapstructure:"state_ttl"`
	// AOFTimeout is retained so existing collector configs still load.
	// Session assignment no longer waits for AOF.
	AOFTimeout time.Duration `mapstructure:"aof_timeout"`
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
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return errors.New("redis_url must not contain query or fragment data")
	}
	username := ""
	password := ""
	hasPassword := false
	if parsed.User != nil {
		username = parsed.User.Username()
		password, hasPassword = parsed.User.Password()
	}
	if err := requireRedisACL(cfg.RedisRequireACLIdentity, username, cfg.RedisACLUsername, "rum-sessionizer"); err != nil {
		return err
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
	if cfg.IdleTimeout != defaultIdleTimeout || cfg.MaximumLength != defaultMaximumLength {
		return errors.New("idle_timeout and maximum_length are fixed product session boundaries")
	}
	if cfg.StateTTL <= cfg.MaximumLength {
		return errors.New("state_ttl must exceed maximum_length")
	}
	return nil
}

func requireRedisACL(require bool, username, configured, fallback string) error {
	if !require {
		return nil
	}
	expected := strings.TrimSpace(configured)
	if expected == "" {
		expected = fallback
	}
	if username == "" || username != expected {
		return errors.New("redis_url ACL username must be " + expected)
	}
	return nil
}

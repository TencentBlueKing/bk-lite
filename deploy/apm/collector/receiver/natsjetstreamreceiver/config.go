package natsjetstreamreceiver

import (
	"errors"
	"regexp"
	"time"
)

var durableNamePattern = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)

type TLSConfig struct {
	CAFile             string `mapstructure:"ca_file"`
	CertFile           string `mapstructure:"cert_file"`
	KeyFile            string `mapstructure:"key_file"`
	ServerName         string `mapstructure:"server_name"`
	InsecureSkipVerify bool   `mapstructure:"insecure_skip_verify"`
}

type Config struct {
	URLs              []string      `mapstructure:"urls"`
	Stream            string        `mapstructure:"stream"`
	Consumer          string        `mapstructure:"consumer"`
	FilterSubject     string        `mapstructure:"filter_subject"`
	CredentialsFile   string        `mapstructure:"credentials_file"`
	TLS               TLSConfig     `mapstructure:"tls"`
	ConnectTimeout    time.Duration `mapstructure:"connect_timeout"`
	DownstreamTimeout time.Duration `mapstructure:"downstream_timeout"`
	NakDelay          time.Duration `mapstructure:"nak_delay"`
	PullMaxMessages   int           `mapstructure:"pull_max_messages"`
}

func (cfg *Config) Validate() error {
	if len(cfg.URLs) == 0 {
		return errors.New("urls must contain at least one NATS server")
	}
	if !durableNamePattern.MatchString(cfg.Stream) || !durableNamePattern.MatchString(cfg.Consumer) {
		return errors.New("stream and consumer must contain only letters, numbers, underscores or hyphens")
	}
	if cfg.FilterSubject != "apm.traces.>" {
		return errors.New("filter_subject must be apm.traces.>")
	}
	if (cfg.TLS.CertFile == "") != (cfg.TLS.KeyFile == "") {
		return errors.New("tls cert_file and key_file must be configured together")
	}
	if cfg.ConnectTimeout <= 0 || cfg.DownstreamTimeout <= 0 || cfg.NakDelay <= 0 {
		return errors.New("timeouts and nak_delay must be positive")
	}
	if cfg.PullMaxMessages <= 0 {
		return errors.New("pull_max_messages must be positive")
	}
	return nil
}

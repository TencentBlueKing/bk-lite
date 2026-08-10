package natsjetstreamexporter

import (
	"errors"
	"regexp"
	"time"

	"go.opentelemetry.io/collector/config/configoptional"
	"go.opentelemetry.io/collector/config/configretry"
	"go.opentelemetry.io/collector/exporter/exporterhelper"
)

var regionalSubjectPattern = regexp.MustCompile(`^apm\.traces\.[A-Za-z0-9_-]+$`)

type TLSConfig struct {
	CAFile             string `mapstructure:"ca_file"`
	CertFile           string `mapstructure:"cert_file"`
	KeyFile            string `mapstructure:"key_file"`
	ServerName         string `mapstructure:"server_name"`
	InsecureSkipVerify bool   `mapstructure:"insecure_skip_verify"`
}

type Config struct {
	exporterhelper.TimeoutConfig `mapstructure:",squash"`
	QueueConfig                  configoptional.Optional[exporterhelper.QueueBatchConfig] `mapstructure:"sending_queue"`
	RetryConfig                  configretry.BackOffConfig                                `mapstructure:"retry_on_failure"`

	URLs            []string      `mapstructure:"urls"`
	Subject         string        `mapstructure:"subject"`
	CredentialsFile string        `mapstructure:"credentials_file"`
	TLS             TLSConfig     `mapstructure:"tls"`
	ConnectTimeout  time.Duration `mapstructure:"connect_timeout"`
	MaxMessageBytes int           `mapstructure:"max_message_bytes"`
}

func (cfg *Config) Validate() error {
	if len(cfg.URLs) == 0 {
		return errors.New("urls must contain at least one NATS server")
	}
	if !regionalSubjectPattern.MatchString(cfg.Subject) {
		return errors.New("subject must match apm.traces.<cloud_region_id>")
	}
	if (cfg.TLS.CertFile == "") != (cfg.TLS.KeyFile == "") {
		return errors.New("tls cert_file and key_file must be configured together")
	}
	if cfg.ConnectTimeout <= 0 {
		return errors.New("connect_timeout must be positive")
	}
	if cfg.MaxMessageBytes <= 0 {
		return errors.New("max_message_bytes must be positive")
	}
	return nil
}

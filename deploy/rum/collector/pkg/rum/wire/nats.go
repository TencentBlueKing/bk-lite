package wire

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
)

type NATSConfig struct {
	URL             string
	CredentialsFile string
	NKeySeedFile    string
	CAFile          string
	CertFile        string
	KeyFile         string
	ServerName      string
	ConnectTimeout  time.Duration
	RequestTimeout  time.Duration
}

func (cfg NATSConfig) Validate() error {
	parsed, err := url.Parse(strings.TrimSpace(cfg.URL))
	if err != nil || parsed.Host == "" || parsed.Scheme != "tls" || parsed.User != nil {
		return errors.New("NATS URL must use tls:// without embedded credentials")
	}
	authMethods := 0
	if strings.TrimSpace(cfg.CredentialsFile) != "" {
		authMethods++
	}
	if strings.TrimSpace(cfg.NKeySeedFile) != "" {
		authMethods++
	}
	if authMethods != 1 {
		return errors.New("exactly one NATS credentials file or NKey seed file is required")
	}
	if (cfg.CertFile == "") != (cfg.KeyFile == "") {
		return errors.New("NATS TLS cert and key files must be configured together")
	}
	for label, path := range map[string]string{
		"NATS credentials": cfg.CredentialsFile,
		"NATS NKey seed":   cfg.NKeySeedFile,
		"NATS TLS key":     cfg.KeyFile,
	} {
		if strings.TrimSpace(path) == "" {
			continue
		}
		if err := validatePrivateFile(path); err != nil {
			return fmt.Errorf("%s: %w", label, err)
		}
	}
	return nil
}

func validatePrivateFile(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return errors.New("must be a regular file")
	}
	if info.Mode().Perm()&0o077 != 0 {
		return errors.New("permissions must be 0600 or stricter")
	}
	return nil
}

func ConnectNATS(cfg NATSConfig, name string) (*nats.Conn, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	timeout := cfg.ConnectTimeout
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	options := []nats.Option{
		nats.Name(name),
		nats.Timeout(timeout),
		nats.NoEcho(),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(time.Second),
	}
	var err error
	if cfg.CredentialsFile != "" {
		options = append(options, nats.UserCredentials(cfg.CredentialsFile))
	} else {
		var nkeyOption nats.Option
		nkeyOption, err = nats.NkeyOptionFromSeed(cfg.NKeySeedFile)
		if err != nil {
			return nil, fmt.Errorf("load NATS NKey seed: %w", err)
		}
		options = append(options, nkeyOption)
	}
	if cfg.CAFile != "" {
		options = append(options, nats.RootCAs(cfg.CAFile))
	}
	if cfg.CertFile != "" {
		options = append(options, nats.ClientCert(cfg.CertFile, cfg.KeyFile))
	}
	if strings.HasPrefix(cfg.URL, "tls://") || cfg.CAFile != "" || cfg.CertFile != "" {
		options = append(options, nats.Secure(&tls.Config{
			MinVersion: tls.VersionTLS13,
			ServerName: cfg.ServerName,
		}))
	}
	connection, err := nats.Connect(cfg.URL, options...)
	if err != nil {
		return nil, fmt.Errorf("connect NATS: %w", err)
	}
	return connection, nil
}

// ControlClientConfig configures a ctl-class NATS connection for control-plane
// clients (e.g. the core-admin server). Unlike rumctl it tolerates plain
// nats:// URLs so development deployments can run without NKey/TLS.
// The local compose fixture authenticates with user:password in the URL
// (rum_controller / rum_ctl). Production should still use tls:// plus a
// credentials file, never embedded secrets.
type ControlClientConfig struct {
	URL             string
	CredentialsFile string
	CAFile          string
	CertFile        string
	KeyFile         string
	ConnectTimeout  time.Duration
}

// ConnectControlClient opens a NATS connection for the RUM control client.
func ConnectControlClient(cfg ControlClientConfig, name string) (*nats.Conn, error) {
	parsed, err := url.Parse(strings.TrimSpace(cfg.URL))
	if err != nil || parsed.Host == "" {
		return nil, errors.New("NATS URL must be a nats:// or tls:// URL")
	}
	if parsed.Scheme != "nats" && parsed.Scheme != "tls" {
		return nil, errors.New("NATS URL must use nats:// or tls://")
	}
	if parsed.Scheme == "tls" && parsed.User != nil {
		return nil, errors.New("NATS URL must use tls:// without embedded credentials")
	}
	if parsed.User != nil && strings.TrimSpace(cfg.CredentialsFile) != "" {
		return nil, errors.New("NATS URL must not mix embedded credentials with a credentials file")
	}
	if (cfg.CertFile == "") != (cfg.KeyFile == "") {
		return nil, errors.New("NATS TLS cert and key files must be configured together")
	}
	timeout := cfg.ConnectTimeout
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	options := []nats.Option{
		nats.Name(name),
		nats.Timeout(timeout),
		nats.NoEcho(),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(time.Second),
	}
	if strings.TrimSpace(cfg.CredentialsFile) != "" {
		options = append(options, nats.UserCredentials(cfg.CredentialsFile))
	}
	if cfg.CAFile != "" {
		options = append(options, nats.RootCAs(cfg.CAFile))
	}
	if cfg.CertFile != "" {
		options = append(options, nats.ClientCert(cfg.CertFile, cfg.KeyFile))
	}
	if strings.HasPrefix(cfg.URL, "tls://") || cfg.CAFile != "" || cfg.CertFile != "" {
		options = append(options, nats.Secure(&tls.Config{MinVersion: tls.VersionTLS13}))
	}
	connection, err := nats.Connect(cfg.URL, options...)
	if err != nil {
		return nil, fmt.Errorf("connect RUM control NATS: %w", err)
	}
	return connection, nil
}

type Client struct {
	connection *nats.Conn
	timeout    time.Duration
	retries    int
}

func NewClient(connection *nats.Conn, timeout time.Duration, retries int) *Client {
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	if retries < 0 {
		retries = 0
	}
	return &Client{connection: connection, timeout: timeout, retries: retries}
}

func (client *Client) Call(ctx context.Context, subject string, request RequestEnvelope) (ResponseEnvelope, error) {
	encoded, err := json.Marshal(request)
	if err != nil {
		return ResponseEnvelope{}, err
	}
	var lastErr error
	for attempt := 0; attempt <= client.retries; attempt++ {
		requestCtx, cancel := context.WithTimeout(ctx, client.timeout)
		message, err := client.connection.RequestWithContext(requestCtx, subject, encoded)
		cancel()
		if err == nil {
			var response ResponseEnvelope
			if err := decodeStrict(message.Data, &response); err != nil {
				return ResponseEnvelope{}, fmt.Errorf("decode controller response: %w", err)
			}
			if response.RequestID != request.RequestID {
				return ResponseEnvelope{}, errors.New("controller response requestId does not match")
			}
			return response, nil
		}
		lastErr = err
		if !errors.Is(err, context.DeadlineExceeded) && !errors.Is(err, nats.ErrTimeout) {
			break
		}
		timer := time.NewTimer(time.Duration(attempt+1) * 100 * time.Millisecond)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ResponseEnvelope{}, ctx.Err()
		case <-timer.C:
		}
	}
	return ResponseEnvelope{}, lastErr
}

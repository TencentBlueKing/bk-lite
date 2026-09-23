package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/controller"
	"github.com/bk-lite/rum-collector/pkg/rum/wire"
	"github.com/nats-io/nats.go"
)

func main() {
	if err := run(); err != nil {
		slog.Error("bklite-rum-controller stopped", "error", err)
		os.Exit(1)
	}
}

func run() error {
	var natsConfig wire.NATSConfig
	var redisURL string
	var redisPasswordFile string
	var currentHMACFile string
	var currentHMACVersion string
	var previousHMACFile string
	var previousHMACVersion string
	var tenantID string
	var natsInsecure bool
	flag.StringVar(&natsConfig.URL, "nats-url", "", "NATS URL")
	flag.StringVar(&natsConfig.CredentialsFile, "nats-creds", "", "NATS credentials file")
	flag.StringVar(&natsConfig.NKeySeedFile, "nats-nkey-seed", "", "NATS NKey seed file")
	flag.StringVar(&natsConfig.CAFile, "nats-ca", "", "NATS TLS CA file")
	flag.StringVar(&natsConfig.CertFile, "nats-cert", "", "NATS TLS client certificate")
	flag.StringVar(&natsConfig.KeyFile, "nats-key", "", "NATS TLS client key")
	flag.StringVar(&natsConfig.ServerName, "nats-server-name", "", "NATS TLS server name")
	flag.BoolVar(&natsInsecure, "nats-insecure", false, "DEV ONLY: allow a plain nats:// URL (optional user:password for the compose fixture); never use in production")
	flag.StringVar(&redisURL, "redis-url", "", "controller Redis URL (ACL user rum-controller)")
	flag.StringVar(&redisPasswordFile, "redis-password-file", "", "controller Redis password file")
	flag.StringVar(&currentHMACFile, "identity-hmac-current-file", "", "current identity HMAC secret file")
	flag.StringVar(&currentHMACVersion, "identity-hmac-current-version", "", "current identity HMAC generation")
	flag.StringVar(&previousHMACFile, "identity-hmac-previous-file", "", "previous identity HMAC secret file")
	flag.StringVar(&previousHMACVersion, "identity-hmac-previous-version", "", "previous identity HMAC generation")
	flag.StringVar(&tenantID, "tenant-id", "", "authoritative RUM tenant identity")
	flag.Parse()

	currentHMAC, err := readSecret(currentHMACFile, true)
	if err != nil {
		return fmt.Errorf("read current identity secret: %w", err)
	}
	previousHMAC, err := readSecret(previousHMACFile, false)
	if err != nil {
		return fmt.Errorf("read previous identity secret: %w", err)
	}
	store, err := controller.NewStore(controller.StoreConfig{
		RedisURL:            redisURL,
		RedisPasswordFile:   redisPasswordFile,
		CurrentHMACSecret:   currentHMAC,
		CurrentHMACVersion:  currentHMACVersion,
		PreviousHMACSecret:  previousHMAC,
		PreviousHMACVersion: previousHMACVersion,
	})
	if err != nil {
		return err
	}
	defer store.Close()

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	if err := store.Start(ctx); err != nil {
		return err
	}
	var connection *nats.Conn
	if natsInsecure {
		// Dev-only escape: lab NATS may be plain and unauthenticated.
		// Production keeps tls:// + NKey via ConnectNATS below.
		connection, err = wire.ConnectControlClient(wire.ControlClientConfig{
			URL:             natsConfig.URL,
			CredentialsFile: natsConfig.CredentialsFile,
			CAFile:          natsConfig.CAFile,
			CertFile:        natsConfig.CertFile,
			KeyFile:         natsConfig.KeyFile,
		}, "bklite-rum-controller")
	} else {
		connection, err = wire.ConnectNATS(natsConfig, "bklite-rum-controller")
	}
	if err != nil {
		return err
	}
	defer connection.Close()
	service, err := controller.NewService(store, tenantID)
	if err != nil {
		return err
	}
	ctrl := controller.NewController(connection, service)
	if err := ctrl.Start(); err != nil {
		return err
	}
	slog.Info("bklite-rum-controller ready", "queue", controller.QueueGroupController)
	<-ctx.Done()

	drainDone := make(chan error, 1)
	go func() { drainDone <- ctrl.Drain() }()
	select {
	case err := <-drainDone:
		return err
	case <-time.After(10 * time.Second):
		return errors.New("controller drain timed out")
	}
}

func readSecret(path string, required bool) (string, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		if required {
			return "", errors.New("secret file is required")
		}
		return "", nil
	}
	info, err := os.Stat(path)
	if err != nil {
		return "", err
	}
	if info.Mode().Perm()&0o077 != 0 {
		return "", errors.New("secret file permissions must be 0600 or stricter")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	value := strings.TrimSpace(string(raw))
	if !required && value == "" {
		return "", nil
	}
	if len(value) < 32 {
		return "", errors.New("secret must contain at least 32 bytes")
	}
	return value, nil
}

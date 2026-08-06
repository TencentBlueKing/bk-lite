package natsjetstreamexporter

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer/consumererror"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.opentelemetry.io/collector/pdata/ptrace/ptraceotlp"
	"go.opentelemetry.io/otel/metric"
)

const contentTypeProtobuf = "application/x-protobuf"
const cloudRegionHeader = "BK-Cloud-Region-Id"
const schemaVersionHeader = "BK-OTLP-Schema-Version"
const schemaVersion = "1"

type jetStreamPublisher interface {
	PublishMsg(context.Context, *nats.Msg, ...jetstream.PublishOpt) (*jetstream.PubAck, error)
}

type tracesExporter struct {
	cfg            *Config
	publisher      jetStreamPublisher
	conn           *nats.Conn
	publishACKs    metric.Int64Counter
	duplicateACKs  metric.Int64Counter
	lastPublishACK metric.Int64Gauge
}

func (exporter *tracesExporter) start(_ context.Context, _ component.Host) error {
	options := []nats.Option{
		nats.Name("bk-lite-apm-regional-collector"),
		nats.Timeout(exporter.cfg.ConnectTimeout),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2 * time.Second),
	}
	if exporter.cfg.CredentialsFile != "" {
		options = append(options, nats.UserCredentials(exporter.cfg.CredentialsFile))
	}
	if exporter.cfg.TLS.CAFile != "" {
		options = append(options, nats.RootCAs(exporter.cfg.TLS.CAFile))
	}
	if exporter.cfg.TLS.CertFile != "" {
		options = append(options, nats.ClientCert(exporter.cfg.TLS.CertFile, exporter.cfg.TLS.KeyFile))
	}
	if exporter.cfg.TLS.ServerName != "" || exporter.cfg.TLS.InsecureSkipVerify {
		options = append(options, nats.Secure(&tls.Config{
			MinVersion:         tls.VersionTLS12,
			ServerName:         exporter.cfg.TLS.ServerName,
			InsecureSkipVerify: exporter.cfg.TLS.InsecureSkipVerify, //nolint:gosec // explicit deployment setting
		}))
	}
	conn, err := nats.Connect(strings.Join(exporter.cfg.URLs, ","), options...)
	if err != nil {
		return err
	}
	publisher, err := jetstream.New(conn)
	if err != nil {
		conn.Close()
		return err
	}
	exporter.conn = conn
	exporter.publisher = publisher
	return nil
}

func (exporter *tracesExporter) shutdown(_ context.Context) error {
	if exporter.conn == nil {
		return nil
	}
	return exporter.conn.Drain()
}

func encodeMessage(subject string, traces ptrace.Traces, maxMessageBytes int) (*nats.Msg, error) {
	request := ptraceotlp.NewExportRequestFromTraces(traces)
	payload, err := request.MarshalProto()
	if err != nil {
		return nil, err
	}
	if len(payload) == 0 {
		return nil, errors.New("refusing to publish an empty OTLP trace request")
	}
	if len(payload) > maxMessageBytes {
		return nil, consumererror.NewPermanent(
			fmt.Errorf("OTLP trace request is %d bytes and exceeds max_message_bytes %d", len(payload), maxMessageBytes),
		)
	}
	regionID := strings.TrimPrefix(subject, "apm.traces.")
	digest := sha256.New()
	_, _ = digest.Write([]byte(schemaVersion))
	_, _ = digest.Write([]byte{0})
	_, _ = digest.Write([]byte(regionID))
	_, _ = digest.Write([]byte{0})
	_, _ = digest.Write(payload)
	message := nats.NewMsg(subject)
	message.Data = payload
	message.Header.Set("Content-Type", contentTypeProtobuf)
	message.Header.Set(cloudRegionHeader, regionID)
	message.Header.Set(schemaVersionHeader, schemaVersion)
	message.Header.Set("Nats-Msg-Id", hex.EncodeToString(digest.Sum(nil)))
	return message, nil
}

func (exporter *tracesExporter) pushTraces(ctx context.Context, traces ptrace.Traces) error {
	if exporter.publisher == nil {
		return errors.New("NATS JetStream publisher is not started")
	}
	message, err := encodeMessage(exporter.cfg.Subject, traces, exporter.cfg.MaxMessageBytes)
	if err != nil {
		return err
	}
	ack, err := exporter.publisher.PublishMsg(ctx, message)
	if err == nil {
		exporter.publishACKs.Add(ctx, 1)
		exporter.lastPublishACK.Record(ctx, time.Now().Unix())
		if ack.Duplicate {
			exporter.duplicateACKs.Add(ctx, 1)
		}
	}
	return err
}

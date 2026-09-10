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
		return nil, &oversizedBatchError{size: len(payload), max: maxMessageBytes}
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

type oversizedBatchError struct {
	size int
	max  int
}

func (err *oversizedBatchError) Error() string {
	return fmt.Sprintf("OTLP trace request is %d bytes and exceeds max_message_bytes %d", err.size, err.max)
}

func encodeMessages(subject string, traces ptrace.Traces, maxMessageBytes int) ([]*nats.Msg, error) {
	message, err := encodeMessage(subject, traces, maxMessageBytes)
	if err == nil {
		return []*nats.Msg{message}, nil
	}
	var oversized *oversizedBatchError
	if !errors.As(err, &oversized) {
		return nil, err
	}
	left, right, splitErr := splitOversizedTraces(traces)
	if splitErr != nil {
		return nil, consumererror.NewPermanent(splitErr)
	}
	leftMessages, err := encodeMessages(subject, left, maxMessageBytes)
	if err != nil {
		return nil, err
	}
	rightMessages, err := encodeMessages(subject, right, maxMessageBytes)
	if err != nil {
		return nil, err
	}
	return append(leftMessages, rightMessages...), nil
}

func splitOversizedTraces(traces ptrace.Traces) (ptrace.Traces, ptrace.Traces, error) {
	resources := traces.ResourceSpans()
	if resources.Len() > 1 {
		mid := resources.Len() / 2
		return cloneResourceRange(traces, 0, mid), cloneResourceRange(traces, mid, resources.Len()), nil
	}
	if resources.Len() == 0 {
		return ptrace.Traces{}, ptrace.Traces{}, errors.New("cannot split an empty OTLP trace batch")
	}
	scopes := resources.At(0).ScopeSpans()
	if scopes.Len() > 1 {
		mid := scopes.Len() / 2
		return cloneScopeRange(resources.At(0), 0, mid), cloneScopeRange(resources.At(0), mid, scopes.Len()), nil
	}
	if scopes.Len() == 0 {
		return ptrace.Traces{}, ptrace.Traces{}, errors.New("cannot split a resource without spans")
	}
	spans := scopes.At(0).Spans()
	if spans.Len() > 1 {
		mid := spans.Len() / 2
		return cloneSpanRange(resources.At(0), scopes.At(0), 0, mid), cloneSpanRange(resources.At(0), scopes.At(0), mid, spans.Len()), nil
	}
	return ptrace.Traces{}, ptrace.Traces{}, fmt.Errorf("single span exceeds max_message_bytes")
}

func cloneResourceRange(traces ptrace.Traces, start, end int) ptrace.Traces {
	out := ptrace.NewTraces()
	for index := start; index < end; index++ {
		traces.ResourceSpans().At(index).CopyTo(out.ResourceSpans().AppendEmpty())
	}
	return out
}

func cloneScopeRange(src ptrace.ResourceSpans, start, end int) ptrace.Traces {
	out := ptrace.NewTraces()
	dest := out.ResourceSpans().AppendEmpty()
	src.Resource().CopyTo(dest.Resource())
	dest.SetSchemaUrl(src.SchemaUrl())
	for index := start; index < end; index++ {
		src.ScopeSpans().At(index).CopyTo(dest.ScopeSpans().AppendEmpty())
	}
	return out
}

func cloneSpanRange(srcResource ptrace.ResourceSpans, srcScope ptrace.ScopeSpans, start, end int) ptrace.Traces {
	out := ptrace.NewTraces()
	destResource := out.ResourceSpans().AppendEmpty()
	srcResource.Resource().CopyTo(destResource.Resource())
	destResource.SetSchemaUrl(srcResource.SchemaUrl())
	destScope := destResource.ScopeSpans().AppendEmpty()
	srcScope.Scope().CopyTo(destScope.Scope())
	destScope.SetSchemaUrl(srcScope.SchemaUrl())
	for index := start; index < end; index++ {
		srcScope.Spans().At(index).CopyTo(destScope.Spans().AppendEmpty())
	}
	return out
}

func (exporter *tracesExporter) pushTraces(ctx context.Context, traces ptrace.Traces) error {
	if exporter.publisher == nil {
		return errors.New("NATS JetStream publisher is not started")
	}
	messages, err := encodeMessages(exporter.cfg.Subject, traces, exporter.cfg.MaxMessageBytes)
	if err != nil {
		return err
	}
	for _, message := range messages {
		ack, err := exporter.publisher.PublishMsg(ctx, message)
		if err != nil {
			return err
		}
		exporter.publishACKs.Add(ctx, 1)
		exporter.lastPublishACK.Record(ctx, time.Now().Unix())
		if ack.Duplicate {
			exporter.duplicateACKs.Add(ctx, 1)
		}
	}
	return nil
}

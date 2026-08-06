package natsjetstreamreceiver

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.opentelemetry.io/collector/pdata/ptrace/ptraceotlp"
	"go.opentelemetry.io/otel/metric"
	"go.uber.org/zap"
)

const contentTypeProtobuf = "application/x-protobuf"
const cloudRegionHeader = "BK-Cloud-Region-Id"
const schemaVersionHeader = "BK-OTLP-Schema-Version"
const schemaVersion = "1"

var subjectPattern = regexp.MustCompile(`^apm\.traces\.([A-Za-z0-9_-]+)$`)

type deliveryAction int

const (
	deliveryRetry deliveryAction = iota
	deliveryAck
	deliveryTerminate
)

type tracesReceiver struct {
	cfg             *Config
	next            consumer.Traces
	logger          *zap.Logger
	conn            *nats.Conn
	consumeContext  jetstream.ConsumeContext
	deliveryACKs    metric.Int64Counter
	deliveryRetries metric.Int64Counter
	poisonMessages  metric.Int64Counter
	ackFailures     metric.Int64Counter
	lastDeliveryACK metric.Int64Gauge
}

func natsOptions(cfg *Config) []nats.Option {
	options := []nats.Option{
		nats.Name("bk-lite-apm-system-collector"),
		nats.Timeout(cfg.ConnectTimeout),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2 * time.Second),
	}
	if cfg.CredentialsFile != "" {
		options = append(options, nats.UserCredentials(cfg.CredentialsFile))
	}
	if cfg.TLS.CAFile != "" {
		options = append(options, nats.RootCAs(cfg.TLS.CAFile))
	}
	if cfg.TLS.CertFile != "" {
		options = append(options, nats.ClientCert(cfg.TLS.CertFile, cfg.TLS.KeyFile))
	}
	if cfg.TLS.ServerName != "" || cfg.TLS.InsecureSkipVerify {
		options = append(options, nats.Secure(&tls.Config{
			MinVersion:         tls.VersionTLS12,
			ServerName:         cfg.TLS.ServerName,
			InsecureSkipVerify: cfg.TLS.InsecureSkipVerify, //nolint:gosec // explicit deployment setting
		}))
	}
	return options
}

func (receiver *tracesReceiver) Start(ctx context.Context, _ component.Host) error {
	conn, err := nats.Connect(strings.Join(receiver.cfg.URLs, ","), natsOptions(receiver.cfg)...)
	if err != nil {
		return err
	}
	js, err := jetstream.New(conn)
	if err != nil {
		conn.Close()
		return err
	}
	stream, err := js.Stream(ctx, receiver.cfg.Stream)
	if err != nil {
		conn.Close()
		return fmt.Errorf("open pre-provisioned stream %q: %w", receiver.cfg.Stream, err)
	}
	durable, err := stream.Consumer(ctx, receiver.cfg.Consumer)
	if err != nil {
		conn.Close()
		return fmt.Errorf("open pre-provisioned consumer %q: %w", receiver.cfg.Consumer, err)
	}
	consumeContext, err := durable.Consume(
		receiver.handleMessage,
		jetstream.PullMaxMessages(receiver.cfg.PullMaxMessages),
		jetstream.ConsumeErrHandler(func(_ jetstream.ConsumeContext, consumeErr error) {
			receiver.logger.Error("NATS JetStream trace consumption failed", zap.Error(consumeErr))
		}),
	)
	if err != nil {
		conn.Close()
		return err
	}
	receiver.conn = conn
	receiver.consumeContext = consumeContext
	return nil
}

func (receiver *tracesReceiver) Shutdown(ctx context.Context) error {
	if receiver.consumeContext != nil {
		receiver.consumeContext.Drain()
		select {
		case <-receiver.consumeContext.Closed():
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	if receiver.conn == nil {
		return nil
	}
	return receiver.conn.Drain()
}

func (receiver *tracesReceiver) handleMessage(message jetstream.Msg) {
	ctx, cancel := context.WithTimeout(context.Background(), receiver.cfg.DownstreamTimeout)
	defer cancel()
	action, err := processMessage(ctx, message.Subject(), message.Headers(), message.Data(), receiver.next)
	switch action {
	case deliveryAck:
		if ackErr := message.DoubleAck(ctx); ackErr != nil {
			receiver.ackFailures.Add(ctx, 1)
			receiver.logger.Error("NATS JetStream trace ACK failed", zap.Error(ackErr))
		} else {
			receiver.deliveryACKs.Add(ctx, 1)
			receiver.lastDeliveryACK.Record(ctx, time.Now().Unix())
		}
	case deliveryTerminate:
		receiver.poisonMessages.Add(ctx, 1)
		if termErr := message.TermWithReason("invalid OTLP trace transport message"); termErr != nil {
			receiver.logger.Error("NATS JetStream poison message termination failed", zap.Error(termErr))
		}
	case deliveryRetry:
		receiver.deliveryRetries.Add(ctx, 1)
		if nakErr := message.NakWithDelay(receiver.cfg.NakDelay); nakErr != nil {
			receiver.logger.Error("NATS JetStream trace NAK failed", zap.Error(nakErr))
		}
	}
	if err != nil {
		receiver.logger.Warn("NATS JetStream trace message was not acknowledged", zap.Error(err))
	}
}

func processMessage(
	ctx context.Context,
	subject string,
	headers nats.Header,
	payload []byte,
	next consumer.Traces,
) (deliveryAction, error) {
	match := subjectPattern.FindStringSubmatch(subject)
	if len(match) != 2 {
		return deliveryTerminate, errors.New("message subject is outside the APM regional contract")
	}
	if headers.Get("Content-Type") != contentTypeProtobuf {
		return deliveryTerminate, errors.New("message content type is not application/x-protobuf")
	}
	if headers.Get(schemaVersionHeader) != schemaVersion {
		return deliveryTerminate, errors.New("message OTLP schema version is unsupported")
	}
	if headers.Get(cloudRegionHeader) != match[1] {
		return deliveryTerminate, errors.New("message cloud region header does not match its subject")
	}
	request := ptraceotlp.NewExportRequest()
	if err := request.UnmarshalProto(payload); err != nil {
		return deliveryTerminate, fmt.Errorf("decode OTLP protobuf: %w", err)
	}
	traces := request.Traces()
	stampTrustedRegion(traces, match[1])
	if err := next.ConsumeTraces(ctx, traces); err != nil {
		return deliveryRetry, fmt.Errorf("send traces downstream: %w", err)
	}
	return deliveryAck, nil
}

func removeReserved(attributes pcommon.Map) {
	attributes.RemoveIf(func(key string, _ pcommon.Value) bool {
		return strings.HasPrefix(key, "bk.")
	})
}

func stampTrustedRegion(traces ptrace.Traces, regionID string) {
	for resourceIndex := 0; resourceIndex < traces.ResourceSpans().Len(); resourceIndex++ {
		resourceSpans := traces.ResourceSpans().At(resourceIndex)
		removeReserved(resourceSpans.Resource().Attributes())
		resourceSpans.Resource().Attributes().PutStr("bk.cloud_region.id", regionID)
		for scopeIndex := 0; scopeIndex < resourceSpans.ScopeSpans().Len(); scopeIndex++ {
			scopeSpans := resourceSpans.ScopeSpans().At(scopeIndex)
			removeReserved(scopeSpans.Scope().Attributes())
			for spanIndex := 0; spanIndex < scopeSpans.Spans().Len(); spanIndex++ {
				span := scopeSpans.Spans().At(spanIndex)
				removeReserved(span.Attributes())
				for eventIndex := 0; eventIndex < span.Events().Len(); eventIndex++ {
					removeReserved(span.Events().At(eventIndex).Attributes())
				}
			}
		}
	}
}

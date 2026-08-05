package natsjetstreamreceiver

import (
	"context"
	"errors"
	"testing"

	"github.com/nats-io/nats.go"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.opentelemetry.io/collector/pdata/ptrace/ptraceotlp"
)

func encodedForgedTraces(t *testing.T) []byte {
	t.Helper()
	traces := ptrace.NewTraces()
	resourceSpans := traces.ResourceSpans().AppendEmpty()
	resourceSpans.Resource().Attributes().PutStr("service.namespace", "shop")
	resourceSpans.Resource().Attributes().PutStr("bk.cloud_region.id", "forged")
	scopeSpans := resourceSpans.ScopeSpans().AppendEmpty()
	scopeSpans.Scope().Attributes().PutStr("bk.scope", "forged")
	span := scopeSpans.Spans().AppendEmpty()
	span.SetTraceID(pcommon.TraceID{1})
	span.SetSpanID(pcommon.SpanID{2})
	span.Attributes().PutStr("bk.span", "forged")
	span.Events().AppendEmpty().Attributes().PutStr("bk.event", "forged")
	payload, err := ptraceotlp.NewExportRequestFromTraces(traces).MarshalProto()
	if err != nil {
		t.Fatal(err)
	}
	return payload
}

func transportHeaders(regionID string) nats.Header {
	return nats.Header{
		"Content-Type":      []string{contentTypeProtobuf},
		cloudRegionHeader:   []string{regionID},
		schemaVersionHeader: []string{schemaVersion},
	}
}

func TestProcessMessageStampsSubjectRegionAndOnlyAcksAfterDownstreamSuccess(t *testing.T) {
	var received ptrace.Traces
	next, err := consumer.NewTraces(func(_ context.Context, traces ptrace.Traces) error {
		received = ptrace.NewTraces()
		traces.CopyTo(received)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	headers := transportHeaders("cn_north-1")
	action, err := processMessage(context.Background(), "apm.traces.cn_north-1", headers, encodedForgedTraces(t), next)
	if err != nil || action != deliveryAck {
		t.Fatalf("valid message was not acknowledged: action=%v err=%v", action, err)
	}
	resourceSpans := received.ResourceSpans().At(0)
	attributes := resourceSpans.Resource().Attributes()
	if region, ok := attributes.Get("bk.cloud_region.id"); !ok || region.Str() != "cn_north-1" {
		t.Fatalf("trusted region was not stamped: %v", attributes.AsRaw())
	}
	if _, ok := resourceSpans.ScopeSpans().At(0).Scope().Attributes().Get("bk.scope"); ok {
		t.Fatal("forged scope attribute survived")
	}
	span := resourceSpans.ScopeSpans().At(0).Spans().At(0)
	if _, ok := span.Attributes().Get("bk.span"); ok {
		t.Fatal("forged span attribute survived")
	}
	if _, ok := span.Events().At(0).Attributes().Get("bk.event"); ok {
		t.Fatal("forged event attribute survived")
	}
}

func TestProcessMessageRetriesDownstreamFailureAndTerminatesPoison(t *testing.T) {
	failing, err := consumer.NewTraces(func(context.Context, ptrace.Traces) error {
		return errors.New("VictoriaTraces unavailable")
	})
	if err != nil {
		t.Fatal(err)
	}
	headers := transportHeaders("7")
	action, err := processMessage(context.Background(), "apm.traces.7", headers, encodedForgedTraces(t), failing)
	if action != deliveryRetry || err == nil {
		t.Fatalf("downstream failure must be retried: action=%v err=%v", action, err)
	}

	noop, err := consumer.NewTraces(func(context.Context, ptrace.Traces) error { return nil })
	if err != nil {
		t.Fatal(err)
	}
	for _, message := range []struct {
		subject string
		header  nats.Header
		payload []byte
	}{
		{"apm.traces.>", headers, encodedForgedTraces(t)},
		{"apm.traces.7", nats.Header{"Content-Type": []string{"application/json"}}, encodedForgedTraces(t)},
		{"apm.traces.7", transportHeaders("8"), encodedForgedTraces(t)},
		{"apm.traces.7", nats.Header{"Content-Type": []string{contentTypeProtobuf}}, encodedForgedTraces(t)},
		{"apm.traces.7", headers, []byte("not protobuf")},
	} {
		action, err = processMessage(context.Background(), message.subject, message.header, message.payload, noop)
		if action != deliveryTerminate || err == nil {
			t.Fatalf("poison message must terminate: action=%v err=%v", action, err)
		}
	}
}

func TestConfigRequiresPreProvisionedBoundedConsumerContract(t *testing.T) {
	cfg := createDefaultConfig().(*Config)
	cfg.Stream = "APM_TRACES"
	cfg.Consumer = "bklite-apm-system"
	if err := cfg.Validate(); err != nil {
		t.Fatalf("valid config rejected: %v", err)
	}
	cfg.FilterSubject = "apm.traces.7"
	if err := cfg.Validate(); err == nil {
		t.Fatal("regional-only filter must be rejected by the system receiver")
	}
}

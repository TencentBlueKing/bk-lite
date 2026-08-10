package natsjetstreamexporter

import (
	"bytes"
	"testing"

	"go.opentelemetry.io/collector/consumer/consumererror"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.opentelemetry.io/collector/pdata/ptrace/ptraceotlp"
)

func sampleTraces() ptrace.Traces {
	traces := ptrace.NewTraces()
	resourceSpans := traces.ResourceSpans().AppendEmpty()
	resourceSpans.Resource().Attributes().PutStr("service.namespace", "shop")
	span := resourceSpans.ScopeSpans().AppendEmpty().Spans().AppendEmpty()
	span.SetTraceID(pcommon.TraceID{1})
	span.SetSpanID(pcommon.SpanID{2})
	span.SetName("GET /orders/{id}")
	return traces
}

func TestEncodeMessagePreservesOTLPProtobufAndStableMessageID(t *testing.T) {
	first, err := encodeMessage("apm.traces.7", sampleTraces(), 1024*1024)
	if err != nil {
		t.Fatal(err)
	}
	second, err := encodeMessage("apm.traces.7", sampleTraces(), 1024*1024)
	if err != nil {
		t.Fatal(err)
	}

	if first.Header.Get("Content-Type") != contentTypeProtobuf {
		t.Fatalf("unexpected content type: %q", first.Header.Get("Content-Type"))
	}
	if first.Header.Get(cloudRegionHeader) != "7" || first.Header.Get(schemaVersionHeader) != schemaVersion {
		t.Fatalf("missing transport identity headers: %v", first.Header)
	}
	if first.Header.Get("Nats-Msg-Id") == "" || first.Header.Get("Nats-Msg-Id") != second.Header.Get("Nats-Msg-Id") {
		t.Fatalf("message ID is not stable: %q / %q", first.Header.Get("Nats-Msg-Id"), second.Header.Get("Nats-Msg-Id"))
	}
	if !bytes.Equal(first.Data, second.Data) {
		t.Fatal("equal trace batches produced different payloads")
	}
	otherRegion, err := encodeMessage("apm.traces.8", sampleTraces(), 1024*1024)
	if err != nil {
		t.Fatal(err)
	}
	if otherRegion.Header.Get("Nats-Msg-Id") == first.Header.Get("Nats-Msg-Id") {
		t.Fatal("message ID must include the trusted cloud region")
	}
	request := ptraceotlp.NewExportRequest()
	if err := request.UnmarshalProto(first.Data); err != nil {
		t.Fatalf("payload is not OTLP protobuf: %v", err)
	}
	attributes := request.Traces().ResourceSpans().At(0).Resource().Attributes()
	if value, ok := attributes.Get("service.namespace"); !ok || value.Str() != "shop" {
		t.Fatalf("resource attributes were not preserved: %v", attributes.AsRaw())
	}
}

func TestEncodeMessagePermanentlyRejectsOversizedBatch(t *testing.T) {
	_, err := encodeMessage("apm.traces.7", sampleTraces(), 1)
	if err == nil || !consumererror.IsPermanent(err) {
		t.Fatalf("oversized batch must be a permanent exporter rejection: %v", err)
	}
}

func TestConfigRequiresBoundedRegionalSubjectAndTLSKeyPair(t *testing.T) {
	cfg := createDefaultConfig().(*Config)
	for _, subject := range []string{"", "apm.traces.>", "metrics.7", "apm.traces.7.extra"} {
		cfg.Subject = subject
		if err := cfg.Validate(); err == nil {
			t.Fatalf("subject %q should be rejected", subject)
		}
	}
	cfg.Subject = "apm.traces.cn_north-1"
	cfg.TLS.CertFile = "/cert.pem"
	if err := cfg.Validate(); err == nil {
		t.Fatal("unpaired client certificate should be rejected")
	}
	cfg.TLS.KeyFile = "/key.pem"
	if err := cfg.Validate(); err != nil {
		t.Fatalf("valid config rejected: %v", err)
	}
}

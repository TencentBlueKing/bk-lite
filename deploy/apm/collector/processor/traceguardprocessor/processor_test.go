package traceguardprocessor

import (
	"strings"
	"testing"

	"go.opentelemetry.io/collector/pdata/ptrace"
)

func TestSanitizeTracesCoversEveryAttributeLayerAndKeepsOwnership(t *testing.T) {
	cfg := createDefaultConfig().(*Config)
	cfg.CloudRegionID = "cn_north-1"
	cfg.MaxAttributeRunes = 16
	cfg.MaxSpanAttrs = 2

	tracesData := ptrace.NewTraces()
	resourceSpans := tracesData.ResourceSpans().AppendEmpty()
	resource := resourceSpans.Resource().Attributes()
	resource.PutStr("service.namespace", "app-id")
	resource.PutStr("service.name", "orders")
	resource.PutStr("bk.cloud_region.id", "forged")
	resource.PutStr("password", "secret")
	scopeSpans := resourceSpans.ScopeSpans().AppendEmpty()
	scopeSpans.Scope().Attributes().PutStr("bk.scope", "forged")
	span := scopeSpans.Spans().AppendEmpty()
	span.SetName("GET /orders?token=secret")
	span.Attributes().PutStr("http.route", "/orders/{id}")
	span.Attributes().PutStr("authorization", "secret")
	span.Attributes().PutStr("long", strings.Repeat("界", 20))
	span.Attributes().PutStr("overflow", "drop")
	span.Events().AppendEmpty().Attributes().PutStr("bk.event", "forged")
	span.Events().At(0).Attributes().PutStr("cookie", "secret")
	span.Links().AppendEmpty().Attributes().PutStr("bk.link", "forged")
	span.Links().At(0).Attributes().PutStr("http.request.body", "secret")

	sanitizeTraces(tracesData, cfg)

	if region, ok := resource.Get("bk.cloud_region.id"); !ok || region.Str() != "cn_north-1" {
		t.Fatalf("trusted region missing: %v", resource.AsRaw())
	}
	for _, key := range []string{"service.namespace", "service.name"} {
		if _, ok := resource.Get(key); !ok {
			t.Fatalf("ownership key %q was removed", key)
		}
	}
	if _, ok := resource.Get("password"); ok {
		t.Fatal("sensitive resource attribute survived")
	}
	if span.Name() != "GET /orders" {
		t.Fatalf("span name query was not removed: %q", span.Name())
	}
	if span.Attributes().Len() != 2 {
		t.Fatalf("span attributes are not bounded: %v", span.Attributes().AsRaw())
	}
	if value, ok := span.Attributes().Get("long"); !ok || len([]rune(value.Str())) != 16 {
		t.Fatalf("unicode value was not safely truncated: %v", span.Attributes().AsRaw())
	}
	if scopeSpans.Scope().Attributes().Len() != 0 || span.Events().At(0).Attributes().Len() != 0 || span.Links().At(0).Attributes().Len() != 0 {
		t.Fatal("reserved or sensitive nested attributes survived")
	}
}

func TestConfigRejectsUntrustedRegionOrUnboundedLimits(t *testing.T) {
	cfg := createDefaultConfig().(*Config)
	cfg.CloudRegionID = "region.with.dot"
	if err := cfg.Validate(); err == nil {
		t.Fatal("invalid region should be rejected")
	}
	cfg.CloudRegionID = "7"
	cfg.MaxLinkAttrs = 0
	if err := cfg.Validate(); err == nil {
		t.Fatal("zero limits should be rejected")
	}
}

func TestSanitizeTracesDropsOversizedIdentityWithoutTruncatingIntoACollision(t *testing.T) {
	cfg := createDefaultConfig().(*Config)
	cfg.CloudRegionID = "7"
	tracesData := ptrace.NewTraces()

	validResourceSpans := tracesData.ResourceSpans().AppendEmpty()
	validResource := validResourceSpans.Resource().Attributes()
	validResource.PutStr("service.namespace", "shop")
	validResource.PutStr("service.name", strings.Repeat("服", 256))
	validResource.PutStr("service.instance.id", strings.Repeat("实", 512))
	validResource.PutStr("service.version", strings.Repeat("版", 256))
	validResource.PutStr("deployment.environment", strings.Repeat("环", 256))
	validResource.PutStr("custom.long", strings.Repeat("界", 4097))

	invalidResourceSpans := tracesData.ResourceSpans().AppendEmpty()
	invalidResource := invalidResourceSpans.Resource().Attributes()
	invalidResource.PutStr("service.namespace", "shop")
	invalidResource.PutStr("service.name", "checkout")
	invalidResource.PutStr("service.instance.id", strings.Repeat("x", 513))

	result := sanitizeTraces(tracesData, cfg)

	if result.DroppedResourceSpans != 1 {
		t.Fatalf("unexpected dropped identity count: %+v", result)
	}
	if tracesData.ResourceSpans().Len() != 1 {
		t.Fatalf("invalid resource spans survived: %d", tracesData.ResourceSpans().Len())
	}
	remaining := tracesData.ResourceSpans().At(0).Resource().Attributes()
	if instance, _ := remaining.Get("service.instance.id"); len([]rune(instance.Str())) != 512 {
		t.Fatalf("valid identity was truncated: %d", len([]rune(instance.Str())))
	}
	if custom, _ := remaining.Get("custom.long"); len([]rune(custom.Str())) != 4096 {
		t.Fatalf("general attribute limit changed: %d", len([]rune(custom.Str())))
	}
}

func TestSanitizeTracesDropsInvalidServiceIdentityButKeepsMissingInstanceForDiagnostics(t *testing.T) {
	cfg := createDefaultConfig().(*Config)
	cfg.CloudRegionID = "7"
	tracesData := ptrace.NewTraces()

	missingInstance := tracesData.ResourceSpans().AppendEmpty()
	missingInstance.Resource().Attributes().PutStr("service.name", "checkout")
	invalidName := tracesData.ResourceSpans().AppendEmpty()
	invalidName.Resource().Attributes().PutStr("service.name", "")
	invalidType := tracesData.ResourceSpans().AppendEmpty()
	invalidType.Resource().Attributes().PutInt("service.name", 42)

	result := sanitizeTraces(tracesData, cfg)

	if result.DroppedResourceSpans != 2 || tracesData.ResourceSpans().Len() != 1 {
		t.Fatalf("identity acceptance mismatch: result=%+v resources=%d", result, tracesData.ResourceSpans().Len())
	}
	if _, ok := tracesData.ResourceSpans().At(0).Resource().Attributes().Get("service.instance.id"); ok {
		t.Fatal("missing instance identity was synthesized")
	}
}

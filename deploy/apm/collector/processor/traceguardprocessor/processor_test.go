package traceguardprocessor

import (
	"strings"
	"testing"

	"go.opentelemetry.io/collector/pdata/pcommon"
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

func TestSanitizeTracesDeletesNestedSensitiveAndReservedKeys(t *testing.T) {
	cfg := createDefaultConfig().(*Config)
	cfg.CloudRegionID = "cn_north-1"
	cfg.MaxAttributeRunes = 16
	cfg.MaxSpanAttrs = 2

	tracesData := ptrace.NewTraces()
	resourceSpans := tracesData.ResourceSpans().AppendEmpty()
	resource := resourceSpans.Resource().Attributes()
	resource.PutStr("service.namespace", "app-id")
	resource.PutStr("service.name", "orders")
	putNestedSensitiveMap(resource.PutEmptyMap("metadata"))

	scopeSpans := resourceSpans.ScopeSpans().AppendEmpty()
	span := scopeSpans.Spans().AppendEmpty()
	span.SetName("GET /orders")
	putNestedSensitiveMap(span.Attributes().PutEmptyMap("metadata"))
	span.Attributes().PutStr("http.route", "/orders/{id}")
	item := span.Attributes().PutEmptySlice("items").AppendEmpty()
	putNestedSensitiveMap(item.SetEmptyMap())

	putNestedSensitiveMap(span.Events().AppendEmpty().Attributes().PutEmptyMap("metadata"))
	putNestedSensitiveMap(span.Links().AppendEmpty().Attributes().PutEmptyMap("metadata"))

	sanitizeTraces(tracesData, cfg)

	assertNestedSensitiveMapCleared(t, "resource", mustMap(t, resource, "metadata"))
	if span.Attributes().Len() != 2 {
		t.Fatalf("outer span attribute cap changed: %v", span.Attributes().AsRaw())
	}
	if _, ok := span.Attributes().Get("items"); ok {
		t.Fatalf("outer overflow should still drop extra span attributes: %v", span.Attributes().AsRaw())
	}
	assertNestedSensitiveMapCleared(t, "span", mustMap(t, span.Attributes(), "metadata"))
	if value, ok := span.Attributes().Get("http.route"); !ok || value.Str() != "/orders/{id}" {
		t.Fatalf("allowed outer span attribute was dropped: %v", span.Attributes().AsRaw())
	}
	assertNestedSensitiveMapCleared(t, "event", mustMap(t, span.Events().At(0).Attributes(), "metadata"))
	assertNestedSensitiveMapCleared(t, "link", mustMap(t, span.Links().At(0).Attributes(), "metadata"))
}

func putNestedSensitiveMap(target pcommon.Map) {
	target.PutStr("safe", "ok")
	target.PutStr("password", "secret")
	target.PutStr("url.full", "https://example.com/secret")
	target.PutStr("bk.internal", "forged")
	target.PutStr("long", strings.Repeat("界", 20))
	child := target.PutEmptyMap("child")
	child.PutStr("safe", "ok")
	child.PutStr("token", "secret")
	item := target.PutEmptySlice("items").AppendEmpty()
	nestedItem := item.SetEmptyMap()
	nestedItem.PutStr("safe", "ok")
	nestedItem.PutStr("http.request.body", "secret")
}

func mustMap(t *testing.T, attributes pcommon.Map, key string) pcommon.Map {
	t.Helper()
	value, ok := attributes.Get(key)
	if !ok || value.Type() != pcommon.ValueTypeMap {
		t.Fatalf("missing nested map %q: %v", key, attributes.AsRaw())
	}
	return value.Map()
}

func assertNestedSensitiveMapCleared(t *testing.T, layer string, nested pcommon.Map) {
	t.Helper()
	raw := nested.AsRaw()
	for _, key := range []string{"password", "url.full", "bk.internal", "token", "http.request.body"} {
		if _, ok := raw[key]; ok {
			t.Fatalf("%s nested key %q survived: %v", layer, key, raw)
		}
	}
	if raw["safe"] != "ok" {
		t.Fatalf("%s allowed nested key was removed: %v", layer, raw)
	}
	long, ok := nested.Get("long")
	if !ok || long.Type() != pcommon.ValueTypeStr || len([]rune(long.Str())) != 16 {
		t.Fatalf("%s nested unicode truncation changed: %v", layer, raw)
	}
	child := mustMap(t, nested, "child")
	if _, ok := child.Get("token"); ok {
		t.Fatalf("%s nested child token survived: %v", layer, child.AsRaw())
	}
	if safe, ok := child.Get("safe"); !ok || safe.Str() != "ok" {
		t.Fatalf("%s nested child safe key was removed: %v", layer, child.AsRaw())
	}
	items, ok := nested.Get("items")
	if !ok || items.Type() != pcommon.ValueTypeSlice || items.Slice().Len() != 1 {
		t.Fatalf("%s nested slice missing: %v", layer, raw)
	}
	item := items.Slice().At(0)
	if item.Type() != pcommon.ValueTypeMap {
		t.Fatalf("%s nested slice item is not a map: %v", layer, items.AsRaw())
	}
	if _, ok := item.Map().Get("http.request.body"); ok {
		t.Fatalf("%s nested slice body survived: %v", layer, item.Map().AsRaw())
	}
	if safe, ok := item.Map().Get("safe"); !ok || safe.Str() != "ok" {
		t.Fatalf("%s nested slice safe key was removed: %v", layer, item.Map().AsRaw())
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

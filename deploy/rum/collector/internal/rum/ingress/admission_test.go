package ingress

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

const testRedisPassword = "rum-admission-test-password-at-least-32-bytes"

func TestParseOriginAcceptsOnlyExactHTTPOrigins(t *testing.T) {
	for _, origin := range []string{
		"https://app.example.test",
		"http://localhost:5100",
		"https://[2001:db8::1]:8443",
	} {
		t.Run(origin, func(t *testing.T) {
			canonical, err := ParseOrigin(origin)
			require.NoError(t, err)
			require.Equal(t, origin, canonical)
		})
	}

	for _, origin := range []string{
		"",
		"null",
		"*",
		"https://*.example.test",
		"file://app",
		"https://user:pass@app.example.test",
		"https://app.example.test/",
		"https://app.example.test/path",
		"https://app.example.test?query=yes",
		"https://app.example.test#fragment",
	} {
		t.Run("reject_"+origin, func(t *testing.T) {
			_, err := ParseOrigin(origin)
			require.ErrorIs(t, err, ErrInvalidOrigin)
		})
	}
}

func TestAdmissionAtomicallyChecksApplicationKeyOriginBudgetAndFence(t *testing.T) {
	admission, server := newTestAdmission(t)
	seedApplication(t, admission.client, Application{
		Name:                       "storefront",
		TenantID:                   "tenant-a",
		OrgID:                      "org-1",
		Enabled:                    true,
		Revision:                   7,
		RequestsPerMinute:          2,
		CompressedBytesPerMinute:   100,
		DecompressedBytesPerMinute: 200,
		EventsPerMinute:            3,
		BrowserKeyDigests:          []string{KeyDigest("browser-key-current"), KeyDigest("browser-key-next")},
		Origins:                    []string{"https://app.example.test"},
	})

	decision, err := admission.Admit(t.Context(), Request{
		Application:       "storefront",
		AuthorityTenantID: "tenant-a",
		BrowserKey:        "browser-key-current",
		Origin:            "https://app.example.test",
		CompressedBytes:   40,
		DecompressedBytes: 80,
		EventCount:        1,
	})
	require.NoError(t, err)
	require.True(t, decision.Allowed)
	require.Equal(t, "tenant-a", decision.TenantID)
	require.Equal(t, int64(7), decision.Revision)

	decision, err = admission.Admit(t.Context(), Request{
		Application:       "storefront",
		AuthorityTenantID: "tenant-a",
		BrowserKey:        "browser-key-next",
		Origin:            "https://app.example.test",
		CompressedBytes:   40,
		DecompressedBytes: 80,
		EventCount:        2,
	})
	require.NoError(t, err)
	require.True(t, decision.Allowed)

	decision, err = admission.Admit(t.Context(), Request{
		Application:       "storefront",
		AuthorityTenantID: "tenant-a",
		BrowserKey:        "browser-key-current",
		Origin:            "https://app.example.test",
		CompressedBytes:   1,
		DecompressedBytes: 1,
		EventCount:        1,
	})
	require.NoError(t, err)
	require.False(t, decision.Allowed)
	require.Equal(t, RejectBudget, decision.Reason)
	require.Equal(t, time.Minute, decision.RetryAfter)

	rateKey := RateKey("storefront", time.Unix(1_784_109_600, 0).UTC())
	require.Equal(t, "2", server.HGet(rateKey, "requests"))
	require.Equal(t, "80", server.HGet(rateKey, "compressed_bytes"))
	require.Equal(t, "160", server.HGet(rateKey, "decompressed_bytes"))
	require.Equal(t, "3", server.HGet(rateKey, "events"))

	userHash := KeyDigest("user-id")
	require.NoError(t, admission.client.ZAdd(
		t.Context(),
		ErasureFenceKey("v1", userHash),
		redis.Z{Score: 0, Member: "fence"},
	).Err())
	decision, err = admission.Admit(t.Context(), Request{
		Application:       "storefront",
		AuthorityTenantID: "tenant-a",
		BrowserKey:        "browser-key-current",
		Origin:            "https://app.example.test",
		UserFences:        []FenceIdentity{{Version: "v1", Digest: userHash}},
	})
	require.NoError(t, err)
	require.False(t, decision.Allowed)
	require.Equal(t, RejectErasureFence, decision.Reason)
}

func TestFenceLeaseSerializesExporterWithErasureSubmission(t *testing.T) {
	server := miniredis.RunT(t)
	manager := &redisFenceLeases{
		client: redis.NewClient(&redis.Options{Addr: server.Addr()}),
		ttl:    defaultFenceLeaseTTL,
		now:    time.Now,
	}
	identity := FenceIdentity{Version: "v1", Digest: strings.Repeat("a", 64)}
	key := ErasureFenceKey(identity.Version, identity.Digest)

	lease, err := manager.Acquire(t.Context(), []FenceIdentity{identity})
	require.NoError(t, err)
	require.Equal(t, int64(1), manager.client.ZCount(t.Context(), key, "1", "+inf").Val())

	require.NoError(t, manager.client.ZAdd(
		t.Context(),
		key,
		redis.Z{Score: 0, Member: "fence"},
	).Err())
	_, err = manager.Acquire(t.Context(), []FenceIdentity{identity})
	require.ErrorIs(t, err, ErrErasureFenced)

	require.NoError(t, lease.Release(t.Context()))
	require.Zero(t, manager.client.ZCount(t.Context(), key, "1", "+inf").Val())
	_, err = manager.client.ZScore(t.Context(), key, "fence").Result()
	require.NoError(t, err)
}

func TestAdmissionReadsRedisOnEveryRequestSoDisableAndRetireAreImmediate(t *testing.T) {
	admission, _ := newTestAdmission(t)
	seedApplication(t, admission.client, Application{
		Name:                       "storefront",
		TenantID:                   "tenant-a",
		OrgID:                      "org-1",
		Enabled:                    true,
		Revision:                   1,
		RequestsPerMinute:          100,
		CompressedBytesPerMinute:   1_000_000,
		DecompressedBytesPerMinute: 4_000_000,
		EventsPerMinute:            1_000,
		BrowserKeyDigests:          []string{KeyDigest("browser-key-current")},
		Origins:                    []string{"https://app.example.test"},
	})
	request := Request{
		Application:       "storefront",
		AuthorityTenantID: "tenant-a",
		BrowserKey:        "browser-key-current",
		Origin:            "https://app.example.test",
	}

	first, err := admission.Admit(t.Context(), request)
	require.NoError(t, err)
	require.True(t, first.Allowed)

	require.NoError(t, admission.client.SRem(t.Context(), ApplicationKeysKey("storefront"), KeyDigest("browser-key-current")).Err())
	retired, err := admission.Admit(t.Context(), request)
	require.NoError(t, err)
	require.Equal(t, RejectBrowserKey, retired.Reason)

	require.NoError(t, admission.client.SAdd(t.Context(), ApplicationKeysKey("storefront"), KeyDigest("browser-key-current")).Err())
	require.NoError(t, admission.client.HSet(t.Context(), ApplicationKey("storefront"), "enabled", "0").Err())
	disabled, err := admission.Admit(t.Context(), request)
	require.NoError(t, err)
	require.Equal(t, RejectApplicationDisabled, disabled.Reason)
}

func TestAdmissionFailsClosedWhenRedisIsUnavailable(t *testing.T) {
	admission, server := newTestAdmission(t)
	server.Close()

	decision, err := admission.Admit(t.Context(), Request{
		Application:       "storefront",
		AuthorityTenantID: "tenant-a",
		BrowserKey:        "browser-key-current",
		Origin:            "https://app.example.test",
	})
	require.ErrorIs(t, err, ErrUnavailable)
	require.False(t, decision.Allowed)
}

func TestAdmissionFailsClosedWhenControllerAndGatewayTenantAuthorityDiffer(t *testing.T) {
	admission, _ := newTestAdmission(t)
	seedApplication(t, admission.client, Application{
		Name:                       "storefront",
		TenantID:                   "tenant-a",
		OrgID:                      "org-1",
		Enabled:                    true,
		Revision:                   1,
		RequestsPerMinute:          100,
		CompressedBytesPerMinute:   1_000_000,
		DecompressedBytesPerMinute: 4_000_000,
		EventsPerMinute:            1_000,
		BrowserKeyDigests:          []string{KeyDigest("browser-key-current")},
		Origins:                    []string{"https://app.example.test"},
	})

	decision, err := admission.Admit(t.Context(), Request{
		Application:       "storefront",
		AuthorityTenantID: "tenant-b",
		BrowserKey:        "browser-key-current",
		Origin:            "https://app.example.test",
	})

	require.ErrorIs(t, err, ErrUnavailable)
	require.False(t, decision.Allowed)
}

func newTestAdmission(t *testing.T) (*Admission, *miniredis.Miniredis) {
	t.Helper()
	server := miniredis.RunT(t)
	server.RequireAuth(testRedisPassword)
	admission, err := New(Config{
		RedisURL: "redis://rum-admission:" + testRedisPassword + "@" + server.Addr(),
		Now:      func() time.Time { return time.Unix(1_784_109_600, 0).UTC() },
	})
	require.NoError(t, err)
	require.NoError(t, admission.client.Close())
	admission.client = redis.NewClient(&redis.Options{Addr: server.Addr(), Password: testRedisPassword})
	t.Cleanup(func() { _ = admission.Shutdown(context.Background()) })
	return admission, server
}

func seedApplication(t *testing.T, client *redis.Client, application Application) {
	t.Helper()
	require.NoError(t, ValidateApplication(application))
	require.NoError(t, client.HSet(t.Context(), ApplicationKey(application.Name), map[string]any{
		"enabled":                       boolInt(application.Enabled),
		"revision":                      application.Revision,
		"tenant_id":                     application.TenantID,
		"org_id":                        application.OrgID,
		"requests_per_minute":           application.RequestsPerMinute,
		"compressed_bytes_per_minute":   application.CompressedBytesPerMinute,
		"decompressed_bytes_per_minute": application.DecompressedBytesPerMinute,
		"events_per_minute":             application.EventsPerMinute,
	}).Err())
	if len(application.BrowserKeyDigests) > 0 {
		require.NoError(t, client.SAdd(t.Context(), ApplicationKeysKey(application.Name), application.BrowserKeyDigests).Err())
	}
	if len(application.Origins) > 0 {
		require.NoError(t, client.SAdd(t.Context(), ApplicationOriginsKey(application.Name), application.Origins).Err())
	}
}

func boolInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

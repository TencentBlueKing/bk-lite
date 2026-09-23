package authority

import "testing"

func TestIdentityKeyIsTenantAndPurposeSeparated(t *testing.T) {
	const secret = "test-rum-identity-hmac-secret-at-least-32-bytes"
	if got := DeriveIdentityKey(secret, "user", "tenant-a", "user-42"); got == "" {
		t.Fatal("identity key must be non-empty")
	}
	if DeriveIdentityKey(secret, "user", "tenant-a", "same-id") == DeriveIdentityKey(secret, "session", "tenant-a", "same-id") {
		t.Fatal("user and session domains must differ")
	}
	if DeriveIdentityKey(secret, "user", "tenant-a", "user-42") == DeriveIdentityKey(secret, "user", "tenant-b", "user-42") {
		t.Fatal("tenant authority must affect the key")
	}
	if DeriveIdentityKey(secret, "user", "tenant-a", "user-42") != DeriveIdentityKey(secret, "user", "tenant-a", "user-42") {
		t.Fatal("identity key must be deterministic")
	}
}

func TestIdentityKeyRejectsIncompleteInput(t *testing.T) {
	if DeriveIdentityKey("", "user", "tenant-a", "user-42") != "" {
		t.Fatal("missing secret must yield empty key")
	}
	if DeriveIdentityKey("secret", "unknown", "tenant-a", "user-42") != "" {
		t.Fatal("unknown purpose must yield empty key")
	}
	if DeriveIdentityKey("secret", "user", "", "user-42") != "" {
		t.Fatal("missing tenant must yield empty key")
	}
}

func TestAnonymousUserIdentityIsSessionScoped(t *testing.T) {
	if UserIdentityMaterial("", "session-1") == UserIdentityMaterial("", "session-2") {
		t.Fatal("anonymous identity must remain session scoped")
	}
	if got := UserIdentityMaterial("user-42", "session-1"); got != "user-42" {
		t.Fatalf("explicit user identity changed: %q", got)
	}
	if got := UserIdentityMaterial("", ""); got != "" {
		t.Fatalf("missing identities must remain empty: %q", got)
	}
}

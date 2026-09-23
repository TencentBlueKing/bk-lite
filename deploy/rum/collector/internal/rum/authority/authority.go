package authority

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

const erasureIdentityDomain = "core-rum-identity-v1"
const anonymousSessionIdentityDomain = "anonymous-session"

// DeriveIdentityKey returns a stable pseudonymous hash for a replay identity
// (user or session). The raw value never leaves the receiver; object keys and
// sessionization only see this hash. The same digest is the active erasure
// fence identity, so queued telemetry can be rejected without retaining the
// original user or session identifier.
func DeriveIdentityKey(secret, kind, tenantID, rawID string) string {
	if secret == "" || tenantID == "" || rawID == "" || (kind != "user" && kind != "session") {
		return ""
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(strings.Join([]string{
		erasureIdentityDomain,
		kind,
		tenantID,
		rawID,
	}, "\x00")))
	return hex.EncodeToString(mac.Sum(nil))
}

// UserIdentityMaterial gives anonymous traffic a stable, erasable user fence
// without inventing or retaining a raw user identity.
func UserIdentityMaterial(rawUserID, rawSessionID string) string {
	if rawUserID != "" {
		return rawUserID
	}
	if rawSessionID == "" {
		return ""
	}
	return anonymousSessionIdentityDomain + "\x00" + rawSessionID
}

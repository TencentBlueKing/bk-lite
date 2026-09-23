package rumprivacy

import (
	"crypto/sha256"
	"encoding/hex"
	"net/url"
	"strings"
)

const sourceMapAssetDomain = "weops-rum-asset-v1"

// AssetFingerprint is the stable privacy boundary shared by RUM ingestion and
// SourceMap upload. It retains only a keyed contract hash of the deployed path.
func AssetFingerprint(raw string) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" || strings.ContainsAny(trimmed, "\x00\r\n\\") {
		return ""
	}
	parsed, err := url.Parse(trimmed)
	if err != nil || parsed.User != nil || (parsed.IsAbs() && parsed.Scheme != "http" && parsed.Scheme != "https") {
		return ""
	}
	for _, segment := range strings.Split(parsed.Path, "/") {
		if segment == "." || segment == ".." {
			return ""
		}
	}
	path := parsed.EscapedPath()
	if path == "" {
		return ""
	}
	if !strings.HasPrefix(path, "/") {
		path = "/" + path
	}
	if path == "/" || strings.HasSuffix(path, "/") {
		return ""
	}
	digest := sha256.Sum256([]byte(sourceMapAssetDomain + "\x00" + path))
	return "asset:" + hex.EncodeToString(digest[:16])
}

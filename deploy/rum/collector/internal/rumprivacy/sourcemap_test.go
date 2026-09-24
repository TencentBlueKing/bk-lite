package rumprivacy

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestAssetFingerprintUsesOnlyNormalizedDeployedPath(t *testing.T) {
	expected := "asset:9ab0ce4d26f7d0ad959edd4b45878c1b"
	require.Equal(t, expected, AssetFingerprint("https://cdn.example.test/assets/checkout.min.js?v=7#x"))
	require.Equal(t, expected, AssetFingerprint("/assets/checkout.min.js"))
	require.Empty(t, AssetFingerprint("javascript:alert(1)"))
	require.Empty(t, AssetFingerprint("../main.js"))
}

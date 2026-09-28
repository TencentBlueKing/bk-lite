package farorumreceiver

import (
	"os"
	"testing"

	"github.com/stretchr/testify/require"
)

// The browser SDK (packages/bklite-rum-sdk) and the gateway receiver each commit
// an identical copy of the exact-SDK golden corpus so the wire contract is
// pinned from both sides. This guard fails the build if the two copies drift.
func TestSDKGoldenCorpusDoesNotDriftFromGatewayFixture(t *testing.T) {
	sdkFixture, err := os.ReadFile("../../../../../../../packages/bklite-rum-sdk/testdata/faro-2.8.2-golden.json")
	require.NoError(t, err)
	gatewayFixture, err := os.ReadFile("testdata/faro-2.8.2-golden.json")
	require.NoError(t, err)
	require.Equal(t, string(sdkFixture), string(gatewayFixture))
}

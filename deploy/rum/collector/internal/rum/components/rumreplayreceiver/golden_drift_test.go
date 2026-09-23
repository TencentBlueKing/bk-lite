package rumreplayreceiver

import (
	"os"
	"testing"

	"github.com/stretchr/testify/require"
)

// The browser SDK and the replay receiver each commit an identical copy of the
// exact replay transport-envelope golden so the segment wire contract is pinned
// from both sides. This guard fails the build if the two copies drift.
func TestSDKReplayEnvelopeGoldenDoesNotDriftFromGatewayFixture(t *testing.T) {
	sdkFixture, err := os.ReadFile("../../../../../../../packages/bklite-rum-sdk/testdata/faro_transport_envelope.golden.json")
	require.NoError(t, err)
	gatewayFixture, err := os.ReadFile("testdata/faro_transport_envelope.golden.json")
	require.NoError(t, err)
	require.Equal(t, string(sdkFixture), string(gatewayFixture))
}

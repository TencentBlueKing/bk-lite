package wire

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestNATSConfigRequiresTLSAndOneFileBackedIdentity(t *testing.T) {
	seed := filepath.Join(t.TempDir(), "seed")
	require.NoError(t, os.WriteFile(seed, []byte("seed"), 0o600))

	valid := NATSConfig{
		URL:          "tls://nats:4222",
		NKeySeedFile: seed,
	}
	require.NoError(t, valid.Validate())

	insecure := valid
	insecure.URL = "nats://nats:4222"
	require.ErrorContains(t, insecure.Validate(), "tls://")

	embedded := valid
	embedded.URL = "tls://user:password@nats:4222"
	require.ErrorContains(t, embedded.Validate(), "embedded credentials")

	multiple := valid
	multiple.CredentialsFile = seed
	require.ErrorContains(t, multiple.Validate(), "exactly one")
}

func TestNATSConfigRejectsReadablePrivateFiles(t *testing.T) {
	seed := filepath.Join(t.TempDir(), "seed")
	require.NoError(t, os.WriteFile(seed, []byte("seed"), 0o644))

	err := (NATSConfig{
		URL:          "tls://nats:4222",
		NKeySeedFile: seed,
	}).Validate()
	require.ErrorContains(t, err, "0600")
}

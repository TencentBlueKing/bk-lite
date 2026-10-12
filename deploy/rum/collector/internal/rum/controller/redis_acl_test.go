package controller

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestControlRedisAcceptsPasswordWithoutUsername(t *testing.T) {
	options, err := controlRedisOptions(
		"redis://:"+strings.Repeat("p", 32)+"@rum-redis:6379",
		"",
		false,
		"",
	)
	require.NoError(t, err)
	require.Equal(t, "", options.Username)
	require.Equal(t, strings.Repeat("p", 32), options.Password)
}

func TestControlRedisRejectsACLUsernameMismatch(t *testing.T) {
	_, err := controlRedisOptions(
		"redis://other:"+strings.Repeat("p", 32)+"@rum-redis:6379",
		"",
		true,
		"",
	)
	require.ErrorContains(t, err, "ACL username must be rum-controller")

	options, err := controlRedisOptions(
		"redis://shared-rum:"+strings.Repeat("p", 32)+"@rum-redis:6379",
		"",
		true,
		"shared-rum",
	)
	require.NoError(t, err)
	require.Equal(t, "shared-rum", options.Username)
}

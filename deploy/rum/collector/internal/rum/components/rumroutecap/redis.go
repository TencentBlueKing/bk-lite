package rumroutecap

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"

	rumstate "github.com/bk-lite/rum-collector/internal/rum/state"
)

// admitRouteLua admits a route while the set has fewer than ARGV[2] members.
// The check and insert run in one script so every gateway replica agrees.
// ARGV: 1 route, 2 limit, 3 ttl milliseconds. Returns 1 when the route is
// admitted and 0 when it belongs in the overflow label.
const admitRouteLua = `
local function touch()
  if redis.call('EXISTS', KEYS[1]) == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[3])
  end
end

if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
  touch()
  return 1
end
if redis.call('SCARD', KEYS[1]) < tonumber(ARGV[2]) then
  redis.call('SADD', KEYS[1], ARGV[1])
  redis.call('PEXPIRE', KEYS[1], ARGV[3])
  return 1
end
touch()
return 0
`

type routeStore struct {
	client *redis.Client
	script *redis.Script
	ttl    time.Duration
}

func newRouteStore(cfg *Config) (*routeStore, error) {
	client, err := newRedisClient(cfg)
	if err != nil {
		return nil, err
	}
	return &routeStore{
		client: client,
		script: redis.NewScript(admitRouteLua),
		ttl:    admissionTTL,
	}, nil
}

func newRedisClient(cfg *Config) (*redis.Client, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	options, err := redis.ParseURL(strings.TrimSpace(cfg.RedisURL))
	if err != nil {
		return nil, fmt.Errorf("parse aggregate route redis url: %w", err)
	}
	if cfg.RedisPasswordFile != "" {
		password, err := readPasswordFile(cfg.RedisPasswordFile)
		if err != nil {
			return nil, err
		}
		options.Password = password
	}
	if options.TLSConfig != nil {
		options.TLSConfig.MinVersion = tls.VersionTLS12
	}
	options.DialTimeout = redisTimeout
	options.ReadTimeout = redisTimeout
	options.WriteTimeout = redisTimeout
	return redis.NewClient(options), nil
}

func readPasswordFile(path string) (string, error) {
	info, err := os.Stat(path)
	if err != nil {
		return "", fmt.Errorf("stat aggregate route redis password file: %w", err)
	}
	if info.Mode().Perm()&0o077 != 0 {
		return "", errors.New("aggregate route redis password file permissions must be 0600 or stricter")
	}
	contents, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read aggregate route redis password file: %w", err)
	}
	password := strings.TrimSpace(string(contents))
	if len(password) < 16 || len(password) > 256 {
		return "", errors.New("aggregate route redis password file must contain 16-256 characters")
	}
	return password, nil
}

func (store *routeStore) admit(ctx context.Context, tenant, application, route string) (bool, error) {
	lookupCtx, cancel := context.WithTimeout(ctx, redisTimeout)
	defer cancel()
	admitted, err := store.script.Run(
		lookupCtx,
		store.client,
		[]string{admissionKey(tenant, application)},
		route,
		maxRoutesPerApplication,
		store.ttl.Milliseconds(),
	).Int()
	if err != nil {
		return false, err
	}
	return admitted == 1, nil
}

func (store *routeStore) close() error {
	return store.client.Close()
}

func admissionKey(tenant, application string) string {
	sum := sha256.Sum256([]byte(tenant + "\x00" + application))
	return rumstate.AggregateRouteKeyPrefix + hex.EncodeToString(sum[:])
}

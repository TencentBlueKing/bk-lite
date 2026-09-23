package rumsessionprocessor

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"

	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/collector/component"
)

const assignSessionLua = `
local values = redis.call('HMGET', KEYS[1], 'key', 'first', 'last', 'traffic')
local session_key = values[1]
local first_seen = tonumber(values[2])
local last_seen = tonumber(values[3])
local traffic = values[4]
local observed = tonumber(ARGV[1])
local rolled = 0

if not session_key or not first_seen or not last_seen
  or observed - last_seen >= tonumber(ARGV[2])
  or observed - first_seen >= tonumber(ARGV[3]) then
  session_key = ARGV[4]
  first_seen = observed
  last_seen = observed
  traffic = ARGV[5]
  rolled = 1
else
  if observed > last_seen then
    last_seen = observed
  end
  if not traffic or traffic == '' or traffic == 'unknown' then
    traffic = ARGV[5]
  end
end

redis.call('HSET', KEYS[1],
  'key', session_key,
  'first', tostring(first_seen),
  'last', tostring(last_seen),
  'traffic', traffic)
redis.call('PEXPIRE', KEYS[1], ARGV[6])
return {session_key, traffic, rolled}
`

type redisSessionStore struct {
	client       *redis.Client
	cfg          *Config
	assignScript *redis.Script
}

func newRedisSessionStore(cfg *Config) (*redisSessionStore, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	parsed, _ := url.Parse(cfg.RedisURL)
	password, _ := parsed.User.Password()
	if cfg.RedisPasswordFile != "" {
		info, err := os.Stat(cfg.RedisPasswordFile)
		if err != nil {
			return nil, fmt.Errorf("stat Redis password file: %w", err)
		}
		if info.Mode().Perm()&0o077 != 0 {
			return nil, errors.New("Redis password file permissions must be 0600 or stricter")
		}
		contents, err := os.ReadFile(cfg.RedisPasswordFile)
		if err != nil {
			return nil, fmt.Errorf("read Redis password file: %w", err)
		}
		password = strings.TrimSpace(string(contents))
		if !redisSecretPattern.MatchString(password) {
			return nil, errors.New("Redis password file must contain one URL-safe 32-256 character secret")
		}
	}
	db := 0
	if dbPath := strings.TrimPrefix(parsed.Path, "/"); dbPath != "" {
		if parsedDB, err := strconv.Atoi(dbPath); err == nil && parsedDB >= 0 {
			db = parsedDB
		}
	}
	options := &redis.Options{
		Addr:     parsed.Host,
		Username: parsed.User.Username(),
		Password: password,
		DB:       db,
	}
	if parsed.Scheme == "rediss" {
		options.TLSConfig = tlsConfig()
	}
	return &redisSessionStore{
		client:       redis.NewClient(options),
		cfg:          cfg,
		assignScript: redis.NewScript(assignSessionLua),
	}, nil
}

func (store *redisSessionStore) start(ctx context.Context, _ component.Host) error {
	if err := store.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("connect authoritative RUM session Redis: %w", err)
	}
	return nil
}

func (store *redisSessionStore) shutdown(ctx context.Context) error {
	return store.client.Close()
}

func (store *redisSessionStore) assign(ctx context.Context, input assignment) (assignedSession, error) {
	result, err := store.assignScript.Run(
		ctx,
		store.client,
		[]string{input.StateKey},
		input.ObservedAt.UnixMilli(),
		store.cfg.IdleTimeout.Milliseconds(),
		store.cfg.MaximumLength.Milliseconds(),
		input.CandidateKey,
		normalizedTrafficClass(input.TrafficClass),
		store.cfg.StateTTL.Milliseconds(),
	).Slice()
	if err != nil {
		return assignedSession{}, err
	}
	if len(result) != 3 {
		return assignedSession{}, errors.New("Redis session script returned an invalid result")
	}
	sessionKey, ok := result[0].(string)
	if !ok || len(sessionKey) != 32 {
		return assignedSession{}, errors.New("Redis session script returned an invalid session key")
	}
	traffic, ok := result[1].(string)
	if !ok {
		return assignedSession{}, errors.New("Redis session script returned an invalid traffic class")
	}
	rolled, err := redisInt64(result[2])
	if err != nil {
		return assignedSession{}, err
	}
	waitResult, err := store.client.Do(ctx, "WAITAOF", 1, 0, store.cfg.AOFTimeout.Milliseconds()).Slice()
	if err != nil {
		return assignedSession{}, fmt.Errorf("confirm Redis AOF durability: %w", err)
	}
	if len(waitResult) < 1 {
		return assignedSession{}, errors.New("Redis WAITAOF returned no local durability acknowledgement")
	}
	localAOF, err := redisInt64(waitResult[0])
	if err != nil || localAOF < 1 {
		return assignedSession{}, errors.New("Redis did not confirm local AOF durability")
	}
	return assignedSession{SessionKey: sessionKey, TrafficClass: normalizedTrafficClass(traffic), Rolled: rolled == 1}, nil
}

func stateKey(tenant, application, erasureSessionKey string) string {
	sum := sha256.Sum256([]byte(strings.Join([]string{tenant, application, erasureSessionKey}, "\x00")))
	return "ops:rum:v2:session:" + hex.EncodeToString(sum[:])
}

func redisInt64(value any) (int64, error) {
	switch typed := value.(type) {
	case int64:
		return typed, nil
	case string:
		return strconv.ParseInt(typed, 10, 64)
	case []byte:
		return strconv.ParseInt(string(typed), 10, 64)
	default:
		return 0, fmt.Errorf("unexpected Redis integer type %T", value)
	}
}

func tlsConfig() *tls.Config {
	return &tls.Config{MinVersion: tls.VersionTLS12}
}

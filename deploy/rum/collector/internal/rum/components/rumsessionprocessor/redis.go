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

	rumstate "github.com/bk-lite/rum-collector/internal/rum/state"
)

// assignSessionLua keeps the 15 minute / 4 hour boundaries and, in the same
// execution, snapshots the previous session before clearing it. ARGV is:
// 1 observed ms, 2 idle ms, 3 max length ms, 4 candidate key, 5 traffic,
// 6 state ttl ms, 7 route, 8 version, 9 user, 10 environment,
// 11 erasure user, 12 erasure session, 13 tenant, 14 application,
// 15 event delta, 16 view delta, 17 error delta, 18 ended-key prefix.
// KEYS[2] is the activity index. Its score is last_seen until
// first_seen+max-idle is earlier, so one range query also selects sessions
// that have reached the 4 hour cap. The hash field "last" stays the real
// last activity time. A roll refreshes the closed session only while that
// member is still indexed. After the maintainer removes it, the next event
// must not put the same session back.
const assignSessionLua = `
local function blank(value)
  return (not value) or value == ''
end

local function index_score(first_ms, last_ms)
  local max_due = first_ms + tonumber(ARGV[3]) - tonumber(ARGV[2])
  if max_due < last_ms then
    return max_due
  end
  return last_ms
end

local function write_snapshot(key, first_ms, last_ms, traffic_value, event_count, view_count, error_count, route_value, version_value, user_value, env_value, erasure_user_value, erasure_session_value, tenant_value, application_value)
  local snap = ARGV[18] .. key
  redis.call('HSET', snap,
    'key', key,
    'first', tostring(first_ms),
    'last', tostring(last_ms),
    'traffic', traffic_value or '',
    'events', tostring(event_count),
    'views', tostring(view_count),
    'errors', tostring(error_count),
    'route', route_value or '',
    'version', version_value or '',
    'user', user_value or '',
    'env', env_value or '',
    'erasure_user', erasure_user_value or '',
    'erasure_session', erasure_session_value or '',
    'tenant', tenant_value or '',
    'application', application_value or '')
  redis.call('PEXPIRE', snap, ARGV[6])
  redis.call('ZADD', KEYS[2], index_score(first_ms, last_ms), key)
end

local values = redis.call('HMGET', KEYS[1],
  'key', 'first', 'last', 'traffic',
  'events', 'views', 'errors',
  'route', 'version', 'user', 'env',
  'erasure_user', 'erasure_session',
  'tenant', 'application')
local session_key = values[1]
local first_seen = tonumber(values[2])
local last_seen = tonumber(values[3])
local traffic = values[4]
local events = tonumber(values[5]) or 0
local views = tonumber(values[6]) or 0
local errors = tonumber(values[7]) or 0
local route = values[8]
local version = values[9]
local user = values[10]
local env = values[11]
local erasure_user = values[12]
local erasure_session = values[13]
local tenant = values[14]
local application = values[15]
local observed = tonumber(ARGV[1])
local rolled = 0
local closed = ''

if not session_key or not first_seen or not last_seen
  or observed - last_seen >= tonumber(ARGV[2])
  or observed - first_seen >= tonumber(ARGV[3]) then
  if session_key and first_seen and last_seen then
    if redis.call('ZSCORE', KEYS[2], session_key) then
      write_snapshot(session_key, first_seen, last_seen, traffic, events, views, errors, route, version, user, env, erasure_user, erasure_session, tenant, application)
    end
    closed = session_key
  end
  session_key = ARGV[4]
  first_seen = observed
  last_seen = observed
  traffic = ARGV[5]
  events = 0
  views = 0
  errors = 0
  route = ''
  version = ''
  user = ''
  env = ''
  erasure_user = ''
  erasure_session = ''
  tenant = ''
  application = ''
  rolled = 1
else
  if observed > last_seen then
    last_seen = observed
  end
  if blank(traffic) or traffic == 'unknown' then
    traffic = ARGV[5]
  end
end

if blank(route) then route = ARGV[7] end
if blank(version) then version = ARGV[8] end
if blank(user) then user = ARGV[9] end
if blank(env) then env = ARGV[10] end
if blank(erasure_user) then erasure_user = ARGV[11] end
if blank(erasure_session) then erasure_session = ARGV[12] end
if blank(tenant) then tenant = ARGV[13] end
if blank(application) then application = ARGV[14] end
events = events + tonumber(ARGV[15])
views = views + tonumber(ARGV[16])
errors = errors + tonumber(ARGV[17])

redis.call('HSET', KEYS[1],
  'key', session_key,
  'first', tostring(first_seen),
  'last', tostring(last_seen),
  'traffic', traffic or '',
  'events', tostring(events),
  'views', tostring(views),
  'errors', tostring(errors),
  'route', route or '',
  'version', version or '',
  'user', user or '',
  'env', env or '',
  'erasure_user', erasure_user or '',
  'erasure_session', erasure_session or '',
  'tenant', tenant or '',
  'application', application or '')
redis.call('PEXPIRE', KEYS[1], ARGV[6])
write_snapshot(session_key, first_seen, last_seen, traffic, events, views, errors, route, version, user, env, erasure_user, erasure_session, tenant, application)
return {session_key, traffic or '', rolled, closed, events, views, errors}
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
	username := ""
	password := ""
	if parsed.User != nil {
		username = parsed.User.Username()
		password, _ = parsed.User.Password()
	}
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
		if len(password) < 16 || len(password) > 256 {
			return nil, errors.New("Redis password file must contain 16-256 characters")
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
		Username: username,
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
		[]string{input.StateKey, rumstate.SessionActivityIndexKey},
		input.ObservedAt.UnixMilli(),
		store.cfg.IdleTimeout.Milliseconds(),
		store.cfg.MaximumLength.Milliseconds(),
		input.CandidateKey,
		normalizedTrafficClass(input.TrafficClass),
		store.cfg.StateTTL.Milliseconds(),
		input.Route,
		input.Version,
		input.User,
		input.Environment,
		input.ErasureUserKey,
		input.ErasureSessionKey,
		input.Tenant,
		input.Application,
		input.EventDelta,
		input.ViewDelta,
		input.ErrorDelta,
		rumstate.SessionEndedKeyPrefix,
	).Slice()
	if err != nil {
		return assignedSession{}, err
	}
	if len(result) != 7 {
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
	closed, err := redisString(result[3])
	if err != nil || (closed != "" && len(closed) != 32) {
		return assignedSession{}, errors.New("Redis session script returned an invalid closed session key")
	}
	events, err := redisInt64(result[4])
	if err != nil {
		return assignedSession{}, err
	}
	views, err := redisInt64(result[5])
	if err != nil {
		return assignedSession{}, err
	}
	errorsCount, err := redisInt64(result[6])
	if err != nil {
		return assignedSession{}, err
	}
	return assignedSession{
		SessionKey:   sessionKey,
		TrafficClass: normalizedTrafficClass(traffic),
		Rolled:       rolled == 1,
		ClosedKey:    closed,
		EventCount:   events,
		ViewCount:    views,
		ErrorCount:   errorsCount,
	}, nil
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

func redisString(value any) (string, error) {
	switch typed := value.(type) {
	case nil:
		return "", nil
	case string:
		return typed, nil
	case []byte:
		return string(typed), nil
	default:
		return "", fmt.Errorf("unexpected Redis string type %T", value)
	}
}

func tlsConfig() *tls.Config {
	return &tls.Config{MinVersion: tls.VersionTLS12}
}

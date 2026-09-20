package rumreplayexporter

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"github.com/redis/go-redis/v9"
)

var (
	acquireLeaseScript = redis.NewScript(`
local now = redis.call("TIME")
local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
for i = 2, 3 do
  redis.call("ZREMRANGEBYSCORE", KEYS[i], "1", now_ms)
end
if redis.call("ZSCORE", KEYS[2], "fence") or redis.call("ZSCORE", KEYS[3], "fence") then
  return {"fenced"}
end
local fingerprint = redis.call("HGET", KEYS[1], "fingerprint")
if fingerprint and fingerprint ~= ARGV[2] then
  return {"conflict"}
end
local current_owner = redis.call("HGET", KEYS[1], "owner")
local lock_until = tonumber(redis.call("HGET", KEYS[1], "lock_until_ms") or "0")
if current_owner and lock_until > now_ms then
  return {"busy"}
end
local accepted_at = redis.call("HGET", KEYS[1], "accepted_at_unix_nano")
if not accepted_at then
  accepted_at = ARGV[3]
  redis.call("HSET", KEYS[1],
    "fingerprint", ARGV[2],
    "accepted_at_unix_nano", accepted_at)
  redis.call("PEXPIREAT", KEYS[1], ARGV[5])
end
redis.call("HSET", KEYS[1],
  "owner", ARGV[1],
  "lock_until_ms", tostring(now_ms + tonumber(ARGV[4])))
for i = 2, 3 do
  redis.call("ZADD", KEYS[i], now_ms + tonumber(ARGV[4]), "replay:" .. ARGV[1])
  redis.call("PEXPIRE", KEYS[i], tonumber(ARGV[4]) * 2)
end
return {"ok", accepted_at, redis.call("HGET", KEYS[1], "object_stored") or "0"}
`)
	renewLeaseScript = redis.NewScript(`
local now = redis.call("TIME")
local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
if redis.call("HGET", KEYS[1], "owner") == ARGV[1] and
   tonumber(redis.call("HGET", KEYS[1], "lock_until_ms") or "0") > now_ms then
  redis.call("HSET", KEYS[1], "lock_until_ms", tostring(now_ms + tonumber(ARGV[2])))
  for i = 2, 3 do
    redis.call("ZADD", KEYS[i], now_ms + tonumber(ARGV[2]), "replay:" .. ARGV[1])
  end
  return 1
end
return 0
`)
	markObjectStoredScript = redis.NewScript(`
local now = redis.call("TIME")
local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
if redis.call("HGET", KEYS[1], "owner") == ARGV[1] and
   tonumber(redis.call("HGET", KEYS[1], "lock_until_ms") or "0") > now_ms then
  redis.call("HSET", KEYS[1],
    "object_stored", "1",
    "lock_until_ms", tostring(now_ms + tonumber(ARGV[2])))
  for i = 2, 3 do
    redis.call("ZADD", KEYS[i], now_ms + tonumber(ARGV[2]), "replay:" .. ARGV[1])
  end
  return 1
end
return 0
`)
	clearObjectStoredScript = redis.NewScript(`
local now = redis.call("TIME")
local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
if redis.call("HGET", KEYS[1], "owner") == ARGV[1] and
   tonumber(redis.call("HGET", KEYS[1], "lock_until_ms") or "0") > now_ms then
  redis.call("HDEL", KEYS[1], "object_stored")
  redis.call("HSET", KEYS[1], "lock_until_ms", tostring(now_ms + tonumber(ARGV[2])))
  for i = 2, 3 do
    redis.call("ZADD", KEYS[i], now_ms + tonumber(ARGV[2]), "replay:" .. ARGV[1])
  end
  return 1
end
return 0
`)
	releaseLeaseScript = redis.NewScript(`
if redis.call("HGET", KEYS[1], "owner") == ARGV[1] then
  redis.call("HDEL", KEYS[1], "owner", "lock_until_ms")
  for i = 2, 3 do
    redis.call("ZREM", KEYS[i], "replay:" .. ARGV[1])
  end
  return 1
end
return 0
`)
)

type redisLeaseStore struct {
	client redis.UniversalClient
}

func newRedisLeaseStore(cfg *Config) (*redisLeaseStore, error) {
	options, err := redisClientOptions(cfg)
	if err != nil {
		return nil, err
	}
	return &redisLeaseStore{client: redis.NewClient(options)}, nil
}

func redisClientOptions(cfg *Config) (*redis.Options, error) {
	options, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		return nil, fmt.Errorf("parse Replay Redis URL: %w", err)
	}
	passwordFile := strings.TrimSpace(cfg.RedisPasswordFile)
	if passwordFile == "" {
		return options, nil
	}
	if options.Password != "" {
		return nil, fmt.Errorf("Replay Redis URL must not embed a password when a password file is configured")
	}
	info, err := os.Stat(passwordFile)
	if err != nil {
		return nil, fmt.Errorf("stat Replay Redis password file: %w", err)
	}
	if info.Mode().Perm()&0o077 != 0 {
		return nil, errors.New("Replay Redis password file permissions must be 0600 or stricter")
	}
	raw, err := os.ReadFile(passwordFile)
	if err != nil {
		return nil, fmt.Errorf("read Replay Redis password file: %w", err)
	}
	password := strings.TrimSpace(string(raw))
	if !redisSecretPattern.MatchString(password) {
		return nil, fmt.Errorf("Replay Redis password must contain 32-256 URL-safe characters")
	}
	options.Password = password
	return options, nil
}

func (store *redisLeaseStore) Start(ctx context.Context) error {
	if err := store.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("ping Replay lease Redis: %w", err)
	}
	return nil
}

func (store *redisLeaseStore) Shutdown(context.Context) error {
	return store.client.Close()
}

func (store *redisLeaseStore) AcquireSequence(
	ctx context.Context,
	row ReplayIndex,
) (leaseToken, leaseState, error) {
	if err := validateReplayIndex(row); err != nil {
		return leaseToken{}, leaseState{}, err
	}
	key, err := sequenceLeaseKey(row)
	if err != nil {
		return leaseToken{}, leaseState{}, err
	}
	ownerBytes := make([]byte, 32)
	if _, err := rand.Read(ownerBytes); err != nil {
		return leaseToken{}, leaseState{}, fmt.Errorf("generate Replay lease owner: %w", err)
	}
	owner := hex.EncodeToString(ownerBytes)
	fingerprint, err := replayIdentityFingerprint(row)
	if err != nil {
		return leaseToken{}, leaseState{}, err
	}
	expireAt := timeFromUnixNano(row.AcceptedAtUnixNano).Add(sequenceStateTTL).UnixMilli()
	fenceKeys := []string{
		ingress.ErasureFenceKey(row.ErasureKeyVersion, row.ErasureUserKey),
		ingress.ErasureFenceKey(row.ErasureKeyVersion, row.ErasureSessionKey),
	}
	result, err := acquireLeaseScript.Run(
		ctx,
		store.client,
		[]string{
			key,
			fenceKeys[0],
			fenceKeys[1],
		},
		owner,
		fingerprint,
		strconv.FormatUint(row.AcceptedAtUnixNano, 10),
		strconv.FormatInt(sequenceLeaseTTL.Milliseconds(), 10),
		strconv.FormatInt(expireAt, 10),
	).Slice()
	if err != nil {
		return leaseToken{}, leaseState{}, fmt.Errorf("acquire Replay lease: %w", err)
	}
	if len(result) == 0 {
		return leaseToken{}, leaseState{}, errors.New("acquire Replay lease returned an empty result")
	}
	status, _ := result[0].(string)
	switch status {
	case "fenced":
		return leaseToken{}, leaseState{}, ErrErasureFenced
	case "conflict":
		return leaseToken{}, leaseState{}, ErrChecksumConflict
	case "busy":
		return leaseToken{}, leaseState{}, ErrLeaseUnavailable
	case "ok":
		if len(result) != 3 {
			return leaseToken{}, leaseState{}, errors.New("acquire Replay lease returned an invalid result")
		}
	default:
		return leaseToken{}, leaseState{}, errors.New("acquire Replay lease returned an unknown result")
	}
	acceptedAt, err := strconv.ParseUint(redisString(result[1]), 10, 64)
	if err != nil || acceptedAt == 0 {
		return leaseToken{}, leaseState{}, errors.New("Replay lease contains an invalid accepted-at timestamp")
	}
	return leaseToken{Key: key, Owner: owner, FenceKeys: fenceKeys}, leaseState{
		AcceptedAtUnixNano: acceptedAt,
		ObjectStored:       redisString(result[2]) == "1",
	}, nil
}

func (store *redisLeaseStore) Renew(ctx context.Context, token leaseToken) error {
	if err := validateLeaseToken(token); err != nil {
		return err
	}
	renewed, err := renewLeaseScript.Run(
		ctx,
		store.client,
		append([]string{token.Key}, token.FenceKeys...),
		token.Owner,
		strconv.FormatInt(sequenceLeaseTTL.Milliseconds(), 10),
	).Int64()
	if err != nil {
		return fmt.Errorf("renew Replay lease: %w", err)
	}
	if renewed != 1 {
		return ErrLeaseLost
	}
	return nil
}

func (store *redisLeaseStore) MarkObjectStored(ctx context.Context, token leaseToken) error {
	return store.updateObjectState(ctx, markObjectStoredScript, token, "mark Replay object stored")
}

func (store *redisLeaseStore) ClearObjectStored(ctx context.Context, token leaseToken) error {
	return store.updateObjectState(ctx, clearObjectStoredScript, token, "clear Replay object state")
}

func (store *redisLeaseStore) updateObjectState(
	ctx context.Context,
	script *redis.Script,
	token leaseToken,
	operation string,
) error {
	if err := validateLeaseToken(token); err != nil {
		return err
	}
	updated, err := script.Run(
		ctx,
		store.client,
		append([]string{token.Key}, token.FenceKeys...),
		token.Owner,
		strconv.FormatInt(sequenceLeaseTTL.Milliseconds(), 10),
	).Int64()
	if err != nil {
		return fmt.Errorf("%s: %w", operation, err)
	}
	if updated != 1 {
		return ErrLeaseLost
	}
	return nil
}

func (store *redisLeaseStore) Release(ctx context.Context, token leaseToken) error {
	if err := validateLeaseToken(token); err != nil {
		return err
	}
	released, err := releaseLeaseScript.Run(
		ctx,
		store.client,
		append([]string{token.Key}, token.FenceKeys...),
		token.Owner,
	).Int64()
	if err != nil {
		return fmt.Errorf("release Replay lease: %w", err)
	}
	if released != 1 {
		return ErrLeaseLost
	}
	return nil
}

func sequenceLeaseKey(row ReplayIndex) (string, error) {
	if !carrierIDPattern.MatchString(row.TenantID) ||
		!validCarrierLabel(row.Application, 256) ||
		!carrierIDPattern.MatchString(row.SessionID) ||
		!carrierIDPattern.MatchString(row.RecordingID) {
		return "", fmt.Errorf("%w: invalid Replay sequence lease identity", ErrInvalidCarrier)
	}
	tenantHash := sha256.Sum256([]byte(row.TenantID))
	logicalHash := sha256.Sum256([]byte(strings.Join([]string{
		"weops.rum.replay.sequence.v2",
		row.TenantID,
		row.Application,
		row.SessionID,
		row.RecordingID,
		strconv.FormatUint(uint64(row.Sequence), 10),
	}, "\x00")))
	return "ops:rum:v2:replay:lease:" + hex.EncodeToString(tenantHash[:]) + ":" + hex.EncodeToString(logicalHash[:]), nil
}

func replayIdentityFingerprint(row ReplayIndex) (string, error) {
	row.AcceptedAtUnixNano = 0
	row.Status = ""
	row.Version = 0
	encoded, err := json.Marshal(row)
	if err != nil {
		return "", fmt.Errorf("encode Replay lease identity: %w", err)
	}
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:]), nil
}

func redisString(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case []byte:
		return string(typed)
	default:
		return ""
	}
}

func timeFromUnixNano(value uint64) time.Time {
	return time.Unix(0, int64(value)).UTC()
}

func validateLeaseToken(token leaseToken) error {
	if !strings.HasPrefix(token.Key, "ops:rum:v2:replay:lease:") ||
		len(token.Owner) != 64 ||
		len(token.FenceKeys) != 2 {
		return fmt.Errorf("%w: invalid Replay lease token", ErrInvalidCarrier)
	}
	for _, key := range token.FenceKeys {
		if !strings.HasPrefix(key, "ops:rum:v2:erasure:fence:") {
			return fmt.Errorf("%w: invalid Replay fence lease token", ErrInvalidCarrier)
		}
	}
	if _, err := hex.DecodeString(token.Owner); err != nil {
		return fmt.Errorf("%w: invalid Replay lease owner", ErrInvalidCarrier)
	}
	return nil
}

package ingress

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

const defaultFenceLeaseTTL = 30 * time.Second

var (
	ErrErasureFenced = errors.New("RUM identity is fenced for erasure")

	acquireFenceLeaseScript = redis.NewScript(`
local now_ms = tonumber(ARGV[2])
for i = 1, #KEYS do
  redis.call("ZREMRANGEBYSCORE", KEYS[i], "1", now_ms)
  if redis.call("ZSCORE", KEYS[i], "fence") then
    return 0
  end
end
for i = 1, #KEYS do
  redis.call("ZADD", KEYS[i], ARGV[3], ARGV[1])
  redis.call("PEXPIRE", KEYS[i], ARGV[4])
end
return 1
`)
	releaseFenceLeaseScript = redis.NewScript(`
for i = 1, #KEYS do
  redis.call("ZREM", KEYS[i], ARGV[1])
end
return 1
`)
)

type LeaseHandle interface {
	Release(context.Context) error
}

type LeaseManager interface {
	Start(context.Context) error
	Shutdown(context.Context) error
	Acquire(context.Context, []FenceIdentity) (LeaseHandle, error)
}

type redisFenceLeases struct {
	client *redis.Client
	ttl    time.Duration
	now    func() time.Time
}

type redisFenceLease struct {
	manager *redisFenceLeases
	keys    []string
	token   string
}

func NewLeaseManager(cfg Config) (LeaseManager, error) {
	options, err := redisOptions(cfg)
	if err != nil {
		return nil, err
	}
	return &redisFenceLeases{
		client: redis.NewClient(options),
		ttl:    defaultFenceLeaseTTL,
		now:    time.Now,
	}, nil
}

func (manager *redisFenceLeases) Start(ctx context.Context) error {
	if err := manager.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("%w: %v", ErrUnavailable, err)
	}
	return nil
}

func (manager *redisFenceLeases) Shutdown(context.Context) error {
	return manager.client.Close()
}

func (manager *redisFenceLeases) Acquire(
	ctx context.Context,
	identities []FenceIdentity,
) (LeaseHandle, error) {
	keys, err := fenceKeys(identities)
	if err != nil {
		return nil, err
	}
	if len(keys) == 0 {
		return noopLease{}, nil
	}
	tokenBytes := make([]byte, 32)
	if _, err := rand.Read(tokenBytes); err != nil {
		return nil, fmt.Errorf("generate erasure lease token: %w", err)
	}
	token := "gateway:" + hex.EncodeToString(tokenBytes)
	now := manager.now().UTC()
	result, err := acquireFenceLeaseScript.Run(
		ctx,
		manager.client,
		keys,
		token,
		strconv.FormatInt(now.UnixMilli(), 10),
		strconv.FormatInt(now.Add(manager.ttl).UnixMilli(), 10),
		strconv.FormatInt((2*manager.ttl).Milliseconds(), 10),
	).Int64()
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrUnavailable, err)
	}
	if result != 1 {
		return nil, ErrErasureFenced
	}
	return &redisFenceLease{manager: manager, keys: keys, token: token}, nil
}

func (lease *redisFenceLease) Release(ctx context.Context) error {
	if lease == nil || lease.manager == nil || len(lease.keys) == 0 || lease.token == "" {
		return errors.New("invalid erasure lease")
	}
	if err := releaseFenceLeaseScript.Run(
		ctx,
		lease.manager.client,
		lease.keys,
		lease.token,
	).Err(); err != nil {
		return fmt.Errorf("%w: %v", ErrUnavailable, err)
	}
	return nil
}

type noopLease struct{}

func (noopLease) Release(context.Context) error { return nil }

func fenceKeys(identities []FenceIdentity) ([]string, error) {
	unique := make(map[string]struct{}, len(identities))
	for _, identity := range identities {
		if err := ValidateFenceIdentity(identity); err != nil {
			return nil, errors.New("invalid erasure lease identity")
		}
		unique[ErasureFenceKey(identity.Version, identity.Digest)] = struct{}{}
	}
	keys := make([]string, 0, len(unique))
	for key := range unique {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys, nil
}

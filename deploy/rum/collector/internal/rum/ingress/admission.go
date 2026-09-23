package ingress

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

const admissionScript = `
local app = KEYS[1]
if redis.call("EXISTS", app) == 0 then
  return {"reject", "application_not_found"}
end
local tenant = redis.call("HGET", app, "tenant_id")
if not tenant or tenant ~= ARGV[6] then
  return {"error", "invalid_application_authority"}
end
if redis.call("HGET", app, "enabled") ~= "1" then
  return {"reject", "application_disabled"}
end
if redis.call("SISMEMBER", KEYS[2], ARGV[1]) ~= 1 then
  return {"reject", "browser_key"}
end
if redis.call("SISMEMBER", KEYS[3], ARGV[2]) ~= 1 then
  return {"reject", "origin"}
end
for i = 5, #KEYS do
  if redis.call("ZSCORE", KEYS[i], "fence") then
    return {"reject", "erasure_fence"}
  end
end

local requestLimit = tonumber(redis.call("HGET", app, "requests_per_minute"))
local compressedLimit = tonumber(redis.call("HGET", app, "compressed_bytes_per_minute"))
local decompressedLimit = tonumber(redis.call("HGET", app, "decompressed_bytes_per_minute"))
local eventLimit = tonumber(redis.call("HGET", app, "events_per_minute"))
local revision = tonumber(redis.call("HGET", app, "revision"))
if not requestLimit or not compressedLimit or not decompressedLimit or not eventLimit or not revision or not tenant then
  return {"error", "invalid_application_state"}
end

local requests = tonumber(redis.call("HGET", KEYS[4], "requests") or "0")
local compressed = tonumber(redis.call("HGET", KEYS[4], "compressed_bytes") or "0")
local decompressed = tonumber(redis.call("HGET", KEYS[4], "decompressed_bytes") or "0")
local events = tonumber(redis.call("HGET", KEYS[4], "events") or "0")
local nextRequests = requests + 1
local nextCompressed = compressed + tonumber(ARGV[3])
local nextDecompressed = decompressed + tonumber(ARGV[4])
local nextEvents = events + tonumber(ARGV[5])
if nextRequests > requestLimit or nextCompressed > compressedLimit or nextDecompressed > decompressedLimit or nextEvents > eventLimit then
  return {"reject", "budget"}
end

redis.call("HSET", KEYS[4],
  "requests", nextRequests,
  "compressed_bytes", nextCompressed,
  "decompressed_bytes", nextDecompressed,
  "events", nextEvents)
redis.call("EXPIRE", KEYS[4], 120)
redis.call("HSET", KEYS[1], "last_accepted_at", ARGV[7])
return {"allow", tenant, tostring(revision)}
`

type Config struct {
	RedisURL          string
	RedisPasswordFile string
	Now               func() time.Time
}

type Admission struct {
	client *redis.Client
	now    func() time.Time
}

// NewRedisClient opens a Redis client using the RUM admission store URL rules.
func NewRedisClient(cfg Config) (*redis.Client, error) {
	options, err := redisOptions(cfg)
	if err != nil {
		return nil, err
	}
	return redis.NewClient(options), nil
}

func New(cfg Config) (*Admission, error) {
	client, err := NewRedisClient(cfg)
	if err != nil {
		return nil, err
	}
	now := cfg.Now
	if now == nil {
		now = time.Now
	}
	return &Admission{client: client, now: now}, nil
}

func ValidateConfig(cfg Config) error {
	_, err := redisOptions(cfg)
	return err
}

func redisOptions(cfg Config) (*redis.Options, error) {
	parsed, err := url.Parse(strings.TrimSpace(cfg.RedisURL))
	if err != nil || parsed.Host == "" || (parsed.Scheme != "redis" && parsed.Scheme != "rediss") {
		return nil, errors.New("redis_url must be a redis:// or rediss:// URL")
	}
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, errors.New("redis_url must not contain query or fragment data")
	}
	if parsed.User == nil || parsed.User.Username() != "rum-admission" {
		return nil, errors.New("RUM admission Redis URL must use the rum-admission ACL identity")
	}
	options, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		return nil, fmt.Errorf("parse RUM admission Redis URL: %w", err)
	}
	passwordFile := strings.TrimSpace(cfg.RedisPasswordFile)
	if passwordFile == "" {
		if options.Password == "" {
			return nil, errors.New("RUM admission Redis requires a password or redis_password_file")
		}
		return options, nil
	}
	if options.Password != "" {
		return nil, errors.New("RUM admission Redis URL must not embed a password when a password file is configured")
	}
	info, err := os.Stat(passwordFile)
	if err != nil {
		return nil, fmt.Errorf("stat RUM admission Redis password file: %w", err)
	}
	if info.Mode().Perm()&0o077 != 0 {
		return nil, errors.New("RUM admission Redis password file permissions must be 0600 or stricter")
	}
	raw, err := os.ReadFile(passwordFile)
	if err != nil {
		return nil, fmt.Errorf("read RUM admission Redis password file: %w", err)
	}
	password := strings.TrimSpace(string(raw))
	if len(password) < 16 || len(password) > 256 {
		return nil, errors.New("RUM admission Redis password file must contain 16-256 characters")
	}
	options.Password = password
	return options, nil
}

func (admission *Admission) Start(ctx context.Context) error {
	if err := admission.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("%w: %v", ErrUnavailable, err)
	}
	return nil
}

func (admission *Admission) Shutdown(context.Context) error {
	return admission.client.Close()
}

func (admission *Admission) Admit(ctx context.Context, request Request) (Decision, error) {
	origin, err := ParseOrigin(request.Origin)
	if err != nil {
		return Decision{Reason: RejectOrigin}, nil
	}
	if !stableIDPattern.MatchString(request.Application) ||
		!stableIDPattern.MatchString(request.AuthorityTenantID) ||
		strings.TrimSpace(request.BrowserKey) == "" ||
		request.CompressedBytes < 0 ||
		request.DecompressedBytes < 0 ||
		request.EventCount < 0 {
		return Decision{}, errors.New("invalid RUM admission request")
	}

	now := admission.now().UTC()
	keys := []string{
		ApplicationKey(request.Application),
		ApplicationKeysKey(request.Application),
		ApplicationOriginsKey(request.Application),
		RateKey(request.Application, now),
	}
	for _, fence := range append(append([]FenceIdentity{}, request.UserFences...), request.SessionFences...) {
		if err := ValidateFenceIdentity(fence); err != nil {
			return Decision{}, err
		}
		keys = append(keys, ErasureFenceKey(fence.Version, fence.Digest))
	}
	result, err := admission.client.Eval(
		ctx,
		admissionScript,
		keys,
		KeyDigest(request.BrowserKey),
		origin,
		request.CompressedBytes,
		request.DecompressedBytes,
		request.EventCount,
		request.AuthorityTenantID,
		now.Unix(),
	).Slice()
	if err != nil {
		return Decision{}, fmt.Errorf("%w: %v", ErrUnavailable, err)
	}
	if len(result) < 2 {
		return Decision{}, fmt.Errorf("%w: invalid admission response", ErrUnavailable)
	}
	status := fmt.Sprint(result[0])
	value := fmt.Sprint(result[1])
	switch status {
	case "allow":
		if len(result) != 3 {
			return Decision{}, fmt.Errorf("%w: invalid allow response", ErrUnavailable)
		}
		var revision int64
		if _, err := fmt.Sscan(fmt.Sprint(result[2]), &revision); err != nil {
			return Decision{}, fmt.Errorf("%w: invalid application revision", ErrUnavailable)
		}
		return Decision{
			Allowed:  true,
			TenantID: value,
			Revision: revision,
		}, nil
	case "reject":
		decision := Decision{Reason: RejectReason(value)}
		if decision.Reason == RejectBudget {
			remaining := time.Minute - time.Duration(now.UnixNano()%int64(time.Minute))
			if remaining <= 0 {
				remaining = time.Minute
			}
			decision.RetryAfter = remaining
		}
		return decision, nil
	default:
		return Decision{}, fmt.Errorf("%w: %s", ErrUnavailable, value)
	}
}

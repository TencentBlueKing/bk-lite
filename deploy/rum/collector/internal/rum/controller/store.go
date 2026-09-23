package controller

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/bk-lite/rum-collector/internal/rum/authority"
	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"github.com/bk-lite/rum-collector/internal/rum/state"
	"github.com/redis/go-redis/v9"
)

const (
	ErasureStreamKey      = state.ErasureStreamKey
	ReconcileStreamKey    = state.ReconcileStreamKey
	ControlAuditStreamKey = state.ControlAuditStreamKey
	OperationKeyPrefix    = state.OperationKeyPrefix
	CommandKeyPrefix      = state.CommandKeyPrefix
	defaultOperationTTL   = 30 * 24 * time.Hour
	defaultAOFTimeout     = 5 * time.Second
)

const applyApplicationScript = `
local command = KEYS[1]
if redis.call("EXISTS", command) == 1 then
  if redis.call("HGET", command, "fingerprint") ~= ARGV[1] then
    return {"idempotency_conflict"}
  end
  return {"cached", redis.call("HGET", command, "result")}
end

local state = cjson.decode(ARGV[5])
local current = tonumber(redis.call("HGET", KEYS[2], "revision") or "0")
local expected = tonumber(ARGV[3])
if current ~= expected then
  return {"revision_conflict", tostring(current)}
end
local existingOrg = redis.call("HGET", KEYS[2], "org_id")
if existingOrg and existingOrg ~= state.org_id then
  return {"org_conflict", existingOrg}
end

redis.call("HSET", KEYS[2],
  "enabled", state.enabled and "1" or "0",
  "revision", tostring(state.revision),
  "tenant_id", state.tenant_id,
  "org_id", state.org_id,
  "requests_per_minute", tostring(state.requests_per_minute),
  "compressed_bytes_per_minute", tostring(state.compressed_bytes_per_minute),
  "decompressed_bytes_per_minute", tostring(state.decompressed_bytes_per_minute),
  "events_per_minute", tostring(state.events_per_minute))
redis.call("DEL", KEYS[3])
for _, digest in ipairs(state.browser_key_digests) do
  redis.call("SADD", KEYS[3], digest)
end
redis.call("DEL", KEYS[4])
for _, origin in ipairs(state.origins) do
  redis.call("SADD", KEYS[4], origin)
end
redis.call("DEL", KEYS[6])
for _, key in ipairs(state.browser_keys) do
  redis.call("SADD", KEYS[6], key)
end
redis.call("HSET", command, "fingerprint", ARGV[1], "result", ARGV[4])
redis.call("EXPIRE", command, tonumber(ARGV[2]))
redis.call("XADD", KEYS[5], "*",
  "request_id", ARGV[6],
  "actor", ARGV[7],
  "action", ARGV[8],
  "application", state.name,
  "revision", tostring(state.revision),
  "created_at", ARGV[9])
return {"ok", ARGV[4]}
`

const submitOperationScript = `
local command = KEYS[1]
if redis.call("EXISTS", command) == 1 then
  if redis.call("HGET", command, "fingerprint") ~= ARGV[1] then
    return {"idempotency_conflict"}
  end
  return {"cached", redis.call("HGET", command, "result")}
end
local current = tonumber(redis.call("HGET", KEYS[2], "revision") or "0")
if current == 0 then
  return {"not_found"}
end
if current ~= tonumber(ARGV[3]) then
  return {"revision_conflict", tostring(current)}
end

redis.call("HSET", KEYS[3],
  "operation_id", ARGV[5],
  "type", ARGV[6],
  "status", "pending",
  "application", ARGV[7],
  "actor", ARGV[8],
  "created_at", ARGV[9],
  "updated_at", ARGV[9])
redis.call("EXPIRE", KEYS[3], tonumber(ARGV[10]))
if ARGV[6] == "erasure" then
  for i = 6, #KEYS do
    redis.call("ZADD", KEYS[i], 0, "fence")
    redis.call("EXPIRE", KEYS[i], tonumber(ARGV[11]))
  end
end
redis.call("XADD", KEYS[4], "*",
  "operation_id", ARGV[5],
  "type", ARGV[6],
  "application", ARGV[7],
  "actor", ARGV[8],
  "identities", ARGV[12],
  "created_at", ARGV[9])
redis.call("HSET", command, "fingerprint", ARGV[1], "result", ARGV[4])
redis.call("EXPIRE", command, tonumber(ARGV[2]))
return {"ok", ARGV[4]}
`

type StoreConfig struct {
	RedisURL            string
	RedisPasswordFile   string
	CommandTTL          time.Duration
	OperationTTL        time.Duration
	FenceTTL            time.Duration
	AOFTimeout          time.Duration
	CurrentHMACSecret   string
	CurrentHMACVersion  string
	PreviousHMACSecret  string
	PreviousHMACVersion string
	Now                 func() time.Time
	NewOperationID      func() string
}

type Store struct {
	client              *redis.Client
	commandTTL          time.Duration
	operationTTL        time.Duration
	fenceTTL            time.Duration
	aofTimeout          time.Duration
	currentHMACSecret   string
	currentHMACVersion  string
	previousHMACSecret  string
	previousHMACVersion string
	now                 func() time.Time
	newOperationID      func() string
	waitDurable         func(context.Context) error
}

type commandResult struct {
	Revision    int64           `json:"revision,omitempty"`
	OperationID string          `json:"operationId,omitempty"`
	Data        json.RawMessage `json:"data,omitempty"`
}

type storeError struct {
	code   ErrorCode
	fields map[string]string
	err    error
}

func (failure *storeError) Error() string {
	if failure.err != nil {
		return failure.err.Error()
	}
	return string(failure.code)
}

func NewStore(cfg StoreConfig) (*Store, error) {
	if len(cfg.CurrentHMACSecret) < 32 {
		return nil, errors.New("current identity HMAC secret must contain at least 32 bytes")
	}
	if err := ingress.ValidateFenceIdentity(ingress.FenceIdentity{
		Version: cfg.CurrentHMACVersion,
		Digest:  strings.Repeat("0", 64),
	}); err != nil {
		return nil, errors.New("current identity HMAC version is invalid")
	}
	if cfg.PreviousHMACSecret != "" && len(cfg.PreviousHMACSecret) < 32 {
		return nil, errors.New("previous identity HMAC secret must contain at least 32 bytes")
	}
	if (cfg.PreviousHMACSecret == "") != (cfg.PreviousHMACVersion == "") {
		return nil, errors.New("previous identity HMAC secret and version must be configured together")
	}
	if cfg.PreviousHMACVersion != "" {
		if err := ingress.ValidateFenceIdentity(ingress.FenceIdentity{
			Version: cfg.PreviousHMACVersion,
			Digest:  strings.Repeat("0", 64),
		}); err != nil || cfg.PreviousHMACVersion == cfg.CurrentHMACVersion {
			return nil, errors.New("previous identity HMAC version must be valid and distinct")
		}
	}
	options, err := controlRedisOptions(cfg.RedisURL, cfg.RedisPasswordFile)
	if err != nil {
		return nil, err
	}
	return newStoreWithClient(redis.NewClient(options), cfg), nil
}

func newStoreWithClient(client *redis.Client, cfg StoreConfig) *Store {
	if cfg.CommandTTL <= 0 {
		cfg.CommandTTL = 24 * time.Hour
	}
	if cfg.OperationTTL <= 0 {
		cfg.OperationTTL = defaultOperationTTL
	}
	if cfg.FenceTTL <= 0 {
		cfg.FenceTTL = 17 * 24 * time.Hour
	}
	if cfg.AOFTimeout <= 0 {
		cfg.AOFTimeout = defaultAOFTimeout
	}
	if cfg.Now == nil {
		cfg.Now = time.Now
	}
	if cfg.NewOperationID == nil {
		cfg.NewOperationID = uuid.NewString
	}
	store := &Store{
		client:              client,
		commandTTL:          cfg.CommandTTL,
		operationTTL:        cfg.OperationTTL,
		fenceTTL:            cfg.FenceTTL,
		aofTimeout:          cfg.AOFTimeout,
		currentHMACSecret:   cfg.CurrentHMACSecret,
		currentHMACVersion:  cfg.CurrentHMACVersion,
		previousHMACSecret:  cfg.PreviousHMACSecret,
		previousHMACVersion: cfg.PreviousHMACVersion,
		now:                 cfg.Now,
		newOperationID:      cfg.NewOperationID,
	}
	store.waitDurable = store.waitAOF
	return store
}

func (store *Store) Start(ctx context.Context) error {
	if err := store.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("connect RUM controller Redis: %w", err)
	}
	return nil
}

func (store *Store) Close() error {
	return store.client.Close()
}

func (store *Store) ApplyApplication(
	ctx context.Context,
	subject string,
	request RequestEnvelope,
	application ingress.Application,
) (commandResult, error) {
	if request.ExpectedRevision == nil {
		return commandResult{}, &storeError{code: ErrorInvalidArgument, err: errors.New("expectedRevision is required")}
	}
	state, err := json.Marshal(applicationRedisState{
		Name:                       application.Name,
		Enabled:                    application.Enabled,
		Revision:                   application.Revision,
		TenantID:                   application.TenantID,
		OrgID:                      application.OrgID,
		RequestsPerMinute:          application.RequestsPerMinute,
		CompressedBytesPerMinute:   application.CompressedBytesPerMinute,
		DecompressedBytesPerMinute: application.DecompressedBytesPerMinute,
		EventsPerMinute:            application.EventsPerMinute,
		BrowserKeys:                application.BrowserKeys,
		BrowserKeyDigests:          application.BrowserKeyDigests,
		Origins:                    application.Origins,
	})
	if err != nil {
		return commandResult{}, err
	}
	view := applicationView(application)
	data, err := json.Marshal(view)
	if err != nil {
		return commandResult{}, err
	}
	result := commandResult{Revision: application.Revision, Data: data}
	resultJSON, err := json.Marshal(result)
	if err != nil {
		return commandResult{}, err
	}
	values, err := store.client.Eval(
		ctx,
		applyApplicationScript,
		[]string{
			CommandKeyPrefix + request.IdempotencyKey,
			ingress.ApplicationKey(application.Name),
			ingress.ApplicationKeysKey(application.Name),
			ingress.ApplicationOriginsKey(application.Name),
			ControlAuditStreamKey,
			ingress.ApplicationKeyMaterialKey(application.Name),
		},
		Fingerprint(subject, request),
		int64(store.commandTTL/time.Second),
		*request.ExpectedRevision,
		string(resultJSON),
		string(state),
		request.RequestID,
		request.Actor,
		subject,
		store.now().UTC().Format(time.RFC3339Nano),
	).Slice()
	if err != nil {
		return commandResult{}, &storeError{code: ErrorUnavailable, err: err}
	}
	resolved, err := parseMutationResult(values)
	if err != nil {
		return commandResult{}, err
	}
	if err := store.waitDurable(ctx); err != nil {
		return commandResult{}, &storeError{code: ErrorUnavailable, err: err}
	}
	return resolved, nil
}

func (store *Store) GetApplication(ctx context.Context, name string) (ingress.Application, error) {
	values, err := store.client.HGetAll(ctx, ingress.ApplicationKey(name)).Result()
	if err != nil {
		return ingress.Application{}, &storeError{code: ErrorUnavailable, err: err}
	}
	if len(values) == 0 {
		return ingress.Application{}, &storeError{code: ErrorNotFound}
	}
	keys, err := store.client.SMembers(ctx, ingress.ApplicationKeysKey(name)).Result()
	if err != nil {
		return ingress.Application{}, &storeError{code: ErrorUnavailable, err: err}
	}
	keyMaterial, err := store.client.SMembers(ctx, ingress.ApplicationKeyMaterialKey(name)).Result()
	if err != nil {
		return ingress.Application{}, &storeError{code: ErrorUnavailable, err: err}
	}
	origins, err := store.client.SMembers(ctx, ingress.ApplicationOriginsKey(name)).Result()
	if err != nil {
		return ingress.Application{}, &storeError{code: ErrorUnavailable, err: err}
	}
	sort.Strings(keys)
	sort.Strings(keyMaterial)
	sort.Strings(origins)
	application := ingress.Application{
		Name:                       name,
		TenantID:                   values["tenant_id"],
		OrgID:                      values["org_id"],
		Enabled:                    values["enabled"] == "1",
		Revision:                   parseInt64(values["revision"]),
		RequestsPerMinute:          parseInt64(values["requests_per_minute"]),
		CompressedBytesPerMinute:   parseInt64(values["compressed_bytes_per_minute"]),
		DecompressedBytesPerMinute: parseInt64(values["decompressed_bytes_per_minute"]),
		EventsPerMinute:            parseInt64(values["events_per_minute"]),
		BrowserKeys:                keyMaterial,
		BrowserKeyDigests:          keys,
		Origins:                    origins,
		LastAcceptedAt:             parseInt64(values["last_accepted_at"]),
		LastStoredAt:               parseInt64(values["last_stored_at"]),
	}
	if err := ingress.ValidateApplication(application); err != nil {
		return ingress.Application{}, &storeError{code: ErrorInternal, err: fmt.Errorf("invalid application state: %w", err)}
	}
	return application, nil
}

func (store *Store) List(ctx context.Context) ([]ingress.Application, error) {
	applications := make([]ingress.Application, 0)
	var cursor uint64
	for {
		keys, next, err := store.client.Scan(ctx, cursor, ingress.KeyPrefix+"app:*", 200).Result()
		if err != nil {
			return nil, &storeError{code: ErrorUnavailable, err: err}
		}
		for _, key := range keys {
			name := strings.TrimPrefix(key, ingress.KeyPrefix+"app:")
			if name == "" || name == key {
				continue
			}
			kind, err := store.client.Type(ctx, key).Result()
			if err != nil {
				return nil, &storeError{code: ErrorUnavailable, err: err}
			}
			if kind != "hash" {
				continue
			}
			application, err := store.GetApplication(ctx, name)
			if err != nil {
				continue
			}
			applications = append(applications, application)
		}
		cursor = next
		if cursor == 0 {
			break
		}
	}
	sort.Slice(applications, func(i, j int) bool { return applications[i].Name < applications[j].Name })
	return applications, nil
}

func (store *Store) ResolveIdempotent(
	ctx context.Context,
	subject string,
	request RequestEnvelope,
) (commandResult, bool, error) {
	values, err := store.client.HGetAll(ctx, CommandKeyPrefix+request.IdempotencyKey).Result()
	if err != nil {
		return commandResult{}, false, &storeError{code: ErrorUnavailable, err: err}
	}
	if len(values) == 0 {
		return commandResult{}, false, nil
	}
	if values["fingerprint"] != Fingerprint(subject, request) {
		return commandResult{}, true, &storeError{code: ErrorIdempotencyConflict}
	}
	var result commandResult
	if err := json.Unmarshal([]byte(values["result"]), &result); err != nil {
		return commandResult{}, true, &storeError{code: ErrorInternal, err: errors.New("cached command result is invalid")}
	}
	if err := store.waitDurable(ctx); err != nil {
		return commandResult{}, true, &storeError{code: ErrorUnavailable, err: err}
	}
	return result, true, nil
}

func (store *Store) SubmitOperation(
	ctx context.Context,
	subject string,
	request RequestEnvelope,
	operationType string,
	application ingress.Application,
	identities []derivedIdentity,
) (commandResult, error) {
	if request.ExpectedRevision == nil {
		return commandResult{}, &storeError{code: ErrorInvalidArgument, err: errors.New("expectedRevision is required")}
	}
	operationID := store.newOperationID()
	now := store.now().UTC().Format(time.RFC3339Nano)
	operation := OperationView{
		OperationID: operationID,
		Type:        operationType,
		Status:      "pending",
		Application: application.Name,
		Actor:       request.Actor,
		CreatedAt:   now,
		UpdatedAt:   now,
	}
	data, err := json.Marshal(operation)
	if err != nil {
		return commandResult{}, err
	}
	result := commandResult{OperationID: operationID, Data: data}
	resultJSON, err := json.Marshal(result)
	if err != nil {
		return commandResult{}, err
	}
	identityJSON, err := json.Marshal(identities)
	if err != nil {
		return commandResult{}, err
	}
	streamKey := ReconcileStreamKey
	if operationType == "erasure" {
		streamKey = ErasureStreamKey
	}
	keys := []string{
		CommandKeyPrefix + request.IdempotencyKey,
		ingress.ApplicationKey(application.Name),
		OperationKeyPrefix + operationID,
		streamKey,
		"ops:rum:v2:operations:reserved",
	}
	if operationType == "erasure" {
		for _, identity := range identities {
			keys = append(keys, ingress.ErasureFenceKey(identity.Version, identity.Digest))
		}
	}
	values, err := store.client.Eval(
		ctx,
		submitOperationScript,
		keys,
		Fingerprint(subject, request),
		int64(store.commandTTL/time.Second),
		*request.ExpectedRevision,
		string(resultJSON),
		operationID,
		operationType,
		application.Name,
		request.Actor,
		now,
		int64(store.operationTTL/time.Second),
		int64(store.fenceTTL/time.Second),
		string(identityJSON),
	).Slice()
	if err != nil {
		return commandResult{}, &storeError{code: ErrorUnavailable, err: err}
	}
	resolved, err := parseMutationResult(values)
	if err != nil {
		return commandResult{}, err
	}
	if err := store.waitDurable(ctx); err != nil {
		return commandResult{}, &storeError{code: ErrorUnavailable, err: err}
	}
	return resolved, nil
}

func (store *Store) DeriveIdentities(application ingress.Application, identities []ErasureIdentity) []derivedIdentity {
	var derived []derivedIdentity
	for _, identity := range identities {
		for _, secret := range []struct {
			version string
			value   string
		}{
			{version: store.currentHMACVersion, value: store.currentHMACSecret},
			{version: store.previousHMACVersion, value: store.previousHMACSecret},
		} {
			if secret.value == "" {
				continue
			}
			digest := authority.DeriveIdentityKey(
				secret.value,
				identity.Kind,
				application.TenantID,
				identity.Value,
			)
			if digest != "" {
				derived = append(derived, derivedIdentity{
					Kind:    identity.Kind,
					Version: secret.version,
					Digest:  digest,
				})
			}
		}
	}
	return derived
}

func (store *Store) GetOperation(ctx context.Context, operationID string) (OperationView, error) {
	values, err := store.client.HGetAll(ctx, OperationKeyPrefix+operationID).Result()
	if err != nil {
		return OperationView{}, &storeError{code: ErrorUnavailable, err: err}
	}
	if len(values) == 0 {
		return OperationView{}, &storeError{code: ErrorNotFound}
	}
	return OperationView{
		OperationID: values["operation_id"],
		Type:        values["type"],
		Status:      values["status"],
		Application: values["application"],
		Actor:       values["actor"],
		CreatedAt:   values["created_at"],
		UpdatedAt:   values["updated_at"],
		Error:       values["error"],
	}, nil
}

func (store *Store) Ping(ctx context.Context) error {
	return store.client.Ping(ctx).Err()
}

func (store *Store) waitAOF(ctx context.Context) error {
	result, err := store.client.Do(ctx, "WAITAOF", 1, 0, store.aofTimeout.Milliseconds()).Slice()
	if err != nil {
		return fmt.Errorf("Redis WAITAOF: %w", err)
	}
	if len(result) == 0 || parseAnyInt64(result[0]) < 1 {
		return errors.New("Redis WAITAOF returned no local durability acknowledgement")
	}
	return nil
}

func parseMutationResult(values []any) (commandResult, error) {
	if len(values) == 0 {
		return commandResult{}, &storeError{code: ErrorInternal, err: errors.New("empty Redis command response")}
	}
	switch fmt.Sprint(values[0]) {
	case "ok", "cached":
		if len(values) != 2 {
			return commandResult{}, &storeError{code: ErrorInternal, err: errors.New("invalid Redis command result")}
		}
		var result commandResult
		if err := json.Unmarshal([]byte(fmt.Sprint(values[1])), &result); err != nil {
			return commandResult{}, &storeError{code: ErrorInternal, err: err}
		}
		return result, nil
	case "idempotency_conflict":
		return commandResult{}, &storeError{code: ErrorIdempotencyConflict}
	case "revision_conflict":
		actual := "0"
		if len(values) > 1 {
			actual = fmt.Sprint(values[1])
		}
		return commandResult{}, &storeError{
			code:   ErrorRevisionConflict,
			fields: map[string]string{"actualRevision": actual},
		}
	case "org_conflict":
		existing := ""
		if len(values) > 1 {
			existing = fmt.Sprint(values[1])
		}
		return commandResult{}, &storeError{
			code:   ErrorOrgConflict,
			fields: map[string]string{"existingOrg": existing},
		}
	case "not_found":
		return commandResult{}, &storeError{code: ErrorNotFound}
	default:
		return commandResult{}, &storeError{code: ErrorInternal, err: fmt.Errorf("unknown Redis command result %q", values[0])}
	}
}

type applicationRedisState struct {
	Name                       string   `json:"name"`
	Enabled                    bool     `json:"enabled"`
	Revision                   int64    `json:"revision"`
	TenantID                   string   `json:"tenant_id"`
	OrgID                      string   `json:"org_id"`
	RequestsPerMinute          int64    `json:"requests_per_minute"`
	CompressedBytesPerMinute   int64    `json:"compressed_bytes_per_minute"`
	DecompressedBytesPerMinute int64    `json:"decompressed_bytes_per_minute"`
	EventsPerMinute            int64    `json:"events_per_minute"`
	BrowserKeys                []string `json:"browser_keys"`
	BrowserKeyDigests          []string `json:"browser_key_digests"`
	Origins                    []string `json:"origins"`
}

type derivedIdentity struct {
	Kind    string `json:"kind"`
	Version string `json:"version"`
	Digest  string `json:"digest"`
}

func applicationView(application ingress.Application) ApplicationView {
	return ApplicationView{
		Application: application.Name,
		TenantID:    application.TenantID,
		Enabled:     application.Enabled,
		Revision:    application.Revision,
		// Use []string{} (not nil) so empty slices JSON-encode as [] never null.
		BrowserKeys:       append([]string{}, application.BrowserKeys...),
		BrowserKeyDigests: append([]string{}, application.BrowserKeyDigests...),
		Origins:           append([]string{}, application.Origins...),
		Budgets: Budgets{
			RequestsPerMinute:          application.RequestsPerMinute,
			CompressedBytesPerMinute:   application.CompressedBytesPerMinute,
			DecompressedBytesPerMinute: application.DecompressedBytesPerMinute,
			EventsPerMinute:            application.EventsPerMinute,
		},
		LastAcceptedAt: application.LastAcceptedAt,
		LastStoredAt:   application.LastStoredAt,
	}
}

func parseInt64(value string) int64 {
	parsed, _ := strconv.ParseInt(value, 10, 64)
	return parsed
}

func parseAnyInt64(value any) int64 {
	parsed, _ := strconv.ParseInt(fmt.Sprint(value), 10, 64)
	return parsed
}

func controlRedisOptions(redisURL, passwordFile string) (*redis.Options, error) {
	parsed, err := url.Parse(strings.TrimSpace(redisURL))
	if err != nil || parsed.Host == "" || (parsed.Scheme != "redis" && parsed.Scheme != "rediss") {
		return nil, errors.New("redis_url must be a redis:// or rediss:// URL")
	}
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, errors.New("redis_url must not contain query or fragment data")
	}
	if parsed.User == nil || parsed.User.Username() != "rum-controller" {
		return nil, errors.New("controller Redis URL must use the rum-controller ACL identity")
	}
	options, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	passwordFile = strings.TrimSpace(passwordFile)
	if passwordFile == "" {
		if options.Password == "" {
			return nil, errors.New("controller Redis requires a password or redis_password_file")
		}
		return options, nil
	}
	if options.Password != "" {
		return nil, errors.New("controller Redis URL must not embed a password when redis_password_file is configured")
	}
	info, err := os.Stat(passwordFile)
	if err != nil {
		return nil, err
	}
	if info.Mode().Perm()&0o077 != 0 {
		return nil, errors.New("controller Redis password file permissions must be 0600 or stricter")
	}
	raw, err := os.ReadFile(passwordFile)
	if err != nil {
		return nil, err
	}
	options.Password = strings.TrimSpace(string(raw))
	if len(options.Password) < 16 {
		return nil, errors.New("controller Redis password must contain at least 16 characters")
	}
	return options, nil
}

package maintainer

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"slices"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	rumstate "github.com/bk-lite/rum-collector/internal/rum/state"
	"github.com/redis/go-redis/v9"
)

const (
	maintainerGroup          = "rum-maintainer"
	reconcileCursorKey       = "ops:rum:v2:operations:reconcile:minio-cursor"
	replayCursorKeyPrefix    = "ops:rum:v2:operations:reconcile:replay-cursor:"
	messageHeartbeatInterval = 10 * time.Second
)

var persistErasureObjectsScript = redis.NewScript(`
if redis.call("HGET", KEYS[1], "operation_id") ~= ARGV[1] then
  return {"not_found"}
end
local existing = redis.call("HGET", KEYS[1], "replay_objects")
if existing then
  return {"cached", existing}
end
redis.call("HSET", KEYS[1], "replay_objects", ARGV[2])
return {"stored", ARGV[2]}
`)

type RedisConfig struct {
	URL          string
	PasswordFile string
}

type RedisState struct {
	client   *redis.Client
	consumer string
	now      func() time.Time
}

func NewRedisState(cfg RedisConfig) (*RedisState, error) {
	options, err := maintainerRedisOptions(cfg)
	if err != nil {
		return nil, err
	}
	return &RedisState{
		client:   redis.NewClient(options),
		consumer: "maintainer-" + uuid.NewString(),
		now:      time.Now,
	}, nil
}

func (state *RedisState) Start(ctx context.Context) error {
	if err := state.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("connect RUM maintainer Redis: %w", err)
	}
	for _, stream := range []string{rumstate.ErasureStreamKey, rumstate.ReconcileStreamKey, rumstate.ControlAuditStreamKey} {
		err := state.client.XGroupCreateMkStream(ctx, stream, maintainerGroup, "0").Err()
		if err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
			return fmt.Errorf("create Redis consumer group for %s: %w", stream, err)
		}
	}
	return nil
}

func (state *RedisState) Close() error {
	return state.client.Close()
}

func (state *RedisState) Complete(ctx context.Context, operationID string) error {
	now := state.now().UTC().Format(time.RFC3339Nano)
	return state.client.HSet(ctx, rumstate.OperationKeyPrefix+operationID, map[string]any{
		"status":     "completed",
		"updated_at": now,
		"error":      "",
	}).Err()
}

func (state *RedisState) Retry(ctx context.Context, operationID string, cause error) error {
	now := state.now().UTC().Format(time.RFC3339Nano)
	message := cause.Error()
	if len(message) > 1024 {
		message = message[:1024]
	}
	return state.client.HSet(ctx, rumstate.OperationKeyPrefix+operationID, map[string]any{
		"status":     "pending",
		"updated_at": now,
		"error":      message,
	}).Err()
}

func (state *RedisState) PersistErasureObjects(
	ctx context.Context,
	operationID string,
	objectKeys []string,
) ([]string, error) {
	operationID = strings.TrimSpace(operationID)
	if operationID == "" {
		return nil, errors.New("operation id is required")
	}
	keys := append([]string(nil), objectKeys...)
	sort.Strings(keys)
	keys = slices.Compact(keys)
	for _, key := range keys {
		if strings.TrimSpace(key) == "" || !strings.HasSuffix(key, ".json.gz") {
			return nil, errors.New("invalid Replay object key in erasure plan")
		}
	}
	encoded, err := json.Marshal(keys)
	if err != nil {
		return nil, err
	}
	result, err := persistErasureObjectsScript.Run(
		ctx,
		state.client,
		[]string{rumstate.OperationKeyPrefix + operationID},
		operationID,
		string(encoded),
	).Slice()
	if err != nil {
		return nil, fmt.Errorf("persist erasure Replay objects: %w", err)
	}
	if len(result) != 2 {
		return nil, errors.New("persist erasure Replay objects returned an invalid result")
	}
	if fmt.Sprint(result[0]) == "not_found" {
		return nil, errors.New("erasure operation no longer exists")
	}
	if fmt.Sprint(result[0]) != "stored" && fmt.Sprint(result[0]) != "cached" {
		return nil, errors.New("persist erasure Replay objects returned an unknown result")
	}
	var persisted []string
	if err := json.Unmarshal([]byte(fmt.Sprint(result[1])), &persisted); err != nil {
		return nil, fmt.Errorf("decode persisted erasure Replay objects: %w", err)
	}
	return persisted, nil
}

func (state *RedisState) Fail(ctx context.Context, operationID string, cause error) error {
	now := state.now().UTC().Format(time.RFC3339Nano)
	message := cause.Error()
	if len(message) > 1024 {
		message = message[:1024]
	}
	return state.client.HSet(ctx, rumstate.OperationKeyPrefix+operationID, map[string]any{
		"status":     "failed",
		"updated_at": now,
		"error":      message,
	}).Err()
}

func (state *RedisState) WaitForErasureLeases(ctx context.Context, identities []Identity) error {
	keys := make([]string, 0, len(identities))
	for _, identity := range identities {
		if !identityVersion.MatchString(identity.Version) || !identityDigest.MatchString(identity.Digest) {
			return errors.New("invalid erasure barrier identity")
		}
		keys = append(keys, ingress.ErasureFenceKey(identity.Version, identity.Digest))
	}
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		now := strconv.FormatInt(state.now().UTC().UnixMilli(), 10)
		active := int64(0)
		for _, key := range keys {
			if err := state.client.ZRemRangeByScore(ctx, key, "1", now).Err(); err != nil {
				return fmt.Errorf("clean expired erasure leases: %w", err)
			}
			count, err := state.client.ZCount(ctx, key, "("+now, "+inf").Result()
			if err != nil {
				return fmt.Errorf("count active erasure leases: %w", err)
			}
			active += count
		}
		if active == 0 {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (state *RedisState) Run(ctx context.Context, processor *Processor, reconciler *Reconciler) error {
	if processor == nil || reconciler == nil {
		return errors.New("maintainer Redis worker requires erasure processor and reconciler")
	}
	if err := state.recoverPending(ctx, processor, reconciler); err != nil {
		return err
	}
	for {
		if err := state.retryOwnPending(ctx, processor, reconciler); err != nil {
			return err
		}
		result, err := state.client.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    maintainerGroup,
			Consumer: state.consumer,
			Streams: []string{
				rumstate.ErasureStreamKey,
				rumstate.ReconcileStreamKey,
				rumstate.ControlAuditStreamKey,
				">",
				">",
				">",
			},
			Count: 10,
			Block: 5 * time.Second,
		}).Result()
		if err != nil {
			if errors.Is(err, context.Canceled) {
				return nil
			}
			if errors.Is(err, redis.Nil) {
				continue
			}
			return err
		}
		for _, stream := range result {
			for _, message := range stream.Messages {
				if err := state.processOwnedMessage(ctx, stream.Stream, message, processor, reconciler); err != nil {
					continue
				}
				if err := state.acknowledge(ctx, stream.Stream, message.ID); err != nil {
					return err
				}
			}
		}
	}
}

func (state *RedisState) recoverPending(ctx context.Context, processor *Processor, reconciler *Reconciler) error {
	for _, stream := range []string{rumstate.ErasureStreamKey, rumstate.ReconcileStreamKey, rumstate.ControlAuditStreamKey} {
		start := "0-0"
		for {
			messages, next, err := state.client.XAutoClaim(ctx, &redis.XAutoClaimArgs{
				Stream:   stream,
				Group:    maintainerGroup,
				Consumer: state.consumer,
				MinIdle:  30 * time.Second,
				Start:    start,
				Count:    10,
			}).Result()
			if err != nil && !errors.Is(err, redis.Nil) {
				return err
			}
			for _, message := range messages {
				if err := state.processOwnedMessage(ctx, stream, message, processor, reconciler); err != nil {
					continue
				}
				if err := state.acknowledge(ctx, stream, message.ID); err != nil {
					return err
				}
			}
			if next == "0-0" || next == "" || next == start {
				break
			}
			start = next
		}
	}
	return nil
}

func (state *RedisState) retryOwnPending(
	ctx context.Context,
	processor *Processor,
	reconciler *Reconciler,
) error {
	for _, stream := range []string{rumstate.ErasureStreamKey, rumstate.ReconcileStreamKey, rumstate.ControlAuditStreamKey} {
		result, err := state.client.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    maintainerGroup,
			Consumer: state.consumer,
			Streams:  []string{stream, "0"},
			Count:    10,
			Block:    -1,
		}).Result()
		if errors.Is(err, redis.Nil) {
			continue
		}
		if err != nil {
			return err
		}
		for _, messages := range result {
			for _, message := range messages.Messages {
				if err := state.processOwnedMessage(ctx, stream, message, processor, reconciler); err != nil {
					continue
				}
				if err := state.acknowledge(ctx, stream, message.ID); err != nil {
					return err
				}
			}
		}
	}
	return nil
}

func (state *RedisState) processOwnedMessage(
	ctx context.Context,
	stream string,
	message redis.XMessage,
	processor *Processor,
	reconciler *Reconciler,
) error {
	taskCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	done := make(chan struct{})
	heartbeatErr := make(chan error, 1)
	go func() {
		ticker := time.NewTicker(messageHeartbeatInterval)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-taskCtx.Done():
				return
			case <-ticker.C:
				claimed, err := state.client.XClaimJustID(taskCtx, &redis.XClaimArgs{
					Stream:   stream,
					Group:    maintainerGroup,
					Consumer: state.consumer,
					MinIdle:  0,
					Messages: []string{message.ID},
				}).Result()
				if err != nil || len(claimed) != 1 || claimed[0] != message.ID {
					if err == nil {
						err = errors.New("maintainer stream message ownership was lost")
					}
					select {
					case heartbeatErr <- err:
					default:
					}
					cancel()
					return
				}
			}
		}
	}()
	err := state.processMessage(taskCtx, stream, message, processor, reconciler)
	close(done)
	select {
	case heartbeat := <-heartbeatErr:
		return errors.Join(err, heartbeat)
	default:
		return err
	}
}

func (state *RedisState) acknowledge(ctx context.Context, stream, messageID string) error {
	if err := state.client.XAck(ctx, stream, maintainerGroup, messageID).Err(); err != nil {
		return err
	}
	return state.client.XDel(ctx, stream, messageID).Err()
}

func (state *RedisState) processMessage(
	ctx context.Context,
	stream string,
	message redis.XMessage,
	processor *Processor,
	reconciler *Reconciler,
) error {
	taskCtx, cancel := context.WithTimeout(ctx, 30*time.Minute)
	defer cancel()
	switch stream {
	case rumstate.ErasureStreamKey:
		task, err := erasureTaskFromMessage(message)
		if err != nil {
			return err
		}
		return processor.Erase(taskCtx, task)
	case rumstate.ReconcileStreamKey:
		task, err := reconcileTaskFromMessage(message)
		if err != nil {
			return err
		}
		return reconciler.RunOperation(taskCtx, task)
	case rumstate.ControlAuditStreamKey:
		task, err := controlAuditTaskFromMessage(message)
		if err != nil {
			return err
		}
		return processor.AuditControl(taskCtx, task)
	default:
		return errors.New("unknown maintainer stream")
	}
}

func controlAuditTaskFromMessage(message redis.XMessage) (ControlAuditTask, error) {
	revision, err := strconv.ParseInt(valueString(message.Values, "revision"), 10, 64)
	if err != nil {
		return ControlAuditTask{}, err
	}
	task := ControlAuditTask{
		RequestID:   valueString(message.Values, "request_id"),
		Actor:       valueString(message.Values, "actor"),
		Action:      valueString(message.Values, "action"),
		Application: valueString(message.Values, "application"),
		Revision:    revision,
		CreatedAt:   valueString(message.Values, "created_at"),
	}
	if task.RequestID == "" || task.Actor == "" || task.Action == "" || task.Application == "" {
		return ControlAuditTask{}, errors.New("invalid control audit stream task")
	}
	return task, nil
}

func (state *RedisState) ReconcileCursor(ctx context.Context) (string, error) {
	value, err := state.client.Get(ctx, reconcileCursorKey).Result()
	if errors.Is(err, redis.Nil) {
		return "", nil
	}
	return value, err
}

func (state *RedisState) SetReconcileCursor(ctx context.Context, value string) error {
	if value == "" {
		return state.client.Del(ctx, reconcileCursorKey).Err()
	}
	return state.client.Set(ctx, reconcileCursorKey, value, 48*time.Hour).Err()
}

func (state *RedisState) ReplayScanCursor(ctx context.Context, application string) (ReplayScanCursor, error) {
	values, err := state.client.HGetAll(ctx, replayCursorKeyPrefix+application).Result()
	if err != nil {
		return ReplayScanCursor{}, err
	}
	if len(values) == 0 {
		return ReplayScanCursor{}, nil
	}
	acceptedAt, err := strconv.ParseUint(values["accepted_at_unix_nano"], 10, 64)
	if err != nil || values["segment_id"] == "" {
		return ReplayScanCursor{}, errors.New("invalid Replay reconciliation cursor")
	}
	return ReplayScanCursor{
		AcceptedAtUnixNano: acceptedAt,
		SegmentID:          values["segment_id"],
	}, nil
}

func (state *RedisState) SetReplayScanCursor(
	ctx context.Context,
	application string,
	cursor ReplayScanCursor,
) error {
	key := replayCursorKeyPrefix + application
	if cursor.AcceptedAtUnixNano == 0 && cursor.SegmentID == "" {
		return state.client.Del(ctx, key).Err()
	}
	if cursor.AcceptedAtUnixNano == 0 || cursor.SegmentID == "" {
		return errors.New("incomplete Replay reconciliation cursor")
	}
	pipe := state.client.Pipeline()
	pipe.HSet(ctx, key, map[string]any{
		"accepted_at_unix_nano": cursor.AcceptedAtUnixNano,
		"segment_id":            cursor.SegmentID,
	})
	pipe.Expire(ctx, key, 48*time.Hour)
	_, err := pipe.Exec(ctx)
	return err
}

func (state *RedisState) Applications(ctx context.Context) ([]string, error) {
	var cursor uint64
	var applications []string
	seen := make(map[string]struct{})
	for {
		keys, next, err := state.client.Scan(ctx, cursor, "ops:rum:v2:app:*", 100).Result()
		if err != nil {
			return nil, err
		}
		for _, key := range keys {
			if strings.HasSuffix(key, ":keys") || strings.HasSuffix(key, ":origins") {
				continue
			}
			name := strings.TrimPrefix(key, "ops:rum:v2:app:")
			if name == "" || strings.Contains(name, ":") {
				continue
			}
			if _, exists := seen[name]; !exists {
				seen[name] = struct{}{}
				applications = append(applications, name)
			}
		}
		cursor = next
		if cursor == 0 {
			return applications, nil
		}
	}
}

func (state *RedisState) CountOverdueErasures(ctx context.Context, before time.Time) (int64, error) {
	var cursor uint64
	var overdue int64
	for {
		keys, next, err := state.client.Scan(ctx, cursor, rumstate.OperationKeyPrefix+"*", 100).Result()
		if err != nil {
			return 0, err
		}
		for _, key := range keys {
			suffix := strings.TrimPrefix(key, rumstate.OperationKeyPrefix)
			if suffix == "requests" || strings.HasPrefix(suffix, "reconcile:") {
				continue
			}
			values, err := state.client.HGetAll(ctx, key).Result()
			if err != nil {
				return 0, err
			}
			if values["operation_id"] == "" || values["type"] != "erasure" || values["status"] != "pending" {
				continue
			}
			createdAt, err := time.Parse(time.RFC3339Nano, values["created_at"])
			if err != nil {
				return 0, fmt.Errorf("invalid erasure operation timestamp for %s: %w", key, err)
			}
			if createdAt.Before(before) {
				overdue++
			}
		}
		cursor = next
		if cursor == 0 {
			return overdue, nil
		}
	}
}

type ReconcileTask struct {
	OperationID string
	Application string
}

func erasureTaskFromMessage(message redis.XMessage) (ErasureTask, error) {
	var identities []Identity
	if err := json.Unmarshal([]byte(valueString(message.Values, "identities")), &identities); err != nil {
		return ErasureTask{}, err
	}
	task := ErasureTask{
		OperationID: valueString(message.Values, "operation_id"),
		Application: valueString(message.Values, "application"),
		Actor:       valueString(message.Values, "actor"),
		Identities:  identities,
	}
	if task.OperationID == "" || task.Application == "" || len(task.Identities) == 0 {
		return ErasureTask{}, errors.New("invalid erasure stream task")
	}
	return task, nil
}

func reconcileTaskFromMessage(message redis.XMessage) (ReconcileTask, error) {
	task := ReconcileTask{
		OperationID: valueString(message.Values, "operation_id"),
		Application: valueString(message.Values, "application"),
	}
	if task.OperationID == "" || task.Application == "" {
		return ReconcileTask{}, errors.New("invalid reconciliation stream task")
	}
	return task, nil
}

func valueString(values map[string]any, key string) string {
	return strings.TrimSpace(fmt.Sprint(values[key]))
}

func maintainerRedisOptions(cfg RedisConfig) (*redis.Options, error) {
	parsed, err := url.Parse(strings.TrimSpace(cfg.URL))
	if err != nil || parsed.Host == "" || (parsed.Scheme != "redis" && parsed.Scheme != "rediss") {
		return nil, errors.New("maintainer Redis URL must use redis:// or rediss://")
	}
	if parsed.User == nil || parsed.User.Username() != "rum-maintainer" {
		return nil, errors.New("maintainer Redis URL must use the rum-maintainer ACL identity")
	}
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, errors.New("maintainer Redis URL must not contain query or fragment")
	}
	options, err := redis.ParseURL(cfg.URL)
	if err != nil {
		return nil, err
	}
	passwordFile := strings.TrimSpace(cfg.PasswordFile)
	if passwordFile == "" {
		return nil, errors.New("maintainer Redis password_file is required")
	}
	if options.Password != "" {
		return nil, errors.New("maintainer Redis URL must not embed a password")
	}
	info, err := os.Stat(passwordFile)
	if err != nil {
		return nil, err
	}
	if info.Mode().Perm()&0o077 != 0 {
		return nil, errors.New("maintainer Redis password file permissions must be 0600 or stricter")
	}
	raw, err := os.ReadFile(passwordFile)
	if err != nil {
		return nil, err
	}
	options.Password = strings.TrimSpace(string(raw))
	if len(options.Password) < 16 {
		return nil, errors.New("maintainer Redis password must contain at least 16 characters")
	}
	return options, nil
}

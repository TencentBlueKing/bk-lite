package maintainer

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	rumstate "github.com/bk-lite/rum-collector/internal/rum/state"
	"github.com/redis/go-redis/v9"
)

const (
	sessionIdleTimeout     = 15 * time.Minute
	sessionEndBatch        = 200
	sessionEndScanInterval = time.Minute
	sessionEndScanTimeout  = 45 * time.Second
)

var sessionKeyPattern = regexp.MustCompile(`^[0-9a-f]{32}$`)
var sessionKeyMaterial = regexp.MustCompile(`\b[0-9a-f]{32}\b`)

type lostCounter interface {
	Add(float64)
}

// SessionRedis reads the session activity index written by the gateway.
type SessionRedis struct {
	client *redis.Client
}

func NewSessionRedis(cfg RedisConfig) (*SessionRedis, error) {
	if strings.TrimSpace(cfg.URL) == "" {
		return nil, errors.New("session Redis URL is required")
	}
	options, err := maintainerRedisOptions(cfg)
	if err != nil {
		return nil, err
	}
	return &SessionRedis{client: redis.NewClient(options)}, nil
}

func (store *SessionRedis) Close() error {
	if store == nil || store.client == nil {
		return nil
	}
	return store.client.Close()
}

func (store *SessionRedis) Client() *redis.Client {
	return store.client
}

// SessionLogWriter inserts one JSON line into VictoriaLogs.
type SessionLogWriter struct {
	insertURL string
	client    *http.Client
}

func NewSessionLogWriter(endpoint string, timeout time.Duration) (*SessionLogWriter, error) {
	parsed, err := url.Parse(strings.TrimSpace(endpoint))
	if err != nil || parsed.Host == "" || (parsed.Scheme != "http" && parsed.Scheme != "https") {
		return nil, errors.New("victoria logs endpoint must be an HTTP URL")
	}
	if timeout <= 0 {
		timeout = 10 * time.Second
	}
	target := *parsed
	target.Path = strings.TrimSuffix(target.Path, "/") + "/insert/jsonline"
	target.RawQuery = ""
	target.Fragment = ""
	return &SessionLogWriter{
		insertURL: target.String(),
		client:    &http.Client{Timeout: timeout},
	}, nil
}

type insertStatusError struct {
	status int
}

func (err *insertStatusError) Error() string {
	return fmt.Sprintf("victoria logs insert status %d", err.status)
}

func (writer *SessionLogWriter) Insert(ctx context.Context, body []byte) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, writer.insertURL, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/stream+json")
	resp, err := writer.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &insertStatusError{status: resp.StatusCode}
	}
	return nil
}

type sessionSnapshot struct {
	SessionKey     string
	FirstMS        int64
	LastMS         int64
	Traffic        string
	Events         int64
	Views          int64
	Errors         int64
	Route          string
	Version        string
	User           string
	Environment    string
	ErasureUser    string
	ErasureSession string
	Tenant         string
	Application    string
}

type sessionEndRecord struct {
	Time           string `json:"_time"`
	EventType      string `json:"rum.event.type"`
	SessionKey     string `json:"rum.session.key"`
	Application    string `json:"rum.application"`
	TenantID       string `json:"tenant.id"`
	Environment    string `json:"rum.environment,omitempty"`
	StartedAtMS    int64  `json:"rum.session.started_at_ms"`
	DurationMS     int64  `json:"rum.session.duration_ms"`
	EventCount     int64  `json:"rum.session.event_count"`
	ViewCount      int64  `json:"rum.session.view_count"`
	ErrorCount     int64  `json:"rum.session.error_count"`
	ViewName       string `json:"rum.view.name,omitempty"`
	Release        string `json:"rum.release,omitempty"`
	UserID         string `json:"rum.user.id,omitempty"`
	TrafficClass   string `json:"rum.traffic.class,omitempty"`
	ErasureUser    string `json:"rum.erasure.user_key,omitempty"`
	ErasureSession string `json:"rum.erasure.session_key,omitempty"`
}

func sessionEndBody(snap sessionSnapshot) ([]byte, error) {
	return sessionEndBatchBody([]sessionSnapshot{snap})
}

func sessionEndBatchBody(snaps []sessionSnapshot) ([]byte, error) {
	var buf bytes.Buffer
	encoder := json.NewEncoder(&buf)
	encoder.SetEscapeHTML(false)
	for _, snap := range snaps {
		duration := snap.LastMS - snap.FirstMS
		if duration < 0 {
			duration = 0
		}
		if err := encoder.Encode(sessionEndRecord{
			Time:           time.UnixMilli(snap.LastMS).UTC().Format(time.RFC3339Nano),
			EventType:      "session_end",
			SessionKey:     snap.SessionKey,
			Application:    snap.Application,
			TenantID:       snap.Tenant,
			Environment:    snap.Environment,
			StartedAtMS:    snap.FirstMS,
			DurationMS:     duration,
			EventCount:     snap.Events,
			ViewCount:      snap.Views,
			ErrorCount:     snap.Errors,
			ViewName:       snap.Route,
			Release:        snap.Version,
			UserID:         snap.User,
			TrafficClass:   snap.Traffic,
			ErasureUser:    snap.ErasureUser,
			ErasureSession: snap.ErasureSession,
		}); err != nil {
			return nil, err
		}
	}
	return buf.Bytes(), nil
}

// SessionEndScanner writes session_end records for index members whose score
// is at least 15 minutes old, then removes them. One scan drains every due
// member in batches, or stops when the context budget is spent or a batch
// insert fails. The gateway stores last_seen as that score until the 4 hour
// cap would arrive sooner.
type SessionEndScanner struct {
	client   *redis.Client
	writer   *SessionLogWriter
	lost     lostCounter
	logger   *slog.Logger
	interval time.Duration
}

func NewSessionEndScanner(client *redis.Client, writer *SessionLogWriter, lost lostCounter, logger *slog.Logger) *SessionEndScanner {
	if logger == nil {
		logger = slog.Default()
	}
	return &SessionEndScanner{
		client:   client,
		writer:   writer,
		lost:     lost,
		logger:   logger,
		interval: sessionEndScanInterval,
	}
}

func (scanner *SessionEndScanner) Run(ctx context.Context) error {
	scanner.scanOnce(ctx)
	ticker := time.NewTicker(scanner.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			scanner.scanOnce(ctx)
		}
	}
}

func (scanner *SessionEndScanner) scanOnce(ctx context.Context) {
	scanCtx, cancel := context.WithTimeout(ctx, sessionEndScanTimeout)
	err := scanner.Scan(scanCtx, time.Now())
	cancel()
	if err != nil && ctx.Err() == nil {
		logScanFailure(scanner.logger, err)
	}
}

func logScanFailure(logger *slog.Logger, err error) {
	logger.Error(
		"event=rum_session_end_scan_failed",
		"failed_stage", "scan",
		"error_type", fmt.Sprintf("%T", err),
		"error", redactOpsError(err.Error()),
	)
}

var redisUserinfoPattern = regexp.MustCompile(`//[^/\s]*@`)

func redactOpsError(message string) string {
	message = sessionKeyMaterial.ReplaceAllString(message, "[redacted]")
	message = redisUserinfoPattern.ReplaceAllString(message, "//[redacted]@")
	message = strings.Map(func(r rune) rune {
		if r == '\n' || r == '\r' {
			return ' '
		}
		return r
	}, message)
	if len(message) > 300 {
		message = message[:300]
	}
	return message
}

type scanFailure struct {
	count     int
	errorType string
	status    int
}

func (scanner *SessionEndScanner) Scan(ctx context.Context, now time.Time) error {
	cutoff := strconv.FormatInt(now.Add(-sessionIdleTimeout).UnixMilli(), 10)
	var written, lost int
	var failed scanFailure
	var scanErr error
	for {
		if ctx.Err() != nil {
			break
		}
		members, err := scanner.client.ZRangeByScore(ctx, rumstate.SessionActivityIndexKey, &redis.ZRangeBy{
			Min:    "-inf",
			Max:    cutoff,
			Offset: 0,
			Count:  sessionEndBatch,
		}).Result()
		if err != nil {
			if ctx.Err() == nil {
				scanErr = err
			}
			break
		}
		if len(members) == 0 {
			break
		}
		ready, dropped, err := scanner.classifyMembers(ctx, members)
		if err != nil && ctx.Err() == nil {
			scanErr = err
		}
		if len(dropped) > 0 {
			removed, removeErr := scanner.removeMembers(ctx, dropped)
			if removeErr != nil && ctx.Err() == nil {
				scanErr = removeErr
			}
			lost += removed
		}
		if scanErr != nil || ctx.Err() != nil {
			break
		}
		if len(ready) == 0 {
			if len(members) < sessionEndBatch {
				break
			}
			continue
		}
		body, err := sessionEndBatchBody(ready)
		if err != nil {
			scanErr = err
			break
		}
		if err := scanner.writer.Insert(ctx, body); err != nil {
			noteInsertFailure(&failed, err, len(ready))
			break
		}
		removed, err := scanner.removeWritten(ctx, ready)
		written += removed
		if err != nil && ctx.Err() == nil {
			scanErr = err
			break
		}
		if err != nil || len(members) < sessionEndBatch {
			break
		}
	}
	if lost > 0 && scanner.lost != nil {
		scanner.lost.Add(float64(lost))
	}
	scanner.logScan(written, lost, failed)
	return scanErr
}

func (scanner *SessionEndScanner) classifyMembers(ctx context.Context, members []string) ([]sessionSnapshot, []string, error) {
	ready := make([]sessionSnapshot, 0, len(members))
	var dropped []string
	for _, member := range members {
		snap, ok, err := scanner.loadSnapshot(ctx, member)
		if err != nil {
			return ready, dropped, err
		}
		if !ok {
			dropped = append(dropped, member)
			continue
		}
		ready = append(ready, snap)
	}
	return ready, dropped, nil
}

func (scanner *SessionEndScanner) removeMembers(ctx context.Context, members []string) (int, error) {
	if len(members) == 0 {
		return 0, nil
	}
	args := make([]any, len(members))
	for i, member := range members {
		args[i] = member
	}
	removed, err := scanner.client.ZRem(ctx, rumstate.SessionActivityIndexKey, args...).Result()
	return int(removed), err
}

func (scanner *SessionEndScanner) removeWritten(ctx context.Context, snaps []sessionSnapshot) (int, error) {
	if len(snaps) == 0 {
		return 0, nil
	}
	members := make([]any, len(snaps))
	keys := make([]string, len(snaps))
	for i, snap := range snaps {
		members[i] = snap.SessionKey
		keys[i] = rumstate.SessionEndedKey(snap.SessionKey)
	}
	pipe := scanner.client.Pipeline()
	removedCmd := pipe.ZRem(ctx, rumstate.SessionActivityIndexKey, members...)
	pipe.Del(ctx, keys...)
	_, err := pipe.Exec(ctx)
	return int(removedCmd.Val()), err
}

func noteInsertFailure(failed *scanFailure, err error, count int) {
	if count < 1 {
		count = 1
	}
	failed.count += count
	if failed.errorType != "" {
		return
	}
	var statusErr *insertStatusError
	if errors.As(err, &statusErr) {
		failed.errorType = "insert_status"
		failed.status = statusErr.status
		return
	}
	failed.errorType = fmt.Sprintf("%T", err)
}

func (scanner *SessionEndScanner) logScan(written, lost int, failed scanFailure) {
	if lost > 0 {
		scanner.logger.Warn("event=rum_session_end_lost", "lost", lost, "failed_stage", "load_snapshot")
	}
	if failed.count > 0 {
		args := []any{"failed", failed.count, "failed_stage", "insert", "error_type", failed.errorType}
		if failed.errorType == "insert_status" {
			args = append(args, "status", failed.status)
		}
		scanner.logger.Warn("event=rum_session_end_write_failed", args...)
	}
	if written > 0 {
		scanner.logger.Info("event=rum_session_end_written", "written", written)
	}
}

func (scanner *SessionEndScanner) loadSnapshot(ctx context.Context, member string) (sessionSnapshot, bool, error) {
	if !sessionKeyPattern.MatchString(member) {
		return sessionSnapshot{}, false, nil
	}
	values, err := scanner.client.HGetAll(ctx, rumstate.SessionEndedKey(member)).Result()
	if err != nil {
		return sessionSnapshot{}, false, err
	}
	if len(values) == 0 {
		return sessionSnapshot{}, false, nil
	}
	snap, err := parseSnapshot(member, values)
	if err != nil {
		if delErr := scanner.client.Del(ctx, rumstate.SessionEndedKey(member)).Err(); delErr != nil {
			return sessionSnapshot{}, false, delErr
		}
		return sessionSnapshot{}, false, nil
	}
	return snap, true, nil
}

func parseSnapshot(member string, values map[string]string) (sessionSnapshot, error) {
	if values["key"] != member {
		return sessionSnapshot{}, errors.New("snapshot session key mismatch")
	}
	first, err := strconv.ParseInt(values["first"], 10, 64)
	if err != nil {
		return sessionSnapshot{}, err
	}
	last, err := strconv.ParseInt(values["last"], 10, 64)
	if err != nil {
		return sessionSnapshot{}, err
	}
	events, err := parseCount(values["events"])
	if err != nil {
		return sessionSnapshot{}, err
	}
	views, err := parseCount(values["views"])
	if err != nil {
		return sessionSnapshot{}, err
	}
	errorCount, err := parseCount(values["errors"])
	if err != nil {
		return sessionSnapshot{}, err
	}
	return sessionSnapshot{
		SessionKey:     member,
		FirstMS:        first,
		LastMS:         last,
		Traffic:        values["traffic"],
		Events:         events,
		Views:          views,
		Errors:         errorCount,
		Route:          values["route"],
		Version:        values["version"],
		User:           values["user"],
		Environment:    values["env"],
		ErasureUser:    values["erasure_user"],
		ErasureSession: values["erasure_session"],
		Tenant:         values["tenant"],
		Application:    values["application"],
	}, nil
}

func parseCount(value string) (int64, error) {
	if value == "" {
		return 0, nil
	}
	return strconv.ParseInt(value, 10, 64)
}

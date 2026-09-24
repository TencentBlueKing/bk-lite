package rumgate

import (
	"context"
	"sort"
	"strconv"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.uber.org/zap"
)

// StoredMarker records last_stored_at after a batch is persisted so the
// control plane can distinguish "admitted but nothing stored" from "stored".
// Best-effort: a marker failure must never fail the pipeline after the batch
// has already been persisted.
type StoredMarker interface {
	Start(context.Context) error
	Shutdown(context.Context) error
	Record(context.Context, []string)
}

type redisStoredMarker struct {
	client *redis.Client
	now    func() time.Time
	logger *zap.Logger
}

// NewStoredMarker opens the Redis last_stored_at writer.
func NewStoredMarker(cfg ingress.Config, logger *zap.Logger) (*redisStoredMarker, error) {
	client, err := ingress.NewRedisClient(cfg)
	if err != nil {
		return nil, err
	}
	return &redisStoredMarker{client: client, now: time.Now, logger: logger}, nil
}

func (marker *redisStoredMarker) Start(ctx context.Context) error {
	return marker.client.Ping(ctx).Err()
}

func (marker *redisStoredMarker) Shutdown(context.Context) error {
	return marker.client.Close()
}

func (marker *redisStoredMarker) Record(ctx context.Context, applications []string) {
	if len(applications) == 0 {
		return
	}
	now := strconv.FormatInt(marker.now().UTC().Unix(), 10)
	for _, application := range applications {
		key := ingress.ApplicationKey(application)
		// Only annotate a registry hash that already has a revision. HSET on a
		// missing key creates last_stored_at-only state; List() then skips it
		// as invalid, so the console looks empty even after the operator creates
		// the same name.
		registered, err := marker.client.HExists(ctx, key, "revision").Result()
		if err != nil {
			marker.logger.Warn(
				"record RUM last_stored_at marker failed",
				zap.String("application", application),
				zap.Error(err),
			)
			continue
		}
		if !registered {
			continue
		}
		if err := marker.client.HSet(ctx, key, "last_stored_at", now).Err(); err != nil {
			marker.logger.Warn(
				"record RUM last_stored_at marker failed",
				zap.String("application", application),
				zap.Error(err),
			)
		}
	}
}

// applicationsFromLogs extracts the distinct `rum.application` values carried
// on log records so the marker can be written back to the matching app hash.
func applicationsFromLogs(logs plog.Logs) []string {
	seen := make(map[string]struct{})
	resources := logs.ResourceLogs()
	for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
		scopes := resources.At(resourceIndex).ScopeLogs()
		for scopeIndex := 0; scopeIndex < scopes.Len(); scopeIndex++ {
			records := scopes.At(scopeIndex).LogRecords()
			for recordIndex := 0; recordIndex < records.Len(); recordIndex++ {
				if value, ok := records.At(recordIndex).Attributes().Get("rum.application"); ok {
					seen[value.Str()] = struct{}{}
				}
			}
		}
	}
	return sortedApplications(seen)
}

// applicationsFromTraces extracts the distinct `rum.application` values carried
// on trace resources.
func applicationsFromTraces(traces ptrace.Traces) []string {
	seen := make(map[string]struct{})
	resources := traces.ResourceSpans()
	for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
		if value, ok := resources.At(resourceIndex).Resource().Attributes().Get("rum.application"); ok {
			seen[value.Str()] = struct{}{}
		}
	}
	return sortedApplications(seen)
}

func sortedApplications(seen map[string]struct{}) []string {
	applications := make([]string, 0, len(seen))
	for application := range seen {
		if application != "" {
			applications = append(applications, application)
		}
	}
	sort.Strings(applications)
	return applications
}

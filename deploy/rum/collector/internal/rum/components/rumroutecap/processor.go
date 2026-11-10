package rumroutecap

import (
	"context"
	"fmt"
	"sync"
	"time"

	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.uber.org/zap"
)

type routeCache struct {
	mu       sync.Mutex
	admitted map[string]struct{}
	overflow map[string]time.Time
}

func newRouteCache() *routeCache {
	return &routeCache{
		admitted: map[string]struct{}{},
		overflow: map[string]time.Time{},
	}
}

func (cache *routeCache) hasAdmitted(key string) bool {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	_, ok := cache.admitted[key]
	return ok
}

func (cache *routeCache) hasOverflow(key string) bool {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	until, ok := cache.overflow[key]
	if !ok {
		return false
	}
	if !time.Now().Before(until) {
		delete(cache.overflow, key)
		return false
	}
	return true
}

func (cache *routeCache) rememberAdmitted(key string) {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	cache.admitted[key] = struct{}{}
	delete(cache.overflow, key)
}

func (cache *routeCache) rememberOverflow(key string) {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	cache.overflow[key] = time.Now().Add(overflowCacheTTL)
}

// limiter stamps rum.aggregate.route on a copy of the logs. The copy is the
// only place that attribute exists, so the VictoriaLogs export keeps the
// original route field and does not receive this one.
type limiter struct {
	store    *routeStore
	cache    *routeCache
	shard    string
	logger   *zap.Logger
	failures interface {
		Add(context.Context, int64)
	}
	next interface {
		ConsumeLogs(context.Context, plog.Logs) error
	}
}

func (processor *limiter) stamp(ctx context.Context, logs plog.Logs) {
	resources := logs.ResourceLogs()
	for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
		resource := resources.At(resourceIndex)
		resourceAttrs := resource.Resource().Attributes()
		tenant := attributeString(resourceAttrs, "tenant.id")
		if tenant == "" {
			tenant = unknownRoute
		}
		scopes := resource.ScopeLogs()
		for scopeIndex := 0; scopeIndex < scopes.Len(); scopeIndex++ {
			records := scopes.At(scopeIndex).LogRecords()
			for recordIndex := 0; recordIndex < records.Len(); recordIndex++ {
				attrs := records.At(recordIndex).Attributes()
				if !aggregates(attributeString(attrs, "rum.event.type")) {
					continue
				}
				application := attributeString(attrs, "rum.application")
				if application == "" {
					application = unknownRoute
				}
				route := attributeString(attrs, "rum.view.name")
				if route == "" {
					route = unknownRoute
				}
				attrs.PutStr(aggregateRouteAttribute, processor.routeFor(ctx, tenant, application, route))
			}
		}
	}
}

func aggregates(eventType string) bool {
	switch eventType {
	case "view", "error", "vital":
		return true
	default:
		return false
	}
}

func (processor *limiter) routeFor(ctx context.Context, tenant, application, route string) string {
	key := tenant + "\x00" + application + "\x00" + route
	if processor.cache.hasAdmitted(key) {
		return route
	}
	if processor.cache.hasOverflow(key) {
		return otherRoute
	}
	admitted, err := processor.store.admit(ctx, tenant, application, route)
	if err != nil {
		processor.failures.Add(context.Background(), 1)
		processor.logger.Warn(
			"rum aggregate route redis lookup failed",
			zap.String("failed_stage", "route_admission"),
			zap.String("error_type", fmt.Sprintf("%T", err)),
		)
		return otherRoute
	}
	if admitted {
		processor.cache.rememberAdmitted(key)
		return route
	}
	processor.cache.rememberOverflow(key)
	return otherRoute
}

func attributeString(attrs pcommon.Map, key string) string {
	value, ok := attrs.Get(key)
	if !ok {
		return ""
	}
	return value.AsString()
}

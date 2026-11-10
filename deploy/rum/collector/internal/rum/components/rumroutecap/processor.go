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
	mu        sync.Mutex
	admitted  map[string]struct{}
	overflow  map[string]time.Time
	lastSweep time.Time
}

type admissionCircuit struct {
	mu        sync.Mutex
	openUntil time.Time
	errorType string
}

type failureLog struct {
	mu        sync.Mutex
	open      bool
	start     time.Time
	pending   int64
	errorType string
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
	now := nowFn()
	cache.mu.Lock()
	defer cache.mu.Unlock()
	until, ok := cache.overflow[key]
	if !ok {
		return false
	}
	if !now.Before(until) {
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

func (cache *routeCache) maintain(now time.Time) {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	cache.sweepLocked(now, false)
}

func (cache *routeCache) sweepLocked(now time.Time, force bool) {
	if !force && !cache.lastSweep.IsZero() && now.Sub(cache.lastSweep) < overflowSweepInterval {
		return
	}
	cache.lastSweep = now
	for key, until := range cache.overflow {
		if !now.Before(until) {
			delete(cache.overflow, key)
		}
	}
}

func (cache *routeCache) rememberOverflow(key string) {
	now := nowFn()
	cache.mu.Lock()
	defer cache.mu.Unlock()
	if _, ok := cache.overflow[key]; ok {
		cache.overflow[key] = now.Add(overflowCacheTTL)
		return
	}
	if len(cache.overflow) >= overflowCacheLimit {
		cache.sweepLocked(now, true)
	}
	if len(cache.overflow) >= overflowCacheLimit {
		// Keep routes already known to be over the cap. Evicting one would
		// send that hot route back to Redis. This route is still labeled 其他.
		return
	}
	cache.overflow[key] = now.Add(overflowCacheTTL)
}

// nowFn is replaced by tests that need a frozen clock. Production stays on time.Now.
var nowFn = time.Now

type routeAdmittor interface {
	admit(context.Context, string, string, string) (bool, error)
}

// limiter stamps rum.aggregate.route on a copy of the logs. The copy is the
// only place that attribute exists, so the VictoriaLogs export keeps the
// original route field and does not receive this one.
type limiter struct {
	store      routeAdmittor
	cache      *routeCache
	circuit    admissionCircuit
	failureLog failureLog
	shard      string
	logger     *zap.Logger
	failures   interface {
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
	now := nowFn()
	processor.rollFailureLog(now)
	processor.cache.maintain(now)
	if processor.cache.hasAdmitted(key) {
		return route
	}
	if processor.cache.hasOverflow(key) {
		return otherRoute
	}
	if open, errorType := processor.circuit.reject(now); open {
		processor.noteUnavailable(ctx, errorType)
		return otherRoute
	}
	admitted, err := processor.store.admit(ctx, tenant, application, route)
	if err != nil {
		errorType := errorTypeName(err)
		processor.circuit.trip(nowFn(), errorType)
		processor.noteUnavailable(ctx, errorType)
		return otherRoute
	}
	if admitted {
		processor.cache.rememberAdmitted(key)
		return route
	}
	processor.cache.rememberOverflow(key)
	return otherRoute
}

func (circuit *admissionCircuit) trip(now time.Time, errorType string) {
	circuit.mu.Lock()
	defer circuit.mu.Unlock()
	until := now.Add(redisCircuitOpenFor)
	if until.After(circuit.openUntil) {
		circuit.openUntil = until
	}
	if errorType != "" {
		circuit.errorType = errorType
	}
}

func (circuit *admissionCircuit) reject(now time.Time) (bool, string) {
	circuit.mu.Lock()
	defer circuit.mu.Unlock()
	if !now.Before(circuit.openUntil) {
		return false, ""
	}
	errorType := circuit.errorType
	if errorType == "" {
		errorType = "circuit_open"
	}
	return true, errorType
}

func (processor *limiter) noteUnavailable(ctx context.Context, errorType string) {
	processor.failures.Add(ctx, 1)
	processor.recordFailure(nowFn(), errorType)
}

func (processor *limiter) rollFailureLog(now time.Time) {
	processor.failureLog.mu.Lock()
	defer processor.failureLog.mu.Unlock()
	processor.rollFailureLogLocked(now)
}

func (processor *limiter) rollFailureLogLocked(now time.Time) {
	if !processor.failureLog.open || now.Sub(processor.failureLog.start) < failureLogWindow {
		return
	}
	processor.flushPendingLocked()
}

func (processor *limiter) recordFailure(now time.Time, errorType string) {
	processor.failureLog.mu.Lock()
	defer processor.failureLog.mu.Unlock()
	processor.rollFailureLogLocked(now)
	if !processor.failureLog.open {
		processor.failureLog.open = true
		processor.failureLog.start = now
		processor.failureLog.pending = 0
		processor.failureLog.errorType = ""
		processor.emitFailureLocked(1, errorType)
		return
	}
	if processor.failureLog.pending == 0 {
		processor.failureLog.errorType = errorType
	}
	processor.failureLog.pending++
}

func (processor *limiter) flushFailure() {
	processor.failureLog.mu.Lock()
	defer processor.failureLog.mu.Unlock()
	processor.flushPendingLocked()
}

func (processor *limiter) flushPendingLocked() {
	pending := processor.failureLog.pending
	errorType := processor.failureLog.errorType
	processor.failureLog.open = false
	processor.failureLog.pending = 0
	processor.failureLog.errorType = ""
	if pending == 0 {
		return
	}
	processor.emitFailureLocked(pending, errorType)
}

func (processor *limiter) emitFailureLocked(count int64, errorType string) {
	processor.logger.Warn(
		"rum aggregate route redis lookup failed",
		zap.String("failed_stage", "route_admission"),
		zap.String("error_type", errorType),
		zap.Int64("failure_count", count),
	)
}

func errorTypeName(err error) string {
	if err == nil {
		return "unknown"
	}
	return fmt.Sprintf("%T", err)
}

func attributeString(attrs pcommon.Map, key string) string {
	value, ok := attrs.Get(key)
	if !ok {
		return ""
	}
	return value.AsString()
}

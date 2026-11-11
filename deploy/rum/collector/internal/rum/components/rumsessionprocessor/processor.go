package rumsessionprocessor

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
)

type sessionState struct {
	SessionKey   string
	FirstSeen    time.Time
	LastSeen     time.Time
	TrafficClass string
}

type assignment struct {
	StateKey          string
	ObservedAt        time.Time
	CandidateKey      string
	TrafficClass      string
	EventDelta        int64
	ViewDelta         int64
	ErrorDelta        int64
	Route             string
	Version           string
	User              string
	Environment       string
	ErasureUserKey    string
	ErasureSessionKey string
	Tenant            string
	Application       string
}

type assignedSession struct {
	SessionKey   string
	TrafficClass string
	Rolled       bool
	ClosedKey    string
	EventCount   int64
	ViewCount    int64
	ErrorCount   int64
}

type sessionStore interface {
	assign(context.Context, assignment) (assignedSession, error)
}

type sessionizer struct {
	store sessionStore
}

func newSessionizer(store sessionStore) *sessionizer {
	return &sessionizer{store: store}
}

func advanceSession(state sessionState, observed time.Time, candidateKey, trafficClass string) (sessionState, bool) {
	if state.SessionKey == "" ||
		(!state.LastSeen.IsZero() && observed.Sub(state.LastSeen) >= defaultIdleTimeout) ||
		(!state.FirstSeen.IsZero() && observed.Sub(state.FirstSeen) >= defaultMaximumLength) {
		return sessionState{
			SessionKey:   candidateKey,
			FirstSeen:    observed,
			LastSeen:     observed,
			TrafficClass: normalizedTrafficClass(trafficClass),
		}, true
	}
	if observed.After(state.LastSeen) {
		state.LastSeen = observed
	}
	if state.TrafficClass == "" || state.TrafficClass == "unknown" {
		state.TrafficClass = normalizedTrafficClass(trafficClass)
	}
	return state, false
}

func (processor *sessionizer) processLogs(ctx context.Context, logs plog.Logs) (plog.Logs, error) {
	resources := logs.ResourceLogs()
	for resourceIndex := 0; resourceIndex < resources.Len(); resourceIndex++ {
		resource := resources.At(resourceIndex)
		resourceAttrs := resource.Resource().Attributes()
		tenant := attributeString(resourceAttrs, "tenant.id")
		traffic := normalizedTrafficClass(attributeString(resourceAttrs, "rum.traffic.class"))
		scopes := resource.ScopeLogs()
		for scopeIndex := 0; scopeIndex < scopes.Len(); scopeIndex++ {
			records := scopes.At(scopeIndex).LogRecords()
			for recordIndex := 0; recordIndex < records.Len(); recordIndex++ {
				record := records.At(recordIndex)
				attrs := record.Attributes()
				erasureKey := attributeString(attrs, "rum.erasure.session_key")
				if erasureKey == "" {
					continue
				}
				application := attributeString(attrs, "rum.application")
				outputAttribute := "rum.session.key"
				accumulate := application != ""
				if !accumulate {
					application = attributeString(attrs, "rum.replay.application")
					outputAttribute = "rum.replay.session_key"
				}
				observed := record.ObservedTimestamp().AsTime()
				if tenant == "" || application == "" || observed.IsZero() {
					return logs, errors.New("authoritative RUM session identity is incomplete")
				}
				candidate, err := newSessionKey()
				if err != nil {
					return logs, fmt.Errorf("create authoritative RUM session key: %w", err)
				}
				eventDelta, viewDelta, errorDelta := sessionDeltas(accumulate, attributeString(attrs, "rum.event.type"))
				route, version, user, environment := "", "", "", ""
				if accumulate {
					route = attributeString(attrs, "rum.view.name")
					version = attributeString(attrs, "rum.release")
					user = attributeString(attrs, "rum.user.id")
					environment = attributeString(attrs, "rum.environment")
				}
				assigned, err := processor.store.assign(ctx, assignment{
					StateKey:          stateKey(tenant, application, erasureKey),
					ObservedAt:        observed.UTC(),
					CandidateKey:      candidate,
					TrafficClass:      traffic,
					EventDelta:        eventDelta,
					ViewDelta:         viewDelta,
					ErrorDelta:        errorDelta,
					Route:             route,
					Version:           version,
					User:              user,
					Environment:       environment,
					ErasureUserKey:    attributeString(attrs, "rum.erasure.user_key"),
					ErasureSessionKey: erasureKey,
					Tenant:            tenant,
					Application:       application,
				})
				if err != nil {
					return logs, fmt.Errorf("assign authoritative RUM session: %w", err)
				}
				attrs.PutStr(outputAttribute, assigned.SessionKey)
				traffic = assigned.TrafficClass
			}
		}
		resourceAttrs.PutStr("rum.traffic.class", traffic)
	}
	return logs, nil
}

func sessionDeltas(accumulate bool, eventType string) (events, views, errorCount int64) {
	if !accumulate {
		return 0, 0, 0
	}
	events = 1
	switch eventType {
	case "view":
		views = 1
	case "error":
		errorCount = 1
	}
	return events, views, errorCount
}

func newSessionKey() (string, error) {
	var value [16]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", err
	}
	return hex.EncodeToString(value[:]), nil
}

func normalizedTrafficClass(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "human", "crawler", "synthetic":
		return strings.ToLower(strings.TrimSpace(value))
	default:
		return "unknown"
	}
}

func attributeString(attrs pcommon.Map, key string) string {
	value, ok := attrs.Get(key)
	if !ok {
		return ""
	}
	return value.Str()
}

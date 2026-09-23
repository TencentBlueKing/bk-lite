package rumreplayreceiver

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"mime"
	"net"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/bk-lite/rum-collector/internal/rum/authority"
	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"go.opentelemetry.io/collector/client"
	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/plog"
	"go.opentelemetry.io/collector/receiver"
	"go.uber.org/zap"
)

const (
	replayPath             = "/rum/v1/replay"
	replayContentType      = "application/vnd.weops.rum-replay.v1+json"
	replayScopeName        = "weops.rum.replay.segment"
	headerAPIKey           = "X-API-Key"
	headerTenantID         = "X-Tenant-Id"
	headerCredentialLookup = "X-RUM-Credential-Lookup"
	headerApplication      = "X-RUM-Application"
	headerRequestClass     = "X-RUM-Request-Class"
	headerBatchID          = "X-RUM-Batch-Id"
	headerGeoCountry       = "X-Geo-Country"
	headerGeoCity          = "X-Geo-City"
	headerFaroSessionID    = "X-Faro-Session-Id"
)

var replayBatchIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)

type ingressAdmission interface {
	Admit(ctx context.Context, request ingress.Request) (ingress.Decision, error)
	Start(ctx context.Context) error
	Shutdown(ctx context.Context) error
}

type replayReceiver struct {
	cfg      *Config
	settings *receiver.Settings
	next     consumer.Logs
	now      func() time.Time
	ingress  ingressAdmission

	mu       sync.RWMutex
	server   *http.Server
	listener net.Listener
}

func newReplayReceiver(cfg *Config, settings *receiver.Settings, next consumer.Logs) (*replayReceiver, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	if next == nil {
		return nil, errors.New("rumreplay receiver requires a logs consumer")
	}
	ingress, err := ingress.New(ingress.Config{
		RedisURL:          cfg.AdmissionRedisURL,
		RedisPasswordFile: cfg.AdmissionRedisPass,
	})
	if err != nil {
		return nil, err
	}
	return &replayReceiver{cfg: cfg, settings: settings, next: next, now: time.Now, ingress: ingress}, nil
}

func (receiver *replayReceiver) Start(ctx context.Context, _ component.Host) error {
	if err := receiver.ingress.Start(ctx); err != nil {
		return err
	}
	receiver.mu.Lock()
	defer receiver.mu.Unlock()
	if receiver.server != nil {
		return nil
	}
	listener, err := net.Listen("tcp", receiver.cfg.Endpoint)
	if err != nil {
		return err
	}
	mux := http.NewServeMux()
	mux.HandleFunc(replayPath, receiver.handleReplay)
	server := &http.Server{
		Handler:           mux,
		ReadHeaderTimeout: receiver.cfg.ReadHeaderTimeout,
		ReadTimeout:       receiver.cfg.ReadTimeout,
		IdleTimeout:       receiver.cfg.IdleTimeout,
	}
	receiver.listener = listener
	receiver.server = server
	go func() {
		if serveErr := server.Serve(listener); serveErr != nil && !errors.Is(serveErr, http.ErrServerClosed) {
			receiver.settings.Logger.Error("rumreplay HTTP server stopped", zap.Error(serveErr))
		}
	}()
	return nil
}

func (receiver *replayReceiver) Shutdown(ctx context.Context) error {
	receiver.mu.RLock()
	server := receiver.server
	receiver.mu.RUnlock()
	if server == nil {
		return nil
	}
	return errors.Join(server.Shutdown(ctx), receiver.ingress.Shutdown(ctx))
}

func (receiver *replayReceiver) handleReplay(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("Access-Control-Allow-Origin", "*")
	if request.Method == http.MethodOptions {
		response.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
		response.Header().Set("Access-Control-Allow-Headers", "Content-Type, Content-Encoding, X-API-Key, X-Faro-Session-Id, X-RUM-Application, X-RUM-Batch-Id")
		response.WriteHeader(http.StatusNoContent)
		return
	}
	if request.Method != http.MethodPost {
		writeRequestError(response, http.StatusMethodNotAllowed)
		return
	}
	metadata, metadataStatus := receiver.requestMetadata(request)
	if metadataStatus != 0 {
		writeRequestError(response, metadataStatus)
		return
	}
	if !isReplayContentType(request.Header.Get("Content-Type")) || !strings.EqualFold(strings.TrimSpace(request.Header.Get("Content-Encoding")), "gzip") {
		writeRequestError(response, http.StatusBadRequest)
		return
	}

	decoded, err := decodeReplay(request.Body, receiver.cfg, metadata.observedAt)
	if err != nil {
		writeRequestError(response, statusForReplayError(err))
		return
	}
	if decoded.envelope.Application != metadata.application {
		writeRequestError(response, http.StatusBadRequest)
		return
	}
	if !replayBatchIDPattern.MatchString(strings.TrimSpace(request.Header.Get(headerBatchID))) {
		writeRequestError(response, http.StatusBadRequest)
		return
	}
	if sessionHeader := strings.TrimSpace(request.Header.Get(headerFaroSessionID)); sessionHeader != "" && sessionHeader != decoded.envelope.SessionID {
		writeRequestError(response, http.StatusBadRequest)
		return
	}
	decision, err := receiver.ingress.Admit(request.Context(), ingress.Request{
		Application:       metadata.application,
		AuthorityTenantID: receiver.cfg.TenantID,
		BrowserKey:        metadata.browserKey,
		Origin:            metadata.origin,
		CompressedBytes:   int64(len(decoded.compressed)),
		DecompressedBytes: int64(decoded.uncompressedBytes),
		EventCount:        int64(decoded.envelope.EventCount),
		UserFences: receiver.identityFences(
			"user",
			authority.UserIdentityMaterial(decoded.userID, decoded.envelope.SessionID),
		),
		SessionFences: receiver.identityFences("session", decoded.envelope.SessionID),
	})
	if err != nil {
		writeRequestError(response, http.StatusServiceUnavailable)
		return
	}
	if !decision.Allowed {
		writeAdmissionRejection(response, decision)
		return
	}
	metadata.tenantID = decision.TenantID
	metadata.credentialLookup = derivedCredentialLookup(decision.TenantID, metadata.application)

	logs := replayCarrier(decoded, metadata)
	ctx := trustedMetadataContext(request.Context(), metadata)
	if err := receiver.next.ConsumeLogs(ctx, logs); err != nil {
		writeRequestError(response, http.StatusServiceUnavailable)
		return
	}
	response.WriteHeader(http.StatusAccepted)
}

type requestMetadata struct {
	tenantID            string
	credentialLookup    string
	application         string
	browserKey          string
	origin              string
	requestClass        string
	geoCountry          string
	geoCity             string
	observedAt          time.Time
	identityHMACSecret  string
	identityHMACVersion string
}

func (receiver *replayReceiver) requestMetadata(request *http.Request) (requestMetadata, int) {
	observedAt := receiver.now().UTC()
	application := strings.TrimSpace(request.Header.Get(headerApplication))
	if !rumApplicationPattern.MatchString(application) {
		return requestMetadata{}, http.StatusBadRequest
	}
	apiKey := strings.TrimSpace(request.Header.Get(headerAPIKey))
	if apiKey == "" {
		return requestMetadata{}, http.StatusUnauthorized
	}
	return requestMetadata{
		application:         application,
		browserKey:          apiKey,
		origin:              request.Header.Get("Origin"),
		requestClass:        "replay",
		geoCountry:          boundedHeader(request.Header.Get(headerGeoCountry), 2),
		geoCity:             boundedHeader(request.Header.Get(headerGeoCity), 128),
		observedAt:          observedAt,
		identityHMACSecret:  receiver.cfg.IdentityHMACSecret,
		identityHMACVersion: receiver.cfg.IdentityHMACVersion,
	}, 0
}

func (receiver *replayReceiver) identityFences(kind, rawID string) []ingress.FenceIdentity {
	fences := make([]ingress.FenceIdentity, 0, 2)
	for _, candidate := range []struct {
		version string
		secret  string
	}{
		{version: receiver.cfg.IdentityHMACVersion, secret: receiver.cfg.IdentityHMACSecret},
		{version: receiver.cfg.IdentityHMACPrevVer, secret: receiver.cfg.IdentityHMACPrevious},
	} {
		if candidate.secret == "" {
			continue
		}
		digest := authority.DeriveIdentityKey(
			candidate.secret,
			kind,
			receiver.cfg.TenantID,
			rawID,
		)
		if digest != "" {
			fences = append(fences, ingress.FenceIdentity{Version: candidate.version, Digest: digest})
		}
	}
	return fences
}

func writeAdmissionRejection(response http.ResponseWriter, decision ingress.Decision) {
	if decision.Reason == ingress.RejectBudget {
		seconds := int64((decision.RetryAfter + time.Second - 1) / time.Second)
		if seconds < 1 {
			seconds = 1
		}
		response.Header().Set("Retry-After", fmt.Sprintf("%d", seconds))
		writeRequestError(response, http.StatusTooManyRequests)
		return
	}
	writeRequestError(response, http.StatusForbidden)
}

// derivedCredentialLookup mints the 16-hex credential identity the replay
// carrier contract requires, deterministically from tenant and application.
func derivedCredentialLookup(tenantID, application string) string {
	sum := sha256.Sum256([]byte(tenantID + "\x00" + application))
	return hex.EncodeToString(sum[:])[:16]
}

func replayCarrier(decoded decodedReplay, metadata requestMetadata) plog.Logs {
	logs := plog.NewLogs()
	resourceLogs := logs.ResourceLogs().AppendEmpty()
	resourceAttrs := resourceLogs.Resource().Attributes()
	resourceAttrs.PutStr("tenant.id", metadata.tenantID)
	resourceAttrs.PutStr("rum.credential.lookup_id", metadata.credentialLookup)
	putString(resourceAttrs, "geo.country.iso_code", metadata.geoCountry)
	putString(resourceAttrs, "geo.locality.name", metadata.geoCity)
	scopeLogs := resourceLogs.ScopeLogs().AppendEmpty()
	scopeLogs.Scope().SetName(replayScopeName)
	scopeLogs.Scope().SetVersion("1")
	record := scopeLogs.LogRecords().AppendEmpty()
	record.SetObservedTimestamp(pcommon.NewTimestampFromTime(metadata.observedAt))
	record.SetTimestamp(pcommon.NewTimestampFromTime(decoded.startedAt))
	record.Body().SetEmptyBytes().FromRaw(decoded.compressed)

	envelope := decoded.envelope
	attrs := record.Attributes()
	attrs.PutInt("rum.replay.schema.version", int64(envelope.SchemaVersion))
	attrs.PutStr("rum.replay.application", envelope.Application)
	putString(attrs, "rum.replay.environment", envelope.Environment)
	putString(attrs, "rum.replay.release", envelope.Release)
	attrs.PutStr("rum.replay.session.id", envelope.SessionID)
	attrs.PutStr("rum.replay.page.id", envelope.PageID)
	attrs.PutStr("rum.replay.recording.id", envelope.RecordingID)
	attrs.PutStr("rum.replay.segment.id", envelope.SegmentID)
	attrs.PutInt("rum.replay.sequence", envelope.Sequence)
	attrs.PutStr("rum.replay.started_at", envelope.StartedAt)
	attrs.PutStr("rum.replay.ended_at", envelope.EndedAt)
	attrs.PutBool("rum.replay.has_full_snapshot", envelope.HasFullSnapshot)
	attrs.PutInt("rum.replay.event_count", int64(envelope.EventCount))
	attrs.PutStr("rum.replay.checksum_sha256", envelope.ChecksumSHA256)
	attrs.PutInt("rum.replay.compressed_bytes", int64(len(decoded.compressed)))
	attrs.PutInt("rum.replay.uncompressed_bytes", int64(decoded.uncompressedBytes))
	attrs.PutInt("rum.accepted_at_unix_nano", metadata.observedAt.UnixNano())
	attrs.PutStr("rum.erasure.key_version", metadata.identityHMACVersion)
	attrs.PutStr(
		"rum.erasure.user_key",
		authority.DeriveIdentityKey(
			metadata.identityHMACSecret,
			"user",
			metadata.tenantID,
			authority.UserIdentityMaterial(decoded.userID, envelope.SessionID),
		),
	)
	attrs.PutStr(
		"rum.erasure.session_key",
		authority.DeriveIdentityKey(metadata.identityHMACSecret, "session", metadata.tenantID, envelope.SessionID),
	)
	return logs
}

func trustedMetadataContext(ctx context.Context, metadata requestMetadata) context.Context {
	values := map[string][]string{
		headerTenantID:         {metadata.tenantID},
		headerCredentialLookup: {metadata.credentialLookup},
		headerApplication:      {metadata.application},
		headerRequestClass:     {metadata.requestClass},
	}
	if metadata.geoCountry != "" {
		values[headerGeoCountry] = []string{metadata.geoCountry}
	}
	if metadata.geoCity != "" {
		values[headerGeoCity] = []string{metadata.geoCity}
	}
	return client.NewContext(ctx, client.Info{Metadata: client.NewMetadata(values)})
}

func isReplayContentType(value string) bool {
	mediaType, _, err := mime.ParseMediaType(value)
	return err == nil && mediaType == replayContentType
}

func statusForReplayError(err error) int {
	if errors.Is(err, ErrReplayTooLarge) {
		return http.StatusRequestEntityTooLarge
	}
	return http.StatusBadRequest
}

func writeRequestError(response http.ResponseWriter, status int) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(map[string]string{"error": http.StatusText(status)})
}

func boundedHeader(value string, limit int) string {
	value = strings.TrimSpace(value)
	if len(value) > limit || strings.ContainsAny(value, "\r\n\x00") {
		return ""
	}
	return value
}

func putString(attrs pcommon.Map, key, value string) {
	if value != "" {
		attrs.PutStr(key, value)
	}
}

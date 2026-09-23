package farorumreceiver

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

	faro "github.com/grafana/faro/pkg/go"
	"github.com/bk-lite/rum-collector/internal/rum/authority"
	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"go.opentelemetry.io/collector/client"
	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/receiver"
	"go.uber.org/zap"
)

var (
	credentialLookupPattern = regexp.MustCompile(`^[0-9a-f]{16}$`)
	applicationPattern      = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$`)
)

const (
	collectPath            = "/rum/v1/collect"
	headerAPIKey           = "X-API-Key"
	headerTenantID         = "X-Tenant-Id"
	headerCredentialLookup = "X-RUM-Credential-Lookup"
	headerApplication      = "X-RUM-Application"
	headerRequestClass     = "X-RUM-Request-Class"
	headerBatchID          = "X-RUM-Batch-Id"
	headerGeoCountry       = "X-Geo-Country"
	headerGeoCity          = "X-Geo-City"
)

type ingressAdmission interface {
	Admit(ctx context.Context, request ingress.Request) (ingress.Decision, error)
	Start(ctx context.Context) error
	Shutdown(ctx context.Context) error
}

type faroReceiver struct {
	cfg      *Config
	settings *receiver.Settings
	now      func() time.Time
	ingress  ingressAdmission

	mu         sync.RWMutex
	nextLogs   consumer.Logs
	nextTraces consumer.Traces
	server     *http.Server
	listener   net.Listener
}

func newFaroReceiver(cfg *Config, settings *receiver.Settings) (*faroReceiver, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	ingress, err := ingress.New(ingress.Config{
		RedisURL:          cfg.AdmissionRedisURL,
		RedisPasswordFile: cfg.AdmissionRedisPass,
	})
	if err != nil {
		return nil, err
	}
	return &faroReceiver{
		cfg:      cfg,
		settings: settings,
		now:      time.Now,
		ingress:  ingress,
	}, nil
}

func (receiver *faroReceiver) registerLogs(next consumer.Logs) {
	receiver.mu.Lock()
	defer receiver.mu.Unlock()
	receiver.nextLogs = next
}

func (receiver *faroReceiver) registerTraces(next consumer.Traces) {
	receiver.mu.Lock()
	defer receiver.mu.Unlock()
	receiver.nextTraces = next
}

func (receiver *faroReceiver) Start(ctx context.Context, _ component.Host) error {
	if err := receiver.ingress.Start(ctx); err != nil {
		return err
	}
	receiver.mu.Lock()
	defer receiver.mu.Unlock()
	if receiver.server != nil {
		return nil
	}
	if receiver.nextLogs == nil && receiver.nextTraces == nil {
		return errors.New("farorum receiver requires at least one signal consumer")
	}
	listener, err := net.Listen("tcp", receiver.cfg.Endpoint)
	if err != nil {
		return err
	}
	mux := http.NewServeMux()
	mux.HandleFunc(collectPath, receiver.handleCollect)
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
			receiver.settings.Logger.Error("farorum HTTP server stopped", zap.Error(serveErr))
		}
	}()
	return nil
}

func (receiver *faroReceiver) Shutdown(ctx context.Context) error {
	receiver.mu.RLock()
	server := receiver.server
	receiver.mu.RUnlock()
	if server == nil {
		return nil
	}
	return errors.Join(server.Shutdown(ctx), receiver.ingress.Shutdown(ctx))
}

func (receiver *faroReceiver) handleCollect(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("Access-Control-Allow-Origin", "*")
	if request.Method == http.MethodOptions {
		response.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
		response.Header().Set("Access-Control-Allow-Headers", "Content-Type, Content-Encoding, X-API-Key, X-RUM-Application, X-RUM-Batch-Id")
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
	if !supportedContentType(request.Header.Get("Content-Type")) {
		receiver.rejectWithEvidence(response, request.Context(), metadata, http.StatusBadRequest, "unsupported_media_type")
		return
	}

	payload, facts, err := decodeFaroBodyWithFacts(request.Body, request.Header.Get("Content-Encoding"), receiver.cfg)
	if err != nil {
		writeRequestError(response, statusForReceiverError(err))
		return
	}
	if strings.TrimSpace(payload.Meta.App.Name) != metadata.application {
		writeRequestError(response, http.StatusBadRequest)
		return
	}
	signal, err := classifyPayload(payload, receiver.cfg.MaxItems)
	if err != nil {
		writeRequestError(response, statusForReceiverError(err))
		return
	}
	batchID := strings.TrimSpace(request.Header.Get(headerBatchID))
	if !stableIDPattern.MatchString(batchID) {
		receiver.rejectWithEvidence(response, request.Context(), metadata, http.StatusBadRequest, "invalid_batch_id")
		return
	}
	metadata.batchID = batchID
	decision, err := receiver.ingress.Admit(request.Context(), ingress.Request{
		Application:       metadata.application,
		AuthorityTenantID: receiver.cfg.TenantID,
		BrowserKey:        metadata.browserKey,
		Origin:            metadata.origin,
		CompressedBytes:   facts.compressedBytes,
		DecompressedBytes: facts.decompressedBytes,
		EventCount:        int64(payloadItemCount(payload)),
		UserFences:        receiver.identityFences("user", payload.Meta.User.ID),
		SessionFences:     receiver.identityFences("session", payload.Meta.Session.ID),
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

	if signal&signalOrdinary != 0 {
		logMetadata := metadata
		logMetadata.requestClass = "ordinary"
		logs := translateOrdinary(payload, logMetadata, receiver.cfg)
		appendParseEvidence(logs, logMetadata, "accepted", "ok")
		receiver.mu.RLock()
		next := receiver.nextLogs
		receiver.mu.RUnlock()
		if next == nil || next.ConsumeLogs(trustedMetadataContext(request.Context(), logMetadata), logs) != nil {
			writeRequestError(response, http.StatusServiceUnavailable)
			return
		}
	}
	if signal&signalTraces != 0 {
		traceMetadata := metadata
		traceMetadata.requestClass = "traces"
		traces := payload.Traces.Traces
		if err := sanitizeTraceData(traces, receiver.cfg); err != nil {
			receiver.rejectWithEvidence(response, request.Context(), traceMetadata, statusForReceiverError(err), parseRejectionReason(err))
			return
		}
		overrideTraceMetadata(traces, traceMetadata, payload.Meta)
		if signal&signalOrdinary == 0 {
			receiver.consumeParseEvidenceAsync(
				trustedMetadataContext(request.Context(), traceMetadata),
				traceMetadata,
				"accepted",
				"ok",
			)
		}
		receiver.mu.RLock()
		next := receiver.nextTraces
		receiver.mu.RUnlock()
		if next == nil || next.ConsumeTraces(trustedMetadataContext(request.Context(), traceMetadata), traces) != nil {
			writeRequestError(response, http.StatusServiceUnavailable)
			return
		}
	}
	response.WriteHeader(http.StatusAccepted)
}

func (receiver *faroReceiver) consumeParseEvidenceAsync(
	ctx context.Context,
	metadata ingestMetadata,
	outcome string,
	reason string,
) {
	ctx = context.WithoutCancel(ctx)
	go func() {
		evidenceCtx, cancel := context.WithTimeout(ctx, time.Second)
		defer cancel()
		if err := receiver.consumeParseEvidence(evidenceCtx, metadata, outcome, reason); err != nil {
			receiver.settings.Logger.Debug("farorum trace parse evidence was dropped", zap.Error(err))
		}
	}()
}

func (receiver *faroReceiver) requestMetadata(request *http.Request) (ingestMetadata, int) {
	observedAt := receiver.now().UTC()
	application := strings.TrimSpace(request.Header.Get(headerApplication))
	if !applicationPattern.MatchString(application) {
		return ingestMetadata{}, http.StatusBadRequest
	}
	apiKey := strings.TrimSpace(request.Header.Get(headerAPIKey))
	if apiKey == "" {
		return ingestMetadata{}, http.StatusUnauthorized
	}
	return ingestMetadata{
		application:         application,
		browserKey:          apiKey,
		origin:              request.Header.Get("Origin"),
		geoCountry:          sanitizeText(strings.TrimSpace(request.Header.Get(headerGeoCountry)), 2),
		geoCity:             sanitizeText(strings.TrimSpace(request.Header.Get(headerGeoCity)), 128),
		observedAt:          observedAt,
		identityHMACSecret:  receiver.cfg.IdentityHMACSecret,
		identityHMACVersion: receiver.cfg.IdentityHMACVersion,
	}, 0
}

func payloadItemCount(payload faro.Payload) int {
	count := len(payload.Events) + len(payload.Exceptions) + len(payload.Logs) + len(payload.Measurements)
	if payload.Traces != nil {
		count += payload.Traces.SpanCount()
	}
	return count
}

func (receiver *faroReceiver) identityFences(kind, rawID string) []ingress.FenceIdentity {
	rawID = safeStableID(rawID)
	if rawID == "" {
		return nil
	}
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
// carrier contract requires. Single-tenant core-admin derives it
// deterministically from the authoritative tenant and application so the
// lookup is stable across a browser session without a per-credential store.
func derivedCredentialLookup(tenantID, application string) string {
	sum := sha256.Sum256([]byte(tenantID + "\x00" + application))
	return hex.EncodeToString(sum[:])[:16]
}

func trustedMetadataContext(ctx context.Context, metadata ingestMetadata) context.Context {
	values := map[string][]string{
		headerTenantID:         {metadata.tenantID},
		headerApplication:      {metadata.application},
		headerRequestClass:     {metadata.requestClass},
		headerCredentialLookup: {metadata.credentialLookup},
	}
	if metadata.geoCountry != "" {
		values[headerGeoCountry] = []string{metadata.geoCountry}
	}
	if metadata.geoCity != "" {
		values[headerGeoCity] = []string{metadata.geoCity}
	}
	if metadata.batchID != "" {
		values[headerBatchID] = []string{metadata.batchID}
	}
	return client.NewContext(ctx, client.Info{Metadata: client.NewMetadata(values)})
}

func (receiver *faroReceiver) consumeParseEvidence(ctx context.Context, metadata ingestMetadata, outcome, reason string) error {
	receiver.mu.RLock()
	next := receiver.nextLogs
	receiver.mu.RUnlock()
	if next == nil {
		return errors.New("farorum receiver parse evidence requires logs consumer")
	}
	return next.ConsumeLogs(trustedMetadataContext(ctx, metadata), newParseEvidence(metadata, outcome, reason))
}

func (receiver *faroReceiver) rejectWithEvidence(response http.ResponseWriter, ctx context.Context, metadata ingestMetadata, status int, reason string) {
	if err := receiver.consumeParseEvidence(ctx, metadata, "rejected", reason); err != nil {
		writeRequestError(response, http.StatusServiceUnavailable)
		return
	}
	writeRequestError(response, status)
}

func parseRejectionReason(err error) string {
	switch {
	case errors.Is(err, ErrPayloadTooLarge):
		return "payload_too_large"
	default:
		return "invalid_payload"
	}
}

func supportedContentType(value string) bool {
	mediaType, _, err := mime.ParseMediaType(value)
	if err != nil {
		return false
	}
	return mediaType == "application/json" || mediaType == "application/vnd.grafana.faro+json"
}

func statusForReceiverError(err error) int {
	if errors.Is(err, ErrPayloadTooLarge) {
		return http.StatusRequestEntityTooLarge
	}
	return http.StatusBadRequest
}

func writeRequestError(response http.ResponseWriter, status int) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(map[string]string{"error": http.StatusText(status)})
}

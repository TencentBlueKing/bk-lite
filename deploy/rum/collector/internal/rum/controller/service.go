package controller

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/bk-lite/rum-collector/internal/rum/ingress"
	"github.com/bk-lite/rum-collector/pkg/rum/wire"
)

type Service struct {
	store    *Store
	tenantID string
}

func NewService(store *Store, tenantID string) (*Service, error) {
	if store == nil {
		return nil, errors.New("controller store is required")
	}
	if !wire.ValidTenantID(tenantID) {
		return nil, errors.New("controller tenant id must be a stable identifier")
	}
	return &Service{store: store, tenantID: tenantID}, nil
}

func (service *Service) Handle(ctx context.Context, subject string, data []byte) []byte {
	request, err := DecodeRequest(data)
	if err != nil {
		return marshalResponse(ErrorResponse(request.RequestID, ErrorInvalidArgument, err.Error(), nil))
	}
	var response ResponseEnvelope
	switch subject {
	case SubjectApplicationApply:
		response = service.apply(ctx, subject, request)
	case SubjectApplicationGet:
		response = service.get(ctx, request)
	case SubjectApplicationList:
		response = service.list(ctx, request)
	case SubjectApplicationRotate:
		response = service.rotate(ctx, subject, request)
	case SubjectApplicationRetire:
		response = service.retire(ctx, subject, request)
	case SubjectApplicationDisable:
		response = service.disable(ctx, subject, request)
	case SubjectErasureSubmit:
		response = service.erase(ctx, subject, request)
	case SubjectReconcileSubmit:
		response = service.reconcile(ctx, subject, request)
	case SubjectOperationGet:
		response = service.operation(ctx, request)
	case SubjectStatusGet:
		response = service.status(ctx, request)
	default:
		response = ErrorResponse(request.RequestID, ErrorNotFound, "unknown control subject", nil)
	}
	response.RequestID = request.RequestID
	return marshalResponse(response)
}

func (service *Service) apply(ctx context.Context, subject string, request RequestEnvelope) ResponseEnvelope {
	payload, err := DecodePayload[ApplicationApplyPayload](request)
	if err != nil {
		return invalid(request, err)
	}
	if err := payload.Validate(); err != nil {
		return invalid(request, err)
	}
	expected, failure := requireExpectedRevision(request)
	if failure != nil {
		return *failure
	}
	application := applicationState(payload, service.tenantID, expected+1)
	result, err := service.store.ApplyApplication(ctx, subject, request, application)
	return responseFromResult(request.RequestID, result, err)
}

func applicationState(payload ApplicationApplyPayload, tenantID string, revision int64) ingress.Application {
	digests := make([]string, 0, len(payload.BrowserKeys))
	for _, key := range payload.BrowserKeys {
		digests = append(digests, ingress.KeyDigest(key))
	}
	return ingress.Application{
		Name:                       payload.Application,
		TenantID:                   tenantID,
		OrgID:                      payload.OrgID,
		Enabled:                    payload.Enabled,
		Revision:                   revision,
		RequestsPerMinute:          payload.Budgets.RequestsPerMinute,
		CompressedBytesPerMinute:   payload.Budgets.CompressedBytesPerMinute,
		DecompressedBytesPerMinute: payload.Budgets.DecompressedBytesPerMinute,
		EventsPerMinute:            payload.Budgets.EventsPerMinute,
		BrowserKeys:                append([]string(nil), payload.BrowserKeys...),
		BrowserKeyDigests:          digests,
		Origins:                    append([]string(nil), payload.Origins...),
	}
}

func (service *Service) get(ctx context.Context, request RequestEnvelope) ResponseEnvelope {
	payload, err := DecodePayload[ApplicationPayload](request)
	if err != nil || !validApplicationName(payload.Application) {
		if err == nil {
			err = errors.New("application is invalid")
		}
		return invalid(request, err)
	}
	application, err := service.store.GetApplication(ctx, payload.Application)
	if err != nil {
		return responseFromResult(request.RequestID, commandResult{}, err)
	}
	return ResponseEnvelope{
		RequestID: request.RequestID,
		Revision:  application.Revision,
		Data:      applicationView(application),
	}
}

func (service *Service) list(ctx context.Context, request RequestEnvelope) ResponseEnvelope {
	applications, err := service.store.List(ctx)
	if err != nil {
		return responseFromResult(request.RequestID, commandResult{}, err)
	}
	views := make([]ApplicationView, 0, len(applications))
	for _, application := range applications {
		views = append(views, applicationView(application))
	}
	return ResponseEnvelope{
		RequestID: request.RequestID,
		Data:      views,
	}
}

func (service *Service) rotate(ctx context.Context, subject string, request RequestEnvelope) ResponseEnvelope {
	payload, err := DecodePayload[ApplicationRotatePayload](request)
	if err != nil {
		return invalid(request, err)
	}
	if !validApplicationName(payload.Application) || !wire.ValidBrowserKey(payload.BrowserKey) {
		return invalid(request, errors.New("application or browserKey is invalid"))
	}
	expected, failure := requireExpectedRevision(request)
	if failure != nil {
		return *failure
	}
	if cached, ok := service.resolveIdempotent(ctx, subject, request); ok {
		return cached
	}
	application, err := service.store.GetApplication(ctx, payload.Application)
	if err != nil {
		return responseFromResult(request.RequestID, commandResult{}, err)
	}
	if application.Revision != expected {
		return revisionConflict(request.RequestID, application.Revision)
	}
	digest := ingress.KeyDigest(payload.BrowserKey)
	for _, existing := range application.BrowserKeyDigests {
		if existing == digest {
			return invalid(request, errors.New("browser key is already active"))
		}
	}
	if len(application.BrowserKeyDigests) >= ingress.MaxActiveBrowserKeys {
		return invalid(request, errors.New("two browser keys are already active; retire one before rotating again"))
	}
	application.BrowserKeyDigests = append(application.BrowserKeyDigests, digest)
	sort.Strings(application.BrowserKeyDigests)
	application.Revision++
	result, err := service.store.ApplyApplication(ctx, subject, request, application)
	return responseFromResult(request.RequestID, result, err)
}

func (service *Service) retire(ctx context.Context, subject string, request RequestEnvelope) ResponseEnvelope {
	payload, err := DecodePayload[ApplicationRetirePayload](request)
	if err != nil {
		return invalid(request, err)
	}
	if !validApplicationName(payload.Application) || !wire.ValidBrowserKey(payload.BrowserKey) {
		return invalid(request, errors.New("application or browserKey is invalid"))
	}
	expected, failure := requireExpectedRevision(request)
	if failure != nil {
		return *failure
	}
	if cached, ok := service.resolveIdempotent(ctx, subject, request); ok {
		return cached
	}
	application, err := service.store.GetApplication(ctx, payload.Application)
	if err != nil {
		return responseFromResult(request.RequestID, commandResult{}, err)
	}
	if application.Revision != expected {
		return revisionConflict(request.RequestID, application.Revision)
	}
	digest := ingress.KeyDigest(payload.BrowserKey)
	var remaining []string
	for _, existing := range application.BrowserKeyDigests {
		if existing != digest {
			remaining = append(remaining, existing)
		}
	}
	if len(remaining) == len(application.BrowserKeyDigests) {
		return ErrorResponse(request.RequestID, ErrorNotFound, "browser key is not active", nil)
	}
	if len(remaining) == 0 {
		return invalid(request, errors.New("at least one browser key must remain active"))
	}
	application.BrowserKeyDigests = remaining
	application.Revision++
	result, err := service.store.ApplyApplication(ctx, subject, request, application)
	return responseFromResult(request.RequestID, result, err)
}

func (service *Service) disable(ctx context.Context, subject string, request RequestEnvelope) ResponseEnvelope {
	payload, err := DecodePayload[ApplicationPayload](request)
	if err != nil || !validApplicationName(payload.Application) {
		if err == nil {
			err = errors.New("application is invalid")
		}
		return invalid(request, err)
	}
	expected, failure := requireExpectedRevision(request)
	if failure != nil {
		return *failure
	}
	if cached, ok := service.resolveIdempotent(ctx, subject, request); ok {
		return cached
	}
	application, err := service.store.GetApplication(ctx, payload.Application)
	if err != nil {
		return responseFromResult(request.RequestID, commandResult{}, err)
	}
	if application.Revision != expected {
		return revisionConflict(request.RequestID, application.Revision)
	}
	application.Enabled = false
	application.Revision++
	result, err := service.store.ApplyApplication(ctx, subject, request, application)
	return responseFromResult(request.RequestID, result, err)
}

func (service *Service) erase(ctx context.Context, subject string, request RequestEnvelope) ResponseEnvelope {
	payload, err := DecodePayload[ErasureSubmitPayload](request)
	if err != nil {
		return invalid(request, err)
	}
	if !validApplicationName(payload.Application) || len(payload.Identities) == 0 || len(payload.Identities) > 10_000 {
		return invalid(request, errors.New("application and 1-10000 identities are required"))
	}
	for _, identity := range payload.Identities {
		if (identity.Kind != "user" && identity.Kind != "session") ||
			strings.TrimSpace(identity.Value) == "" ||
			len(identity.Value) > 256 {
			return invalid(request, errors.New("identity kind or value is invalid"))
		}
	}
	application, err := service.store.GetApplication(ctx, payload.Application)
	if err != nil {
		return responseFromResult(request.RequestID, commandResult{}, err)
	}
	derived := service.store.DeriveIdentities(application, payload.Identities)
	if len(derived) == 0 {
		return ErrorResponse(request.RequestID, ErrorInternal, "identity HMAC secrets are unavailable", nil)
	}
	result, err := service.store.SubmitOperation(ctx, subject, request, "erasure", application, derived)
	return responseFromResult(request.RequestID, result, err)
}

func (service *Service) reconcile(ctx context.Context, subject string, request RequestEnvelope) ResponseEnvelope {
	payload, err := DecodePayload[ReconcileSubmitPayload](request)
	if err != nil {
		return invalid(request, err)
	}
	if payload.Application == "" {
		return invalid(request, errors.New("application is required"))
	}
	application, err := service.store.GetApplication(ctx, payload.Application)
	if err != nil {
		return responseFromResult(request.RequestID, commandResult{}, err)
	}
	result, err := service.store.SubmitOperation(ctx, subject, request, "reconcile", application, nil)
	return responseFromResult(request.RequestID, result, err)
}

func (service *Service) operation(ctx context.Context, request RequestEnvelope) ResponseEnvelope {
	payload, err := DecodePayload[OperationGetPayload](request)
	if err != nil || !wire.ValidEnvelopeID(payload.OperationID) {
		if err == nil {
			err = errors.New("operationId is invalid")
		}
		return invalid(request, err)
	}
	operation, err := service.store.GetOperation(ctx, payload.OperationID)
	if err != nil {
		return responseFromResult(request.RequestID, commandResult{}, err)
	}
	return ResponseEnvelope{RequestID: request.RequestID, OperationID: operation.OperationID, Data: operation}
}

func (service *Service) status(ctx context.Context, request RequestEnvelope) ResponseEnvelope {
	if err := service.store.Ping(ctx); err != nil {
		return ErrorResponse(request.RequestID, ErrorUnavailable, "controller Redis is unavailable", nil)
	}
	return ResponseEnvelope{
		RequestID: request.RequestID,
		Data: map[string]string{
			"status":     "ready",
			"apiVersion": APIVersion,
			"tenantId":   service.tenantID,
		},
	}
}

func (service *Service) resolveIdempotent(
	ctx context.Context,
	subject string,
	request RequestEnvelope,
) (ResponseEnvelope, bool) {
	result, found, err := service.store.ResolveIdempotent(ctx, subject, request)
	if err != nil {
		return responseFromResult(request.RequestID, result, err), true
	}
	if !found {
		return ResponseEnvelope{}, false
	}
	return responseFromResult(request.RequestID, result, nil), true
}

func responseFromResult(requestID string, result commandResult, err error) ResponseEnvelope {
	if err != nil {
		var failure *storeError
		if errors.As(err, &failure) {
			message := failure.Error()
			if failure.err == nil {
				message = strings.ReplaceAll(string(failure.code), "_", " ")
			}
			return ErrorResponse(requestID, failure.code, message, failure.fields)
		}
		return ErrorResponse(requestID, ErrorInternal, err.Error(), nil)
	}
	var data any
	if len(result.Data) > 0 {
		if err := json.Unmarshal(result.Data, &data); err != nil {
			return ErrorResponse(requestID, ErrorInternal, "cached command result is invalid", nil)
		}
	}
	return ResponseEnvelope{
		RequestID:   requestID,
		Revision:    result.Revision,
		OperationID: result.OperationID,
		Data:        data,
	}
}

func requireExpectedRevision(request RequestEnvelope) (int64, *ResponseEnvelope) {
	if request.ExpectedRevision == nil || *request.ExpectedRevision < 0 {
		response := invalid(request, errors.New("expectedRevision is required and must not be negative"))
		return 0, &response
	}
	return *request.ExpectedRevision, nil
}

func revisionConflict(requestID string, actual int64) ResponseEnvelope {
	return ErrorResponse(requestID, ErrorRevisionConflict, "expected revision does not match", map[string]string{
		"actualRevision": fmt.Sprintf("%d", actual),
	})
}

func invalid(request RequestEnvelope, err error) ResponseEnvelope {
	return ErrorResponse(request.RequestID, ErrorInvalidArgument, err.Error(), nil)
}

func validApplicationName(value string) bool {
	return wire.ValidApplicationName(value)
}

func marshalResponse(response ResponseEnvelope) []byte {
	encoded, err := json.Marshal(response)
	if err == nil {
		return encoded
	}
	fallback, _ := json.Marshal(ErrorResponse(response.RequestID, ErrorInternal, "response serialization failed", nil))
	return fallback
}

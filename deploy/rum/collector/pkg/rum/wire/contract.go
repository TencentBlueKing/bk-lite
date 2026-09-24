package wire

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/url"
	"regexp"
	"strconv"
	"strings"
)

const APIVersion = "rum.control/v1"

const (
	SubjectApplicationApply   = "rum.v1.control.application.apply"
	SubjectApplicationGet     = "rum.v1.control.application.get"
	SubjectApplicationList    = "rum.v1.control.application.list"
	SubjectApplicationRotate  = "rum.v1.control.application.rotate"
	SubjectApplicationRetire  = "rum.v1.control.application.retire"
	SubjectApplicationDisable = "rum.v1.control.application.disable"
	SubjectErasureSubmit      = "rum.v1.control.erasure.submit"
	SubjectReconcileSubmit    = "rum.v1.control.reconcile.submit"
	SubjectOperationGet       = "rum.v1.control.operation.get"
	SubjectStatusGet          = "rum.v1.control.status.get"
	QueueGroupController      = "rum-controller"
)

var AllSubjects = []string{
	SubjectApplicationApply,
	SubjectApplicationGet,
	SubjectApplicationList,
	SubjectApplicationRotate,
	SubjectApplicationRetire,
	SubjectApplicationDisable,
	SubjectErasureSubmit,
	SubjectReconcileSubmit,
	SubjectOperationGet,
	SubjectStatusGet,
}

var (
	envelopeIDPattern  = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}$`)
	browserKeyPattern  = regexp.MustCompile(`^[A-Za-z0-9._:-]{16,256}$`)
	applicationPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$`)
	stableIDPattern    = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)
)

type RequestEnvelope struct {
	APIVersion       string          `json:"apiVersion"`
	RequestID        string          `json:"requestId"`
	IdempotencyKey   string          `json:"idempotencyKey"`
	ExpectedRevision *int64          `json:"expectedRevision,omitempty"`
	Actor            string          `json:"actor"`
	Payload          json.RawMessage `json:"payload"`
}

type ResponseEnvelope struct {
	RequestID   string         `json:"requestId"`
	Revision    int64          `json:"revision,omitempty"`
	OperationID string         `json:"operationId,omitempty"`
	Data        any            `json:"data,omitempty"`
	Error       *ResponseError `json:"error,omitempty"`
}

type ResponseError struct {
	Code    ErrorCode         `json:"code"`
	Message string            `json:"message"`
	Fields  map[string]string `json:"fields,omitempty"`
}

type ErrorCode string

const (
	ErrorInvalidArgument     ErrorCode = "invalid_argument"
	ErrorNotFound            ErrorCode = "not_found"
	ErrorRevisionConflict    ErrorCode = "revision_conflict"
	ErrorIdempotencyConflict ErrorCode = "idempotency_conflict"
	ErrorOrgConflict         ErrorCode = "org_conflict"
	ErrorForbidden           ErrorCode = "forbidden"
	ErrorUnavailable         ErrorCode = "unavailable"
	ErrorInternal            ErrorCode = "internal_error"
)

type Budgets struct {
	RequestsPerMinute          int64 `json:"requestsPerMinute"`
	CompressedBytesPerMinute   int64 `json:"compressedBytesPerMinute"`
	DecompressedBytesPerMinute int64 `json:"decompressedBytesPerMinute"`
	EventsPerMinute            int64 `json:"eventsPerMinute"`
}

type ApplicationApplyPayload struct {
	Application string   `json:"application"`
	// OrgID scopes application identity to one organization. The deployment
	// registry is shared, so the controller rejects an apply that would move
	// an existing name to a different organization.
	OrgID       string   `json:"orgId"`
	Enabled     bool     `json:"enabled"`
	BrowserKeys []string `json:"browserKeys"`
	Origins     []string `json:"origins"`
	Budgets     Budgets  `json:"budgets"`
}

func (payload ApplicationApplyPayload) Validate() error {
	if !applicationPattern.MatchString(payload.Application) {
		return errors.New("application name must be a stable identifier")
	}
	if !applicationPattern.MatchString(payload.OrgID) {
		return errors.New("organization id must be a stable identifier")
	}
	if payload.Budgets.RequestsPerMinute <= 0 ||
		payload.Budgets.CompressedBytesPerMinute <= 0 ||
		payload.Budgets.DecompressedBytesPerMinute <= 0 ||
		payload.Budgets.EventsPerMinute <= 0 {
		return errors.New("budgets: all application budgets must be explicit and positive")
	}
	if len(payload.BrowserKeys) == 0 || len(payload.BrowserKeys) > 2 {
		return errors.New("browser keys: application must have between one and two active browser keys")
	}
	seenKeys := make(map[string]struct{}, len(payload.BrowserKeys))
	for _, key := range payload.BrowserKeys {
		if !browserKeyPattern.MatchString(key) {
			return errors.New("browser keys must contain 16-256 URL-safe characters")
		}
		if _, duplicate := seenKeys[key]; duplicate {
			return errors.New("browser keys must be unique")
		}
		seenKeys[key] = struct{}{}
	}
	if len(payload.Origins) == 0 || len(payload.Origins) > 20 {
		return errors.New("origins: application must have between one and twenty exact origins")
	}
	seenOrigins := make(map[string]struct{}, len(payload.Origins))
	for _, origin := range payload.Origins {
		canonical, err := canonicalOrigin(origin)
		if err != nil || canonical != origin {
			return errors.New("origin: origin must be an exact canonical HTTP or HTTPS origin")
		}
		if _, duplicate := seenOrigins[canonical]; duplicate {
			return errors.New("origins must be unique")
		}
		seenOrigins[canonical] = struct{}{}
	}
	return nil
}

func canonicalOrigin(value string) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" || value == "null" || value == "*" || strings.ContainsAny(value, "*\\") {
		return "", errors.New("invalid origin")
	}
	parsed, err := url.Parse(value)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" ||
		parsed.User != nil ||
		parsed.Path != "" ||
		parsed.RawPath != "" ||
		parsed.RawQuery != "" ||
		parsed.Fragment != "" {
		return "", errors.New("invalid origin")
	}
	host := parsed.Hostname()
	if host == "" {
		return "", errors.New("invalid origin")
	}
	if port := parsed.Port(); port != "" {
		if _, err := strconv.ParseUint(port, 10, 16); err != nil {
			return "", errors.New("invalid origin")
		}
		host = net.JoinHostPort(strings.ToLower(host), port)
	} else if strings.Contains(host, ":") {
		host = "[" + strings.ToLower(host) + "]"
	} else {
		host = strings.ToLower(host)
	}
	return parsed.Scheme + "://" + host, nil
}

type ApplicationPayload struct {
	Application string `json:"application"`
}

type ApplicationRotatePayload struct {
	Application string `json:"application"`
	BrowserKey  string `json:"browserKey"`
}

type ApplicationRetirePayload struct {
	Application string `json:"application"`
	BrowserKey  string `json:"browserKey"`
}

type ErasureIdentity struct {
	Kind  string `json:"kind"`
	Value string `json:"value"`
}

type ErasureSubmitPayload struct {
	Application string            `json:"application"`
	Identities  []ErasureIdentity `json:"identities"`
}

type ReconcileSubmitPayload struct {
	Application string `json:"application,omitempty"`
}

type OperationGetPayload struct {
	OperationID string `json:"operationId"`
}

type ApplicationView struct {
	Application       string   `json:"application"`
	TenantID          string   `json:"tenantId"`
	Enabled           bool     `json:"enabled"`
	Revision          int64    `json:"revision"`
	BrowserKeys       []string `json:"browserKeys"`
	BrowserKeyDigests []string `json:"browserKeyDigests"`
	Origins           []string `json:"origins"`
	Budgets           Budgets  `json:"budgets"`
	LastAcceptedAt    int64    `json:"lastAcceptedAt,omitempty"`
	LastStoredAt      int64    `json:"lastStoredAt,omitempty"`
}

type OperationView struct {
	OperationID string `json:"operationId"`
	Type        string `json:"type"`
	Status      string `json:"status"`
	Application string `json:"application,omitempty"`
	Actor       string `json:"actor"`
	CreatedAt   string `json:"createdAt"`
	UpdatedAt   string `json:"updatedAt"`
	Error       string `json:"error,omitempty"`
}

func DecodeRequest(data []byte) (RequestEnvelope, error) {
	var request RequestEnvelope
	if err := decodeStrict(data, &request); err != nil {
		return RequestEnvelope{}, err
	}
	if request.APIVersion != APIVersion {
		return RequestEnvelope{}, errors.New("unsupported apiVersion")
	}
	if !envelopeIDPattern.MatchString(request.RequestID) {
		return RequestEnvelope{}, errors.New("requestId is required and must be a stable identifier")
	}
	if !envelopeIDPattern.MatchString(request.IdempotencyKey) {
		return RequestEnvelope{}, errors.New("idempotencyKey is required and must be a stable identifier")
	}
	if strings.TrimSpace(request.Actor) == "" || len(request.Actor) > 256 {
		return RequestEnvelope{}, errors.New("actor is required and must not exceed 256 characters")
	}
	if len(request.Payload) == 0 || bytes.Equal(bytes.TrimSpace(request.Payload), []byte("null")) {
		return RequestEnvelope{}, errors.New("payload is required")
	}
	return request, nil
}

func DecodePayload[T any](request RequestEnvelope) (T, error) {
	var payload T
	if err := decodeStrict(request.Payload, &payload); err != nil {
		return payload, err
	}
	return payload, nil
}

func decodeStrict(data []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(new(any)); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("multiple JSON values are not allowed")
		}
		return err
	}
	return nil
}

func Fingerprint(subject string, request RequestEnvelope) string {
	var payload any
	if err := json.Unmarshal(request.Payload, &payload); err != nil {
		payload = string(request.Payload)
	}
	canonical, _ := json.Marshal(struct {
		Subject          string `json:"subject"`
		APIVersion       string `json:"apiVersion"`
		ExpectedRevision *int64 `json:"expectedRevision,omitempty"`
		Actor            string `json:"actor"`
		Payload          any    `json:"payload"`
	}{
		Subject:          subject,
		APIVersion:       request.APIVersion,
		ExpectedRevision: request.ExpectedRevision,
		Actor:            request.Actor,
		Payload:          payload,
	})
	sum := sha256.Sum256(canonical)
	return hex.EncodeToString(sum[:])
}

func ErrorResponse(requestID string, code ErrorCode, message string, fields map[string]string) ResponseEnvelope {
	return ResponseEnvelope{
		RequestID: requestID,
		Error: &ResponseError{
			Code:    code,
			Message: message,
			Fields:  fields,
		},
	}
}

func ValidEnvelopeID(value string) bool {
	return envelopeIDPattern.MatchString(value)
}

func ValidBrowserKey(value string) bool {
	return browserKeyPattern.MatchString(value)
}

func ValidApplicationName(value string) bool {
	return applicationPattern.MatchString(value)
}

func ValidTenantID(value string) bool {
	return stableIDPattern.MatchString(value)
}

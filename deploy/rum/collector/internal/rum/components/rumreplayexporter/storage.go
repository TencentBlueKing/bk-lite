package rumreplayexporter

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"
)

var (
	ErrChecksumConflict = errors.New("Replay logical slot has conflicting payload or storage identity")
	ErrErasureFenced    = errors.New("Replay identity is fenced for erasure")
	ErrInvalidCarrier   = errors.New("invalid Replay carrier")
	ErrLeaseUnavailable = errors.New("Replay erasure lease is unavailable")
	ErrLeaseLost        = errors.New("Replay erasure lease ownership was lost")
)

type EnsureOutcome uint8

const (
	EnsureUnknown EnsureOutcome = iota
	EnsureCreated
	EnsureReused
	EnsureAlreadyReady
)

type ObjectWrite struct {
	Bucket          string
	LogicalPrefix   string
	Key             string
	ChecksumSHA256  string
	Body            []byte
	ContentType     string
	ContentEncoding string
	Metadata        map[string]string
}

type ObjectStore interface {
	Start(context.Context) error
	Ensure(context.Context, ObjectWrite) (EnsureOutcome, error)
	Shutdown(context.Context) error
}

// ReplayIndex mirrors the frozen ClickHouse JSONEachRow contract exactly.
type ReplayIndex struct {
	TenantID           string `json:"tenant_id"`
	CredentialLookupID string `json:"CredentialLookupId"`
	Application        string `json:"Application"`
	Environment        string `json:"Environment"`
	Release            string `json:"Release"`
	SessionID          string `json:"SessionId"`
	SessionKey         string `json:"SessionKey"`
	PageID             string `json:"PageId"`
	RecordingID        string `json:"RecordingId"`
	SegmentID          string `json:"SegmentId"`
	Sequence           uint32 `json:"Sequence"`
	StartTime          string `json:"StartTime"`
	EndTime            string `json:"EndTime"`
	EventCount         uint32 `json:"EventCount"`
	CompressedBytes    uint64 `json:"CompressedBytes"`
	UncompressedBytes  uint64 `json:"UncompressedBytes"`
	HasFullSnapshot    uint8  `json:"HasFullSnapshot"`
	ChecksumSHA256     string `json:"ChecksumSHA256"`
	ObjectKey          string `json:"ObjectKey"`
	Status             string `json:"Status"`
	ErasureKeyVersion  string `json:"ErasureKeyVersion"`
	ErasureUserKey     string `json:"ErasureUserKey"`
	ErasureSessionKey  string `json:"ErasureSessionKey"`
	AcceptedAtUnixNano uint64 `json:"AcceptedAtUnixNano"`
	Version            uint64 `json:"Version"`
}

func validateReplayIndex(row ReplayIndex) error {
	if !carrierHashPattern.MatchString(row.ChecksumSHA256) ||
		!carrierVersionPattern.MatchString(row.ErasureKeyVersion) ||
		!carrierHashPattern.MatchString(row.ErasureUserKey) ||
		!carrierHashPattern.MatchString(row.ErasureSessionKey) ||
		row.AcceptedAtUnixNano == 0 || row.ObjectKey == "" {
		return fmt.Errorf("%w: invalid Replay index", ErrInvalidCarrier)
	}
	return nil
}

func (row ReplayIndex) LogicalKey() string {
	return strings.Join([]string{
		row.TenantID,
		row.Application,
		row.SessionID,
		row.RecordingID,
		strconv.FormatUint(uint64(row.Sequence), 10),
	}, "\x00")
}

type IndexStore interface {
	Start(context.Context) error
	BeginPending(context.Context, ReplayIndex) (EnsureOutcome, error)
	PublishReady(context.Context, ReplayIndex) (EnsureOutcome, error)
	Tombstone(context.Context, ReplayIndex) error
	Shutdown(context.Context) error
}

type leaseState struct {
	AcceptedAtUnixNano uint64
	ObjectStored       bool
}

type leaseToken struct {
	Key       string
	Owner     string
	FenceKeys []string
}

type LeaseStore interface {
	Start(context.Context) error
	AcquireSequence(context.Context, ReplayIndex) (leaseToken, leaseState, error)
	Renew(context.Context, leaseToken) error
	MarkObjectStored(context.Context, leaseToken) error
	ClearObjectStored(context.Context, leaseToken) error
	Release(context.Context, leaseToken) error
	Shutdown(context.Context) error
}

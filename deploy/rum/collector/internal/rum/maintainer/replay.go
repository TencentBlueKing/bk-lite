package maintainer

import (
	"regexp"
	"time"
)

var (
	identityDigest  = regexp.MustCompile(`^[0-9a-f]{64}$`)
	identityVersion = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,32}$`)
)

// ReplayIndex is one Replay object row used by orphan reconcile.
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

func (index ReplayIndex) Record() ReplayRecord {
	return ReplayRecord{
		TenantID:           index.TenantID,
		Application:        index.Application,
		SessionID:          index.SessionID,
		RecordingID:        index.RecordingID,
		Sequence:           index.Sequence,
		Status:             index.Status,
		UpdatedAt:          time.Unix(0, int64(index.AcceptedAtUnixNano)).UTC(),
		ChecksumSHA256:     index.ChecksumSHA256,
		ObjectKey:          index.ObjectKey,
		AcceptedAtUnixNano: index.AcceptedAtUnixNano,
		ErasureKeyVersion:  index.ErasureKeyVersion,
		Version:            index.Version,
	}
}

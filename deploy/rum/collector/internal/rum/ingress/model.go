package ingress

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"net"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	KeyPrefix = "ops:rum:v2:"

	MaxActiveBrowserKeys = 2
	MaxExactOrigins      = 20
)

var (
	ErrInvalidOrigin = errors.New("origin must be an exact HTTP or HTTPS origin")
	ErrUnavailable   = errors.New("RUM admission store is unavailable")

	stableIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)
	digestPattern   = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

type Application struct {
	Name                       string
	TenantID                   string
	// OrgID scopes the application to one organization. The deployment-wide
	// registry keys by name, so an apply for another organization is rejected
	// instead of silently taking over keys, origins, and admission state.
	OrgID                      string
	Enabled                    bool
	Revision                   int64
	RequestsPerMinute          int64
	CompressedBytesPerMinute   int64
	DecompressedBytesPerMinute int64
	EventsPerMinute            int64
	BrowserKeys                []string
	BrowserKeyDigests          []string
	Origins                    []string
	LastAcceptedAt             int64
	LastStoredAt               int64
}

type FenceIdentity struct {
	Version string
	Digest  string
}

type Request struct {
	Application       string
	AuthorityTenantID string
	BrowserKey        string
	Origin            string
	CompressedBytes   int64
	DecompressedBytes int64
	EventCount        int64
	UserFences        []FenceIdentity
	SessionFences     []FenceIdentity
}

type RejectReason string

const (
	RejectNone                RejectReason = ""
	RejectApplicationNotFound RejectReason = "application_not_found"
	RejectApplicationDisabled RejectReason = "application_disabled"
	RejectBrowserKey          RejectReason = "browser_key"
	RejectOrigin              RejectReason = "origin"
	RejectErasureFence        RejectReason = "erasure_fence"
	RejectBudget              RejectReason = "budget"
)

type Decision struct {
	Allowed    bool
	Reason     RejectReason
	TenantID   string
	Revision   int64
	RetryAfter time.Duration
}

func ApplicationKey(application string) string {
	return KeyPrefix + "app:" + application
}

func ApplicationKeysKey(application string) string {
	return ApplicationKey(application) + ":keys"
}

func ApplicationKeyMaterialKey(application string) string {
	return ApplicationKey(application) + ":key_material"
}

func ApplicationOriginsKey(application string) string {
	return ApplicationKey(application) + ":origins"
}

func RateKey(application string, now time.Time) string {
	return KeyPrefix + "rate:" + application + ":" + strconv.FormatInt(now.UTC().Unix()/60, 10)
}

func ErasureFenceKey(version, digest string) string {
	return KeyPrefix + "erasure:fence:" + version + ":" + digest
}

func ValidateFenceIdentity(identity FenceIdentity) error {
	if !stableIDPattern.MatchString(identity.Version) || !digestPattern.MatchString(identity.Digest) {
		return errors.New("invalid erasure fence identity")
	}
	return nil
}

func KeyDigest(browserKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(browserKey)))
	return hex.EncodeToString(sum[:])
}

func ParseOrigin(value string) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" || value == "null" || value == "*" || strings.ContainsAny(value, "*\\") {
		return "", ErrInvalidOrigin
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
		return "", ErrInvalidOrigin
	}
	host := parsed.Hostname()
	if host == "" {
		return "", ErrInvalidOrigin
	}
	if port := parsed.Port(); port != "" {
		if _, err := strconv.ParseUint(port, 10, 16); err != nil {
			return "", ErrInvalidOrigin
		}
		host = net.JoinHostPort(strings.ToLower(host), port)
	} else if strings.Contains(host, ":") {
		host = "[" + strings.ToLower(host) + "]"
	} else {
		host = strings.ToLower(host)
	}
	return parsed.Scheme + "://" + host, nil
}

func ValidateApplication(application Application) error {
	if !stableIDPattern.MatchString(application.Name) {
		return errors.New("application name must be a stable identifier")
	}
	if !stableIDPattern.MatchString(application.TenantID) {
		return errors.New("tenant id must be a stable identifier")
	}
	if !stableIDPattern.MatchString(application.OrgID) {
		return errors.New("organization id must be a stable identifier")
	}
	if application.Revision <= 0 {
		return errors.New("revision must be positive")
	}
	if application.RequestsPerMinute <= 0 ||
		application.CompressedBytesPerMinute <= 0 ||
		application.DecompressedBytesPerMinute <= 0 ||
		application.EventsPerMinute <= 0 {
		return errors.New("all application budgets must be explicit and positive")
	}
	if len(application.BrowserKeyDigests) == 0 || len(application.BrowserKeyDigests) > MaxActiveBrowserKeys {
		return fmt.Errorf("application must have between one and %d active browser key digests", MaxActiveBrowserKeys)
	}
	for _, digest := range application.BrowserKeyDigests {
		if !digestPattern.MatchString(digest) {
			return errors.New("browser key digest must be lowercase SHA-256")
		}
	}
	if len(application.Origins) == 0 || len(application.Origins) > MaxExactOrigins {
		return fmt.Errorf("application must have between one and %d origins", MaxExactOrigins)
	}
	for _, origin := range application.Origins {
		canonical, err := ParseOrigin(origin)
		if err != nil || canonical != origin {
			return ErrInvalidOrigin
		}
	}
	return nil
}

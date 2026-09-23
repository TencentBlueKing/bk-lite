package maintainer

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type MinIOConfig struct {
	Endpoint      string
	Secure        bool
	AccessKey     string
	SecretKeyFile string
	Bucket        string
}

type MinIOStore struct {
	client *minio.Client
	bucket string
}

func NewMinIOStore(cfg MinIOConfig) (*MinIOStore, error) {
	endpoint, secure, err := parseMinIOEndpoint(cfg.Endpoint, cfg.Secure)
	if err != nil {
		return nil, err
	}
	if strings.TrimSpace(cfg.AccessKey) == "" || strings.EqualFold(cfg.AccessKey, "minioadmin") {
		return nil, errors.New("maintainer MinIO access key must be a non-root service identity")
	}
	secret, err := readCredentialFile(cfg.SecretKeyFile)
	if err != nil {
		return nil, fmt.Errorf("read maintainer MinIO secret: %w", err)
	}
	if strings.TrimSpace(cfg.Bucket) == "" {
		return nil, errors.New("maintainer MinIO bucket is required")
	}
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, secret, ""),
		Secure: secure,
	})
	if err != nil {
		return nil, err
	}
	return &MinIOStore{client: client, bucket: cfg.Bucket}, nil
}

func (store *MinIOStore) Start(ctx context.Context) error {
	exists, err := store.client.BucketExists(ctx, store.bucket)
	if err != nil {
		return err
	}
	if !exists {
		return errors.New("Replay bucket does not exist")
	}
	return nil
}

func (store *MinIOStore) DeleteAllVersions(ctx context.Context, key string) error {
	if strings.TrimSpace(key) == "" || !strings.HasSuffix(key, ".json.gz") {
		return errors.New("invalid Replay object key")
	}
	found := false
	for object := range store.client.ListObjects(ctx, store.bucket, minio.ListObjectsOptions{
		Prefix:       key,
		Recursive:    true,
		WithVersions: true,
	}) {
		if object.Err != nil {
			return object.Err
		}
		if object.Key != key {
			continue
		}
		found = true
		if err := store.client.RemoveObject(ctx, store.bucket, key, minio.RemoveObjectOptions{
			VersionID: object.VersionID,
		}); err != nil {
			return err
		}
	}
	if !found {
		return nil
	}
	info, err := store.client.StatObject(ctx, store.bucket, key, minio.StatObjectOptions{})
	if err == nil {
		return fmt.Errorf("Replay object %s still exists after version deletion (version %s)", key, info.VersionID)
	}
	response := minio.ToErrorResponse(err)
	if response.Code != "NoSuchKey" && response.Code != "NoSuchObject" && response.StatusCode != 404 {
		return err
	}
	return nil
}

func (store *MinIOStore) Stat(ctx context.Context, key string) (ObjectState, error) {
	info, err := store.client.StatObject(ctx, store.bucket, key, minio.StatObjectOptions{})
	if err != nil {
		response := minio.ToErrorResponse(err)
		if response.Code == "NoSuchKey" || response.Code == "NoSuchObject" || response.StatusCode == 404 {
			return ObjectState{}, nil
		}
		return ObjectState{}, err
	}
	checksum := metadataValue(info, "sha256")
	acceptedAt, _ := strconv.ParseUint(metadataValue(info, "accepted-at-unix-nano"), 10, 64)
	return ObjectState{
		Exists:             true,
		ChecksumSHA256:     checksum,
		AcceptedAtUnixNano: acceptedAt,
		ErasureKeyVersion:  metadataValue(info, "erasure-key-version"),
	}, nil
}

func (store *MinIOStore) ListAfter(
	ctx context.Context,
	cursor string,
	visit func(key string, modifiedAt time.Time) error,
) error {
	for object := range store.client.ListObjects(ctx, store.bucket, minio.ListObjectsOptions{
		Recursive: true,
	}) {
		if object.Err != nil {
			return object.Err
		}
		if object.Key <= cursor || !strings.HasSuffix(object.Key, ".json.gz") {
			continue
		}
		if err := visit(object.Key, object.LastModified.UTC()); err != nil {
			return err
		}
	}
	return nil
}

func metadataValue(info minio.ObjectInfo, key string) string {
	if value := info.UserMetadata[key]; value != "" {
		return value
	}
	return info.Metadata.Get("X-Amz-Meta-" + key)
}

func parseMinIOEndpoint(raw string, configuredSecure bool) (string, bool, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "", false, errors.New("minio endpoint is required")
	}
	if !strings.Contains(raw, "://") {
		parsed, err := url.Parse("//" + raw)
		if err != nil || parsed.Host == "" || parsed.Path != "" || parsed.RawQuery != "" || parsed.Fragment != "" {
			return "", false, errors.New("minio endpoint must be a host:port")
		}
		return raw, configuredSecure, nil
	}
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Host == "" || (parsed.Path != "" && parsed.Path != "/") || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", false, errors.New("minio endpoint must be an HTTP(S) URL without path")
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return "", false, errors.New("minio endpoint must use HTTP(S)")
	}
	if configuredSecure && parsed.Scheme != "https" {
		return "", false, errors.New("minio secure mode conflicts with HTTP endpoint")
	}
	return parsed.Host, parsed.Scheme == "https", nil
}

func readCredentialFile(path string) (string, error) {
	info, err := os.Stat(path)
	if err != nil {
		return "", err
	}
	if info.Mode().Perm()&0o077 != 0 {
		return "", errors.New("credential file permissions must be 0600 or stricter")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	value := strings.TrimSpace(string(raw))
	if len(value) < 16 {
		return "", errors.New("credential must contain at least 16 characters")
	}
	return value, nil
}

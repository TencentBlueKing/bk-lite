package rumreplayexporter

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type minIOObjectStore struct {
	client *minio.Client
	bucket string
}

func newMinIOObjectStore(cfg *Config) (*minIOObjectStore, error) {
	endpoint, secure, err := parseMinIOEndpoint(cfg.MinIOEndpoint, cfg.MinIOSecure)
	if err != nil {
		return nil, err
	}
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinIOAccessKey, string(cfg.MinIOSecretKey), ""),
		Secure: secure,
	})
	if err != nil {
		return nil, fmt.Errorf("create MinIO client: %w", err)
	}
	return &minIOObjectStore{client: client, bucket: cfg.MinIOBucket}, nil
}

func (store *minIOObjectStore) Start(ctx context.Context) error {
	_ = ctx
	// A bucket existence probe requires ListBucket in S3-compatible IAM. The
	// Gateway deliberately has only Put/Get/Stat; the first queued segment is
	// the connectivity and credential probe.
	return nil
}

func (store *minIOObjectStore) Shutdown(context.Context) error { return nil }

func (store *minIOObjectStore) Ensure(ctx context.Context, write ObjectWrite) (EnsureOutcome, error) {
	if write.Bucket != store.bucket || write.ContentType != "application/octet-stream" || write.ContentEncoding != "" {
		return EnsureUnknown, fmt.Errorf("%w: invalid object transport metadata", ErrInvalidCarrier)
	}
	if write.Key == "" || write.LogicalPrefix == "" || !strings.HasPrefix(write.Key, write.LogicalPrefix) || !strings.HasSuffix(write.Key, ".json.gz") {
		return EnsureUnknown, fmt.Errorf("%w: invalid object key", ErrInvalidCarrier)
	}
	if write.Metadata["sha256"] != write.ChecksumSHA256 || !carrierHashPattern.MatchString(write.ChecksumSHA256) {
		return EnsureUnknown, fmt.Errorf("%w: invalid object checksum metadata", ErrInvalidCarrier)
	}
	acceptedAt, acceptedErr := strconv.ParseUint(write.Metadata["accepted-at-unix-nano"], 10, 64)
	if acceptedErr != nil || acceptedAt == 0 || !carrierVersionPattern.MatchString(write.Metadata["erasure-key-version"]) {
		return EnsureUnknown, fmt.Errorf("%w: invalid object erasure metadata", ErrInvalidCarrier)
	}

	if _, err := store.client.StatObject(ctx, store.bucket, write.Key, minio.StatObjectOptions{}); err == nil {
		return store.verifyExisting(ctx, write)
	} else {
		response := minio.ToErrorResponse(err)
		if response.Code != "NoSuchKey" && response.Code != "NoSuchObject" && response.StatusCode != 404 {
			return EnsureUnknown, fmt.Errorf("stat Replay object before put: %w", err)
		}
	}

	options := minio.PutObjectOptions{
		ContentType:      write.ContentType,
		ContentEncoding:  "",
		UserMetadata:     copyStringMap(write.Metadata),
		DisableMultipart: true,
	}
	options.SetMatchETagExcept("*")
	if _, err := store.client.PutObject(
		ctx,
		store.bucket,
		write.Key,
		bytes.NewReader(write.Body),
		int64(len(write.Body)),
		options,
	); err != nil {
		response := minio.ToErrorResponse(err)
		if response.Code == "PreconditionFailed" || response.Code == "ConditionalRequestConflict" {
			return store.verifyExisting(ctx, write)
		}
		return EnsureUnknown, fmt.Errorf("put Replay object: %w", err)
	}
	return EnsureCreated, nil
}

func (store *minIOObjectStore) verifyExisting(ctx context.Context, write ObjectWrite) (EnsureOutcome, error) {
	info, err := store.client.StatObject(ctx, store.bucket, write.Key, minio.StatObjectOptions{})
	if err != nil {
		return EnsureUnknown, fmt.Errorf("stat Replay object: %w", err)
	}
	checksum := info.UserMetadata["sha256"]
	if checksum == "" {
		checksum = info.Metadata.Get("X-Amz-Meta-Sha256")
	}
	if checksum != write.ChecksumSHA256 {
		return EnsureUnknown, ErrChecksumConflict
	}
	acceptedAt := info.UserMetadata["accepted-at-unix-nano"]
	if acceptedAt == "" {
		acceptedAt = info.Metadata.Get("X-Amz-Meta-Accepted-At-Unix-Nano")
	}
	keyVersion := info.UserMetadata["erasure-key-version"]
	if keyVersion == "" {
		keyVersion = info.Metadata.Get("X-Amz-Meta-Erasure-Key-Version")
	}
	if acceptedAt != write.Metadata["accepted-at-unix-nano"] || keyVersion != write.Metadata["erasure-key-version"] {
		return EnsureUnknown, ErrChecksumConflict
	}
	if info.ContentEncoding != "" || info.ContentType != write.ContentType || info.Size != int64(len(write.Body)) {
		return EnsureUnknown, errors.New("existing Replay object violates immutable storage metadata")
	}
	return EnsureReused, nil
}

func copyStringMap(input map[string]string) map[string]string {
	result := make(map[string]string, len(input))
	for key, value := range input {
		result[key] = value
	}
	return result
}

package jetstream

import (
	"errors"
	"io"
	"testing"

	"github.com/nats-io/nats.go"
)

type stubObjectStoreImpl struct{}

func (stubObjectStoreImpl) Put(obj *nats.ObjectMeta, reader io.Reader, opts ...nats.ObjectOpt) (*nats.ObjectInfo, error) {
	return nil, nil
}
func (stubObjectStoreImpl) Get(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
	return nil, nil
}
func (stubObjectStoreImpl) PutBytes(name string, data []byte, opts ...nats.ObjectOpt) (*nats.ObjectInfo, error) {
	return nil, nil
}
func (stubObjectStoreImpl) GetBytes(name string, opts ...nats.GetObjectOpt) ([]byte, error) {
	return nil, nil
}
func (stubObjectStoreImpl) PutString(name string, data string, opts ...nats.ObjectOpt) (*nats.ObjectInfo, error) {
	return nil, nil
}
func (stubObjectStoreImpl) GetString(name string, opts ...nats.GetObjectOpt) (string, error) {
	return "", nil
}
func (stubObjectStoreImpl) PutFile(file string, opts ...nats.ObjectOpt) (*nats.ObjectInfo, error) {
	return nil, nil
}
func (stubObjectStoreImpl) GetFile(name, file string, opts ...nats.GetObjectOpt) error { return nil }
func (stubObjectStoreImpl) GetInfo(name string, opts ...nats.GetObjectInfoOpt) (*nats.ObjectInfo, error) {
	return nil, nil
}
func (stubObjectStoreImpl) UpdateMeta(name string, meta *nats.ObjectMeta) error { return nil }
func (stubObjectStoreImpl) Delete(name string) error                            { return nil }
func (stubObjectStoreImpl) AddLink(name string, obj *nats.ObjectInfo) (*nats.ObjectInfo, error) {
	return nil, nil
}
func (stubObjectStoreImpl) AddBucketLink(name string, bucket nats.ObjectStore) (*nats.ObjectInfo, error) {
	return nil, nil
}
func (stubObjectStoreImpl) Seal() error                                             { return nil }
func (stubObjectStoreImpl) Watch(opts ...nats.WatchOpt) (nats.ObjectWatcher, error) { return nil, nil }
func (stubObjectStoreImpl) List(opts ...nats.ListObjectsOpt) ([]*nats.ObjectInfo, error) {
	return nil, nil
}
func (stubObjectStoreImpl) Status() (nats.ObjectStoreStatus, error) { return nil, nil }

type stubObjectStoreManager struct {
	objectStore       nats.ObjectStore
	objectStoreErr    error
	createdStore      nats.ObjectStore
	createErr         error
	createdBucketName string
}

func (s *stubObjectStoreManager) ObjectStore(bucket string) (nats.ObjectStore, error) {
	s.createdBucketName = bucket
	return s.objectStore, s.objectStoreErr
}

func (s *stubObjectStoreManager) CreateObjectStore(cfg *nats.ObjectStoreConfig) (nats.ObjectStore, error) {
	s.createdBucketName = cfg.Bucket
	return s.createdStore, s.createErr
}

func TestEnsureObjectStoreUsesExistingBucket(t *testing.T) {
	store := stubObjectStoreImpl{}
	manager := &stubObjectStoreManager{objectStore: store}

	got, err := ensureObjectStore(manager, "artifacts")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if got != store {
		t.Fatalf("expected existing store to be reused")
	}
	if manager.createdBucketName != "artifacts" {
		t.Fatalf("expected bucket artifacts, got %q", manager.createdBucketName)
	}
}

func TestEnsureObjectStoreReturnsBucketNotFoundError(t *testing.T) {
	manager := &stubObjectStoreManager{
		objectStoreErr: nats.ErrBucketNotFound,
	}

	_, err := ensureObjectStore(manager, "downloads")
	if err == nil {
		t.Fatal("expected error for missing bucket")
	}
	if !errors.Is(err, nats.ErrBucketNotFound) {
		t.Fatalf("expected wrapped ErrBucketNotFound, got %v", err)
	}
}

func TestEnsureObjectStoreReturnsAccessError(t *testing.T) {
	manager := &stubObjectStoreManager{objectStoreErr: errors.New("jetstream offline")}

	_, err := ensureObjectStore(manager, "downloads")
	if err == nil {
		t.Fatal("expected access error")
	}
}

func TestNewJetStreamClientFromContextReturnsClientWithStore(t *testing.T) {
	store := stubObjectStoreImpl{}
	manager := &stubObjectStoreManager{objectStore: store}

	client, err := newJetStreamClientFromContext(nil, manager, "downloads")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if client == nil || client.objectStore == nil {
		t.Fatalf("expected client with object store, got %#v", client)
	}
}

func TestNewJetStreamClientUsesJetStreamFactory(t *testing.T) {
	original := jetStreamFromConn
	store := stubObjectStoreImpl{}
	jetStreamFromConn = func(nc *nats.Conn) (objectStoreManager, error) {
		return &stubObjectStoreManager{objectStore: store}, nil
	}
	defer func() { jetStreamFromConn = original }()

	client, err := NewJetStreamClient(nil, "downloads")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if client == nil || client.objectStore == nil {
		t.Fatalf("expected client with object store, got %#v", client)
	}
}

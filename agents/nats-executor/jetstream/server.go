package jetstream

import (
	"fmt"
	"io"
	"nats-executor/logger"
	"os"

	"github.com/nats-io/nats.go"
)

type JetStreamClient struct {
	nc          *nats.Conn
	js          nats.JetStreamContext
	objectStore nats.ObjectStore
}

func NewJetStreamClient(nc *nats.Conn, bucketName string) (*JetStreamClient, error) {
	js, err := nc.JetStream()
	if err != nil {
		return nil, fmt.Errorf("failed to get JetStream context: %v", err)
	}

	store, err := js.ObjectStore(bucketName)
	if err != nil {
		if err == nats.ErrBucketNotFound {
			store, err = js.CreateObjectStore(&nats.ObjectStoreConfig{
				Bucket:      bucketName,
				Description: "File distribution bucket",
			})
		}
		if err != nil {
			return nil, fmt.Errorf("failed to create or access object store: %v", err)
		}
	}

	return &JetStreamClient{nc: nc, js: js, objectStore: store}, nil
}

func (jsc *JetStreamClient) DownloadToFile(fileKey, targetPath, fileName string) error {
	obj, err := jsc.objectStore.Get(fileKey)
	if err != nil {
		return fmt.Errorf("failed to get object from store with key %s: %v", fileKey, err)
	}
	defer obj.Close()

	fullPath := fmt.Sprintf("%s/%s", targetPath, fileName)

	file, err := os.Create(fullPath)
	if err != nil {
		return fmt.Errorf("failed to create file at %s: %v", fullPath, err)
	}
	defer file.Close()

	written, err := io.Copy(file, obj)
	if err != nil {
		return fmt.Errorf("failed to write file: %v", err)
	}

	logger.Debugf("[JetStream] File successfully downloaded to %s (%d bytes)", fullPath, written)
	return nil
}

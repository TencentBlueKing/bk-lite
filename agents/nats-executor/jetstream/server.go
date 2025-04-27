package jetstream

import (
	"fmt"
	"github.com/nats-io/nats.go"
	"io"
	"log"
	"os"
)

// JetStreamClient 封装了 JetStream 和 ObjectStore 的操作
type JetStreamClient struct {
	nc          *nats.Conn
	js          nats.JetStreamContext
	objectStore nats.ObjectStore
}

// NewJetStreamClient 创建新的客户端实例
func NewJetStreamClient(nc *nats.Conn, bucketName string) (*JetStreamClient, error) {
	// 获取 JetStream 上下文
	js, err := nc.JetStream()
	if err != nil {
		return nil, fmt.Errorf("failed to get JetStream context: %v", err)
	}

	// 尝试获取 ObjectStore，若不存在则创建新的
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

	// 返回封装的客户端
	return &JetStreamClient{nc: nc, js: js, objectStore: store}, nil
}

// DownloadToFile 从 ObjectStore 下载文件并保存到本地指定路径
func (jsc *JetStreamClient) DownloadToFile(fileKey, targetPath, fileName string) error {
	// 获取对象
	obj, err := jsc.objectStore.Get(fileKey)
	if err != nil {
		return fmt.Errorf("failed to get object from store with key %s: %v", fileKey, err)
	}
	defer obj.Close() // 确保关闭对象

	// 读取对象内容
	data, err := io.ReadAll(obj)
	if err != nil {
		return fmt.Errorf("failed to read object data: %v", err)
	}

	// 确定保存路径
	fullPath := fmt.Sprintf("%s/%s", targetPath, fileName)

	// 写入文件到本地
	err = os.WriteFile(fullPath, data, 0644)
	if err != nil {
		return fmt.Errorf("failed to write file to target path %s: %v", fullPath, err)
	}

	log.Printf("File successfully downloaded to %s", fullPath)
	return nil
}

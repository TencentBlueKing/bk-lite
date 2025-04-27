package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/nats-io/nats.go"
	"gopkg.in/yaml.v3"

	"nats-executor/local"
	"nats-executor/ssh"
)

type Config struct {
	NATSUrls       string `yaml:"nats_urls"`
	NATSInstanceID string `yaml:"nats_instanceId"`
}

func loadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}
	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}
	return &cfg, nil
}

func main() {
	configPath := flag.String("config", "", "Path to the config file (YAML format)")
	flag.Parse()

	if *configPath == "" {
		log.Fatal("Please specify the config file path using --config")
	}

	cfg, err := loadConfig(*configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)

	}

	log.Printf("Connecting to NATS server at %s", cfg.NATSUrls)
	opts := []nats.Option{
		nats.Name("nats-executor"),
		nats.Compression(true),
	}

	nc, err := nats.Connect(cfg.NATSUrls, opts...)
	if err != nil {
		log.Fatalf("Failed to connect to NATS server: %v", err)
	}
	defer nc.Close()
	log.Println("Connected to NATS server")

	// 注册各类订阅
	subscribeLocalExecutor(nc, &cfg.NATSInstanceID)
	subscribeSSHExecutor(nc, &cfg.NATSInstanceID)
	subscribeDownloadToLocal(nc, &cfg.NATSInstanceID)
	subscribeDownloadToRemote(nc, &cfg.NATSInstanceID)

	log.Println("Waiting for messages...")
	select {}
}

func subscribeLocalExecutor(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("local.execute.%s", *instanceId)
	log.Printf("Subscribing to subject: %s", subject)
	nc.Subscribe(subject, func(msg *nats.Msg) {
		// 定义一个临时结构来接收请求方格式
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("Error unmarshalling incoming message: %v", err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("No arguments received")
			return
		}
		var localExecuteRequest local.ExecuteRequest
		if err := json.Unmarshal(incoming.Args[0], &localExecuteRequest); err != nil {
			log.Printf("Error unmarshalling first arg to local.ExecuteRequest: %v", err)
			return
		}

		log.Printf("Received command: %s", localExecuteRequest.Command)
		responseData := local.Execute(localExecuteRequest, *instanceId)
		log.Printf("Publishing response to subject: local.execute.response")

		responseContent, _ := json.Marshal(responseData)
		if err := msg.Respond(responseContent); err != nil {
			log.Printf("Error publishing response: %v", err)
		}

	})
}

func subscribeSSHExecutor(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("ssh.execute.%s", *instanceId)
	log.Printf("Subscribing to subject: %s", subject)
	nc.Subscribe(subject, func(msg *nats.Msg) {
		// 解析 request 的标准结构
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("Error unmarshalling incoming message: %v", err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("No arguments received")
			return
		}

		var sshExecuteRequest ssh.ExecuteRequest
		if err := json.Unmarshal(incoming.Args[0], &sshExecuteRequest); err != nil {
			log.Printf("Error unmarshalling first arg to ssh.ExecuteRequest: %v", err)
			return
		}

		log.Printf("Received SSH command: %s", sshExecuteRequest.Command)
		responseData := ssh.Execute(sshExecuteRequest, *instanceId)
		log.Printf("Publishing SSH response using msg.Respond")

		responseContent, _ := json.Marshal(responseData)
		if err := msg.Respond(responseContent); err != nil {
			log.Printf("Error responding to SSH request: %v", err)
		}
	})
}

func subscribeDownloadToLocal(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("download.local.%s", *instanceId)
	log.Printf("Subscribing to subject: %s", subject)

	nc.Subscribe(subject, func(msg *nats.Msg) {
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("Error unmarshalling incoming message: %v", err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("No arguments received")
			return
		}

		var downloadRequest local.DownloadFileRequest
		if err := json.Unmarshal(incoming.Args[0], &downloadRequest); err != nil {
			log.Printf("Error unmarshalling first arg to DownloadFileRequest: %v", err)
			return
		}

		log.Printf("Starting download from bucket %s, file %s to local path %s", downloadRequest.BucketName, downloadRequest.FileKey, downloadRequest.TargetPath)

		// ✅ 直接调用 DownloadFile，返回 ExecuteResponse
		resp := local.DownloadFile(downloadRequest, nc, *instanceId)

		responseContent, _ := json.Marshal(resp)
		if err := msg.Respond(responseContent); err != nil {
			log.Printf("Error responding to download request: %v", err)
		}
	})
}

func subscribeDownloadToRemote(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("download.remote.%s", *instanceId)
	log.Printf("Subscribing to subject: %s", subject)

	nc.Subscribe(subject, func(msg *nats.Msg) {
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("Error unmarshalling incoming message: %v", err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("No arguments received")
			return
		}

		var downloadRequest ssh.DownloadFileRequest

		if err := json.Unmarshal(incoming.Args[0], &downloadRequest); err != nil {
			log.Printf("Error unmarshalling first arg to DownloadFileRequest: %v", err)
			return
		}

		log.Printf("Starting download from bucket %s, file %s to local path %s", downloadRequest.BucketName, downloadRequest.FileKey, downloadRequest.TargetPath)

		// Step 1: 下载文件到本地
		localdownloadRequest := local.DownloadFileRequest{
			BucketName:     downloadRequest.BucketName,
			FileKey:        downloadRequest.FileKey,
			FileName:       downloadRequest.FileName,
			TargetPath:     downloadRequest.TargetPath,
			ExecuteTimeout: downloadRequest.ExecuteTimeout,
		}

		resp := local.DownloadFile(localdownloadRequest, nc, *instanceId)
		if !resp.Success {
			log.Printf("Error downloading file: %s", resp.Output)
			return
		}

		// 使用sshpass处理带密码的scp传输
		scpCommand := fmt.Sprintf("sshpass -p '%s' scp -o StrictHostKeyChecking=no %s/%s %s@%s:%s",
			downloadRequest.Password,
			localdownloadRequest.TargetPath,
			localdownloadRequest.FileName,
			downloadRequest.User,
			downloadRequest.Host,
			downloadRequest.TargetPath)

		localExecuteRequest := local.ExecuteRequest{
			Command:        scpCommand,
			ExecuteTimeout: downloadRequest.ExecuteTimeout,
		}

		log.Printf("Starting file transfer to remote host: %s@%s:%s", downloadRequest.User, downloadRequest.Host, downloadRequest.TargetPath)
		responseData := local.Execute(localExecuteRequest, *instanceId)

		responseContent, _ := json.Marshal(responseData)
		if err := msg.Respond(responseContent); err != nil {
			log.Printf("Error responding to download request: %v", err)
		}
	})
}

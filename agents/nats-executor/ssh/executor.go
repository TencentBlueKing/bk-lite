package ssh

import (
	"context"
	"fmt"
	"github.com/melbahja/goph"
	"golang.org/x/crypto/ssh"
	"log"
	"time"
)

func Execute(req ExecuteRequest, instanceId string) ExecuteResponse {
	auth := goph.Password(req.Password)
	client, err := goph.NewConn(&goph.Config{
		User:     req.User,
		Addr:     req.Host,
		Port:     22,
		Auth:     auth,
		Timeout:  30 * time.Second,
		Callback: ssh.InsecureIgnoreHostKey(), // 👈 跳过 known_hosts 验证
	})

	if err != nil {
		log.Printf("Failed to create new SSH client: %v", err)
		return ExecuteResponse{
			InstanceId: instanceId,
			Success:    false,
			Output:     fmt.Sprintf("Failed to create new SSH client: %v", err),
		}
	}

	defer client.Close()

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	out, err := client.RunContext(ctx, req.Command)
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			log.Printf("Command timed out")
		} else {
			log.Printf("Command execution error: %v", err)
		}
		return ExecuteResponse{
			Output:     string(out),
			InstanceId: instanceId,
			Success:    false,
		}
	}

	return ExecuteResponse{
		Output:     string(out),
		InstanceId: instanceId,
		Success:    true,
	}
}

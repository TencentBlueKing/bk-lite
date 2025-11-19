def main():
    print("Hello from container-manager!")


if __name__ == "__main__":
    # 1. 使用 Fire 做一个 Class 模式的 CLI 入口
    # 2. 提供 runserver 的 cli
    # 3. Server启动后，绑定到环境变量指定的 Nats 的 NS 和 IP 及端口地址，TLS 可选
    # 4. 提供docker相关管理能力，包括： compose-start、 compose-stop、 compose-restart、 compose-status
    # 5. 提供Kubernetes相关管理能力，包括: start-k8s-app、 stop-k8s-app、 restart-k8s-app、 k8s-app-status

    main()

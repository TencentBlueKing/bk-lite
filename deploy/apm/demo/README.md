# 本机 APM 演示流量

这套夹具在现有 `deploy/apm` 数据面上启动 5 个带 OpenTelemetry SDK 的微服务和一个持续流量发生器。它产生正常、慢调用、支付失败和库存失败，用于本机体验应用/实例发现、服务 RED、端点、Trace/Span、错误、拓扑、SLO、策略与事件。

```bash
cd deploy/apm
make demo-up
make demo-ps
make demo-logs
make demo-down
```

`demo-up` 会幂等创建组织 `1` 下的 `apm-demo-shop` 应用，等待真实遥测进入 VictoriaTraces，再对账服务目录并创建两个 SLO 和两条不发送外部通知的演示策略。Storefront 也映射到 `http://127.0.0.1:18081`，可手工请求：

```bash
curl http://127.0.0.1:18081/api/products
curl -X POST 'http://127.0.0.1:18081/api/checkout?scenario=payment-failure'
```

`/api/products` 会让 catalog 发出模拟 **mysql** Client Span（`db.system=mysql`、`server.address`、`server.port`、`db.name`），storefront 的 `/api/profile` 发出 redis Client Span。这些下游不会进入服务目录，只应出现在服务拓扑的推断节点上；调查栏展示 Span 里实际有的地址和库名。

停止演示容器不会删除 VictoriaTraces 或控制面中的历史数据。`make demo-up` 可安全重复执行；仅需重新对账/播种控制面时运行 `make demo-seed`。

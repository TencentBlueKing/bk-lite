.PHONY: tidy test test-controller test-maintainer build build-gateway build-controller build-maintainer validate-config

tidy:
	go mod tidy

test:
	go test ./internal/rum/components/... ./internal/rum/ingress/... ./internal/rumprivacy/... ./pkg/rum/...

test-controller:
	go test ./internal/rum/controller/... ./pkg/rum/wire/...

test-maintainer:
	go test ./internal/rum/maintainer/... ./pkg/rum/replayindex/...

build: build-gateway build-controller build-maintainer

build-gateway:
	mkdir -p _build
	go build -o _build/bklite-rum-gateway ./cmd/bklite-rum-gateway

build-controller:
	mkdir -p _build
	go build -o _build/bklite-rum-controller ./cmd/bklite-rum-controller

build-maintainer:
	mkdir -p _build
	go build -o _build/bklite-rum-maintainer ./cmd/bklite-rum-maintainer

validate-config: build-gateway
	set -a; . ./env/rum.gateway.dev.env.example; set +a; \
	mkdir -p "$$RUM_QUEUE_DIR"; \
	./_build/bklite-rum-gateway validate --config=./otel/rum.gateway.dev.yaml

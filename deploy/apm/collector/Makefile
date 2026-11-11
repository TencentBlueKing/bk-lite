.PHONY: test build validate

COLLECTOR_IMAGE ?= bklite/apm-otel-collector:0.153.0-bklite.3

test:
	cd exporter/natsjetstreamexporter && go test ./...
	cd receiver/natsjetstreamreceiver && go test ./...
	cd processor/traceguardprocessor && go test ./...

build:
	docker build -t $(COLLECTOR_IMAGE) .

validate: build
	docker run --rm \
		-e APM_CLOUD_REGION_ID=local \
		-e APM_NATS_URL=nats://127.0.0.1:4222 \
		-e APM_NATS_CREDENTIALS_FILE= \
		-e APM_NATS_CA_FILE= \
		-e APM_NATS_CERT_FILE= \
		-e APM_NATS_KEY_FILE= \
		-e APM_NATS_TLS_SERVER_NAME= \
		-e APM_NATS_MAX_MESSAGE_BYTES=8388608 \
		-e APM_COLLECTOR_MEMORY_LIMIT_MIB=128 \
		-e APM_COLLECTOR_MEMORY_SPIKE_MIB=32 \
		-e APM_TRACE_BATCH_SIZE=32 \
		-e APM_TRACE_BATCH_MAX_SIZE=64 \
		-e APM_REGIONAL_QUEUE_MAX_BYTES=1048576 \
		-v "$(CURDIR)/../otel:/etc/bklite-apm:ro" \
		$(COLLECTOR_IMAGE) \
		validate --config=/etc/bklite-apm/regional.yaml
	docker run --rm \
		-e APM_NATS_URL=nats://127.0.0.1:4222 \
		-e APM_NATS_STREAM=APM_TRACES \
		-e APM_NATS_CONSUMER=BKLITE_APM_SYSTEM \
		-e APM_NATS_CREDENTIALS_FILE= \
		-e APM_NATS_CA_FILE= \
		-e APM_NATS_CERT_FILE= \
		-e APM_NATS_KEY_FILE= \
		-e APM_NATS_TLS_SERVER_NAME= \
		-e APM_NATS_MAX_ACK_PENDING=32 \
		-e APM_COLLECTOR_MEMORY_LIMIT_MIB=128 \
		-e APM_COLLECTOR_MEMORY_SPIKE_MIB=32 \
		-e APM_VICTORIATRACES_OTLP_ENDPOINT=http://127.0.0.1:10428/insert/opentelemetry/v1/traces \
		-v "$(CURDIR)/../otel:/etc/bklite-apm:ro" \
		$(COLLECTOR_IMAGE) \
		validate --config=/etc/bklite-apm/system.yaml
	docker run --rm \
		-e APM_NATS_URL=nats://127.0.0.1:4222 \
		-e APM_NATS_STREAM=APM_TRACES \
		-e APM_NATS_CONSUMER=BKLITE_APM_AGGREGATE \
		-e APM_NATS_CREDENTIALS_FILE= \
		-e APM_NATS_CA_FILE= \
		-e APM_NATS_CERT_FILE= \
		-e APM_NATS_KEY_FILE= \
		-e APM_NATS_TLS_SERVER_NAME= \
		-e APM_NATS_MAX_ACK_PENDING=32 \
		-e APM_COLLECTOR_MEMORY_LIMIT_MIB=128 \
		-e APM_COLLECTOR_MEMORY_SPIKE_MIB=32 \
		-e AGG_VICTORIAMETRICS_WRITE_URL=http://127.0.0.1:9/api/v1/write \
		-e APM_AGG_SHARD=validate-shard \
		-v "$(CURDIR)/../otel:/etc/bklite-apm:ro" \
		$(COLLECTOR_IMAGE) \
		validate --config=/etc/bklite-apm/aggregate.yaml
	docker run --rm \
		-e APM_NATS_URL=nats://127.0.0.1:4222 \
		-e APM_NATS_STREAM=APM_TRACES \
		-e APM_NATS_CONSUMER=BKLITE_APM_AGGREGATE \
		-e APM_NATS_CREDENTIALS_FILE= \
		-e APM_NATS_CA_FILE= \
		-e APM_NATS_CERT_FILE= \
		-e APM_NATS_KEY_FILE= \
		-e APM_NATS_TLS_SERVER_NAME= \
		-e APM_NATS_MAX_ACK_PENDING=32 \
		-e APM_COLLECTOR_MEMORY_LIMIT_MIB=128 \
		-e APM_COLLECTOR_MEMORY_SPIKE_MIB=32 \
		-e AGG_VICTORIAMETRICS_WRITE_URL=http://127.0.0.1:9/api/v1/write \
		-e APM_AGG_SHARD=validate-shard \
		-e AGG_VICTORIAMETRICS_USER=validate-user \
		-e AGG_VICTORIAMETRICS_PASSWORD=validate-only-password \
		-v "$(CURDIR)/../otel:/etc/bklite-apm:ro" \
		$(COLLECTOR_IMAGE) \
		validate --config=/etc/bklite-apm/aggregate.yaml --config=/etc/bklite-apm/aggregate-auth.yaml
	url_missing=$$(docker run --rm \
		-e APM_NATS_URL=nats://127.0.0.1:4222 \
		-e APM_NATS_STREAM=APM_TRACES \
		-e APM_NATS_CONSUMER=BKLITE_APM_AGGREGATE \
		-e APM_NATS_CREDENTIALS_FILE= \
		-e APM_NATS_CA_FILE= \
		-e APM_NATS_CERT_FILE= \
		-e APM_NATS_KEY_FILE= \
		-e APM_NATS_TLS_SERVER_NAME= \
		-e APM_NATS_MAX_ACK_PENDING=32 \
		-e APM_COLLECTOR_MEMORY_LIMIT_MIB=128 \
		-e APM_COLLECTOR_MEMORY_SPIKE_MIB=32 \
		-e APM_AGG_SHARD=validate-shard \
		-v "$(CURDIR)/../otel:/etc/bklite-apm:ro" \
		$(COLLECTOR_IMAGE) \
		validate --config=/etc/bklite-apm/aggregate.yaml 2>&1 || true); \
	printf '%s\n' "$$url_missing"; \
	printf '%s\n' "$$url_missing" | grep -q "invalid endpoint" || { \
		echo "aggregate.yaml must reject an empty AGG_VICTORIAMETRICS_WRITE_URL" >&2; \
		exit 1; \
	}
	shard_missing=$$(docker run --rm \
		-e APM_NATS_URL=nats://127.0.0.1:4222 \
		-e APM_NATS_STREAM=APM_TRACES \
		-e APM_NATS_CONSUMER=BKLITE_APM_AGGREGATE \
		-e APM_NATS_CREDENTIALS_FILE= \
		-e APM_NATS_CA_FILE= \
		-e APM_NATS_CERT_FILE= \
		-e APM_NATS_KEY_FILE= \
		-e APM_NATS_TLS_SERVER_NAME= \
		-e APM_NATS_MAX_ACK_PENDING=32 \
		-e APM_COLLECTOR_MEMORY_LIMIT_MIB=128 \
		-e APM_COLLECTOR_MEMORY_SPIKE_MIB=32 \
		-e AGG_VICTORIAMETRICS_WRITE_URL=http://127.0.0.1:9/api/v1/write \
		-v "$(CURDIR)/../otel:/etc/bklite-apm:ro" \
		$(COLLECTOR_IMAGE) \
		validate --config=/etc/bklite-apm/aggregate.yaml 2>&1 || true); \
	printf '%s\n' "$$shard_missing"; \
	printf '%s\n' "$$shard_missing" | grep -q "empty key or value" || { \
		echo "aggregate.yaml must reject an empty APM_AGG_SHARD" >&2; \
		exit 1; \
	}

.PHONY: test build validate

test:
	cd exporter/natsjetstreamexporter && go test ./...
	cd receiver/natsjetstreamreceiver && go test ./...
	cd processor/traceguardprocessor && go test ./...

build:
	docker build -t bklite/apm-otel-collector:0.153.0-bklite.1 .

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
		bklite/apm-otel-collector:0.153.0-bklite.1 \
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
		bklite/apm-otel-collector:0.153.0-bklite.1 \
		validate --config=/etc/bklite-apm/system.yaml

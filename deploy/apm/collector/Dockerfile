FROM public.ecr.aws/docker/library/golang:1.25.6-alpine AS builder

ARG GOPROXY=https://goproxy.cn,direct
ENV GOPROXY=${GOPROXY}
RUN apk add --no-cache ca-certificates git
RUN go install go.opentelemetry.io/collector/cmd/builder@v0.153.0

WORKDIR /src
COPY . .
RUN /go/bin/builder --config builder-config.yaml

FROM scratch
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder /src/_build/bklite-otelcol /bklite-otelcol
USER 65532:65532
ENTRYPOINT ["/bklite-otelcol"]

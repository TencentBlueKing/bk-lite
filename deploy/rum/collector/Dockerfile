ARG GO_IMAGE=public.ecr.aws/docker/library/golang:1.26.8-alpine

FROM ${GO_IMAGE} AS builder

ARG GOPROXY=https://goproxy.cn,direct
ENV GOPROXY=${GOPROXY} \
    GOTOOLCHAIN=local \
    CGO_ENABLED=0
RUN apk add --no-cache ca-certificates git

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN mkdir -p /out \
    && go build -trimpath -ldflags="-s -w" -o /out/bklite-rum-gateway ./cmd/bklite-rum-gateway \
    && go build -trimpath -ldflags="-s -w" -o /out/bklite-rum-controller ./cmd/bklite-rum-controller \
    && go build -trimpath -ldflags="-s -w" -o /out/bklite-rum-maintainer ./cmd/bklite-rum-maintainer

FROM scratch
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder /out/ /usr/local/bin/
COPY otel/rum.gateway.yaml /etc/bklite-rum/rum.gateway.yaml
USER 65532:65532

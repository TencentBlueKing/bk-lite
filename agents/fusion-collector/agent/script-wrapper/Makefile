NAME := bklite-script-wrapper

.PHONY: all linux-amd64 linux-arm64 windows-amd64 clean

all: linux-amd64 linux-arm64 windows-amd64

linux-amd64:
	mkdir -p dist/linux/x86_64
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o dist/linux/x86_64/$(NAME) .

linux-arm64:
	mkdir -p dist/linux/arm64
	CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -trimpath -ldflags="-s -w" -o dist/linux/arm64/$(NAME) .

windows-amd64:
	mkdir -p dist/windows/x86_64
	CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o dist/windows/x86_64/$(NAME).exe .

clean:
	rm -rf dist

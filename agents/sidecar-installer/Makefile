.PHONY: all build icons worker nsis clean check-deps

WORKER = setup-worker.exe
INSTALLER = collector-sidecar-installer.exe

all: build

build: check-deps icons worker nsis
	@echo "Build complete: $(INSTALLER)"
	@ls -lh $(INSTALLER)

icons:
	@python3 gen_icon.py

worker:
	GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o $(WORKER) setup-worker.go
	@ls -lh $(WORKER)

nsis:
	makensis -V2 setup.nsi

check-deps:
	@which makensis >/dev/null || (echo "NSIS not installed"; exit 1)
	@which go >/dev/null || (echo "Go not installed"; exit 1)
	@python3 -c "from PIL import Image" 2>/dev/null || (echo "Pillow not installed"; exit 1)

clean:
	rm -f $(WORKER) $(INSTALLER) installer.ico header.bmp wizard.bmp

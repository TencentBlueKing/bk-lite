.PHONY: all build icons worker linux-worker linux-worker-arm64 linux-worker-amd64 release-artifacts nsis clean check-deps install-deps

WORKER = setup-worker.exe
INSTALLER = bklite-controller-installer.exe
LINUX_INSTALLER = bklite-controller-installer
DIST_DIR = dist
VENV_DIR = .venv

all: build

build: check-deps icons worker linux-worker nsis
	@echo "Build complete: $(INSTALLER)"
	@ls -lh $(INSTALLER)
	@ls -lh $(LINUX_INSTALLER)

install-deps:
	@set -eu; \
	OS_NAME="$$(uname -s 2>/dev/null || printf '%s' "$${OS:-unknown}")"; \
	PYTHON_BIN=""; \
	if [ "$$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; else SUDO=""; fi; \
	case "$$OS_NAME" in \
		Darwin) \
			command -v brew >/dev/null 2>&1 || { echo "Homebrew is required on macOS: https://brew.sh"; exit 1; }; \
			brew install go python nsis; \
			PYTHON_BIN="$$(command -v python3 || command -v python)"; \
			;; \
		Linux) \
			if command -v apt-get >/dev/null 2>&1; then \
				$$SUDO apt-get update; \
				$$SUDO apt-get install -y golang-go python3 python3-venv python3-pip nsis; \
			elif command -v dnf >/dev/null 2>&1; then \
				$$SUDO dnf install -y golang python3 python3-pip nsis; \
			elif command -v yum >/dev/null 2>&1; then \
				$$SUDO yum install -y golang python3 python3-pip nsis; \
			elif command -v apk >/dev/null 2>&1; then \
				$$SUDO apk add --no-cache go python3 py3-pip nsis; \
			elif command -v pacman >/dev/null 2>&1; then \
				$$SUDO pacman -Sy --noconfirm go python python-pip nsis; \
			elif command -v zypper >/dev/null 2>&1; then \
				$$SUDO zypper --non-interactive install go python3 python3-pip nsis; \
			else \
				echo "Unsupported Linux package manager. Install go, python3, Pillow, and nsis manually."; \
				exit 1; \
			fi; \
			PYTHON_BIN="$$(command -v python3 || command -v python)"; \
			;; \
		MINGW*|MSYS*|CYGWIN*|Windows_NT) \
			if command -v winget >/dev/null 2>&1; then \
				winget install --id GoLang.Go -e --accept-package-agreements --accept-source-agreements; \
				winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements; \
				winget install --id NSIS.NSIS -e --accept-package-agreements --accept-source-agreements; \
			elif command -v choco >/dev/null 2>&1; then \
				choco install -y golang python nsis; \
			else \
				echo "Unsupported Windows package manager. Install Go, Python 3, Pillow, and NSIS manually."; \
				exit 1; \
			fi; \
			PYTHON_BIN="$$(command -v python3 || command -v python)"; \
			;; \
		*) \
			echo "Unsupported OS: $$OS_NAME"; \
			exit 1; \
			;; \
	esac; \
	[ -n "$$PYTHON_BIN" ] || { echo "Python not found after installation"; exit 1; }; \
	"$$PYTHON_BIN" -m venv "$(VENV_DIR)"; \
	if [ -x "$(VENV_DIR)/bin/python3" ]; then VENV_PYTHON="$(VENV_DIR)/bin/python3"; \
	elif [ -x "$(VENV_DIR)/bin/python" ]; then VENV_PYTHON="$(VENV_DIR)/bin/python"; \
	elif [ -x "$(VENV_DIR)/Scripts/python.exe" ]; then VENV_PYTHON="$(VENV_DIR)/Scripts/python.exe"; \
	elif [ -x "$(VENV_DIR)/Scripts/python" ]; then VENV_PYTHON="$(VENV_DIR)/Scripts/python"; \
	else echo "Virtualenv python not found"; exit 1; fi; \
	"$$VENV_PYTHON" -m pip install --upgrade pip Pillow; \
	echo "Dependencies installed. Run 'make build' next."

icons:
	@set -eu; \
	if [ -x "$(VENV_DIR)/bin/python3" ]; then PYTHON_BIN="$(VENV_DIR)/bin/python3"; \
	elif [ -x "$(VENV_DIR)/bin/python" ]; then PYTHON_BIN="$(VENV_DIR)/bin/python"; \
	elif [ -x "$(VENV_DIR)/Scripts/python.exe" ]; then PYTHON_BIN="$(VENV_DIR)/Scripts/python.exe"; \
	elif [ -x "$(VENV_DIR)/Scripts/python" ]; then PYTHON_BIN="$(VENV_DIR)/Scripts/python"; \
	elif command -v python3 >/dev/null 2>&1; then PYTHON_BIN="$$(command -v python3)"; \
	elif command -v python >/dev/null 2>&1; then PYTHON_BIN="$$(command -v python)"; \
	else echo "Python not installed"; exit 1; fi; \
	"$$PYTHON_BIN" gen_icon.py

worker:
	GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o $(WORKER) setup-worker.go
	@ls -lh $(WORKER)

linux-worker:
	GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o $(LINUX_INSTALLER) setup-worker.go
	@ls -lh $(LINUX_INSTALLER)

linux-worker-amd64:
	@mkdir -p $(DIST_DIR)/linux/x86_64
	GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o $(DIST_DIR)/linux/x86_64/$(LINUX_INSTALLER) setup-worker.go
	@ls -lh $(DIST_DIR)/linux/x86_64/$(LINUX_INSTALLER)

linux-worker-arm64:
	@mkdir -p $(DIST_DIR)/linux/arm64
	GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o $(DIST_DIR)/linux/arm64/$(LINUX_INSTALLER) setup-worker.go
	@ls -lh $(DIST_DIR)/linux/arm64/$(LINUX_INSTALLER)

release-artifacts: worker linux-worker-amd64 linux-worker-arm64 nsis
	@mkdir -p $(DIST_DIR)/windows/x86_64
	@cp $(INSTALLER) $(DIST_DIR)/windows/x86_64/$(INSTALLER)
	@ls -lh $(DIST_DIR)/windows/x86_64/$(INSTALLER)

nsis:
	makensis -V2 setup.nsi

check-deps:
	@which makensis >/dev/null || (echo "NSIS not installed"; exit 1)
	@which go >/dev/null || (echo "Go not installed"; exit 1)
	@set -eu; \
	if [ -x "$(VENV_DIR)/bin/python3" ]; then PYTHON_BIN="$(VENV_DIR)/bin/python3"; \
	elif [ -x "$(VENV_DIR)/bin/python" ]; then PYTHON_BIN="$(VENV_DIR)/bin/python"; \
	elif [ -x "$(VENV_DIR)/Scripts/python.exe" ]; then PYTHON_BIN="$(VENV_DIR)/Scripts/python.exe"; \
	elif [ -x "$(VENV_DIR)/Scripts/python" ]; then PYTHON_BIN="$(VENV_DIR)/Scripts/python"; \
	elif command -v python3 >/dev/null 2>&1; then PYTHON_BIN="$$(command -v python3)"; \
	elif command -v python >/dev/null 2>&1; then PYTHON_BIN="$$(command -v python)"; \
	else echo "Python not installed"; exit 1; fi; \
	"$$PYTHON_BIN" -c "from PIL import Image" 2>/dev/null || (echo "Pillow not installed. Run 'make install-deps' first."; exit 1)

clean:
	rm -f $(WORKER) $(INSTALLER) $(LINUX_INSTALLER) installer.ico header.bmp wizard.bmp

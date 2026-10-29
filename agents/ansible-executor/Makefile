install:
	uv sync

run:
	uv run python main.py

# Use a fresh WORK_DIR and DIST_DIR for each release; never reuse the developer venv.
UV ?= uv
DIST_DIR ?= $(CURDIR)/dist
package:
	@test -n "$(RELEASE_PYTHON)" -a -n "$(WORK_DIR)" || (echo "Set RELEASE_PYTHON and a fresh WORK_DIR"; exit 1)
	"$(RELEASE_PYTHON)" build_release.py --python "$(RELEASE_PYTHON)" --uv "$(UV)" --work-dir "$(WORK_DIR)" --dist-dir "$(DIST_DIR)"

clean-package:
	rm -rf build dist

build:
	docker build -t bklite/ansible-executor -f ./support-files/Dockerfile .

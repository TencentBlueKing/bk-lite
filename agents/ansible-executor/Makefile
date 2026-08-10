install:
	uv sync

run:
	uv run python main.py

package:
	uv run ansible-galaxy collection install -r ./collections/requirements.yml -p ./build/pyinstaller-collections --force
	uv run --with pyinstaller==6.16.0 pyinstaller --noconfirm ansible-executor.spec

clean-package:
	rm -rf build dist

build:
	docker build -t bklite/ansible-executor -f ./support-files/Dockerfile .

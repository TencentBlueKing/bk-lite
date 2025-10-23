push:
	git add . && codegpt commit . && git push

clean:
	rm -Rf ./dist

install:
	uv sync --all-groups
	uv sync --all-extras

install-hook:
	pre-commit install

lint:
	pre-commit run --all-files

run:
	uv run sanic server:app --host=0.0.0.0 --port=8083 --workers=1 --debug

build:
	docker build -t bklite/stargazer -f ./support-files/docker/Dockerfile .
push:
	git add .
	git commit -m "release"
	git push

build:
	rm -Rf ./dist
	uv build

install: 
	uv sync --all-groups
	uv sync --all-extras

update:
	copier update 

serving:
	uv run python -m bentoml serve classify_anomaly_server.serving.service:MLService

release:
	docker build -t bklite/classify_anomaly_server:latest -f ./support-files/release/Dockerfile .
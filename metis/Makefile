.PHONY: setup clean install-%

install: 
	uv sync --all-groups
	uv sync --all-extras

download-models:
	uv run sanic server:bootstrap exec download_models

sync-db:
	uv run sanic server:bootstrap exec sync_db

dev:
	uv pip install -e "../neco[core,llm,mlflow,sanic,doc_parser,devops,ocr]"
	GRAPHITI_TELEMETRY_ENABLED="false" TRANSFORMERS_OFFLINE="true" HF_DATASETS_OFFLINE="1" uv run --no-sync sanic server:bootstrap --factory --debug --host=0.0.0.0 --port=18082

build-base:
	docker build -t bklite/metis:base -f ./support-files/Dockerfile.base .
	docker push bklite/metis:base

release:
	docker build -t bklite/metis -f ./support-files/Dockerfile .
	docker push bklite/metis


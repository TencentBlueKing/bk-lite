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
	@expected_enterprise_sha="$$(git -C ../.. ls-tree HEAD -- enterprise | awk '$$1 == "160000" && $$2 == "commit" {print $$3}')"; \
	actual_enterprise_sha="$$(git -C ../../enterprise rev-parse HEAD 2>/dev/null || true)"; \
	if [ -z "$$expected_enterprise_sha" ]; then \
		echo "ERROR: 主仓库 HEAD 未声明 enterprise gitlink" >&2; \
		exit 1; \
	fi; \
	if [ "$$actual_enterprise_sha" != "$$expected_enterprise_sha" ]; then \
		echo "ERROR: Enterprise 子模块版本不匹配 expected=$$expected_enterprise_sha actual=$${actual_enterprise_sha:-missing}" >&2; \
		echo "请执行: git submodule sync -- enterprise && git submodule update --init --checkout -- enterprise" >&2; \
		exit 1; \
	fi; \
	docker build \
		--build-context enterprise_src=../../enterprise/agents/stargazer/enterprise \
		--build-arg ENTERPRISE_SHA="$$expected_enterprise_sha" \
		--label "com.weops.stargazer.enterprise.revision=$$expected_enterprise_sha" \
		-t bklite/stargazer \
		-f ./support-files/docker/Dockerfile \
		.

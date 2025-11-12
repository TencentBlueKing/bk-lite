build:
	rm -Rf ./dist
	uv build
	
push:
	git add .
	git commit -m "release"
	git push

install: 
	uv sync --all-groups
	uv sync --all-extras

export-tools:
	uv run python -m neco.cli.tools_cli export --output=./dist/tools.yml  
	
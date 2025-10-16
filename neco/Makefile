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

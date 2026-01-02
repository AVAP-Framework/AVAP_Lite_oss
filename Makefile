.PHONY: install build test clean

install:
	maturin build --release --out dist
	pip install dist/*.whl

test:
	pytest tests/

build:
	maturin build --release

clean:
	rm -rf dist/
	rm -rf target/
	find . -type d -name "__pycache__" -exec rm -rf {} +
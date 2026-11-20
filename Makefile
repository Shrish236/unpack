.PHONY: help install dev-server dev-worker dev-ui contract test clean

help:
	@echo "Unpack Development Tasks:"
	@echo "  install      Install python dependencies in editable mode"
	@echo "  dev-server   Start FastAPI development server"
	@echo "  dev-worker   Start background worker & reconciler loop"
	@echo "  dev-ui       Start web frontend development server"
	@echo "  contract     Export Pydantic schemas to JSON Schema for UI"
	@echo "  test         Run all tests with pytest"
	@echo "  lint         Run ruff checks"
	@echo "  clean        Remove build artifacts and caches"

install:
	pip install -e ".[dev]"
	cd web && npm install

contract:
	python contract/export_schemas.py

test:
	pytest tests/ -n auto

lint:
	ruff check .

dev-server:
	uvicorn server.app.main:app --reload --port 8000

dev-worker:
	python -m server.app.jobs.worker

dev-ui:
	cd web && npm run dev

rollup:
	python -c "import asyncio; from server.app.pipeline.rollup import rollup_measured; print(asyncio.run(rollup_measured()))"

seed-dashboard:
	python -m server.app.dashboard_seed

build-ui:
	cd web && npm run build

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf build dist *.egg-info web/dist

PYTHON ?= python3
.PHONY: up down bootstrap demo test lint logs clean
up:
	$(PYTHON) scripts/configure.py
	docker compose up -d --build postgres flagsmith mock-mcp mock-llm
	$(MAKE) bootstrap
	docker compose up -d --build gateway dashboard
bootstrap:
	$(PYTHON) scripts/bootstrap_flagsmith.py
demo:
	$(PYTHON) demo/run_demo_agents.py
test:
	$(PYTHON) -m pytest -v gateway/tests
	$(PYTHON) scripts/verify_e2e.py
lint:
	ruff check gateway/
	cd dashboard && npm ci && npx tsc --noEmit && npm run build
down:
	docker compose down
logs:
	docker compose logs -f --tail 100
clean:
	docker compose down --volumes --remove-orphans

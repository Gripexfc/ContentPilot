.PHONY: install backend frontend dev test lint db-upgrade

install:
	uv venv --python 3.12 .venv312
	.venv312/bin/pip install -e '.[dev]'
	cd web/frontend && npm install

backend:
	.venv312/bin/creatoros web --host 127.0.0.1 --port 8000

frontend:
	cd web/frontend && npm run dev

dev:
	@echo "Run 'make backend' and 'make frontend' in separate terminals."

test:
	.venv312/bin/pytest
	cd web/frontend && npm test -- --run

lint:
	PYTHONPYCACHEPREFIX=/tmp/creatoros-pycache .venv312/bin/python -m compileall creatoros tests
	cd web/frontend && npm run typecheck

db-upgrade:
	.venv312/bin/creatoros db upgrade

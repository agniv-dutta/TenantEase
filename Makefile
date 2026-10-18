.PHONY: setup seed train eval api web test demo check report-assets lint docker

PYTHON ?= python
PIP ?= pip
BACKEND_DIR := backend
FRONTEND_DIR := frontend

setup:
	$(PIP) install -e "$(BACKEND_DIR)[dev]"
	cd $(FRONTEND_DIR) && npm install

seed:
	cd $(BACKEND_DIR) && $(PYTHON) -m app.ml.synth --seed 42 --out data/khata.db

train:
	cd $(BACKEND_DIR) && $(PYTHON) -m app.ml.train

eval:
	cd $(BACKEND_DIR) && $(PYTHON) -m app.ml.evaluate
	cd $(BACKEND_DIR) && $(PYTHON) -m app.ml.simulate
	cd $(BACKEND_DIR) && $(PYTHON) -m app.llm.eval

api:
	cd $(BACKEND_DIR) && $(PYTHON) -m uvicorn app.main:app --reload --port 8000

web:
	cd $(FRONTEND_DIR) && npm run dev

test:
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest -q

lint:
	cd $(BACKEND_DIR) && $(PYTHON) -m ruff check .

check: lint test
	cd $(FRONTEND_DIR) && npx tsc -b
	cd $(FRONTEND_DIR) && npm run build

report-assets:
	cd $(BACKEND_DIR) && $(PYTHON) -m app.ml.report_assets

demo: seed train
	@echo "Run 'make api' and 'make web' in two terminals."

docker:
	docker compose up --build

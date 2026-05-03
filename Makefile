# Makefile — common developer commands
# Run `make help` to see all targets

.PHONY: help keys env up down logs shell migrate migrate-new test lint fmt typecheck clean

COMPOSE = docker compose
APP_SERVICE = app

##@ Setup

help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n"} \
	/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 } \
	/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)

keys: ## Generate RSA key pair for JWT signing
	@bash scripts/generate_keys.sh

env: ## Copy .env.example to .env (if .env doesn't exist)
	@test -f .env || (cp .env.example .env && echo "✅ .env created. Edit it before proceeding.")

##@ Docker

up: ## Start all services (build if needed)
	$(COMPOSE) up --build -d
	@echo "🚀 Services running. API: http://localhost:8000/docs"

down: ## Stop and remove containers
	$(COMPOSE) down

restart: ## Restart the app container only
	$(COMPOSE) restart $(APP_SERVICE)

logs: ## Tail app logs
	$(COMPOSE) logs -f $(APP_SERVICE)

logs-all: ## Tail all service logs
	$(COMPOSE) logs -f

shell: ## Open a shell inside the running app container
	$(COMPOSE) exec $(APP_SERVICE) bash

##@ Database

migrate: ## Apply pending Alembic migrations
	$(COMPOSE) exec $(APP_SERVICE) alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new MSG="add_column_x")
	$(COMPOSE) exec $(APP_SERVICE) alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback the last migration
	$(COMPOSE) exec $(APP_SERVICE) alembic downgrade -1

migrate-history: ## Show migration history
	$(COMPOSE) exec $(APP_SERVICE) alembic history --verbose

##@ Development (local, no Docker)

install: ## Install dependencies into local venv
	pip install -r requirements.txt

run: ## Run app locally (requires DB + Redis running)
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

##@ Testing

test: ## Run all tests
	pytest tests/ -v

test-unit: ## Run unit tests only
	pytest tests/unit/ -v -m unit

test-integration: ## Run integration tests only
	pytest tests/integration/ -v -m integration

test-cov: ## Run tests with HTML coverage report
	pytest tests/ --cov=app --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"

##@ Code Quality

lint: ## Run ruff linter
	ruff check app/ tests/

fmt: ## Auto-format code with ruff + black
	ruff check --fix app/ tests/
	black app/ tests/

typecheck: ## Run mypy type checks
	mypy app/ --ignore-missing-imports

##@ Cleanup

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache htmlcov .coverage
	@echo "🧹 Clean!"

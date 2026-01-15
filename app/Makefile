.EXPORT_ALL_VARIABLES:
DJANGO_SETTINGS_MODULE = sequence_run_manager.settings.local

# Docker compose files
COMPOSE_LOCAL = compose_local.yml
COMPOSE_TEST = compose_test.yml

# Database configuration
DB_NAME = sequence_run_manager
DB_USER = orcabus
DB_PASSWORD = orcabus
DB_HOST = localhost

# Docker container names
DB_CONTAINER = orcabus_db
APP_CONTAINER = sequence_run_manager

# Docker compose commands
DC_LOCAL = docker compose -f $(COMPOSE_LOCAL)
DC_TEST = docker compose -f $(COMPOSE_TEST)

# DB backup files
LOCAL_DB_BACKUP_FILE_PATH = data/
REMOTE_DB_BACKUP_BASE_PATH = s3://orcabus-pg-dd-843407916570-ap-southeast-2/pg-dd/

# Check if database container exists
DB_EXISTS := $(shell docker ps -q -f name=$(DB_CONTAINER))

# Development commands
.PHONY: up down stop restart logs clean

# Start all services
up:
	@echo "Starting fresh database and application..."
	@echo "initializing database..."
	@$(MAKE) db-init
	@echo "starting application..."
	@$(DC_LOCAL) up --wait -d $(APP_CONTAINER)
	@echo "application started"

# Stop and remove only the application container
down:
	@echo "Stopping and removing application container..."
	@$(DC_LOCAL) down

# Stop all services but keep containers
stop:
	@echo "Stopping all services..."
	@$(DC_LOCAL) stop

# Restart all services
restart: stop up

# View logs
logs:
	@$(DC_LOCAL) logs -f

# Clean up all containers and volumes (use with caution)
clean:
	@echo "Cleaning up all containers and volumes..."
	@$(DC_LOCAL) down -v
	@$(DC_TEST) down -v

# Database operations
.PHONY: db-status db-remove db-reset db-init db-create get-latest-backup-date s3-dump-download s3-dump-download-if-not-exists db-load-data s3-load db-restore

# set up aws credentials
setup-dev-aws-credentials:
	@echo "Setting up AWS credentials..."
	@export AWS_PROFILE=dev
	@echo "AWS credentials set to profile: $$AWS_PROFILE"

# Check database status
db-status:
	@echo "Checking database status..."
	@if ! docker ps -q -f name=$(DB_CONTAINER) | grep -q .; then \
		echo "Error: Database container is not running"; \
		exit 1; \
	fi
	@docker exec -e PGPASSWORD=$(DB_PASSWORD) -it $(DB_CONTAINER) \
		psql -h $(DB_HOST) -U $(DB_USER) -d $(DB_NAME) -c "\l"

# Remove database
db-remove:
	@echo "Removing database..."
	@docker exec -e PGPASSWORD=$(DB_PASSWORD) -it $(DB_CONTAINER) psql -U $(DB_USER) -d postgres -c "DROP DATABASE IF EXISTS $(DB_NAME);"

# Create database with init-db.sql logic
db-create:
	@echo "Creating database and role..."
	@docker exec -e PGPASSWORD=$(DB_PASSWORD) $(DB_CONTAINER) psql -U $(DB_USER) -d postgres -c "CREATE ROLE sequence_run_manager WITH LOGIN;" 2>/dev/null || echo "Role sequence_run_manager already exists or created."
	@docker exec -e PGPASSWORD=$(DB_PASSWORD) $(DB_CONTAINER) psql -U $(DB_USER) -d postgres -c "CREATE DATABASE $(DB_NAME) OWNER sequence_run_manager;"
	@docker exec -e PGPASSWORD=$(DB_PASSWORD) $(DB_CONTAINER) psql -U $(DB_USER) -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE $(DB_NAME) TO sequence_run_manager;"

db-reset: db-remove db-create

# Initialize database: check container, create if needed, check database, restore or create
db-init:
	@echo "Initializing database setup..."
	@CONTAINER_EXISTS=$$(docker ps -a -q -f name=$(DB_CONTAINER)); \
	if [ -z "$$CONTAINER_EXISTS" ]; then \
		echo "Container $(DB_CONTAINER) does not exist. Creating container with docker compose..."; \
		$(DC_LOCAL) up -d $(DB_CONTAINER); \
		echo "Waiting for database container to be ready..."; \
		timeout=60; \
		while [ $$timeout -gt 0 ]; do \
			if docker exec $(DB_CONTAINER) pg_isready -U $(DB_USER) -d postgres >/dev/null 2>&1; then \
				echo "Database container is ready."; \
				break; \
			fi; \
			echo "Waiting for database... ($$timeout seconds remaining)"; \
			sleep 2; \
			timeout=$$((timeout - 2)); \
		done; \
		if [ $$timeout -le 0 ]; then \
			echo "Error: Database container did not become ready in time"; \
			exit 1; \
		fi; \
		echo "Checking if database was initialized via init-db.sql..."; \
		sleep 2; \
		DB_EXISTS=$$(docker exec -e PGPASSWORD=$(DB_PASSWORD) $(DB_CONTAINER) psql -U $(DB_USER) -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$(DB_NAME)'" 2>/dev/null | grep -q 1 && echo "yes" || echo "no"); \
		if [ "$$DB_EXISTS" = "no" ]; then \
			echo "Database $(DB_NAME) does not exist. Creating database..."; \
			$(MAKE) db-create; \
			$(MAKE) s3-load; \
		else \
			echo "Database $(DB_NAME) exists. Restoring from latest dump..."; \
			$(MAKE) s3-load; \
		fi; \
	else \
		echo "Container $(DB_CONTAINER) exists."; \
		CONTAINER_RUNNING=$$(docker ps -q -f name=$(DB_CONTAINER)); \
		if [ -z "$$CONTAINER_RUNNING" ]; then \
			echo "Container is stopped. Starting container..."; \
			docker start $(DB_CONTAINER); \
			echo "Waiting for database container to be ready..."; \
			timeout=60; \
			while [ $$timeout -gt 0 ]; do \
				if docker exec $(DB_CONTAINER) pg_isready -U $(DB_USER) -d postgres >/dev/null 2>&1; then \
					echo "Database container is ready."; \
					break; \
				fi; \
				echo "Waiting for database... ($$timeout seconds remaining)"; \
				sleep 2; \
				timeout=$$((timeout - 2)); \
			done; \
			if [ $$timeout -le 0 ]; then \
				echo "Error: Database container did not become ready in time"; \
				exit 1; \
			fi; \
		else \
			echo "Container is already running."; \
		fi; \
		echo "Checking if database $(DB_NAME) exists..."; \
		DB_EXISTS=$$(docker exec -e PGPASSWORD=$(DB_PASSWORD) $(DB_CONTAINER) psql -U $(DB_USER) -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$(DB_NAME)'" 2>/dev/null | grep -q 1 && echo "yes" || echo "no"); \
		if [ "$$DB_EXISTS" = "no" ]; then \
			echo "Database $(DB_NAME) does not exist. Creating database..."; \
			$(MAKE) db-create; \
			$(MAKE) s3-load; \
		else \
			echo "Database $(DB_NAME) exists. Restoring from latest dump..."; \
			$(MAKE) s3-load; \
		fi; \
	fi

# Get latest backup date from S3
get-latest-backup-date: setup-dev-aws-credentials
	@aws s3 ls $(REMOTE_DB_BACKUP_BASE_PATH) | grep -E 'PRE [0-9]{8}/' | sed 's/.*PRE \([0-9]\{8\}\)\/.*/\1/' | sort -r | head -1

# Download latest db dump from s3
s3-dump-download: setup-dev-aws-credentials
	@echo "Finding latest backup date..."
	@LATEST_DATE=$$(aws s3 ls $(REMOTE_DB_BACKUP_BASE_PATH) | grep -E 'PRE [0-9]{8}/' | sed 's/.*PRE \([0-9]\{8\}\)\/.*/\1/' | sort -r | head -1); \
	if [ -z "$$LATEST_DATE" ]; then \
		echo "Error: No backup found in S3"; \
		exit 1; \
	fi; \
	echo "Latest backup date: $$LATEST_DATE"; \
	REMOTE_DUMP_FILE="$(REMOTE_DB_BACKUP_BASE_PATH)$$LATEST_DATE/$(DB_NAME).dump"; \
	echo "Checking if dump file exists: $$REMOTE_DUMP_FILE"; \
	if ! aws s3 ls "$$REMOTE_DUMP_FILE" > /dev/null 2>&1; then \
		echo "Error: Dump file $(DB_NAME).dump not found in latest backup ($$LATEST_DATE)"; \
		exit 1; \
	fi; \
	echo "Downloading db dump from $$REMOTE_DUMP_FILE..."; \
	mkdir -p $(LOCAL_DB_BACKUP_FILE_PATH); \
	aws s3 cp "$$REMOTE_DUMP_FILE" "$(LOCAL_DB_BACKUP_FILE_PATH)$(DB_NAME).dump"

# Check if local dump exists
s3-dump-download-if-not-exists:
	@if [ ! -f "$(LOCAL_DB_BACKUP_FILE_PATH)$(DB_NAME).dump" ]; then \
		$(MAKE) s3-dump-download; \
	else \
		echo "Local db dump already exists, skipping download..."; \
	fi

# Load data into database from local dump file (be careful, this will overwrite existing data)
db-load-data:
	@echo "Loading data into database from dump file..."
	@if [ ! -f "$(LOCAL_DB_BACKUP_FILE_PATH)$(DB_NAME).dump" ]; then \
		echo "Error: Dump file not found at $(LOCAL_DB_BACKUP_FILE_PATH)$(DB_NAME).dump"; \
		exit 1; \
	fi
	@echo "Copying dump file into container..."
	@docker cp $(LOCAL_DB_BACKUP_FILE_PATH)$(DB_NAME).dump $(DB_CONTAINER):/tmp/$(DB_NAME).dump
	@echo "Restoring database from dump file..."
	@docker exec -e PGPASSWORD=$(DB_PASSWORD) $(DB_CONTAINER) \
		pg_restore -U $(DB_USER) -d $(DB_NAME) --clean --if-exists --no-owner --no-acl /tmp/$(DB_NAME).dump
	@echo "Cleaning up temporary dump file from container..."
	@docker exec $(DB_CONTAINER) rm -f /tmp/$(DB_NAME).dump

# Load data into database from s3
s3-load: s3-dump-download-if-not-exists db-load-data

# Restore database from backup
db-restore: s3-dump-download-if-not-exists
	@echo "Restoring database from backup..."
	@if [ -z "$(LOCAL_DB_BACKUP_FILE)" ]; then \
		echo "Error: Please specify backup file with LOCAL_DB_BACKUP_FILE=path/to/backup.sql"; \
		exit 1; \
	fi
	@docker exec -e PGPASSWORD=$(DB_PASSWORD) -i $(DB_CONTAINER) \
		psql -h $(DB_HOST) -U $(DB_USER) -d $(DB_NAME) < $(LOCAL_DB_BACKUP_FILE)

# Local development commands
.PHONY: install check lint lint-fix makemigrations migrate load start openapi validate

install:
	@pip install -r deps/requirements-dev.txt

check: lint

lint:
	@black -t py312 --check . --exclude .venv

lint-fix:
	@black -t py312 . --exclude .venv

# Generate migrations
makemigrations:
	@python manage.py makemigrations

# Run migrations
migrate:
	@echo "Running migrations..."
	@python manage.py migrate

# Load mock data
load: migrate
	@python manage.py generate_mock_data

# Start server
start: migrate
	@python manage.py runserver_plus 0.0.0.0:8000

# Generate OpenAPI spec
openapi:
	@python manage.py spectacular --format openapi > orcabus.sequencerunmanager.openapi.yaml

# Validate OpenAPI spec
validate: openapi
	@python -m openapi_spec_validator orcabus.sequencerunmanager.openapi.yaml

schema-gen: schema-gen-srsc schema-gen-srssc schema-gen-srllc

schema-gen-srsc:
	@echo "Generating SRSC schema..."
	@datamodel-codegen --input ../docs/events/SequenceRunStateChange/SequenceRunStateChange.schema.json --input-file-type jsonschema --output sequence_run_manager_proc/domain/events/srsc.py

schema-gen-srssc:
	@echo "Generating SRSSC schema..."
	@datamodel-codegen --input ../docs/events/SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json --input-file-type jsonschema --output sequence_run_manager_proc/domain/events/srssc.py

schema-gen-srllc:
	@echo "Generating SRLLC schema..."
	@datamodel-codegen --input ../docs/events/SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json --input-file-type jsonschema --output sequence_run_manager_proc/domain/events/srllc.py


# Database commands
.PHONY: psql

# Connect to database
psql:
	@docker exec -e PGPASSWORD=$(DB_PASSWORD) -it $(DB_CONTAINER) psql -h $(DB_HOST) -U $(DB_USER) -d $(DB_NAME)

# Test commands
.PHONY: test suite

# full mock suite test pipeline - install deps, bring up compose test stack, run suite, bring down compose test stack
test: install test-up suite test-down

suite:
	@DJANGO_SETTINGS_MODULE=sequence_run_manager.settings.it \
	DB_HOSTNAME=localhost \
	DB_PORT=5435 \
	python manage.py test

# Run tests with coverage
coverage: install up migrate
	@echo $$DJANGO_SETTINGS_MODULE
	@coverage run --source='.' manage.py test

# Generate coverage report
report:
	@coverage report -m
	@coverage html

# Bring up test stack
test-up:
	@docker compose -f $(COMPOSE_TEST) up --wait -d

# Bring down test stack
test-down:
	@docker compose -f $(COMPOSE_TEST) down

# List containers
ps:
	@docker compose ps

# Help command
.PHONY: help
help:
	@echo "Available commands:"
	@echo "\nDevelopment Commands:"
	@echo "  make up          - Start all services"
	@echo "  make down        - Stop and remove all containers"
	@echo "  make stop        - Stop all services but keep containers"
	@echo "  make clean       - Clean up all containers and volumes"
	@echo "\nDatabase Commands:"
	@echo "  make db-init     - Initialize database: check/create container, check/create database, restore from latest dump"
	@echo "  make db-status   - Check database status"
	@echo "  make db-create   - Create database and role (uses init-db.sql logic)"
	@echo "  make db-remove   - Remove database"
	@echo "  make db-reset    - Reset database (remove and create)"
	@echo "  make setup-dev-aws-credentials - Setup AWS credentials"
	@echo "  make get-latest-backup-date - Get latest backup date from S3"
	@echo "  make s3-dump-download - Download latest db dump from S3"
	@echo "  make s3-dump-download-if-not-exists - Download latest db dump from S3 if not exists"
	@echo "  make db-load-data - Load data into database from local dump file"
	@echo "  make s3-load     - Download and load data from S3"
	@echo "\nLocal Development Commands:"
	@echo "  make migrate     - Apply database migrations"
	@echo "  make load        - Load mock data"
	@echo "  make install     - Install dependencies"
	@echo "  make start       - Start development server"
	@echo "\nCode Quality Commands:"
	@echo "  make check       - Run code quality checks"
	@echo "  make lint        - Check code formatting"
	@echo "  make lint-fix    - Fix code formatting"
	@echo "  make openapi     - Generate OpenAPI specification"
	@echo "  make validate    - Validate OpenAPI specification"
	@echo "  make schema-gen  - Generate schema from events"
	@echo "\nTest Commands:"
	@echo "  make test        - Run full test suite"
	@echo "  make test-up     - Start test environment"
	@echo "  make test-down   - Stop test environment"
	@echo "  make coverage    - Run tests with coverage"
	@echo "  make report      - Generate coverage report"

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
DB_CONTAINER = orcabus_db_sequence_run_manager
APP_CONTAINER = sequence_run_manager

# Docker compose commands
DC_LOCAL = docker compose -f $(COMPOSE_LOCAL)
DC_TEST = docker compose -f $(COMPOSE_TEST)

# DB backup files
LOCAL_DB_BACKUP_FILE_PATH = data/
REMOTE_DB_BACKUP_FILE_PATH = s3://orcabus-test-data-843407916570-ap-southeast-2/pg-dd/sequence_run_manager/

# Check if database container exists
DB_EXISTS := $(shell docker ps -q -f name=$(DB_CONTAINER))

# Development commands
.PHONY: up down stop restart logs clean

# Start all services
up:
	@echo "Starting fresh database and application..."
	@$(DC_LOCAL) up --wait -d

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
.PHONY: db-status db-remove db-reset  s3-dump-download s3-dump-download-if-not-exists db-load-data s3-load db-restore

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

# Reset database (remove and create)
db-reset: db-remove
	@echo "Creating fresh database..."
	@docker exec -e PGPASSWORD=$(DB_PASSWORD) -it $(DB_CONTAINER) psql -U $(DB_USER) -d postgres -c "CREATE DATABASE $(DB_NAME) OWNER sequence_run_manager;" || true

# Download all sql dumps from s3
s3-dump-download:
	@echo "Downloading all SQL dumps from S3..."
	@mkdir -p $(LOCAL_DB_BACKUP_FILE_PATH)
	@aws s3 cp $(REMOTE_DB_BACKUP_FILE_PATH) $(LOCAL_DB_BACKUP_FILE_PATH) --recursive

# Check if local dump exists
s3-dump-download-if-not-exists:
	@if [ ! -d "$(LOCAL_DB_BACKUP_FILE_PATH)" ] || [ -z "$$(ls -A $(LOCAL_DB_BACKUP_FILE_PATH))" ]; then \
		$(MAKE) s3-dump-download; \
	else \
		echo "Local SQL dumps already exist, skipping download..."; \
	fi

# Load data into database from local (be careful, this will overwrite existing data)
db-load-data:
	@echo "Loading data into database..."

	@echo "Loading sequence data first into database..."
	@gunzip -c $(LOCAL_DB_BACKUP_FILE_PATH)sequence_run_manager_sequence.csv.gz | docker exec -i $(DB_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -c "\COPY sequence_run_manager_sequence FROM STDIN WITH CSV HEADER;" >/dev/null;

	@echo "Loading remaining data into database..."
	@for file in $(LOCAL_DB_BACKUP_FILE_PATH)*.csv.gz; do \
		if [ "$$file" != "$(LOCAL_DB_BACKUP_FILE_PATH)sequence_run_manager_sequence.csv.gz" ]; then \
			table_name=$$(basename $$file .csv.gz); \
			echo "Loading $$table_name..."; \
			gunzip -c $$file | docker exec -i $(DB_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -c "\COPY $$table_name FROM STDIN WITH CSV HEADER;" >/dev/null; \
		fi \
	done

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
	@python manage.py test

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
	@echo "  make up          - Start all services and load data from S3"
	@echo "  make down        - Stop and remove all containers"
	@echo "  make stop        - Stop all services but keep containers"
	@echo "  make clean       - Clean up all containers and volumes"
	@echo "\nDatabase Commands:"
	@echo "  make db-status   - Check database status"
	@echo "  make db-remove   - Remove database"
	@echo "  make db-reset    - Reset database (remove and create)"
	@echo "  make db-backup   - Create database backup"
	@echo "  make db-restore  - Restore database from backup"
	@echo "  make db-load-data - Load data into database from local dump"
	@echo "  make s3-load     - Download and load data from S3"
	@echo "  make db-restore  - Restore database from backup (requires LOCAL_DB_BACKUP_FILE)"
	@echo "\nDjango Commands:"
	@echo "  make migrate     - Apply database migrations"
	@echo "  make load        - Load mock data"
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
	@echo "\nUtility Commands:"
	@echo "  make help        - Show this help message"

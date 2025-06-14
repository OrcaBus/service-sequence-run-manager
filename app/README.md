# Sequence Run Manager

```
Namespace: orcabus.sequencerunmanager
```

## CDK

See [deploy/README.md](deploy)

## How to run SRM locally

### Ready Check

- Go to Django project root
```
cd app
```
_*If you are PyCharm-er and opening the whole `orcabus` project then annotate this level as "source" directory in the project structure dialog._

### Python

- Setup Python environment (conda or venv)
```
conda create -n sequence_run_manager python=3.12
conda activate sequence_run_manager
```

### Make

- At app root, perform
```
make install
make up
make ps
```

### Migration

```
python manage.py help
python manage.py showmigrations
python manage.py migrate
```

### Mock Data

_^^^ please make sure to run `python manage.py migrate` first! ^^^_

#### Generate Sequence Record

```
python manage.py help generate_mock_data
    > Generate mock Sequence run data into database for local development and testing
```

```
python manage.py generate_mock_data
```

#### Generate BSSH Event

```
python manage.py help generate_mock_bssh_event
    > Generate mock BSSH SQS event in JSON format for local development and testing
```

```
python manage.py generate_mock_bssh_event | jq
```

#### Generate Domain Event

```
python manage.py help generate_mock_domain_event

    Generate mock Sequence domain event for local development and testing

    options:
      -h, --help            show this help message and exit
      --domain              Deserialized form of Sequence entity in SequenceRunStateChange
      --envelope            SequenceRunStateChange wrap in AWSEvent envelope
      --boto                AWSEvent to Boto PutEvent API envelope
```

```
python manage.py generate_mock_domain_event | jq
```

```
python manage.py generate_mock_domain_event --domain | jq
```

```
python manage.py generate_mock_domain_event --envelope | jq
```

```
python manage.py generate_mock_domain_event --boto | jq
```

### Run API

```
python manage.py runserver_plus
```

```
curl -s http://localhost:8000/srm/v1/sequence | jq
```

```
curl -s http://localhost:8000/srm/v1/sequence/1 | jq
```

Or visit in browser:
- http://localhost:8000/srm/v1
- http://localhost:8000/srm/v1/sequence
- http://localhost:8000/srm/v1/sequence/1

### API Doc

#### Swagger

- http://localhost:8000/schema/swagger-ui/

#### OpenAPI v3

- http://localhost:8000/schema/openapi.json


## Local DB

```
make psql
```

```
sequence_run_manager# \l
sequence_run_manager# \c sequence_run_manager
sequence_run_manager# \dt
sequence_run_manager# \d
sequence_run_manager# \d sequence_run_manager_sequence
sequence_run_manager# select count(1) from sequence_run_manager_sequence;
sequence_run_manager# select * from sequence_run_manager_sequence;
sequence_run_manager# \q
```

## Testing

### Coverage report

```
make coverage report
```

_The html report is in `htmlcov/index.html`._

### Run test suite

```
python manage.py test
```

### Unit test

```
python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_api
```

```
python manage.py test sequence_run_manager_proc.tests.test_bssh_event.BSSHEventUnitTests.test_sqs_handler
```

```
python manage.py test sequence_run_manager_proc.tests.test_sequence_domain.SequenceDomainUnitTests.test_marshall
```

```
python manage.py test sequence_run_manager_proc.tests.test_sequence_domain.SequenceDomainUnitTests.test_unmarshall
```

```
python manage.py test sequence_run_manager_proc.tests.test_sequence_domain.SequenceDomainUnitTests.test_aws_event_serde
```

```
python manage.py test sequence_run_manager_proc.tests.test_sequence_domain.SequenceDomainUnitTests.test_put_events_request_entry
```

## Tear Down

```
make down
```

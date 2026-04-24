# Backend

This service owns:
- document upload and job creation
- validation against the shared schema and ontology
- orchestration of extraction runs
- graph and evidence read APIs

The current scaffold includes:
- JSON-based Markdown upload with a 30-document cap
- stable chunk generation with `char_start` and `char_end`
- in-memory job creation and retrieval
- synchronous Python extractor invocation during job creation
- job result retrieval API for extracted entities and relations
- graph-serving APIs for graph list, entity detail, relation evidence, and source chunks
- dev fixture endpoint at `POST /api/v1/dev/fixtures/wikipedia` for local frontend testing

## Planned packages
- `cmd/server`: application entrypoint
- `internal/api`: HTTP handlers and router
- `internal/config`: environment-driven configuration
- `internal/domain`: core models and validation rules
- `internal/store`: persistence interfaces
- `internal/jobs`: orchestration logic

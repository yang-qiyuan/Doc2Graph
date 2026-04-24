# Doc2Graph Implementation Plan

## Scope
This MVP targets 10-20 Wikipedia biography documents and supports Markdown first. PDF support is deferred until the Markdown path is stable because source highlighting depends on accurate character offsets.

The system has three runtime components:
- `backend`: Go API for uploads, job orchestration, validation, and graph-serving APIs
- `extractor`: Python service for the agentic extraction loop
- `frontend`: Flutter client for upload, job status, and graph visualization

## Milestones

### Milestone 1: Shared contracts
- Freeze ontology and relation type matrix
- Define canonical JSON schema for documents, entities, relations, and evidence spans
- Define job status and API payload contracts

Exit criteria:
- Every service reads the same schema documents
- A sample extraction file validates against the export schema

### Milestone 2: Backend ingestion
- Create upload API with a 30-file cap
- Accept Markdown documents and normalize them into internal document records
- Chunk text while preserving stable `char_start` and `char_end`
- Persist document metadata and chunk records

Exit criteria:
- Markdown upload returns a created job
- Stored chunks can be used to reconstruct source highlighting offsets

### Milestone 3: Extraction loop
- Build Python pipeline stages for entity extraction, relation extraction, normalization, and scoring
- Add a deterministic validation pass before persistence
- Persist both intermediate extraction results and final canonical graph payload

Exit criteria:
- A Markdown document can produce valid entities and relations in the export schema
- Invalid or overlapping relations are rejected with explicit errors

### Milestone 4: Graph read APIs
- Write canonical entities and relations into Neo4j
- Add APIs to list graph nodes and edges
- Add APIs to fetch evidence, source chunks, and highlighted spans

Exit criteria:
- Frontend can render a graph and request evidence for any relation

### Milestone 5: Flutter prototype
- Upload screen
- Processing status screen
- Graph visualization screen
- Hover tooltip and click-to-highlight source panel

Exit criteria:
- A user can upload Markdown biographies and inspect extracted evidence in the graph UI

## Core design decisions

### 1. Ontology first
Only the predefined relation set is allowed in the MVP. Any extracted relation outside the ontology must be rejected or mapped explicitly.

### 2. Stable offsets
The parser and chunker must preserve source text offsets exactly. Highlighting depends on this and it is not negotiable.

### 3. Separation of concerns
- Go handles transport, validation, orchestration, and graph-serving
- Python handles semantic extraction and normalization
- Flutter handles presentation and user interactions

### 4. Canonical IDs
- Internal storage uses UUIDs
- Frontend export uses stable IDs like `E1` and `R1`
- Mentions and relations always reference source documents and offsets

## Initial API surface
- `POST /api/v1/documents:upload`
- `POST /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/graph`
- `GET /api/v1/entities/{entity_id}`
- `GET /api/v1/relations/{relation_id}/evidence`
- `GET /api/v1/documents/{doc_id}/chunks/{chunk_id}`

## Initial backlog
1. Implement Markdown ingestion end to end
2. Add schema validation tests
3. Implement extractor interfaces with fixture-driven tests
4. Add Neo4j persistence
5. Build the graph screen in Flutter
6. Add PDF parsing after Markdown is reliable

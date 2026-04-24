# Project Status

## Current state
The repository is past the initial scaffold stage. It now runs as a working local prototype with three active parts:
- a Go backend for ingestion, job orchestration, validation, and graph/evidence APIs
- a Python extractor with deterministic cross-document extraction and normalization
- a Flutter frontend that can run locally and inspect the sample graph interactively

The current prototype is centered on the 30-document Wikipedia biography fixture set in `testdata/wikipedia_markdown/`.

## Implemented

### Shared contracts and planning
- Repository structure for `backend`, `extractor`, `frontend`, `docs`, `schemas`, and `testdata`
- Shared ontology in `schemas/ontology.json`
- Shared export schema in `schemas/export.schema.json`
- Architecture and milestone plan in `docs/implementation-plan.md`

### Backend
- Markdown upload validation with a 30-document cap
- Document normalization and stable chunk generation with source offsets
- In-memory persistence for documents, jobs, and extraction results
- Synchronous job execution through the Python extractor
- Job APIs:
  - `POST /api/v1/jobs`
  - `GET /api/v1/jobs/{job_id}`
  - `GET /api/v1/jobs/result/{job_id}`
- Graph and evidence APIs:
  - `GET /api/v1/graph`
  - `GET /api/v1/entities/{entity_id}`
  - `GET /api/v1/relations/{relation_id}/evidence`
  - `GET /api/v1/documents/{doc_id}/chunks/{chunk_id}`
- Display-graph transform in the graph service so `GET /api/v1/graph` returns a frontend-friendly graph instead of the raw canonical extraction result
- Collapsed metadata summaries in the display graph:
  - one-hop metadata `Time` and `Place` leaves are grouped into synthetic summary nodes
  - grouped summary edges preserve counts of underlying hidden relations
  - `expand_metadata=true` returns the expanded metadata view on demand
- Dev fixture endpoint for loading and processing the 30-page Wikipedia sample from the frontend
- Backend-side validation for:
  - allowed entity types
  - allowed relation predicates
  - subject/object reference integrity
  - predicate subject/object type compatibility
  - mention and evidence offset bounds
  - confidence bounds

### Extractor
- Deterministic extraction pipeline in `extractor/doc2graph_extractor/pipeline.py`
- Cross-document normalization of canonical entities with merged mentions and aliases
- Current supported relation coverage:
  - PERSON-TIME: `born_on`, `died_on`
  - PERSON-PLACE: `born_in`, `died_in`, `lived_in`
  - PERSON-ORG: `worked_at`, `studied_at`, `founded`, `member_of`
  - PERSON-WORK: `authored`, `translated`, `edited`
  - PERSON-PERSON: `influenced_by`, `collaborated_with`, `family_of`, `student_of`
- Unicode-aware person-name handling in family relation extraction
- Extractor test coverage for both baseline and enhanced patterns

### Frontend
- Local Flutter inspector runnable on Chrome and macOS
- Backend connectivity for creating and viewing sample jobs
- Interactive graph canvas with:
  - auto-fit on load
  - pan and zoom
  - node dragging
  - connected-node dragging behavior
  - hover state for nodes and edges
  - relation evidence lookup and highlighted source text
  - relation type and confidence filtering
  - display summary for hidden nodes and edges after graph transformation
  - metadata expansion toggle that reloads the graph in grouped or expanded mode
  - summary-node and summary-edge hover/detail behavior for grouped metadata
- Local web shell and loading state improvements so the app does not boot to a blank page

### Verification
- `cd backend && go test ./...`
- `cd extractor && python3 -m pytest`
- `cd frontend && /opt/homebrew/share/flutter/bin/flutter test`

All of the above passed during the latest review pass.

## Known gaps
- Backend validation is implemented in Go code and is not yet generated from or directly enforced against `schemas/export.schema.json` and `schemas/ontology.json`
- Storage is still in-memory; there is no persistent graph store yet
- The frontend still depends on the dev Wikipedia fixture flow rather than a real user-facing file upload flow
- The extractor is still regex-driven and generally captures only the first matching instance for each relation pattern
- Entity normalization is canonical-key based and does not yet do fuzzy matching, alias resolution, or stronger cross-document person reconciliation
- The graph payload now supports grouped metadata summary nodes and an expanded metadata mode, but it still does not support in-canvas progressive expand/collapse of individual groups

## Recommended next start
The highest-value next implementation pass is graph quality rather than more UI polish:
1. Add per-group expansion in the canvas so users can expand one summary node without refetching the whole graph
2. Strengthen cross-document normalization for `Person`, `Organization`, and `Work`
3. Add a real frontend upload flow that targets the existing backend ingestion path
4. Decide whether validation should remain code-defined in Go or be driven from the shared schema/ontology files

## Notes from current review
- `CLAUDE.md` is useful as an orientation file, but parts of it are aspirational
- In particular, the backend currently validates extraction results through `backend/internal/domain/validation.go`, not by directly loading the JSON schema or ontology files
- `PROJECT_STATUS.md` had been behind the implementation and is now updated to match the actual codebase

# Project Status

## Current state
Initial scaffold created from the README requirements.

## Implemented in this pass
- Repository structure for backend, extractor, frontend, docs, and schemas
- Shared ontology document
- Shared export JSON schema
- Go backend HTTP skeleton
- Python extractor package skeleton
- Flutter app skeleton
- Written implementation plan
- Wikipedia Markdown fixture set with 30 biography pages in `testdata/wikipedia_markdown`
- Backend Markdown upload validation and chunk generation
- Go tests covering fixture ingestion and chunk boundaries
- Synchronous job processing through the Python extractor
- Job result storage and retrieval APIs
- Graph-oriented read APIs for frontend consumption
- Flutter local inspector UI wired to backend APIs
- Dev fixture endpoint for launching the 30-page Wikipedia sample job from the UI
- Local web build verified for the frontend
- Cross-document extractor normalization for shared place and time entities
- Backend validation for entity types, relation predicates, reference integrity, and source offsets

## Next implementation target
Richer extraction quality, including:
- stronger deterministic relation extraction for organizations and works
- broader cross-document entity normalization
- graph shaping that collapses repetitive metadata leaves for the UI
- real file upload flow in the frontend

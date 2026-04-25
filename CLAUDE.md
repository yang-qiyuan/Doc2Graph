# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Doc2Graph extracts entities and relationships from biographical documents (Wikipedia Markdown fixtures in the prototype) and builds a knowledge graph with source-level provenance. The pipeline uses deterministic regex-based extraction (with future LLM integration planned) to identify Person, Organization, Place, Work, and Time entities, then normalizes them across documents and validates against a strict ontology.

## Commands

### Backend (Go)
```bash
# Run the backend server (from backend/)
cd backend && go run cmd/server/main.go

# Run backend tests
cd backend && go test ./...

# Run specific package tests
cd backend && go test ./internal/api
cd backend && go test ./internal/domain

# Run tests with verbose output
cd backend && go test -v ./...
```

### Extractor (Python)
```bash
# Run extractor tests (from extractor/)
cd extractor && python3 -m pytest

# Run extractor tests with verbose output
cd extractor && python3 -m pytest -v

# Run specific test file
cd extractor && python3 -m pytest tests/test_pipeline.py

# Run the extractor module directly (reads JSON from stdin)
cd extractor && python3 -m doc2graph_extractor.main
```

### Frontend (Flutter)
```bash
# Run on macOS (from frontend/)
cd frontend && flutter run -d macos

# Run on Chrome (from frontend/)
cd frontend && flutter run -d chrome

# Build for web
cd frontend && flutter build web

# Run tests
cd frontend && flutter test
```

### Full Stack Development
The typical development flow:
1. Start backend: `cd backend && go run cmd/server/main.go` (listens on :8080)
2. Start frontend: `cd frontend && flutter run -d chrome`
3. Use the frontend UI to trigger the Wikipedia fixture job via the backend

## Architecture

### Three-Tier Structure

**Backend (Go)** - `backend/`
- HTTP API server orchestrating document ingestion and extraction jobs
- Invokes the Python extractor synchronously via subprocess (`internal/extractor/runner.go`)
- Validates extraction results against `schemas/export.schema.json` and `schemas/ontology.json`
- Stores extraction results in Neo4j graph database with jobs/documents in memory
- Serves graph data and evidence to the frontend

**Extractor (Python)** - `extractor/`
- Standalone pipeline accepting JSON on stdin, emitting JSON on stdout
- Entry point: `doc2graph_extractor/main.py`
- Core logic: `doc2graph_extractor/pipeline.py` (`ExtractionPipeline`)
- Current implementation uses deterministic regex patterns for entity and relation extraction
- Performs cross-document normalization: entities with matching canonical keys are merged

**Frontend (Flutter)** - `frontend/`
- Interactive graph visualization UI for viewing extracted knowledge graphs
- Connects to backend API to create jobs and fetch results
- Features:
  - **Interactive graph canvas** with pan, zoom, and auto-fit
  - **Connected node dragging**: When dragging a node, all connected nodes move together maintaining their spatial relationships
  - **Hover state management**: Entity and relation tooltips with proper boundary detection
  - **Evidence highlighting**: Click relations to view source text with highlighted evidence
  - **Graph filtering**: Filter by confidence threshold and relation type
- Dev fixture endpoint: POSTs to `/api/v1/dev/fixtures/wikipedia` to run the 30-page Wikipedia sample
- Graph layout uses force-directed simulation with entity-type-specific radial positioning

### Shared Contracts

**`schemas/ontology.json`**
- Defines the 5 entity types: Person, Organization, Place, Work, Time
- Defines relation predicates grouped by subject-object type pairs
- Example: `PERSON-PLACE` relations include `born_in`, `died_in`, `lived_in`

**`schemas/export.schema.json`**
- JSON Schema for the extraction result format
- Each entity has: id, name, type, aliases, source_doc, mentions (doc_id + char offsets)
- Each relation has: id, subject, predicate, object, evidence, source_doc, char offsets, confidence
- Backend validates all extraction results against this schema

### Backend Package Structure

- `cmd/server` - Application entry point
- `internal/api` - HTTP handlers, routing, JSON request/response models
- `internal/config` - Environment-driven configuration (DOC2GRAPH_HTTP_ADDR, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE)
- `internal/domain` - Core models (Document, Job, Entity, Relation, ExtractionResult) and validation
- `internal/extractor` - Python extractor subprocess runner
- `internal/jobs` - Job orchestration and result storage
- `internal/graph` - Graph-serving logic for frontend consumption
- `internal/devfixtures` - Wikipedia fixture loading for local testing
- `internal/store` - Persistence layer with MemoryStore (jobs/documents) and Neo4jStore (extraction results)

### Neo4j Graph Schema

The Neo4j database uses a graph-native schema with the following node types and relationships:

**Node Types:**
- `Job` - Represents an extraction job with properties: id, status, updated_at
- `Entity` - Knowledge graph entities with properties: id, name, type, source_doc, aliases
- `Mention` - Entity mention locations with properties: doc_id, char_start, char_end
- `Relation` - Knowledge graph relations with properties: id, predicate, evidence, source_doc, char_start, char_end, confidence

**Relationship Types:**
- `(Job)-[:HAS_ENTITY]->(Entity)` - Links jobs to extracted entities
- `(Job)-[:HAS_RELATION]->(Relation)` - Links jobs to extracted relations
- `(Entity)-[:HAS_MENTION]->(Mention)` - Links entities to their source mentions
- `(Relation)-[:HAS_SUBJECT]->(Entity)` - Links relations to subject entities
- `(Relation)-[:HAS_OBJECT]->(Entity)` - Links relations to object entities

**Key Design Decisions:**
- Relations are stored as nodes (not edges) to capture metadata like evidence, confidence, and source provenance
- Entity IDs serve as primary keys through actual graph relationships rather than string properties
- This graph-native design enables powerful traversals and maintains referential integrity
- The schema follows the RDF triple pattern: Subject-Predicate-Object, represented as Relation nodes with HAS_SUBJECT and HAS_OBJECT edges

### Extractor Implementation Details

**Entity Extraction** (`_extract_entities` in `pipeline.py`):
- Primary entity: the document title is treated as a Person entity
- Secondary entities extracted via regex patterns covering all 5 entity types:
  - **Person**: Related individuals (family, collaborators, mentors)
  - **Organization**: Universities, companies, institutions, academies
  - **Place**: Cities, countries, regions (birth, death, residence locations)
  - **Work**: Publications, books, articles (titles in quotes)
  - **Time**: Dates and temporal information (birth/death dates)
- Entity IDs use the format: `{doc_id}:{type_lower}:{canonical_key}`
- Unicode support for international names (e.g., "Bronisława", "José")

**Relation Extraction** (`_extract_relations` in `pipeline.py`):
The extractor supports **13 relation types** across 5 categories:

*PERSON-TIME Relations:*
- `born_on`, `died_on` - Birth and death dates (confidence: 0.88)

*PERSON-PLACE Relations:*
- `born_in`, `died_in`, `lived_in` - Birth, death, and residence locations (confidence: 0.75-0.82)

*PERSON-ORG Relations:*
- `worked_at` - Employment relationships (confidence: 0.72)
- `studied_at` - Educational institutions (confidence: 0.78)
- `founded` - Organizations founded (confidence: 0.85)
- `member_of` - Professional/academic memberships (confidence: 0.76)

*PERSON-WORK Relations:*
- `authored`, `translated`, `edited` - Creative work relationships (confidence: 0.77-0.83)

*PERSON-PERSON Relations:*
- `influenced_by` - Intellectual influence (confidence: 0.70)
- `collaborated_with` - Professional collaboration (confidence: 0.74)
- `family_of` - Family relationships (confidence: 0.81)
- `student_of` - Teacher/mentor relationships (confidence: 0.79)

Each relation stores `char_start` and `char_end` for source text highlighting. See `extractor/EXTRACTION_ENHANCEMENTS.md` for detailed pattern documentation.

**Normalization** (`_normalize_graph` in `pipeline.py`):
- Entities with identical canonical keys (type + case-folded name) are merged across documents
- Normalized entity IDs use prefixes: P (Person), O (Organization), L (Place), W (Work), T (Time)
- Relations are deduplicated by (subject, predicate, object, source_doc, char_start, char_end)
- Mentions and aliases are accumulated across all merged entities

### Data Flow

1. Frontend uploads Markdown documents or triggers the Wikipedia fixture endpoint
2. Backend creates a Job and stores Documents with stable `char_start`/`char_end` chunk boundaries
3. Backend invokes Python extractor via `PythonRunner`, passing JSON payload on stdin
4. Extractor runs the pipeline and returns JSON result on stdout
5. Backend validates the result and stores it in Neo4j graph database
6. Backend stores the extraction result in memory for backward compatibility and marks the Job as completed
7. Frontend fetches the graph data from Neo4j via `/api/v1/graph?job_id={id}`
8. Frontend displays entities/relations and fetches evidence via `/api/v1/graphs/{id}/relations/{relation_id}`

### Frontend Graph Interaction

**Graph Layout (`GraphLayout.build` in `main.dart`):**
- Force-directed layout with 220 iterations for stability
- Person entities positioned in inner circle (radius ~80-100px)
- Other entities (Time, Place, Organization, Work) in outer rings by type
- Repulsion forces prevent node overlap
- Attraction forces along edges maintain relationships

**Interactive Features:**
- **Pan**: Drag empty canvas space to pan the view
- **Zoom**: Scroll/pinch to zoom (min: fitted scale, max: 2.8x)
- **Node Dragging**: Click and drag any node to reposition it
  - When dragging a node, `getConnectedNodeIds()` identifies all connected nodes
  - Connected nodes move together via `moveNodeWithConnected()`, maintaining relative positions
  - Prevents graph fragmentation during manual adjustments
- **Hover**: Mouse over nodes/edges shows tooltips in the detail pane
  - Boundary detection clears tooltips when cursor leaves canvas edges
- **Click Node**: Fetches and displays entity mentions with source document references
- **Click Edge Label**: Fetches and displays relation evidence with highlighted source text

### Key Patterns and Conventions

**Entity Normalization**:
- Canonical keys are case-folded, whitespace-normalized versions of entity names
- For Time entities, commas are stripped from the canonical key to match "1881" with "1,881"
- Cross-document entities are merged if their (type, canonical_key) tuple matches

**Source Provenance**:
- Every entity has a `mentions` array with (doc_id, char_start, char_end) tuples
- Every relation has `char_start` and `char_end` pointing to the evidence span in `source_doc`
- This enables the frontend to highlight the exact source text that supports each extracted fact

**Validation**:
- Backend validates entity types against the ontology's `entity_types` list
- Backend validates relation predicates against the ontology's `relations` map
- Backend ensures relation subject/object reference existing entity IDs
- Backend checks that char_start < char_end and both are within document bounds

**Testing**:
- Backend tests use the 30 Wikipedia Markdown fixtures in `testdata/wikipedia_markdown/`
- Extractor tests use programmatically constructed fixture documents
  - `tests/test_pipeline.py`: Core pipeline and normalization tests
  - `tests/test_enhanced_extraction.py`: Tests for all 13 relation types, unicode support
- Tests verify:
  - Chunk boundaries and character offset accuracy
  - All 13 relation extraction patterns
  - Entity type extraction (Person, Organization, Place, Work, Time)
  - Cross-document normalization and deduplication
  - Backend validation logic against schema/ontology
  - API contracts and HTTP endpoints
  - Go/Python subprocess integration

## Test Data

The `testdata/wikipedia_markdown/` directory contains 30 Wikipedia biographical entries used for fixture-driven development and integration testing. The backend's dev fixture endpoint loads all 30 documents and creates a sample job.

## Recent Enhancements

**Backend (2026-04-25):**
- ✅ Neo4j graph database integration for persistent storage of extraction results
- ✅ Graph-native schema with Entity and Relation nodes, HAS_SUBJECT/HAS_OBJECT relationships
- ✅ Hybrid architecture: Neo4jStore for extraction results, MemoryStore for jobs/documents
- ✅ Environment-driven Neo4j configuration (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE)
- ✅ Automatic storage to Neo4j after extraction with fallback to memory store
- ✅ Graph retrieval from Neo4j for frontend rendering
- ✅ Tested with Neo4j Aura cloud instance (207 entities, 177 relations)

**Extractor (2026-04-24):**
- ✅ Expanded from 5 to 13 relation types, covering all ontology-defined relationships
- ✅ Added PERSON-WORK relations (authored, translated, edited)
- ✅ Added PERSON-PERSON relations (influenced_by, collaborated_with, family_of, student_of)
- ✅ Added PERSON-ORG relations (studied_at, founded, member_of)
- ✅ Added PERSON-PLACE relation (lived_in)
- ✅ Unicode support for international names in regex patterns
- ✅ Comprehensive test suite with 5 passing tests

**Frontend (2026-04-24):**
- ✅ Connected node dragging: Nodes move together with their connected neighbors
- ✅ Improved hover state management with canvas boundary detection
- ✅ Enhanced user experience for graph interaction

## Current Limitations and Future Work

**Extraction:**
- Deterministic regex-based extraction; LLM integration is planned for complex multi-sentence relationships
- Entity normalization is limited to exact canonical key matching; fuzzy matching and alias resolution are future targets
- Patterns extract first occurrence only; multiple instances of same relation type not captured

**Storage & Infrastructure:**
- Neo4j integration complete for extraction results; jobs/documents still in-memory
- No horizontal scaling support yet
- Graph queries could be optimized with custom Cypher indexes

**Frontend:**
- File upload flow not yet implemented; only the dev fixture endpoint works
- Graph visualization could be enhanced with community detection and clustering
- No undo/redo for graph manipulations

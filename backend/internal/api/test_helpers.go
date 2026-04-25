package api

import (
	"context"

	"doc2graph/backend/internal/domain"
	"doc2graph/backend/internal/graph"
	"doc2graph/backend/internal/jobs"
	"doc2graph/backend/internal/store"
)

type stubRunner struct {
	result domain.ExtractionResult
	err    error
}

func (s stubRunner) Run(_ context.Context, _ []domain.Document) (domain.ExtractionResult, error) {
	return s.result, s.err
}

func newTestApp(result domain.ExtractionResult) *App {
	memStore := store.NewMemoryStore()
	// For tests, we don't need actual Neo4j connectivity, so we pass nil
	// The test will use the stubRunner to bypass actual extraction
	graphService := graph.NewService(nil)
	graphService.SetMemoryStore(memStore)

	return &App{
		store:        memStore,
		neo4jStore:   nil,
		jobService:   jobs.NewService(memStore, nil, stubRunner{result: result}),
		graphService: graphService,
	}
}

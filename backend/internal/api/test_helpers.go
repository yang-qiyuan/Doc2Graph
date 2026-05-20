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
	return &App{
		store:        memStore,
		jobService:   jobs.NewService(memStore, stubRunner{result: result}),
		graphService: graph.NewService(memStore),
	}
}

package api

import (
	"doc2graph/backend/internal/extractor"
	"doc2graph/backend/internal/graph"
	"doc2graph/backend/internal/jobs"
	"doc2graph/backend/internal/store"
)

type App struct {
	store        *store.MemoryStore
	jobService   *jobs.Service
	graphService *graph.Service
}

func NewApp() *App {
	memStore := store.NewMemoryStore()
	return &App{
		store:        memStore,
		jobService:   jobs.NewService(memStore, extractor.NewPythonRunner()),
		graphService: graph.NewService(memStore),
	}
}

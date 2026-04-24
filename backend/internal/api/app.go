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
	st := store.NewMemoryStore()
	return &App{
		store:        st,
		jobService:   jobs.NewService(st, extractor.NewPythonRunner()),
		graphService: graph.NewService(st),
	}
}

package api

import (
	"doc2graph/backend/internal/extractor"
	"doc2graph/backend/internal/graph"
	"doc2graph/backend/internal/jobs"
	"doc2graph/backend/internal/store"
)

type App struct {
	store        *store.MemoryStore
	neo4jStore   *store.Neo4jStore
	jobService   *jobs.Service
	graphService *graph.Service
}

func NewApp(neo4jStore *store.Neo4jStore) *App {
	memStore := store.NewMemoryStore()
	graphService := graph.NewService(neo4jStore)
	graphService.SetMemoryStore(memStore)

	return &App{
		store:        memStore,
		neo4jStore:   neo4jStore,
		jobService:   jobs.NewService(memStore, neo4jStore, extractor.NewPythonRunner()),
		graphService: graphService,
	}
}

package main

import (
	"context"
	"log"
	"net/http"

	"doc2graph/backend/internal/api"
	"doc2graph/backend/internal/config"
	"doc2graph/backend/internal/store"
)

func main() {
	cfg := config.Load()

	// Initialize Neo4j store
	ctx := context.Background()
	neo4jStore, err := store.NewNeo4jStore(cfg.Neo4j)
	if err != nil {
		log.Fatalf("failed to create neo4j store: %v", err)
	}
	defer neo4jStore.Close(ctx)

	server := &http.Server{
		Addr:    cfg.HTTPAddr,
		Handler: api.NewRouter(neo4jStore),
	}

	log.Printf("backend listening on %s", cfg.HTTPAddr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server failed: %v", err)
	}
}

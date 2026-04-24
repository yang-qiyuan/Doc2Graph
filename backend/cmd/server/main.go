package main

import (
	"log"
	"net/http"

	"doc2graph/backend/internal/api"
	"doc2graph/backend/internal/config"
)

func main() {
	cfg := config.Load()
	server := &http.Server{
		Addr:    cfg.HTTPAddr,
		Handler: api.NewRouter(),
	}

	log.Printf("backend listening on %s", cfg.HTTPAddr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server failed: %v", err)
	}
}

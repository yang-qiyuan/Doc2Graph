package jobs

import (
	"context"
	"fmt"
	"log"
	"time"

	"doc2graph/backend/internal/domain"
	"doc2graph/backend/internal/extractor"
	"doc2graph/backend/internal/store"
)

type Service struct {
	memStore   *store.MemoryStore
	neo4jStore *store.Neo4jStore
	runner     extractor.Runner
}

func NewService(memStore *store.MemoryStore, neo4jStore *store.Neo4jStore, runner extractor.Runner) *Service {
	return &Service{
		memStore:   memStore,
		neo4jStore: neo4jStore,
		runner:     runner,
	}
}

func (s *Service) CreateAndProcess(ctx context.Context, documents []domain.Document, mode string) (domain.Job, error) {
	job := s.memStore.CreateJob(documents)
	s.memStore.UpdateJobStatus(job.ID, domain.JobStatusProcessing, "")

	// Create a timeout context for the extractor. `validated` mode does N
	// per-doc validation calls + per-pair resolution + optional Wikipedia
	// fetches; on a 30-doc fixture that easily exceeded the old 5-minute
	// budget when calls were sequential. With LLM parallelism this is
	// generous; without it, it's at least no longer the first thing to fail.
	extractorCtx, cancel := context.WithTimeout(ctx, 30*time.Minute)
	defer cancel()

	result, err := s.runner.Run(extractorCtx, documents, mode)
	if err != nil {
		s.memStore.UpdateJobStatus(job.ID, domain.JobStatusFailed, err.Error())
		return domain.Job{}, fmt.Errorf("process job %s: %w", job.ID, err)
	}
	if err := domain.ValidateExtractionResult(result, documents); err != nil {
		s.memStore.UpdateJobStatus(job.ID, domain.JobStatusFailed, err.Error())
		return domain.Job{}, fmt.Errorf("validate job %s result: %w", job.ID, err)
	}

	// Clear database before storing new results (for prototype testing)
	if err := s.neo4jStore.ClearDatabase(ctx); err != nil {
		log.Printf("Warning: failed to clear Neo4j database: %v", err)
	}

	// Store in Neo4j
	if err := s.neo4jStore.StoreExtractionResult(ctx, job.ID, &result); err != nil {
		log.Printf("Warning: failed to store extraction result in Neo4j: %v", err)
		// Continue with memory store as fallback
	} else {
		log.Printf("Successfully stored extraction result in Neo4j for job %s", job.ID)
	}

	// Also store in memory for backward compatibility
	job = s.memStore.UpdateJobResult(job.ID, result)
	return job, nil
}

package jobs

import (
	"context"
	"fmt"
	"log"

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

func (s *Service) CreateAndProcess(ctx context.Context, documents []domain.Document) (domain.Job, error) {
	job := s.memStore.CreateJob(documents)
	s.memStore.UpdateJobStatus(job.ID, domain.JobStatusProcessing, "")

	result, err := s.runner.Run(ctx, documents)
	if err != nil {
		s.memStore.UpdateJobStatus(job.ID, domain.JobStatusFailed, err.Error())
		return domain.Job{}, fmt.Errorf("process job %s: %w", job.ID, err)
	}
	if err := domain.ValidateExtractionResult(result, documents); err != nil {
		s.memStore.UpdateJobStatus(job.ID, domain.JobStatusFailed, err.Error())
		return domain.Job{}, fmt.Errorf("validate job %s result: %w", job.ID, err)
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

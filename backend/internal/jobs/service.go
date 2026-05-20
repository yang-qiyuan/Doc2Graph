package jobs

import (
	"context"
	"fmt"
	"time"

	"doc2graph/backend/internal/domain"
	"doc2graph/backend/internal/extractor"
	"doc2graph/backend/internal/store"
)

type Service struct {
	memStore *store.MemoryStore
	runner   extractor.Runner
}

func NewService(memStore *store.MemoryStore, runner extractor.Runner) *Service {
	return &Service{
		memStore: memStore,
		runner:   runner,
	}
}

func (s *Service) CreateAndProcess(ctx context.Context, documents []domain.Document) (domain.Job, error) {
	job := s.memStore.CreateJob(documents)
	s.memStore.UpdateJobStatus(job.ID, domain.JobStatusProcessing, "")

	extractorCtx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()

	result, err := s.runner.Run(extractorCtx, documents)
	if err != nil {
		s.memStore.UpdateJobStatus(job.ID, domain.JobStatusFailed, err.Error())
		return domain.Job{}, fmt.Errorf("process job %s: %w", job.ID, err)
	}
	if err := domain.ValidateExtractionResult(result, documents); err != nil {
		s.memStore.UpdateJobStatus(job.ID, domain.JobStatusFailed, err.Error())
		return domain.Job{}, fmt.Errorf("validate job %s result: %w", job.ID, err)
	}

	job = s.memStore.UpdateJobResult(job.ID, result)
	return job, nil
}

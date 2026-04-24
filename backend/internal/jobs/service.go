package jobs

import (
	"context"
	"fmt"

	"doc2graph/backend/internal/domain"
	"doc2graph/backend/internal/extractor"
	"doc2graph/backend/internal/store"
)

type Service struct {
	store  *store.MemoryStore
	runner extractor.Runner
}

func NewService(store *store.MemoryStore, runner extractor.Runner) *Service {
	return &Service{
		store:  store,
		runner: runner,
	}
}

func (s *Service) CreateAndProcess(ctx context.Context, documents []domain.Document) (domain.Job, error) {
	job := s.store.CreateJob(documents)
	s.store.UpdateJobStatus(job.ID, domain.JobStatusProcessing, "")

	result, err := s.runner.Run(ctx, documents)
	if err != nil {
		s.store.UpdateJobStatus(job.ID, domain.JobStatusFailed, err.Error())
		return domain.Job{}, fmt.Errorf("process job %s: %w", job.ID, err)
	}
	if err := domain.ValidateExtractionResult(result, documents); err != nil {
		s.store.UpdateJobStatus(job.ID, domain.JobStatusFailed, err.Error())
		return domain.Job{}, fmt.Errorf("validate job %s result: %w", job.ID, err)
	}

	job = s.store.UpdateJobResult(job.ID, result)
	return job, nil
}

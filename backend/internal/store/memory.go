package store

import (
	"fmt"
	"sync"
	"time"

	"doc2graph/backend/internal/domain"
)

type MemoryStore struct {
	mu        sync.RWMutex
	documents map[string]domain.Document
	jobs      map[string]domain.Job
	results   map[string]domain.ExtractionResult
	nextJobID int
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		documents: make(map[string]domain.Document),
		jobs:      make(map[string]domain.Job),
		results:   make(map[string]domain.ExtractionResult),
		nextJobID: 1,
	}
}

func (s *MemoryStore) SaveDocuments(documents []domain.Document) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, doc := range documents {
		s.documents[doc.ID] = doc
	}
}

func (s *MemoryStore) CreateJob(documents []domain.Document) domain.Job {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now().UTC()
	jobID := fmt.Sprintf("job-%04d", s.nextJobID)
	s.nextJobID++

	documentIDs := make([]string, 0, len(documents))
	for _, doc := range documents {
		s.documents[doc.ID] = doc
		documentIDs = append(documentIDs, doc.ID)
	}

	job := domain.Job{
		ID:          jobID,
		Status:      domain.JobStatusPending,
		DocumentIDs: documentIDs,
		CreatedAt:   now,
		UpdatedAt:   now,
	}
	s.jobs[jobID] = job

	return job
}

func (s *MemoryStore) GetJob(jobID string) (domain.Job, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	job, ok := s.jobs[jobID]
	return job, ok
}

func (s *MemoryStore) UpdateJobStatus(jobID string, status domain.JobStatus, errMsg string) domain.Job {
	s.mu.Lock()
	defer s.mu.Unlock()

	job := s.jobs[jobID]
	job.Status = status
	job.Error = errMsg
	job.UpdatedAt = time.Now().UTC()
	s.jobs[jobID] = job
	return job
}

func (s *MemoryStore) UpdateJobResult(jobID string, result domain.ExtractionResult) domain.Job {
	s.mu.Lock()
	defer s.mu.Unlock()

	job := s.jobs[jobID]
	job.Status = domain.JobStatusCompleted
	job.Error = ""
	job.UpdatedAt = time.Now().UTC()
	s.jobs[jobID] = job
	s.results[jobID] = result
	return job
}

func (s *MemoryStore) GetJobResult(jobID string) (domain.ExtractionResult, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result, ok := s.results[jobID]
	return result, ok
}

func (s *MemoryStore) GetDocument(documentID string) (domain.Document, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	document, ok := s.documents[documentID]
	return document, ok
}

func (s *MemoryStore) ListDocumentsByIDs(ids []string) []domain.Document {
	s.mu.RLock()
	defer s.mu.RUnlock()

	documents := make([]domain.Document, 0, len(ids))
	for _, id := range ids {
		doc, ok := s.documents[id]
		if !ok {
			continue
		}
		documents = append(documents, doc)
	}

	return documents
}

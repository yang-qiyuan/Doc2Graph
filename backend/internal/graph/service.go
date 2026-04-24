package graph

import (
	"fmt"

	"doc2graph/backend/internal/domain"
	"doc2graph/backend/internal/store"
)

type Service struct {
	store *store.MemoryStore
}

func NewService(store *store.MemoryStore) *Service {
	return &Service{store: store}
}

func (s *Service) GetGraph(jobID string) (domain.GraphResponse, error) {
	result, ok := s.store.GetJobResult(jobID)
	if !ok {
		return domain.GraphResponse{}, fmt.Errorf("job result not found")
	}

	return domain.GraphResponse{
		Documents: result.Documents,
		Entities:  result.Entities,
		Relations: result.Relations,
	}, nil
}

func (s *Service) GetEntity(jobID, entityID string) (domain.Entity, error) {
	result, ok := s.store.GetJobResult(jobID)
	if !ok {
		return domain.Entity{}, fmt.Errorf("job result not found")
	}

	for _, entity := range result.Entities {
		if entity.ID == entityID {
			return entity, nil
		}
	}

	return domain.Entity{}, fmt.Errorf("entity not found")
}

func (s *Service) GetRelationEvidence(jobID, relationID string) (domain.RelationEvidenceResponse, error) {
	result, ok := s.store.GetJobResult(jobID)
	if !ok {
		return domain.RelationEvidenceResponse{}, fmt.Errorf("job result not found")
	}

	var relation domain.Relation
	found := false
	for _, item := range result.Relations {
		if item.ID == relationID {
			relation = item
			found = true
			break
		}
	}
	if !found {
		return domain.RelationEvidenceResponse{}, fmt.Errorf("relation not found")
	}

	doc, ok := s.store.GetDocument(relation.SourceDoc)
	if !ok {
		return domain.RelationEvidenceResponse{}, fmt.Errorf("document not found")
	}

	for _, chunk := range doc.Chunks {
		if chunk.CharStart <= relation.CharStart && chunk.CharEnd >= relation.CharEnd {
			return domain.RelationEvidenceResponse{
				Relation: relation,
				Document: doc,
				Chunk:    chunk,
				Highlight: domain.Mention{
					DocID:     relation.SourceDoc,
					CharStart: relation.CharStart,
					CharEnd:   relation.CharEnd,
				},
			}, nil
		}
	}

	return domain.RelationEvidenceResponse{}, fmt.Errorf("supporting chunk not found")
}

func (s *Service) GetChunk(documentID, chunkID string) (domain.ChunkDetailResponse, error) {
	doc, ok := s.store.GetDocument(documentID)
	if !ok {
		return domain.ChunkDetailResponse{}, fmt.Errorf("document not found")
	}

	for _, chunk := range doc.Chunks {
		if chunk.ID == chunkID {
			return domain.ChunkDetailResponse{
				DocumentID: documentID,
				Chunk:      chunk,
			}, nil
		}
	}

	return domain.ChunkDetailResponse{}, fmt.Errorf("chunk not found")
}

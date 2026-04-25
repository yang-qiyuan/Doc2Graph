package graph

import (
	"context"
	"fmt"

	"doc2graph/backend/internal/domain"
	"doc2graph/backend/internal/store"
)

type Service struct {
	memStore   *store.MemoryStore
	neo4jStore *store.Neo4jStore
}

func NewService(neo4jStore *store.Neo4jStore) *Service {
	// For backward compatibility, we'll fallback to memStore for certain operations
	// In a future version, all operations should use Neo4j
	return &Service{
		neo4jStore: neo4jStore,
	}
}

func (s *Service) SetMemoryStore(memStore *store.MemoryStore) {
	s.memStore = memStore
}

func (s *Service) GetGraph(jobID string, expandMetadata bool) (domain.GraphResponse, error) {
	ctx := context.Background()
	graphData, err := s.neo4jStore.GetGraphForJob(ctx, jobID)
	if err != nil {
		return domain.GraphResponse{}, fmt.Errorf("failed to get graph from Neo4j: %w", err)
	}

	// Fetch documents from memory store for isPrimaryEntity check
	// Documents are needed to determine which Person entities are "primary" (document subjects)
	var documents []domain.ExportDocument
	if memResult, ok := s.memStore.GetJobResult(jobID); ok {
		documents = memResult.Documents
	}

	// Convert GraphData to ExtractionResult for compatibility with buildDisplayGraph
	result := domain.ExtractionResult{
		Documents: documents,
		Entities:  graphData.Entities,
		Relations: graphData.Relations,
	}

	return buildDisplayGraph(result, expandMetadata), nil
}

func (s *Service) GetEntity(jobID, entityID string) (domain.Entity, error) {
	result, ok := s.memStore.GetJobResult(jobID)
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

func (s *Service) GetEntityDetail(jobID, entityID string) (domain.EntityDetailResponse, error) {
	result, ok := s.memStore.GetJobResult(jobID)
	if !ok {
		return domain.EntityDetailResponse{}, fmt.Errorf("job result not found")
	}

	transform := newDisplayTransform(result)
	var entity domain.Entity
	found := false
	for _, item := range result.Entities {
		if item.ID == entityID {
			entity, _, _ = transform.decorateEntity(item, false)
			found = true
			break
		}
	}
	if !found {
		return domain.EntityDetailResponse{}, fmt.Errorf("entity not found")
	}

	hiddenConnections := make([]domain.HiddenConnection, 0)
	visibleRelationCount := 0
	for _, relation := range result.Relations {
		var neighborID string
		switch {
		case relation.Subject == entityID:
			neighborID = relation.Object
		case relation.Object == entityID:
			neighborID = relation.Subject
		default:
			continue
		}

		neighbor, ok := transform.entityByID[neighborID]
		if !ok {
			continue
		}
		neighborWithDisplay, hidden, reason := transform.decorateEntity(neighbor, true)
		relationWithDisplay, _, _ := transform.decorateRelation(relation, nil)
		if hidden {
			hiddenConnections = append(hiddenConnections, domain.HiddenConnection{
				Entity:   neighborWithDisplay,
				Relation: relationWithDisplay,
				Display: &domain.FactInfo{
					Group: reason,
				},
			})
			continue
		}
		visibleRelationCount++
	}

	return domain.EntityDetailResponse{
		Entity:               entity,
		HiddenConnections:    hiddenConnections,
		VisibleRelationCount: visibleRelationCount,
	}, nil
}

func (s *Service) GetRelationEvidence(jobID, relationID string) (domain.RelationEvidenceResponse, error) {
	result, ok := s.memStore.GetJobResult(jobID)
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

	doc, ok := s.memStore.GetDocument(relation.SourceDoc)
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
	doc, ok := s.memStore.GetDocument(documentID)
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

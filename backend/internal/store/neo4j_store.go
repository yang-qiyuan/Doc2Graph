package store

import (
	"context"
	"fmt"
	"log"

	"doc2graph/backend/internal/config"
	"doc2graph/backend/internal/domain"

	"github.com/neo4j/neo4j-go-driver/v5/neo4j"
)

type Neo4jStore struct {
	driver neo4j.DriverWithContext
	db     string
}

func NewNeo4jStore(cfg config.Neo4jConfig) (*Neo4jStore, error) {
	driver, err := neo4j.NewDriverWithContext(
		cfg.URI,
		neo4j.BasicAuth(cfg.Username, cfg.Password, ""),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create neo4j driver: %w", err)
	}

	// Verify connectivity
	ctx := context.Background()
	err = driver.VerifyConnectivity(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to neo4j: %w", err)
	}

	log.Printf("Connected to Neo4j at %s", cfg.URI)

	return &Neo4jStore{
		driver: driver,
		db:     cfg.Database,
	}, nil
}

func (s *Neo4jStore) Close(ctx context.Context) error {
	return s.driver.Close(ctx)
}

// ClearDatabase removes all nodes and relationships from the database
// This is useful for testing/prototype scenarios where you want a clean slate
func (s *Neo4jStore) ClearDatabase(ctx context.Context) error {
	session := s.driver.NewSession(ctx, neo4j.SessionConfig{
		DatabaseName: s.db,
	})
	defer session.Close(ctx)

	_, err := session.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
		// Delete all nodes and relationships
		_, err := tx.Run(ctx, "MATCH (n) DETACH DELETE n", nil)
		return nil, err
	})

	if err != nil {
		return fmt.Errorf("failed to clear database: %w", err)
	}

	log.Printf("Cleared all data from Neo4j database")
	return nil
}

// StoreExtractionResult stores the extraction result in Neo4j using batched transactions
func (s *Neo4jStore) StoreExtractionResult(ctx context.Context, jobID string, result *domain.ExtractionResult) error {
	session := s.driver.NewSession(ctx, neo4j.SessionConfig{
		DatabaseName: s.db,
	})
	defer session.Close(ctx)

	// Create Job node first
	_, err := session.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
		_, err := tx.Run(ctx,
			`MERGE (j:Job {id: $jobID})
			 SET j.status = 'completed',
			     j.updated_at = datetime()`,
			map[string]any{
				"jobID": jobID,
			})
		return nil, err
	})
	if err != nil {
		return fmt.Errorf("failed to create job node: %w", err)
	}

	// Store entities in batches of 50
	batchSize := 50
	for i := 0; i < len(result.Entities); i += batchSize {
		end := i + batchSize
		if end > len(result.Entities) {
			end = len(result.Entities)
		}
		batch := result.Entities[i:end]

		_, err := session.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
			for _, entity := range batch {
				_, err := tx.Run(ctx,
					`MERGE (e:Entity {id: $id})
					 SET e.name = $name,
					     e.type = $type,
					     e.source_doc = $source_doc,
					     e.aliases = $aliases
					 WITH e
					 MATCH (j:Job {id: $jobID})
					 MERGE (j)-[:HAS_ENTITY]->(e)`,
					map[string]any{
						"id":         entity.ID,
						"name":       entity.Name,
						"type":       entity.Type,
						"source_doc": entity.SourceDoc,
						"aliases":    entity.Aliases,
						"jobID":      jobID,
					})
				if err != nil {
					return nil, err
				}

				// Store mentions for this entity
				for _, mention := range entity.Mentions {
					_, err := tx.Run(ctx,
						`MATCH (e:Entity {id: $entityID})
						 CREATE (m:Mention {
						     doc_id: $doc_id,
						     char_start: $char_start,
						     char_end: $char_end
						 })
						 CREATE (e)-[:HAS_MENTION]->(m)`,
						map[string]any{
							"entityID":   entity.ID,
							"doc_id":     mention.DocID,
							"char_start": mention.CharStart,
							"char_end":   mention.CharEnd,
						})
					if err != nil {
						return nil, err
					}
				}
			}
			return nil, nil
		})
		if err != nil {
			return fmt.Errorf("failed to store entity batch %d-%d: %w", i, end, err)
		}
	}

	// Store relations in batches of 50
	for i := 0; i < len(result.Relations); i += batchSize {
		end := i + batchSize
		if end > len(result.Relations) {
			end = len(result.Relations)
		}
		batch := result.Relations[i:end]

		_, err := session.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
			for _, relation := range batch {
				_, err := tx.Run(ctx,
					`CREATE (r:Relation {
					     id: $id,
					     predicate: $predicate,
					     evidence: $evidence,
					     source_doc: $source_doc,
					     char_start: $char_start,
					     char_end: $char_end,
					     confidence: $confidence
					 })
					 WITH r
					 MATCH (subj:Entity {id: $subject})
					 MATCH (obj:Entity {id: $object})
					 MERGE (r)-[:HAS_SUBJECT]->(subj)
					 MERGE (r)-[:HAS_OBJECT]->(obj)
					 WITH r
					 MATCH (j:Job {id: $jobID})
					 MERGE (j)-[:HAS_RELATION]->(r)`,
					map[string]any{
						"id":         relation.ID,
						"subject":    relation.Subject,
						"object":     relation.Object,
						"predicate":  relation.Predicate,
						"evidence":   relation.Evidence,
						"source_doc": relation.SourceDoc,
						"char_start": relation.CharStart,
						"char_end":   relation.CharEnd,
						"confidence": relation.Confidence,
						"jobID":      jobID,
					})
				if err != nil {
					return nil, err
				}
			}
			return nil, nil
		})
		if err != nil {
			return fmt.Errorf("failed to store relation batch %d-%d: %w", i, end, err)
		}
	}

	log.Printf("Stored extraction result for job %s: %d entities, %d relations",
		jobID, len(result.Entities), len(result.Relations))

	return nil
}

// GetGraphForJob retrieves the graph data for a job from Neo4j
func (s *Neo4jStore) GetGraphForJob(ctx context.Context, jobID string) (*domain.GraphData, error) {
	session := s.driver.NewSession(ctx, neo4j.SessionConfig{
		DatabaseName: s.db,
	})
	defer session.Close(ctx)

	result, err := session.ExecuteRead(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
		// Get all entities for this job
		entitiesResult, err := tx.Run(ctx,
			`MATCH (j:Job {id: $jobID})-[:HAS_ENTITY]->(e:Entity)
			 OPTIONAL MATCH (e)-[:HAS_MENTION]->(m:Mention)
			 RETURN e.id as id, e.name as name, e.type as type,
			        e.source_doc as source_doc, e.aliases as aliases,
			        collect({doc_id: m.doc_id, char_start: m.char_start, char_end: m.char_end}) as mentions`,
			map[string]any{
				"jobID": jobID,
			})
		if err != nil {
			return nil, fmt.Errorf("failed to fetch entities: %w", err)
		}

		entities := []domain.Entity{}
		for entitiesResult.Next(ctx) {
			record := entitiesResult.Record()

			id, _ := record.Get("id")
			name, _ := record.Get("name")
			entityType, _ := record.Get("type")
			sourceDoc, _ := record.Get("source_doc")
			aliases, _ := record.Get("aliases")
			mentionsRaw, _ := record.Get("mentions")

			var mentionsList []domain.Mention
			if mentions, ok := mentionsRaw.([]any); ok {
				for _, m := range mentions {
					if mentionMap, ok := m.(map[string]any); ok {
						docID, _ := mentionMap["doc_id"].(string)
						charStart, _ := mentionMap["char_start"].(int64)
						charEnd, _ := mentionMap["char_end"].(int64)

						// Skip empty mentions
						if docID != "" {
							mentionsList = append(mentionsList, domain.Mention{
								DocID:     docID,
								CharStart: int(charStart),
								CharEnd:   int(charEnd),
							})
						}
					}
				}
			}

			aliasesList := []string{}
			if aliasSlice, ok := aliases.([]any); ok {
				for _, a := range aliasSlice {
					if aliasStr, ok := a.(string); ok {
						aliasesList = append(aliasesList, aliasStr)
					}
				}
			}

			entities = append(entities, domain.Entity{
				ID:        id.(string),
				Name:      name.(string),
				Type:      entityType.(string),
				SourceDoc: sourceDoc.(string),
				Aliases:   aliasesList,
				Mentions:  mentionsList,
			})
		}

		// Get all relations for this job
		relationsResult, err := tx.Run(ctx,
			`MATCH (j:Job {id: $jobID})-[:HAS_RELATION]->(r:Relation)
			 MATCH (r)-[:HAS_SUBJECT]->(subj:Entity)
			 MATCH (r)-[:HAS_OBJECT]->(obj:Entity)
			 RETURN r.id as id, r.predicate as predicate, r.evidence as evidence,
			        r.source_doc as source_doc, r.char_start as char_start,
			        r.char_end as char_end, r.confidence as confidence,
			        subj.id as subject, obj.id as object`,
			map[string]any{
				"jobID": jobID,
			})
		if err != nil {
			return nil, fmt.Errorf("failed to fetch relations: %w", err)
		}

		relations := []domain.Relation{}
		for relationsResult.Next(ctx) {
			record := relationsResult.Record()

			id, _ := record.Get("id")
			predicate, _ := record.Get("predicate")
			evidence, _ := record.Get("evidence")
			sourceDoc, _ := record.Get("source_doc")
			charStart, _ := record.Get("char_start")
			charEnd, _ := record.Get("char_end")
			confidence, _ := record.Get("confidence")
			subject, _ := record.Get("subject")
			object, _ := record.Get("object")

			relations = append(relations, domain.Relation{
				ID:         id.(string),
				Subject:    subject.(string),
				Predicate:  predicate.(string),
				Object:     object.(string),
				Evidence:   evidence.(string),
				SourceDoc:  sourceDoc.(string),
				CharStart:  int(charStart.(int64)),
				CharEnd:    int(charEnd.(int64)),
				Confidence: confidence.(float64),
			})
		}

		return &domain.GraphData{
			Entities:  entities,
			Relations: relations,
		}, nil
	})

	if err != nil {
		return nil, err
	}

	graphData := result.(*domain.GraphData)
	log.Printf("Retrieved graph for job %s: %d entities, %d relations",
		jobID, len(graphData.Entities), len(graphData.Relations))

	return graphData, nil
}

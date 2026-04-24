package graph

import (
	"math"
	"slices"
	"strings"

	"doc2graph/backend/internal/domain"
)

type displayTransform struct {
	entityByID       map[string]domain.Entity
	degreeByEntityID map[string]int
	relationsByID    map[string]domain.Relation
	docTitleByID     map[string]string
}

func buildDisplayGraph(result domain.ExtractionResult, expandMetadata bool) domain.GraphResponse {
	transform := newDisplayTransform(result)
	if expandMetadata {
		return transform.buildExpandedGraph(result)
	}
	return transform.buildCollapsedGraph(result)
}

func newDisplayTransform(result domain.ExtractionResult) displayTransform {
	entityByID := make(map[string]domain.Entity, len(result.Entities))
	degreeByEntityID := make(map[string]int, len(result.Entities))
	relationsByID := make(map[string]domain.Relation, len(result.Relations))
	docTitleByID := make(map[string]string, len(result.Documents))
	for _, document := range result.Documents {
		docTitleByID[document.ID] = document.Title
	}
	for _, entity := range result.Entities {
		entityByID[entity.ID] = entity
	}
	for _, relation := range result.Relations {
		degreeByEntityID[relation.Subject]++
		degreeByEntityID[relation.Object]++
		relationsByID[relation.ID] = relation
	}
	return displayTransform{
		entityByID:       entityByID,
		degreeByEntityID: degreeByEntityID,
		relationsByID:    relationsByID,
		docTitleByID:     docTitleByID,
	}
}

func (t displayTransform) buildExpandedGraph(result domain.ExtractionResult) domain.GraphResponse {
	entities := make([]domain.Entity, 0, len(result.Entities))
	relations := make([]domain.Relation, 0, len(result.Relations))
	for _, entity := range result.Entities {
		entityWithDisplay, _, _ := t.decorateEntity(entity, false)
		entities = append(entities, entityWithDisplay)
	}
	for _, relation := range result.Relations {
		relationWithDisplay, _, _ := t.decorateRelation(relation, nil)
		relations = append(relations, relationWithDisplay)
	}

	return domain.GraphResponse{
		Documents: result.Documents,
		Entities:  entities,
		Relations: relations,
		Display: domain.GraphDisplayResponse{
			Transformed:      true,
			MetadataExpanded: true,
		},
	}
}

func (t displayTransform) buildCollapsedGraph(result domain.ExtractionResult) domain.GraphResponse {
	visibleEntities := make([]domain.Entity, 0, len(result.Entities))
	visibleRelations := make([]domain.Relation, 0, len(result.Relations))
	display := domain.GraphDisplayResponse{Transformed: true}

	hiddenEntityIDs := make(map[string]string)

	for _, entity := range result.Entities {
		entityWithDisplay, hidden, reason := t.decorateEntity(entity, true)
		if hidden {
			hiddenEntityIDs[entity.ID] = reason
			display.HiddenEntityCount++
			switch reason {
			case "metadata_time_leaf":
				display.CollapsedTimeLeaves++
			case "metadata_place_leaf":
				display.CollapsedPlaceLeaves++
			case "metadata_org_leaf":
				display.CollapsedOrgLeaves++
			case "metadata_work_leaf":
				display.CollapsedWorkLeaves++
			}
			continue
		}
		visibleEntities = append(visibleEntities, entityWithDisplay)
	}

	for _, relation := range result.Relations {
		relationWithDisplay, hidden, hiddenReason := t.decorateRelation(relation, hiddenEntityIDs)
		if hidden {
			display.HiddenRelationCount++
			_ = hiddenReason
			continue
		}
		visibleRelations = append(visibleRelations, relationWithDisplay)
	}

	return domain.GraphResponse{
		Documents: result.Documents,
		Entities:  visibleEntities,
		Relations: visibleRelations,
		Display:   display,
	}
}

func (t displayTransform) decorateEntity(entity domain.Entity, allowHidden bool) (domain.Entity, bool, string) {
	role := "leaf"
	if entity.Type == "Person" || t.degreeByEntityID[entity.ID] >= 3 {
		role = "hub"
	}
	crossDocumentCount := uniqueMentionDocs(entity.Mentions)
	importance := computeImportance(entity.Type, t.degreeByEntityID[entity.ID], crossDocumentCount)

	hidden := false
	reason := ""
	if allowHidden {
		hidden, reason = t.shouldHideEntity(entity)
	}
	entity.Display = &domain.EntityDisplay{
		Role:               role,
		Importance:         importance,
		CrossDocumentCount: crossDocumentCount,
		Hidden:             hidden,
		HiddenReason:       reason,
	}
	return entity, hidden, reason
}

func (t displayTransform) decorateRelation(
	relation domain.Relation,
	hiddenEntityIDs map[string]string,
) (domain.Relation, bool, string) {
	role := "structural"
	if isMetadataPredicate(relation.Predicate) {
		role = "metadata"
	}

	hiddenReason := ""
	hidden := false
	if hiddenEntityIDs != nil {
		if reason, ok := hiddenEntityIDs[relation.Subject]; ok {
			hidden = true
			hiddenReason = reason
		}
		if reason, ok := hiddenEntityIDs[relation.Object]; ok {
			hidden = true
			hiddenReason = reason
		}
	}

	relation.Display = &domain.RelationDisplay{
		Role:         role,
		Hidden:       hidden,
		HiddenReason: hiddenReason,
	}
	return relation, hidden, hiddenReason
}

func (t displayTransform) shouldHideEntity(entity domain.Entity) (bool, string) {
	if t.isPrimaryEntity(entity) {
		return false, ""
	}

	switch entity.Type {
	case "Person":
		return true, "secondary_person_leaf"
	case "Time":
		return true, "metadata_time_leaf"
	case "Place":
		return true, "metadata_place_leaf"
	case "Organization":
		return true, "metadata_org_leaf"
	case "Work":
		return true, "metadata_work_leaf"
	}

	return false, ""
}

func (t displayTransform) isPrimaryEntity(entity domain.Entity) bool {
	if entity.Type != "Person" {
		return false
	}
	title := t.docTitleByID[entity.SourceDoc]
	return normalizeGraphLabel(title) == normalizeGraphLabel(entity.Name)
}

func normalizeGraphLabel(value string) string {
	return strings.Join(strings.Fields(strings.ToLower(value)), " ")
}

func (t displayTransform) onlyMetadataPredicates(entityID string, allowed []string) bool {
	for _, relation := range t.relationsByID {
		if relation.Subject != entityID && relation.Object != entityID {
			continue
		}
		if !slices.Contains(allowed, relation.Predicate) {
			return false
		}
	}
	return true
}

func computeImportance(entityType string, degree int, crossDocumentCount int) float64 {
	base := float64(degree) + float64(crossDocumentCount-1)*1.25
	switch entityType {
	case "Person":
		base += 2
	case "Organization", "Work":
		base += 1
	case "MetaGroup":
		base = 0.4
	}
	return math.Round(base*100) / 100
}

func uniqueMentionDocs(mentions []domain.Mention) int {
	docIDs := make(map[string]struct{}, len(mentions))
	for _, mention := range mentions {
		docIDs[mention.DocID] = struct{}{}
	}
	return len(docIDs)
}

func isMetadataPredicate(predicate string) bool {
	switch predicate {
	case "born_on", "died_on", "born_in", "died_in":
		return true
	default:
		return false
	}
}

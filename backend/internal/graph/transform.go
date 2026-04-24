package graph

import (
	"fmt"
	"math"
	"slices"
	"strings"

	"doc2graph/backend/internal/domain"
)

type displayTransform struct {
	entityByID       map[string]domain.Entity
	degreeByEntityID map[string]int
	relationsByID    map[string]domain.Relation
}

type hiddenMetadataLeaf struct {
	entity   domain.Entity
	relation domain.Relation
	reason   string
	anchorID string
}

type summaryGroup struct {
	id        string
	anchorID  string
	groupKind string
	leaves    []hiddenMetadataLeaf
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
	hiddenLeavesByAnchor := make(map[string][]hiddenMetadataLeaf)

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
			}
			continue
		}
		visibleEntities = append(visibleEntities, entityWithDisplay)
	}

	for _, relation := range result.Relations {
		relationWithDisplay, hidden, hiddenReason := t.decorateRelation(relation, hiddenEntityIDs)
		if hidden {
			display.HiddenRelationCount++
			anchorID, ok := t.anchorForHiddenRelation(relation, hiddenEntityIDs)
			if ok {
				hiddenEntityID := relation.Object
				if _, exists := hiddenEntityIDs[hiddenEntityID]; !exists {
					hiddenEntityID = relation.Subject
				}
				hiddenEntity := t.entityByID[hiddenEntityID]
				groupKey := summaryGroupKey(anchorID, hiddenReason)
				hiddenLeavesByAnchor[groupKey] = append(hiddenLeavesByAnchor[groupKey], hiddenMetadataLeaf{
					entity:   hiddenEntity,
					relation: relation,
					reason:   hiddenReason,
					anchorID: anchorID,
				})
			}
			continue
		}
		visibleRelations = append(visibleRelations, relationWithDisplay)
	}

	groups := buildSummaryGroups(hiddenLeavesByAnchor)
	for _, group := range groups {
		visibleEntities = append(visibleEntities, t.buildSummaryEntity(group))
		visibleRelations = append(visibleRelations, t.buildSummaryRelation(group))
	}
	display.SummaryNodeCount = len(groups)
	display.SummaryEdgeCount = len(groups)

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

func (t displayTransform) anchorForHiddenRelation(
	relation domain.Relation,
	hiddenEntityIDs map[string]string,
) (string, bool) {
	if _, ok := hiddenEntityIDs[relation.Object]; ok {
		return relation.Subject, true
	}
	if _, ok := hiddenEntityIDs[relation.Subject]; ok {
		return relation.Object, true
	}
	return "", false
}

func buildSummaryGroups(grouped map[string][]hiddenMetadataLeaf) []summaryGroup {
	groups := make([]summaryGroup, 0, len(grouped))
	for key, leaves := range grouped {
		if len(leaves) == 0 {
			continue
		}
		parts := strings.SplitN(key, "::", 2)
		if len(parts) != 2 {
			continue
		}
		groups = append(groups, summaryGroup{
			id:        fmt.Sprintf("summary:%s:%s", parts[0], parts[1]),
			anchorID:  parts[0],
			groupKind: parts[1],
			leaves:    leaves,
		})
	}
	slices.SortFunc(groups, func(a, b summaryGroup) int {
		return strings.Compare(a.id, b.id)
	})
	return groups
}

func summaryGroupKey(anchorID, reason string) string {
	return anchorID + "::" + reason
}

func (t displayTransform) buildSummaryEntity(group summaryGroup) domain.Entity {
	memberEntityIDs := make([]string, 0, len(group.leaves))
	memberRelationIDs := make([]string, 0, len(group.leaves))
	for _, leaf := range group.leaves {
		memberEntityIDs = append(memberEntityIDs, leaf.entity.ID)
		memberRelationIDs = append(memberRelationIDs, leaf.relation.ID)
	}

	label := fmt.Sprintf("%d %s facts", len(group.leaves), summaryGroupLabel(group.groupKind))
	anchor := t.entityByID[group.anchorID]
	return domain.Entity{
		ID:        group.id,
		Name:      label,
		Type:      "MetaGroup",
		SourceDoc: anchor.SourceDoc,
		Mentions:  nil,
		Display: &domain.EntityDisplay{
			Role:              "summary",
			Importance:        0.4,
			GroupKind:         group.groupKind,
			Expandable:        true,
			MemberEntityIDs:   memberEntityIDs,
			MemberRelationIDs: memberRelationIDs,
		},
	}
}

func (t displayTransform) buildSummaryRelation(group summaryGroup) domain.Relation {
	memberRelationIDs := make([]string, 0, len(group.leaves))
	for _, leaf := range group.leaves {
		memberRelationIDs = append(memberRelationIDs, leaf.relation.ID)
	}

	anchor := t.entityByID[group.anchorID]
	predicate := fmt.Sprintf("has_%s_facts", summaryGroupLabel(group.groupKind))
	return domain.Relation{
		ID:         "summary-rel:" + group.id,
		Subject:    group.anchorID,
		Predicate:  predicate,
		Object:     group.id,
		Evidence:   "",
		SourceDoc:  anchor.SourceDoc,
		CharStart:  0,
		CharEnd:    0,
		Confidence: 1,
		Display: &domain.RelationDisplay{
			Role:              "summary",
			Aggregated:        true,
			MemberRelationIDs: memberRelationIDs,
		},
	}
}

func summaryGroupLabel(reason string) string {
	switch reason {
	case "metadata_time_leaf":
		return "time"
	case "metadata_place_leaf":
		return "place"
	default:
		return "metadata"
	}
}

func (t displayTransform) shouldHideEntity(entity domain.Entity) (bool, string) {
	if t.degreeByEntityID[entity.ID] != 1 {
		return false, ""
	}

	switch entity.Type {
	case "Time":
		if t.onlyMetadataPredicates(entity.ID, []string{"born_on", "died_on"}) {
			return true, "metadata_time_leaf"
		}
	case "Place":
		if t.onlyMetadataPredicates(entity.ID, []string{"born_in", "died_in"}) && uniqueMentionDocs(entity.Mentions) == 1 {
			return true, "metadata_place_leaf"
		}
	}

	return false, ""
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

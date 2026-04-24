package domain

import "fmt"

var allowedEntityTypes = map[string]struct{}{
	"Person":       {},
	"Organization": {},
	"Place":        {},
	"Work":         {},
	"Time":         {},
}

var relationTypeConstraints = map[string]struct {
	subjectType string
	objectType  string
}{
	"influenced_by":     {subjectType: "Person", objectType: "Person"},
	"collaborated_with": {subjectType: "Person", objectType: "Person"},
	"family_of":         {subjectType: "Person", objectType: "Person"},
	"student_of":        {subjectType: "Person", objectType: "Person"},
	"worked_at":         {subjectType: "Person", objectType: "Organization"},
	"studied_at":        {subjectType: "Person", objectType: "Organization"},
	"founded":           {subjectType: "Person", objectType: "Organization"},
	"member_of":         {subjectType: "Person", objectType: "Organization"},
	"born_in":           {subjectType: "Person", objectType: "Place"},
	"died_in":           {subjectType: "Person", objectType: "Place"},
	"lived_in":          {subjectType: "Person", objectType: "Place"},
	"authored":          {subjectType: "Person", objectType: "Work"},
	"translated":        {subjectType: "Person", objectType: "Work"},
	"edited":            {subjectType: "Person", objectType: "Work"},
	"born_on":           {subjectType: "Person", objectType: "Time"},
	"died_on":           {subjectType: "Person", objectType: "Time"},
}

func ValidateExtractionResult(result ExtractionResult, documents []Document) error {
	documentLengths := make(map[string]int, len(documents))
	for _, doc := range documents {
		documentLengths[doc.ID] = len([]rune(doc.Content))
	}

	entityByID := make(map[string]Entity, len(result.Entities))
	for _, entity := range result.Entities {
		if entity.ID == "" {
			return fmt.Errorf("entity id is required")
		}
		if _, exists := entityByID[entity.ID]; exists {
			return fmt.Errorf("duplicate entity id %q", entity.ID)
		}
		if _, ok := allowedEntityTypes[entity.Type]; !ok {
			return fmt.Errorf("entity %s has unsupported type %q", entity.ID, entity.Type)
		}
		if entity.SourceDoc == "" {
			return fmt.Errorf("entity %s is missing source_doc", entity.ID)
		}
		if _, ok := documentLengths[entity.SourceDoc]; !ok {
			return fmt.Errorf("entity %s references unknown source_doc %q", entity.ID, entity.SourceDoc)
		}
		if len(entity.Mentions) == 0 {
			return fmt.Errorf("entity %s must have at least one mention", entity.ID)
		}
		for _, mention := range entity.Mentions {
			if err := validateMention(mention, documentLengths); err != nil {
				return fmt.Errorf("entity %s has invalid mention: %w", entity.ID, err)
			}
		}
		entityByID[entity.ID] = entity
	}

	relationIDs := make(map[string]struct{}, len(result.Relations))
	for _, relation := range result.Relations {
		if relation.ID == "" {
			return fmt.Errorf("relation id is required")
		}
		if _, exists := relationIDs[relation.ID]; exists {
			return fmt.Errorf("duplicate relation id %q", relation.ID)
		}
		relationIDs[relation.ID] = struct{}{}

		constraint, ok := relationTypeConstraints[relation.Predicate]
		if !ok {
			return fmt.Errorf("relation %s has unsupported predicate %q", relation.ID, relation.Predicate)
		}

		subject, ok := entityByID[relation.Subject]
		if !ok {
			return fmt.Errorf("relation %s references unknown subject %q", relation.ID, relation.Subject)
		}
		object, ok := entityByID[relation.Object]
		if !ok {
			return fmt.Errorf("relation %s references unknown object %q", relation.ID, relation.Object)
		}
		if subject.Type != constraint.subjectType || object.Type != constraint.objectType {
			return fmt.Errorf(
				"relation %s has invalid types %s -> %s for predicate %s",
				relation.ID,
				subject.Type,
				object.Type,
				relation.Predicate,
			)
		}
		if relation.SourceDoc == "" {
			return fmt.Errorf("relation %s is missing source_doc", relation.ID)
		}
		if _, ok := documentLengths[relation.SourceDoc]; !ok {
			return fmt.Errorf("relation %s references unknown source_doc %q", relation.ID, relation.SourceDoc)
		}
		if relation.CharStart < 0 || relation.CharEnd < 0 || relation.CharStart >= relation.CharEnd {
			return fmt.Errorf("relation %s has invalid char range %d:%d", relation.ID, relation.CharStart, relation.CharEnd)
		}
		if relation.CharEnd > documentLengths[relation.SourceDoc] {
			return fmt.Errorf("relation %s highlight exceeds source bounds", relation.ID)
		}
		if relation.Confidence < 0 || relation.Confidence > 1 {
			return fmt.Errorf("relation %s has invalid confidence %f", relation.ID, relation.Confidence)
		}
	}

	return nil
}

func validateMention(mention Mention, documentLengths map[string]int) error {
	if mention.DocID == "" {
		return fmt.Errorf("doc_id is required")
	}
	length, ok := documentLengths[mention.DocID]
	if !ok {
		return fmt.Errorf("unknown doc_id %q", mention.DocID)
	}
	if mention.CharStart < 0 || mention.CharEnd < 0 || mention.CharStart >= mention.CharEnd {
		return fmt.Errorf("invalid char range %d:%d", mention.CharStart, mention.CharEnd)
	}
	if mention.CharEnd > length {
		return fmt.Errorf("char range exceeds document bounds")
	}
	return nil
}

package graph

import (
	"testing"

	"doc2graph/backend/internal/domain"
)

func TestBuildDisplayGraphCollapsedAddsSummaryNodes(t *testing.T) {
	result := testExtractionResult()

	graph := buildDisplayGraph(result, false)

	if len(graph.Entities) != 2 {
		t.Fatalf("expected 2 visible primary entities, got %d", len(graph.Entities))
	}
	if len(graph.Relations) != 0 {
		t.Fatalf("expected 0 visible relations after collapsing minor leaves, got %d", len(graph.Relations))
	}
	if !graph.Display.Transformed || graph.Display.MetadataExpanded {
		t.Fatal("expected collapsed transformed graph")
	}
	if graph.Display.HiddenEntityCount != 4 {
		t.Fatalf("expected 4 hidden entities, got %d", graph.Display.HiddenEntityCount)
	}
	if graph.Display.HiddenRelationCount != 4 {
		t.Fatalf("expected 4 hidden relations, got %d", graph.Display.HiddenRelationCount)
	}
	if graph.Display.CollapsedTimeLeaves != 1 || graph.Display.CollapsedPlaceLeaves != 2 || graph.Display.CollapsedOrgLeaves != 1 {
		t.Fatalf("unexpected collapsed counts: %+v", graph.Display)
	}
	for _, entity := range graph.Entities {
		if entity.Display == nil {
			t.Fatalf("expected display metadata for entity %s", entity.ID)
		}
		if !newDisplayTransform(result).isPrimaryEntity(entity) {
			t.Fatalf("expected only primary document entities in collapsed graph, got %s", entity.Name)
		}
	}
}

func TestBuildDisplayGraphCollapsedHidesSecondaryPeople(t *testing.T) {
	result := testExtractionResult()
	result.Entities = append(result.Entities, domain.Entity{
		ID:        "P3",
		Name:      "Morehouse College",
		Type:      "Person",
		SourceDoc: "doc-1",
		Mentions:  []domain.Mention{{DocID: "doc-1", CharStart: 80, CharEnd: 97}},
	})
	result.Relations = append(result.Relations, domain.Relation{
		ID:         "R5",
		Subject:    "P1",
		Predicate:  "family_of",
		Object:     "P3",
		Evidence:   "Morehouse College",
		SourceDoc:  "doc-1",
		CharStart:  80,
		CharEnd:    97,
		Confidence: 0.5,
	})

	graph := buildDisplayGraph(result, false)

	for _, entity := range graph.Entities {
		if entity.ID == "P3" {
			t.Fatal("expected secondary person entity to be hidden in collapsed graph")
		}
	}
	if graph.Display.HiddenEntityCount != 5 {
		t.Fatalf("expected 5 hidden entities, got %d", graph.Display.HiddenEntityCount)
	}
}

func TestBuildDisplayGraphExpandedReturnsUnderlyingMetadataLeaves(t *testing.T) {
	result := testExtractionResult()

	graph := buildDisplayGraph(result, true)

	if len(graph.Entities) != 6 {
		t.Fatalf("expected all 6 entities in expanded graph, got %d", len(graph.Entities))
	}
	if len(graph.Relations) != 4 {
		t.Fatalf("expected all 4 relations in expanded graph, got %d", len(graph.Relations))
	}
	if !graph.Display.MetadataExpanded {
		t.Fatal("expected metadata expanded flag")
	}
	if graph.Display.SummaryNodeCount != 0 || graph.Display.HiddenEntityCount != 0 {
		t.Fatal("expected no hidden entities or summary nodes in expanded graph")
	}
}

func testExtractionResult() domain.ExtractionResult {
	return domain.ExtractionResult{
		Documents: []domain.ExportDocument{
			{ID: "doc-1", Title: "Albert Einstein", SourceType: "markdown"},
			{ID: "doc-2", Title: "Ada Lovelace", SourceType: "markdown"},
		},
		Entities: []domain.Entity{
			{
				ID:        "P1",
				Name:      "Albert Einstein",
				Type:      "Person",
				SourceDoc: "doc-1",
				Mentions:  []domain.Mention{{DocID: "doc-1", CharStart: 2, CharEnd: 17}},
			},
			{
				ID:        "P2",
				Name:      "Ada Lovelace",
				Type:      "Person",
				SourceDoc: "doc-2",
				Mentions:  []domain.Mention{{DocID: "doc-2", CharStart: 2, CharEnd: 14}},
			},
			{
				ID:        "T1",
				Name:      "14 March 1879",
				Type:      "Time",
				SourceDoc: "doc-1",
				Mentions:  []domain.Mention{{DocID: "doc-1", CharStart: 36, CharEnd: 49}},
			},
			{
				ID:        "L1",
				Name:      "Ulm",
				Type:      "Place",
				SourceDoc: "doc-1",
				Mentions:  []domain.Mention{{DocID: "doc-1", CharStart: 69, CharEnd: 72}},
			},
			{
				ID:        "L2",
				Name:      "London",
				Type:      "Place",
				SourceDoc: "doc-2",
				Mentions:  []domain.Mention{{DocID: "doc-2", CharStart: 32, CharEnd: 38}},
			},
			{
				ID:        "O1",
				Name:      "Royal Society",
				Type:      "Organization",
				SourceDoc: "doc-2",
				Mentions:  []domain.Mention{{DocID: "doc-2", CharStart: 50, CharEnd: 63}},
			},
		},
		Relations: []domain.Relation{
			{
				ID:         "R1",
				Subject:    "P1",
				Predicate:  "born_on",
				Object:     "T1",
				Evidence:   "14 March 1879",
				SourceDoc:  "doc-1",
				CharStart:  36,
				CharEnd:    49,
				Confidence: 0.88,
			},
			{
				ID:         "R2",
				Subject:    "P1",
				Predicate:  "born_in",
				Object:     "L1",
				Evidence:   "Ulm",
				SourceDoc:  "doc-1",
				CharStart:  69,
				CharEnd:    72,
				Confidence: 0.82,
			},
			{
				ID:         "R3",
				Subject:    "P2",
				Predicate:  "born_in",
				Object:     "L2",
				Evidence:   "London",
				SourceDoc:  "doc-2",
				CharStart:  32,
				CharEnd:    38,
				Confidence: 0.82,
			},
			{
				ID:         "R4",
				Subject:    "P2",
				Predicate:  "member_of",
				Object:     "O1",
				Evidence:   "Royal Society",
				SourceDoc:  "doc-2",
				CharStart:  50,
				CharEnd:    63,
				Confidence: 0.76,
			},
		},
	}
}

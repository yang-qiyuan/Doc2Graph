package graph

import (
	"testing"

	"doc2graph/backend/internal/domain"
)

func TestBuildDisplayGraphCollapsedAddsSummaryNodes(t *testing.T) {
	result := testExtractionResult()

	graph := buildDisplayGraph(result, false)

	if len(graph.Entities) != 6 {
		t.Fatalf("expected 6 visible entities including summaries, got %d", len(graph.Entities))
	}
	if len(graph.Relations) != 4 {
		t.Fatalf("expected 4 visible relations including summaries, got %d", len(graph.Relations))
	}
	if !graph.Display.Transformed || graph.Display.MetadataExpanded {
		t.Fatal("expected collapsed transformed graph")
	}
	if graph.Display.HiddenEntityCount != 3 {
		t.Fatalf("expected 3 hidden entities, got %d", graph.Display.HiddenEntityCount)
	}
	if graph.Display.HiddenRelationCount != 3 {
		t.Fatalf("expected 3 hidden relations, got %d", graph.Display.HiddenRelationCount)
	}
	if graph.Display.SummaryNodeCount != 3 || graph.Display.SummaryEdgeCount != 3 {
		t.Fatalf("expected 3 summary nodes and edges, got %d and %d", graph.Display.SummaryNodeCount, graph.Display.SummaryEdgeCount)
	}

	summaryNodes := 0
	summaryEdges := 0
	for _, entity := range graph.Entities {
		if entity.Display == nil {
			t.Fatalf("expected display metadata for entity %s", entity.ID)
		}
		if entity.Display.Role == "summary" {
			summaryNodes++
			if !entity.Display.Expandable {
				t.Fatalf("expected summary entity %s to be expandable", entity.ID)
			}
		}
	}
	for _, relation := range graph.Relations {
		if relation.Display != nil && relation.Display.Role == "summary" {
			summaryEdges++
		}
	}
	if summaryNodes != 3 || summaryEdges != 3 {
		t.Fatalf("expected 3 summary nodes and 3 summary edges, got %d and %d", summaryNodes, summaryEdges)
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

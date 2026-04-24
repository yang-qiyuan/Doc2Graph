package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"doc2graph/backend/internal/domain"
)

func TestGraphEndpointsReturnStoredExtractionData(t *testing.T) {
	app := newTestApp(domain.ExtractionResult{
		Documents: []domain.ExportDocument{
			{ID: "doc-1", Title: "Albert Einstein", SourceType: "markdown"},
		},
		Entities: []domain.Entity{
			{
				ID:        "E1",
				Name:      "Albert Einstein",
				Type:      "Person",
				SourceDoc: "doc-1",
				Mentions: []domain.Mention{
					{DocID: "doc-1", CharStart: 2, CharEnd: 17},
				},
			},
			{
				ID:        "E1B",
				Name:      "14 March 1879",
				Type:      "Time",
				SourceDoc: "doc-1",
				Mentions: []domain.Mention{
					{DocID: "doc-1", CharStart: 36, CharEnd: 49},
				},
			},
		},
		Relations: []domain.Relation{
			{
				ID:         "R1B",
				Subject:    "E1",
				Predicate:  "born_on",
				Object:     "E1B",
				Evidence:   "14 March 1879",
				SourceDoc:  "doc-1",
				CharStart:  36,
				CharEnd:    49,
				Confidence: 0.85,
			},
		},
	})

	body, err := json.Marshal(uploadDocumentsRequest{
		Documents: []domain.UploadDocument{
			{
				ID:         "doc-1",
				Title:      "Albert Einstein",
				SourceType: domain.SourceTypeMarkdown,
				Content:    "# Albert Einstein\n\nAlbert Einstein (14 March 1879 - 18 April 1955) was born in Ulm.",
			},
		},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	createReq := httptest.NewRequest(http.MethodPost, "/api/v1/jobs", bytes.NewReader(body))
	createRec := httptest.NewRecorder()
	app.handleJobs(createRec, createReq)

	if createRec.Code != http.StatusCreated {
		t.Fatalf("expected status %d, got %d", http.StatusCreated, createRec.Code)
	}

	var created createJobResponse
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("unmarshal create response: %v", err)
	}

	t.Run("graph", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/graph?job_id="+created.Job.ID, nil)
		rec := httptest.NewRecorder()
		app.handleGraph(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
		}

		var graph domain.GraphResponse
		if err := json.Unmarshal(rec.Body.Bytes(), &graph); err != nil {
			t.Fatalf("unmarshal graph response: %v", err)
		}
		if len(graph.Entities) != 2 || len(graph.Relations) != 1 {
			t.Fatalf("unexpected graph counts: %d entities, %d relations", len(graph.Entities), len(graph.Relations))
		}
		if !graph.Display.Transformed {
			t.Fatal("expected transformed display graph")
		}
		if graph.Display.SummaryNodeCount != 1 {
			t.Fatalf("expected 1 summary node, got %d", graph.Display.SummaryNodeCount)
		}
	})

	t.Run("graph expanded metadata", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/graph?job_id="+created.Job.ID+"&expand_metadata=true", nil)
		rec := httptest.NewRecorder()
		app.handleGraph(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
		}

		var graph domain.GraphResponse
		if err := json.Unmarshal(rec.Body.Bytes(), &graph); err != nil {
			t.Fatalf("unmarshal graph response: %v", err)
		}
		if len(graph.Entities) != 2 || len(graph.Relations) != 1 {
			t.Fatalf("unexpected expanded graph counts: %d entities, %d relations", len(graph.Entities), len(graph.Relations))
		}
		if !graph.Display.MetadataExpanded {
			t.Fatal("expected metadata expanded flag")
		}
	})

	t.Run("entity detail", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/entities/E1?job_id="+created.Job.ID, nil)
		rec := httptest.NewRecorder()
		app.handleEntityByID(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
		}
	})

	t.Run("relation evidence", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/relations/R1B/evidence?job_id="+created.Job.ID, nil)
		rec := httptest.NewRecorder()
		app.handleRelationEvidenceByID(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
		}

		var response domain.RelationEvidenceResponse
		if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
			t.Fatalf("unmarshal evidence response: %v", err)
		}
		if response.Highlight.CharStart != 36 || response.Highlight.CharEnd != 49 {
			t.Fatalf("unexpected highlight: %#v", response.Highlight)
		}
		if response.Chunk.ID == "" {
			t.Fatal("expected supporting chunk")
		}
	})

	t.Run("chunk detail", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/documents/doc-1/chunks/doc-1-chunk-000", nil)
		rec := httptest.NewRecorder()
		app.handleDocumentChunkByID(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
		}

		var response domain.ChunkDetailResponse
		if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
			t.Fatalf("unmarshal chunk response: %v", err)
		}
		if response.Chunk.ID != "doc-1-chunk-000" {
			t.Fatalf("unexpected chunk id %s", response.Chunk.ID)
		}
	})
}

package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"doc2graph/backend/internal/domain"
)

func TestCreateJobAndFetchByID(t *testing.T) {
	body, err := json.Marshal(uploadDocumentsRequest{
		Documents: []domain.UploadDocument{
			{
				ID:         "doc-1",
				Title:      "Ada Lovelace",
				SourceType: domain.SourceTypeMarkdown,
				Content:    "# Ada Lovelace\n\nAda Lovelace wrote about Charles Babbage.",
			},
		},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	app := newTestApp(domain.ExtractionResult{
		Documents: []domain.ExportDocument{
			{ID: "doc-1", Title: "Ada Lovelace", SourceType: "markdown"},
		},
		Entities: []domain.Entity{
			{
				ID:        "E1",
				Name:      "Ada Lovelace",
				Type:      "Person",
				SourceDoc: "doc-1",
				Mentions:  []domain.Mention{{DocID: "doc-1", CharStart: 2, CharEnd: 14}},
			},
		},
	})

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

	if created.Job.ID == "" {
		t.Fatal("expected job id to be set")
	}
	if len(created.Documents) != 1 {
		t.Fatalf("expected 1 document, got %d", len(created.Documents))
	}

	getReq := httptest.NewRequest(http.MethodGet, "/api/v1/jobs/"+created.Job.ID, nil)
	getRec := httptest.NewRecorder()
	app.handleJobByID(getRec, getReq)

	if getRec.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, getRec.Code)
	}

	var fetched getJobResponse
	if err := json.Unmarshal(getRec.Body.Bytes(), &fetched); err != nil {
		t.Fatalf("unmarshal get response: %v", err)
	}

	if fetched.Job.ID != created.Job.ID {
		t.Fatalf("expected job id %s, got %s", created.Job.ID, fetched.Job.ID)
	}
	if len(fetched.Documents) != 1 {
		t.Fatalf("expected 1 document, got %d", len(fetched.Documents))
	}
}

func TestFetchJobResultByID(t *testing.T) {
	app := newTestApp(domain.ExtractionResult{
		Documents: []domain.ExportDocument{
			{ID: "doc-1", Title: "Ada Lovelace", SourceType: "markdown"},
		},
		Entities: []domain.Entity{
			{
				ID:        "E1",
				Name:      "Ada Lovelace",
				Type:      "Person",
				SourceDoc: "doc-1",
				Mentions:  []domain.Mention{{DocID: "doc-1", CharStart: 2, CharEnd: 14}},
			},
			{
				ID:        "W1",
				Name:      "Notes on the Analytical Engine",
				Type:      "Work",
				SourceDoc: "doc-1",
				Mentions:  []domain.Mention{{DocID: "doc-1", CharStart: 20, CharEnd: 45}},
			},
		},
		Relations: []domain.Relation{
			{
				ID:         "R1",
				Subject:    "E1",
				Predicate:  "authored",
				Object:     "W1",
				Evidence:   "Ada Lovelace wrote notes",
				SourceDoc:  "doc-1",
				CharStart:  20,
				CharEnd:    45,
				Confidence: 0.7,
			},
		},
	})

	body, err := json.Marshal(uploadDocumentsRequest{
		Documents: []domain.UploadDocument{
			{
				ID:         "doc-1",
				Title:      "Ada Lovelace",
				SourceType: domain.SourceTypeMarkdown,
				Content:    "# Ada Lovelace\n\nAda Lovelace wrote notes on Babbage's engine.",
			},
		},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	createReq := httptest.NewRequest(http.MethodPost, "/api/v1/jobs", bytes.NewReader(body))
	createRec := httptest.NewRecorder()
	app.handleJobs(createRec, createReq)

	var created createJobResponse
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("unmarshal create response: %v", err)
	}

	resultReq := httptest.NewRequest(http.MethodGet, "/api/v1/jobs/result/"+created.Job.ID, nil)
	resultRec := httptest.NewRecorder()
	app.handleJobResultByID(resultRec, resultReq)

	if resultRec.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, resultRec.Code)
	}

	var result domain.ExtractionResult
	if err := json.Unmarshal(resultRec.Body.Bytes(), &result); err != nil {
		t.Fatalf("unmarshal result response: %v", err)
	}
	if len(result.Entities) != 2 || len(result.Relations) != 1 {
		t.Fatalf("expected 2 entities and 1 relation, got %d and %d", len(result.Entities), len(result.Relations))
	}
}

func TestCreateJobRejectsInvalidExtractionResult(t *testing.T) {
	app := newTestApp(domain.ExtractionResult{
		Documents: []domain.ExportDocument{
			{ID: "doc-1", Title: "Ada Lovelace", SourceType: "markdown"},
		},
		Entities: []domain.Entity{
			{
				ID:        "P1",
				Name:      "Ada Lovelace",
				Type:      "Person",
				SourceDoc: "doc-1",
				Mentions:  []domain.Mention{{DocID: "doc-1", CharStart: 2, CharEnd: 14}},
			},
			{
				ID:        "L1",
				Name:      "London",
				Type:      "Place",
				SourceDoc: "doc-1",
				Mentions:  []domain.Mention{{DocID: "doc-1", CharStart: 20, CharEnd: 26}},
			},
		},
		Relations: []domain.Relation{
			{
				ID:         "R1",
				Subject:    "P1",
				Predicate:  "born_on",
				Object:     "L1",
				Evidence:   "London",
				SourceDoc:  "doc-1",
				CharStart:  20,
				CharEnd:    26,
				Confidence: 0.8,
			},
		},
	})

	body, err := json.Marshal(uploadDocumentsRequest{
		Documents: []domain.UploadDocument{
			{
				ID:         "doc-1",
				Title:      "Ada Lovelace",
				SourceType: domain.SourceTypeMarkdown,
				Content:    "# Ada Lovelace\n\nAda Lovelace was born in London.",
			},
		},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	createReq := httptest.NewRequest(http.MethodPost, "/api/v1/jobs", bytes.NewReader(body))
	createRec := httptest.NewRecorder()
	app.handleJobs(createRec, createReq)

	if createRec.Code != http.StatusInternalServerError {
		t.Fatalf("expected status %d, got %d", http.StatusInternalServerError, createRec.Code)
	}
}

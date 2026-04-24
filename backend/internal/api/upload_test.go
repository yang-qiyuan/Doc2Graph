package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"doc2graph/backend/internal/domain"
)

func TestUploadDocumentsRejectsOverLimit(t *testing.T) {
	docs := make([]domain.UploadDocument, 0, domain.MaxUploadDocuments+1)
	for i := 0; i < domain.MaxUploadDocuments+1; i++ {
		docs = append(docs, domain.UploadDocument{
			ID:         "doc-" + strings.Repeat("x", 1),
			Title:      "Doc",
			SourceType: domain.SourceTypeMarkdown,
			Content:    "# Doc\n\nText",
		})
	}

	body, err := json.Marshal(uploadDocumentsRequest{Documents: docs})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents:upload", bytes.NewReader(body))
	rec := httptest.NewRecorder()

	app := NewApp()
	app.handleUploadDocuments(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status %d, got %d", http.StatusBadRequest, rec.Code)
	}
}

func TestUploadDocumentsAcceptsWikipediaFixtureSet(t *testing.T) {
	dir := filepath.Join("..", "..", "..", "testdata", "wikipedia_markdown")
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("read fixture dir: %v", err)
	}

	docs := make([]domain.UploadDocument, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".md") {
			continue
		}

		raw, err := os.ReadFile(filepath.Join(dir, entry.Name()))
		if err != nil {
			t.Fatalf("read fixture %s: %v", entry.Name(), err)
		}

		id := strings.TrimSuffix(entry.Name(), ".md")
		docs = append(docs, domain.UploadDocument{
			ID:         id,
			Title:      strings.ReplaceAll(id, "_", " "),
			SourceType: domain.SourceTypeMarkdown,
			Content:    string(raw),
		})
	}

	body, err := json.Marshal(uploadDocumentsRequest{Documents: docs})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents:upload", bytes.NewReader(body))
	rec := httptest.NewRecorder()

	app := NewApp()
	app.handleUploadDocuments(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
	}

	var resp uploadDocumentsResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}

	if len(resp.Documents) != 30 {
		t.Fatalf("expected 30 documents, got %d", len(resp.Documents))
	}

	for _, doc := range resp.Documents {
		if len(doc.Chunks) == 0 {
			t.Fatalf("document %s returned no chunks", doc.ID)
		}
	}
}

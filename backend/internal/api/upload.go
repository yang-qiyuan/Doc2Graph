package api

import (
	"encoding/json"
	"fmt"
	"net/http"

	"doc2graph/backend/internal/domain"
)

type uploadDocumentsRequest struct {
	Documents []domain.UploadDocument `json:"documents"`
}

type uploadDocumentsResponse struct {
	Documents []domain.Document `json:"documents"`
}

func decodeUploadDocumentsRequest(r *http.Request) (uploadDocumentsRequest, error) {
	defer r.Body.Close()

	var req uploadDocumentsRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		return uploadDocumentsRequest{}, fmt.Errorf("invalid request body: %w", err)
	}
	if err := domain.ValidateUploadDocuments(req.Documents); err != nil {
		return uploadDocumentsRequest{}, err
	}

	return req, nil
}

func buildUploadDocumentsResponse(req uploadDocumentsRequest) uploadDocumentsResponse {
	documents := make([]domain.Document, 0, len(req.Documents))
	for _, doc := range req.Documents {
		documents = append(documents, domain.NormalizeDocument(doc))
	}

	return uploadDocumentsResponse{Documents: documents}
}

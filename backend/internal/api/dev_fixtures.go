package api

import (
	"encoding/json"
	"net/http"

	"doc2graph/backend/internal/devfixtures"
	"doc2graph/backend/internal/domain"
	"doc2graph/backend/internal/extractor"
)

func (a *App) handleWikipediaFixtureJob(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
		return
	}

	// Accept extraction mode via either query param (?mode=validated) or a
	// small JSON body ({"mode": "validated"}). Body takes precedence.
	mode := r.URL.Query().Get("mode")
	if r.ContentLength > 0 {
		defer r.Body.Close()
		var body struct {
			Mode string `json:"mode"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err == nil && body.Mode != "" {
			mode = body.Mode
		}
	}
	if err := extractor.ValidateExtractionMode(mode); err != nil {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: err.Error()})
		return
	}

	input, err := devfixtures.LoadWikipediaFixtures()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, errorResponse{Error: err.Error()})
		return
	}

	if err := domain.ValidateUploadDocuments(input); err != nil {
		writeJSON(w, http.StatusInternalServerError, errorResponse{Error: err.Error()})
		return
	}

	req := uploadDocumentsRequest{Documents: input}
	resp := buildUploadDocumentsResponse(req)
	job, err := a.jobService.CreateAndProcess(r.Context(), resp.Documents, mode)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, errorResponse{Error: err.Error()})
		return
	}

	writeJSON(w, http.StatusCreated, createJobResponse{
		Job:       job,
		Documents: resp.Documents,
	})
}

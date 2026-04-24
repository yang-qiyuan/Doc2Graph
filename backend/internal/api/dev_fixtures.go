package api

import (
	"net/http"

	"doc2graph/backend/internal/devfixtures"
	"doc2graph/backend/internal/domain"
)

func (a *App) handleWikipediaFixtureJob(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
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
	job, err := a.jobService.CreateAndProcess(r.Context(), resp.Documents)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, errorResponse{Error: err.Error()})
		return
	}

	writeJSON(w, http.StatusCreated, createJobResponse{
		Job:       job,
		Documents: resp.Documents,
	})
}

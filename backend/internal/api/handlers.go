package api

import (
	"encoding/json"
	"net/http"
	"strings"
)

type errorResponse struct {
	Error string `json:"error"`
}

func (a *App) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (a *App) handleUploadDocuments(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
		return
	}

	req, err := decodeUploadDocumentsRequest(r)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: err.Error()})
		return
	}

	resp := buildUploadDocumentsResponse(req)
	a.store.SaveDocuments(resp.Documents)
	writeJSON(w, http.StatusOK, resp)
}

func (a *App) handleJobs(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodPost:
		req, err := decodeUploadDocumentsRequest(r)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, errorResponse{Error: err.Error()})
			return
		}

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
	default:
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
	}
}

func (a *App) handleJobByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
		return
	}

	if strings.HasPrefix(r.URL.Path, "/api/v1/jobs/result/") {
		a.handleJobResultByID(w, r)
		return
	}

	jobID := strings.TrimPrefix(r.URL.Path, "/api/v1/jobs/")
	if jobID == "" || jobID == r.URL.Path {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: "job id is required"})
		return
	}

	job, ok := a.store.GetJob(jobID)
	if !ok {
		writeJSON(w, http.StatusNotFound, errorResponse{Error: "job not found"})
		return
	}

	writeJSON(w, http.StatusOK, getJobResponse{
		Job:       job,
		Documents: a.store.ListDocumentsByIDs(job.DocumentIDs),
	})
}

func (a *App) handleJobResultByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
		return
	}

	jobID := strings.TrimPrefix(r.URL.Path, "/api/v1/jobs/result/")
	if jobID == "" || jobID == r.URL.Path {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: "job id is required"})
		return
	}

	result, ok := a.store.GetJobResult(jobID)
	if !ok {
		writeJSON(w, http.StatusNotFound, errorResponse{Error: "job result not found"})
		return
	}

	writeJSON(w, http.StatusOK, result)
}

func (a *App) handleGraph(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
		return
	}

	jobID := r.URL.Query().Get("job_id")
	if jobID == "" {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: "job_id is required"})
		return
	}

	graph, err := a.graphService.GetGraph(jobID)
	if err != nil {
		writeJSON(w, http.StatusNotFound, errorResponse{Error: err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, graph)
}

func (a *App) handleEntityByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
		return
	}

	jobID := r.URL.Query().Get("job_id")
	if jobID == "" {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: "job_id is required"})
		return
	}

	entityID := strings.TrimPrefix(r.URL.Path, "/api/v1/entities/")
	if entityID == "" || entityID == r.URL.Path {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: "entity id is required"})
		return
	}

	entity, err := a.graphService.GetEntity(jobID, entityID)
	if err != nil {
		writeJSON(w, http.StatusNotFound, errorResponse{Error: err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{"entity": entity})
}

func (a *App) handleRelationEvidenceByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
		return
	}

	jobID := r.URL.Query().Get("job_id")
	if jobID == "" {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: "job_id is required"})
		return
	}

	relationPath := strings.TrimPrefix(r.URL.Path, "/api/v1/relations/")
	if !strings.HasSuffix(relationPath, "/evidence") {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: "relation evidence path is invalid"})
		return
	}

	relationID := strings.TrimSuffix(relationPath, "/evidence")
	relationID = strings.TrimSuffix(relationID, "/")
	if relationID == "" {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: "relation id is required"})
		return
	}

	response, err := a.graphService.GetRelationEvidence(jobID, relationID)
	if err != nil {
		writeJSON(w, http.StatusNotFound, errorResponse{Error: err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, response)
}

func (a *App) handleDocumentChunkByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, errorResponse{Error: "method not allowed"})
		return
	}

	path := strings.TrimPrefix(r.URL.Path, "/api/v1/documents/")
	parts := strings.Split(path, "/")
	if len(parts) != 3 || parts[1] != "chunks" || parts[0] == "" || parts[2] == "" {
		writeJSON(w, http.StatusBadRequest, errorResponse{Error: "document chunk path is invalid"})
		return
	}

	response, err := a.graphService.GetChunk(parts[0], parts[2])
	if err != nil {
		writeJSON(w, http.StatusNotFound, errorResponse{Error: err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, response)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

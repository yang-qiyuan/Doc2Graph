package api

import "net/http"

func NewRouter() http.Handler {
	app := NewApp()
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", app.handleHealth)
	mux.HandleFunc("/api/v1/dev/fixtures/wikipedia", app.handleWikipediaFixtureJob)
	mux.HandleFunc("/api/v1/documents:upload", app.handleUploadDocuments)
	mux.HandleFunc("/api/v1/documents/", app.handleDocumentChunkByID)
	mux.HandleFunc("/api/v1/entities/", app.handleEntityByID)
	mux.HandleFunc("/api/v1/jobs", app.handleJobs)
	mux.HandleFunc("/api/v1/jobs/", app.handleJobByID)
	mux.HandleFunc("/api/v1/jobs/result/", app.handleJobResultByID)
	mux.HandleFunc("/api/v1/relations/", app.handleRelationEvidenceByID)
	mux.HandleFunc("/api/v1/graph", app.handleGraph)
	return withCORS(mux)
}

func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next.ServeHTTP(w, r)
	})
}

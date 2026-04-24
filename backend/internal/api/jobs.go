package api

import "doc2graph/backend/internal/domain"

type createJobResponse struct {
	Job       domain.Job        `json:"job"`
	Documents []domain.Document `json:"documents"`
}

type getJobResponse struct {
	Job       domain.Job        `json:"job"`
	Documents []domain.Document `json:"documents"`
}

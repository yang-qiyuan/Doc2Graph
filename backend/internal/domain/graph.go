package domain

type GraphResponse struct {
	Documents []ExportDocument `json:"documents"`
	Entities  []Entity         `json:"entities"`
	Relations []Relation       `json:"relations"`
}

type RelationEvidenceResponse struct {
	Relation  Relation `json:"relation"`
	Document  Document `json:"document"`
	Chunk     Chunk    `json:"chunk"`
	Highlight Mention  `json:"highlight"`
}

type ChunkDetailResponse struct {
	DocumentID string `json:"document_id"`
	Chunk      Chunk  `json:"chunk"`
}

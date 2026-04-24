package domain

type GraphResponse struct {
	Documents []ExportDocument     `json:"documents"`
	Entities  []Entity             `json:"entities"`
	Relations []Relation           `json:"relations"`
	Display   GraphDisplayResponse `json:"display"`
}

type GraphDisplayResponse struct {
	Transformed          bool `json:"transformed"`
	MetadataExpanded     bool `json:"metadata_expanded"`
	HiddenEntityCount    int  `json:"hidden_entity_count"`
	HiddenRelationCount  int  `json:"hidden_relation_count"`
	CollapsedTimeLeaves  int  `json:"collapsed_time_leaves"`
	CollapsedPlaceLeaves int  `json:"collapsed_place_leaves"`
	SummaryNodeCount     int  `json:"summary_node_count"`
	SummaryEdgeCount     int  `json:"summary_edge_count"`
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

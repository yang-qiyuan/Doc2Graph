package domain

type ExportDocument struct {
	ID         string `json:"id"`
	SourceType string `json:"source_type"`
	Title      string `json:"title"`
	URI        string `json:"uri,omitempty"`
}

type Mention struct {
	DocID     string `json:"doc_id"`
	CharStart int    `json:"char_start"`
	CharEnd   int    `json:"char_end"`
}

type Entity struct {
	ID        string         `json:"id"`
	Name      string         `json:"name"`
	Type      string         `json:"type"`
	Aliases   []string       `json:"aliases,omitempty"`
	SourceDoc string         `json:"source_doc"`
	Mentions  []Mention      `json:"mentions"`
	Display   *EntityDisplay `json:"display,omitempty"`
}

type Relation struct {
	ID         string           `json:"id"`
	Subject    string           `json:"subject"`
	Predicate  string           `json:"predicate"`
	Object     string           `json:"object"`
	Evidence   string           `json:"evidence"`
	SourceDoc  string           `json:"source_doc"`
	CharStart  int              `json:"char_start"`
	CharEnd    int              `json:"char_end"`
	Confidence float64          `json:"confidence"`
	Display    *RelationDisplay `json:"display,omitempty"`
}

type ExtractionResult struct {
	Documents []ExportDocument `json:"documents"`
	Entities  []Entity         `json:"entities"`
	Relations []Relation       `json:"relations"`
}

type HiddenConnection struct {
	Entity   Entity    `json:"entity"`
	Relation Relation  `json:"relation"`
	Display  *FactInfo `json:"display,omitempty"`
}

type FactInfo struct {
	Group string `json:"group,omitempty"`
}

type EntityDisplay struct {
	Role               string   `json:"role,omitempty"`
	Importance         float64  `json:"importance,omitempty"`
	CrossDocumentCount int      `json:"cross_document_count,omitempty"`
	Hidden             bool     `json:"hidden,omitempty"`
	HiddenReason       string   `json:"hidden_reason,omitempty"`
	GroupKind          string   `json:"group_kind,omitempty"`
	Expandable         bool     `json:"expandable,omitempty"`
	MemberEntityIDs    []string `json:"member_entity_ids,omitempty"`
	MemberRelationIDs  []string `json:"member_relation_ids,omitempty"`
}

type RelationDisplay struct {
	Role              string   `json:"role,omitempty"`
	Hidden            bool     `json:"hidden,omitempty"`
	HiddenReason      string   `json:"hidden_reason,omitempty"`
	Aggregated        bool     `json:"aggregated,omitempty"`
	MemberRelationIDs []string `json:"member_relation_ids,omitempty"`
}

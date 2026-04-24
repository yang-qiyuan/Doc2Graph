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
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	Type      string    `json:"type"`
	Aliases   []string  `json:"aliases,omitempty"`
	SourceDoc string    `json:"source_doc"`
	Mentions  []Mention `json:"mentions"`
}

type Relation struct {
	ID         string  `json:"id"`
	Subject    string  `json:"subject"`
	Predicate  string  `json:"predicate"`
	Object     string  `json:"object"`
	Evidence   string  `json:"evidence"`
	SourceDoc  string  `json:"source_doc"`
	CharStart  int     `json:"char_start"`
	CharEnd    int     `json:"char_end"`
	Confidence float64 `json:"confidence"`
}

type ExtractionResult struct {
	Documents []ExportDocument `json:"documents"`
	Entities  []Entity         `json:"entities"`
	Relations []Relation       `json:"relations"`
}

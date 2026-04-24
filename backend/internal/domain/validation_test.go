package domain

import "testing"

func TestValidateExtractionResultAcceptsNormalizedGraph(t *testing.T) {
	documents := []Document{
		{
			ID:         "doc-1",
			Title:      "Albert Einstein",
			SourceType: SourceTypeMarkdown,
			Content:    "# Albert Einstein\n\nAlbert Einstein (14 March 1879 - 18 April 1955) was born in Ulm.",
		},
	}

	result := ExtractionResult{
		Documents: []ExportDocument{
			{ID: "doc-1", Title: "Albert Einstein", SourceType: "markdown"},
		},
		Entities: []Entity{
			{
				ID:        "P1",
				Name:      "Albert Einstein",
				Type:      "Person",
				SourceDoc: "doc-1",
				Mentions:  []Mention{{DocID: "doc-1", CharStart: 2, CharEnd: 17}},
			},
			{
				ID:        "T1",
				Name:      "14 March 1879",
				Type:      "Time",
				SourceDoc: "doc-1",
				Mentions:  []Mention{{DocID: "doc-1", CharStart: 36, CharEnd: 49}},
			},
		},
		Relations: []Relation{
			{
				ID:         "R1",
				Subject:    "P1",
				Predicate:  "born_on",
				Object:     "T1",
				Evidence:   "14 March 1879",
				SourceDoc:  "doc-1",
				CharStart:  36,
				CharEnd:    49,
				Confidence: 0.88,
			},
		},
	}

	if err := ValidateExtractionResult(result, documents); err != nil {
		t.Fatalf("expected valid result, got %v", err)
	}
}

func TestValidateExtractionResultRejectsPredicateTypeMismatch(t *testing.T) {
	documents := []Document{
		{
			ID:         "doc-1",
			Title:      "Albert Einstein",
			SourceType: SourceTypeMarkdown,
			Content:    "# Albert Einstein\n\nAlbert Einstein (14 March 1879 - 18 April 1955) was born in Ulm.",
		},
	}

	result := ExtractionResult{
		Documents: []ExportDocument{
			{ID: "doc-1", Title: "Albert Einstein", SourceType: "markdown"},
		},
		Entities: []Entity{
			{
				ID:        "P1",
				Name:      "Albert Einstein",
				Type:      "Person",
				SourceDoc: "doc-1",
				Mentions:  []Mention{{DocID: "doc-1", CharStart: 2, CharEnd: 17}},
			},
			{
				ID:        "L1",
				Name:      "Ulm",
				Type:      "Place",
				SourceDoc: "doc-1",
				Mentions:  []Mention{{DocID: "doc-1", CharStart: 69, CharEnd: 72}},
			},
		},
		Relations: []Relation{
			{
				ID:         "R1",
				Subject:    "P1",
				Predicate:  "born_on",
				Object:     "L1",
				Evidence:   "Ulm",
				SourceDoc:  "doc-1",
				CharStart:  69,
				CharEnd:    72,
				Confidence: 0.88,
			},
		},
	}

	if err := ValidateExtractionResult(result, documents); err == nil {
		t.Fatal("expected predicate type mismatch to fail validation")
	}
}

package extractor

import (
	"context"
	"testing"

	"doc2graph/backend/internal/domain"
)

func TestPythonRunnerProducesStructuredResult(t *testing.T) {
	runner := NewPythonRunner()
	result, err := runner.Run(context.Background(), []domain.Document{
		{
			ID:         "doc-1",
			Title:      "Albert Einstein",
			SourceType: domain.SourceTypeMarkdown,
			Content:    "# Albert Einstein\n\nAlbert Einstein (14 March 1879 - 18 April 1955) was born in Ulm.",
		},
	})
	if err != nil {
		t.Fatalf("run extractor: %v", err)
	}
	if len(result.Entities) == 0 {
		t.Fatal("expected entities")
	}
	if len(result.Relations) == 0 {
		t.Fatal("expected relations")
	}
}

func TestPythonRunnerNormalizesSharedEntitiesAcrossDocuments(t *testing.T) {
	runner := NewPythonRunner()
	result, err := runner.Run(context.Background(), []domain.Document{
		{
			ID:         "doc-1",
			Title:      "Albert Einstein",
			SourceType: domain.SourceTypeMarkdown,
			Content:    "# Albert Einstein\n\nAlbert Einstein (14 March 1879 - 18 April 1955) was born in Ulm.",
		},
		{
			ID:         "doc-2",
			Title:      "Another Scientist",
			SourceType: domain.SourceTypeMarkdown,
			Content:    "# Another Scientist\n\nAnother Scientist (14 March 1879 - 1 January 1940) was born in Ulm.",
		},
	})
	if err != nil {
		t.Fatalf("run extractor: %v", err)
	}

	placeCount := 0
	timeCount := 0
	for _, entity := range result.Entities {
		if entity.Type == "Place" && entity.Name == "Ulm" {
			placeCount++
			if len(entity.Mentions) != 2 {
				t.Fatalf("expected shared place to carry 2 mentions, got %d", len(entity.Mentions))
			}
		}
		if entity.Type == "Time" && entity.Name == "14 March 1879" {
			timeCount++
			if len(entity.Mentions) != 2 {
				t.Fatalf("expected shared time to carry 2 mentions, got %d", len(entity.Mentions))
			}
		}
	}

	if placeCount != 1 {
		t.Fatalf("expected 1 normalized Ulm entity, got %d", placeCount)
	}
	if timeCount != 1 {
		t.Fatalf("expected 1 normalized birth date entity, got %d", timeCount)
	}
}

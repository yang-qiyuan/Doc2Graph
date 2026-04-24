package domain

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestBuildChunksCoversDocument(t *testing.T) {
	content := strings.Repeat("abc123 ", 600)
	chunks := BuildChunks("doc-1", content, 120, 20)

	if len(chunks) < 2 {
		t.Fatalf("expected multiple chunks, got %d", len(chunks))
	}

	runes := []rune(content)
	for i, chunk := range chunks {
		if chunk.CharStart < 0 || chunk.CharEnd > len(runes) {
			t.Fatalf("chunk %d has invalid bounds: %#v", i, chunk)
		}
		if chunk.CharStart >= chunk.CharEnd {
			t.Fatalf("chunk %d is empty: %#v", i, chunk)
		}
		expected := string(runes[chunk.CharStart:chunk.CharEnd])
		if chunk.Text != expected {
			t.Fatalf("chunk %d text mismatch", i)
		}
		if i > 0 && chunk.CharStart > chunks[i-1].CharEnd {
			t.Fatalf("chunk %d introduced a gap", i)
		}
	}
}

func TestNormalizeDocumentBuildsChunksForFixture(t *testing.T) {
	path := filepath.Join("..", "..", "..", "testdata", "wikipedia_markdown", "Albert_Einstein.md")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}

	doc := NormalizeDocument(UploadDocument{
		ID:         "doc-albert-einstein",
		Title:      "Albert Einstein",
		SourceType: SourceTypeMarkdown,
		Content:    string(raw),
	})

	if len(doc.Chunks) == 0 {
		t.Fatal("expected chunks to be generated")
	}
	if doc.Chunks[0].CharStart != 0 {
		t.Fatalf("expected first chunk to start at 0, got %d", doc.Chunks[0].CharStart)
	}

	last := doc.Chunks[len(doc.Chunks)-1]
	if last.CharEnd != len([]rune(doc.Content)) {
		t.Fatalf("expected last chunk to end at content length, got %d", last.CharEnd)
	}
}

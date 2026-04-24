package devfixtures

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"

	"doc2graph/backend/internal/domain"
)

const wikipediaFixtureDirName = "wikipedia_markdown"

func LoadWikipediaFixtures() ([]domain.UploadDocument, error) {
	dir := fixtureDir()
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read fixture directory: %w", err)
	}

	documents := make([]domain.UploadDocument, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".md") {
			continue
		}

		content, err := os.ReadFile(filepath.Join(dir, entry.Name()))
		if err != nil {
			return nil, fmt.Errorf("read fixture %s: %w", entry.Name(), err)
		}

		id := strings.TrimSuffix(entry.Name(), ".md")
		documents = append(documents, domain.UploadDocument{
			ID:         id,
			Title:      strings.ReplaceAll(id, "_", " "),
			SourceType: domain.SourceTypeMarkdown,
			Content:    string(content),
		})
	}

	slices.SortFunc(documents, func(a, b domain.UploadDocument) int {
		return strings.Compare(a.ID, b.ID)
	})

	return documents, nil
}

func fixtureDir() string {
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		return filepath.Join("..", "testdata", wikipediaFixtureDirName)
	}

	return filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", "..", "..", "testdata", wikipediaFixtureDirName))
}

package domain

import (
	"fmt"
	"strings"
)

const (
	MaxUploadDocuments  = 30
	DefaultChunkSize    = 1200
	DefaultChunkOverlap = 150
)

type SourceType string

const (
	SourceTypeMarkdown SourceType = "markdown"
	SourceTypePDF      SourceType = "pdf"
	SourceTypeURL      SourceType = "url"
)

type UploadDocument struct {
	ID         string     `json:"id"`
	Title      string     `json:"title"`
	SourceType SourceType `json:"source_type"`
	Content    string     `json:"content"`
	URI        string     `json:"uri,omitempty"`
}

type Document struct {
	ID         string     `json:"id"`
	Title      string     `json:"title"`
	SourceType SourceType `json:"source_type"`
	Content    string     `json:"content"`
	URI        string     `json:"uri,omitempty"`
	Chunks     []Chunk    `json:"chunks"`
}

type Chunk struct {
	ID        string `json:"id"`
	DocID     string `json:"doc_id"`
	Index     int    `json:"index"`
	Text      string `json:"text"`
	CharStart int    `json:"char_start"`
	CharEnd   int    `json:"char_end"`
}

func ValidateUploadDocuments(input []UploadDocument) error {
	if len(input) == 0 {
		return fmt.Errorf("at least one document is required")
	}
	if len(input) > MaxUploadDocuments {
		return fmt.Errorf("document upload cap exceeded: %d > %d", len(input), MaxUploadDocuments)
	}

	for i, doc := range input {
		if doc.ID == "" {
			return fmt.Errorf("document %d is missing id", i)
		}
		if strings.TrimSpace(doc.Title) == "" {
			return fmt.Errorf("document %s is missing title", doc.ID)
		}
		if doc.SourceType != SourceTypeMarkdown {
			return fmt.Errorf("document %s has unsupported source_type %q", doc.ID, doc.SourceType)
		}
		if strings.TrimSpace(doc.Content) == "" {
			return fmt.Errorf("document %s is empty", doc.ID)
		}
	}

	return nil
}

func NormalizeDocument(input UploadDocument) Document {
	content := strings.ReplaceAll(input.Content, "\r\n", "\n")
	content = strings.ReplaceAll(content, "\r", "\n")

	return Document{
		ID:         input.ID,
		Title:      strings.TrimSpace(input.Title),
		SourceType: input.SourceType,
		Content:    content,
		URI:        input.URI,
		Chunks:     BuildChunks(input.ID, content, DefaultChunkSize, DefaultChunkOverlap),
	}
}

func BuildChunks(docID, content string, chunkSize, overlap int) []Chunk {
	if chunkSize <= 0 {
		chunkSize = DefaultChunkSize
	}
	if overlap < 0 {
		overlap = 0
	}
	if overlap >= chunkSize {
		overlap = chunkSize / 4
	}

	runes := []rune(content)
	if len(runes) == 0 {
		return nil
	}

	chunks := make([]Chunk, 0, (len(runes)/chunkSize)+1)
	start := 0
	index := 0

	for start < len(runes) {
		end := start + chunkSize
		if end > len(runes) {
			end = len(runes)
		}

		chunks = append(chunks, Chunk{
			ID:        fmt.Sprintf("%s-chunk-%03d", docID, index),
			DocID:     docID,
			Index:     index,
			Text:      string(runes[start:end]),
			CharStart: start,
			CharEnd:   end,
		})

		if end == len(runes) {
			break
		}

		start = end - overlap
		index++
	}

	return chunks
}

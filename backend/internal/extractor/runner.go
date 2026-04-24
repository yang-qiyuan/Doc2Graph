package extractor

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"doc2graph/backend/internal/domain"
)

type Runner interface {
	Run(ctx context.Context, documents []domain.Document) (domain.ExtractionResult, error)
}

type PythonRunner struct {
	Command string
	Args    []string
	WorkDir string
}

func NewPythonRunner() *PythonRunner {
	return &PythonRunner{
		Command: "python3",
		Args: []string{
			"-m",
			"doc2graph_extractor.main",
		},
		WorkDir: defaultExtractorDir(),
	}
}

func (r *PythonRunner) Run(ctx context.Context, documents []domain.Document) (domain.ExtractionResult, error) {
	payloadDocuments := make([]map[string]any, 0, len(documents))
	for _, doc := range documents {
		payloadDocuments = append(payloadDocuments, map[string]any{
			"id":          doc.ID,
			"title":       doc.Title,
			"source_type": doc.SourceType,
			"content":     doc.Content,
			"uri":         doc.URI,
		})
	}

	payload := map[string]any{"documents": payloadDocuments}
	input, err := json.Marshal(payload)
	if err != nil {
		return domain.ExtractionResult{}, fmt.Errorf("marshal extractor request: %w", err)
	}

	cmd := exec.CommandContext(ctx, r.Command, r.Args...)
	cmd.Dir = r.WorkDir
	cmd.Env = withEnv(cmd.Environ(), "PYTHONPATH", r.WorkDir)
	cmd.Stdin = bytes.NewReader(input)

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return domain.ExtractionResult{}, fmt.Errorf("run extractor: %w: %s", err, stderr.String())
	}

	var result domain.ExtractionResult
	if err := json.Unmarshal(stdout.Bytes(), &result); err != nil {
		return domain.ExtractionResult{}, fmt.Errorf("decode extractor response: %w", err)
	}

	return result, nil
}

func defaultExtractorDir() string {
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		return "."
	}

	return filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", "..", "..", "extractor"))
}

func withEnv(env []string, key, value string) []string {
	prefix := key + "="
	filtered := make([]string, 0, len(env)+1)
	for _, item := range env {
		if strings.HasPrefix(item, prefix) {
			continue
		}
		filtered = append(filtered, item)
	}
	return append(filtered, prefix+value)
}

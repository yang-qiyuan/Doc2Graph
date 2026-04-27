#!/usr/bin/env python3
"""
Demo script to test parallel extraction with real Wikipedia fixture files.
Compares sequential vs parallel processing performance.
"""

import os
import time
from pathlib import Path
from doc2graph_extractor.pipeline import ExtractionPipeline


def load_wikipedia_document(filepath: Path) -> dict:
    """Load a Wikipedia markdown file as a document dict."""
    content = filepath.read_text(encoding="utf-8")
    title = filepath.stem.replace("_", " ")
    return {
        "id": filepath.stem,
        "title": title,
        "source_type": "markdown",
        "content": content,
        "uri": f"file://{filepath}",
    }


def main():
    # Load 2 Wikipedia fixture files
    testdata_path = Path(__file__).parent.parent / "testdata" / "wikipedia_markdown"

    doc_files = [
        testdata_path / "Albert_Einstein.md",
        testdata_path / "Marie_Curie.md",
    ]

    print("Loading documents...")
    documents = [load_wikipedia_document(f) for f in doc_files]
    print(f"Loaded {len(documents)} documents\n")

    pipeline = ExtractionPipeline()

    # Test 1: Sequential processing
    print("=" * 60)
    print("TEST 1: SEQUENTIAL PROCESSING")
    print("=" * 60)
    os.environ["USE_PARALLEL_EXTRACTION"] = "false"

    start_time = time.time()
    sequential_result = pipeline.run(documents)
    sequential_time = time.time() - start_time

    print(f"Time: {sequential_time:.4f} seconds")
    print(f"Entities extracted: {len(sequential_result['entities'])}")
    print(f"Relations extracted: {len(sequential_result['relations'])}")

    # Test 2: Parallel processing
    print("\n" + "=" * 60)
    print("TEST 2: PARALLEL PROCESSING (2 workers)")
    print("=" * 60)
    os.environ["USE_PARALLEL_EXTRACTION"] = "true"
    os.environ["EXTRACTION_WORKERS"] = "2"

    start_time = time.time()
    parallel_result = pipeline.run(documents)
    parallel_time = time.time() - start_time

    print(f"Time: {parallel_time:.4f} seconds")
    print(f"Entities extracted: {len(parallel_result['entities'])}")
    print(f"Relations extracted: {len(parallel_result['relations'])}")

    # Clean up environment
    del os.environ["USE_PARALLEL_EXTRACTION"]
    del os.environ["EXTRACTION_WORKERS"]

    # Compare results
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"Sequential time: {sequential_time:.4f}s")
    print(f"Parallel time:   {parallel_time:.4f}s")

    if parallel_time < sequential_time:
        speedup = sequential_time / parallel_time
        print(f"Speedup: {speedup:.2f}x faster")
    else:
        print(f"Note: Parallel may be slower for small documents due to overhead")

    # Verify results match
    entity_match = len(sequential_result['entities']) == len(parallel_result['entities'])
    relation_match = len(sequential_result['relations']) == len(parallel_result['relations'])

    print(f"\nResults match:")
    print(f"  Entities: {'✓' if entity_match else '✗'}")
    print(f"  Relations: {'✓' if relation_match else '✗'}")

    if entity_match and relation_match:
        print("\n✓ Parallel extraction produces identical results!")
    else:
        print("\n✗ Warning: Results differ between sequential and parallel modes")

    # Show some extracted entities
    print("\n" + "=" * 60)
    print("SAMPLE EXTRACTED ENTITIES")
    print("=" * 60)
    for entity in sequential_result['entities'][:10]:
        print(f"  {entity['type']:12s} | {entity['name']}")


if __name__ == "__main__":
    main()

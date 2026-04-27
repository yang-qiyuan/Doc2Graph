#!/usr/bin/env python3
"""
Benchmark script to compare sequential vs parallel extraction with 30 Wikipedia files.
"""

import os
import time
from pathlib import Path
from doc2graph_extractor.pipeline import ExtractionPipeline


def load_wikipedia_documents(limit=None):
    """Load Wikipedia markdown files as document dicts."""
    testdata_path = Path(__file__).parent.parent / "testdata" / "wikipedia_markdown"
    doc_files = sorted(testdata_path.glob("*.md"))

    if limit:
        doc_files = doc_files[:limit]

    documents = []
    for filepath in doc_files:
        content = filepath.read_text(encoding="utf-8")
        title = filepath.stem.replace("_", " ")
        documents.append({
            "id": filepath.stem,
            "title": title,
            "source_type": "markdown",
            "content": content,
            "uri": f"file://{filepath}",
        })

    return documents


def benchmark_extraction(documents, mode_name, use_parallel, num_workers=None):
    """Run extraction and measure time."""
    print(f"\n{'=' * 70}")
    print(f"BENCHMARK: {mode_name}")
    print(f"{'=' * 70}")
    print(f"Documents: {len(documents)}")
    print(f"Parallel: {use_parallel}")
    if num_workers:
        print(f"Workers: {num_workers}")

    # Set environment
    os.environ["USE_PARALLEL_EXTRACTION"] = "true" if use_parallel else "false"
    if num_workers:
        os.environ["EXTRACTION_WORKERS"] = str(num_workers)

    pipeline = ExtractionPipeline()

    # Warm-up run (ignore timing)
    if len(documents) > 5:
        print("Running warm-up with 2 documents...")
        pipeline.run(documents[:2])

    # Actual benchmark
    print("Starting benchmark...")
    start_time = time.time()
    result = pipeline.run(documents)
    elapsed_time = time.time() - start_time

    # Clean up environment
    if "USE_PARALLEL_EXTRACTION" in os.environ:
        del os.environ["USE_PARALLEL_EXTRACTION"]
    if "EXTRACTION_WORKERS" in os.environ:
        del os.environ["EXTRACTION_WORKERS"]

    # Report results
    print(f"\n{'─' * 70}")
    print(f"RESULTS: {mode_name}")
    print(f"{'─' * 70}")
    print(f"Time: {elapsed_time:.4f} seconds")
    print(f"Entities extracted: {len(result['entities'])}")
    print(f"Relations extracted: {len(result['relations'])}")
    print(f"Throughput: {len(documents) / elapsed_time:.2f} documents/second")
    print(f"Average per document: {(elapsed_time / len(documents)) * 1000:.2f} ms")

    return elapsed_time, result


def main():
    print("=" * 70)
    print("PARALLEL EXTRACTION BENCHMARK - Wikipedia Fixtures")
    print("=" * 70)

    # Load all 30 Wikipedia documents
    print("\nLoading Wikipedia documents...")
    documents = load_wikipedia_documents()
    print(f"Loaded {len(documents)} documents")

    # Show document sizes
    total_chars = sum(len(doc["content"]) for doc in documents)
    avg_chars = total_chars / len(documents)
    print(f"Total content size: {total_chars:,} characters")
    print(f"Average document size: {avg_chars:,.0f} characters")

    results = {}

    # Test 1: Sequential processing
    time_seq, result_seq = benchmark_extraction(
        documents,
        "Sequential Processing",
        use_parallel=False
    )
    results["sequential"] = time_seq

    # Test 2: Parallel processing with 2 workers
    time_par_2, result_par_2 = benchmark_extraction(
        documents,
        "Parallel Processing (2 workers)",
        use_parallel=True,
        num_workers=2
    )
    results["parallel_2"] = time_par_2

    # Test 3: Parallel processing with 4 workers
    time_par_4, result_par_4 = benchmark_extraction(
        documents,
        "Parallel Processing (4 workers)",
        use_parallel=True,
        num_workers=4
    )
    results["parallel_4"] = time_par_4

    # Test 4: Parallel processing with CPU count
    import multiprocessing
    cpu_count = multiprocessing.cpu_count()
    time_par_cpu, result_par_cpu = benchmark_extraction(
        documents,
        f"Parallel Processing ({cpu_count} workers - CPU count)",
        use_parallel=True,
        num_workers=cpu_count
    )
    results["parallel_cpu"] = time_par_cpu

    # Final comparison
    print(f"\n{'=' * 70}")
    print("FINAL COMPARISON")
    print(f"{'=' * 70}")
    print(f"\nProcessing {len(documents)} documents:")
    print(f"  Sequential:          {results['sequential']:.4f}s")
    print(f"  Parallel (2 workers): {results['parallel_2']:.4f}s")
    print(f"  Parallel (4 workers): {results['parallel_4']:.4f}s")
    print(f"  Parallel ({cpu_count} workers):  {results['parallel_cpu']:.4f}s")

    print(f"\nSpeedup vs Sequential:")
    print(f"  2 workers: {results['sequential'] / results['parallel_2']:.2f}x")
    print(f"  4 workers: {results['sequential'] / results['parallel_4']:.2f}x")
    print(f"  {cpu_count} workers: {results['sequential'] / results['parallel_cpu']:.2f}x")

    # Find best configuration
    best_mode = min(results.items(), key=lambda x: x[1])
    print(f"\n✓ Best configuration: {best_mode[0]} ({best_mode[1]:.4f}s)")

    # Verify results match
    entity_match_2 = len(result_seq['entities']) == len(result_par_2['entities'])
    entity_match_4 = len(result_seq['entities']) == len(result_par_4['entities'])
    entity_match_cpu = len(result_seq['entities']) == len(result_par_cpu['entities'])

    print(f"\nResults verification (entity count):")
    print(f"  2 workers: {'✓' if entity_match_2 else '✗'}")
    print(f"  4 workers: {'✓' if entity_match_4 else '✗'}")
    print(f"  {cpu_count} workers: {'✓' if entity_match_cpu else '✗'}")

    if entity_match_2 and entity_match_4 and entity_match_cpu:
        print("\n✓ All parallel modes produce identical results!")
    else:
        print("\n✗ Warning: Some results differ")


if __name__ == "__main__":
    main()

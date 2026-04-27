#!/usr/bin/env python3
"""
Realistic benchmark that measures end-to-end processing time including:
- Document preparation
- Python subprocess execution (simulating backend invocation)
- JSON serialization/deserialization
"""

import json
import subprocess
import time
from pathlib import Path


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


def benchmark_subprocess_invocation(documents, use_parallel=False, num_workers=None):
    """
    Simulate how the backend invokes the Python extractor:
    - Serialize documents to JSON
    - Spawn Python subprocess
    - Pass JSON via stdin
    - Read result from stdout
    """
    import os

    # Prepare input
    input_data = {"documents": documents}
    input_json = json.dumps(input_data)

    # Set environment
    env = os.environ.copy()
    env["USE_PARALLEL_EXTRACTION"] = "true" if use_parallel else "false"
    if num_workers:
        env["EXTRACTION_WORKERS"] = str(num_workers)

    # Measure total time including subprocess overhead
    start_time = time.time()

    # Spawn Python extractor (this is what the backend does)
    process = subprocess.Popen(
        ["python3", "-m", "doc2graph_extractor.main"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=Path(__file__).parent
    )

    stdout, stderr = process.communicate(input=input_json.encode('utf-8'))

    if process.returncode != 0:
        print(f"ERROR: Process failed with code {process.returncode}")
        print(f"STDERR: {stderr.decode('utf-8')}")
        return None, None

    # Parse result
    result = json.loads(stdout.decode('utf-8'))

    elapsed_time = time.time() - start_time

    return elapsed_time, result


def main():
    print("=" * 70)
    print("REALISTIC END-TO-END BENCHMARK")
    print("(Includes subprocess spawning and JSON serialization)")
    print("=" * 70)

    # Test with different document counts
    for doc_count in [5, 10, 17, 30]:
        print(f"\n{'=' * 70}")
        print(f"Testing with {doc_count} documents")
        print(f"{'=' * 70}")

        documents = load_wikipedia_documents(limit=doc_count)
        total_chars = sum(len(doc["content"]) for doc in documents)
        print(f"Total content: {total_chars:,} characters")

        # Sequential
        print(f"\nSequential processing...")
        time_seq, result_seq = benchmark_subprocess_invocation(documents, use_parallel=False)
        if time_seq:
            print(f"  Time: {time_seq:.4f}s")
            print(f"  Entities: {len(result_seq['entities'])}")
            print(f"  Relations: {len(result_seq['relations'])}")

        # Parallel with 4 workers
        print(f"\nParallel processing (4 workers)...")
        time_par, result_par = benchmark_subprocess_invocation(documents, use_parallel=True, num_workers=4)
        if time_par:
            print(f"  Time: {time_par:.4f}s")
            print(f"  Entities: {len(result_par['entities'])}")
            print(f"  Relations: {len(result_par['relations'])}")
            print(f"  Speedup: {time_seq / time_par:.2f}x")

    print(f"\n{'=' * 70}")
    print("Note: This benchmark includes subprocess spawning overhead")
    print("but does NOT include:")
    print("  - Backend HTTP server overhead")
    print("  - Neo4j database writes")
    print("  - Frontend network requests")
    print("  - Frontend rendering")
    print("=" * 70)


if __name__ == "__main__":
    main()

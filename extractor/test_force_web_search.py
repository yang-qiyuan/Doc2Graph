#!/usr/bin/env python3
"""
Force web search disambiguation by setting a high confidence threshold.

This demonstrates the web search feature in action by requiring very high
confidence (0.9) for fusion, which will trigger web search for most entity pairs.
"""

import json
import os
from pathlib import Path

# Load environment variables
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

from doc2graph_extractor.agent import ValidationAgent
from doc2graph_extractor.pipeline import ExtractionPipeline


def load_test_documents():
    """Load test fixture documents."""
    fixture_dir = Path(__file__).parent / "fusion_not_enough_info"

    docs = []
    # Only use the ambiguous pair
    for filename in ["person_a_minimal.md", "person_b_detailed.md"]:
        filepath = fixture_dir / filename
        if not filepath.exists():
            continue

        content = filepath.read_text(encoding="utf-8")
        title = filepath.stem.replace("_", " ")
        docs.append({
            "id": filepath.stem,
            "title": title,
            "source_type": "markdown",
            "content": content,
        })

    return docs


def main():
    print("=" * 70)
    print("FORCED WEB SEARCH DISAMBIGUATION TEST")
    print("=" * 70)
    print("\nThis test forces web search by setting a HIGH confidence threshold (0.9)")
    print("Any fusion with confidence < 0.9 will trigger web search")

    # Load test documents
    documents = load_test_documents()
    print(f"\nLoaded {len(documents)} documents:")
    for doc in documents:
        print(f"  - {doc['title']}")

    # Run extraction
    print("\nRunning regex extraction first...")
    os.environ["EXTRACTION_MODE"] = "regex"
    pipeline = ExtractionPipeline()
    result = pipeline.run(documents)

    entities = [
        {
            'id': e['id'],
            'name': e['name'],
            'type': e['type'],
            'mentions': e.get('mentions', []),
            'aliases': e.get('aliases', [])
        }
        for e in result['entities']
    ]

    print(f"Extracted {len(entities)} entities")

    # Perform fusion with HIGH threshold to force web search
    print("\n" + "=" * 70)
    print("CROSS-DOCUMENT FUSION WITH WEB SEARCH")
    print("=" * 70)
    print(f"Confidence threshold: 0.9 (HIGH - will trigger web search)")

    agent = ValidationAgent()

    print("\nCalling cross_document_fusion with web_search_threshold=0.9...")
    merges = agent.cross_document_fusion(
        entities,
        use_web_search=True,
        web_search_threshold=0.9  # HIGH threshold to force web search
    )

    # Display results
    print(f"\n{'=' * 70}")
    print("RESULTS")
    print(f"{'=' * 70}")

    if merges:
        print(f"\nMerges performed: {len(merges)}")
        for source_id, target_id, aliases in merges:
            print(f"\n  {source_id}")
            print(f"    → {target_id}")
            if aliases:
                print(f"    Aliases: {', '.join(aliases)}")
    else:
        print("\nNo merges performed")

    print(f"\n{'=' * 70}")
    print("Check the stderr output above to see web search in action!")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()

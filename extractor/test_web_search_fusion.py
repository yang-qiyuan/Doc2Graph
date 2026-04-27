#!/usr/bin/env python3
"""
Test web search-based entity fusion disambiguation.

This test uses two documents:
1. Marie Curie with detailed information
2. Maria Sklodowska with minimal information

The agent should use web search to determine they are the same person.
"""

import json
import os
from pathlib import Path

# Load environment variables from .env file
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# Set extraction mode to validated (which includes fusion)
os.environ["EXTRACTION_MODE"] = "validated"

from doc2graph_extractor.pipeline import ExtractionPipeline


def load_test_documents():
    """Load test fixture documents."""
    fixture_dir = Path(__file__).parent / "fusion_not_enough_info"

    docs = []
    for filepath in sorted(fixture_dir.glob("*.md")):
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
    print("WEB SEARCH FUSION DISAMBIGUATION TEST")
    print("=" * 70)

    # Load test documents
    documents = load_test_documents()
    print(f"\nLoaded {len(documents)} documents:")
    for doc in documents:
        print(f"  - {doc['title']}")

    # Run extraction with validated mode (includes fusion with web search)
    print("\nRunning extraction with cross-document fusion...")
    print("This will use web search if fusion confidence is low (<0.5)")

    pipeline = ExtractionPipeline()
    result = pipeline.run(documents)

    # Display results
    print(f"\n{'=' * 70}")
    print("EXTRACTION RESULTS")
    print(f"{'=' * 70}")

    print(f"\nEntities extracted: {len(result['entities'])}")
    for entity in result['entities']:
        print(f"  {entity['type']:12s} | {entity['name']}")
        if entity.get('aliases'):
            print(f"                     Aliases: {', '.join(entity['aliases'])}")

    print(f"\nRelations extracted: {len(result['relations'])}")

    # Check if fusion happened
    person_entities = [e for e in result['entities'] if e['type'] == 'Person']
    print(f"\n{'=' * 70}")
    print("FUSION CHECK")
    print(f"{'=' * 70}")

    print(f"\nPerson entities found: {len(person_entities)}")
    if len(person_entities) == 1:
        person = person_entities[0]
        print(f"\n✓ SUCCESS: Entities were fused!")
        print(f"  Name: {person['name']}")
        print(f"  Aliases: {person.get('aliases', [])}")
        print(f"  Mentions: {len(person.get('mentions', []))}")

        # Check if both original names are represented
        names = {person['name']} | set(person.get('aliases', []))
        has_marie = any('Marie' in name or 'marie' in name.lower() for name in names)
        has_maria = any('Maria' in name or 'maria' in name.lower() for name in names)

        if has_marie and has_maria:
            print("\n✓ Both 'Marie Curie' and 'Maria Sklodowska' are represented!")
        else:
            print(f"\n⚠ Warning: Missing name variants")
            print(f"   Has Marie: {has_marie}, Has Maria: {has_maria}")

    elif len(person_entities) == 2:
        print(f"\n✗ FAILED: Entities were NOT fused (still 2 separate Person entities)")
        for person in person_entities:
            print(f"  - {person['name']}")
    else:
        print(f"\n⚠ Unexpected: Found {len(person_entities)} Person entities")

    # Save result for inspection
    output_file = Path(__file__).parent / "test_web_search_fusion_result.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nFull result saved to: {output_file}")


if __name__ == "__main__":
    main()

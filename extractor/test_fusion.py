#!/usr/bin/env python3
"""
Test script for cross-document entity fusion.

This script tests the fusion of Marie Curie and Maria Skłodowska entities
from two separate documents.
"""

import json
import os
import sys
from pathlib import Path

# Add the package to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables from .env file
from dotenv import load_dotenv
env_file = Path(__file__).parent / '.env'
if env_file.exists():
    load_dotenv(env_file)

from doc2graph_extractor.pipeline import ExtractionPipeline


def load_document(file_path: Path, doc_id: str) -> dict:
    """Load a markdown document."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract title from first line
    lines = content.strip().split('\n')
    title = lines[0].strip('# ').strip() if lines else 'Untitled'

    return {
        'id': doc_id,
        'title': title,
        'content': content,
        'source_type': 'markdown',
        'uri': str(file_path)
    }


def main():
    # Set environment to validated mode
    os.environ['EXTRACTION_MODE'] = 'validated'

    # Load the two test documents
    fusion_dir = Path(__file__).parent / 'fusion_test_file'
    documents = [
        load_document(fusion_dir / 'marie_curie.md', 'doc1'),
        load_document(fusion_dir / 'maria_sklodowska.md', 'doc2'),
    ]

    print("=" * 80)
    print("Testing Cross-Document Entity Fusion")
    print("=" * 80)
    print(f"\nLoaded {len(documents)} documents:")
    for doc in documents:
        print(f"  - {doc['id']}: {doc['title']}")

    # Run extraction with fusion
    print("\nRunning extraction with cross-document fusion...")
    pipeline = ExtractionPipeline()
    result = pipeline.run(documents)

    # Display results
    print("\n" + "=" * 80)
    print("Extraction Results")
    print("=" * 80)

    print(f"\nTotal entities: {len(result['entities'])}")
    print("\nPerson entities:")
    for entity in result['entities']:
        if entity['type'] == 'Person':
            aliases_str = f" (aliases: {', '.join(entity['aliases'])})" if entity['aliases'] else ""
            print(f"  - {entity['name']}{aliases_str}")
            print(f"    ID: {entity['id']}")
            print(f"    Source: {entity['source_doc']}")

    print(f"\nTotal relations: {len(result['relations'])}")

    # Check if fusion worked
    person_entities = [e for e in result['entities'] if e['type'] == 'Person']
    person_names = {e['name'] for e in person_entities}

    print("\n" + "=" * 80)
    print("Fusion Check")
    print("=" * 80)

    # Check if Marie Curie and Maria Skłodowska are merged
    has_marie = 'Marie Curie' in person_names
    has_maria = 'Maria Skłodowska' in person_names

    if has_marie and not has_maria:
        # Check if Maria is an alias of Marie
        marie_entity = next((e for e in person_entities if e['name'] == 'Marie Curie'), None)
        if marie_entity and 'Maria Skłodowska' in marie_entity.get('aliases', []):
            print("✓ SUCCESS: Entities merged correctly!")
            print(f"  - Primary name: Marie Curie")
            print(f"  - Aliases: {', '.join(marie_entity['aliases'])}")
        else:
            print("✗ PARTIAL: Marie Curie exists but Maria Skłodowska not found in aliases")
    elif not has_marie and has_maria:
        # Check if Marie is an alias of Maria
        maria_entity = next((e for e in person_entities if e['name'] == 'Maria Skłodowska'), None)
        if maria_entity and 'Marie Curie' in maria_entity.get('aliases', []):
            print("✓ SUCCESS: Entities merged correctly!")
            print(f"  - Primary name: Maria Skłodowska")
            print(f"  - Aliases: {', '.join(maria_entity['aliases'])}")
        else:
            print("✗ PARTIAL: Maria Skłodowska exists but Marie Curie not found in aliases")
    elif has_marie and has_maria:
        print("✗ FAILURE: Both entities still exist separately - fusion did not work")
        print("  - Marie Curie: separate entity")
        print("  - Maria Skłodowska: separate entity")
    else:
        print("? UNKNOWN: Neither entity found")

    # Save result to file for inspection
    output_file = Path(__file__).parent / 'fusion_test_result.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nFull results saved to: {output_file}")


if __name__ == '__main__':
    main()

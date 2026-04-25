#!/usr/bin/env python3
"""
Test script to verify that the agentic loop is working.
"""

import json
import os
import sys

# Load .env file manually
env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

# Set environment variables for testing
os.environ["ENABLE_AGENTIC_LOOP"] = "true"

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from doc2graph_extractor.pipeline import ExtractionPipeline

# Create a simple test document
test_document = {
    "id": "test_doc_1",
    "title": "Marie Curie",
    "content": """Marie Curie (1867 – 1934) was born in Warsaw, Poland.
She studied at the University of Paris and worked at the Radium Institute.
She authored "Treatise on Radioactivity" and collaborated with Pierre Curie.
Marie Curie was influenced by Henri Becquerel.""",
    "source_type": "markdown",
    "uri": "test://marie-curie"
}

print("=" * 80)
print("Testing Agentic Loop Integration")
print("=" * 80)
print()

# Check if agent is available
try:
    from doc2graph_extractor.agent import ValidationAgent
    print("✓ ValidationAgent module imported successfully")
    print(f"✓ ENABLE_AGENTIC_LOOP = {os.getenv('ENABLE_AGENTIC_LOOP')}")
    print(f"✓ API Key configured: {bool(os.getenv('ANTHROPIC_API_KEY'))}")
except ImportError as e:
    print(f"✗ Failed to import ValidationAgent: {e}")
    sys.exit(1)

print()
print("-" * 80)
print("Running extraction pipeline...")
print("-" * 80)
print()

# Monkey-patch the ValidationAgent to detect when it's called
original_validate = ValidationAgent.validate
call_count = [0]

def tracked_validate(self, document, entities, relations):
    call_count[0] += 1
    print(f"\n>>> ValidationAgent.validate() called! (call #{call_count[0]})")
    print(f"    Document: {document['title']}")
    print(f"    Entities to validate: {len(entities)}")
    print(f"    Relations to validate: {len(relations)}")
    print()

    result = original_validate(self, document, entities, relations)

    print(f"<<< ValidationAgent.validate() completed")
    print(f"    Validated entities: {len(result[0])}")
    print(f"    Validated relations: {len(result[1])}")
    print()

    return result

ValidationAgent.validate = tracked_validate

try:
    pipeline = ExtractionPipeline()
    result = pipeline.run([test_document])

    print()
    print("=" * 80)
    print("Test Results")
    print("=" * 80)
    print()

    if call_count[0] > 0:
        print(f"✓ SUCCESS: Agent was called {call_count[0]} time(s)")
        print(f"✓ Extracted {len(result['entities'])} entities")
        print(f"✓ Extracted {len(result['relations'])} relations")
        print()
        print("The agentic loop is WORKING!")
    else:
        print("✗ FAILURE: Agent was NOT called")
        print("The agentic loop is NOT working - falling back to regex-only extraction")

    print()

except Exception as e:
    print()
    print("=" * 80)
    print(f"ERROR: {e}")
    print("=" * 80)
    import traceback
    traceback.print_exc()
    sys.exit(1)

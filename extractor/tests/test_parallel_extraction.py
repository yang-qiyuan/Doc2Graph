import os
from doc2graph_extractor.pipeline import ExtractionPipeline


def test_parallel_extraction_produces_same_results_as_sequential():
    """
    Test that parallel extraction with 2 documents produces the same results
    as sequential extraction.
    """
    # Two test documents
    documents = [
        {
            "id": "doc-1",
            "title": "Albert Einstein",
            "source_type": "markdown",
            "content": "# Albert Einstein\n\nAlbert Einstein (14 March 1879 - 18 April 1955) was born in Ulm. He worked at ETH Zurich.",
        },
        {
            "id": "doc-2",
            "title": "Marie Curie",
            "source_type": "markdown",
            "content": "# Marie Curie\n\nMarie Curie (7 November 1867 - 4 July 1934) was born in Warsaw. She studied at University of Paris.",
        },
    ]

    pipeline = ExtractionPipeline()

    # Run sequential extraction
    os.environ["USE_PARALLEL_EXTRACTION"] = "false"
    sequential_result = pipeline.run(documents)

    # Run parallel extraction
    os.environ["USE_PARALLEL_EXTRACTION"] = "true"
    parallel_result = pipeline.run(documents)

    # Clean up environment
    del os.environ["USE_PARALLEL_EXTRACTION"]

    # Compare results - entities should be the same
    assert len(sequential_result["entities"]) == len(parallel_result["entities"]), \
        f"Entity count mismatch: sequential={len(sequential_result['entities'])}, parallel={len(parallel_result['entities'])}"

    # Compare relations - should be the same
    assert len(sequential_result["relations"]) == len(parallel_result["relations"]), \
        f"Relation count mismatch: sequential={len(sequential_result['relations'])}, parallel={len(parallel_result['relations'])}"

    # Verify entity types and names match
    sequential_entity_set = {(e["id"], e["name"], e["type"]) for e in sequential_result["entities"]}
    parallel_entity_set = {(e["id"], e["name"], e["type"]) for e in parallel_result["entities"]}
    assert sequential_entity_set == parallel_entity_set, \
        f"Entity sets don't match:\nSequential: {sequential_entity_set}\nParallel: {parallel_entity_set}"

    # Verify relation predicates match
    sequential_relation_set = {
        (r["subject"], r["predicate"], r["object"]) for r in sequential_result["relations"]
    }
    parallel_relation_set = {
        (r["subject"], r["predicate"], r["object"]) for r in parallel_result["relations"]
    }
    assert sequential_relation_set == parallel_relation_set, \
        f"Relation sets don't match:\nSequential: {sequential_relation_set}\nParallel: {parallel_relation_set}"


def test_parallel_extraction_with_two_workers():
    """
    Test parallel extraction with explicit worker count.
    """
    documents = [
        {
            "id": "doc-1",
            "title": "Isaac Newton",
            "source_type": "markdown",
            "content": "# Isaac Newton\n\nIsaac Newton (25 December 1642 - 20 March 1726) was born in Woolsthorpe.",
        },
        {
            "id": "doc-2",
            "title": "Galileo Galilei",
            "source_type": "markdown",
            "content": "# Galileo Galilei\n\nGalileo Galilei (15 February 1564 - 8 January 1642) was born in Pisa.",
        },
    ]

    pipeline = ExtractionPipeline()

    # Run with 2 workers
    os.environ["USE_PARALLEL_EXTRACTION"] = "true"
    os.environ["EXTRACTION_WORKERS"] = "2"
    result = pipeline.run(documents)

    # Clean up environment
    del os.environ["USE_PARALLEL_EXTRACTION"]
    del os.environ["EXTRACTION_WORKERS"]

    # Verify we got results from both documents
    assert len(result["entities"]) >= 6, f"Expected at least 6 entities, got {len(result['entities'])}"
    assert len(result["relations"]) >= 4, f"Expected at least 4 relations, got {len(result['relations'])}"

    # Verify we have both Person entities
    person_names = {e["name"] for e in result["entities"] if e["type"] == "Person"}
    assert "Isaac Newton" in person_names
    assert "Galileo Galilei" in person_names


def test_single_document_uses_sequential_mode():
    """
    Test that single document extraction doesn't use parallel mode even if enabled.
    """
    documents = [
        {
            "id": "doc-1",
            "title": "Charles Darwin",
            "source_type": "markdown",
            "content": "# Charles Darwin\n\nCharles Darwin (12 February 1809 - 19 April 1882) was born in Shrewsbury.",
        },
    ]

    pipeline = ExtractionPipeline()

    # Enable parallel mode (should fall back to sequential for single document)
    os.environ["USE_PARALLEL_EXTRACTION"] = "true"
    result = pipeline.run(documents)

    # Clean up environment
    del os.environ["USE_PARALLEL_EXTRACTION"]

    # Verify we got results
    assert len(result["entities"]) >= 3
    person_entities = [e for e in result["entities"] if e["type"] == "Person"]
    assert len(person_entities) == 1
    assert person_entities[0]["name"] == "Charles Darwin"

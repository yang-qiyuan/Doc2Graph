"""Test enhanced extraction patterns for all relation types."""
from doc2graph_extractor.pipeline import ExtractionPipeline


def test_extraction_of_all_relation_types():
    """Test that the extractor can extract all supported relation types."""
    pipeline = ExtractionPipeline()

    # Create a test document with various relation patterns
    test_document = {
        "id": "test_001",
        "title": "Albert Einstein",
        "source_type": "markdown",
        "content": """Albert Einstein (1879 – 1955) was born in Ulm, Germany.
        He studied at ETH Zurich and worked at the Swiss Patent Office.
        He lived in Princeton for many years and founded the Institute for Advanced Study.
        Einstein was a member of the Prussian Academy of Sciences.
        He wrote "The Theory of Relativity" and edited "Annalen der Physik".
        Einstein collaborated with Niels Bohr and was influenced by Ernst Mach.
        He was the son of Hermann Einstein.""",
        "uri": "",
    }

    result = pipeline.run([test_document])

    # Verify we have entities
    assert len(result["entities"]) > 0

    # Verify we have multiple relations
    assert len(result["relations"]) > 0

    # Extract predicates to verify different relation types
    predicates = {rel["predicate"] for rel in result["relations"]}

    # Check that we extracted various relation types
    assert "born_on" in predicates  # PERSON-TIME
    assert "died_on" in predicates  # PERSON-TIME
    assert "born_in" in predicates  # PERSON-PLACE
    assert "lived_in" in predicates  # PERSON-PLACE
    assert "studied_at" in predicates  # PERSON-ORG
    assert "worked_at" in predicates  # PERSON-ORG
    assert "founded" in predicates  # PERSON-ORG
    assert "member_of" in predicates  # PERSON-ORG
    assert "authored" in predicates  # PERSON-WORK
    assert "edited" in predicates  # PERSON-WORK
    assert "collaborated_with" in predicates  # PERSON-PERSON
    assert "influenced_by" in predicates  # PERSON-PERSON
    assert "family_of" in predicates  # PERSON-PERSON

    # Verify entity types
    entity_types = {ent["type"] for ent in result["entities"]}
    assert "Person" in entity_types
    assert "Time" in entity_types
    assert "Place" in entity_types
    assert "Organization" in entity_types
    assert "Work" in entity_types

    print(f"\nExtracted {len(result['relations'])} relations with predicates: {predicates}")
    print(f"Extracted {len(result['entities'])} entities of types: {entity_types}")


def test_person_person_relations():
    """Test extraction of PERSON-PERSON relations."""
    pipeline = ExtractionPipeline()

    document = {
        "id": "test_002",
        "title": "Marie Curie",
        "source_type": "markdown",
        "content": """Marie Curie (1867 – 1934) was born in Warsaw.
        She was influenced by Henri Becquerel and collaborated with Pierre Curie.
        She was the daughter of Bronisława Curie and was a student of Paul Langevin.""",
        "uri": "",
    }

    result = pipeline.run([document])
    predicates = {rel["predicate"] for rel in result["relations"]}

    assert "influenced_by" in predicates
    assert "collaborated_with" in predicates
    assert "family_of" in predicates
    assert "student_of" in predicates


def test_person_work_relations():
    """Test extraction of PERSON-WORK relations."""
    pipeline = ExtractionPipeline()

    document = {
        "id": "test_003",
        "title": "Charles Darwin",
        "source_type": "markdown",
        "content": """Charles Darwin (1809 – 1882) wrote "On the Origin of Species"
        and edited "The Descent of Man". He also translated "The Formation of Vegetable Mould".""",
        "uri": "",
    }

    result = pipeline.run([document])
    predicates = {rel["predicate"] for rel in result["relations"]}

    assert "authored" in predicates
    assert "edited" in predicates
    assert "translated" in predicates

    # Verify Work entities were extracted
    entity_types = {ent["type"] for ent in result["entities"]}
    assert "Work" in entity_types

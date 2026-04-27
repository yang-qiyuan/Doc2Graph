from doc2graph_extractor.pipeline import ExtractionPipeline


def test_pipeline_extracts_person_and_time_relations():
    pipeline = ExtractionPipeline()
    result = pipeline.run(
        [
            {
                "id": "doc-1",
                "title": "Albert Einstein",
                "source_type": "markdown",
                "content": "# Albert Einstein\n\nAlbert Einstein (14 March 1879 - 18 April 1955) was born in Ulm.",
            }
        ]
    )

    assert len(result["entities"]) >= 3
    assert any(entity["name"] == "Albert Einstein" for entity in result["entities"])
    predicates = {relation["predicate"] for relation in result["relations"]}
    assert "born_on" in predicates
    assert "died_on" in predicates
    assert "born_in" in predicates


def test_pipeline_normalizes_shared_place_and_time_entities_across_documents():
    pipeline = ExtractionPipeline()
    result = pipeline.run(
        [
            {
                "id": "doc-1",
                "title": "Albert Einstein",
                "source_type": "markdown",
                "content": "# Albert Einstein\n\nAlbert Einstein (14 March 1879 - 18 April 1955) was born in Ulm.",
            },
            {
                "id": "doc-2",
                "title": "Another Scientist",
                "source_type": "markdown",
                "content": "# Another Scientist\n\nAnother Scientist (14 March 1879 - 1 January 1940) was born in Ulm.",
            },
        ]
    )

    place_entities = [entity for entity in result["entities"] if entity["type"] == "Place" and entity["name"] == "Ulm"]
    time_entities = [
        entity for entity in result["entities"] if entity["type"] == "Time" and entity["name"] == "14 March 1879"
    ]

    assert len(place_entities) == 1
    assert len(place_entities[0]["mentions"]) == 2
    assert len(time_entities) == 1
    assert len(time_entities[0]["mentions"]) == 2

    born_in_targets = {
        relation["object"] for relation in result["relations"] if relation["predicate"] == "born_in"
    }
    assert born_in_targets == {place_entities[0]["id"]}


def test_pipeline_extracts_all_occurrences_of_each_relation_type():
    """Recall: regex must capture every occurrence per pattern, not just the first."""
    pipeline = ExtractionPipeline()
    result = pipeline.run(
        [
            {
                "id": "doc-recall",
                "title": "Jane Doe",
                "source_type": "markdown",
                "content": (
                    "# Jane Doe\n\n"
                    "Jane Doe (1900 - 1980) worked at Acme Corporation. "
                    "Then she worked at Globex Industries. "
                    "Finally she worked at Initech. "
                    "Earlier she studied at Stanford University. "
                    "She also studied at MIT. "
                    "She lived in Paris. "
                    "Later she lived in Berlin."
                ),
            }
        ]
    )

    predicates = [relation["predicate"] for relation in result["relations"]]
    assert predicates.count("worked_at") == 3
    assert predicates.count("studied_at") == 2
    assert predicates.count("lived_in") == 2

    worked_at_evidence = sorted(
        relation["evidence"]
        for relation in result["relations"]
        if relation["predicate"] == "worked_at"
    )
    assert worked_at_evidence == ["Acme Corporation", "Globex Industries", "Initech"]

    # Distinct character spans confirm we're not collapsing onto the first match.
    worked_at_spans = {
        (relation["char_start"], relation["char_end"])
        for relation in result["relations"]
        if relation["predicate"] == "worked_at"
    }
    assert len(worked_at_spans) == 3


def test_pipeline_accumulates_multiple_mentions_for_repeated_entity():
    """An entity referenced via the same pattern multiple times should accumulate mentions."""
    pipeline = ExtractionPipeline()
    result = pipeline.run(
        [
            {
                "id": "doc-mentions",
                "title": "John Smith",
                "source_type": "markdown",
                "content": (
                    "# John Smith\n\n"
                    "John Smith lived in Paris for two years. "
                    "Later he lived in Paris and retired."
                ),
            }
        ]
    )

    paris_entities = [
        entity for entity in result["entities"]
        if entity["type"] == "Place" and entity["name"] == "Paris"
    ]
    assert len(paris_entities) == 1
    assert len(paris_entities[0]["mentions"]) == 2

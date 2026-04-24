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

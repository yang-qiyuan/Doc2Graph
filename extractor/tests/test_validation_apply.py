"""Unit tests for the LLM-add path in ValidationAgent.

These exercise the apply layer without calling Claude — we feed synthetic
validation responses directly into the agent and check that new entities
and new relations are merged, resolved by name, and given valid spans.
"""
from doc2graph_extractor.agent import ValidationAgent


def _make_agent() -> ValidationAgent:
    # The Anthropic client only validates the key on first request, so a
    # placeholder is fine for unit tests that never call .messages.create().
    return ValidationAgent(api_key="test-key")


def test_apply_adds_new_entity_with_explicit_span():
    agent = _make_agent()
    document = {
        "id": "doc-1",
        "content": "Marie Curie was a chemist working in Paris and later in Geneva.",
    }
    entities = [
        {
            "id": "doc-1:person:marie curie",
            "name": "Marie Curie",
            "type": "Person",
            "aliases": [],
            "source_doc": "doc-1",
            "mentions": [{"doc_id": "doc-1", "char_start": 0, "char_end": 11}],
        },
    ]
    relations: list[dict] = []

    new_entities = [
        {
            "name": "Geneva",
            "type": "Place",
            "char_start": 56,
            "char_end": 62,
        },
    ]

    refined_entities, _ = agent._apply_new_entities_and_relations(
        document, entities, relations, new_entities, []
    )

    geneva = next((e for e in refined_entities if e["name"] == "Geneva"), None)
    assert geneva is not None
    assert geneva["type"] == "Place"
    assert geneva["mentions"] == [
        {"doc_id": "doc-1", "char_start": 56, "char_end": 62}
    ]


def test_apply_resolves_new_relation_by_name():
    agent = _make_agent()
    document = {
        "id": "doc-1",
        "content": "Marie Curie was a chemist working in Paris and later in Geneva.",
    }
    entities = [
        {
            "id": "doc-1:person:marie curie",
            "name": "Marie Curie",
            "type": "Person",
            "aliases": [],
            "source_doc": "doc-1",
            "mentions": [{"doc_id": "doc-1", "char_start": 0, "char_end": 11}],
        },
    ]

    new_entities = [
        {"name": "Geneva", "type": "Place", "char_start": 56, "char_end": 62},
    ]
    new_relations = [
        {
            "subject": "Marie Curie",
            "subject_type": "Person",
            "predicate": "lived_in",
            "object": "Geneva",
            "object_type": "Place",
            "evidence": "later in Geneva",
            "char_start": 47,
            "char_end": 62,
            "confidence": 0.78,
        },
    ]

    refined_entities, refined_relations = agent._apply_new_entities_and_relations(
        document, entities, [], new_entities, new_relations
    )

    geneva_id = next(e["id"] for e in refined_entities if e["name"] == "Geneva")
    marie_id = next(e["id"] for e in refined_entities if e["name"] == "Marie Curie")

    lived_in = [r for r in refined_relations if r["predicate"] == "lived_in"]
    assert len(lived_in) == 1
    assert lived_in[0]["subject"] == marie_id
    assert lived_in[0]["object"] == geneva_id
    assert lived_in[0]["evidence"] == "later in Geneva"
    assert lived_in[0]["confidence"] == 0.78


def test_apply_drops_relation_with_unresolved_endpoint():
    agent = _make_agent()
    document = {"id": "doc-1", "content": "Marie Curie was born in Warsaw."}
    entities = [
        {
            "id": "doc-1:person:marie curie",
            "name": "Marie Curie",
            "type": "Person",
            "aliases": [],
            "source_doc": "doc-1",
            "mentions": [{"doc_id": "doc-1", "char_start": 0, "char_end": 11}],
        },
    ]
    new_relations = [
        {
            # "Pierre Curie" is not in the entity set and not added — must drop.
            "subject": "Marie Curie",
            "subject_type": "Person",
            "predicate": "family_of",
            "object": "Pierre Curie",
            "object_type": "Person",
            "evidence": "",
        },
    ]

    _, refined_relations = agent._apply_new_entities_and_relations(
        document, entities, [], [], new_relations
    )
    assert refined_relations == []


def test_apply_falls_back_to_find_when_span_invalid():
    agent = _make_agent()
    document = {"id": "doc-1", "content": "Marie Curie lived in Paris."}
    new_entities = [
        # Bogus offsets — the implementation must fall back to content.find().
        {"name": "Paris", "type": "Place", "char_start": 9999, "char_end": 99999},
    ]

    refined_entities, _ = agent._apply_new_entities_and_relations(
        document, [], [], new_entities, []
    )
    paris = next((e for e in refined_entities if e["name"] == "Paris"), None)
    assert paris is not None
    expected_start = document["content"].find("Paris")
    assert paris["mentions"][0]["char_start"] == expected_start
    assert paris["mentions"][0]["char_end"] == expected_start + len("Paris")


def test_apply_folds_alias_into_existing_entity_instead_of_duplicating():
    agent = _make_agent()
    document = {"id": "doc-1", "content": "Marie Curie, also known as Madame Curie."}
    entities = [
        {
            "id": "doc-1:person:marie curie",
            "name": "Marie Curie",
            "type": "Person",
            "aliases": [],
            "source_doc": "doc-1",
            "mentions": [{"doc_id": "doc-1", "char_start": 0, "char_end": 11}],
        },
    ]
    # LLM "rediscovers" Marie Curie under an alias — must merge, not duplicate.
    new_entities = [
        {
            "name": "Marie Curie",
            "type": "Person",
            "aliases": ["Madame Curie"],
            "char_start": 0,
            "char_end": 11,
        },
    ]
    refined_entities, _ = agent._apply_new_entities_and_relations(
        document, entities, [], new_entities, []
    )
    persons = [e for e in refined_entities if e["type"] == "Person"]
    assert len(persons) == 1
    assert "Madame Curie" in persons[0]["aliases"]

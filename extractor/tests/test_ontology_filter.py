"""Regression tests for the ontology type-pair filter in `_normalize_graph`.

The Go backend's `ValidateExtractionResult` rejects the entire job if any
relation's `(subject_type, predicate, object_type)` falls outside the
ontology. The LLM in `validated` mode can occasionally type an entity
wrong (e.g., "Prussian Academy of Sciences" as Work instead of
Organization) and emit a `member_of` relation pointing to it; this test
suite ensures the extractor strips those relations before they reach
the backend rather than letting the whole job fail.
"""
from __future__ import annotations

from doc2graph_extractor.models import Entity, Mention, Relation
from doc2graph_extractor.pipeline import (
    ExtractionPipeline,
    _is_relation_type_pair_valid,
)


def _person(eid: str, name: str) -> Entity:
    return Entity(
        id=eid,
        name=name,
        type="Person",
        source_doc="d",
        mentions=[Mention(doc_id="d", char_start=0, char_end=len(name))],
    )


def _other(eid: str, name: str, etype: str) -> Entity:
    return Entity(
        id=eid,
        name=name,
        type=etype,
        source_doc="d",
        mentions=[Mention(doc_id="d", char_start=0, char_end=len(name))],
    )


def _relation(rid: str, subject: str, predicate: str, obj: str) -> Relation:
    return Relation(
        id=rid,
        subject=subject,
        predicate=predicate,
        object=obj,
        evidence="evidence",
        source_doc="d",
        char_start=0,
        char_end=8,
        confidence=0.9,
    )


def test_helper_accepts_canonical_pairs():
    assert _is_relation_type_pair_valid("member_of", "Person", "Organization")
    assert _is_relation_type_pair_valid("born_on", "Person", "Time")
    assert _is_relation_type_pair_valid("collaborated_with", "Person", "Person")


def test_helper_rejects_screenshot_bug_case():
    """The exact failure from the screenshot: Person -> Work for member_of."""
    assert not _is_relation_type_pair_valid("member_of", "Person", "Work")


def test_helper_rejects_unknown_predicate():
    assert not _is_relation_type_pair_valid("knows", "Person", "Person")


def test_normalize_graph_drops_invalid_type_pair_relation():
    """Mirror of the screenshot bug: an LLM-added Work entity tagged with a
    member_of relation must be silently dropped, not propagated."""
    pipeline = ExtractionPipeline()
    entities = [
        _person("p1", "Albert Einstein"),
        _other("o1", "Prussian Academy of Sciences", "Organization"),
        _other("w1", "Prussian Academy of Sciences", "Work"),  # LLM mis-typed it
    ]
    relations = [
        _relation("R-good", "p1", "member_of", "o1"),
        _relation("R-bad", "p1", "member_of", "w1"),  # invalid: Person -> Work
    ]

    norm_entities, norm_relations = pipeline._normalize_graph(entities, relations)

    predicates_with_objects = [
        (
            r.predicate,
            next((e.type for e in norm_entities if e.id == r.object), None),
        )
        for r in norm_relations
    ]
    # The valid Person -> Organization member_of survives; the Person -> Work
    # one is filtered out before the backend ever sees it.
    assert ("member_of", "Organization") in predicates_with_objects
    assert ("member_of", "Work") not in predicates_with_objects


def test_normalize_graph_keeps_all_valid_relations_unchanged():
    """The filter must be a no-op when every relation is well-typed."""
    pipeline = ExtractionPipeline()
    entities = [
        _person("p1", "Marie Curie"),
        _other("o1", "Sorbonne", "Organization"),
        _other("t1", "1867", "Time"),
        _other("l1", "Warsaw", "Place"),
        _other("w1", "Treatise on Radioactivity", "Work"),
        _person("p2", "Pierre Curie"),
    ]
    relations = [
        _relation("r1", "p1", "studied_at", "o1"),
        _relation("r2", "p1", "born_on", "t1"),
        _relation("r3", "p1", "born_in", "l1"),
        _relation("r4", "p1", "authored", "w1"),
        _relation("r5", "p1", "family_of", "p2"),
    ]

    _, norm_relations = pipeline._normalize_graph(entities, relations)
    assert len(norm_relations) == len(relations)


def test_normalize_graph_drops_unknown_predicate():
    pipeline = ExtractionPipeline()
    entities = [_person("p1", "Marie Curie"), _person("p2", "Pierre Curie")]
    relations = [
        _relation("r1", "p1", "knows", "p2"),  # not in ontology
        _relation("r2", "p1", "family_of", "p2"),  # valid
    ]
    _, norm_relations = pipeline._normalize_graph(entities, relations)
    predicates = [r.predicate for r in norm_relations]
    assert predicates == ["family_of"]

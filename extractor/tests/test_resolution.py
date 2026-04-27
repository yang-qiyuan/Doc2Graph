"""Unit tests for the entity-resolution helpers in resolution.py."""
from doc2graph_extractor.resolution import (
    block_candidate_pairs,
    build_evidence_pack,
    transitive_closure,
)


def _entity(eid: str, name: str, etype: str = "Person", **extra) -> dict:
    return {
        "id": eid,
        "name": name,
        "type": etype,
        "aliases": extra.get("aliases", []),
        "source_doc": extra.get("source_doc", "doc"),
        "mentions": extra.get("mentions", []),
    }


def test_blocking_pairs_via_shared_name_token():
    """Marie Curie and Marie Skłodowska-Curie share the surname token 'curie'."""
    entities = [
        _entity("p1", "Marie Curie", "Person"),
        _entity("p2", "Marie Skłodowska-Curie", "Person"),
        _entity("p3", "Albert Einstein", "Person"),
    ]
    pairs, unresolved = block_candidate_pairs(entities, [])
    pair_ids = set(pairs)

    assert ("p1", "p2") in pair_ids
    assert ("p1", "p3") not in pair_ids and ("p2", "p3") not in pair_ids


def test_blocking_pairs_via_shared_attribute_when_names_diverge():
    """Marie Curie and Maria Skłodowska share zero name tokens but co-locate
    via shared family_of and born_on relations — the canonical attribute
    blocking case the old char-similarity implementation could not handle."""
    entities = [
        _entity("marie", "Marie Curie", "Person"),
        _entity("maria", "Maria Skłodowska", "Person"),
        _entity("pierre", "Pierre Curie", "Person"),
        _entity("y1867", "1867", "Time"),
    ]
    relations = [
        {"subject": "marie", "predicate": "family_of", "object": "pierre"},
        {"subject": "maria", "predicate": "family_of", "object": "pierre"},
        {"subject": "marie", "predicate": "born_on", "object": "y1867"},
        {"subject": "maria", "predicate": "born_on", "object": "y1867"},
    ]
    pairs, _ = block_candidate_pairs(entities, relations)
    assert ("maria", "marie") in pairs


def test_blocking_uses_wikipedia_summary_for_sparse_entities():
    """Two stub entities with no relations and no shared name tokens still pair
    when Wikipedia surfaces a connecting proper-noun token (e.g., the maiden
    name in Marie Curie's official summary)."""
    entities = [
        _entity("marie", "Marie Curie", "Person"),
        _entity("maria", "Maria Skłodowska", "Person"),
    ]

    def fake_wiki(name: str) -> str | None:
        if name == "Marie Curie":
            return "Marie Curie, born Maria Salomea Skłodowska, was a Polish physicist."
        if name == "Maria Skłodowska":
            return "Maria Skłodowska, later known as Marie Curie, won two Nobel Prizes."
        return None

    pairs, unresolved = block_candidate_pairs(
        entities, [], wiki_fetcher=fake_wiki, sparse_relation_threshold=2
    )
    assert ("maria", "marie") in pairs
    assert unresolved == []


def test_blocking_logs_unresolved_when_no_signal_anywhere():
    """A name-only stub with no relations and no Wikipedia hit ends up
    in the unresolved bucket so a human can review."""
    entities = [_entity("ghost", "Some Obscure Person", "Person")]
    pairs, unresolved = block_candidate_pairs(
        entities, [], wiki_fetcher=lambda _: None
    )
    assert pairs == []
    assert unresolved == ["ghost"]


def test_blocking_skips_overly_broad_keys():
    """When a token like 'foundation' is shared by many organizations, it
    becomes uninformative and must not produce N² candidate pairs."""
    entities = [
        _entity(f"o{i}", f"{name} Foundation", "Organization")
        for i, name in enumerate([
            "Curie", "Einstein", "Darwin", "Turing", "Bohr",
            "Lovelace", "Aristotle", "Plato", "Socrates", "Nobel",
        ])
    ]
    pairs, _ = block_candidate_pairs(entities, [])
    # 'foundation' appears in 10/10 entities — must be filtered out.
    # Other tokens are unique per entity, so no pairs survive.
    assert pairs == []


def test_transitive_closure_three_way_merge():
    clusters = transitive_closure([("A", "B"), ("B", "C"), ("D", "E")])
    # A, B, C all share one root; D, E share another.
    assert clusters["A"] == clusters["B"] == clusters["C"]
    assert clusters["D"] == clusters["E"]
    assert clusters["A"] != clusters["D"]


def test_transitive_closure_picks_lex_smallest_root():
    clusters = transitive_closure([("zeta", "alpha"), ("alpha", "mu")])
    assert clusters["zeta"] == "alpha"
    assert clusters["mu"] == "alpha"


def test_evidence_pack_collects_dated_facts_and_affiliations():
    entity = _entity(
        "p1",
        "Marie Curie",
        "Person",
        source_doc="doc-1",
        mentions=[{"doc_id": "doc-1", "char_start": 0, "char_end": 11}],
    )
    other = _entity("t1", "1867", "Time", source_doc="doc-1")
    other2 = _entity("o1", "Sorbonne", "Organization", source_doc="doc-1")
    document = {
        "id": "doc-1",
        "content": "Marie Curie was born in 1867 and studied at the Sorbonne.",
    }
    relations = [
        {
            "id": "R1",
            "subject": "p1",
            "predicate": "born_on",
            "object": "t1",
            "evidence": "1867",
            "source_doc": "doc-1",
            "char_start": 24,
            "char_end": 28,
            "confidence": 0.88,
        },
        {
            "id": "R2",
            "subject": "p1",
            "predicate": "studied_at",
            "object": "o1",
            "evidence": "Sorbonne",
            "source_doc": "doc-1",
            "char_start": 48,
            "char_end": 56,
            "confidence": 0.78,
        },
    ]

    pack = build_evidence_pack(
        entity,
        entities_by_id={"p1": entity, "t1": other, "o1": other2},
        relations=relations,
        documents_by_id={"doc-1": document},
    )

    assert pack.dated_facts == {"born_on": ["1867"]}
    assert pack.affiliations == {"studied_at": ["Sorbonne"]}
    assert pack.mention_contexts and "Marie Curie" in pack.mention_contexts[0]


def test_evidence_pack_handles_missing_document_gracefully():
    entity = _entity("p1", "Anna", "Person", source_doc="missing-doc", mentions=[])
    pack = build_evidence_pack(
        entity,
        entities_by_id={"p1": entity},
        relations=[],
        documents_by_id={},
    )
    assert pack.entity_id == "p1"
    assert pack.mention_contexts == []

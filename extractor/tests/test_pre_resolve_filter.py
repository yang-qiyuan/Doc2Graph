"""Pre-resolve filter and tightened blocking thresholds.

These prevent the pipeline from sending obviously-different pairs to
Claude — the cost-saving rule that protects against scenarios like
'Einstein (born 1879) vs Turing (born 1912) shouldn't trigger an LLM
call.'
"""
from __future__ import annotations

from doc2graph_extractor.models import Entity, Mention, Relation
from doc2graph_extractor.pipeline import ExtractionPipeline
from doc2graph_extractor.resolution import (
    block_candidate_pairs,
    is_obviously_incompatible,
)


# ---------------------------------------------------------------------------
# is_obviously_incompatible — direct unit tests
# ---------------------------------------------------------------------------

def _person(eid: str, name: str) -> dict:
    return {"id": eid, "name": name, "type": "Person", "source_doc": "d", "mentions": []}


def _time(eid: str, name: str) -> dict:
    return {"id": eid, "name": name, "type": "Time", "source_doc": "d", "mentions": []}


def _place(eid: str, name: str) -> dict:
    return {"id": eid, "name": name, "type": "Place", "source_doc": "d", "mentions": []}


def _rel(subject: str, predicate: str, obj: str) -> dict:
    return {
        "id": f"r-{subject}-{predicate}-{obj}",
        "subject": subject,
        "predicate": predicate,
        "object": obj,
    }


def test_pre_filter_rejects_different_birth_years():
    """The canonical Einstein-vs-Turing case: born_on years disjoint."""
    a = _person("a", "Albert Einstein")
    b = _person("b", "Alan Turing")
    t1879 = _time("t1879", "March 14, 1879")
    t1912 = _time("t1912", "23 June 1912")
    relations = [
        _rel("a", "born_on", "t1879"),
        _rel("b", "born_on", "t1912"),
    ]
    entities_by_id = {e["id"]: e for e in (a, b, t1879, t1912)}
    reason = is_obviously_incompatible(a, b, relations, entities_by_id)
    assert reason is not None and "born_on" in reason


def test_pre_filter_rejects_different_death_years():
    a = _person("a", "Person A")
    b = _person("b", "Person B")
    relations = [
        _rel("a", "died_on", "t1900"),
        _rel("b", "died_on", "t1980"),
    ]
    entities_by_id = {e["id"]: e for e in (a, b, _time("t1900", "1900"), _time("t1980", "1980"))}
    reason = is_obviously_incompatible(a, b, relations, entities_by_id)
    assert reason is not None and "died_on" in reason


def test_pre_filter_rejects_disjoint_birthplaces():
    a = _person("a", "Person A")
    b = _person("b", "Person B")
    relations = [
        _rel("a", "born_in", "p-warsaw"),
        _rel("b", "born_in", "p-london"),
    ]
    entities_by_id = {
        e["id"]: e
        for e in (a, b, _place("p-warsaw", "Warsaw"), _place("p-london", "London"))
    }
    reason = is_obviously_incompatible(a, b, relations, entities_by_id)
    assert reason is not None and "born_in" in reason


def test_pre_filter_accepts_matching_birth_year():
    """Same year → compatible (resolver gets to decide)."""
    a = _person("a", "Marie Curie")
    b = _person("b", "Maria Skłodowska")
    relations = [
        _rel("a", "born_on", "t1867a"),
        _rel("b", "born_on", "t1867b"),
    ]
    entities_by_id = {
        e["id"]: e
        for e in (a, b, _time("t1867a", "November 7, 1867"), _time("t1867b", "1867"))
    }
    assert is_obviously_incompatible(a, b, relations, entities_by_id) is None


def test_pre_filter_accepts_when_one_side_lacks_predicate():
    """Stubs without a born_on relation must not be rejected — we don't
    have enough signal to say they're different."""
    a = _person("a", "Person A")
    b = _person("b", "Person B")
    relations = [_rel("a", "born_on", "t1879")]  # only A has born_on
    entities_by_id = {
        e["id"]: e for e in (a, b, _time("t1879", "1879"))
    }
    assert is_obviously_incompatible(a, b, relations, entities_by_id) is None


def test_pre_filter_does_not_use_lived_in_or_family():
    """lived_in and family_of are multi-valued / role-ambiguous and must
    not trigger rejection on disjointness."""
    a = _person("a", "Marie Curie")
    b = _person("b", "Marie Curie alt")
    relations = [
        _rel("a", "lived_in", "p-paris"),
        _rel("b", "lived_in", "p-warsaw"),  # she lived in both
        _rel("a", "family_of", "p-pierre"),
        _rel("b", "family_of", "p-bronisława"),  # spouse vs mother
    ]
    entities_by_id = {
        e["id"]: e
        for e in (
            a, b,
            _place("p-paris", "Paris"),
            _place("p-warsaw", "Warsaw"),
            _person("p-pierre", "Pierre Curie"),
            _person("p-bronisława", "Bronisława Curie"),
        )
    }
    assert is_obviously_incompatible(a, b, relations, entities_by_id) is None


# ---------------------------------------------------------------------------
# block_candidate_pairs — tightened threshold rules
# ---------------------------------------------------------------------------

def _entity(eid: str, name: str, etype: str = "Person") -> dict:
    return {
        "id": eid,
        "name": name,
        "type": etype,
        "aliases": [],
        "source_doc": "d",
        "mentions": [],
    }


def test_blocking_requires_two_keys_when_both_rich():
    """Two rich entities sharing only one common name token (e.g. given
    name) should NOT become a candidate pair."""
    a = _entity("a", "Albert Einstein")
    b = _entity("b", "Albert Hofmann")
    # Both have ≥ 2 attached relations → "rich"
    relations = [
        _rel("a", "born_on", "t-a-y"),
        _rel("a", "lived_in", "p-a-x"),
        _rel("b", "born_on", "t-b-y"),
        _rel("b", "lived_in", "p-b-x"),
    ]
    pairs, _ = block_candidate_pairs([a, b], relations)
    assert (a["id"], b["id"]) not in {tuple(sorted(p)) for p in pairs}


def test_blocking_pairs_when_two_keys_shared_for_rich():
    """Same surname AND given name → 2 shared name tokens → pairs."""
    a = _entity("a", "Marie Curie")
    b = _entity("b", "Marie Curie")
    relations = [
        _rel("a", "born_on", "t-a-y"),
        _rel("a", "lived_in", "p-a-x"),
        _rel("b", "born_on", "t-b-y"),
        _rel("b", "lived_in", "p-b-x"),
    ]
    pairs, _ = block_candidate_pairs([a, b], relations)
    assert (a["id"], b["id"]) in {tuple(sorted(p)) for p in pairs}


def test_blocking_still_pairs_sparse_on_single_key():
    """Sparse entities can still pair on a single shared key — they have
    less structured signal anyway, so we keep the looser rule."""
    a = _entity("a", "Marie Curie")  # 0 relations
    b = _entity("b", "Marie Skłodowska")  # 0 relations
    pairs, _ = block_candidate_pairs([a, b], [])
    # Sparse + no shared tokens → no pair (which is correct).
    # Use a shared family_of attribute key to exercise the sparse branch.
    a2 = _entity("a2", "Marie Curie alt")
    b2 = _entity("b2", "Maria Skłodowska alt")
    relations = [
        _rel("a2", "family_of", "p-pierre"),
        _rel("b2", "family_of", "p-pierre"),
    ]
    pairs2, _ = block_candidate_pairs(
        [a2, b2, _entity("p-pierre", "Pierre Curie")], relations
    )
    assert (a2["id"], b2["id"]) in {tuple(sorted(p)) for p in pairs2}


# ---------------------------------------------------------------------------
# Integration: pipeline-level — Einstein vs Turing should not reach resolver
# ---------------------------------------------------------------------------

class _NeverCalledAgent:
    """Asserts the pairwise resolver is never invoked."""

    def __init__(self) -> None:
        self.calls: list = []

    def resolve_pair(self, *_args, **_kwargs):  # pragma: no cover - failure path
        self.calls.append(_args)
        raise AssertionError("resolve_pair should not have been called")

    def review_merged_relations(self, *_args, **_kwargs):
        return {}


def test_pipeline_does_not_resolve_einstein_vs_turing(monkeypatch):
    """End-to-end: two Person entities with disjoint born_on years and
    disjoint name tokens must not reach pairwise resolution."""
    monkeypatch.setenv("FUSION_CONFIDENCE_THRESHOLD", "0.5")
    monkeypatch.setenv("FUSION_SPARSE_THRESHOLD", "0")

    docs = [
        {"id": "doc-einstein", "title": "Albert Einstein", "content": "..."},
        {"id": "doc-turing", "title": "Alan Turing", "content": "..."},
    ]
    entities = [
        Entity(
            id="e-einstein",
            name="Albert Einstein",
            type="Person",
            source_doc="doc-einstein",
            mentions=[Mention(doc_id="doc-einstein", char_start=0, char_end=15)],
        ),
        Entity(
            id="e-turing",
            name="Alan Turing",
            type="Person",
            source_doc="doc-turing",
            mentions=[Mention(doc_id="doc-turing", char_start=0, char_end=11)],
        ),
        Entity(
            id="t1879", name="1879", type="Time",
            source_doc="doc-einstein",
            mentions=[Mention(doc_id="doc-einstein", char_start=0, char_end=4)],
        ),
        Entity(
            id="t1912", name="1912", type="Time",
            source_doc="doc-turing",
            mentions=[Mention(doc_id="doc-turing", char_start=0, char_end=4)],
        ),
    ]
    relations = [
        Relation(
            id="r1", subject="e-einstein", predicate="born_on", object="t1879",
            evidence="1879", source_doc="doc-einstein",
            char_start=0, char_end=4, confidence=0.9,
        ),
        Relation(
            id="r2", subject="e-turing", predicate="born_on", object="t1912",
            evidence="1912", source_doc="doc-turing",
            char_start=0, char_end=4, confidence=0.9,
        ),
    ]

    pipeline = ExtractionPipeline()
    agent = _NeverCalledAgent()
    out_entities, out_relations = pipeline._resolve_cross_document(
        docs, entities, relations, agent, wiki_fetcher=lambda _n: None
    )

    # Both Person entities survive separately — never merged.
    person_names = {e.name for e in out_entities if e.type == "Person"}
    assert person_names == {"Albert Einstein", "Alan Turing"}
    # And the resolver was never called.
    assert agent.calls == []

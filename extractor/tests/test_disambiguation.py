"""Tests for tiered disambiguation, pair cache, and wiki cache."""
import pytest

from doc2graph_extractor.models import Entity, Mention, Relation
from doc2graph_extractor.pipeline import ExtractionPipeline


@pytest.fixture(autouse=True)
def confidence_threshold(monkeypatch):
    monkeypatch.setenv("FUSION_CONFIDENCE_THRESHOLD", "0.5")
    # Disable blocking-time Wikipedia enrichment so these tests can isolate
    # the tier-2 disambiguation behavior. Blocking-time wiki is exercised
    # in test_resolution.py instead.
    monkeypatch.setenv("FUSION_SPARSE_THRESHOLD", "0")


class StubAgent:
    """Records resolve_pair calls and returns scripted responses by tier."""

    def __init__(self, by_tier: dict[int, dict]):
        self.by_tier = by_tier
        self.calls: list[tuple[str, str, int]] = []

    def resolve_pair(self, pack_a: dict, pack_b: dict) -> dict:
        if "wikipedia_summary" in pack_a or "wikipedia_summary" in pack_b:
            tier = 2
        elif "full_document_text" in pack_a or "full_document_text" in pack_b:
            tier = 1
        else:
            tier = 0
        self.calls.append((pack_a["id"], pack_b["id"], tier))
        return dict(self.by_tier[tier])

    def review_merged_relations(self, *_args, **_kwargs):
        return {}


def _docs() -> list[dict]:
    return [
        {
            "id": "doc-marie-fr",
            "title": "Marie Curie",
            "content": "Marie Curie was born in 1867.",
        },
        {
            "id": "doc-maria-pl",
            "title": "Maria Skłodowska",
            "content": "Maria Skłodowska was born in 1867.",
        },
    ]


def _fixture() -> tuple[list[Entity], list[Relation]]:
    """Two Person entities that don't share name tokens but share a
    born_on→1867 relation. Multi-signal blocking surfaces them via the
    attribute key `born_on:1867` even though the names differ."""
    entities = [
        Entity(
            id="doc-marie-fr:person:marie curie",
            name="Marie Curie",
            type="Person",
            source_doc="doc-marie-fr",
            mentions=[Mention(doc_id="doc-marie-fr", char_start=0, char_end=11)],
        ),
        Entity(
            id="doc-maria-pl:person:maria skłodowska",
            name="Maria Skłodowska",
            type="Person",
            source_doc="doc-maria-pl",
            mentions=[Mention(doc_id="doc-maria-pl", char_start=0, char_end=16)],
        ),
        Entity(
            id="t1867",
            name="1867",
            type="Time",
            source_doc="doc-marie-fr",
            mentions=[Mention(doc_id="doc-marie-fr", char_start=24, char_end=28)],
        ),
    ]
    relations = [
        Relation(
            id="r1",
            subject="doc-marie-fr:person:marie curie",
            predicate="born_on",
            object="t1867",
            evidence="1867",
            source_doc="doc-marie-fr",
            char_start=24,
            char_end=28,
            confidence=0.9,
        ),
        Relation(
            id="r2",
            subject="doc-maria-pl:person:maria skłodowska",
            predicate="born_on",
            object="t1867",
            evidence="1867",
            source_doc="doc-maria-pl",
            char_start=29,
            char_end=33,
            confidence=0.9,
        ),
    ]
    return entities, relations


def test_high_confidence_at_tier_0_skips_escalation():
    pipeline = ExtractionPipeline()
    agent = StubAgent({0: {"same_entity": True, "confidence": 0.92, "reason": "exact"}})

    fetcher_calls = []

    def fetcher(name: str):
        fetcher_calls.append(name)
        return None

    entities, _ = pipeline._resolve_cross_document(
        _docs(), *_fixture(), agent, wiki_fetcher=fetcher
    )

    assert [tier for _, _, tier in agent.calls] == [0]
    assert fetcher_calls == []
    # The two Person entities collapsed into one cluster (the Time entity stays).
    person_entities = [e for e in entities if e.type == "Person"]
    assert len(person_entities) == 1


def test_low_confidence_escalates_through_tiers():
    pipeline = ExtractionPipeline()
    agent = StubAgent(
        {
            0: {"same_entity": False, "confidence": 0.2, "reason": "not enough"},
            1: {"same_entity": False, "confidence": 0.3, "reason": "still uncertain"},
            2: {"same_entity": True, "confidence": 0.95, "reason": "wiki confirms"},
        }
    )
    fetcher_calls: list[str] = []

    def fetcher(name: str):
        fetcher_calls.append(name)
        return f"Wikipedia summary for {name}"

    entities, _ = pipeline._resolve_cross_document(
        _docs(), *_fixture(), agent, wiki_fetcher=fetcher
    )

    tiers_invoked = [tier for _, _, tier in agent.calls]
    assert tiers_invoked == [0, 1, 2]
    # Wikipedia should be queried once per distinct name.
    assert sorted(fetcher_calls) == ["Maria Skłodowska", "Marie Curie"]
    person_entities = [e for e in entities if e.type == "Person"]
    assert len(person_entities) == 1


def test_wiki_cache_is_per_job_and_per_name():
    """When a name appears in multiple uncertain pairs, tier-2 fetches it once."""
    pipeline = ExtractionPipeline()
    agent = StubAgent(
        {
            0: {"same_entity": False, "confidence": 0.2, "reason": ""},
            1: {"same_entity": False, "confidence": 0.2, "reason": ""},
            2: {"same_entity": False, "confidence": 0.2, "reason": ""},
        }
    )

    fixture_entities, fixture_relations = _fixture()
    extra_marie = Entity(
        id="doc-third:person:marie curie",
        name="Marie Curie",
        type="Person",
        source_doc="doc-third",
        mentions=[Mention(doc_id="doc-third", char_start=0, char_end=11)],
    )
    extra_relation = Relation(
        id="r3",
        subject="doc-third:person:marie curie",
        predicate="born_on",
        object="t1867",
        evidence="1867",
        source_doc="doc-third",
        char_start=24,
        char_end=28,
        confidence=0.9,
    )
    docs = _docs() + [
        {"id": "doc-third", "title": "Marie Curie", "content": "Marie Curie was born in 1867."}
    ]
    entities = fixture_entities + [extra_marie]
    relations = fixture_relations + [extra_relation]

    fetcher_calls: list[str] = []

    def fetcher(name: str):
        fetcher_calls.append(name)
        return f"summary:{name}"

    pipeline._resolve_cross_document(
        docs, entities, relations, agent, wiki_fetcher=fetcher
    )
    # Two "Marie Curie" entities share many keys with Maria — tier 2 still
    # only fetches the canonical name once.
    assert fetcher_calls.count("Marie Curie") == 1


def test_pair_cache_prevents_duplicate_resolution():
    """Each candidate pair is resolved exactly once regardless of how many
    blocking keys it shares (the per-job pair cache keys on frozenset)."""
    pipeline = ExtractionPipeline()
    agent = StubAgent({0: {"same_entity": True, "confidence": 0.9, "reason": "ok"}})

    fixture_entities, fixture_relations = _fixture()
    extra_marie = Entity(
        id="doc-other:person:marie curie",
        name="Marie Curie",
        type="Person",
        source_doc="doc-other",
        mentions=[Mention(doc_id="doc-other", char_start=0, char_end=11)],
    )
    extra_relation = Relation(
        id="r3",
        subject="doc-other:person:marie curie",
        predicate="born_on",
        object="t1867",
        evidence="1867",
        source_doc="doc-other",
        char_start=24,
        char_end=28,
        confidence=0.9,
    )
    entities = fixture_entities + [extra_marie]
    relations = fixture_relations + [extra_relation]
    docs = _docs() + [
        {"id": "doc-other", "title": "Marie Curie", "content": "Marie Curie was born in 1867."}
    ]

    pipeline._resolve_cross_document(
        docs, entities, relations, agent, wiki_fetcher=lambda _n: None
    )

    # No pair should be resolved twice even if it collides on multiple
    # blocking keys.
    pair_keys = {frozenset({a, b}) for a, b, _ in agent.calls}
    assert len(pair_keys) == len(agent.calls)


def test_parallel_llm_produces_same_merges_as_sequential(monkeypatch):
    """USE_PARALLEL_LLM=true must not change which pairs get merged. Drive
    the same fixture twice — once parallel, once sequential — with a
    deterministic stub agent and compare outputs."""
    pipeline = ExtractionPipeline()

    def run(parallel: bool):
        monkeypatch.setenv("USE_PARALLEL_LLM", "true" if parallel else "false")
        agent = StubAgent({0: {"same_entity": True, "confidence": 0.9, "reason": "ok"}})
        entities, relations = _fixture()
        return pipeline._resolve_cross_document(
            _docs(), entities, relations, agent, wiki_fetcher=lambda _n: None
        ), agent.calls

    (par_entities, par_relations), par_calls = run(parallel=True)
    (seq_entities, seq_relations), seq_calls = run(parallel=False)

    par_pair_keys = {frozenset({a, b}) for a, b, _ in par_calls}
    seq_pair_keys = {frozenset({a, b}) for a, b, _ in seq_calls}
    assert par_pair_keys == seq_pair_keys
    assert len([e for e in par_entities if e.type == "Person"]) == len(
        [e for e in seq_entities if e.type == "Person"]
    )


def test_wiki_skipped_when_documents_provide_evidence_already():
    """Tier 1 is enough when full-doc evidence resolves the pair — wiki is not called."""
    pipeline = ExtractionPipeline()
    agent = StubAgent(
        {
            0: {"same_entity": False, "confidence": 0.3, "reason": ""},
            1: {"same_entity": True, "confidence": 0.9, "reason": "doc evidence"},
        }
    )
    fetcher_calls: list[str] = []

    def fetcher(name: str):
        fetcher_calls.append(name)
        return None

    pipeline._resolve_cross_document(
        _docs(), *_fixture(), agent, wiki_fetcher=fetcher
    )
    assert fetcher_calls == []
    tiers_invoked = [tier for _, _, tier in agent.calls]
    assert 2 not in tiers_invoked

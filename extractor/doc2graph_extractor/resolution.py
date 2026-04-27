"""
Entity-resolution helpers: candidate-pair blocking, transitive closure,
and evidence-pack assembly.

This module replaces the single-shot cross-document fusion call with the
standard ER pipeline shape: block (cheap) → pairwise resolve (LLM) →
transitive closure (cheap).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable


def _canonical(name: str) -> str:
    return " ".join((name or "").split()).casefold().strip()


# Tokens that carry no entity-identity signal. Surnames, given names, dates,
# and place names cut through these.
_NAME_TOKEN_STOPWORDS = frozenset(
    {
        "the", "of", "von", "van", "der", "den", "de", "di", "da", "du",
        "la", "le", "el", "al", "and", "with", "for", "to", "from",
        "ibn", "bin", "san", "saint", "st",
    }
)
_TOKEN_SPLIT_RE = re.compile(r"[\s\-/']+")
_YEAR_RE = re.compile(r"\b(\d{4})\b")
_PROPER_NOUN_RE = re.compile(r"\b([A-ZÀ-Þ][A-Za-zÀ-ÿ'\-]{2,})\b")


def _name_tokens(name: str) -> set[str]:
    """Split a name into discriminating tokens (≥3 chars, non-stopword)."""
    tokens: set[str] = set()
    for raw in _TOKEN_SPLIT_RE.split(name or ""):
        token = _canonical(raw)
        if len(token) < 3 or token in _NAME_TOKEN_STOPWORDS or token.isdigit():
            continue
        tokens.add(token)
    return tokens


def _attribute_keys(
    entity: dict,
    relations: Iterable[dict],
    entities_by_id: dict[str, dict],
) -> set[str]:
    """
    Derive blocking keys from an entity's outgoing relations. The point is to
    let "Marie Curie" and "Maria Skłodowska" collide because they share
    `born_on:1867` and `family_of:pierre curie`, regardless of how their
    surface names compare.
    """
    keys: set[str] = set()
    for relation in relations:
        if relation.get("subject") != entity["id"]:
            continue
        predicate = relation.get("predicate", "")
        target = entities_by_id.get(relation.get("object", ""))
        if not target:
            continue
        target_name = target.get("name", "")
        if predicate in ("born_on", "died_on"):
            for year in _YEAR_RE.findall(target_name):
                keys.add(f"{predicate}:{year}")
        elif predicate:
            keys.add(f"{predicate}:{_canonical(target_name)}")
    return keys


def _wikipedia_keys(
    entity: dict,
    wiki_fetcher: Callable[[str], str | None] | None,
) -> set[str]:
    """
    For sparse entities — those with little internal evidence — fetch a
    Wikipedia summary and harvest its proper-noun tokens and years as
    blocking keys. This closes the "name-only stub" case where the
    document carries no other signal: the redirect or first-paragraph
    text on Wikipedia ("Marie Curie, born Maria Salomea Skłodowska...")
    is what ties the entity to a richer biography elsewhere in the corpus.
    """
    if not wiki_fetcher:
        return set()
    summary = wiki_fetcher(entity.get("name", ""))
    if not summary:
        return set()
    keys: set[str] = set()
    for token in _PROPER_NOUN_RE.findall(summary):
        canonical = _canonical(token)
        if len(canonical) >= 3 and canonical not in _NAME_TOKEN_STOPWORDS:
            keys.add(f"name:{canonical}")
    for year in _YEAR_RE.findall(summary):
        keys.add(f"year:{year}")
    return keys


def block_candidate_pairs(
    entities: list[dict],
    relations: list[dict] | None = None,
    *,
    wiki_fetcher: Callable[[str], str | None] | None = None,
    sparse_relation_threshold: int = 2,
    broad_key_threshold: int | None = None,
    rich_pair_relation_threshold: int = 2,
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Multi-signal blocker. A pair of entities (same type) becomes a candidate
    when they share at least one of:

    - an attribute key derived from a relation (e.g., `born_on:1867`,
      `family_of:pierre curie`, `studied_at:sorbonne`), or
    - a name-token key (e.g., `name:curie` for "Marie Curie" vs
      "Marie Skłodowska-Curie"), or
    - a Wikipedia-derived key (year or proper-noun token from the
      official summary), but only for entities with fewer than
      `sparse_relation_threshold` attached relations.

    Char similarity is intentionally NOT used: it both misses true matches
    with different surface forms (Marie Curie / Maria Skłodowska) and
    promotes false positives between unrelated same-named people.

    Returns `(pairs, unresolved_ids)` — `unresolved_ids` lists entities
    that were sparse, lacked any blocking signal, and whose Wikipedia
    lookup also returned nothing. Those merges, if real, can't be made
    from internal data; the caller should surface them.
    """
    relations = relations or []
    entities_by_id = {e["id"]: e for e in entities}

    relations_by_subject: dict[str, list[dict]] = defaultdict(list)
    for relation in relations:
        if relation.get("subject"):
            relations_by_subject[relation["subject"]].append(relation)

    keys_by_entity: dict[str, set[str]] = {}
    for entity in entities:
        eid = entity["id"]
        keys = set()
        keys |= _attribute_keys(entity, relations_by_subject[eid], entities_by_id)
        keys |= {f"name:{tok}" for tok in _name_tokens(entity.get("name", ""))}
        for alias in entity.get("aliases") or []:
            keys |= {f"name:{tok}" for tok in _name_tokens(alias)}
        if len(relations_by_subject[eid]) < sparse_relation_threshold:
            keys |= _wikipedia_keys(entity, wiki_fetcher)
        keys_by_entity[eid] = keys

    # Drop overly common keys to avoid combinatorial blowup. The threshold
    # adapts to corpus size — for tiny corpora (2 docs) the old `max(5, …)`
    # floor was too loose: any common given name like "albert" or shared
    # institution like "cambridge" survived as a blocking key and produced
    # spurious candidate pairs.
    if broad_key_threshold is None:
        broad_key_threshold = max(2, len(entities) // 10)
    key_counts: Counter[str] = Counter()
    for keys in keys_by_entity.values():
        key_counts.update(keys)
    broad_keys = {k for k, c in key_counts.items() if c > broad_key_threshold}

    groups: dict[str, list[str]] = defaultdict(list)
    for eid, keys in keys_by_entity.items():
        for key in keys:
            if key in broad_keys:
                continue
            groups[key].append(eid)

    # Count how many distinct (non-broad) keys each pair shares. Each
    # increment below corresponds to a collision in one group, i.e. one
    # blocking key the two entities have in common.
    pair_share_count: Counter[tuple[str, str]] = Counter()
    for members in groups.values():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if entities_by_id[a].get("type") != entities_by_id[b].get("type"):
                    continue
                if a > b:
                    a, b = b, a
                pair_share_count[(a, b)] += 1

    # When both entities have ≥ rich_pair_relation_threshold attached
    # relations ("rich"), require ≥ 2 shared blocking keys for a candidate.
    # One shared token like a common given name is not enough signal in that
    # case. Either side being sparse falls back to the looser ≥ 1 rule —
    # sparse entities have less structured signal to match on anyway. This
    # threshold is intentionally separate from `sparse_relation_threshold`
    # (which only governs whether to consult Wikipedia at blocking time).
    pair_set: set[tuple[str, str]] = set()
    for (a, b), share_count in pair_share_count.items():
        a_rich = len(relations_by_subject[a]) >= rich_pair_relation_threshold
        b_rich = len(relations_by_subject[b]) >= rich_pair_relation_threshold
        min_required = 2 if (a_rich and b_rich) else 1
        if share_count >= min_required:
            pair_set.add((a, b))

    pairs = sorted(pair_set)

    paired_ids = {eid for pair in pairs for eid in pair}
    # An entity is "unresolved" when it's sparse (little internal evidence)
    # and blocking failed to surface any candidate match for it. The keys
    # it does have were either unique to itself or filtered as too broad.
    unresolved = [
        eid
        for eid in keys_by_entity
        if eid not in paired_ids
        and len(relations_by_subject[eid]) < sparse_relation_threshold
    ]

    return pairs, unresolved


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
            return x
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # Path compression.
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, x: str, y: str) -> None:
        root_x, root_y = self.find(x), self.find(y)
        if root_x != root_y:
            # Pick the lexicographically smaller id as the cluster root for
            # deterministic output.
            if root_x < root_y:
                self.parent[root_y] = root_x
            else:
                self.parent[root_x] = root_y


def transitive_closure(
    confirmed_pairs: Iterable[tuple[str, str]],
) -> dict[str, str]:
    """
    Given pairs of entity ids confirmed to be the same real-world entity,
    return a mapping `entity_id -> cluster_root_id`. Cluster roots are
    chosen as the lexicographically smallest id in each cluster.
    """
    uf = _UnionFind()
    for id_a, id_b in confirmed_pairs:
        uf.union(id_a, id_b)
    return {member: uf.find(member) for member in uf.parent}


# ---------------------------------------------------------------------------
# Evidence pack: the data the old fusion prompt asked Claude to use but
# never actually passed.
# ---------------------------------------------------------------------------

# Predicates whose objects describe what kind of biographical fact this is.
_DATED_PREDICATES = ("born_on", "died_on")
_PLACE_PREDICATES = ("born_in", "died_in", "lived_in")
_AFFILIATION_PREDICATES = ("worked_at", "studied_at", "founded", "member_of")
_FAMILY_PREDICATES = ("family_of", "student_of")
_WORK_PREDICATES = ("authored", "translated", "edited")


@dataclass
class EvidencePack:
    entity_id: str
    name: str
    type: str
    aliases: list[str] = field(default_factory=list)
    source_doc: str = ""
    dated_facts: dict[str, list[str]] = field(default_factory=dict)
    places: dict[str, list[str]] = field(default_factory=dict)
    affiliations: dict[str, list[str]] = field(default_factory=dict)
    family: dict[str, list[str]] = field(default_factory=dict)
    works: dict[str, list[str]] = field(default_factory=dict)
    mention_contexts: list[str] = field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        return {
            "id": self.entity_id,
            "name": self.name,
            "type": self.type,
            "aliases": self.aliases,
            "source_doc": self.source_doc,
            "dated_facts": self.dated_facts,
            "places": self.places,
            "affiliations": self.affiliations,
            "family": self.family,
            "works": self.works,
            "mention_contexts": self.mention_contexts,
        }


def build_evidence_pack(
    entity: dict,
    *,
    entities_by_id: dict[str, dict],
    relations: list[dict],
    documents_by_id: dict[str, dict],
    context_radius: int = 100,
    max_mention_contexts: int = 3,
) -> EvidencePack:
    """
    Assemble structured evidence for one entity from the full graph.

    The pack is the minimum set of facts a human (or LLM) would need to
    decide whether two entities are the same person/place/etc. The fields
    map to predicate categories so the resolver can compare facts directly
    rather than guessing from names.
    """
    pack = EvidencePack(
        entity_id=entity["id"],
        name=entity.get("name", ""),
        type=entity.get("type", ""),
        aliases=list(entity.get("aliases", []) or []),
        source_doc=entity.get("source_doc", ""),
    )

    for relation in relations:
        if relation.get("subject") == entity["id"]:
            other = entities_by_id.get(relation.get("object", ""))
            other_name = (other or {}).get("name") or relation.get("object", "")
            predicate = relation.get("predicate", "")
            target = _bucket_for(predicate, pack)
            if target is not None:
                target.setdefault(predicate, []).append(other_name)
        elif relation.get("object") == entity["id"]:
            other = entities_by_id.get(relation.get("subject", ""))
            other_name = (other or {}).get("name") or relation.get("subject", "")
            predicate = relation.get("predicate", "")
            target = _bucket_for(predicate, pack)
            if target is not None:
                target.setdefault(predicate + "_of", []).append(other_name)

    document = documents_by_id.get(entity.get("source_doc", ""))
    if document:
        content = document.get("content", "") or ""
        contexts: list[str] = []
        seen_spans: set[tuple[int, int]] = set()
        for mention in entity.get("mentions", []) or []:
            cs = max(0, int(mention.get("char_start", 0)) - context_radius)
            ce = min(len(content), int(mention.get("char_end", 0)) + context_radius)
            if (cs, ce) in seen_spans:
                continue
            seen_spans.add((cs, ce))
            window = content[cs:ce].strip()
            if window:
                contexts.append(window)
            if len(contexts) >= max_mention_contexts:
                break
        pack.mention_contexts = contexts

    return pack


_WIKIPEDIA_SUMMARY_URL = (
    "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
)


# Predicates whose object disjointness across two entities is a strong
# "different real-world entity" signal. Singular-by-nature only — `lived_in`
# is multi-valued and `family_of` covers many roles, so disjoint sets there
# don't prove anything.
_INCOMPATIBLE_DATED_PREDICATES = ("born_on", "died_on")
_INCOMPATIBLE_PLACE_PREDICATES = ("born_in", "died_in")


def _outgoing_facts_by_predicate(
    entity_id: str,
    relations: list[dict],
    entities_by_id: dict[str, dict],
) -> dict[str, set[str]]:
    """For a single entity, group outgoing relation objects by predicate
    as a set of canonical object names."""
    facts: dict[str, set[str]] = defaultdict(set)
    for relation in relations:
        if relation.get("subject") != entity_id:
            continue
        target = entities_by_id.get(relation.get("object", ""))
        if not target:
            continue
        predicate = relation.get("predicate", "")
        facts[predicate].add(_canonical(target.get("name", "")))
    return facts


def _years(names: set[str]) -> set[str]:
    out: set[str] = set()
    for name in names:
        out.update(_YEAR_RE.findall(name))
    return out


def is_obviously_incompatible(
    entity_a: dict,
    entity_b: dict,
    relations: list[dict],
    entities_by_id: dict[str, dict],
) -> str | None:
    """
    Return a short reason string if the pair is structurally incompatible
    (so we can drop it without a Claude call), else None.

    Rules are deliberately conservative — they only fire when BOTH sides
    have the same predicate populated and the values cannot reconcile:

      - born_on / died_on: extracted years are disjoint
      - born_in / died_in: canonical place names are disjoint

    Predicates like `lived_in` and `family_of` are noisy (people lived in
    many places; family relations cover many roles) so we don't reject
    on them — those go through the LLM resolver as before.
    """
    facts_a = _outgoing_facts_by_predicate(entity_a["id"], relations, entities_by_id)
    facts_b = _outgoing_facts_by_predicate(entity_b["id"], relations, entities_by_id)

    for predicate in _INCOMPATIBLE_DATED_PREDICATES:
        years_a = _years(facts_a.get(predicate, set()))
        years_b = _years(facts_b.get(predicate, set()))
        if years_a and years_b and years_a.isdisjoint(years_b):
            return f"{predicate} years differ: {sorted(years_a)} vs {sorted(years_b)}"

    for predicate in _INCOMPATIBLE_PLACE_PREDICATES:
        places_a = facts_a.get(predicate, set())
        places_b = facts_b.get(predicate, set())
        if places_a and places_b and places_a.isdisjoint(places_b):
            return f"{predicate} places differ: {sorted(places_a)} vs {sorted(places_b)}"

    return None


def fetch_wikipedia_summary(name: str, *, timeout: float = 5.0) -> str | None:
    """
    Fetch the official summary for `name` from the Wikipedia REST API.
    Returns the extract text, or None if the title can't be resolved or
    the network call fails. Callers should cache results — this function
    intentionally has no internal cache so the cache scope stays with the
    job that owns it.
    """
    if not name:
        return None
    title = urllib.parse.quote(name.replace(" ", "_"))
    url = _WIKIPEDIA_SUMMARY_URL.format(title=title)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "doc2graph-extractor/0.1 (entity-resolution)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None
    extract = payload.get("extract")
    return extract if isinstance(extract, str) else None


def _bucket_for(predicate: str, pack: EvidencePack) -> dict[str, list[str]] | None:
    if predicate in _DATED_PREDICATES:
        return pack.dated_facts
    if predicate in _PLACE_PREDICATES:
        return pack.places
    if predicate in _AFFILIATION_PREDICATES:
        return pack.affiliations
    if predicate in _FAMILY_PREDICATES:
        return pack.family
    if predicate in _WORK_PREDICATES:
        return pack.works
    return None

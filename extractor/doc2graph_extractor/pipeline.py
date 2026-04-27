from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import multiprocessing
import os
import re
import threading

from .models import Entity, ExtractionResult, Mention, Relation
from .resolution import (
    block_candidate_pairs,
    build_evidence_pack,
    fetch_wikipedia_summary,
    is_obviously_incompatible,
    transitive_closure,
)

# Import agents for LLM-based extraction/validation (optional, controlled by env var)
try:
    from .agent import ExtractionAgent, ValidationAgent
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False


_DATE_RANGE_RE = re.compile(r"\(([^()]+?)\s+[–-]\s+([^()]+?)\)")
_BORN_IN_RE = re.compile(r"\bwas born in ([A-Z][A-Za-z' .,-]+?)(?:[.;]|\s+on\s|\s+to\s|\s+and\s)")
_DIED_IN_RE = re.compile(r"\bdied in ([A-Z][A-Za-z' .,-]+?)(?:[.;]|\s+on\s|\s+at\s|\s+after\s)")
_LIVED_IN_RE = re.compile(r"\b(?:lived|resided|settled|moved to|relocated to)\s+in\s+([A-Z][A-Za-z' .,-]+?)(?:[.;,]|\s+where\s|\s+for\s|\s+and\s)")
_WORKED_AT_RE = re.compile(
    r"\b(?:worked|served|taught|researched)\s+(?:at|for)\s+(?:the\s+)?([A-Z][A-Za-z0-9&' .,-]+?)(?:[.;,]|\s+where\s|\s+from\s)"
)
_STUDIED_AT_RE = re.compile(
    r"\b(?:studied|educated|graduated|attended|enrolled)\s+(?:at|from)\s+(?:the\s+)?([A-Z][A-Za-z0-9&' .,-]+?)(?:[.;,]|\s+where\s|\s+in\s)"
)
_FOUNDED_RE = re.compile(
    r"\b(?:founded|established|co-founded|created)\s+(?:the\s+)?([A-Z][A-Za-z0-9&' .,-]+?)(?:[.;,]|\s+in\s|\s+with\s)"
)
_MEMBER_OF_RE = re.compile(
    r"\b(?:member|fellow|associate|part)\s+of\s+(?:the\s+)?([A-Z][A-Za-z0-9&' .,-]+?)(?:[.;,]|\s+and\s|\s+from\s)"
)
_AUTHORED_RE = re.compile(
    r"\b(?:wrote|authored|published|penned)\s+(?:the\s+)?[\"']([^\"']+)[\"']"
)
_TRANSLATED_RE = re.compile(
    r"\b(?:translated)\s+(?:the\s+)?[\"']([^\"']+)[\"']"
)
_EDITED_RE = re.compile(
    r"\b(?:edited)\s+(?:the\s+)?[\"']([^\"']+)[\"']"
)
# NOTE: the inner `(?:\s+[\wÀ-ÿ.-]+)*?` is intentionally non-greedy. With a
# greedy `*`, the engine extends each capture to the LAST valid terminator
# (often end-of-string), swallowing trailing clauses — e.g. "collaborated
# with Albert Einstein on quantum mechanics and won..." captures
# "Albert Einstein on quantum mechanics" instead of "Albert Einstein".
_INFLUENCED_BY_RE = re.compile(
    r"\b(?:influenced|inspired|mentored|guided)\s+by\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*?)(?:\s+(?:and|who|,|;|\.)|$)",
    re.UNICODE
)
_COLLABORATED_WITH_RE = re.compile(
    r"\b(?:collaborated|worked|partnered)\s+(?:together\s+)?with\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*?)(?:\s+(?:on|to|and|,|;|\.)|$)",
    re.UNICODE
)
_FAMILY_OF_RE = re.compile(
    r"\b(?:son|daughter|brother|sister|father|mother|parent|child|spouse|wife|husband)\s+of\s+([A-ZÀ-ÿ][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*?)(?:\s+(?:and|who|was|were|,|;|\.)|$)",
    re.UNICODE
)
_STUDENT_OF_RE = re.compile(
    r"\b(?:student|pupil|apprentice|disciple)\s+of\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*?)(?:\s+(?:and|who|was|were|,|;|\.)|$)",
    re.UNICODE
)
_MARRIED_TO_RE = re.compile(
    r"\bmarried\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*?)(?:\s+(?:in|on|at|and|,|;)|$)",
    re.UNICODE
)
# Additional pattern for "met [Person]" relationships
_MET_PERSON_RE = re.compile(
    r"\bmet\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*?)(?:\s+(?:in|at|and|who|,|;|\.)|$)",
    re.UNICODE
)


# Mirror of the Go-side `relationTypeConstraints` map in
# `backend/internal/domain/validation.go`. Anything outside this map will be
# rejected by the backend's `ValidateExtractionResult`, so we strip those
# relations here rather than letting the whole job fail. The LLM-driven
# `validated` mode can occasionally type a new entity wrong (e.g.,
# "Prussian Academy of Sciences" as Work instead of Organization) and emit
# a relation pointing to it; this filter is the safety net.
_RELATION_TYPE_CONSTRAINTS: dict[str, tuple[str, str]] = {
    "influenced_by": ("Person", "Person"),
    "collaborated_with": ("Person", "Person"),
    "family_of": ("Person", "Person"),
    "student_of": ("Person", "Person"),
    "worked_at": ("Person", "Organization"),
    "studied_at": ("Person", "Organization"),
    "founded": ("Person", "Organization"),
    "member_of": ("Person", "Organization"),
    "born_in": ("Person", "Place"),
    "died_in": ("Person", "Place"),
    "lived_in": ("Person", "Place"),
    "authored": ("Person", "Work"),
    "translated": ("Person", "Work"),
    "edited": ("Person", "Work"),
    "born_on": ("Person", "Time"),
    "died_on": ("Person", "Time"),
}


def _is_relation_type_pair_valid(
    predicate: str, subject_type: str, object_type: str
) -> bool:
    """Return True iff (subject_type, predicate, object_type) is allowed by
    the ontology. Unknown predicates are rejected — the backend will too."""
    constraint = _RELATION_TYPE_CONSTRAINTS.get(predicate)
    if constraint is None:
        return False
    expected_subject, expected_object = constraint
    return subject_type == expected_subject and object_type == expected_object


# Module-level worker functions for multiprocessing
def _worker_extract_document(document: dict) -> tuple[list[dict], list[dict]]:
    """
    Worker function for parallel document extraction.
    Returns tuple of (entity_dicts, relation_dicts).
    """
    pipeline = ExtractionPipeline()
    entities = pipeline._extract_entities(document)
    relations = pipeline._extract_relations(document)
    # Convert to dicts for serialization
    entity_dicts = [asdict(e) for e in entities]
    relation_dicts = [asdict(r) for r in relations]
    return entity_dicts, relation_dicts


class ExtractionPipeline:
    """Entity and relation extraction with multiple modes: regex, validated, or llm."""

    def run(self, documents: list[dict]) -> dict:
        export_documents = [self._build_export_document(document) for document in documents]

        # Determine extraction mode
        # Priority: EXTRACTION_MODE > ENABLE_AGENTIC_LOOP (for backward compatibility)
        raw_mode = os.getenv("EXTRACTION_MODE", "")
        extraction_mode = raw_mode.lower()
        if not extraction_mode:
            # Backward compatibility: map ENABLE_AGENTIC_LOOP to new modes
            if os.getenv("ENABLE_AGENTIC_LOOP", "false").lower() == "true":
                extraction_mode = "validated"
            else:
                extraction_mode = "regex"

        # Validate extraction mode
        if extraction_mode not in ["regex", "validated", "llm"]:
            raise ValueError(
                f"Invalid EXTRACTION_MODE: {extraction_mode}. "
                "Must be one of: validated (default A方案), llm (B方案). "
                "`regex` is deprecated and runs only the candidate stage."
            )

        if raw_mode and extraction_mode == "regex":
            import sys

            print(
                "WARNING: EXTRACTION_MODE=regex is deprecated. The regex pass "
                "is now the candidate stage of `validated` mode; running it "
                "alone ships high-recall noisy output without LLM precision "
                "filtering. Prefer EXTRACTION_MODE=validated.",
                file=sys.stderr,
            )

        if extraction_mode in ["validated", "llm"] and not AGENT_AVAILABLE:
            raise ValueError(
                f"EXTRACTION_MODE={extraction_mode} requires anthropic package. "
                "Install with: pip install anthropic"
            )

        raw_entities: list[Entity] = []
        raw_relations: list[Relation] = []

        if extraction_mode == "llm":
            # Pure LLM extraction - no regex
            agent = ExtractionAgent()
            for document in documents:
                entity_dicts, relation_dicts = agent.extract(document)
                # Convert LLM output to Entity/Relation objects with proper ID mapping
                entities, relations = self._llm_dicts_to_entities_and_relations(
                    document, entity_dicts, relation_dicts
                )
                raw_entities.extend(entities)
                raw_relations.extend(relations)
        else:
            # Regex extraction (used for both "regex" and "validated" modes)
            # Check if parallel processing is enabled
            use_parallel = os.getenv("USE_PARALLEL_EXTRACTION", "false").lower() == "true"
            num_workers = int(os.getenv("EXTRACTION_WORKERS", str(multiprocessing.cpu_count())))

            if use_parallel and len(documents) > 1:
                # Parallel extraction using multiprocessing.Pool
                with multiprocessing.Pool(processes=num_workers) as pool:
                    results = pool.map(_worker_extract_document, documents)

                # Combine results from all workers
                for entity_dicts, relation_dicts in results:
                    # Convert dicts back to Entity/Relation objects
                    for entity_dict in entity_dicts:
                        mentions = [Mention(**m) for m in entity_dict.get("mentions", [])]
                        raw_entities.append(
                            Entity(
                                id=entity_dict["id"],
                                name=entity_dict["name"],
                                type=entity_dict["type"],
                                source_doc=entity_dict["source_doc"],
                                mentions=mentions,
                                aliases=entity_dict.get("aliases", []),
                            )
                        )
                    for relation_dict in relation_dicts:
                        raw_relations.append(
                            Relation(
                                id=relation_dict["id"],
                                subject=relation_dict["subject"],
                                predicate=relation_dict["predicate"],
                                object=relation_dict["object"],
                                evidence=relation_dict["evidence"],
                                source_doc=relation_dict["source_doc"],
                                char_start=relation_dict["char_start"],
                                char_end=relation_dict["char_end"],
                                confidence=relation_dict["confidence"],
                            )
                        )
            else:
                # Sequential extraction (original behavior)
                for document in documents:
                    raw_entities.extend(self._extract_entities(document))
                    raw_relations.extend(self._extract_relations(document))

            # Validation stage - optional Claude-based refinement for "validated" mode
            if extraction_mode == "validated":
                agent = ValidationAgent()

                def _validate_one(document: dict) -> tuple[list[dict], list[dict]]:
                    doc_entities = [e for e in raw_entities if e.source_doc == document["id"]]
                    doc_relations = [r for r in raw_relations if r.source_doc == document["id"]]
                    entity_dicts = [asdict(e) for e in doc_entities]
                    relation_dicts = [asdict(r) for r in doc_relations]
                    return agent.validate(document, entity_dicts, relation_dicts)

                use_parallel_llm = os.getenv("USE_PARALLEL_LLM", "true").lower() == "true"
                if use_parallel_llm and len(documents) > 1:
                    workers = min(
                        len(documents),
                        int(os.getenv("EXTRACTION_LLM_WORKERS", "8")),
                    )
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        # `executor.map` preserves input ordering, which matters
                        # for the existing tests that compare result lists.
                        per_doc_results = list(pool.map(_validate_one, documents))
                else:
                    per_doc_results = [_validate_one(doc) for doc in documents]

                validated_entities: list[Entity] = []
                validated_relations: list[Relation] = []
                for refined_entity_dicts, refined_relation_dicts in per_doc_results:
                    for entity_dict in refined_entity_dicts:
                        mentions = [Mention(**m) for m in entity_dict.get("mentions", [])]
                        validated_entities.append(
                            Entity(
                                id=entity_dict["id"],
                                name=entity_dict["name"],
                                type=entity_dict["type"],
                                source_doc=entity_dict["source_doc"],
                                mentions=mentions,
                                aliases=entity_dict.get("aliases", []),
                            )
                        )
                    for relation_dict in refined_relation_dicts:
                        validated_relations.append(
                            Relation(
                                id=relation_dict["id"],
                                subject=relation_dict["subject"],
                                predicate=relation_dict["predicate"],
                                object=relation_dict["object"],
                                evidence=relation_dict["evidence"],
                                source_doc=relation_dict["source_doc"],
                                char_start=relation_dict["char_start"],
                                char_end=relation_dict["char_end"],
                                confidence=relation_dict["confidence"],
                            )
                        )

                # Replace raw extractions with validated ones
                raw_entities = validated_entities
                raw_relations = validated_relations

                # Cross-document entity resolution: block → resolve_pair → transitive closure.
                raw_entities, raw_relations = self._resolve_cross_document(
                    documents, raw_entities, raw_relations, agent
                )

        entities, relations = self._normalize_graph(raw_entities, raw_relations)
        result = ExtractionResult(documents=export_documents, entities=entities, relations=relations)
        return {
            "documents": result.documents,
            "entities": [asdict(entity) for entity in result.entities],
            "relations": [asdict(relation) for relation in result.relations],
        }

    def _build_export_document(self, document: dict) -> dict:
        return {
            "id": document.get("id", ""),
            "source_type": document.get("source_type", "markdown"),
            "title": document.get("title", ""),
            "uri": document.get("uri", ""),
        }

    def _extract_entities(self, document: dict) -> list[Entity]:
        title = document.get("title", "").strip()
        content = document.get("content", "")
        document_id = document.get("id", "")
        if not title or not content or not document_id:
            return []

        entities: list[Entity] = []
        person_mention = self._find_mention(document_id, content, title)
        entities.append(
            Entity(
                id=f"{document_id}:person:{self._canonical_key('Person', title)}",
                name=title,
                type="Person",
                source_doc=document_id,
                mentions=[person_mention],
            )
        )

        for name, entity_type, char_start, char_end in self._extract_secondary_entity_values(content):
            entities.append(
                Entity(
                    id=f"{document_id}:{entity_type.lower()}:{self._canonical_key(entity_type, name)}",
                    name=name,
                    type=entity_type,
                    source_doc=document_id,
                    mentions=[Mention(doc_id=document_id, char_start=char_start, char_end=char_end)],
                )
            )

        return entities

    def _extract_secondary_entity_values(self, content: str) -> list[tuple[str, str, int, int]]:
        values: list[tuple[str, str, int, int]] = []

        # Time entities — date range: two groups (born year, died year)
        for date_match in _DATE_RANGE_RE.finditer(content):
            born = date_match.group(1).strip()
            died = date_match.group(2).strip()
            if born:
                values.append((born, "Time", date_match.start(1), date_match.end(1)))
            if died:
                values.append((died, "Time", date_match.start(2), date_match.end(2)))

        # Place entities
        for pattern in (_BORN_IN_RE, _DIED_IN_RE, _LIVED_IN_RE):
            for match in pattern.finditer(content):
                place = self._clean_place(match.group(1))
                if place:
                    values.append((place, "Place", match.start(1), match.end(1)))

        # Organization entities
        for pattern in (_WORKED_AT_RE, _STUDIED_AT_RE, _FOUNDED_RE, _MEMBER_OF_RE):
            for match in pattern.finditer(content):
                org = self._clean_org(match.group(1))
                if org:
                    values.append((org, "Organization", match.start(1), match.end(1)))

        # Work entities (titles in quotes)
        for pattern in (_AUTHORED_RE, _TRANSLATED_RE, _EDITED_RE):
            for match in pattern.finditer(content):
                work_title = match.group(1).strip()
                if work_title:
                    values.append((work_title, "Work", match.start(1), match.end(1)))

        # Person entities (for PERSON-PERSON relations)
        for pattern in (
            _INFLUENCED_BY_RE,
            _COLLABORATED_WITH_RE,
            _FAMILY_OF_RE,
            _STUDENT_OF_RE,
            _MARRIED_TO_RE,
            _MET_PERSON_RE,
        ):
            for match in pattern.finditer(content):
                person_name = self._clean_person(match.group(1))
                if person_name:
                    values.append((person_name, "Person", match.start(1), match.end(1)))

        # Deduplicate by (type, canonical_key, span). Different spans of the
        # same entity are kept so that _normalize_graph can collect all mentions.
        deduped: list[tuple[str, str, int, int]] = []
        seen: set[tuple[str, str, int, int]] = set()
        for name, entity_type, start, end in values:
            key = (entity_type, self._canonical_key(entity_type, name), start, end)
            if key in seen or not name:
                continue
            seen.add(key)
            deduped.append((name, entity_type, start, end))

        return deduped

    def _extract_relations(self, document: dict) -> list[Relation]:
        content = document.get("content", "")
        document_id = document.get("id", "")
        title = document.get("title", "").strip()
        if not content or not title or not document_id:
            return []

        person_id = f"{document_id}:person:{self._canonical_key('Person', title)}"
        relations: list[Relation] = []
        relation_counter = 0

        def emit(predicate: str, object_id: str, evidence: str, confidence: float, char_start: int, char_end: int) -> None:
            nonlocal relation_counter
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate=predicate,
                    object_id=object_id,
                    evidence=evidence,
                    source_doc=document_id,
                    content=content,
                    confidence=confidence,
                    char_start=char_start,
                    char_end=char_end,
                )
            )
            relation_counter += 1

        # PERSON-TIME relations
        for date_match in _DATE_RANGE_RE.finditer(content):
            born = date_match.group(1).strip()
            died = date_match.group(2).strip()
            if born:
                emit(
                    "born_on",
                    f"{document_id}:time:{self._canonical_key('Time', born)}",
                    born,
                    0.88,
                    date_match.start(1),
                    date_match.end(1),
                )
            if died:
                emit(
                    "died_on",
                    f"{document_id}:time:{self._canonical_key('Time', died)}",
                    died,
                    0.88,
                    date_match.start(2),
                    date_match.end(2),
                )

        # Person → Place patterns
        place_patterns = (
            (_BORN_IN_RE, "born_in", 0.82),
            (_DIED_IN_RE, "died_in", 0.79),
            (_LIVED_IN_RE, "lived_in", 0.75),
        )
        for pattern, predicate, confidence in place_patterns:
            for match in pattern.finditer(content):
                place = self._clean_place(match.group(1))
                if not place:
                    continue
                emit(
                    predicate,
                    f"{document_id}:place:{self._canonical_key('Place', place)}",
                    place,
                    confidence,
                    match.start(1),
                    match.end(1),
                )

        # Person → Organization patterns
        org_patterns = (
            (_WORKED_AT_RE, "worked_at", 0.72),
            (_STUDIED_AT_RE, "studied_at", 0.78),
            (_FOUNDED_RE, "founded", 0.85),
            (_MEMBER_OF_RE, "member_of", 0.76),
        )
        for pattern, predicate, confidence in org_patterns:
            for match in pattern.finditer(content):
                org = self._clean_org(match.group(1))
                if not org:
                    continue
                emit(
                    predicate,
                    f"{document_id}:organization:{self._canonical_key('Organization', org)}",
                    org,
                    confidence,
                    match.start(1),
                    match.end(1),
                )

        # Person → Work patterns
        work_patterns = (
            (_AUTHORED_RE, "authored", 0.83),
            (_TRANSLATED_RE, "translated", 0.80),
            (_EDITED_RE, "edited", 0.77),
        )
        for pattern, predicate, confidence in work_patterns:
            for match in pattern.finditer(content):
                work_title = match.group(1).strip()
                if not work_title:
                    continue
                emit(
                    predicate,
                    f"{document_id}:work:{self._canonical_key('Work', work_title)}",
                    work_title,
                    confidence,
                    match.start(1),
                    match.end(1),
                )

        # Person → Person patterns. _MARRIED_TO_RE is mapped to family_of and
        # _MET_PERSON_RE to collaborated_with to align with the ontology.
        person_patterns = (
            (_INFLUENCED_BY_RE, "influenced_by", 0.70),
            (_COLLABORATED_WITH_RE, "collaborated_with", 0.74),
            (_FAMILY_OF_RE, "family_of", 0.81),
            (_STUDENT_OF_RE, "student_of", 0.79),
            (_MARRIED_TO_RE, "family_of", 0.85),
            (_MET_PERSON_RE, "collaborated_with", 0.65),
        )
        for pattern, predicate, confidence in person_patterns:
            for match in pattern.finditer(content):
                person_name = self._clean_person(match.group(1))
                if not person_name:
                    continue
                object_id = f"{document_id}:person:{self._canonical_key('Person', person_name)}"
                if object_id == person_id:
                    continue
                emit(
                    predicate,
                    object_id,
                    person_name,
                    confidence,
                    match.start(1),
                    match.end(1),
                )

        return relations

    def _resolve_cross_document(
        self,
        documents: list[dict],
        entities: list[Entity],
        relations: list[Relation],
        agent,
        wiki_fetcher=None,
    ) -> tuple[list[Entity], list[Relation]]:
        """
        Run the entity-resolution pipeline:

        1. Block candidate pairs cheaply by name similarity within type.
        2. For each surviving pair, build evidence packs and ask the LLM
           (`agent.resolve_pair`). If confidence is low, escalate by
           expanding evidence — Tier 1 attaches the full source documents,
           Tier 2 attaches Wikipedia summaries.
        3. Apply transitive closure: if {A,B} and {B,C} are merged, fold C
           into A's cluster.
        4. Apply merges via the existing `_apply_fusion_merges` utility.
        5. Re-validate post-merge relation buckets where multiple relations
           collapsed onto the same (subject, predicate, object) shape.
        """
        import sys

        if len(entities) < 2:
            return entities, relations

        confidence_threshold = float(
            os.getenv("FUSION_CONFIDENCE_THRESHOLD", "0.5")
        )
        sparse_threshold = int(os.getenv("FUSION_SPARSE_THRESHOLD", "2"))
        if wiki_fetcher is None:
            wiki_fetcher = fetch_wikipedia_summary

        entity_dicts = [asdict(e) for e in entities]
        relation_dicts = [asdict(r) for r in relations]
        entities_by_id = {e["id"]: e for e in entity_dicts}
        documents_by_id = {d.get("id", ""): d for d in documents}

        # Per-job caches: same (A,B) pair never resolved twice; each
        # canonical name fetched from Wikipedia at most once. The wiki
        # cache is shared between blocking-time enrichment and tier-2
        # disambiguation so a name is at most one network round trip.
        # Both are accessed concurrently when USE_PARALLEL_LLM is on.
        pair_cache: dict[frozenset[str], dict] = {}
        wiki_cache: dict[str, str | None] = {}
        wiki_lock = threading.Lock()

        def get_wiki(name: str) -> str | None:
            if not name:
                return None
            with wiki_lock:
                if name in wiki_cache:
                    return wiki_cache[name]
                # Mark as in-flight by inserting None first to avoid duplicate
                # fetches under concurrent access; replaced after the fetch.
            summary = wiki_fetcher(name)
            with wiki_lock:
                wiki_cache[name] = summary
            return summary

        candidate_pairs, unresolved = block_candidate_pairs(
            entity_dicts,
            relation_dicts,
            wiki_fetcher=get_wiki,
            sparse_relation_threshold=sparse_threshold,
        )
        print(
            f"\nEntity resolution: {len(candidate_pairs)} candidate pair(s) "
            "from multi-signal blocking (attribute + name-token + wiki)",
            file=sys.stderr,
        )
        if unresolved:
            print(
                f"  {len(unresolved)} sparse entit{'y' if len(unresolved) == 1 else 'ies'} "
                "had no resolution signal — left unmerged: "
                f"{unresolved[:10]}{'...' if len(unresolved) > 10 else ''}",
                file=sys.stderr,
            )

        # Pre-resolve filter: drop pairs whose structured evidence already
        # rules out a merge (different born_on years, different born_in
        # places, etc.). Pure Python — saves the Claude round-trip per pair.
        accepted_pairs: list[tuple[str, str]] = []
        pre_dropped = 0
        for id_a, id_b in candidate_pairs:
            entity_a = entities_by_id.get(id_a)
            entity_b = entities_by_id.get(id_b)
            if not entity_a or not entity_b:
                continue
            reason = is_obviously_incompatible(
                entity_a, entity_b, relation_dicts, entities_by_id
            )
            if reason:
                pre_dropped += 1
                continue
            accepted_pairs.append((id_a, id_b))

        if pre_dropped:
            print(
                f"  pre-resolve filter dropped {pre_dropped} obviously-"
                f"incompatible pair(s) without an LLM call",
                file=sys.stderr,
            )
        candidate_pairs = accepted_pairs

        def _resolve_one(pair: tuple[str, str]) -> tuple[str, str, dict] | None:
            id_a, id_b = pair
            entity_a = entities_by_id.get(id_a)
            entity_b = entities_by_id.get(id_b)
            if not entity_a or not entity_b:
                return None
            pack_a = build_evidence_pack(
                entity_a,
                entities_by_id=entities_by_id,
                relations=relation_dicts,
                documents_by_id=documents_by_id,
            ).to_prompt_dict()
            pack_b = build_evidence_pack(
                entity_b,
                entities_by_id=entities_by_id,
                relations=relation_dicts,
                documents_by_id=documents_by_id,
            ).to_prompt_dict()
            decision = self._resolve_pair_with_escalation(
                agent,
                pack_a,
                pack_b,
                entity_a,
                entity_b,
                documents_by_id,
                confidence_threshold,
                get_wiki,
            )
            pair_cache[frozenset({id_a, id_b})] = decision
            return id_a, id_b, decision

        use_parallel_llm = os.getenv("USE_PARALLEL_LLM", "true").lower() == "true"
        results: list[tuple[str, str, dict]] = []
        if use_parallel_llm and len(candidate_pairs) > 1:
            workers = min(
                len(candidate_pairs),
                int(os.getenv("EXTRACTION_LLM_WORKERS", "8")),
            )
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for outcome in pool.map(_resolve_one, candidate_pairs):
                    if outcome is not None:
                        results.append(outcome)
        else:
            for pair in candidate_pairs:
                outcome = _resolve_one(pair)
                if outcome is not None:
                    results.append(outcome)

        confirmed_pairs: list[tuple[str, str]] = []
        for id_a, id_b, decision in results:
            if decision.get("same_entity") and decision.get("confidence", 0.0) >= confidence_threshold:
                confirmed_pairs.append((id_a, id_b))
                print(
                    f"  ✓ merge ({id_a} ↔ {id_b}) "
                    f"confidence={decision['confidence']:.2f} "
                    f"tier={decision.get('tier', 0)} "
                    f"reason={decision.get('reason', '')!r}",
                    file=sys.stderr,
                )

        if not confirmed_pairs:
            print("  no cross-document merges confirmed", file=sys.stderr)
            return entities, relations

        clusters = transitive_closure(confirmed_pairs)
        fusion_merges: list[tuple[str, str, list[str]]] = []
        for source_id, root_id in clusters.items():
            if source_id == root_id:
                continue
            fusion_merges.append((source_id, root_id, []))

        if not fusion_merges:
            return entities, relations

        merged_entities, merged_relations = self._apply_fusion_merges(
            entities, relations, fusion_merges
        )
        print(
            f"  applied {len(fusion_merges)} merges across {len({r for _, r, _ in fusion_merges})} cluster(s)",
            file=sys.stderr,
        )

        merged_entities, merged_relations = self._review_post_merge_relations(
            merged_entities, merged_relations, agent
        )

        return merged_entities, merged_relations

    def _resolve_pair_with_escalation(
        self,
        agent,
        pack_a: dict,
        pack_b: dict,
        entity_a: dict,
        entity_b: dict,
        documents_by_id: dict[str, dict],
        confidence_threshold: float,
        get_wiki,
    ) -> dict:
        """
        Three-tier resolution: basic pack → +full source docs → +Wikipedia.
        Tiers 1 and 2 only fire if the previous tier returned a confidence
        below `confidence_threshold` — the document evidence we already have
        is consulted before reaching for the network.
        """
        import sys

        def call_agent(pack_a_local: dict, pack_b_local: dict, tier: int) -> dict:
            try:
                decision = agent.resolve_pair(pack_a_local, pack_b_local)
            except Exception as exc:
                print(
                    f"  resolve_pair tier {tier} failed for ({entity_a['id']}, {entity_b['id']}): {exc}",
                    file=sys.stderr,
                )
                return {"same_entity": False, "confidence": 0.0, "reason": str(exc), "tier": tier}
            decision["tier"] = tier
            return decision

        decision = call_agent(pack_a, pack_b, tier=0)
        if decision.get("confidence", 0.0) >= confidence_threshold:
            return decision

        # Tier 1 — re-resolve with the entire source document attached.
        doc_a = documents_by_id.get(entity_a.get("source_doc", ""), {}).get("content", "")
        doc_b = documents_by_id.get(entity_b.get("source_doc", ""), {}).get("content", "")
        if doc_a or doc_b:
            expanded_a = {**pack_a, "full_document_text": doc_a}
            expanded_b = {**pack_b, "full_document_text": doc_b}
            decision = call_agent(expanded_a, expanded_b, tier=1)
            if decision.get("confidence", 0.0) >= confidence_threshold:
                return decision
            pack_a, pack_b = expanded_a, expanded_b

        # Tier 2 — last resort: Wikipedia summaries for each name.
        wiki_a = get_wiki(entity_a.get("name", ""))
        wiki_b = get_wiki(entity_b.get("name", ""))
        if wiki_a or wiki_b:
            wiki_pack_a = {**pack_a, "wikipedia_summary": wiki_a or ""}
            wiki_pack_b = {**pack_b, "wikipedia_summary": wiki_b or ""}
            decision = call_agent(wiki_pack_a, wiki_pack_b, tier=2)

        return decision

    def _review_post_merge_relations(
        self,
        entities: list[Entity],
        relations: list[Relation],
        agent,
    ) -> tuple[list[Entity], list[Relation]]:
        """
        After fusion, group relations by (subject, predicate, object) and ask
        the agent to drop redundant duplicates whose evidence overlaps. This
        catches cases where regex extracted equivalent facts about the same
        person from two different biographies.
        """
        import sys
        from collections import defaultdict

        if not relations:
            return entities, relations

        entity_name_by_id = {e.id: e.name for e in entities}
        buckets: dict[tuple[str, str, str], list[Relation]] = defaultdict(list)
        for relation in relations:
            buckets[(relation.subject, relation.predicate, relation.object)].append(relation)

        drop_ids: set[str] = set()
        for (subject_id, predicate, object_id), bucket in buckets.items():
            if len(bucket) < 2:
                continue
            relation_dicts = [asdict(r) for r in bucket]
            try:
                decisions = agent.review_merged_relations(
                    entity_name_by_id.get(subject_id, subject_id),
                    predicate,
                    entity_name_by_id.get(object_id, object_id),
                    relation_dicts,
                )
            except Exception as exc:
                print(f"  review_merged_relations failed: {exc}", file=sys.stderr)
                continue
            for relation_id, action in decisions.items():
                if action == "drop":
                    drop_ids.add(relation_id)

        if not drop_ids:
            return entities, relations

        kept = [r for r in relations if r.id not in drop_ids]
        print(
            f"  post-merge review dropped {len(drop_ids)} redundant relation(s)",
            file=sys.stderr,
        )
        return entities, kept

    def _apply_fusion_merges(
        self,
        entities: list[Entity],
        relations: list[Relation],
        fusion_merges: list[tuple[str, str, list[str]]],
    ) -> tuple[list[Entity], list[Relation]]:
        """
        Apply cross-document entity fusion merges.

        Args:
            entities: List of entities
            relations: List of relations
            fusion_merges: List of (source_id, target_id, aliases) tuples

        Returns:
            Tuple of (merged_entities, updated_relations)
        """
        # Build merge map: source_id -> target_id
        merge_map = {source_id: target_id for source_id, target_id, _ in fusion_merges}

        # Build entity lookup for efficient access
        entity_by_id = {e.id: e for e in entities}

        # Update target entities with accumulated aliases
        for source_id, target_id, aliases in fusion_merges:
            if target_id in entity_by_id:
                target_entity = entity_by_id[target_id]
                # Add the source entity's name to the target's aliases
                if source_id in entity_by_id:
                    source_name = entity_by_id[source_id].name
                    # Add source name as alias if it's different from target name
                    if source_name.lower() != target_entity.name.lower():
                        if source_name not in target_entity.aliases:
                            target_entity.aliases.append(source_name)
                    # Also add any existing aliases from source entity
                    if source_id in entity_by_id:
                        for alias in entity_by_id[source_id].aliases:
                            if alias not in target_entity.aliases and alias.lower() != target_entity.name.lower():
                                target_entity.aliases.append(alias)
                # Add additional aliases from fusion
                for alias in aliases:
                    if alias not in target_entity.aliases and alias.lower() != target_entity.name.lower():
                        target_entity.aliases.append(alias)

        # Remove merged entities (keep only targets)
        merged_entities = [e for e in entities if e.id not in merge_map]

        # Update relations to use target entity IDs
        updated_relations = []
        seen_relations = set()  # Track (subject, predicate, object) to deduplicate

        for relation in relations:
            # Apply merge map to subject and object
            subject_id = merge_map.get(relation.subject, relation.subject)
            object_id = merge_map.get(relation.object, relation.object)

            # Deduplicate relations
            relation_key = (subject_id, relation.predicate, object_id)
            if relation_key in seen_relations:
                continue
            seen_relations.add(relation_key)

            # Create updated relation
            updated_relation = Relation(
                id=relation.id,
                subject=subject_id,
                predicate=relation.predicate,
                object=object_id,
                evidence=relation.evidence,
                source_doc=relation.source_doc,
                char_start=relation.char_start,
                char_end=relation.char_end,
                confidence=relation.confidence,
            )
            updated_relations.append(updated_relation)

        return merged_entities, updated_relations

    def _llm_dicts_to_entities_and_relations(
        self,
        document: dict,
        entity_dicts: list[dict],
        relation_dicts: list[dict]
    ) -> tuple[list[Entity], list[Relation]]:
        """
        Convert LLM extraction output to Entity and Relation objects.

        This combined method ensures that relation subject/object IDs properly
        reference the actual entity IDs created from the entity_dicts.
        """
        # Step 1: Create entities and build name->ID mapping
        entities = []
        name_to_entity_id: dict[tuple[str, str], str] = {}  # (name, type) -> entity_id

        for idx, entity_dict in enumerate(entity_dicts):
            entity_id = f"{document['id']}:{entity_dict['type'].lower()}:{idx}"
            entity_name = entity_dict["name"]
            entity_type = entity_dict["type"]

            # Find the entity name in the document to get char offsets
            # For now, we create a single mention spanning the whole document
            # (LLM doesn't provide precise char offsets for entity mentions)
            mention = Mention(
                doc_id=document["id"],
                char_start=0,
                char_end=len(document.get("content", ""))
            )

            entity = Entity(
                id=entity_id,
                name=entity_name,
                type=entity_type,
                source_doc=document["id"],
                mentions=[mention],
                aliases=entity_dict.get("aliases", []),
            )
            entities.append(entity)

            # Map entity name to ID for relation linking
            name_to_entity_id[(entity_name, entity_type)] = entity_id

            # Also map aliases to the same ID
            for alias in entity_dict.get("aliases", []):
                name_to_entity_id[(alias, entity_type)] = entity_id

        # Step 2: Create relations using the name->ID mapping
        relations = []
        for idx, relation_dict in enumerate(relation_dicts):
            relation_id = f"{document['id']}:relation:{idx}"

            # Look up subject and object entity IDs
            subject_key = (relation_dict["subject"], relation_dict["subject_type"])
            object_key = (relation_dict["object"], relation_dict["object_type"])

            subject_id = name_to_entity_id.get(subject_key)
            object_id = name_to_entity_id.get(object_key)

            if not subject_id or not object_id:
                # Skip relations where we can't find the referenced entities
                import sys
                print(f"WARNING: Skipping relation {relation_id}: subject or object entity not found", file=sys.stderr)
                print(f"  Subject: {subject_key} -> {subject_id}", file=sys.stderr)
                print(f"  Object: {object_key} -> {object_id}", file=sys.stderr)
                continue

            relation = Relation(
                id=relation_id,
                subject=subject_id,
                predicate=relation_dict["predicate"],
                object=object_id,
                evidence=relation_dict.get("evidence", ""),
                source_doc=document["id"],
                char_start=relation_dict.get("char_start", 0),
                char_end=relation_dict.get("char_end", len(document.get("content", ""))),
                confidence=relation_dict.get("confidence", 0.5),
            )
            relations.append(relation)

        return entities, relations

    def _normalize_graph(
        self, entities: list[Entity], relations: list[Relation]
    ) -> tuple[list[Entity], list[Relation]]:
        canonical_to_entity_id: dict[tuple[str, str], str] = {}
        normalized_entities: list[Entity] = []
        mentions_by_entity: dict[str, dict[tuple[str, int, int], Mention]] = defaultdict(dict)
        aliases_by_entity: dict[str, set[str]] = defaultdict(set)
        raw_to_normalized: dict[str, str] = {}

        for entity in entities:
            key = (entity.type, self._canonical_key(entity.type, entity.name))
            normalized_id = canonical_to_entity_id.get(key)
            if normalized_id is None:
                prefix = self._entity_prefix(entity.type)
                normalized_id = f"{prefix}{len(normalized_entities) + 1}"
                canonical_to_entity_id[key] = normalized_id
                normalized_entities.append(
                    Entity(
                        id=normalized_id,
                        name=entity.name,
                        type=entity.type,
                        source_doc=entity.source_doc,
                        mentions=[],
                        aliases=[],
                    )
                )

            raw_to_normalized[entity.id] = normalized_id
            bucket = self._find_entity(normalized_entities, normalized_id)
            aliases_by_entity[normalized_id].add(entity.name)
            for alias in entity.aliases:
                aliases_by_entity[normalized_id].add(alias)
            for mention in entity.mentions:
                mentions_by_entity[normalized_id][
                    (mention.doc_id, mention.char_start, mention.char_end)
                ] = mention
            if entity.source_doc < bucket.source_doc:
                bucket.source_doc = entity.source_doc

        for entity in normalized_entities:
            entity.mentions = sorted(
                mentions_by_entity[entity.id].values(),
                key=lambda item: (item.doc_id, item.char_start, item.char_end),
            )
            entity.aliases = sorted(
                alias
                for alias in aliases_by_entity[entity.id]
                if self._canonical_text(alias) != self._canonical_text(entity.name)
            )

        type_by_id = {entity.id: entity.type for entity in normalized_entities}

        relation_keys: set[tuple[str, str, str, str, int, int]] = set()
        normalized_relations: list[Relation] = []
        dropped_invalid = 0
        for relation in relations:
            subject = raw_to_normalized.get(relation.subject)
            object_id = raw_to_normalized.get(relation.object)
            if not subject or not object_id:
                continue

            subject_type = type_by_id.get(subject, "")
            object_type = type_by_id.get(object_id, "")
            if not _is_relation_type_pair_valid(
                relation.predicate, subject_type, object_type
            ):
                dropped_invalid += 1
                continue

            key = (
                subject,
                relation.predicate,
                object_id,
                relation.source_doc,
                relation.char_start,
                relation.char_end,
            )
            if key in relation_keys:
                continue
            relation_keys.add(key)

            normalized_relations.append(
                Relation(
                    id=f"R{len(normalized_relations) + 1}",
                    subject=subject,
                    predicate=relation.predicate,
                    object=object_id,
                    evidence=relation.evidence,
                    source_doc=relation.source_doc,
                    char_start=relation.char_start,
                    char_end=relation.char_end,
                    confidence=relation.confidence,
                )
            )

        if dropped_invalid:
            import sys

            print(
                f"WARNING: dropped {dropped_invalid} relation(s) with invalid "
                "type-pair against the ontology (likely LLM-typed an entity wrong).",
                file=sys.stderr,
            )

        normalized_entities.sort(key=lambda item: (self._entity_type_rank(item.type), item.name.casefold(), item.id))
        normalized_relations.sort(
            key=lambda item: (item.subject, item.predicate, item.object, item.source_doc, item.char_start)
        )
        return normalized_entities, normalized_relations

    def _build_relation(
        self,
        relation_id: str,
        subject: str,
        predicate: str,
        object_id: str,
        evidence: str,
        source_doc: str,
        content: str,
        confidence: float,
        char_start: int | None = None,
        char_end: int | None = None,
    ) -> Relation:
        if char_start is None or char_end is None:
            mention = self._find_mention(source_doc, content, evidence)
            char_start, char_end = mention.char_start, mention.char_end
        return Relation(
            id=relation_id,
            subject=subject,
            predicate=predicate,
            object=object_id,
            evidence=evidence,
            source_doc=source_doc,
            char_start=char_start,
            char_end=char_end,
            confidence=confidence,
        )

    def _find_mention(self, doc_id: str, content: str, value: str) -> Mention:
        start = content.find(value)
        if start < 0:
            start = 0
        return Mention(doc_id=doc_id, char_start=start, char_end=start + len(value))

    def _canonical_key(self, entity_type: str, value: str) -> str:
        normalized = self._canonical_text(value)
        if entity_type == "Time":
            normalized = normalized.replace(",", "")
        return normalized

    def _canonical_text(self, value: str) -> str:
        return " ".join(value.split()).casefold().strip()

    def _clean_place(self, value: str) -> str:
        return value.strip(" .,;")

    def _clean_org(self, value: str) -> str:
        return value.strip(" .,;")

    def _clean_person(self, value: str) -> str:
        return value.strip(" .,;")

    def _find_entity(self, entities: list[Entity], entity_id: str) -> Entity:
        for entity in entities:
            if entity.id == entity_id:
                return entity
        raise KeyError(entity_id)

    def _entity_prefix(self, entity_type: str) -> str:
        return {
            "Person": "P",
            "Organization": "O",
            "Place": "L",
            "Work": "W",
            "Time": "T",
        }.get(entity_type, "E")

    def _entity_type_rank(self, entity_type: str) -> int:
        return {
            "Person": 0,
            "Organization": 1,
            "Place": 2,
            "Work": 3,
            "Time": 4,
        }.get(entity_type, 99)

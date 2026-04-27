from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import multiprocessing
import os
import re

from .models import Entity, ExtractionResult, Mention, Relation

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
_INFLUENCED_BY_RE = re.compile(
    r"\b(?:influenced|inspired|mentored|guided)\s+by\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*)(?:\s+(?:and|who|,|;|\.)|$)",
    re.UNICODE
)
_COLLABORATED_WITH_RE = re.compile(
    r"\b(?:collaborated|worked|partnered)\s+(?:together\s+)?with\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*)(?:\s+(?:on|to|and|,|;|\.)|$)",
    re.UNICODE
)
_FAMILY_OF_RE = re.compile(
    r"\b(?:son|daughter|brother|sister|father|mother|parent|child|spouse|wife|husband)\s+of\s+([A-ZÀ-ÿ][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*)(?:\s+(?:and|who|was|were|,|;|\.)|$)",
    re.UNICODE
)
_STUDENT_OF_RE = re.compile(
    r"\b(?:student|pupil|apprentice|disciple)\s+of\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*)(?:\s+(?:and|who|was|were|,|;|\.)|$)",
    re.UNICODE
)
_MARRIED_TO_RE = re.compile(
    r"\bmarried\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*)(?:\s+(?:in|on|at|and|,|;)|$)",
    re.UNICODE
)
# Additional pattern for "met [Person]" relationships
_MET_PERSON_RE = re.compile(
    r"\bmet\s+([A-Z][\wÀ-ÿ.-]+(?:\s+[\wÀ-ÿ.-]+)*)(?:\s+(?:in|at|and|who|,|;|\.)|$)",
    re.UNICODE
)


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
        extraction_mode = os.getenv("EXTRACTION_MODE", "").lower()
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
                "Must be one of: regex, validated, llm"
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
                validated_entities: list[Entity] = []
                validated_relations: list[Relation] = []

                for document in documents:
                    # Get entities and relations for this document
                    doc_entities = [e for e in raw_entities if e.source_doc == document["id"]]
                    doc_relations = [r for r in raw_relations if r.source_doc == document["id"]]

                    # Convert dataclasses to dicts for validation
                    entity_dicts = [asdict(e) for e in doc_entities]
                    relation_dicts = [asdict(r) for r in doc_relations]

                    # Call Claude for validation
                    refined_entity_dicts, refined_relation_dicts = agent.validate(
                        document, entity_dicts, relation_dicts
                    )

                    # Convert validated dicts back to dataclasses
                    for entity_dict in refined_entity_dicts:
                        # Reconstruct mentions from dicts
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

                # Cross-document fusion - merge duplicate entities across documents
                import sys
                print(f"\nPerforming cross-document entity fusion on {len(raw_entities)} entities...", file=sys.stderr)
                entity_dicts = [asdict(e) for e in raw_entities]
                fusion_merges = agent.cross_document_fusion(entity_dicts)

                # Apply fusion merges
                if fusion_merges:
                    raw_entities, raw_relations = self._apply_fusion_merges(
                        raw_entities, raw_relations, fusion_merges
                    )
                    print(f"Fusion complete: {len(fusion_merges)} entity merges applied", file=sys.stderr)
                else:
                    print("No cross-document duplicates detected", file=sys.stderr)

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

        for name, entity_type in self._extract_secondary_entity_values(content):
            mention = self._find_mention(document_id, content, name)
            entities.append(
                Entity(
                    id=f"{document_id}:{entity_type.lower()}:{self._canonical_key(entity_type, name)}",
                    name=name,
                    type=entity_type,
                    source_doc=document_id,
                    mentions=[mention],
                )
            )

        return entities

    def _extract_secondary_entity_values(self, content: str) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = []

        # Extract Time entities
        date_match = _DATE_RANGE_RE.search(content)
        if date_match:
            values.append((date_match.group(1).strip(), "Time"))
            values.append((date_match.group(2).strip(), "Time"))

        # Extract Place entities
        for pattern in (_BORN_IN_RE, _DIED_IN_RE, _LIVED_IN_RE):
            match = pattern.search(content)
            if match:
                values.append((self._clean_place(match.group(1)), "Place"))

        # Extract Organization entities
        for pattern in (_WORKED_AT_RE, _STUDIED_AT_RE, _FOUNDED_RE, _MEMBER_OF_RE):
            match = pattern.search(content)
            if match:
                values.append((self._clean_org(match.group(1)), "Organization"))

        # Extract Work entities
        for pattern in (_AUTHORED_RE, _TRANSLATED_RE, _EDITED_RE):
            match = pattern.search(content)
            if match:
                work_title = match.group(1).strip()
                if work_title:
                    values.append((work_title, "Work"))

        # Extract Person entities (for PERSON-PERSON relations)
        for pattern in (_INFLUENCED_BY_RE, _COLLABORATED_WITH_RE, _FAMILY_OF_RE, _STUDENT_OF_RE, _MARRIED_TO_RE, _MET_PERSON_RE):
            match = pattern.search(content)
            if match:
                person_name = self._clean_person(match.group(1))
                if person_name:
                    values.append((person_name, "Person"))

        deduped: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for name, entity_type in values:
            key = (entity_type, self._canonical_key(entity_type, name))
            if key in seen or not name:
                continue
            seen.add(key)
            deduped.append((name, entity_type))

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

        # PERSON-TIME relations
        date_match = _DATE_RANGE_RE.search(content)
        if date_match:
            born = date_match.group(1).strip()
            died = date_match.group(2).strip()
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="born_on",
                    object_id=f"{document_id}:time:{self._canonical_key('Time', born)}",
                    evidence=born,
                    source_doc=document_id,
                    content=content,
                    confidence=0.88,
                )
            )
            relation_counter += 1
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="died_on",
                    object_id=f"{document_id}:time:{self._canonical_key('Time', died)}",
                    evidence=died,
                    source_doc=document_id,
                    content=content,
                    confidence=0.88,
                )
            )
            relation_counter += 1

        # PERSON-PLACE relations
        born_in_match = _BORN_IN_RE.search(content)
        if born_in_match:
            place = self._clean_place(born_in_match.group(1))
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="born_in",
                    object_id=f"{document_id}:place:{self._canonical_key('Place', place)}",
                    evidence=place,
                    source_doc=document_id,
                    content=content,
                    confidence=0.82,
                )
            )
            relation_counter += 1

        died_in_match = _DIED_IN_RE.search(content)
        if died_in_match:
            place = self._clean_place(died_in_match.group(1))
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="died_in",
                    object_id=f"{document_id}:place:{self._canonical_key('Place', place)}",
                    evidence=place,
                    source_doc=document_id,
                    content=content,
                    confidence=0.79,
                )
            )
            relation_counter += 1

        lived_in_match = _LIVED_IN_RE.search(content)
        if lived_in_match:
            place = self._clean_place(lived_in_match.group(1))
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="lived_in",
                    object_id=f"{document_id}:place:{self._canonical_key('Place', place)}",
                    evidence=place,
                    source_doc=document_id,
                    content=content,
                    confidence=0.75,
                )
            )
            relation_counter += 1

        # PERSON-ORG relations
        worked_at_match = _WORKED_AT_RE.search(content)
        if worked_at_match:
            org = self._clean_org(worked_at_match.group(1))
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="worked_at",
                    object_id=f"{document_id}:organization:{self._canonical_key('Organization', org)}",
                    evidence=org,
                    source_doc=document_id,
                    content=content,
                    confidence=0.72,
                )
            )
            relation_counter += 1

        studied_at_match = _STUDIED_AT_RE.search(content)
        if studied_at_match:
            org = self._clean_org(studied_at_match.group(1))
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="studied_at",
                    object_id=f"{document_id}:organization:{self._canonical_key('Organization', org)}",
                    evidence=org,
                    source_doc=document_id,
                    content=content,
                    confidence=0.78,
                )
            )
            relation_counter += 1

        founded_match = _FOUNDED_RE.search(content)
        if founded_match:
            org = self._clean_org(founded_match.group(1))
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="founded",
                    object_id=f"{document_id}:organization:{self._canonical_key('Organization', org)}",
                    evidence=org,
                    source_doc=document_id,
                    content=content,
                    confidence=0.85,
                )
            )
            relation_counter += 1

        member_of_match = _MEMBER_OF_RE.search(content)
        if member_of_match:
            org = self._clean_org(member_of_match.group(1))
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="member_of",
                    object_id=f"{document_id}:organization:{self._canonical_key('Organization', org)}",
                    evidence=org,
                    source_doc=document_id,
                    content=content,
                    confidence=0.76,
                )
            )
            relation_counter += 1

        # PERSON-WORK relations
        authored_match = _AUTHORED_RE.search(content)
        if authored_match:
            work_title = authored_match.group(1).strip()
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="authored",
                    object_id=f"{document_id}:work:{self._canonical_key('Work', work_title)}",
                    evidence=work_title,
                    source_doc=document_id,
                    content=content,
                    confidence=0.83,
                )
            )
            relation_counter += 1

        translated_match = _TRANSLATED_RE.search(content)
        if translated_match:
            work_title = translated_match.group(1).strip()
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="translated",
                    object_id=f"{document_id}:work:{self._canonical_key('Work', work_title)}",
                    evidence=work_title,
                    source_doc=document_id,
                    content=content,
                    confidence=0.80,
                )
            )
            relation_counter += 1

        edited_match = _EDITED_RE.search(content)
        if edited_match:
            work_title = edited_match.group(1).strip()
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="edited",
                    object_id=f"{document_id}:work:{self._canonical_key('Work', work_title)}",
                    evidence=work_title,
                    source_doc=document_id,
                    content=content,
                    confidence=0.77,
                )
            )
            relation_counter += 1

        # PERSON-PERSON relations
        influenced_by_match = _INFLUENCED_BY_RE.search(content)
        if influenced_by_match:
            person_name = self._clean_person(influenced_by_match.group(1))
            object_id = f"{document_id}:person:{self._canonical_key('Person', person_name)}"
            # Skip self-referential relations
            if object_id != person_id:
                relations.append(
                    self._build_relation(
                        relation_id=f"{document_id}:R{relation_counter}",
                        subject=person_id,
                        predicate="influenced_by",
                        object_id=object_id,
                        evidence=person_name,
                        source_doc=document_id,
                        content=content,
                        confidence=0.70,
                    )
                )
                relation_counter += 1

        collaborated_with_match = _COLLABORATED_WITH_RE.search(content)
        if collaborated_with_match:
            person_name = self._clean_person(collaborated_with_match.group(1))
            object_id = f"{document_id}:person:{self._canonical_key('Person', person_name)}"
            # Skip self-referential relations
            if object_id != person_id:
                relations.append(
                    self._build_relation(
                        relation_id=f"{document_id}:R{relation_counter}",
                        subject=person_id,
                        predicate="collaborated_with",
                        object_id=object_id,
                        evidence=person_name,
                        source_doc=document_id,
                        content=content,
                        confidence=0.74,
                    )
                )
                relation_counter += 1

        family_of_match = _FAMILY_OF_RE.search(content)
        if family_of_match:
            person_name = self._clean_person(family_of_match.group(1))
            object_id = f"{document_id}:person:{self._canonical_key('Person', person_name)}"
            # Skip self-referential relations
            if object_id != person_id:
                relations.append(
                    self._build_relation(
                        relation_id=f"{document_id}:R{relation_counter}",
                        subject=person_id,
                        predicate="family_of",
                        object_id=object_id,
                        evidence=person_name,
                        source_doc=document_id,
                        content=content,
                        confidence=0.81,
                    )
                )
                relation_counter += 1

        student_of_match = _STUDENT_OF_RE.search(content)
        if student_of_match:
            person_name = self._clean_person(student_of_match.group(1))
            object_id = f"{document_id}:person:{self._canonical_key('Person', person_name)}"
            # Skip self-referential relations
            if object_id != person_id:
                relations.append(
                    self._build_relation(
                        relation_id=f"{document_id}:R{relation_counter}",
                        subject=person_id,
                        predicate="student_of",
                        object_id=object_id,
                        evidence=person_name,
                        source_doc=document_id,
                        content=content,
                        confidence=0.79,
                    )
                )
                relation_counter += 1

        married_to_match = _MARRIED_TO_RE.search(content)
        if married_to_match:
            person_name = self._clean_person(married_to_match.group(1))
            object_id = f"{document_id}:person:{self._canonical_key('Person', person_name)}"
            # Skip self-referential relations
            if object_id != person_id:
                relations.append(
                    self._build_relation(
                        relation_id=f"{document_id}:R{relation_counter}",
                        subject=person_id,
                        predicate="family_of",
                        object_id=object_id,
                        evidence=person_name,
                        source_doc=document_id,
                        content=content,
                        confidence=0.85,
                    )
                )
                relation_counter += 1

        met_person_match = _MET_PERSON_RE.search(content)
        if met_person_match:
            person_name = self._clean_person(met_person_match.group(1))
            object_id = f"{document_id}:person:{self._canonical_key('Person', person_name)}"
            # Skip self-referential relations
            if object_id != person_id:
                relations.append(
                    self._build_relation(
                        relation_id=f"{document_id}:R{relation_counter}",
                        subject=person_id,
                        predicate="collaborated_with",
                        object_id=object_id,
                        evidence=person_name,
                        source_doc=document_id,
                        content=content,
                        confidence=0.65,
                    )
                )
                relation_counter += 1

        return relations

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

        relation_keys: set[tuple[str, str, str, str, int, int]] = set()
        normalized_relations: list[Relation] = []
        for relation in relations:
            subject = raw_to_normalized.get(relation.subject)
            object_id = raw_to_normalized.get(relation.object)
            if not subject or not object_id:
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
    ) -> Relation:
        mention = self._find_mention(source_doc, content, evidence)
        return Relation(
            id=relation_id,
            subject=subject,
            predicate=predicate,
            object=object_id,
            evidence=evidence,
            source_doc=source_doc,
            char_start=mention.char_start,
            char_end=mention.char_end,
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

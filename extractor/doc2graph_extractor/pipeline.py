from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import re

from .models import Entity, ExtractionResult, Mention, Relation


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
    r"\b(?:influenced|inspired|mentored|guided)\s+by\s+([A-Z][A-Za-z' .,-]+?)(?:[.;,]|\s+and\s|\s+who\s)"
)
_COLLABORATED_WITH_RE = re.compile(
    r"\b(?:collaborated|worked together|partnered)\s+with\s+([A-Z][A-Za-z' .,-]+?)(?:[.;,]|\s+on\s|\s+to\s)"
)
_FAMILY_OF_RE = re.compile(
    r"\b(?:the\s+)?(?:son|daughter|brother|sister|father|mother|parent|child|spouse|wife|husband)\s+of\s+([A-ZÀ-ÿ][\wÀ-ÿ' .,-]+?)(?:[.;,]|\s+and\s|\s+who\s)",
    re.UNICODE
)
_STUDENT_OF_RE = re.compile(
    r"\b(?:student|pupil|apprentice|disciple)\s+of\s+([A-Z][A-Za-z' .,-]+?)(?:[.;,]|\s+and\s|\s+who\s)"
)


class ExtractionPipeline:
    """Deterministic first-pass extraction with normalization."""

    def run(self, documents: list[dict]) -> dict:
        export_documents = [self._build_export_document(document) for document in documents]
        raw_entities: list[Entity] = []
        raw_relations: list[Relation] = []

        for document in documents:
            raw_entities.extend(self._extract_entities(document))
            raw_relations.extend(self._extract_relations(document))

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
        for pattern in (_INFLUENCED_BY_RE, _COLLABORATED_WITH_RE, _FAMILY_OF_RE, _STUDENT_OF_RE):
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
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="influenced_by",
                    object_id=f"{document_id}:person:{self._canonical_key('Person', person_name)}",
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
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="collaborated_with",
                    object_id=f"{document_id}:person:{self._canonical_key('Person', person_name)}",
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
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="family_of",
                    object_id=f"{document_id}:person:{self._canonical_key('Person', person_name)}",
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
            relations.append(
                self._build_relation(
                    relation_id=f"{document_id}:R{relation_counter}",
                    subject=person_id,
                    predicate="student_of",
                    object_id=f"{document_id}:person:{self._canonical_key('Person', person_name)}",
                    evidence=person_name,
                    source_doc=document_id,
                    content=content,
                    confidence=0.79,
                )
            )
            relation_counter += 1

        return relations

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

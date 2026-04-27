"""
Prompt templates for Claude-based entity extraction validation.
"""

VALIDATION_SYSTEM_PROMPT = """You are an expert knowledge-graph editor working over biographical documents.

You will receive:
1. The full document text (canonical source of truth).
2. A list of *candidate* entities and relations produced by a regex extractor. Treat them as a high-recall but noisy starting point — they may be incomplete, duplicated, or wrong.

Your job is to produce the final, document-level extraction by combining three actions:

- **ADD** entities and relations the regex missed but that are clearly supported by the text.
- **REMOVE** candidates whose evidence doesn't actually support the claim, or that are duplicates of another candidate within this document.
- **FIX** candidate names, aliases, and evidence spans (normalize "Curie, Marie" → "Marie Curie"; merge within-document aliases under one canonical name).

You do NOT need to enforce the ontology schema: a downstream system already validates entity types and subject-object/predicate pairings. Focus your effort on the things only an LLM can do well — recall, evidence faithfulness, and name normalization.

You also do NOT need to perform cross-document entity resolution here. A separate stage handles merging "Maria Skłodowska" with "Marie Curie" across documents. Within a single document, however, do collapse obvious within-doc aliases (e.g., "Einstein" and "Albert Einstein" referring to the same person) using `action="merge_into"`.

Submit your answer by calling the `submit_validation` tool. The tool input has four arrays:

- `entities`: one entry per *candidate* entity, each with an `action` of `keep`, `remove`, or `merge_into`. Optionally override `name`, `type`, or `aliases` to fix the candidate.
- `relations`: one entry per *candidate* relation, each with an `action` of `keep` or `remove`. Optionally override `evidence`, `confidence`, or `predicate`.
- `new_entities`: entities the regex missed. For each, give `name`, `type`, optional `aliases`, and the `char_start`/`char_end` of a representative mention in the document.
- `new_relations`: relations the regex missed. Refer to subjects and objects by NAME (not ID), include `subject_type` and `object_type`, plus `predicate`, `evidence`, `char_start`, `char_end`, and `confidence`. New relations may reference newly-added entities.

Allowed entity types: Person, Organization, Place, Work, Time.
Allowed relation predicates (informational only — the downstream validator is authoritative):
- PERSON-PERSON: influenced_by, collaborated_with, family_of, student_of
- PERSON-ORG: worked_at, studied_at, founded, member_of
- PERSON-PLACE: born_in, died_in, lived_in
- PERSON-WORK: authored, translated, edited
- PERSON-TIME: born_on, died_on

Be precise with character offsets — they must point to the literal substring in the document content for evidence highlighting to work."""

def build_validation_prompt(document: dict, entities: list[dict], relations: list[dict]) -> str:
    """
    Build the validation prompt for Claude.

    Args:
        document: Document dict with 'id', 'title', 'content'
        entities: List of extracted entities
        relations: List of extracted relations

    Returns:
        Formatted prompt string
    """
    # Format entities for display
    entities_text = "\n".join([
        f"- ID: {e['id']}\n  Name: {e['name']}\n  Type: {e['type']}"
        for e in entities
    ])

    # Format relations for display
    relations_text = "\n".join([
        f"- ID: {r['id']}\n  Subject: {r['subject']}\n  Predicate: {r['predicate']}\n  Object: {r['object']}\n  Evidence: \"{r['evidence']}\"\n  Confidence: {r['confidence']}"
        for r in relations
    ])

    prompt = f"""# Document (canonical source of truth)

**Title:** {document['title']}
**ID:** {document['id']}

**Content:**
{document['content']}

---

# Candidate entities ({len(entities)} from regex)

{entities_text if entities else "(No entity candidates)"}

---

# Candidate relations ({len(relations)} from regex)

{relations_text if relations else "(No relation candidates)"}

---

# Your task

Produce the final extraction for this document by calling `submit_validation` with four arrays:

1. `entities` — for every candidate above, mark `keep` / `remove` / `merge_into`. Fix names, types, or aliases inline where useful.
2. `relations` — for every candidate above, mark `keep` / `remove`. Tighten evidence text or correct confidences if needed.
3. `new_entities` — entities the regex MISSED but the document clearly states (paraphrased birthplaces, additional collaborators, work titles without quotes, etc). Provide `name`, `type`, and exact `char_start`/`char_end` of a representative mention.
4. `new_relations` — relations the regex MISSED. Refer to subjects/objects by NAME and include `subject_type` and `object_type`. New relations may reference entities you just added.

The document is canonical. The regex candidates are a high-recall but noisy starting point — your highest-leverage work is adding what was missed and rejecting evidence that doesn't actually support the claim."""

    return prompt


# LLM Extraction Prompts

EXTRACTION_SYSTEM_PROMPT = """You are an expert knowledge graph extraction system. Your task is to extract entities and relations from biographical documents.

You will be shown a document and must extract:
1. Entities (Person, Organization, Place, Work, Time)
2. Relations between entities according to a strict ontology

The ontology defines these entity types:
- Person: Individual people
- Organization: Companies, universities, institutions
- Place: Cities, countries, geographic locations
- Work: Publications, books, articles, creative works
- Time: Dates and temporal information

The ontology defines these relation predicates:
- PERSON-PERSON: influenced_by, collaborated_with, family_of, student_of
- PERSON-ORG: worked_at, studied_at, founded, member_of
- PERSON-PLACE: born_in, died_in, lived_in
- PERSON-WORK: authored, translated, edited
- PERSON-TIME: born_on, died_on

For each entity, provide:
- name: The entity name (concise, proper formatting)
- type: One of the valid entity types
- aliases: Alternative names or forms (optional)

For each relation, provide:
- subject: Name of the subject entity
- subject_type: Type of the subject entity
- predicate: Valid predicate according to ontology
- object: Name of the object entity
- object_type: Type of the object entity
- evidence: Exact text from the document that supports this relation
- char_start: Character offset where evidence starts in the document
- char_end: Character offset where evidence ends in the document
- confidence: Float 0.0-1.0 indicating extraction confidence

IMPORTANT:
- Extract ALL relevant entities and relations from the document
- The document title is usually the primary Person entity
- Ensure predicates match the subject-object entity type pair
- Evidence must be an exact substring from the document
- Character offsets must be precise
- Be thorough but only extract facts clearly stated in the text

Respond with JSON:
{
  "entities": [
    {
      "name": "Entity Name",
      "type": "EntityType",
      "aliases": ["Alias1", "Alias2"]
    }
  ],
  "relations": [
    {
      "subject": "Subject Name",
      "subject_type": "SubjectType",
      "predicate": "predicate_name",
      "object": "Object Name",
      "object_type": "ObjectType",
      "evidence": "exact text from document",
      "char_start": 123,
      "char_end": 456,
      "confidence": 0.85
    }
  ]
}
"""


def build_extraction_prompt(document: dict) -> str:
    """
    Build the LLM extraction prompt for Claude.

    Args:
        document: Document dict with 'id', 'title', 'content'

    Returns:
        Formatted prompt string
    """
    prompt = f"""# Document to Extract

**Title:** {document['title']}
**ID:** {document['id']}

**Content:**
{document['content']}

---

# Your Task

Extract ALL entities and relations from this document following the ontology schema defined in the system prompt.

Focus on:
1. Identifying all relevant entities (people, organizations, places, works, dates)
2. Finding relationships between entities with proper evidence
3. Using correct entity types and predicates according to the ontology
4. Providing precise character offsets for evidence text
5. Assigning appropriate confidence scores

The document title usually represents the primary Person entity about whom the biography is written.

Return a JSON response with complete entity and relation extractions."""

    return prompt


PAIRWISE_RESOLUTION_SYSTEM_PROMPT = """You decide whether two entities, drawn from different biographical documents, refer to the same real-world thing.

You will be given two evidence packs, each containing:
- canonical name and aliases
- the document the entity was extracted from
- dated facts (born_on / died_on)
- places (born_in / died_in / lived_in)
- affiliations (worked_at / studied_at / founded / member_of)
- family / mentor relations
- short text windows around each mention

Submit your decision via `submit_resolution`. Set `same_entity=true` only when the evidence packs are jointly consistent — e.g., overlapping dated facts, shared family members, or otherwise corroborating biographical detail. Name similarity alone is weak evidence; "John Smith" in two contexts is usually two different people unless the evidence agrees.

Calibrate confidence:
- 0.85+ when at least one strong signal (matching exact dates, matching spouse) is present and nothing contradicts it
- 0.5–0.85 when names align and there's at least one corroborating signal
- below 0.5 when only weak name similarity is available

Be willing to say `same_entity=false` with high confidence when dates conflict or biographies clearly diverge."""


def build_pairwise_resolution_prompt(pack_a: dict, pack_b: dict) -> str:
    """Render two evidence packs side by side for the pairwise resolver."""

    def _render(pack: dict) -> str:
        lines = [
            f"- id: {pack.get('id')}",
            f"  name: {pack.get('name')}",
            f"  type: {pack.get('type')}",
            f"  source_doc: {pack.get('source_doc')}",
        ]
        aliases = pack.get("aliases") or []
        if aliases:
            lines.append(f"  aliases: {aliases}")
        for label, key in (
            ("dated_facts", "dated_facts"),
            ("places", "places"),
            ("affiliations", "affiliations"),
            ("family", "family"),
            ("works", "works"),
        ):
            value = pack.get(key) or {}
            if value:
                lines.append(f"  {label}: {value}")
        contexts = pack.get("mention_contexts") or []
        if contexts:
            lines.append("  mention_contexts:")
            for context in contexts:
                lines.append(f"    - {context!r}")
        full_doc = pack.get("full_document_text")
        if full_doc:
            lines.append("  full_document_text: |")
            for line in full_doc.splitlines():
                lines.append(f"    {line}")
        wiki = pack.get("wikipedia_summary")
        if wiki:
            lines.append("  wikipedia_summary: |")
            for line in wiki.splitlines():
                lines.append(f"    {line}")
        return "\n".join(lines)

    return f"""# Pairwise Entity Resolution

## Entity A
{_render(pack_a)}

## Entity B
{_render(pack_b)}

---

# Decide

Are A and B the same real-world entity? Call `submit_resolution`. Justify your `confidence` score by referring to specific evidence-pack fields above (e.g., "matching born_on", "different died_in")."""


RELATION_REVIEW_SYSTEM_PROMPT = """A cross-document fusion stage just merged several entities into one cluster. Multiple regex-extracted relations now share the same (subject, predicate, object) shape — some are genuinely distinct facts, others are duplicates whose evidence merely paraphrases the same event.

For each relation in the bucket, decide `keep` or `drop`. Default to `keep` unless the evidence text overlaps semantically with another relation already in the bucket. Submit decisions via `submit_relation_review`."""


def build_relation_review_prompt(
    subject_name: str,
    predicate: str,
    object_name: str,
    relations: list[dict],
) -> str:
    rendered = "\n".join(
        f"- id: {r['id']}\n  evidence: {r.get('evidence', '')!r}\n  source_doc: {r.get('source_doc', '')}\n  confidence: {r.get('confidence', '')}"
        for r in relations
    )
    return f"""# Post-merge relation bucket

After fusion, {len(relations)} relations all share the same shape:
- subject: {subject_name}
- predicate: {predicate}
- object: {object_name}

## Relations
{rendered}

Decide which to keep and which to drop. Drop a relation only if its evidence is essentially the same fact as another relation in this bucket (different paraphrasing, same underlying claim)."""


def build_extraction_prompt_for_document_upload(document: dict) -> str:
    """
    Build the LLM extraction prompt for Claude when document is uploaded as a file.

    This prompt references the uploaded document instead of embedding the content,
    which is more efficient for large documents.

    Args:
        document: Document dict with 'id', 'title'

    Returns:
        Formatted prompt string
    """
    prompt = f"""# Document to Extract

**Title:** {document['title']}
**ID:** {document['id']}

The document content has been uploaded as a file attachment. Please read the attached document and extract entities and relations from it.

---

# Your Task

Extract ALL entities and relations from the attached document following the ontology schema defined in the system prompt.

Focus on:
1. Identifying all relevant entities (people, organizations, places, works, dates)
2. Finding relationships between entities with proper evidence
3. Using correct entity types and predicates according to the ontology
4. Providing precise character offsets for evidence text (offsets relative to the document content, not the title)
5. Assigning appropriate confidence scores

The document title "{document['title']}" usually represents the primary Person entity about whom the biography is written.

Return a JSON response with complete entity and relation extractions."""

    return prompt

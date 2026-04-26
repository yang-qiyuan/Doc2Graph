"""
Prompt templates for Claude-based entity extraction validation.
"""

VALIDATION_SYSTEM_PROMPT = """You are an expert knowledge graph extraction validator. Your task is to review entity and relation extractions from biographical documents and ensure they are correct, properly formatted, and concise.

You will be shown:
1. The source document text
2. Entities extracted by a regex-based system
3. Relations extracted by a regex-based system
4. The ontology schema defining valid entity types and relation predicates

Your job is to:
- Verify each entity is correctly typed according to the ontology
- Verify each relation uses a valid predicate for the subject-object type pair
- Check that evidence text accurately supports the claimed relation
- Remove or correct any incorrectly extracted entities/relations
- Make entity names and evidence text more concise where appropriate
- Ensure proper formatting (no extra whitespace, consistent casing)

CRITICAL - Entity Fusion and Disambiguation Rules:
1. **Entity Deduplication**: If multiple entities refer to the same real-world entity, merge them into one entity:
   - Keep the most formal/complete name as the primary name
   - Add other names as aliases
   - Mark duplicate entities with action="merge_into" and specify the target entity ID

2. **Entity Alignment**: Identify entities that are the same person/place/organization despite different names:
   - Same person with different name formats (e.g., "Marie Curie" vs "Marie Skłodowska-Curie")
   - Same person with maiden/married names
   - Same organization with full name vs abbreviation (e.g., "University of Paris" vs "Sorbonne")
   - Same place with different names (e.g., "Warsaw" vs "Warszawa")

3. **Relation Deduplication**: Only one relation is allowed between two entities:
   - If multiple relations of the same type exist between two entities, keep the one with better evidence
   - Mark duplicate relations with action="remove" and reason="duplicate"

4. **Name Selection Priority**:
   - For persons: Use the most commonly known formal name
   - For places: Use the English name when available
   - For organizations: Use the full official name
   - For works: Use the original title

IMPORTANT: Only validate and refine existing extractions. Do not add new entities or relations that were not extracted by the regex system.

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

Respond with a JSON object containing:
{
  "entities": [
    {
      "id": "original_id",
      "name": "Refined Name",
      "type": "ValidType",
      "aliases": ["Alternative Name 1", "Alternative Name 2"],
      "action": "keep" or "remove" or "merge_into",
      "merge_target_id": "target_entity_id (only if action=merge_into)",
      "reason": "explanation if removed, merged, or significantly changed"
    }
  ],
  "relations": [
    {
      "id": "original_id",
      "subject": "entity_id",
      "predicate": "valid_predicate",
      "object": "entity_id",
      "evidence": "concise evidence text",
      "confidence": 0.0-1.0,
      "action": "keep" or "remove",
      "reason": "explanation if removed or changed"
    }
  ]
}
"""

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

    prompt = f"""# Document to Validate

**Title:** {document['title']}
**ID:** {document['id']}

**Content:**
{document['content']}

---

# Extracted Entities ({len(entities)} total)

{entities_text if entities else "(No entities extracted)"}

---

# Extracted Relations ({len(relations)} total)

{relations_text if relations else "(No relations extracted)"}

---

# Your Task

Please validate these extractions and return a JSON response with refined entities and relations. For each entity and relation, specify whether to "keep" or "remove" it, and provide a reason if you make significant changes.

Focus on:
1. Type correctness (does the entity match its assigned type?)
2. Predicate validity (is the predicate appropriate for the entity types?)
3. Evidence accuracy (does the evidence text support the claimed relation?)
4. Conciseness (can names or evidence be shortened without losing meaning?)
5. Formatting (remove extra whitespace, fix casing issues)

Remember: Only validate and refine the provided extractions. Do not add new entities or relations."""

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


CROSS_DOCUMENT_FUSION_SYSTEM_PROMPT = """You are an expert at identifying duplicate entities across multiple documents and merging them intelligently.

You will be given a list of entities extracted from multiple biographical documents. Your task is to identify entities that refer to the same real-world entity and mark them for merging.

**Strong Matching Signals** (if ANY of these match, entities are likely the same):
1. **Exact birth and death dates** - If two Person entities have the exact same birth/death dates, they are almost certainly the same person
2. **Shared spouse** - If two Person entities are married to the same person, they are likely the same
3. **Same organization affiliations + similar time period** - Same university, same workplace at similar times
4. **Multiple overlapping facts** - Same achievements, same locations, same collaborators

**Name Variations to Consider**:
- Maiden names vs married names (e.g., "Maria Skłodowska" → "Marie Curie")
- Different transliterations (e.g., "Warszawa" → "Warsaw")
- Abbreviations vs full names (e.g., "MIT" → "Massachusetts Institute of Technology")
- Different language versions (e.g., "Sorbonne" → "University of Paris")

**Critical Example - Marie Curie**:
- "Marie Curie" (married name, French) and "Maria Skłodowska" (maiden name, Polish) are THE SAME PERSON
- Both born November 7, 1867 in Warsaw, died July 4, 1934
- Both married Pierre Curie in 1895
- Both won Nobel Prize in Physics 1903 and Chemistry 1911
- **ACTION**: Merge "Maria Skłodowska" into "Marie Curie", add "Maria Skłodowska" as alias

Respond with JSON listing entities to merge:
{
  "merges": [
    {
      "source_entity_id": "entity_to_merge",
      "target_entity_id": "entity_to_keep",
      "confidence": 0.0-1.0,
      "reason": "explanation of why these are the same entity",
      "merged_name": "Canonical name to use",
      "aliases": ["Alternative names to add as aliases"]
    }
  ]
}
"""


def build_cross_document_fusion_prompt(all_entities: list[dict]) -> str:
    """
    Build prompt for cross-document entity fusion.

    Args:
        all_entities: All entities from all documents

    Returns:
        Formatted prompt string
    """
    # Group entities by type for easier comparison
    entities_by_type = {}
    for entity in all_entities:
        entity_type = entity.get('type', 'Unknown')
        if entity_type not in entities_by_type:
            entities_by_type[entity_type] = []
        entities_by_type[entity_type].append(entity)

    # Format entities for display
    entities_text = []
    for entity_type, entities in sorted(entities_by_type.items()):
        entities_text.append(f"\n## {entity_type} Entities ({len(entities)} total)")
        for entity in entities:
            aliases_str = f", aliases: {entity.get('aliases', [])}" if entity.get('aliases') else ""
            source_doc = entity.get('source_doc', 'unknown')
            entities_text.append(f"- ID: {entity['id']}")
            entities_text.append(f"  Name: {entity['name']}{aliases_str}")
            entities_text.append(f"  Source: {source_doc}")

    prompt = f"""# Cross-Document Entity Fusion Task

You have been given {len(all_entities)} entities extracted from multiple biographical documents. Your task is to identify entities that refer to the same real-world entity despite having different names or being from different documents.

{"".join(entities_text)}

---

# Your Task

Identify entities that should be merged because they refer to the same real-world entity. Pay special attention to:

1. **Person entities with different names** - Look for maiden vs married names, different spellings, or different language versions
2. **Same birth/death dates** - This is a very strong signal for Person entities
3. **Shared relationships** - Entities connected to the same spouse, colleagues, or organizations
4. **Place entities with different names** - Different spellings or language versions of the same location
5. **Organization entities** - Abbreviations vs full names, alternative names

For each set of duplicate entities:
- Choose the most formal/complete name as the target
- Mark others to merge into it
- List all name variations as aliases

Return a JSON response with the merges list."""

    return prompt


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

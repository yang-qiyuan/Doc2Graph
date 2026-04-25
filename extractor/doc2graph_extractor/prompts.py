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
      "action": "keep" or "remove",
      "reason": "explanation if removed or significantly changed"
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

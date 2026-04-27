"""
Claude-based validation agent for entity extraction refinement.
"""

import base64
import os
from typing import Any

import httpx
from anthropic import Anthropic
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from .prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    PAIRWISE_RESOLUTION_SYSTEM_PROMPT,
    RELATION_REVIEW_SYSTEM_PROMPT,
    VALIDATION_SYSTEM_PROMPT,
    build_extraction_prompt,
    build_extraction_prompt_for_document_upload,
    build_pairwise_resolution_prompt,
    build_relation_review_prompt,
    build_validation_prompt,
)


class ValidationResponse(BaseModel):
    """Structured response from Claude validation."""

    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    new_entities: list[dict[str, Any]] = Field(default_factory=list)
    new_relations: list[dict[str, Any]] = Field(default_factory=list)


class ExtractionResponse(BaseModel):
    """Structured response from Claude extraction."""

    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool schemas. Forcing tool_choice on these eliminates markdown-fence parsing
# and JSONDecodeError handling — the SDK guarantees the input matches schema.
# ---------------------------------------------------------------------------

VALIDATION_TOOL = {
    "name": "submit_validation",
    "description": (
        "Submit the final extraction for one document. `entities` and "
        "`relations` carry per-candidate actions (keep / remove / fix / "
        "merge_into); `new_entities` and `new_relations` add items the "
        "regex candidate generator missed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "action": {
                            "type": "string",
                            "enum": ["keep", "remove", "merge_into"],
                        },
                        "merge_target_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "action"],
                },
            },
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "subject": {"type": "string"},
                        "predicate": {"type": "string"},
                        "object": {"type": "string"},
                        "evidence": {"type": "string"},
                        "confidence": {"type": "number"},
                        "action": {"type": "string", "enum": ["keep", "remove"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "action"],
                },
            },
            "new_entities": {
                "type": "array",
                "description": (
                    "Entities the regex missed. Each item must be supported by "
                    "the document text via the given char_start/char_end span."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "char_start": {"type": "integer"},
                        "char_end": {"type": "integer"},
                    },
                    "required": ["name", "type"],
                },
            },
            "new_relations": {
                "type": "array",
                "description": (
                    "Relations the regex missed. Subject and object are given "
                    "by name+type and resolved against the entity set, "
                    "including newly-added entities."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "subject_type": {"type": "string"},
                        "predicate": {"type": "string"},
                        "object": {"type": "string"},
                        "object_type": {"type": "string"},
                        "evidence": {"type": "string"},
                        "char_start": {"type": "integer"},
                        "char_end": {"type": "integer"},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "subject",
                        "subject_type",
                        "predicate",
                        "object",
                        "object_type",
                    ],
                },
            },
        },
        "required": ["entities", "relations"],
    },
}

RESOLVE_PAIR_TOOL = {
    "name": "submit_resolution",
    "description": "Same-or-different decision for one entity pair, with confidence and reasoning grounded in the evidence packs supplied.",
    "input_schema": {
        "type": "object",
        "properties": {
            "same_entity": {"type": "boolean"},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
            "preferred_name": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["same_entity", "confidence", "reason"],
    },
}

RELATION_REVIEW_TOOL = {
    "name": "submit_relation_review",
    "description": "Per-relation keep/drop decisions for a post-merge bucket.",
    "input_schema": {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "action": {"type": "string", "enum": ["keep", "drop"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "action"],
                },
            },
        },
        "required": ["decisions"],
    },
}

EXTRACTION_TOOL = {
    "name": "submit_extraction",
    "description": "Submit extracted entities and relations for the document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "type"],
                },
            },
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "subject_type": {"type": "string"},
                        "predicate": {"type": "string"},
                        "object": {"type": "string"},
                        "object_type": {"type": "string"},
                        "evidence": {"type": "string"},
                        "char_start": {"type": "integer"},
                        "char_end": {"type": "integer"},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "subject",
                        "subject_type",
                        "predicate",
                        "object",
                        "object_type",
                    ],
                },
            },
        },
        "required": ["entities", "relations"],
    },
}


def _call_claude_with_tool(
    client: Anthropic,
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system_prompt: str,
    user_content: Any,
    tool_schema: dict,
    tool_name: str,
    use_streaming: bool = False,
) -> dict[str, Any]:
    """
    Invoke Claude with tool_choice forced to a single tool and return the
    tool-input dict. Replaces text-JSON-with-markdown-fences parsing.
    """
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": tool_name},
    )

    if use_streaming:
        with client.messages.stream(**kwargs) as stream:
            stream.until_done()
            message = stream.get_final_message()
    else:
        message = client.messages.create(**kwargs)

    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return dict(block.input)

    raise RuntimeError(
        f"Claude did not invoke tool {tool_name}; "
        f"got blocks: {[getattr(b, 'type', None) for b in message.content]}"
    )


def _build_anthropic_client(api_key: str) -> Anthropic:
    """Create an Anthropic client, honouring HTTP(S)_PROXY env vars."""
    http_proxy = os.getenv("http_proxy") or os.getenv("HTTP_PROXY")
    https_proxy = os.getenv("https_proxy") or os.getenv("HTTPS_PROXY")
    if http_proxy or https_proxy:
        proxy = https_proxy or http_proxy
        return Anthropic(api_key=api_key, http_client=httpx.Client(proxy=proxy))
    return Anthropic(api_key=api_key)


class ValidationAgent:
    """
    Agent that uses Claude to validate and refine entity extractions.

    This agent takes regex-extracted entities and relations, sends them to
    Claude for validation, and returns refined extractions with corrections
    and formatting improvements.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        """
        Initialize the validation agent.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model to use (defaults to CLAUDE_MODEL env var or claude-3-5-sonnet-20241022)
            max_tokens: Maximum tokens for response (defaults to MAX_TOKENS env var or 4096)
            temperature: Temperature for generation (defaults to TEMPERATURE env var or 0.0)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable must be set or api_key must be provided"
            )

        self.model = model or os.getenv("CLAUDE_MODEL", "claude-3-haiku-20240307")
        self.max_tokens = max_tokens or int(os.getenv("MAX_TOKENS", "4096"))
        self.temperature = temperature or float(os.getenv("TEMPERATURE", "0.0"))
        self.client = _build_anthropic_client(self.api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _validate_via_tool(self, user_prompt: str) -> ValidationResponse:
        data = _call_claude_with_tool(
            self.client,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system_prompt=VALIDATION_SYSTEM_PROMPT,
            user_content=user_prompt,
            tool_schema=VALIDATION_TOOL,
            tool_name="submit_validation",
        )
        return ValidationResponse(**data)

    def _apply_entity_refinements(
        self,
        original_entities: list[dict],
        validated_entities: list[dict],
    ) -> list[dict]:
        """
        Apply Claude's entity refinements to original extractions, including entity merging.

        Args:
            original_entities: Original regex-extracted entities
            validated_entities: Claude's validated/refined entities

        Returns:
            Refined entity list with merged entities
        """
        # Create lookup by ID for validated entities
        validated_by_id = {e["id"]: e for e in validated_entities}

        # Build merge map: source_id -> target_id
        merge_map = {}
        for validated in validated_entities:
            if validated.get("action") == "merge_into" and validated.get("merge_target_id"):
                merge_map[validated["id"]] = validated["merge_target_id"]

        # First pass: collect entities to keep and accumulate aliases for merged entities
        entities_to_keep = {}
        merged_aliases = {}  # target_id -> list of aliases from merged entities

        for original in original_entities:
            entity_id = original["id"]

            if entity_id not in validated_by_id:
                # Entity not in validation response - keep original
                entities_to_keep[entity_id] = original
                continue

            validated = validated_by_id[entity_id]

            if validated.get("action") == "remove":
                # Entity marked for removal - skip it
                continue

            if validated.get("action") == "merge_into":
                # Entity should be merged into another
                target_id = validated.get("merge_target_id")
                if target_id:
                    # Accumulate this entity's name as an alias for the target
                    if target_id not in merged_aliases:
                        merged_aliases[target_id] = []
                    merged_aliases[target_id].append(original["name"])
                    # Also add any validated aliases
                    if "aliases" in validated:
                        merged_aliases[target_id].extend(validated["aliases"])
                continue

            # Apply refinements for entities to keep
            refined_entity = original.copy()
            if "name" in validated:
                refined_entity["name"] = validated["name"]
            if "type" in validated:
                refined_entity["type"] = validated["type"]

            # Handle aliases
            existing_aliases = set(refined_entity.get("aliases", []))
            if "aliases" in validated:
                existing_aliases.update(validated["aliases"])
            if existing_aliases:
                refined_entity["aliases"] = sorted(list(existing_aliases))

            entities_to_keep[entity_id] = refined_entity

        # Second pass: add accumulated aliases to target entities
        for target_id, aliases in merged_aliases.items():
            if target_id in entities_to_keep:
                existing_aliases = set(entities_to_keep[target_id].get("aliases", []))
                existing_aliases.update(aliases)
                # Remove the entity's own name from its aliases
                existing_aliases.discard(entities_to_keep[target_id]["name"])
                if existing_aliases:
                    entities_to_keep[target_id]["aliases"] = sorted(list(existing_aliases))

        return list(entities_to_keep.values())

    def _apply_relation_refinements(
        self,
        original_relations: list[dict],
        validated_relations: list[dict],
        entity_merge_map: dict[str, str],
    ) -> list[dict]:
        """
        Apply Claude's relation refinements to original extractions.

        Updates relation subject/object IDs when entities are merged and deduplicates relations.

        Args:
            original_relations: Original regex-extracted relations
            validated_relations: Claude's validated/refined relations
            entity_merge_map: Map from merged entity ID to target entity ID

        Returns:
            Refined relation list with deduplicated relations
        """
        # Create lookup by ID for validated relations
        validated_by_id = {r["id"]: r for r in validated_relations}

        refined = []
        seen_relations = set()  # Track (subject, predicate, object) tuples to deduplicate

        for original in original_relations:
            relation_id = original["id"]

            if relation_id not in validated_by_id:
                # Relation not in validation response - keep original
                refined.append(original)
                continue

            validated = validated_by_id[relation_id]

            if validated.get("action") == "remove":
                # Relation marked for removal - skip it
                continue

            # Apply refinements
            refined_relation = original.copy()
            if "evidence" in validated:
                refined_relation["evidence"] = validated["evidence"]
            if "confidence" in validated:
                refined_relation["confidence"] = validated["confidence"]
            if "predicate" in validated:
                refined_relation["predicate"] = validated["predicate"]

            # Update subject/object IDs if entities were merged
            subject_id = refined_relation["subject"]
            object_id = refined_relation["object"]
            predicate = refined_relation["predicate"]

            # Apply entity merges
            if subject_id in entity_merge_map:
                refined_relation["subject"] = entity_merge_map[subject_id]
                subject_id = refined_relation["subject"]

            if object_id in entity_merge_map:
                refined_relation["object"] = entity_merge_map[object_id]
                object_id = refined_relation["object"]

            # Deduplicate: only one relation per (subject, predicate, object) tuple
            relation_key = (subject_id, predicate, object_id)
            if relation_key in seen_relations:
                # Duplicate relation - skip it
                continue

            seen_relations.add(relation_key)
            refined.append(refined_relation)

        return refined

    def validate(
        self,
        document: dict,
        entities: list[dict],
        relations: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """
        Validate, refine, and extend entity/relation extractions using Claude.

        Claude is allowed to add, remove, and fix candidates from the regex
        pass — it acts as a precision filter on top of the high-recall
        candidate generator, not as a rubber stamp.

        Args:
            document: Document dict with 'id', 'title', 'content'
            entities: List of extracted entity dicts
            relations: List of extracted relation dicts

        Returns:
            Tuple of (refined_entities, refined_relations)

        Raises:
            Exception if validation fails
        """
        user_prompt = build_validation_prompt(document, entities, relations)
        validation_response = self._validate_via_tool(user_prompt)

        # Build entity merge map
        entity_merge_map = {}
        for validated_entity in validation_response.entities:
            if validated_entity.get("action") == "merge_into" and validated_entity.get("merge_target_id"):
                entity_merge_map[validated_entity["id"]] = validated_entity["merge_target_id"]

        refined_entities = self._apply_entity_refinements(
            entities, validation_response.entities
        )
        refined_relations = self._apply_relation_refinements(
            relations, validation_response.relations, entity_merge_map
        )

        refined_entities, refined_relations = self._apply_new_entities_and_relations(
            document,
            refined_entities,
            refined_relations,
            validation_response.new_entities,
            validation_response.new_relations,
        )

        return refined_entities, refined_relations

    @staticmethod
    def _canonical_name(value: str) -> str:
        return " ".join((value or "").split()).casefold().strip()

    def _apply_new_entities_and_relations(
        self,
        document: dict,
        entities: list[dict],
        relations: list[dict],
        new_entities: list[dict],
        new_relations: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """
        Append LLM-added entities and relations.

        New entities are given synthetic IDs prefixed with `llm_added_`; the
        downstream `_normalize_graph` will fold them in by canonical key
        alongside any regex-extracted siblings of the same name and type.
        New relations refer to subject/object by name+type and are dropped
        if the names can't be resolved to an entity in the merged set.
        """
        doc_id = document.get("id", "")
        content = document.get("content", "")

        # Index merged entity set by (canonical name, type) -> id.
        name_index: dict[tuple[str, str], str] = {}
        for entity in entities:
            name_index[(self._canonical_name(entity["name"]), entity["type"])] = entity["id"]
            for alias in entity.get("aliases", []) or []:
                name_index[(self._canonical_name(alias), entity["type"])] = entity["id"]

        added_entity_count = 0
        for ne in new_entities or []:
            name = (ne.get("name") or "").strip()
            etype = ne.get("type") or ""
            if not name or not etype:
                continue

            key = (self._canonical_name(name), etype)
            if key in name_index:
                # Already present — fold any extra aliases into the existing entity.
                existing_id = name_index[key]
                for entity in entities:
                    if entity["id"] == existing_id:
                        merged = set(entity.get("aliases", []) or [])
                        merged.update(ne.get("aliases", []) or [])
                        merged.discard(entity["name"])
                        if merged:
                            entity["aliases"] = sorted(merged)
                        break
                continue

            char_start, char_end = self._coerce_span(
                ne.get("char_start"), ne.get("char_end"), name, content
            )
            if char_start is None:
                continue

            new_id = f"{doc_id}:llm_added_{added_entity_count}"
            added_entity_count += 1
            entities.append(
                {
                    "id": new_id,
                    "name": name,
                    "type": etype,
                    "aliases": ne.get("aliases", []) or [],
                    "source_doc": doc_id,
                    "mentions": [
                        {"doc_id": doc_id, "char_start": char_start, "char_end": char_end}
                    ],
                }
            )
            name_index[key] = new_id

        seen_relations = {
            (r["subject"], r.get("predicate", ""), r["object"]) for r in relations
        }
        added_relation_count = 0
        for nr in new_relations or []:
            predicate = nr.get("predicate") or ""
            subject_name = nr.get("subject") or ""
            subject_type = nr.get("subject_type") or ""
            object_name = nr.get("object") or ""
            object_type = nr.get("object_type") or ""
            if not predicate or not subject_name or not object_name:
                continue

            subject_id = name_index.get((self._canonical_name(subject_name), subject_type))
            object_id = name_index.get((self._canonical_name(object_name), object_type))
            if not subject_id or not object_id:
                continue

            relation_key = (subject_id, predicate, object_id)
            if relation_key in seen_relations:
                continue

            evidence = nr.get("evidence") or ""
            char_start, char_end = self._coerce_span(
                nr.get("char_start"), nr.get("char_end"), evidence, content
            )
            if char_start is None:
                continue

            seen_relations.add(relation_key)
            relations.append(
                {
                    "id": f"{doc_id}:Rnew{added_relation_count}",
                    "subject": subject_id,
                    "predicate": predicate,
                    "object": object_id,
                    "evidence": evidence,
                    "source_doc": doc_id,
                    "char_start": char_start,
                    "char_end": char_end,
                    "confidence": float(nr.get("confidence", 0.7)),
                }
            )
            added_relation_count += 1

        return entities, relations

    @staticmethod
    def _coerce_span(
        char_start: Any,
        char_end: Any,
        text: str,
        content: str,
    ) -> tuple[int | None, int | None]:
        """Validate LLM-supplied char offsets and fall back to content.find()."""
        try:
            cs = int(char_start)
            ce = int(char_end)
        except (TypeError, ValueError):
            cs, ce = -1, -1

        content_len = len(content)
        if 0 <= cs < ce <= content_len:
            return cs, ce

        if text:
            pos = content.find(text)
            if pos >= 0:
                return pos, pos + len(text)
        return None, None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def resolve_pair(self, pack_a: dict, pack_b: dict) -> dict[str, Any]:
        """
        Decide whether two entities (given as evidence-pack dicts) refer to
        the same real-world entity. Returns a dict with `same_entity`,
        `confidence`, `reason`, `preferred_name`, and `aliases`.
        """
        user_prompt = build_pairwise_resolution_prompt(pack_a, pack_b)
        result = _call_claude_with_tool(
            self.client,
            model=self.model,
            max_tokens=1024,
            temperature=self.temperature,
            system_prompt=PAIRWISE_RESOLUTION_SYSTEM_PROMPT,
            user_content=user_prompt,
            tool_schema=RESOLVE_PAIR_TOOL,
            tool_name="submit_resolution",
        )
        result.setdefault("aliases", [])
        result.setdefault("preferred_name", "")
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def review_merged_relations(
        self,
        subject_name: str,
        predicate: str,
        object_name: str,
        relations: list[dict],
    ) -> dict[str, str]:
        """
        Decide which relations in a post-merge bucket to keep vs drop.
        Returns `{relation_id: 'keep' | 'drop'}`. Relations not mentioned
        in the response default to keep.
        """
        if len(relations) < 2:
            return {r["id"]: "keep" for r in relations}

        user_prompt = build_relation_review_prompt(
            subject_name, predicate, object_name, relations
        )
        result = _call_claude_with_tool(
            self.client,
            model=self.model,
            max_tokens=1024,
            temperature=self.temperature,
            system_prompt=RELATION_REVIEW_SYSTEM_PROMPT,
            user_content=user_prompt,
            tool_schema=RELATION_REVIEW_TOOL,
            tool_name="submit_relation_review",
        )
        decisions: dict[str, str] = {}
        for entry in result.get("decisions", []):
            rid = entry.get("id")
            action = entry.get("action")
            if rid and action in {"keep", "drop"}:
                decisions[rid] = action
        # Default to keep for any relation Claude didn't explicitly mention.
        for r in relations:
            decisions.setdefault(r["id"], "keep")
        return decisions


class ExtractionAgent:
    """
    Agent that uses Claude to perform direct entity and relation extraction.

    This agent takes a document and uses Claude to extract entities and relations
    directly, without relying on regex patterns. This is the most accurate but
    slowest extraction mode.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        """
        Initialize the extraction agent.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model to use (defaults to CLAUDE_MODEL env var)
            max_tokens: Maximum tokens for response (defaults to MAX_TOKENS env var or 8192)
            temperature: Temperature for generation (defaults to TEMPERATURE env var or 0.0)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable must be set or api_key must be provided"
            )

        self.model = model or os.getenv("CLAUDE_MODEL", "claude-3-haiku-20240307")
        self.max_tokens = max_tokens or int(os.getenv("MAX_TOKENS", "8192"))
        self.temperature = temperature or float(os.getenv("TEMPERATURE", "0.0"))
        self.client = _build_anthropic_client(self.api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _extract_via_tool(
        self,
        user_prompt: str,
        document_content: str | None = None,
    ) -> ExtractionResponse:
        if document_content:
            document_bytes = document_content.encode("utf-8")
            document_base64 = base64.standard_b64encode(document_bytes).decode("utf-8")
            user_content: Any = [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "text/plain",
                        "data": document_base64,
                    },
                },
                {"type": "text", "text": user_prompt},
            ]
        else:
            user_content = user_prompt

        # Stream when generating very large outputs to avoid SDK timeout.
        use_streaming = self.max_tokens > 16384

        data = _call_claude_with_tool(
            self.client,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_content=user_content,
            tool_schema=EXTRACTION_TOOL,
            tool_name="submit_extraction",
            use_streaming=use_streaming,
        )
        return ExtractionResponse(**data)

    def extract(self, document: dict) -> tuple[list[dict], list[dict]]:
        """
        Extract entities and relations from a document using Claude.

        Args:
            document: Document dict with 'id', 'title', 'content'

        Returns:
            Tuple of (entities, relations) as lists of dicts

        Raises:
            Exception if extraction fails
        """
        user_prompt = build_extraction_prompt(document)
        response = self._extract_via_tool(user_prompt)
        return response.entities, response.relations

"""
Claude-based validation agent for entity extraction refinement.
"""

import base64
import json
import os
from typing import Any

import httpx
from anthropic import Anthropic
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from .prompts import (
    CROSS_DOCUMENT_FUSION_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
    VALIDATION_SYSTEM_PROMPT,
    build_cross_document_fusion_prompt,
    build_extraction_prompt,
    build_extraction_prompt_for_document_upload,
    build_validation_prompt,
)


class ValidationResponse(BaseModel):
    """Structured response from Claude validation."""

    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)


class ExtractionResponse(BaseModel):
    """Structured response from Claude extraction."""

    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)


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

        # Configure proxy support from environment variables
        http_proxy = os.getenv("http_proxy") or os.getenv("HTTP_PROXY")
        https_proxy = os.getenv("https_proxy") or os.getenv("HTTPS_PROXY")

        if http_proxy or https_proxy:
            # Create httpx client with proxy configuration
            # httpx expects a proxy URL string or a dict of protocol->URL mappings
            proxy = https_proxy or http_proxy  # Prefer https_proxy
            http_client = httpx.Client(proxy=proxy)
            self.client = Anthropic(api_key=self.api_key, http_client=http_client)
        else:
            self.client = Anthropic(api_key=self.api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _call_claude(self, user_prompt: str) -> str:
        """
        Call Claude API with retry logic.

        Args:
            user_prompt: The user prompt to send to Claude

        Returns:
            Claude's response text

        Raises:
            Exception if API call fails after retries
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=VALIDATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        return response.content[0].text

    def _parse_validation_response(self, response_text: str) -> ValidationResponse:
        """
        Parse Claude's JSON response into structured format.

        Args:
            response_text: Raw text response from Claude

        Returns:
            Parsed ValidationResponse object

        Raises:
            json.JSONDecodeError if response is not valid JSON
        """
        # Extract JSON from response (Claude sometimes wraps it in markdown)
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]  # Remove ```json
        if response_text.startswith("```"):
            response_text = response_text[3:]  # Remove ```
        if response_text.endswith("```"):
            response_text = response_text[:-3]  # Remove trailing ```

        response_text = response_text.strip()

        # Parse JSON
        data = json.loads(response_text)

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
        Validate and refine entity/relation extractions using Claude.

        Performs entity fusion, disambiguation, and relation deduplication.

        Args:
            document: Document dict with 'id', 'title', 'content'
            entities: List of extracted entity dicts
            relations: List of extracted relation dicts

        Returns:
            Tuple of (refined_entities, refined_relations)

        Raises:
            Exception if validation fails
        """
        # Build the validation prompt
        user_prompt = build_validation_prompt(document, entities, relations)

        # Call Claude
        response_text = self._call_claude(user_prompt)

        # Parse response
        validation_response = self._parse_validation_response(response_text)

        # Build entity merge map
        entity_merge_map = {}
        for validated_entity in validation_response.entities:
            if validated_entity.get("action") == "merge_into" and validated_entity.get("merge_target_id"):
                entity_merge_map[validated_entity["id"]] = validated_entity["merge_target_id"]

        # Apply entity refinements (includes merging)
        refined_entities = self._apply_entity_refinements(
            entities, validation_response.entities
        )

        # Apply relation refinements (updates entity references and deduplicates)
        refined_relations = self._apply_relation_refinements(
            relations, validation_response.relations, entity_merge_map
        )

        return refined_entities, refined_relations

    def cross_document_fusion(
        self,
        all_entities: list[dict],
    ) -> list[tuple[str, str, list[str]]]:
        """
        Perform cross-document entity fusion using Claude.

        Identifies entities from different documents that refer to the same real-world entity.

        Args:
            all_entities: All entities from all documents

        Returns:
            List of (source_id, target_id, aliases) tuples for entities to merge

        Raises:
            Exception if fusion fails
        """
        if len(all_entities) < 2:
            # Need at least 2 entities to perform fusion
            return []

        # Build the fusion prompt
        user_prompt = build_cross_document_fusion_prompt(all_entities)

        # Call Claude with fusion system prompt
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=CROSS_DOCUMENT_FUSION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_text = response.content[0].text

        # Parse response
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            import sys
            print(f"WARNING: Failed to parse cross-document fusion response: {e}", file=sys.stderr)
            print(f"Response text: {response_text[:500]}", file=sys.stderr)
            return []

        # Extract merge instructions
        merges = []
        for merge in data.get("merges", []):
            source_id = merge.get("source_entity_id")
            target_id = merge.get("target_entity_id")
            aliases = merge.get("aliases", [])

            if source_id and target_id:
                merges.append((source_id, target_id, aliases))
                import sys
                print(f"Cross-document fusion: {source_id} → {target_id} (confidence: {merge.get('confidence', 0.0):.2f})", file=sys.stderr)
                print(f"  Reason: {merge.get('reason', 'N/A')}", file=sys.stderr)

        return merges


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

        # Configure proxy support from environment variables
        http_proxy = os.getenv("http_proxy") or os.getenv("HTTP_PROXY")
        https_proxy = os.getenv("https_proxy") or os.getenv("HTTPS_PROXY")

        if http_proxy or https_proxy:
            proxy = https_proxy or http_proxy
            http_client = httpx.Client(proxy=proxy)
            self.client = Anthropic(api_key=self.api_key, http_client=http_client)
        else:
            self.client = Anthropic(api_key=self.api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _call_claude(self, user_prompt: str, document_content: str | None = None) -> str:
        """
        Call Claude API with retry logic.

        Args:
            user_prompt: The user prompt to send to Claude
            document_content: Optional document content to upload as base64-encoded file

        Returns:
            Claude's response text

        Raises:
            Exception if API call fails after retries
        """
        # Build message content
        if document_content:
            # Encode document content as base64
            document_bytes = document_content.encode('utf-8')
            document_base64 = base64.standard_b64encode(document_bytes).decode('utf-8')

            # Create message with document upload
            message_content = [
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
            # Plain text message
            message_content = user_prompt

        # Use streaming for large max_tokens values to avoid SDK timeout errors
        if self.max_tokens > 16384:
            # Streaming mode for very large responses
            full_response = []
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": message_content}],
            ) as stream:
                for text in stream.text_stream:
                    full_response.append(text)
            return "".join(full_response)
        else:
            # Standard non-streaming mode
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": message_content}],
            )
            return response.content[0].text

    def _parse_extraction_response(self, response_text: str) -> ExtractionResponse:
        """
        Parse Claude's JSON response into structured format.

        Args:
            response_text: Raw text response from Claude

        Returns:
            Parsed ExtractionResponse object

        Raises:
            json.JSONDecodeError if response is not valid JSON
        """
        original_text = response_text
        response_text = response_text.strip()

        # Extract JSON from response (Claude sometimes wraps it in markdown or adds explanatory text)
        # Look for JSON object markers
        if "```json" in response_text:
            # Extract content between ```json and ```
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end != -1:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            # Extract content between ``` markers
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end != -1:
                response_text = response_text[start:end].strip()
        else:
            # Try to find JSON object by looking for { and }
            start = response_text.find("{")
            end = response_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                response_text = response_text[start:end+1].strip()

        # Parse JSON with better error handling
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            # Print detailed debug info to stderr
            import sys
            print(f"\n{'=' * 80}", file=sys.stderr)
            print(f"JSON Parse Error at position {e.pos} (line {e.lineno}, col {e.colno})", file=sys.stderr)
            print(f"Error: {e.msg}", file=sys.stderr)
            print(f"{'=' * 80}", file=sys.stderr)

            # Show context around error
            start = max(0, e.pos - 200)
            end = min(len(response_text), e.pos + 200)
            context = response_text[start:end]
            print(f"Context around error position {e.pos}:", file=sys.stderr)
            print(context, file=sys.stderr)
            print(f"\n{'=' * 80}", file=sys.stderr)

            # Show first and last parts of response
            print(f"First 500 chars of response:", file=sys.stderr)
            print(response_text[:500], file=sys.stderr)
            print(f"\nLast 500 chars of response:", file=sys.stderr)
            print(response_text[-500:], file=sys.stderr)
            print(f"{'=' * 80}\n", file=sys.stderr)

            # Save full response to file for debugging
            with open("/tmp/claude_extraction_error.txt", "w") as f:
                f.write("=== ORIGINAL RESPONSE ===\n")
                f.write(original_text)
                f.write("\n\n=== PROCESSED RESPONSE ===\n")
                f.write(response_text)
            print(f"Full response saved to /tmp/claude_extraction_error.txt", file=sys.stderr)

            raise

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
        # Build the extraction prompt
        user_prompt = build_extraction_prompt(document)

        # Call Claude
        response_text = self._call_claude(user_prompt)

        # Parse response
        extraction_response = self._parse_extraction_response(response_text)

        return extraction_response.entities, extraction_response.relations

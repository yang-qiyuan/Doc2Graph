"""
Claude-based validation agent for entity extraction refinement.
"""

import json
import os
from typing import Any

import httpx
from anthropic import Anthropic
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from .prompts import VALIDATION_SYSTEM_PROMPT, build_validation_prompt


class ValidationResponse(BaseModel):
    """Structured response from Claude validation."""

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
        Apply Claude's entity refinements to original extractions.

        Args:
            original_entities: Original regex-extracted entities
            validated_entities: Claude's validated/refined entities

        Returns:
            Refined entity list (keeping only entities marked as "keep")
        """
        # Create lookup by ID for validated entities
        validated_by_id = {e["id"]: e for e in validated_entities}

        refined = []
        for original in original_entities:
            entity_id = original["id"]

            if entity_id not in validated_by_id:
                # Entity not in validation response - keep original
                refined.append(original)
                continue

            validated = validated_by_id[entity_id]

            if validated.get("action") == "remove":
                # Entity marked for removal - skip it
                continue

            # Apply refinements
            refined_entity = original.copy()
            if "name" in validated:
                refined_entity["name"] = validated["name"]
            if "type" in validated:
                refined_entity["type"] = validated["type"]

            refined.append(refined_entity)

        return refined

    def _apply_relation_refinements(
        self,
        original_relations: list[dict],
        validated_relations: list[dict],
    ) -> list[dict]:
        """
        Apply Claude's relation refinements to original extractions.

        Args:
            original_relations: Original regex-extracted relations
            validated_relations: Claude's validated/refined relations

        Returns:
            Refined relation list (keeping only relations marked as "keep")
        """
        # Create lookup by ID for validated relations
        validated_by_id = {r["id"]: r for r in validated_relations}

        refined = []
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

        # Apply refinements
        refined_entities = self._apply_entity_refinements(
            entities, validation_response.entities
        )
        refined_relations = self._apply_relation_refinements(
            relations, validation_response.relations
        )

        return refined_entities, refined_relations

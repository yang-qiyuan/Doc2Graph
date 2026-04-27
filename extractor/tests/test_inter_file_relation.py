"""Regression tests for the inter_file_relation fixtures.

Both fixture documents reference each other ("Einstein collaborated with
Niels Bohr" / "Bohr collaborated with Albert Einstein") and contain
several PERSON-PERSON relations whose triggers (`influenced_by`,
`married`, `collaborated_with`, etc.) are followed by additional clauses.

Before the regex fix, the inner `(\\s+[\\wÀ-ÿ.-]+)*` was greedy and the
engine extended each capture to the LAST valid terminator (often
end-of-string), so:

  - "collaborated with Albert Einstein on quantum mechanics and won..."
    captured "Albert Einstein on quantum mechanics" instead of
    "Albert Einstein", and
  - that polluted name produced a different canonical key, so the
    Einstein entity in `niels_bohr.md` failed to merge with the clean
    Einstein entity from `albert_einstein.md`.

These tests load the actual fixture files so future trigger broadening
or pattern edits keep both invariants: clean captures + cross-doc merge.
"""
from __future__ import annotations

import pathlib

import pytest

from doc2graph_extractor.pipeline import ExtractionPipeline


FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[1] / "inter_file_relation"


def _load_documents() -> list[dict]:
    docs = []
    for filename in ("albert_einstein.md", "niels_bohr.md"):
        path = FIXTURE_DIR / filename
        docs.append(
            {
                "id": path.stem,
                "title": path.stem.replace("_", " ").title(),
                "source_type": "markdown",
                "content": path.read_text(),
            }
        )
    return docs


@pytest.fixture(scope="module")
def extraction_result() -> dict:
    return ExtractionPipeline().run(_load_documents())


def _persons(result: dict) -> list[dict]:
    return [e for e in result["entities"] if e["type"] == "Person"]


def test_person_captures_are_clean_without_trailing_clauses(extraction_result):
    """No Person name should bleed into the next clause."""
    person_names = {e["name"] for e in _persons(extraction_result)}

    # Specific captures from the regex triggers in the fixtures.
    assert "Albert Einstein" in person_names
    assert "Niels Bohr" in person_names
    assert "Max Planck" in person_names
    assert "Mileva Marić" in person_names
    assert "Ernest Rutherford" in person_names
    assert "Margrethe Nørlund" in person_names

    # Sanity: no captured name should be longer than ~5 tokens. Real
    # human names are short; anything longer is the over-capture bug.
    for name in person_names:
        assert len(name.split()) <= 5, f"Person name looks over-captured: {name!r}"


def test_einstein_and_bohr_merge_across_documents(extraction_result):
    """Both protagonists appear in each other's documents — they must
    normalize to a single Person entity with mentions in both files."""
    persons_by_name = {e["name"]: e for e in _persons(extraction_result)}

    einstein = persons_by_name.get("Albert Einstein")
    bohr = persons_by_name.get("Niels Bohr")
    assert einstein is not None and bohr is not None

    einstein_docs = {m["doc_id"] for m in einstein["mentions"]}
    bohr_docs = {m["doc_id"] for m in bohr["mentions"]}
    assert einstein_docs == {"albert_einstein", "niels_bohr"}
    assert bohr_docs == {"albert_einstein", "niels_bohr"}


def test_cross_document_collaboration_links_correct_entities(extraction_result):
    """Both `collaborated_with` relations must connect the merged
    Einstein and Bohr entities (not orphan duplicates)."""
    persons_by_name = {e["name"]: e for e in _persons(extraction_result)}
    einstein_id = persons_by_name["Albert Einstein"]["id"]
    bohr_id = persons_by_name["Niels Bohr"]["id"]

    collaborations = [
        r for r in extraction_result["relations"] if r["predicate"] == "collaborated_with"
    ]
    pairs = {
        (r["subject"], r["object"], r["source_doc"]) for r in collaborations
    }
    assert (einstein_id, bohr_id, "albert_einstein") in pairs
    assert (bohr_id, einstein_id, "niels_bohr") in pairs


def test_no_garbage_person_entities_from_overcapture(extraction_result):
    """Sentinel: no Person should contain phrases that only appear when
    the regex over-captures past a real name (e.g., 'on quantum',
    'and was', 'in 1903')."""
    overcapture_signatures = ("on quantum", "and was", "in 1903", "in 1912")
    bad = [
        e["name"]
        for e in _persons(extraction_result)
        if any(sig in e["name"].lower() for sig in overcapture_signatures)
    ]
    assert bad == [], f"over-captured Person names leaked through: {bad}"

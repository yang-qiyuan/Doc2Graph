from dataclasses import dataclass, field


@dataclass(slots=True)
class Mention:
    doc_id: str
    char_start: int
    char_end: int


@dataclass(slots=True)
class Entity:
    id: str
    name: str
    type: str
    source_doc: str
    mentions: list[Mention]
    aliases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Relation:
    id: str
    subject: str
    predicate: str
    object: str
    evidence: str
    source_doc: str
    char_start: int
    char_end: int
    confidence: float


@dataclass(slots=True)
class ExtractionResult:
    documents: list[dict]
    entities: list[Entity]
    relations: list[Relation]

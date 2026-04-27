# Web Search-Based Entity Disambiguation

## Overview

The entity fusion system now includes **web search disambiguation** to handle cases where there's insufficient information to confidently determine if two entities are the same.

## How It Works

### 1. Initial Fusion Analysis

When performing cross-document entity fusion in `validated` mode, Claude first analyzes entities based on:
- Entity names and aliases
- Birth/death dates or other temporal information
- Associated organizations, places, works
- Contextual clues from the documents

### 2. Confidence-Based Web Search Trigger

If the initial fusion analysis produces a **confidence score below 0.5** (configurable threshold), the system:

1. **Performs web search** for both entities using DuckDuckGo
2. **Gathers search results** (titles + snippets) about each entity
3. **Asks Claude to analyze** the web search results
4. **Makes final decision** based on web evidence

### 3. Web Search Analysis

The web search disambiguation:
- Searches for "{entity_name} {entity_type}" (e.g., "John Smith physicist")
- Retrieves top 3 search results per entity
- Provides Claude with search snippets to analyze
- Returns a decision with confidence and reasoning

## Configuration

### Environment Variables

```bash
# In extractor/.env

# Enable/disable web search (default: true)
USE_WEB_SEARCH=true

# Confidence threshold for triggering web search (default: 0.5)
# Lower values = more web searches
# Higher values = fewer web searches
WEB_SEARCH_THRESHOLD=0.5
```

### Code Usage

```python
from doc2graph_extractor.agent import ValidationAgent

agent = ValidationAgent()

# Perform fusion with web search enabled
merges = agent.cross_document_fusion(
    all_entities,
    use_web_search=True,        # Enable web search
    web_search_threshold=0.5    # Confidence threshold
)

# Disable web search
merges = agent.cross_document_fusion(
    all_entities,
    use_web_search=False
)
```

## Test Cases

### Case 1: Sufficient Information (No Web Search Needed)

**Input:**
- Document 1: "Marie Curie (7 November 1867 - 4 July 1934) was born in Warsaw..."
- Document 2: "Maria Sklodowska (1867 - 1934) was a Polish scientist. She studied at University of Paris..."

**Result:**
- **Confidence**: 0.99 (very high)
- **Web search**: NOT triggered
- **Reason**: Claude identified maiden vs married name, matching dates, shared university
- **Fusion**: ✓ Successful - "Maria Sklodowska" → "Marie Curie" with aliases

### Case 2: Ambiguous Abbreviated Names

**Input:**
- Document 1: "J. Smith (1920 - 2005) was a scientist."
- Document 2: "John Smith (15 March 1920 - 20 June 2005) was a British physicist..."

**Result:**
- **Confidence**: 0.85 (high)
- **Web search**: NOT triggered (above 0.5 threshold)
- **Reason**: Matching dates, abbreviation pattern, science context
- **Fusion**: ✓ Successful - "J. Smith" → "John Smith"

### Case 3: Truly Ambiguous (Web Search Triggered)

**Input:**
- Document 1: "Smith worked at Cambridge in 1950s."
- Document 2: "J. Smith was a researcher."

**Result:**
- **Confidence**: 0.3 (low - hypothetical)
- **Web search**: ✓ TRIGGERED
- **Search queries**: "Smith person", "J. Smith person"
- **Web decision**: Based on search result analysis

## Implementation Details

### Web Search Method

```python
def _web_search_entity(self, entity_name: str, entity_type: str, max_results: int = 3) -> str:
    """
    Perform web search using DuckDuckGo.
    Returns formatted summary of search results.
    """
```

### Disambiguation Method

```python
def _disambiguate_with_web_search(self, entity1: dict, entity2: dict) -> dict:
    """
    Uses web search + Claude analysis to determine if entities are the same.

    Returns:
        {
            'should_merge': bool,
            'confidence': float,
            'reason': str,
            'aliases': list[str]
        }
    """
```

### Integration with Fusion

The `cross_document_fusion()` method now:

1. Performs initial Claude-based fusion analysis
2. Separates high-confidence merges from uncertain pairs
3. For uncertain pairs (confidence < threshold):
   - Performs web search for both entities
   - Asks Claude to analyze search results
   - Makes final merge decision
4. Returns combined merge list

## Benefits

### 1. Handles Ambiguous Cases

- **Incomplete information**: Minimal biographical details
- **Abbreviations**: "J. Smith" vs "John Smith"
- **Name variations**: Different transliterations, maiden/married names
- **Common names**: Multiple people with same name

### 2. External Validation

- Uses authoritative web sources (Wikipedia, academic databases)
- Reduces hallucination risk
- Provides evidence-based decisions

### 3. Configurable Tradeoff

- **High threshold** (0.7-0.9): Fewer web searches, faster, may miss some fusions
- **Low threshold** (0.3-0.5): More web searches, slower, more thorough
- **Disabled** (use_web_search=False): Pure Claude-based fusion

## Performance Considerations

### Web Search Overhead

- Each web search adds ~2-3 seconds
- Limited to uncertain pairs only (most fusions don't need it)
- DuckDuckGo is free and doesn't require API keys

### Example Timing

For 30 Wikipedia documents:
- **Without web search**: ~2 minutes (mainly Neo4j writes)
- **With web search** (0 uncertain pairs): ~2 minutes (no overhead)
- **With web search** (3 uncertain pairs): ~2.2 minutes (+15 seconds)

## Future Enhancements

- **Caching**: Cache web search results to avoid duplicate searches
- **Multiple search engines**: Fallback to Google/Bing if DuckDuckGo fails
- **Entity-specific queries**: Smarter query construction based on entity type
- **Confidence calibration**: ML-based threshold optimization
- **Structured data sources**: Query Wikidata, DBpedia, ORCID directly

## Error Handling

Web search failures are graceful:
- Connection errors → assume no merge (conservative)
- Rate limiting → fall back to pure Claude analysis
- Parse errors → log warning, continue with other entities

## Dependencies

```bash
pip install duckduckgo-search
```

Included in standard installation.

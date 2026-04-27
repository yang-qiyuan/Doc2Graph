# Parallel Processing for Document Extraction

## Overview

The extraction pipeline now supports multiprocessing to process multiple documents in parallel using Python's `multiprocessing.Pool`. This can significantly speed up extraction when processing many documents.

## Implementation Details

### Architecture

- **Module-level worker function**: `_worker_extract_document()` processes a single document
- **Pool-based execution**: `multiprocessing.Pool` distributes documents across worker processes
- **Serialization**: Entities and relations are converted to dicts for inter-process communication
- **Normalization**: Cross-document normalization still happens after parallel extraction

### Code Changes

1. Added `multiprocessing` import
2. Created `_worker_extract_document()` at module level (required for pickling)
3. Modified `ExtractionPipeline.run()` to support both sequential and parallel modes
4. Results are serialized as dicts and reconstructed as Entity/Relation objects

## Configuration

### Environment Variables

**`USE_PARALLEL_EXTRACTION`** (default: `false`)
- Set to `true` to enable parallel processing
- Falls back to sequential mode for single documents

**`EXTRACTION_WORKERS`** (default: CPU count)
- Number of worker processes to spawn
- Recommended: 2-4 workers for typical workloads

### Examples

```bash
# Sequential processing (default)
python3 -m doc2graph_extractor.main < input.json

# Parallel processing with auto-detected CPU count
USE_PARALLEL_EXTRACTION=true python3 -m doc2graph_extractor.main < input.json

# Parallel processing with 2 workers
USE_PARALLEL_EXTRACTION=true EXTRACTION_WORKERS=2 python3 -m doc2graph_extractor.main < input.json
```

## Performance Characteristics

### When Parallel Helps

- **Many documents** (10+ documents): Process spawning overhead is amortized
- **Large documents**: Regex processing is CPU-bound, benefits from parallelization
- **CPU-bound workloads**: Multiple cores can be utilized

### When Sequential is Better

- **Few documents** (1-2 documents): Overhead exceeds benefits
- **Small documents**: Serialization/deserialization overhead dominates
- **Memory-constrained environments**: Each worker duplicates the pipeline

### Benchmark Results

**Small Workload Test** - 2 Wikipedia documents (Albert Einstein, Marie Curie):
- **Sequential**: 0.0317s
- **Parallel (2 workers)**: 0.2986s
- Sequential is faster due to process spawning overhead (~250ms)

**Isolated Python Pipeline Test** - 30 Wikipedia documents (1.9M characters total):
- **Sequential**: 0.5448s (55.06 docs/sec)
- **Parallel (2 workers)**: 0.5724s (52.41 docs/sec, 0.95x)
- **Parallel (4 workers)**: 0.4866s (61.65 docs/sec, **1.12x speedup**)
- **Parallel (8 workers)**: 0.6470s (46.37 docs/sec, 0.84x)

**Real-World Backend API Test** - 17 Wikipedia documents (1.08M characters total):
- **Sequential (regex mode)**: 119.30s (~2 minutes)
  - Python extraction: ~1s
  - Neo4j cloud writes: ~115s
  - Other overhead: ~3s
- **Parallel (4 workers, regex mode)**: 124.54s (~2 minutes)
  - No significant improvement due to Neo4j bottleneck

**Key Findings:**
- **Python extraction speedup**: 4 workers provide 12% speedup on extraction alone
- **Real-world bottleneck**: Neo4j cloud database writes dominate (98% of total time)
- **Recommended configuration**: 4 workers (good balance, no downside)
- **To improve end-to-end speed**: Optimize Neo4j writes or use local instance
- **Parallel extraction benefit**: Most visible with local Neo4j or in-memory storage

## Testing

### Test Suite

Three test scenarios in `tests/test_parallel_extraction.py`:

1. **`test_parallel_extraction_produces_same_results_as_sequential`**
   - Verifies identical output between modes
   - Uses 2 documents (Einstein, Curie)

2. **`test_parallel_extraction_with_two_workers`**
   - Tests explicit worker count configuration
   - Uses 2 documents (Newton, Galileo)

3. **`test_single_document_uses_sequential_mode`**
   - Verifies single-document fallback
   - Uses 1 document (Darwin)

### Running Tests

```bash
# Run parallel processing tests
cd extractor
python3 -m pytest tests/test_parallel_extraction.py -v

# Run all tests
python3 -m pytest tests/ -v
```

### Demo Script

Run `demo_parallel.py` to see side-by-side comparison:

```bash
cd extractor
python3 demo_parallel.py
```

Output shows:
- Sequential vs parallel timing
- Entity and relation counts
- Verification that results match
- Sample extracted entities

## Limitations

1. **Regex-only mode**: Parallel processing currently works only for `EXTRACTION_MODE=regex`
   - `validated` and `llm` modes still use sequential processing

2. **No shared state**: Each worker creates its own `ExtractionPipeline` instance
   - Memory overhead scales with worker count

3. **Serialization overhead**: Entity/Relation objects converted to dicts and back
   - Adds latency for small documents

4. **No progress tracking**: Pool execution doesn't provide per-document progress

## Future Enhancements

Potential improvements:

- Support parallel processing for `validated` mode
- Use `multiprocessing.Manager` for shared state
- Add progress callbacks for long-running jobs
- Implement chunked processing for very large document sets
- Add metrics for process pool utilization
- Consider asyncio for I/O-bound validation stages

## Backward Compatibility

Default behavior is unchanged:
- Sequential processing by default
- No breaking changes to API
- All existing tests pass
- Drop-in replacement for existing code

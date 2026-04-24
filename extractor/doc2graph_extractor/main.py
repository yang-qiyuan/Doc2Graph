from __future__ import annotations

import json
import sys

from .pipeline import ExtractionPipeline


def main() -> int:
    payload = json.load(sys.stdin)
    documents = payload.get("documents", [])
    pipeline = ExtractionPipeline()
    result = pipeline.run(documents)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

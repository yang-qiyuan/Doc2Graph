from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

from .pipeline import ExtractionPipeline

# Load .env file from the extractor directory
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(_env_path)


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

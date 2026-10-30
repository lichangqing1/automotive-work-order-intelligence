from __future__ import annotations

import argparse
import json
from pathlib import Path

from automotive.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the automotive intelligence platform")
    parser.add_argument("--rows", type=int, default=30_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    summary = run_pipeline(Path(__file__).resolve().parents[1], rows=args.rows, seed=args.seed)
    print(json.dumps(summary.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()

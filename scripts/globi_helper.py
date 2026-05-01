"""
globi_helper.py
===============
Fetches species interactions from the Global Biotic Interactions (GloBI) API
and prints them in a human-readable form. Use this as a research aid —
GloBI results are NOT automatically added to the curated CSV.

Workflow:
  1. Run this for a species of interest.
  2. Review the output. If a documented interaction looks credible and
     relevant to Sabangau, look up the original citation GloBI links to.
  3. Manually add the interaction to data/raw/sabangau/interactions_curated.csv,
     citing the original paper, NOT GloBI itself (GloBI is an aggregator).

Usage:
    python scripts/globi_helper.py "Pongo pygmaeus" --limit 50
    python scripts/globi_helper.py "Buceros rhinoceros" --type eats

Requirements: requests
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable

import requests

GLOBI_API = "https://api.globalbioticinteractions.org/interaction"


def fetch_globi(
    species: str, interaction_type: str | None = None, limit: int = 100,
) -> list[dict]:
    params = {
        "sourceTaxon": species,
        "type": "json.v2",
        "limit": str(limit),
    }
    if interaction_type:
        params["interactionType"] = interaction_type

    print(f"Querying GloBI for: {species}", file=sys.stderr)
    r = requests.get(GLOBI_API, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    # GloBI's json.v2 format: {"columns": [...], "data": [[row1], [row2], ...]}
    columns = data.get("columns", [])
    rows = data.get("data", [])
    return [dict(zip(columns, row)) for row in rows]


def summarise(records: list[dict]) -> None:
    if not records:
        print("No interactions found.")
        return

    print(f"\nFound {len(records)} interactions.\n")

    # Group by interaction type for readability
    by_type: dict[str, list[dict]] = {}
    for r in records:
        by_type.setdefault(r.get("interaction_type", "?"), []).append(r)

    for itype, rs in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        print(f"\n--- {itype} ({len(rs)} records) ---")
        for r in rs[:30]:  # cap per-type to keep output manageable
            src = r.get("source_taxon_name", "?")
            tgt = r.get("target_taxon_name", "?")
            ref = r.get("study_citation", "?")[:80]
            print(f"  {src} -> {tgt}")
            print(f"    citation: {ref}")
        if len(rs) > 30:
            print(f"  ... and {len(rs) - 30} more")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Query GloBI for species interactions (research aid only).",
    )
    parser.add_argument("species", help="Scientific name, e.g. 'Pongo pygmaeus'")
    parser.add_argument(
        "--type", dest="interaction_type", default=None,
        help="Filter by interaction type, e.g. 'eats', 'pollinates', 'preysOn'",
    )
    parser.add_argument(
        "--limit", type=int, default=100,
        help="Max records to return (default 100)",
    )
    args = parser.parse_args()

    try:
        records = fetch_globi(args.species, args.interaction_type, args.limit)
    except requests.RequestException as e:
        print(f"GloBI request failed: {e}", file=sys.stderr)
        sys.exit(2)

    summarise(records)

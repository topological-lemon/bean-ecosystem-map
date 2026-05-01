"""
globi_fetch.py
==============
Bulk-fetch GloBI interactions for every species in our roster.

This is the PRIMARY interaction data source for the Sabangau network.
The curated CSV (interactions_curated.csv) is layered on top as overrides
and supplements via interactions_harmonisation.py.

Strategy:
  - Query GloBI's REST API for each species in our roster, both as source
    and as target.
  - Save raw response with full provenance (citation, source dataset URL).
  - Subsequent steps (globi_filter.py) apply relevance heuristics.

Why API and not Zenodo dump:
  - The full Zenodo dump (~10 GB) is overkill for 30 species.
  - The API gives us the same records with built-in taxonomic resolution
    (handles synonyms, e.g. matches "Cynocephalus variegatus" to current
    "Galeopterus variegatus").
  - For reproducibility we record the API query date; if we want a stable
    snapshot we can swap to the Zenodo dump later.

Usage:
    python scripts/globi_fetch.py \
        --species data/processed/sabangau/species.json \
        --output data/raw/sabangau/globi_pull.tsv

Requirements: requests
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

GLOBI_API = "https://api.globalbioticinteractions.org/interaction"

# Fields we care about. GloBI's current json.v2 returns a flat list of dicts
# (the older {columns, data} matrix shape is gone). We keep a stable subset
# of the available scalar fields. Citation provenance is thinner than it
# used to be — only `study` and `study_title` survive, and both are often
# null. If we ever need richer per-record citations we can switch to the
# Zenodo bulk dump, which preserves study_doi/study_url.
KEEP_FIELDS = [
    "source_taxon_name", "source_taxon_external_id", "source_taxon_path",
    "interaction_type",
    "target_taxon_name", "target_taxon_external_id", "target_taxon_path",
    "latitude", "longitude",
    "study", "study_title",
]


def fetch_for_species(
    scientific_name: str, role: str, limit: int = 5000,
) -> list[dict]:
    """Fetch interactions where species is source (role='source') or target.

    GloBI accepts trinomials like 'Pongo pygmaeus wurmbii' but its taxonomic
    backbone may not always have them — falls back to binomial gracefully.
    We try the trinomial first, then strip to binomial if the result is empty.
    """
    names_to_try = [scientific_name]
    parts = scientific_name.split()
    if len(parts) == 3:
        names_to_try.append(" ".join(parts[:2]))  # binomial fallback

    all_records = []
    for name in names_to_try:
        param_key = "sourceTaxon" if role == "source" else "targetTaxon"
        params = {
            param_key: name,
            "type": "json.v2",
            "limit": str(limit),
        }
        try:
            r = requests.get(GLOBI_API, params=params, timeout=60)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  WARN: fetch failed for {name} ({role}): {e}", file=sys.stderr)
            continue

        data = r.json()
        # Current GloBI json.v2 returns a list of dicts directly (no columns/data
        # wrapper). Defensive: tolerate either shape in case the API flips back.
        if isinstance(data, dict) and "data" in data and "columns" in data:
            columns = data.get("columns", [])
            records = [dict(zip(columns, row)) for row in data.get("data", [])]
        elif isinstance(data, list):
            records = data
        else:
            records = []

        for rec in records:
            if not isinstance(rec, dict):
                continue
            rec["_query_role"] = role
            rec["_query_name"] = name
            rec["_query_input_taxon"] = scientific_name
            all_records.append(rec)

        # Warn if a single API call hit the ceiling — likely truncated, will
        # need pagination (sourceTaxon + skip/offset) to get the rest.
        if len(records) >= limit:
            print(
                f"  WARN: {name} ({role}) returned {len(records)} records "
                f"== limit ({limit}). Result is likely truncated; consider "
                f"paginating or raising --limit.",
                file=sys.stderr,
            )

        if all_records:
            break  # got results from trinomial; no need for binomial fallback

        time.sleep(0.5)  # polite pause between fallback attempts

    return all_records


def run(species_path: Path, output_path: Path) -> int:
    with open(species_path) as f:
        species_list = json.load(f)

    print(f"Loaded {len(species_list)} species from roster")
    print(f"Pulling GloBI interactions (this takes ~5-10 minutes)...")
    print(f"Query date: {datetime.now(timezone.utc).isoformat()}")

    all_records = []
    for sp in species_list:
        name = sp["scientific_name"]
        # Skip the abstract functional groups; GloBI won't have them
        if name in {"Ceratosolen spp.", "Mycorrhizal community"}:
            print(f"  skip (functional group): {name}")
            continue

        print(f"  {name}", end=" ", flush=True)
        records = []
        for role in ("source", "target"):
            records.extend(fetch_for_species(name, role))
            time.sleep(0.5)  # be polite to the API

        # Drop unrelated fields, tag with query metadata
        cleaned = []
        for r in records:
            cleaned_r = {k: r.get(k, "") for k in KEEP_FIELDS}
            cleaned_r["_query_role"] = r.get("_query_role", "")
            cleaned_r["_query_name"] = r.get("_query_name", "")
            cleaned_r["_query_input_taxon"] = r.get("_query_input_taxon", "")
            cleaned.append(cleaned_r)

        all_records.extend(cleaned)
        print(f"-> {len(cleaned)} records")

    # Deduplicate on the (source, type, target, study) tuple — the same
    # interaction is sometimes returned twice when both species are in our roster
    # (once as source-query, once as target-query).
    seen = set()
    deduped = []
    for r in all_records:
        key = (
            r.get("source_taxon_name", ""),
            r.get("interaction_type", ""),
            r.get("target_taxon_name", ""),
            r.get("study_citation", "")[:120],
        )
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = KEEP_FIELDS + ["_query_role", "_query_name", "_query_input_taxon"]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for r in deduped:
            writer.writerow(r)

    print(f"\nWrote {len(deduped)} unique records to {output_path}")
    print(f"  ({len(all_records) - len(deduped)} duplicates dropped)")

    # Quick coverage report
    by_input = {}
    for r in deduped:
        by_input.setdefault(r["_query_input_taxon"], 0)
        by_input[r["_query_input_taxon"]] += 1
    print("\nGloBI coverage by species (records returned):")
    for sp, count in sorted(by_input.items(), key=lambda kv: -kv[1]):
        print(f"  {sp:40s} {count:5d}")

    zero = [sp["scientific_name"] for sp in species_list
            if sp["scientific_name"] not in by_input
            and sp["scientific_name"] not in {"Ceratosolen spp.", "Mycorrhizal community"}]
    if zero:
        print(f"\n{len(zero)} species with NO GloBI records (will need curated entries):")
        for sp in zero:
            print(f"  {sp}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch GloBI interactions for every species in roster.",
    )
    parser.add_argument(
        "--species", default="data/processed/sabangau/species.json",
        type=Path,
    )
    parser.add_argument(
        "--output", default="data/raw/sabangau/globi_pull.tsv",
        type=Path,
    )
    args = parser.parse_args()
    sys.exit(run(args.species, args.output))

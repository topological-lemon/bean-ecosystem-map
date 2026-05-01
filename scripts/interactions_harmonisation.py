"""
interactions_harmonisation.py (v2)
==================================
Merge GloBI-derived interactions with curated overrides/supplements,
validate against species roster, emit canonical interactions.json.

Merge logic:
  - Start with globi_filtered.json as the base.
  - For each row in interactions_curated.csv:
      action='add'      -> append (warn if duplicate of existing GloBI key)
      action='override' -> replace any existing entry with the same
                           (src, layer, interaction_type, tgt) key
      action='exclude'  -> remove any matching entry from the base
  - Validate, deduplicate, emit.

Provenance is preserved: every output record knows whether it came from
GloBI, from curation, or was overridden, so the writeup can cite honestly.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

VALID_LAYERS = {
    "trophic", "mutualism_pollination", "mutualism_dispersal",
    "facilitation", "competition", "parasitism",
}


def load_species(path: Path) -> dict[str, dict]:
    with open(path) as f:
        return {r["scientific_name"]: r for r in json.load(f)}


def load_globi(path: Path) -> list[dict]:
    if not path.exists():
        print(f"WARN: {path} not found; proceeding without GloBI base.",
              file=sys.stderr)
        return []
    with open(path) as f:
        records = json.load(f)
    for r in records:
        r["_provenance"] = "globi"
    return records


def load_curated(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(
            (line for line in f if not line.lstrip().startswith("#") and line.strip())
        )
        for row in reader:
            rows.append({k: (v.strip() if isinstance(v, str) else v)
                         for k, v in row.items()})
    return rows


def make_key(r: dict) -> tuple:
    return (
        r["source_scientific_name"],
        r["layer"],
        r["interaction_type"],
        r["target_scientific_name"],
    )


def merge(globi: list[dict], curated_rows: list[dict],
          species: dict[str, dict]) -> tuple[list[dict], list[str]]:
    errors: list[str] = []

    # Index GloBI base by key
    base = {make_key(r): r for r in globi}

    add_count = override_count = exclude_count = 0
    skipped = 0

    for idx, row in enumerate(curated_rows, start=1):
        action = row.get("action", "").lower()
        src = row.get("source_scientific_name", "")
        tgt = row.get("target_scientific_name", "")
        layer = row.get("layer", "")
        itype = row.get("interaction_type", "")

        if src and src not in species:
            errors.append(f"curated row {idx}: source '{src}' not in roster")
            skipped += 1
            continue
        if tgt and tgt not in species:
            errors.append(f"curated row {idx}: target '{tgt}' not in roster")
            skipped += 1
            continue
        if layer and layer not in VALID_LAYERS:
            errors.append(f"curated row {idx}: layer '{layer}' invalid")
            skipped += 1
            continue

        key = (src, layer, itype, tgt)

        if action == "exclude":
            if key in base:
                del base[key]
                exclude_count += 1
            else:
                errors.append(f"curated row {idx}: 'exclude' for nonexistent key {key}")
            continue

        try:
            strength = float(row.get("strength", "0"))
        except ValueError:
            errors.append(f"curated row {idx}: strength not numeric")
            skipped += 1
            continue

        new_record = {
            "source_scientific_name": src,
            "target_scientific_name": tgt,
            "layer": layer,
            "interaction_type": itype,
            "strength": round(strength, 3),
            "evidence": row.get("evidence", ""),
            "doi_or_url": row.get("doi_or_url", ""),
            "notes": row.get("notes", ""),
            "_provenance": "curated" if action == "add" else "curated_override",
        }

        if action == "add":
            if key in base:
                errors.append(
                    f"curated row {idx}: 'add' duplicates existing key {key}; "
                    "use 'override' instead"
                )
            base[key] = new_record
            add_count += 1
        elif action == "override":
            base[key] = new_record
            override_count += 1
        else:
            errors.append(f"curated row {idx}: unknown action '{action}'")
            skipped += 1

    print(f"\nMerge summary:")
    print(f"  GloBI base records:     {len(globi)}")
    print(f"  Curated 'add':          {add_count}")
    print(f"  Curated 'override':     {override_count}")
    print(f"  Curated 'exclude':      {exclude_count}")
    print(f"  Curated rows skipped:   {skipped}")
    print(f"  Final records:          {len(base)}")

    return list(base.values()), errors


def assign_ids_and_finalise(records: list[dict],
                             species: dict[str, dict]) -> list[dict]:
    final = []
    for idx, r in enumerate(records, start=1):
        sp_src = species[r["source_scientific_name"]]
        sp_tgt = species[r["target_scientific_name"]]
        final.append({
            "id": f"int_{idx:04d}",
            "source_species_id": sp_src["id"],
            "target_species_id": sp_tgt["id"],
            "source_scientific_name": r["source_scientific_name"],
            "target_scientific_name": r["target_scientific_name"],
            "layer": r["layer"],
            "interaction_type": r["interaction_type"],
            "strength": r["strength"],
            "evidence": r.get("evidence", ""),
            "doi_or_url": r.get("doi_or_url", ""),
            "notes": r.get("notes", ""),
            "provenance": r.get("_provenance", "unknown"),
            "globi_study_citation": r.get("globi_study_citation", ""),
            "globi_record_count": r.get("globi_record_count"),
        })
    return final


def report(records: list[dict], species: dict[str, dict]) -> None:
    print("\n" + "=" * 60)
    print("Final interaction summary")
    print("=" * 60)

    by_provenance = Counter(r["provenance"] for r in records)
    print("\nProvenance:")
    for k, v in by_provenance.most_common():
        print(f"  {k:25s} {v:5d}")

    by_layer = Counter(r["layer"] for r in records)
    print("\nBy layer:")
    for k, v in sorted(by_layer.items(), key=lambda kv: -kv[1]):
        print(f"  {k:30s} {v:5d}")

    sp_count: dict[str, int] = defaultdict(int)
    for r in records:
        sp_count[r["source_scientific_name"]] += 1
        sp_count[r["target_scientific_name"]] += 1

    orphans = sorted(set(species.keys()) - set(sp_count.keys()))
    if orphans:
        print(f"\n{len(orphans)} species with NO interactions:")
        for sp in orphans:
            print(f"  {sp}")
    else:
        print("\nAll species have at least one interaction.")


def run(species_path: Path, globi_path: Path, curated_path: Path,
        output_path: Path, strict: bool = True) -> int:
    species = load_species(species_path)
    globi = load_globi(globi_path)
    curated = load_curated(curated_path)

    merged, errors = merge(globi, curated, species)

    if errors:
        print(f"\n{len(errors)} validation issue(s):")
        for e in errors:
            print(f"  ERROR: {e}")
        if strict:
            print("\nFailed validation. Fix and re-run.")
            return 1

    final = assign_ids_and_finalise(merged, species)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(final, f, indent=2)

    report(final, species)
    print(f"\nWrote {len(final)} interactions to {output_path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--species", type=Path,
                        default="data/processed/sabangau/species.json")
    parser.add_argument("--globi", type=Path,
                        default="data/raw/sabangau/globi_filtered.json")
    parser.add_argument("--curated", type=Path,
                        default="data/raw/sabangau/interactions_curated.csv")
    parser.add_argument("--output", type=Path,
                        default="data/processed/sabangau/interactions.json")
    parser.add_argument("--lax", action="store_true")
    args = parser.parse_args()
    sys.exit(run(args.species, args.globi, args.curated, args.output,
                 strict=not args.lax))

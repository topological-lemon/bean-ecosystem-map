"""
globi_filter.py
===============
Apply relevance filtering to raw GloBI pull, producing a clean JSON of
interactions ready to merge with the curated CSV.

Filters applied:
  1. Both source AND target must be in our species roster (no edges to species
     we don't model). Uses our species roster's scientific_name plus a small
     synonym map to handle taxonomy mismatches.
  2. Map GloBI's interaction_type vocabulary to our layer/interaction_type
     taxonomy. Records with unmappable types are dropped with a warning.
  3. Optional region filter: drop records explicitly tagged outside SE Asia
     when the same interaction has SE Asia evidence elsewhere; keep records
     with no locality (treated as 'global / unknown context').
  4. Drop records flagged as captivity/lab studies based on study_citation
     keywords (e.g. 'zoo', 'captive', 'in vitro').

Outputs a JSON list of records with provenance fields preserved so every
interaction can be traced to its original source paper.

Usage:
    python scripts/globi_filter.py \
        --species data/processed/sabangau/species.json \
        --globi-tsv data/raw/sabangau/globi_pull.tsv \
        --output data/raw/sabangau/globi_filtered.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path


# Map GloBI interaction types -> our (layer, interaction_type) tuples.
# GloBI uses OBO Relations Ontology (RO) terms. List based on common
# values observed in tropical mammal/plant data.
# Reference: https://www.globalbioticinteractions.org/interactionTypes.html
GLOBI_TYPE_MAP: dict[str, tuple[str, str]] = {
    # Trophic
    "eats":                  ("trophic", "consumes_fruit"),  # default, refine below
    "preysOn":               ("trophic", "preys_on"),
    "killsAndEats":          ("trophic", "preys_on"),
    "kills":                 ("trophic", "preys_on"),
    "eatsCarcassOf":         ("trophic", "opportunistic_predation"),
    # Mutualism — pollination
    "pollinates":            ("mutualism_pollination", "primary_pollinates"),
    "pollinatedBy":          ("mutualism_pollination", "primary_pollinates"),  # direction handled in build
    "visitsFlowersOf":       ("mutualism_pollination", "occasional_pollinates"),
    "flowersVisitedBy":      ("mutualism_pollination", "occasional_pollinates"),
    # Mutualism — dispersal
    "disperses":             ("mutualism_dispersal", "seeds_dispersed_by"),
    "dispersalVectorOf":     ("mutualism_dispersal", "seeds_dispersed_by"),
    "hasDispersalVector":    ("mutualism_dispersal", "seeds_dispersed_by"),
    # Habitat / facilitation
    "providesNutrientsFor":  ("facilitation", "enables_seedling_establishment"),
    "symbiontOf":            ("facilitation", "enables_seedling_establishment"),
    "roostOf":               ("facilitation", "provides_roost_habitat"),
    "hasRoost":              ("facilitation", "provides_roost_habitat"),  # flip in code
    # Direction-flipped (target eats source etc.) handled in code
    "eatenBy":               ("trophic", "consumes_fruit"),  # flip in code
    "preyedUponBy":          ("trophic", "preys_on"),         # flip in code
    # Intentionally NOT mapped (would route here otherwise — see drop log):
    #   hostOf / hasHost      -> mostly host-pathogen records, not facilitation
    #   parasiteOf / pathogenOf -> parasitism layer not modelled in v1
    #   mutualistOf           -> too vague without per-record review
}

# Taxonomic synonyms — old name in GloBI -> current name in our roster.
# Applies to ALL interaction types (subspecies / synonym → species is unambiguous).
# Add to this when globi_fetch coverage report shows expected species missing.
SYNONYM_MAP: dict[str, str] = {
    # Pre-pivot baseline
    "Cynocephalus variegatus":          "Galeopterus variegatus",
    "Hylobates agilis albibarbis":      "Hylobates albibarbis",
    "Cervus unicolor":                  "Rusa unicolor",
    # Pongo (we treat all Bornean orangutan records as our wurmbii subspecies)
    "Pongo pygmaeus":                   "Pongo pygmaeus wurmbii",
    "Pongo pygmaeus morio":             "Pongo pygmaeus wurmbii",
    "Pongo pygmaeus pygmaeus":          "Pongo pygmaeus wurmbii",
    # Subspecies → species
    "Helarctos malayanus malayanus":    "Helarctos malayanus",
    "Macaca fascicularis fascicularis": "Macaca fascicularis",
    "Buceros rhinoceros borneoensis":   "Buceros rhinoceros",
    "Buceros rhinoceros rhinoceros":    "Buceros rhinoceros",
    "Anthracoceros albirostris convexus":    "Anthracoceros albirostris",
    "Anthracoceros albirostris albirostris": "Anthracoceros albirostris",
    "Pteropus vampyrus natunae":        "Pteropus vampyrus",
    "Pteropus vampyrus lanensis":       "Pteropus vampyrus",
    "Rusa unicolor cambojensis":        "Rusa unicolor",
    "Rusa unicolor unicolor":           "Rusa unicolor",
    "Paradoxurus hermaphroditus javanica":      "Paradoxurus hermaphroditus",
    "Paradoxurus hermaphroditus philippinensis": "Paradoxurus hermaphroditus",
    "Paradoxurus musangus":             "Paradoxurus hermaphroditus",
    "Hylobates agilis":                 "Hylobates albibarbis",
    "Apis dorsata breviligula":         "Apis dorsata",
}


# ---------------------------------------------------------------------------
# Genus-level aggregation (lossy — only applied for whitelisted interaction
# types where congenerics are ecologically interchangeable in our network).
#
# Rationale: GloBI is rich on Ficus benjamina (1000+ records) plus dozens of
# Sundaland congeners, but our network only models three Ficus species. For
# trophic / pollination / dispersal interactions, congeneric figs are
# functionally equivalent dispersers/food/pollinator hosts in this forest, so
# we fold them into the roster representative. We do NOT aggregate parasitism
# or disease records — those are taxon-specific.
#
# Travis: every aggregation event is reported at run-end so the writeup can
# document this honestly. See model_assumptions.md.
# ---------------------------------------------------------------------------
GENUS_AGGREGATION_MAP: dict[str, str] = {
    # Ficus → Ficus benjamina (most-recorded roster fig; serves as Sundaland
    # fig genus representative for trophic/dispersal/pollination edges).
    **{f: "Ficus benjamina" for f in (
        "Ficus crassiramea", "Ficus altissima", "Ficus virens", "Ficus variegata",
        "Ficus obscura", "Ficus stricta", "Ficus sumatrana", "Ficus glandulifera",
        "Ficus subulata", "Ficus drupacea", "Ficus racemosa", "Ficus globbosa",
        "Ficus pellucidopunctata", "Ficus binnendijkii", "Ficus maitin",
        "Ficus sundaica", "Ficus vilosa", "Ficus lamponga", "Ficus consociata",
        "Ficus xylophylla", "Ficus chartacea", "Ficus fistulosa", "Ficus subcordata",
        "Ficus heteropleura", "Ficus caulocarpa", "Ficus parietalis",
        "Ficus sagittata", "Ficus pisocarpa", "Ficus nervosa", "Ficus minahassae",
        "Ficus tsjakela", "Ficus sarmentosa", "Ficus tinctoria", "Ficus rumphii",
        "Ficus amplissima", "Ficus microcarpa", "Ficus rubra", "Ficus lowii",
    )},
    # Palaquium → Palaquium leiocarpum (Sundaland Sapotaceae representative).
    **{p: "Palaquium leiocarpum" for p in (
        "Palaquium obotatum", "Palaquium rostratum", "Palaquium gutta",
    )},
    # Diospyros → Diospyros bantamensis (Sundaland congeners only — see drop list).
    **{d: "Diospyros bantamensis" for d in (
        "Diospyros lanceifolia", "Diospyros singaporensis",
        "Diospyros cauliflora", "Diospyros discocalyxe",
    )},
    # Shorea → Shorea balangeran (Sundaland dipterocarp peer in canopy role).
    "Shorea curtisii": "Shorea balangeran",
}

# Biogeographic outliers — congenerics whose interactions are NOT
# transferable to our Sundaland roster. When a whitelisted interaction
# surfaces these names we drop the record silently (no near-match log spam).
GENUS_AGGREGATION_DROP: set[str] = {
    # Out-of-Sundaland Ficus
    "Ficus carica", "Ficus religiosa", "Ficus benghalensis",
    "Ficus macrophylla", "Ficus pseudopalma", "Ficus retusa", "Ficus palmata",
    # Out-of-Sundaland Diospyros (Indian + East Asian)
    "Diospyros melanoxylon", "Diospyros malabarica", "Diospyros kaki",
    "Diospyros lotus",
}

# GloBI interaction types eligible for genus-level aggregation. Trophic and
# mutualism interactions tend to be conserved across congeners; parasitism /
# disease / "interactsWith" are taxon-specific or too vague to aggregate.
GENUS_AGGREGATABLE_TYPES: set[str] = {
    "eats", "eatenBy",
    "pollinates", "pollinatedBy",
    "visitsFlowersOf", "flowersVisitedBy",
    "hasDispersalVector", "dispersalVectorOf",
    "mutualistOf",
}

# Keywords that suggest the record is from a captive/lab study, not field ecology.
EXCLUDE_KEYWORDS = (
    "zoo ", "zoological", "captive", "captivity", "in vitro",
    "laboratory study", "lab-reared", "aquarium",
)


def load_species_roster(path: Path) -> set[str]:
    with open(path) as f:
        records = json.load(f)
    return {r["scientific_name"] for r in records}


def normalise_name(name: str, roster: set[str]) -> str | None:
    """Return the canonical name from our roster, or None if not present.

    Tries: exact match -> synonym map -> binomial-only match for trinomials in roster.
    """
    if not name:
        return None
    if name in roster:
        return name
    if name in SYNONYM_MAP and SYNONYM_MAP[name] in roster:
        return SYNONYM_MAP[name]
    # If roster has a trinomial like 'Pongo pygmaeus wurmbii' and GloBI gave us
    # the binomial 'Pongo pygmaeus', accept it
    for canonical in roster:
        if canonical.startswith(name + " "):
            return canonical
    return None


def is_captive_study(citation: str) -> bool:
    if not citation:
        return False
    lower = citation.lower()
    return any(kw in lower for kw in EXCLUDE_KEYWORDS)


def best_citation(row: dict) -> str:
    """Return the best-available citation-ish string from a GloBI TSV row.

    GloBI's current json.v2 only exposes `study` and `study_title`, both
    frequently the literal string 'null' or an empty value. We coalesce them
    and treat 'null'/'none' (case-insensitive) as missing.
    """
    for key in ("study", "study_title"):
        v = (row.get(key) or "").strip()
        if v and v.lower() not in {"null", "none"}:
            return v
    return ""


def best_locality(row: dict) -> str:
    """Lat/long stand-in for the dropped `locality` field.

    GloBI no longer ships a free-text locality string in its API response;
    we keep coordinates instead so curators can still tell e.g. tropical
    SE Asia from a North American sample.
    """
    lat = (row.get("latitude") or "").strip()
    lon = (row.get("longitude") or "").strip()
    if lat and lon:
        return f"{lat}, {lon}"
    return ""


def is_silent_drop_taxon(name: str, itype: str) -> bool:
    """True if `name` should be silently dropped under a whitelisted itype.

    Used to suppress near-match log spam for biogeographic outliers we've
    explicitly decided not to aggregate (e.g. Ficus carica is well-recorded
    in GloBI from Mediterranean studies and would otherwise flood the
    near-match log against our Sundaland Ficus roster).
    """
    return itype in GENUS_AGGREGATABLE_TYPES and name in GENUS_AGGREGATION_DROP


def genus_aggregate(name: str, itype: str) -> str | None:
    """If `name` is an aggregatable congener under `itype`, return the roster
    representative. Otherwise return None (caller falls through to drop)."""
    if itype not in GENUS_AGGREGATABLE_TYPES:
        return None
    return GENUS_AGGREGATION_MAP.get(name)


def find_near_matches(name: str, roster: set[str]) -> list[str]:
    """Return roster species whose name shares a token of length >=4 with `name`.

    Used to surface possible synonym mismatches: GloBI may return 'Pongo' alone
    or 'Cervus unicolor' (a synonym), and we want Travis to see those rather
    than silently dropping them. Genus-only or one-token matches are typical.
    """
    if not name:
        return []
    name_tokens = {tok.lower() for tok in name.split() if len(tok) >= 4}
    if not name_tokens:
        return []
    matches = []
    for canonical in roster:
        canonical_tokens = {tok.lower() for tok in canonical.split() if len(tok) >= 4}
        if name_tokens & canonical_tokens:
            matches.append(canonical)
    return sorted(matches)


def map_interaction(itype: str, src_name: str, tgt_name: str) -> tuple[str, str, str, str] | None:
    """Return (layer, interaction_type, src, tgt) or None if unmappable.

    Some GloBI types are direction-flipped relative to our schema; this
    function handles those flips so the source is always the 'agent' species.
    """
    if itype not in GLOBI_TYPE_MAP:
        return None
    layer, our_type = GLOBI_TYPE_MAP[itype]

    # Direction handling for inverse types
    if itype in ("eatenBy", "preyedUponBy", "pollinatedBy", "flowersVisitedBy",
                 "hasDispersalVector", "hasRoost"):
        return (layer, our_type, tgt_name, src_name)
    return (layer, our_type, src_name, tgt_name)


def estimate_strength(layer: str, itype: str) -> float:
    """Default strength when we have one GloBI record. Curated overrides
    can adjust this to literature-informed values."""
    defaults = {
        ("trophic", "preys_on"): 0.5,
        ("trophic", "opportunistic_predation"): 0.3,
        ("trophic", "consumes_fruit"): 0.6,
        ("trophic", "consumes_leaves"): 0.5,
        ("trophic", "consumes_seeds"): 0.5,
        ("mutualism_pollination", "primary_pollinates"): 0.6,
        ("mutualism_pollination", "occasional_pollinates"): 0.4,
        ("mutualism_dispersal", "seeds_dispersed_by"): 0.5,
        ("facilitation", "provides_nesting_habitat"): 0.5,
        ("facilitation", "enables_seedling_establishment"): 0.6,
    }
    return defaults.get((layer, itype), 0.4)


def run(species_path: Path, globi_tsv: Path, output_path: Path) -> int:
    roster = load_species_roster(species_path)
    print(f"Roster: {len(roster)} species")

    raw_records = []
    with open(globi_tsv, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            raw_records.append(row)
    print(f"Raw GloBI records: {len(raw_records)}")

    kept: list[dict] = []
    drop_stats: Counter = Counter()
    # (raw_globi_name → roster_canonical) record counts for genus aggregation,
    # broken out separately so we can print a transparency report at end of run.
    aggregation_stats: Counter = Counter()
    # (raw_globi_name, suggested_roster_match) pairs already logged — avoids
    # flooding stderr when the same near-match recurs across many records.
    seen_near_matches: set[tuple[str, str]] = set()

    def _log_near_matches(raw_name: str, side: str, itype: str) -> None:
        suggestions = find_near_matches(raw_name, roster)
        for match in suggestions:
            key = (raw_name, match)
            if key in seen_near_matches:
                continue
            seen_near_matches.add(key)
            print(
                f"NEAR-MATCH: globi {side}='{raw_name}' partially matches roster "
                f"'{match}' (interaction_type={itype}). "
                f"Add to SYNONYM_MAP if appropriate.",
                file=sys.stderr,
            )

    for r in raw_records:
        src_raw = r.get("source_taxon_name", "")
        tgt_raw = r.get("target_taxon_name", "")
        itype = r.get("interaction_type", "")
        citation = best_citation(r)

        src = normalise_name(src_raw, roster)
        # Genus aggregation only fires when the exact/synonym match fails AND
        # the interaction type is on the whitelist (trophic + mutualism, not
        # parasitism/disease). Silent drops for biogeographic outliers go via
        # GENUS_AGGREGATION_DROP and bypass near-match logging.
        if not src:
            if is_silent_drop_taxon(src_raw, itype):
                drop_stats["non-Sundaland congener (silent)"] += 1
                continue
            agg = genus_aggregate(src_raw, itype)
            if agg:
                src = agg
                aggregation_stats[(src_raw, agg)] += 1

        tgt = normalise_name(tgt_raw, roster)
        if not tgt:
            if is_silent_drop_taxon(tgt_raw, itype):
                drop_stats["non-Sundaland congener (silent)"] += 1
                continue
            agg = genus_aggregate(tgt_raw, itype)
            if agg:
                tgt = agg
                aggregation_stats[(tgt_raw, agg)] += 1

        if not src:
            drop_stats["source not in roster"] += 1
            _log_near_matches(src_raw, "source", itype)
            continue
        if not tgt:
            drop_stats["target not in roster"] += 1
            _log_near_matches(tgt_raw, "target", itype)
            continue
        if src == tgt:
            drop_stats["self-loop"] += 1
            continue
        if is_captive_study(citation):
            drop_stats["captive/lab study"] += 1
            continue

        mapped = map_interaction(itype, src, tgt)
        if mapped is None:
            drop_stats[f"unmappable type: {itype}"] += 1
            continue
        layer, our_type, real_src, real_tgt = mapped

        kept.append({
            "source_scientific_name": real_src,
            "target_scientific_name": real_tgt,
            "layer": layer,
            "interaction_type": our_type,
            "strength": estimate_strength(layer, our_type),
            "evidence": "globi_aggregated",
            "doi_or_url": "https://www.globalbioticinteractions.org/",
            "globi_study_citation": citation[:300],
            "globi_locality": best_locality(r),
            "notes": (
                f"GloBI-derived. Original source: {citation[:150] or '(no citation supplied by GloBI)'}. "
                "Verify against primary literature before relying on for keystone claims."
            ),
        })

    # Collapse to one representative record per (src, layer, type, tgt) edge,
    # but keep the record COUNT so we can fold weight-of-evidence into the
    # strength. Without this, 30 GloBI records supporting an edge produce the
    # same strength as 1 — which masks the contribution of genus aggregation.
    edge_first: dict[tuple, dict] = {}
    edge_count: Counter = Counter()
    for r in kept:
        key = (
            r["source_scientific_name"], r["layer"],
            r["interaction_type"], r["target_scientific_name"],
        )
        edge_count[key] += 1
        if key not in edge_first:
            edge_first[key] = r

    final: list[dict] = []
    for key, rec in edge_first.items():
        count = edge_count[key]
        # Base strength was set by estimate_strength(layer, type) when the
        # record was appended. Apply a log-scaled boost so heavily-evidenced
        # edges land closer to 1.0. Caps at 1.0 to keep the [0,1] schema.
        base = rec["strength"]
        boosted = min(1.0, base + 0.05 * math.log(count))
        new_rec = dict(rec)
        new_rec["strength"] = round(boosted, 3)
        new_rec["globi_record_count"] = count
        final.append(new_rec)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(final, f, indent=2)

    # Surface unmapped GloBI interaction types as stderr INFO lines so we
    # can audit what we're dropping and decide whether to extend the map.
    unmapped_prefix = "unmappable type: "
    unmapped_total = 0
    for reason, count in drop_stats.items():
        if reason.startswith(unmapped_prefix):
            itype_name = reason[len(unmapped_prefix):]
            print(
                f"INFO: dropping {count} records of type '{itype_name}' "
                f"(not in GLOBI_TYPE_MAP).",
                file=sys.stderr,
            )
            unmapped_total += count
    if unmapped_total:
        print(
            f"INFO: {unmapped_total} records dropped in total due to "
            f"unmapped interaction types.",
            file=sys.stderr,
        )

    print(f"\nKept after filtering: {len(final)} unique interactions")
    print(f"({len(kept) - len(final)} duplicates collapsed)")
    print("\nDrop reasons:")
    for reason, count in drop_stats.most_common():
        print(f"  {reason:50s} {count:6d}")

    by_layer = Counter(r["layer"] for r in final)
    print("\nBy layer:")
    for layer, count in sorted(by_layer.items(), key=lambda kv: -kv[1]):
        print(f"  {layer:30s} {count:5d}")

    if aggregation_stats:
        print("\n" + "=" * 60)
        print("GENUS-LEVEL AGGREGATION REPORT")
        print("=" * 60)
        print("Congeneric records folded into roster representatives "
              "(only for whitelisted trophic / mutualism interaction types).")
        # Roll-up by canonical roster representative
        per_canonical: Counter = Counter()
        for (raw, canonical), count in aggregation_stats.items():
            per_canonical[canonical] += count
        print("\nSummary (records → roster representative):")
        for canonical, count in per_canonical.most_common():
            print(f"  {count:5d} records mapped to {canonical}")
        # Per-source-name detail for the writeup
        print("\nDetail (raw GloBI taxon → roster representative, record count):")
        for (raw, canonical), count in sorted(
            aggregation_stats.items(), key=lambda kv: -kv[1]
        ):
            print(f"  {raw:35s} → {canonical:25s} {count:5d}")

    # Sanity-check: which edges have the most GloBI evidence behind them?
    # Goes to stderr alongside the other INFO lines so it doesn't clutter the
    # main report; the keystone interactions should land in the top of this list.
    if edge_count:
        print("\nINFO: Top 10 most-evidenced edges by GloBI record count:",
              file=sys.stderr)
        for (src, layer, itype, tgt), count in sorted(
            edge_count.items(), key=lambda kv: -kv[1]
        )[:10]:
            print(
                f"INFO:   {count:5d}  {src} --[{itype}]--> {tgt}  ({layer})",
                file=sys.stderr,
            )

    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--species", type=Path,
                        default="data/processed/sabangau/species.json")
    parser.add_argument("--globi-tsv", type=Path,
                        default="data/raw/sabangau/globi_pull.tsv")
    parser.add_argument("--output", type=Path,
                        default="data/raw/sabangau/globi_filtered.json")
    args = parser.parse_args()
    sys.exit(run(args.species, args.globi_tsv, args.output))

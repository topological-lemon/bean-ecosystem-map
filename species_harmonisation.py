"""
species_harmonisation.py
========================
Fetches species data from GBIF API for a given ecosystem/region,
harmonises taxonomy, and outputs a canonical species.json.

Usage:
    python scripts/species_harmonisation.py --ecosystem amazon --output data/processed/species.json

Requirements: requests, pandas
"""

import argparse
import json
import time
from pathlib import Path

import requests

GBIF_SPECIES_API = "https://api.gbif.org/v1/species"
GBIF_OCCURRENCE_API = "https://api.gbif.org/v1/occurrence/search"
IUCN_API = "https://apiv3.iucnredlist.org/api/v3/species"

# Curated seed species for Amazon tropical rainforest (Phase 1)
# Extend this list as the project grows. Each entry: (scientific_name, taxa_group, trophic_level)
AMAZON_SEED_SPECIES = [
    # Apex predators
    ("Panthera onca", "mammal", 4.2),
    ("Harpia harpyja", "bird", 4.0),

    # Large herbivores / frugivores
    ("Tapirus terrestris", "mammal", 2.5),
    ("Tayassu pecari", "mammal", 2.3),
    ("Ateles paniscus", "mammal", 2.5),
    ("Lagothrix lagothricha", "mammal", 2.2),

    # Medium-level consumers
    ("Mazama americana", "mammal", 3.0),
    ("Dasyprocta leporina", "mammal", 2.2),
    ("Nasua nasua", "mammal", 2.8),
    ("Ara macao", "bird", 2.3),

    # Key plant species (structure providers)
    ("Ficus insipida", "plant", 1.0),
    ("Cecropia peltata", "plant", 1.0),
    ("Heliconia latispatha", "plant", 1.0),
    ("Swietenia macrophylla", "plant", 1.0),
    ("Mauritia flexuosa", "plant", 1.0),

    # Pollinators / dispersers
    ("Eulaema meriana", "invertebrate", 2.0),
    ("Apis mellifera", "invertebrate", 2.0),
    ("Ramphastos tucanus", "bird", 2.5),

    # Detritivores / nutrient mediators
    ("Atta cephalotes", "invertebrate", 2.0),
    ("Liometopum apiculatum", "invertebrate", 2.0),

    # Keystone / ecosystem engineers
    ("Hydrochoerus hydrochaeris", "mammal", 2.2),
    ("Pteronura brasiliensis", "mammal", 3.8),
]

IUCN_STATUS_MAP = {
    "Least Concern": "LC", "Near Threatened": "NT", "Vulnerable": "VU",
    "Endangered": "EN", "Critically Endangered": "CR", "Extinct in the Wild": "EW",
    "Extinct": "EX", "Data Deficient": "DD", "Not Evaluated": "NE",
}

TAXA_PERSISTENCE_DEFAULTS = {
    "mammal": 0.70,
    "bird": 0.72,
    "reptile": 0.80,
    "amphibian": 0.65,
    "fish": 0.75,
    "invertebrate": 0.85,
    "plant": 0.88,
    "fungi": 0.90,
    "other": 0.75,
}

TAXA_REDUNDANCY_DEFAULTS = {
    "mammal": 0.25,
    "bird": 0.30,
    "reptile": 0.35,
    "amphibian": 0.30,
    "fish": 0.40,
    "invertebrate": 0.50,
    "plant": 0.55,
    "fungi": 0.60,
    "other": 0.35,
}

KEYSTONE_CANDIDATES = {
    "Panthera onca", "Harpia harpyja", "Ficus insipida", "Ateles paniscus",
    "Eulaema meriana", "Atta cephalotes", "Tapirus terrestris",
}


def gbif_lookup(scientific_name: str) -> dict:
    """Lookup species in GBIF and return canonical record."""
    try:
        resp = requests.get(
            f"{GBIF_SPECIES_API}/match",
            params={"name": scientific_name, "verbose": False},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  GBIF lookup failed for {scientific_name}: {e}")
        return {}


def build_species_record(
    idx: int,
    scientific_name: str,
    taxa_group: str,
    trophic_level: float,
    gbif_data: dict,
) -> dict:
    """Construct a species.json record."""
    common_name = gbif_data.get("vernacularName") or scientific_name.split()[1]
    gbif_key = gbif_data.get("usageKey") or gbif_data.get("speciesKey")

    is_keystone = scientific_name in KEYSTONE_CANDIDATES
    persistence = TAXA_PERSISTENCE_DEFAULTS.get(taxa_group, 0.75)
    redundancy = TAXA_REDUNDANCY_DEFAULTS.get(taxa_group, 0.35)

    # Adjust persistence for apex predators and keystone species
    if trophic_level >= 4.0 or is_keystone:
        persistence -= 0.10
        redundancy -= 0.10

    return {
        "id": f"sp_{idx:03d}",
        "scientific_name": scientific_name,
        "common_name": common_name,
        "taxa_group": taxa_group,
        "trophic_level": trophic_level,
        "trophic_role": _infer_trophic_role(trophic_level, taxa_group),
        "persistence_score": round(max(0.3, persistence), 2),
        "redundancy_factor": round(max(0.05, redundancy), 2),
        "recovery_potential": _infer_recovery(trophic_level, taxa_group),
        "keystone_candidate": is_keystone,
        "iucn_status": "LC",  # Will be updated if IUCN key provided
        "gbif_taxon_key": gbif_key,
        "notes": f"Phase 1 seed species. GBIF match confidence: {gbif_data.get('confidence', 'N/A')}%",
    }


def _infer_trophic_role(trophic_level: float, taxa_group: str) -> str:
    if taxa_group == "plant":
        return "producer"
    if trophic_level <= 1.5:
        return "producer"
    if trophic_level <= 2.5:
        return "primary_consumer"
    if trophic_level <= 3.5:
        return "secondary_consumer"
    if trophic_level >= 4.0:
        return "apex_predator"
    return "omnivore"


def _infer_recovery(trophic_level: float, taxa_group: str) -> str:
    if taxa_group in ("plant", "fungi", "invertebrate"):
        return "high"
    if taxa_group in ("fish", "reptile", "amphibian"):
        return "medium"
    if trophic_level >= 4.0:
        return "very_low"
    return "low"


def run(ecosystem: str, output_path: str, use_gbif: bool = True) -> None:
    seed_species = {
        "amazon": AMAZON_SEED_SPECIES,
    }.get(ecosystem.lower(), AMAZON_SEED_SPECIES)

    print(f"Building species.json for ecosystem: {ecosystem}")
    print(f"Seed species count: {len(seed_species)}")
    if use_gbif:
        print("Querying GBIF API for each species...")

    records = []
    for idx, (sci_name, taxa, tl) in enumerate(seed_species, start=1):
        print(f"  [{idx:02d}/{len(seed_species)}] {sci_name}", end=" ")
        gbif_data = gbif_lookup(sci_name) if use_gbif else {}
        record = build_species_record(idx, sci_name, taxa, tl, gbif_data)
        records.append(record)
        print(f"→ {record['id']} ({record['common_name']})")
        if use_gbif:
            time.sleep(0.3)  # be polite to the GBIF API

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2)

    print(f"\nDone. Written {len(records)} species to {out_path}")
    print("\nNext step: build interactions.json using GloBI and Bascompte lab data.")
    print("See research/literature_review.md for dataset URLs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bud Ecosystem species harmonisation pipeline")
    parser.add_argument("--ecosystem", default="amazon", help="Ecosystem name (default: amazon)")
    parser.add_argument("--output", default="data/processed/species.json", help="Output path")
    parser.add_argument("--no-gbif", action="store_true", help="Skip GBIF API calls (dry run)")
    args = parser.parse_args()
    run(args.ecosystem, args.output, use_gbif=not args.no_gbif)

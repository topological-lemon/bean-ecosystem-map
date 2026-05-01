"""
species_harmonisation.py
========================
Fetches species data from GBIF API for a given ecosystem/region,
harmonises taxonomy, and outputs a canonical species.json.

Usage:
    python scripts/species_harmonisation.py --ecosystem sabangau --output data/processed/sabangau/species.json
    python scripts/species_harmonisation.py --ecosystem amazon --output data/processed/amazon/species.json

Requirements: requests
"""

import argparse
import json
import time
from pathlib import Path

import requests

GBIF_SPECIES_API = "https://api.gbif.org/v1/species"
GBIF_OCCURRENCE_API = "https://api.gbif.org/v1/occurrence/search"
IUCN_API = "https://apiv3.iucnredlist.org/api/v3/species"


# ---------------------------------------------------------------------------
# AMAZON (legacy Phase 1 prototype roster — kept for backward compatibility)
# ---------------------------------------------------------------------------
AMAZON_SEED_SPECIES = [
    ("Panthera onca", "mammal", 4.2),
    ("Harpia harpyja", "bird", 4.0),
    ("Tapirus terrestris", "mammal", 2.5),
    ("Tayassu pecari", "mammal", 2.3),
    ("Ateles paniscus", "mammal", 2.5),
    ("Lagothrix lagothricha", "mammal", 2.2),
    ("Mazama americana", "mammal", 3.0),
    ("Dasyprocta leporina", "mammal", 2.2),
    ("Nasua nasua", "mammal", 2.8),
    ("Ara macao", "bird", 2.3),
    ("Ficus insipida", "plant", 1.0),
    ("Cecropia peltata", "plant", 1.0),
    ("Heliconia latispatha", "plant", 1.0),
    ("Swietenia macrophylla", "plant", 1.0),
    ("Mauritia flexuosa", "plant", 1.0),
    ("Eulaema meriana", "invertebrate", 2.0),
    ("Apis mellifera", "invertebrate", 2.0),
    ("Ramphastos tucanus", "bird", 2.5),
    ("Atta cephalotes", "invertebrate", 2.0),
    ("Liometopum apiculatum", "invertebrate", 2.0),
    ("Hydrochoerus hydrochaeris", "mammal", 2.2),
    ("Pteronura brasiliensis", "mammal", 3.8),
]


# ---------------------------------------------------------------------------
# SABANGAU peat-swamp forest, Central Kalimantan (Phase 2 — primary roster)
# ---------------------------------------------------------------------------
# Species selected from documented Sabangau community (Page et al. 1997,
# Morrogh-Bernard 2009, Posa 2011, Borneo Nature Foundation surveys).
# Trophic levels follow standard ecological convention:
#   1.0       producers (plants, fungi)
#   2.0–2.5   primary consumers (frugivores, folivores)
#   2.5–3.0   mixed feeders / omnivores
#   3.0–3.5   secondary consumers
#   3.8–4.2   top predators
# Where a species is functionally rare / depressed (e.g. clouded leopard),
# trophic level reflects its role when present.
SABANGAU_SEED_SPECIES = [
    # --- Apex / top predators ---
    # Note: Sundaland tigers extinct from this area; ecosystem is mesopredator-released.
    # See model_assumptions.md.
    ("Helarctos malayanus",        "mammal",       3.2),  # sun bear — opportunistic omnivore
    ("Neofelis diardi",            "mammal",       4.0),  # Sunda clouded leopard — apex when present
    ("Tomistoma schlegelii",       "reptile",      4.0),  # false gharial — aquatic apex

    # --- Primates ---
    ("Pongo pygmaeus wurmbii",     "mammal",       2.3),  # Bornean orangutan (Felix's subspecies)
    ("Hylobates albibarbis",       "mammal",       2.3),  # Bornean white-bearded gibbon
    ("Nasalis larvatus",           "mammal",       2.2),  # proboscis monkey — peat-swamp specialist
    ("Presbytis rubicunda",        "mammal",       2.2),  # red leaf monkey
    ("Macaca fascicularis",        "mammal",       2.6),  # long-tailed macaque (omnivorous)
    ("Macaca nemestrina",          "mammal",       2.6),  # southern pig-tailed macaque

    # --- Other large frugivores / dispersers ---
    ("Buceros rhinoceros",         "bird",         2.5),  # rhinoceros hornbill — keystone disperser
    ("Anthracoceros albirostris",  "bird",         2.5),  # oriental pied hornbill
    ("Pteropus vampyrus",          "mammal",       2.2),  # large flying fox — long-distance disperser
    ("Galeopterus variegatus",     "mammal",       2.1),  # Sunda colugo (folivore; revised genus name)

    # --- Mid-trophic mammals ---
    ("Tragulus javanicus",         "mammal",       2.4),  # lesser mousedeer
    ("Rusa unicolor",              "mammal",       2.3),  # sambar deer
    ("Hemigalus derbyanus",        "mammal",       3.0),  # banded civet
    ("Paradoxurus hermaphroditus", "mammal",       2.9),  # common palm civet (also a disperser)
    ("Sus barbatus",               "mammal",       2.5),  # bearded pig — keystone seed predator/disperser

    # --- Plants: keystone figs and dipterocarps ---
    ("Ficus stupenda",             "plant",        1.0),  # large strangler fig
    ("Ficus benjamina",            "plant",        1.0),
    ("Ficus albipila",             "plant",        1.0),
    ("Shorea balangeran",          "plant",        1.0),  # dominant peat-swamp dipterocarp
    ("Gonystylus bancanus",        "plant",        1.0),  # ramin — Critically Endangered
    ("Dyera lowii",                "plant",        1.0),  # jelutong — culturally important
    ("Combretocarpus rotundatus",  "plant",        1.0),  # tumih — dominant peat-swamp tree
    ("Palaquium leiocarpum",       "plant",        1.0),  # orangutan food plant
    ("Diospyros bantamensis",      "plant",        1.0),  # orangutan food plant
    ("Tetramerista glabra",        "plant",        1.0),  # punak — co-dominant peat tree

    # --- Pollinators and decomposer abstractions ---
    ("Apis dorsata",               "invertebrate", 2.0),  # giant honeybee — primary canopy pollinator
    ("Ceratosolen spp.",           "invertebrate", 2.0),  # fig wasp complex — obligate fig pollinators
    ("Mycorrhizal community",      "fungi",        1.0),  # abstracted; facilitates dipterocarp roots
]


# ---------------------------------------------------------------------------
# Common-name overrides
# GBIF's vernacularName field is unreliable (often null, sometimes wrong).
# We hardcode common names for every Sabangau species so the demo reads cleanly
# to non-ecologists. This is the single highest-leverage usability fix.
# ---------------------------------------------------------------------------
COMMON_NAME_OVERRIDES = {
    # Sabangau
    "Helarctos malayanus":        "Sun bear",
    "Neofelis diardi":            "Sunda clouded leopard",
    "Tomistoma schlegelii":       "False gharial",
    "Pongo pygmaeus wurmbii":     "Bornean orangutan",
    "Hylobates albibarbis":       "Bornean white-bearded gibbon",
    "Nasalis larvatus":           "Proboscis monkey",
    "Presbytis rubicunda":        "Red leaf monkey",
    "Macaca fascicularis":        "Long-tailed macaque",
    "Macaca nemestrina":          "Southern pig-tailed macaque",
    "Buceros rhinoceros":         "Rhinoceros hornbill",
    "Anthracoceros albirostris":  "Oriental pied hornbill",
    "Pteropus vampyrus":          "Large flying fox",
    "Galeopterus variegatus":     "Sunda colugo",
    "Tragulus javanicus":         "Lesser mousedeer",
    "Rusa unicolor":              "Sambar deer",
    "Hemigalus derbyanus":        "Banded civet",
    "Paradoxurus hermaphroditus": "Common palm civet",
    "Sus barbatus":               "Bearded pig",
    "Ficus stupenda":             "Strangler fig (F. stupenda)",
    "Ficus benjamina":            "Weeping fig",
    "Ficus albipila":             "Strangler fig (F. albipila)",
    "Shorea balangeran":          "Balangeran (peat-swamp meranti)",
    "Gonystylus bancanus":        "Ramin",
    "Dyera lowii":                "Jelutong",
    "Combretocarpus rotundatus":  "Tumih",
    "Palaquium leiocarpum":       "Nyatoh (Palaquium)",
    "Diospyros bantamensis":      "Peat ebony",
    "Tetramerista glabra":        "Punak",
    "Apis dorsata":               "Giant honeybee",
    "Ceratosolen spp.":           "Fig wasp complex",
    "Mycorrhizal community":      "Mycorrhizal fungi",

    # Amazon (legacy)
    "Panthera onca":              "Jaguar",
    "Harpia harpyja":              "Harpy eagle",
    "Tapirus terrestris":         "Lowland tapir",
    "Tayassu pecari":             "White-lipped peccary",
    "Ateles paniscus":            "Red-faced spider monkey",
    "Lagothrix lagothricha":      "Brown woolly monkey",
    "Mazama americana":           "Red brocket deer",
    "Dasyprocta leporina":        "Red-rumped agouti",
    "Nasua nasua":                "South American coati",
    "Ara macao":                  "Scarlet macaw",
    "Ficus insipida":             "Higueron fig",
    "Cecropia peltata":           "Trumpet tree",
    "Heliconia latispatha":       "Heliconia",
    "Swietenia macrophylla":      "Big-leaf mahogany",
    "Mauritia flexuosa":          "Moriche palm",
    "Eulaema meriana":            "Orchid bee",
    "Apis mellifera":             "Western honeybee",
    "Ramphastos tucanus":         "White-throated toucan",
    "Atta cephalotes":            "Leafcutter ant",
    "Liometopum apiculatum":      "Velvety tree ant",
    "Hydrochoerus hydrochaeris":  "Capybara",
    "Pteronura brasiliensis":     "Giant otter",
}


IUCN_STATUS_MAP = {
    "Least Concern": "LC", "Near Threatened": "NT", "Vulnerable": "VU",
    "Endangered": "EN", "Critically Endangered": "CR", "Extinct in the Wild": "EW",
    "Extinct": "EX", "Data Deficient": "DD", "Not Evaluated": "NE",
}


# ---------------------------------------------------------------------------
# IUCN status overrides — accurate as of IUCN Red List 2024 assessments.
# These will be replaced by live API lookup in a later step (requires API key).
# Source for each is the IUCN Red List species page; verify before final
# submission as listings can change.
# ---------------------------------------------------------------------------
IUCN_STATUS_OVERRIDES = {
    # Sabangau
    "Pongo pygmaeus wurmbii":     "CR",  # Critically Endangered
    "Pongo pygmaeus":             "CR",
    "Nasalis larvatus":           "EN",
    "Presbytis rubicunda":        "VU",
    "Helarctos malayanus":        "VU",
    "Neofelis diardi":            "VU",
    "Tomistoma schlegelii":       "VU",
    "Buceros rhinoceros":         "VU",
    "Anthracoceros albirostris":  "LC",
    "Pteropus vampyrus":          "NT",
    "Hylobates albibarbis":       "EN",
    "Macaca fascicularis":        "EN",  # recently uplisted
    "Macaca nemestrina":          "VU",
    "Galeopterus variegatus":     "LC",
    "Tragulus javanicus":         "DD",
    "Rusa unicolor":              "VU",
    "Hemigalus derbyanus":        "NT",
    "Paradoxurus hermaphroditus": "LC",
    "Sus barbatus":               "VU",
    "Gonystylus bancanus":        "CR",
    "Shorea balangeran":          "EN",
    "Dyera lowii":                "VU",
    "Combretocarpus rotundatus":  "VU",
    "Tetramerista glabra":        "LC",
    # Plants without formal IUCN assessment default to NE
    "Ficus stupenda":             "LC",
    "Ficus benjamina":            "LC",
    "Ficus albipila":             "NE",
    "Palaquium leiocarpum":       "NE",
    "Diospyros bantamensis":      "NE",
    # Functional groups / abstractions
    "Apis dorsata":               "NE",
    "Ceratosolen spp.":           "NE",
    "Mycorrhizal community":      "NE",
}


TAXA_PERSISTENCE_DEFAULTS = {
    "mammal": 0.70, "bird": 0.72, "reptile": 0.80, "amphibian": 0.65,
    "fish": 0.75, "invertebrate": 0.85, "plant": 0.88, "fungi": 0.90, "other": 0.75,
}

TAXA_REDUNDANCY_DEFAULTS = {
    "mammal": 0.25, "bird": 0.30, "reptile": 0.35, "amphibian": 0.30,
    "fish": 0.40, "invertebrate": 0.50, "plant": 0.55, "fungi": 0.60, "other": 0.35,
}

# Persistence is also reduced for IUCN-threatened species, since "real-world"
# extinction probability is what we are modelling.
IUCN_PERSISTENCE_PENALTY = {
    "LC": 0.00, "NT": 0.05, "VU": 0.10, "EN": 0.18, "CR": 0.28,
    "EW": 0.40, "EX": 1.00, "DD": 0.05, "NE": 0.00,
}


# ---------------------------------------------------------------------------
# Sabangau keystone species — based on Sabangau-specific literature, not
# the Amazon defaults. Selection rationale documented in model_assumptions.md.
# ---------------------------------------------------------------------------
KEYSTONE_CANDIDATES = {
    # Sabangau keystones
    "Pongo pygmaeus wurmbii",   # primary frugivore / disperser, large-gaped
    "Buceros rhinoceros",       # large-gaped seed disperser; dispersal-layer keystone
    "Hylobates albibarbis",     # canopy disperser; redundancy partner with orangutan
    "Sus barbatus",             # ground-layer seed predator/disperser, ecosystem engineer
    "Ficus stupenda",           # keystone fig; fallback food across drought periods
    "Ficus benjamina",          # keystone fig
    "Ficus albipila",           # keystone fig
    "Shorea balangeran",        # dominant canopy tree; structural keystone
    "Ceratosolen spp.",         # obligate mutualist for figs

    # Amazon keystones (kept for amazon ecosystem mode)
    "Panthera onca", "Harpia harpyja", "Ficus insipida", "Ateles paniscus",
    "Eulaema meriana", "Atta cephalotes", "Tapirus terrestris",
}


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

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


def _resolve_common_name(scientific_name: str, gbif_data: dict) -> str:
    """Prefer hardcoded common name, then GBIF vernacular, then full Latin name.

    The previous implementation extracted scientific_name.split()[1], which
    yielded the species epithet (e.g. 'pecari') rather than a real common name.
    """
    if scientific_name in COMMON_NAME_OVERRIDES:
        return COMMON_NAME_OVERRIDES[scientific_name]
    if gbif_data.get("vernacularName"):
        return gbif_data["vernacularName"]
    return scientific_name


def _resolve_iucn_status(scientific_name: str) -> str:
    """Return hardcoded IUCN status override, or 'LC' as default.

    TODO (Travis): replace with live IUCN API lookup once a token is available.
    """
    return IUCN_STATUS_OVERRIDES.get(scientific_name, "LC")


def build_species_record(
    idx: int,
    scientific_name: str,
    taxa_group: str,
    trophic_level: float,
    gbif_data: dict,
) -> dict:
    """Construct a species.json record."""
    common_name = _resolve_common_name(scientific_name, gbif_data)
    gbif_key = gbif_data.get("usageKey") or gbif_data.get("speciesKey")
    iucn_status = _resolve_iucn_status(scientific_name)

    is_keystone = scientific_name in KEYSTONE_CANDIDATES
    persistence = TAXA_PERSISTENCE_DEFAULTS.get(taxa_group, 0.75)
    redundancy = TAXA_REDUNDANCY_DEFAULTS.get(taxa_group, 0.35)

    # Adjust persistence for apex predators and keystone species
    if trophic_level >= 4.0 or is_keystone:
        persistence -= 0.10
        redundancy -= 0.10

    # Further adjust persistence for IUCN-threatened species so the simulator
    # reflects real-world fragility, not just trophic-position fragility.
    persistence -= IUCN_PERSISTENCE_PENALTY.get(iucn_status, 0.0)

    return {
        "id": f"sp_{idx:03d}",
        "scientific_name": scientific_name,
        "common_name": common_name,
        "taxa_group": taxa_group,
        "trophic_level": trophic_level,
        "trophic_role": _infer_trophic_role(trophic_level, taxa_group),
        "persistence_score": round(max(0.20, persistence), 2),
        "redundancy_factor": round(max(0.05, redundancy), 2),
        "recovery_potential": _infer_recovery(trophic_level, taxa_group),
        "keystone_candidate": is_keystone,
        "iucn_status": iucn_status,
        "gbif_taxon_key": gbif_key,
        "notes": (
            f"Sabangau roster v1. GBIF match confidence: "
            f"{gbif_data.get('confidence', 'N/A')}%."
        ),
    }


def _infer_trophic_role(trophic_level: float, taxa_group: str) -> str:
    if taxa_group == "plant":
        return "producer"
    if taxa_group == "fungi":
        return "decomposer_facilitator"
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


ECOSYSTEM_ROSTERS = {
    "amazon":   AMAZON_SEED_SPECIES,
    "sabangau": SABANGAU_SEED_SPECIES,
}


def run(ecosystem: str, output_path: str, use_gbif: bool = True) -> None:
    seed_species = ECOSYSTEM_ROSTERS.get(ecosystem.lower())
    if seed_species is None:
        raise ValueError(
            f"Unknown ecosystem '{ecosystem}'. "
            f"Available: {sorted(ECOSYSTEM_ROSTERS.keys())}"
        )

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
        print(
            f"→ {record['id']} "
            f"({record['common_name']}, {record['iucn_status']})"
        )
        if use_gbif:
            time.sleep(0.3)  # be polite to the GBIF API

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2)

    print(f"\nDone. Written {len(records)} species to {out_path}")
    print("\nNext step: build interactions.json using GloBI, Bascompte data, "
          "and manual extraction from Morrogh-Bernard 2009.")
    print("See research/literature/sabangau/ for primary sources.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bud Ecosystem species harmonisation pipeline"
    )
    parser.add_argument(
        "--ecosystem", default="sabangau",
        help="Ecosystem name. Choices: amazon, sabangau (default: sabangau)",
    )
    parser.add_argument(
        "--output", default="data/processed/sabangau/species.json",
        help="Output path",
    )
    parser.add_argument(
        "--no-gbif", action="store_true",
        help="Skip GBIF API calls (dry run)",
    )
    args = parser.parse_args()
    run(args.ecosystem, args.output, use_gbif=not args.no_gbif)

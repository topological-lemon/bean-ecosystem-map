# Bud Ecosystem Quantum Map

> **A multilayer ecological network simulator revealing hidden cascade vulnerabilities.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Status: Active Development](https://img.shields.io/badge/Status-Active%20Development-orange.svg)]()

## What is this?

Standard ecological models treat ecosystems as a single network — every interaction collapsed into one layer. This systematically misses cascade pathways that only appear when you model **trophic, mutualistic, parasitic, dispersal, and habitat dependencies as separate, interacting layers**.

This project builds an interactive multilayer ecosystem cascade simulator that:

- Models ecosystems as layered networks (trophic / mutualistic / parasitic / dispersal / habitat)
- Simulates extinction cascades in both multilayer and monolayer modes — revealing what aggregation hides
- Computes live metrics: extinction count, cascade depth, hidden cascade events, robustness score, keystone centrality shift
- Outputs an **Ecological Integrity Index** (0–100) tied to ecosystem services provision
- Estimates the **human and financial cost** of ecosystem degradation (using published valuations)
- Long-term: reformulates network resilience optimisation as a quantum computing problem

## Why it matters

Monolayer ecological models underestimate cascade risk. When a species disappears, it may not just remove itself from the food web — it may collapse a pollination network, sever a seed dispersal pathway, and destabilise a mycorrhizal facilitation chain simultaneously. None of these second-order effects are visible in a single aggregated graph.

This simulator makes those hidden dependencies visible, interactive, and quantifiable.

## Current status

**Phase 1 — Proof of concept.** Building a 20–30 species tropical rainforest network with 3 interaction layers and live cascade simulation.

## Quick start

```bash
git clone https://github.com/[your-handle]/bud-ecosystem-map.git
cd bud-ecosystem-map
pip install -r requirements.txt
python simulator/app.py
```

Open `http://localhost:8050` in your browser.

## Project structure

```
bud-ecosystem-map/
├── data/
│   ├── raw/                  # Source datasets (GBIF, GloBI, IUCN)
│   └── processed/            # Harmonised JSON data files
│       ├── species.json       # Canonical species list with traits
│       ├── interactions.json  # Pairwise interaction records
│       ├── layers.json        # Layer definitions and metadata
│       └── scenarios.json     # Disturbance scenario configurations
├── simulator/
│   ├── graph.py              # MultilayerGraph class
│   ├── cascade.py            # Cascade simulation engine
│   ├── metrics.py            # Ecological metrics calculations
│   ├── integrity.py          # Ecological Integrity Index
│   ├── cost.py               # Ecosystem services cost calculator
│   └── app.py                # Dash/Plotly interactive app (Phase 1)
├── frontend/                 # React app (Phase 4+)
├── research/
│   ├── literature/           # Annotated bibliography
│   └── quantum/              # QUBO formulation notes (Phase 6)
├── docs/
│   ├── data_schema.md        # JSON schema documentation
│   ├── model_assumptions.md  # Explicit ecological model assumptions
│   └── ecosystem_services.md # Valuation methodology
├── scripts/
│   └── species_harmonisation.py  # GBIF data pipeline
├── requirements.txt
└── README.md
```

## Data sources

| Source | Content | Access |
|--------|---------|--------|
| [GBIF](https://www.gbif.org/) | Species occurrence, taxonomy | Free API |
| [GloBI](https://www.globalbioticinteractions.org/) | Species interactions | Free |
| [Web of Life / mangal](https://mangal.io/) | Network datasets | Free |
| [IUCN Red List](https://www.iucnredlist.org/about/support-our-work) | Extinction risk, traits | API key |
| [TRY Plant Traits](https://www.try-db.org/) | Functional traits | Open access |
| [Bascompte Lab](https://bascompte.net/networksdata.html) | Mutualistic networks | Open access |
| [TEEB / Costanza 2014](https://www.teebweb.org/) | Ecosystem services values | Published |

## Ecological model

### Interaction layers
- **Trophic**: predator–prey, herbivory
- **Mutualistic**: pollination, seed dispersal, mycorrhizal associations
- **Parasitic**: host–parasite, pathogen
- **Habitat facilitation**: ecosystem engineering, nurse plant relationships
- **Competitive**: resource competition

### Cascade logic
When species X is removed or stressed:
1. Direct dependents in each layer are identified and stress-weighted
2. Extinction thresholds are checked (probabilistic, informed by persistence scores)
3. Secondary cascades propagate iteratively until stability or total collapse
4. Redundancy buffering is applied (functional redundancy reduces extinction probability)
5. All metrics and the integrity index are recalculated

See `docs/model_assumptions.md` for full methodological detail and empirical grounding.

### Ecological Integrity Index
A composite 0–100 score derived from:
- Extinction count (weighted)
- Interaction diversity loss
- Functional group coverage
- Cascade depth
- Connectivity retained
- Keystone species persistence

Dollar cost is computed by mapping integrity loss to ecosystem services degradation using biome-specific valuations (Costanza et al. 2014, TEEB database).

## Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Proof of concept — 20–30 species, 3 layers, Dash prototype | 🔄 In progress |
| 2 | Full multilayer structure — 5–8 layers, cross-layer dependencies | ⏳ Planned |
| 3 | Cascade logic — thresholds, redundancy, recovery | ⏳ Planned |
| 4 | Monolayer vs multilayer comparison | ⏳ Planned |
| 5 | Disturbance scenarios + integrity index + cost output | ⏳ Planned |
| 6 | Quantum extension — QUBO reformulation | 🔬 Research |

## Contributing

We welcome contributions from ecologists, network scientists, and developers. Please read `CONTRIBUTING.md` before submitting a PR.

Priority contributions needed:
- Ecological review of interaction datasets
- Additional ecosystem data (mangrove estuary, coral reef)
- Front-end React development (Phase 4+)
- Literature review expansions

## Citation

If you use this simulator in your research, please cite:

```
[Citation to be added upon first publication]
```

## Team

- **Jacinta May** — Architecture, data pipeline, front-end [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/jacinta-may-quantum/)
- **Travis Raheb-Mol** — Ecological model, literature grounding, cascade logic [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/travisraheb-mol/)

## Licence

The code in this repository is licensed under the MIT License — see `LICENSE`.

The data, documentation, and research outputs (including `/data`, `/docs`, and `/research`) are licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

**Attribution is required for all use.** Any use, adaptation, derivative work, publication, or deployment of any part of this project must visibly credit:

> Jacinta May & Travis Raheb-Mol, *Bean Ecosystem Quantum Map* (2025), https://github.com/topological-lemon/bean-ecosystem-map

This applies to academic publications, commercial tools, policy reports, presentations, and software that incorporates this work in whole or in part.

## References

Key literature underpinning the model:

- Poirier et al. (2021) *Nat. Ecol. Evol.* — Multilayer network framework for ecological cascades
- Bascompte & Jordano (2007) *Science* — Mutualistic networks and biodiversity
- Dunne et al. (2002) *PNAS* — Network structure and robustness of marine food webs
- Eklöf & Ebenman (2006) *J. Animal Ecol.* — Species loss and secondary extinctions
- Costanza et al. (2014) *Global Environmental Change* — Changes in the global value of ecosystem services

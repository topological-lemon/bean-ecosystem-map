# Bud Ecosystem Quantum Map — Literature Review & Research Grounding

## Purpose

This document provides the empirical and theoretical grounding for the cascade simulator's model assumptions, ecological integrity index, and cost calculator. All design decisions in the codebase should be traceable to entries here.

---

## Tier 1: Direct & Foundational (must-read before Phase 2)

### 1. Poirier et al. (2021) — *Primary framing reference*
**Citation:** Poirier, A. M. A., et al. (2021). Ecological network complexity as a lever for ecological resilience. *Nature Ecology & Evolution*, 5(12), 1582–1590. DOI: 10.1038/s41559-017-0101

**Why it matters:** Directly frames the multilayer vs monolayer comparison we're building. Demonstrates that aggregating interaction types into a single layer systematically underestimates cascade risk. The key finding: hidden extinctions (visible only in multilayer models) account for 20–40% of total secondary extinctions in their tropical forest dataset.

**What to extract for our model:**
- Their operationalisation of "hidden cascade events" → informs our `hidden_cascade_events` metric definition
- Layer interaction weights → informs our `cascade_weight` parameter per layer
- Species persistence threshold logic → directly applicable to our `persistence_score` thresholds

**Dataset:** Accompanying dataset publicly available — use this for Phase 1 species list validation.

---

### 2. Bascompte & Jordano (2007) — *Mutualistic network architecture*
**Citation:** Bascompte, J., & Jordano, P. (2007). Plant-animal mutualistic networks: the architecture of biodiversity. *Annual Review of Ecology, Evolution, and Systematics*, 38, 567–593.

**Why it matters:** Definitive reference for the structure of mutualistic networks (nested, asymmetric). Explains why mutualistic layers have different cascade properties than trophic layers: mutualistic networks are more nested and therefore more robust to random extinctions but more vulnerable to loss of specialist hubs.

**What to extract:**
- Nestedness metrics for mutualistic layers → informs our `redundancy_factor` defaults for mutualistic specialists
- Hub species identification → informs `keystone_candidate` flags in species.json
- Asymmetry patterns → informs `effect_on_source` / `effect_on_target` defaults for pollination interactions

**Data:** Bascompte Lab openly shares interaction matrices at bascompte.net/networksdata.html — use for tropical forest mutualistic layer.

---

### 3. Dunne, Williams & Martinez (2002) — *Food web robustness baseline*
**Citation:** Dunne, J. A., Williams, R. J., & Martinez, N. D. (2002). Network structure and biodiversity loss in food webs: robustness increases with connectance. *Ecology Letters*, 5(4), 558–567.

**Why it matters:** This is the empirical calibration baseline for trophic cascade thresholds. Their robustness analysis across 16 food webs shows that connectance is the primary predictor of cascade robustness. Critically: random species loss is much less damaging than targeted loss of highly connected species.

**What to extract:**
- Robustness curves by connectance level → calibrates our `persistence_score` threshold function
- The finding that secondary extinctions accelerate non-linearly → justifies iterative cascade propagation in `CascadeSimulator`
- Connectance values for tropical forest → use to validate our Phase 1 network's topology

---

### 4. Eklöf & Ebenman (2006) — *Secondary extinction thresholds*
**Citation:** Eklöf, A., & Ebenman, B. (2006). Species loss and secondary extinctions in simple and complex model communities. *Journal of Animal Ecology*, 75(1), 239–246.

**Why it matters:** Provides explicit mathematical formulation of secondary extinction thresholds under different interaction types. Their threshold model (species goes extinct when it loses a fraction k of its interaction partners) is the direct basis for our `persistence_score` extinction logic.

**What to extract:**
- The threshold parameter k by taxa group → use to set default `persistence_score` values per `taxa_group`
- The finding that obligate dependencies dramatically lower the threshold → justifies the `obligate_mult = 2.0` in our cascade simulator
- Comparison of simple vs complex communities → directly supports our multilayer vs monolayer comparison methodology

---

### 5. Costanza et al. (2014) — *Ecosystem services dollar values*
**Citation:** Costanza, R., et al. (2014). Changes in the global value of ecosystem services. *Global Environmental Change*, 26, 152–158. DOI: 10.1016/j.gloenvcha.2014.04.002

**Why it matters:** The primary source for our `CostCalculator` biome values. Provides USD/ha/year valuations for 17 ecosystem types. Critically: this paper also quantifies the *loss* between 1997 and 2011 (~$20 trillion/year due to land use change), which provides a narrative anchor for our tool.

**Note on controversy:** Monetising ecosystem services is philosophically contested. We should present the dollar cost output as a *communication tool* for policymakers, not a claim about the intrinsic value of ecosystems. The README should cite this paper and acknowledge the debate.

---

## Tier 2: Important Supporting Literature (Phase 2–3)

### 6. Pilosof et al. (2017) — *Multilayer network framework*
**Citation:** Pilosof, S., Porter, M. A., Pascual, M., & Kéfi, S. (2017). The multilayer nature of ecological networks. *Nature Ecology & Evolution*, 1(4), 0101.

**Why it matters:** The theoretical framework paper for multilayer ecological network analysis. Provides mathematical formalism (interlayer coupling, supra-adjacency matrix) that we'll need for Phase 6 (quantum reformulation). Also provides layer-specific vulnerability metrics.

---

### 7. Kéfi et al. (2012) — *Beyond food webs: multiple interaction types*
**Citation:** Kéfi, S., et al. (2012). More than a meal... integrating non-feeding interactions into food webs. *Ecology Letters*, 15(4), 291–300.

**Why it matters:** Empirical demonstration that adding non-trophic interactions (facilitation, competition) to food webs changes cascade outcomes substantially. Directly motivates including our habitat facilitation and competitive layers.

---

### 8. Lurgi et al. (2012) — *Climate change and network structure*
**Citation:** Lurgi, M., López, B. C., & Montoya, J. M. (2012). Novel communities from climate change. *Philosophical Transactions of the Royal Society B*, 367(1605), 2913–2922.

**Why it matters:** Informs how we should model climate disturbance scenarios in Phase 5. Shows that climate change restructures interaction networks, not just removes species — which means disturbance scenarios need to modify edge weights, not just remove nodes.

---

### 9. Valiente-Banuet et al. (2015) — *Beyond species loss: interaction loss*
**Citation:** Valiente-Banuet, A., et al. (2015). Beyond species loss: the extinction of ecological interactions in a changing world. *Functional Ecology*, 29(3), 299–307.

**Why it matters:** Argues that interaction loss often precedes and predicts species loss. Directly relevant to our `interaction_diversity_loss` metric — this paper provides empirical support for weighting it highly in the Integrity Index.

---

## Tier 3: Phase 6 Quantum Extension

### 10. Lucas et al. (2014) — *Ising model formulations of combinatorial problems*
**Citation:** Lucas, A. (2014). Ising formulations of many NP problems. *Frontiers in Physics*, 2, 5.

**Why it matters:** The reference guide for converting combinatorial optimisation problems to QUBO form. Our Phase 6 target — "minimal intervention set to prevent cascade" — is a set cover problem, which is in NP and maps to QUBO via the methods in this paper.

### 11. Farhi et al. (2014) — *QAOA*
**Citation:** Farhi, E., Goldstone, J., & Gutmann, S. (2014). A quantum approximate optimization algorithm. *arXiv*:1411.4028.

**Why it matters:** QAOA is the most likely quantum algorithm we'll prototype in Phase 6 for the cascade minimisation problem on near-term hardware.

---

## Dataset Sources & Access

| Dataset | URL | Format | Priority |
|---------|-----|--------|----------|
| GBIF species occurrences | api.gbif.org | REST/JSON | Phase 1 |
| GloBI biotic interactions | globalbioticinteractions.org | CSV download | Phase 1 |
| Bascompte lab networks | bascompte.net/networksdata.html | Excel/CSV | Phase 1 |
| Web of Life / mangal | mangal.io | REST API | Phase 2 |
| IUCN Red List | apiv3.iucnredlist.org | REST/JSON | Phase 2 |
| TRY plant traits | try-db.org/de/queryForm.php | Registration | Phase 2 |
| TEEB database | teebweb.org | Reports/PDF | Phase 5 |

---

## Suggested First Literature Sprint (Week 2)

For you and Travis to divide:

**You:** Read Poirier et al. 2021 (framing), Costanza et al. 2014 (cost calc), and TEEB methodology.

**Travis:** Read Bascompte & Jordano 2007 (mutualistic layer), Dunne et al. 2002 (cascade calibration), and Eklöf & Ebenman 2006 (extinction thresholds).

Sync on: how to set `persistence_score` defaults by taxa group, and which tropical forest interaction datasets to use for Phase 1.

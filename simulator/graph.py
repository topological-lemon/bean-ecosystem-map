"""
Bud Ecosystem Quantum Map — Core Simulator
==========================================
MultilayerGraph, CascadeSimulator, MetricsEngine, IntegrityIndex.

Phase 1 implementation: supports N layers, probabilistic cascades,
and the full metrics suite described in the project brief.

Dependencies: networkx, numpy, pandas
"""

from __future__ import annotations
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Species:
    id: str
    scientific_name: str
    common_name: str
    taxa_group: str
    trophic_level: float
    persistence_score: float = 0.8
    redundancy_factor: float = 0.3
    recovery_potential: str = "medium"
    keystone_candidate: bool = False
    iucn_status: str = "LC"
    attributes: dict = field(default_factory=dict)

    def __post_init__(self):
        self.persistence_score = max(0.0, min(1.0, self.persistence_score))
        self.redundancy_factor = max(0.0, min(1.0, self.redundancy_factor))


@dataclass
class Interaction:
    id: str
    source: str
    target: str
    interaction_type: str
    layer: str
    strength: float = 0.5
    obligate: bool = False
    effect_on_source: float = 0.0
    effect_on_target: float = -1.0
    confidence_score: float = 0.8


@dataclass
class CascadeResult:
    removed_species: list[str]
    extinct_species: list[str]
    cascade_steps: list[dict]
    metrics: dict
    integrity_score: float
    integrity_delta: float
    estimated_cost_usd: float


# ─────────────────────────────────────────────────────────────────────────────
# MultilayerGraph
# ─────────────────────────────────────────────────────────────────────────────

class MultilayerGraph:
    """
    Represents an ecosystem as a set of named interaction layers,
    each a directed NetworkX graph. Nodes (species) are shared across layers.
    """

    def __init__(self, ecosystem_name: str = "Unnamed Ecosystem"):
        self.ecosystem_name = ecosystem_name
        self.species: dict[str, Species] = {}
        self.layers: dict[str, nx.DiGraph] = {}
        self.layer_metadata: dict[str, dict] = {}
        self.interactions: list[Interaction] = []

    # ── Loading ────────────────────────────────────────────────────────────

    @classmethod
    def from_json_files(
        cls,
        species_path: str | Path,
        interactions_path: str | Path,
        layers_path: str | Path,
        ecosystem_name: str = "Ecosystem",
    ) -> "MultilayerGraph":
        g = cls(ecosystem_name)
        with open(species_path) as f:
            for s in json.load(f):
                g.add_species(Species(
                    id=s["id"],
                    scientific_name=s["scientific_name"],
                    common_name=s.get("common_name", s["scientific_name"]),
                    taxa_group=s.get("taxa_group", "other"),
                    trophic_level=s.get("trophic_level", 1.0),
                    persistence_score=s.get("persistence_score", 0.8),
                    redundancy_factor=s.get("redundancy_factor", 0.3),
                    recovery_potential=s.get("recovery_potential", "medium"),
                    keystone_candidate=s.get("keystone_candidate", False),
                    iucn_status=s.get("iucn_status", "LC"),
                    attributes=s,
                ))
        with open(layers_path) as f:
            for layer in json.load(f):
                g.add_layer(layer["id"], layer)
        with open(interactions_path) as f:
            for i in json.load(f):
                g.add_interaction(Interaction(
                    id=i["id"],
                    source=i["source_species_id"],
                    target=i["target_species_id"],
                    interaction_type=i["interaction_type"],
                    layer=i["layer"],
                    strength=i.get("strength", 0.5),
                    obligate=i.get("obligate", False),
                    effect_on_source=i.get("effect_on_source", 0.0),
                    effect_on_target=i.get("effect_on_target", -1.0),
                    confidence_score=i.get("confidence_score", 0.8),
                ))
        return g

    # ── Mutating ───────────────────────────────────────────────────────────

    def add_species(self, species: Species) -> None:
        self.species[species.id] = species
        for layer in self.layers.values():
            layer.add_node(species.id)

    def add_layer(self, layer_id: str, metadata: dict | None = None) -> None:
        g = nx.DiGraph()
        for sp_id in self.species:
            g.add_node(sp_id)
        self.layers[layer_id] = g
        self.layer_metadata[layer_id] = metadata or {}

    def add_interaction(self, interaction: Interaction) -> None:
        if interaction.layer not in self.layers:
            self.add_layer(interaction.layer)
        self.layers[interaction.layer].add_edge(
            interaction.source,
            interaction.target,
            strength=interaction.strength,
            obligate=interaction.obligate,
            effect_on_target=interaction.effect_on_target,
            confidence_score=interaction.confidence_score,
            interaction_type=interaction.interaction_type,
        )
        self.interactions.append(interaction)

    # ── Queries ────────────────────────────────────────────────────────────

    def get_dependents(self, species_id: str, layer: str | None = None) -> dict[str, list[str]]:
        """Return species that depend on species_id, keyed by layer."""
        result: dict[str, list[str]] = {}
        layers = [layer] if layer else list(self.layers.keys())
        for l in layers:
            g = self.layers[l]
            if species_id not in g:
                continue
            deps = list(g.successors(species_id))
            if deps:
                result[l] = deps
        return result

    def get_interaction_diversity(self, active_species: set[str]) -> float:
        """Count distinct interaction types present among active species."""
        types = set()
        for intr in self.interactions:
            if intr.source in active_species and intr.target in active_species:
                types.add(intr.interaction_type)
        return len(types)

    def flatten_to_monolayer(self) -> nx.DiGraph:
        """Aggregate all layers into a single weighted graph (monolayer baseline)."""
        mono = nx.DiGraph()
        for sp_id in self.species:
            mono.add_node(sp_id)
        for layer_id, g in self.layers.items():
            cw = self.layer_metadata.get(layer_id, {}).get("cascade_weight", 1.0)
            for u, v, data in g.edges(data=True):
                if mono.has_edge(u, v):
                    mono[u][v]["strength"] = max(mono[u][v]["strength"], data["strength"] * cw)
                else:
                    mono.add_edge(u, v, strength=data["strength"] * cw)
        return mono

    def active_species(self, extinct: set[str] | None = None) -> set[str]:
        extinct = extinct or set()
        return set(self.species.keys()) - extinct

    def species_count(self) -> int:
        return len(self.species)

    def interaction_count(self, active: set[str] | None = None) -> int:
        active = active or set(self.species.keys())
        return sum(
            1 for i in self.interactions
            if i.source in active and i.target in active
        )


# ─────────────────────────────────────────────────────────────────────────────
# CascadeSimulator
# ─────────────────────────────────────────────────────────────────────────────

class CascadeSimulator:
    """
    Simulates extinction cascades on a MultilayerGraph.

    Cascade logic (empirically grounded, see docs/model_assumptions.md):
    - Species lose persistence when interaction partners are removed
    - Extinction probability = f(persistence_score, obligate_loss, redundancy)
    - Cascades propagate iteratively until stable state or full collapse
    - Stochastic: run multiple trials for probabilistic output
    """

    RECOVERY_MULTIPLIERS = {
        "very_low": 0.1, "low": 0.3, "medium": 0.5, "high": 0.8
    }

    def __init__(self, graph: MultilayerGraph, seed: int = 42):
        self.graph = graph
        self.rng = random.Random(seed)

    def simulate(
        self,
        removed_species: list[str],
        multilayer: bool = True,
        n_trials: int = 50,
        max_steps: int = 20,
    ) -> CascadeResult:
        """
        Run the cascade simulation.

        Args:
            removed_species: Species IDs to remove as the initial disturbance.
            multilayer: If False, runs on the flattened monolayer graph.
            n_trials: Number of stochastic trials to average over.
            max_steps: Maximum cascade propagation steps.

        Returns:
            CascadeResult with mean extinction list and all metrics.
        """
        trial_extinctions: list[set[str]] = []
        trial_steps: list[list[dict]] = []

        for _ in range(n_trials):
            extinct, steps = self._single_trial(removed_species, multilayer, max_steps)
            trial_extinctions.append(extinct)
            trial_steps.append(steps)

        # Consensus extinctions: species extinct in > 50% of trials
        sp_ids = set(self.graph.species.keys())
        extinct_counts = {sp: 0 for sp in sp_ids}
        for trial in trial_extinctions:
            for sp in trial:
                extinct_counts[sp] += 1

        consensus_extinct = {
            sp for sp, count in extinct_counts.items()
            if count > n_trials * 0.5
        } | set(removed_species)

        # Pick the trial closest to median extinction count for step-by-step output
        median_n = sorted(len(t) for t in trial_extinctions)[n_trials // 2]
        best_trial = min(trial_steps, key=lambda s: abs(
            sum(len(step.get("newly_extinct", [])) for step in s) + len(removed_species) - median_n
        ))

        baseline_metrics = MetricsEngine.compute(self.graph, set(), set())
        post_metrics = MetricsEngine.compute(self.graph, set(removed_species), consensus_extinct)
        integrity_before = IntegrityIndex.compute(baseline_metrics)
        integrity_after = IntegrityIndex.compute(post_metrics)

        cost = CostCalculator.estimate_usd(
            ecosystem_name=self.graph.ecosystem_name,
            integrity_delta=integrity_before - integrity_after,
        )

        return CascadeResult(
            removed_species=list(removed_species),
            extinct_species=sorted(consensus_extinct - set(removed_species)),
            cascade_steps=best_trial,
            metrics=post_metrics,
            integrity_score=integrity_after,
            integrity_delta=integrity_before - integrity_after,
            estimated_cost_usd=cost,
        )

    def _single_trial(
        self,
        removed_species: list[str],
        multilayer: bool,
        max_steps: int,
    ) -> tuple[set[str], list[dict]]:
        extinct = set(removed_species)
        steps = []

        for step_n in range(max_steps):
            newly_extinct: set[str] = set()
            active = self.graph.active_species(extinct)

            for sp_id in active:
                species = self.graph.species[sp_id]
                stress = self._compute_stress(sp_id, extinct, multilayer)
                if stress == 0:
                    continue

                # Redundancy buffering: square-rooted so high-redundancy
                # species are still vulnerable when stress is severe
                # (linear formulation made keystone-dependent species
                # implausibly resistant).
                buffered_stress = stress * (1 - species.redundancy_factor ** 0.5)

                # Extinction probability: square-rooted persistence response
                # for the same reason — gives biologically realistic
                # extinction frequencies under maximum stress.
                ext_prob = buffered_stress * ((1 - species.persistence_score) ** 0.5)

                # Recovery potential dampens extinction probability,
                # but only on cascade steps after the first. Recovery_potential
                # describes whether species rebound from disturbance over time,
                # not whether they survive the initial loss of partners.
                if step_n > 0:
                    recovery_mult = self.RECOVERY_MULTIPLIERS.get(species.recovery_potential, 0.5)
                    ext_prob *= (1 - recovery_mult * 0.3)

                if self.rng.random() < ext_prob:
                    newly_extinct.add(sp_id)

            if not newly_extinct:
                break

            steps.append({
                "step": step_n + 1,
                "newly_extinct": list(newly_extinct),
                "total_extinct_so_far": len(extinct) + len(newly_extinct),
            })
            extinct |= newly_extinct

        return extinct, steps

    def _compute_stress(self, species_id: str, extinct: set[str], multilayer: bool) -> float:
        """
        Compute the stress on a species given the current set of extinct species.
        Stress accumulates across all layers in multilayer mode.
        """
        total_stress = 0.0
        layers_to_check = list(self.graph.layers.items()) if multilayer else [
            ("_mono", self.graph.flatten_to_monolayer())
        ]

        for layer_id, g in layers_to_check:
            if species_id not in g:
                continue
            cw = self.graph.layer_metadata.get(layer_id, {}).get("cascade_weight", 1.0)
            in_edges = list(g.in_edges(species_id, data=True))
            if not in_edges:
                continue

            for source, _, data in in_edges:
                if source in extinct:
                    # Only positive-effect partners contribute to stress
                    # when lost. A plant losing its disperser is stressed;
                    # losing its herbivore/seed-predator is not.
                    effect = data.get("effect_on_target", "positive")
                    if effect == "negative":
                        continue
                    strength = data.get("strength", 0.5)
                    obligate_mult = 2.0 if data.get("obligate", False) else 1.0
                    # Square-root the per-partner contribution: losing the
                    # largest partner should dominate the signal rather than
                    # being diluted by smaller partners.
                    total_stress += (strength * obligate_mult * cw) ** 0.5

        # Normalise by this species' own incoming-edge capacity
        # (sum of all incoming strengths across all layers).
        # This makes the loss of a single keystone partner read as
        # high stress in proportion to that species' total support network.
        max_possible = 0.0
        for layer_id, g in (
            list(self.graph.layers.items()) if multilayer
            else [("_mono", self.graph.flatten_to_monolayer())]
        ):
            if species_id not in g:
                continue
            cw = self.graph.layer_metadata.get(layer_id, {}).get("cascade_weight", 1.0)
            for _, _, data in g.in_edges(species_id, data=True):
                # Mirror the stress filter: only positive-effect edges
                # contribute to the support-network capacity for normalisation.
                effect = data.get("effect_on_target", "positive")
                if effect == "negative":
                    continue
                strength = data.get("strength", 0.5)
                obligate_mult = 2.0 if data.get("obligate", False) else 1.0
                max_possible += strength * obligate_mult * cw

        # Sqrt-normalised: matches the sqrt sum of contributions above.
        # This keeps the [0, 1] range while rewarding loss of high-strength
        # partners more than loss of an equivalent number of weak partners.
        if max_possible < 0.01:
            return 0.0
        sqrt_max_possible = max_possible ** 0.5
        return min(1.0, total_stress / sqrt_max_possible)

    def compare_multilayer_vs_monolayer(
        self,
        removed_species: list[str],
        n_trials: int = 50,
    ) -> dict:
        """Run both modes and return a comparison dict."""
        multi = self.simulate(removed_species, multilayer=True, n_trials=n_trials)
        mono = self.simulate(removed_species, multilayer=False, n_trials=n_trials)
        hidden = set(multi.extinct_species) - set(mono.extinct_species)
        return {
            "multilayer_extinctions": len(multi.extinct_species),
            "monolayer_extinctions": len(mono.extinct_species),
            "hidden_cascade_events": len(hidden),
            "hidden_species": sorted(hidden),
            "multilayer_integrity_score": multi.integrity_score,
            "monolayer_integrity_score": mono.integrity_score,
            "multilayer_cost_usd": multi.estimated_cost_usd,
            "monolayer_cost_usd": mono.estimated_cost_usd,
        }


# ─────────────────────────────────────────────────────────────────────────────
# MetricsEngine
# ─────────────────────────────────────────────────────────────────────────────

class MetricsEngine:

    @staticmethod
    def compute(
        graph: MultilayerGraph,
        removed: set[str],
        extinct: set[str],
    ) -> dict:
        """Compute the full suite of ecological metrics."""
        all_lost = removed | extinct
        active = graph.active_species(all_lost)
        total = graph.species_count()

        # Extinction count
        extinction_count = len(all_lost)
        extinction_fraction = extinction_count / max(1, total)

        # Cascade depth (longest chain that went extinct)
        cascade_depth = MetricsEngine._cascade_depth(graph, removed, extinct)

        # Connectivity retained
        original_interactions = graph.interaction_count()
        remaining_interactions = graph.interaction_count(active)
        connectivity_loss = 1 - (remaining_interactions / max(1, original_interactions))

        # Interaction diversity loss
        original_diversity = graph.get_interaction_diversity(set(graph.species.keys()))
        remaining_diversity = graph.get_interaction_diversity(active)
        interaction_diversity_loss = 1 - (remaining_diversity / max(1, original_diversity))

        # Robustness score (fraction of species still present after cascade)
        robustness = len(active) / max(1, total)

        # Keystone centrality shift
        keystone_loss_fraction = MetricsEngine._keystone_loss(graph, all_lost)

        return {
            "extinction_count": extinction_count,
            "extinction_fraction": round(extinction_fraction, 4),
            "cascade_depth": cascade_depth,
            "connectivity_loss": round(connectivity_loss, 4),
            "interaction_diversity_loss": round(interaction_diversity_loss, 4),
            "robustness_score": round(robustness, 4),
            "keystone_centrality_shift": round(keystone_loss_fraction, 4),
            "species_remaining": len(active),
            "species_total": total,
            "interactions_remaining": remaining_interactions,
            "interactions_original": original_interactions,
        }

    @staticmethod
    def _cascade_depth(graph: MultilayerGraph, removed: set[str], extinct: set[str]) -> int:
        """Approximate cascade depth as longest path through extinct species."""
        all_lost = removed | extinct
        max_depth = 0
        for layer_g in graph.layers.values():
            for sp in removed:
                if sp not in layer_g:
                    continue
                try:
                    for target in all_lost:
                        if target != sp:
                            try:
                                path_length = nx.shortest_path_length(layer_g, sp, target)
                                max_depth = max(max_depth, path_length)
                            except (nx.NetworkXNoPath, nx.NodeNotFound):
                                pass
                except Exception:
                    pass
        return max_depth

    @staticmethod
    def _keystone_loss(graph: MultilayerGraph, lost: set[str]) -> float:
        """Fraction of keystone-candidate species that are lost."""
        keystones = {sp_id for sp_id, sp in graph.species.items() if sp.keystone_candidate}
        if not keystones:
            return 0.0
        return len(lost & keystones) / len(keystones)


# ─────────────────────────────────────────────────────────────────────────────
# IntegrityIndex
# ─────────────────────────────────────────────────────────────────────────────

class IntegrityIndex:
    """
    Composite Ecological Integrity Index (0–100).

    Sub-metric weights (sum to 1.0):
      - Robustness score:           0.25
      - Connectivity loss:          0.20
      - Interaction diversity loss: 0.20
      - Extinction fraction:        0.15
      - Cascade depth (norm):       0.10
      - Keystone centrality shift:  0.10

    Design principle: weights informed by ecological literature on
    functional redundancy and ecosystem stability (see docs/model_assumptions.md).
    These weights are configurable — future versions will allow user adjustment.
    """

    WEIGHTS = {
        "robustness_score": 0.25,
        "connectivity_retained": 0.20,
        "interaction_diversity_retained": 0.20,
        "species_retained": 0.15,
        "cascade_depth_norm": 0.10,
        "keystone_retained": 0.10,
    }

    MAX_CASCADE_DEPTH = 10  # normalisation constant

    @classmethod
    def compute(cls, metrics: dict) -> float:
        """Compute integrity score 0–100 from metrics dict."""
        sub = {
            "robustness_score": metrics.get("robustness_score", 1.0),
            "connectivity_retained": 1 - metrics.get("connectivity_loss", 0.0),
            "interaction_diversity_retained": 1 - metrics.get("interaction_diversity_loss", 0.0),
            "species_retained": 1 - metrics.get("extinction_fraction", 0.0),
            "cascade_depth_norm": 1 - min(1, metrics.get("cascade_depth", 0) / cls.MAX_CASCADE_DEPTH),
            "keystone_retained": 1 - metrics.get("keystone_centrality_shift", 0.0),
        }
        score = sum(sub[k] * cls.WEIGHTS[k] for k in cls.WEIGHTS)
        return round(score * 100, 2)


# ─────────────────────────────────────────────────────────────────────────────
# CostCalculator
# ─────────────────────────────────────────────────────────────────────────────

class CostCalculator:
    """
    Estimates the annual financial cost of ecosystem integrity loss.

    Values are derived from:
    - Costanza et al. (2014) — Changes in the global value of ecosystem services.
      Global Environmental Change, 26, 152–158. DOI: 10.1016/j.gloenvcha.2014.04.002
    - TEEB (2010) — The Economics of Ecosystems and Biodiversity: Mainstreaming
      the Economics of Nature.

    Annual ecosystem services value per hectare (2011 USD, by biome):
    These are conservative central estimates. Significant uncertainty exists.
    """

    # USD/ha/year (Costanza et al. 2014, Table 2, mean values)
    BIOME_VALUES_USD_HA_YEAR = {
        "tropical_forest": 5382,
        "mangrove": 193_843,
        "coral_reef": 352_249,
        "temperate_forest": 3137,
        "grassland": 2871,
        "wetland": 140_174,
        "coastal": 28_916,
        "kelp_forest": 58_000,
        "savanna": 1588,
        "default": 4000,
    }

    # Approximate biome areas in million ha (rough estimates for scaling)
    BIOME_AREAS_MHA = {
        "tropical_forest": 1_750,
        "mangrove": 15,
        "coral_reef": 25,
        "temperate_forest": 1_040,
        "grassland": 3_400,
        "wetland": 1_280,
        "coastal": 150,
        "kelp_forest": 30,
        "savanna": 2_780,
        "default": 500,
    }

    @classmethod
    def estimate_usd(
        cls,
        ecosystem_name: str,
        integrity_delta: float,
        area_ha: float | None = None,
    ) -> float:
        """
        Estimate annual cost of integrity loss in USD.

        Args:
            ecosystem_name: Used to look up biome value.
            integrity_delta: Points of integrity lost (0–100 scale).
            area_ha: Ecosystem area in hectares. If None, uses default for biome.

        Returns:
            Estimated annual cost in USD.
        """
        biome_key = cls._map_ecosystem_to_biome(ecosystem_name)
        value_per_ha = cls.BIOME_VALUES_USD_HA_YEAR.get(biome_key, cls.BIOME_VALUES_USD_HA_YEAR["default"])

        if area_ha is None:
            area_ha = cls.BIOME_AREAS_MHA.get(biome_key, cls.BIOME_AREAS_MHA["default"]) * 1_000  # sample 1000 ha

        fraction_lost = integrity_delta / 100.0
        return round(value_per_ha * area_ha * fraction_lost, 2)

    @staticmethod
    def _map_ecosystem_to_biome(name: str) -> str:
        name = name.lower()
        if any(w in name for w in ["tropical", "rainforest", "amazon"]):
            return "tropical_forest"
        if "mangrove" in name:
            return "mangrove"
        if "coral" in name:
            return "coral_reef"
        if "temperate" in name or "boreal" in name:
            return "temperate_forest"
        if "grassland" in name or "prairie" in name:
            return "grassland"
        if "wetland" in name or "marsh" in name:
            return "wetland"
        if "kelp" in name:
            return "kelp_forest"
        if "savanna" in name:
            return "savanna"
        return "default"


# ─────────────────────────────────────────────────────────────────────────────
# Quick smoke test
# ─────────────────────────────────────────────────────────────────────────────

def _smoke_test():
    """Build a tiny synthetic graph and run a cascade."""
    g = MultilayerGraph("Amazon Tropical Forest")

    species_data = [
        ("sp_001", "Panthera onca", "Jaguar", "mammal", 4.0, 0.7, 0.1, True),
        ("sp_002", "Mazama americana", "Red brocket deer", "mammal", 3.0, 0.8, 0.4, False),
        ("sp_003", "Ateles paniscus", "Black spider monkey", "mammal", 2.5, 0.7, 0.3, True),
        ("sp_004", "Ficus insipida", "Fig tree", "plant", 1.0, 0.9, 0.5, True),
        ("sp_005", "Eulaema meriana", "Orchid bee", "invertebrate", 2.0, 0.6, 0.4, False),
        ("sp_006", "Heliconia latispatha", "Heliconia", "plant", 1.0, 0.85, 0.6, False),
    ]
    for sp_id, sci, common, taxa, tl, ps, rf, kc in species_data:
        g.add_species(Species(sp_id, sci, common, taxa, tl, ps, rf, keystone_candidate=kc))

    g.add_layer("trophic", {"cascade_weight": 0.9})
    g.add_layer("mutualistic", {"cascade_weight": 0.7})

    interactions = [
        Interaction("i01", "sp_001", "sp_002", "predation", "trophic", 0.8, True),
        Interaction("i02", "sp_001", "sp_003", "predation", "trophic", 0.5, False),
        Interaction("i03", "sp_002", "sp_004", "herbivory", "trophic", 0.6, False),
        Interaction("i04", "sp_004", "sp_003", "seed_dispersal", "mutualistic", 0.9, True),
        Interaction("i05", "sp_005", "sp_006", "pollination", "mutualistic", 0.95, True),
        Interaction("i06", "sp_003", "sp_005", "habitat_facilitation", "mutualistic", 0.4, False),
    ]
    for intr in interactions:
        g.add_interaction(intr)

    sim = CascadeSimulator(g)

    print("=== Cascade from removing Jaguar (sp_001) ===")
    result = sim.simulate(["sp_001"], multilayer=True, n_trials=30)
    print(f"  Extinct species: {result.extinct_species}")
    print(f"  Integrity score: {result.integrity_score}/100")
    print(f"  Integrity delta: -{result.integrity_delta:.1f} points")
    print(f"  Est. cost: USD {result.estimated_cost_usd:,.0f}/year")
    print(f"  Metrics: {result.metrics}")

    print("\n=== Multilayer vs Monolayer comparison ===")
    comparison = sim.compare_multilayer_vs_monolayer(["sp_004"])
    for k, v in comparison.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    _smoke_test()

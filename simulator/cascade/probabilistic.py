"""
probabilistic.py
================
Wraps CascadeSimulator to expose probabilistic cascade output rather than
consensus-filtered extinction lists. This is what the demo presents and
what we feed Gemma as RAG context.
"""

from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field

from simulator.graph import (
    MultilayerGraph,
    CascadeSimulator,
    MetricsEngine,
    IntegrityIndex,
    CostCalculator,
)


@dataclass
class SpeciesAtRisk:
    species_id: str
    scientific_name: str
    common_name: str
    extinction_probability: float  # 0..1
    iucn_status: str
    keystone_candidate: bool
    primary_loss_layer: str  # which layer drove the cascade

    def __str__(self):
        return (
            f"{self.scientific_name} ({self.common_name}): "
            f"{self.extinction_probability:.0%} risk, IUCN {self.iucn_status}"
        )


@dataclass
class CascadeBrief:
    """Structured output of a probabilistic cascade run.

    Designed both as a programmatic record AND as RAG context for Gemma:
    every field is a string or simple value Gemma can parse and narrate.
    """
    ecosystem_name: str
    removed_species: list[str]
    removed_scientific_names: list[str]
    n_trials: int

    species_at_risk: list[SpeciesAtRisk]
    layer_cascade_counts: dict[str, int]  # which layers did cascades flow through

    integrity_baseline: float
    integrity_mean_after: float
    integrity_delta_mean: float

    estimated_cost_usd_mean: float

    mean_cascade_size: float
    max_cascade_size: int

    notes: list[str] = field(default_factory=list)


def run_probabilistic_cascade(
    graph: MultilayerGraph,
    removed_species_ids: list[str],
    n_trials: int = 200,
    risk_threshold: float = 0.05,
) -> CascadeBrief:
    """
    Run n_trials of the cascade simulation and return a probabilistic brief.

    Args:
        graph: loaded MultilayerGraph
        removed_species_ids: list of species IDs to remove as initial disturbance
        n_trials: Monte Carlo iterations
        risk_threshold: minimum probability to include in species_at_risk
    """
    sim = CascadeSimulator(graph)

    extinction_counter = Counter()
    cascade_sizes = []
    layer_cascade_counts = Counter()
    integrities_after = []
    deltas = []
    costs = []

    for _ in range(n_trials):
        extinct, steps = sim._single_trial(
            removed_species_ids,
            multilayer=True,
            max_steps=20,
        )
        cascade_sizes.append(len(extinct) - len(removed_species_ids))

        for sp_id in extinct:
            if sp_id not in removed_species_ids:
                extinction_counter[sp_id] += 1

                # Track which layer drove this species's loss
                # (its strongest positive incoming edge from an extinct partner)
                best_layer = None
                best_strength = 0
                for layer_id, layer_g in graph.layers.items():
                    if sp_id not in layer_g:
                        continue
                    for src, _, data in layer_g.in_edges(sp_id, data=True):
                        if src in extinct and data.get("effect_on_target") != "negative":
                            s = data.get("strength", 0.5)
                            if s > best_strength:
                                best_strength = s
                                best_layer = layer_id
                if best_layer:
                    layer_cascade_counts[best_layer] += 1

        # Per-trial metrics
        baseline_metrics = MetricsEngine.compute(graph, set(), set())
        post_metrics = MetricsEngine.compute(
            graph, set(removed_species_ids), extinct
        )
        integrity_before = IntegrityIndex.compute(baseline_metrics)
        integrity_after = IntegrityIndex.compute(post_metrics)
        integrities_after.append(integrity_after)
        deltas.append(integrity_before - integrity_after)
        costs.append(CostCalculator.estimate_usd(
            ecosystem_name=graph.ecosystem_name,
            integrity_delta=integrity_before - integrity_after,
        ))

    # Build species_at_risk list
    species_at_risk = []
    for sp_id, count in extinction_counter.most_common():
        prob = count / n_trials
        if prob < risk_threshold:
            continue
        sp = graph.species[sp_id]

        # Find which layer most often drove this species's cascade
        # (we'll do a lighter computation: just look at the species's strongest
        # positive in-edge from a removed species)
        primary_layer = "unknown"
        best_strength = 0
        for layer_id, layer_g in graph.layers.items():
            if sp_id not in layer_g:
                continue
            for src, _, data in layer_g.in_edges(sp_id, data=True):
                if src in removed_species_ids and data.get("effect_on_target") != "negative":
                    s = data.get("strength", 0.5)
                    if s > best_strength:
                        best_strength = s
                        primary_layer = layer_id

        species_at_risk.append(SpeciesAtRisk(
            species_id=sp_id,
            scientific_name=sp.scientific_name,
            common_name=sp.common_name,
            extinction_probability=prob,
            iucn_status=sp.iucn_status,
            keystone_candidate=sp.keystone_candidate,
            primary_loss_layer=primary_layer,
        ))

    # Removed species names
    removed_names = [
        graph.species[sid].scientific_name for sid in removed_species_ids
    ]

    return CascadeBrief(
        ecosystem_name=graph.ecosystem_name,
        removed_species=removed_species_ids,
        removed_scientific_names=removed_names,
        n_trials=n_trials,
        species_at_risk=species_at_risk,
        layer_cascade_counts=dict(layer_cascade_counts),
        integrity_baseline=IntegrityIndex.compute(
            MetricsEngine.compute(graph, set(), set())
        ),
        integrity_mean_after=sum(integrities_after) / len(integrities_after),
        integrity_delta_mean=sum(deltas) / len(deltas),
        estimated_cost_usd_mean=sum(costs) / len(costs),
        mean_cascade_size=sum(cascade_sizes) / len(cascade_sizes),
        max_cascade_size=max(cascade_sizes),
    )


def format_brief_for_human(brief: CascadeBrief) -> str:
    """Pretty-print the brief for terminal/console viewing."""
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"CASCADE BRIEF: {brief.ecosystem_name}")
    lines.append(f"{'='*70}")
    lines.append(f"Initial removal: {', '.join(brief.removed_scientific_names)}")
    lines.append(f"Monte Carlo: {brief.n_trials} trials")
    lines.append("")
    lines.append(f"Cascade size: mean {brief.mean_cascade_size:.2f}, "
                 f"max {brief.max_cascade_size}")
    lines.append(f"Integrity: {brief.integrity_baseline:.1f} (baseline) → "
                 f"{brief.integrity_mean_after:.1f} (mean after) "
                 f"[Δ {brief.integrity_delta_mean:.1f}]")
    lines.append(f"Estimated ecosystem-services cost: "
                 f"${brief.estimated_cost_usd_mean:,.0f}")
    lines.append("")

    if brief.species_at_risk:
        lines.append(f"Species at elevated extinction risk:")
        for s in brief.species_at_risk:
            keystone_mark = " ★" if s.keystone_candidate else ""
            lines.append(f"  {s.extinction_probability:5.0%}  "
                        f"{s.scientific_name:32s} "
                        f"({s.common_name[:25]:25s})  "
                        f"IUCN {s.iucn_status}{keystone_mark}  "
                        f"[via {s.primary_loss_layer}]")
    else:
        lines.append("No species at elevated extinction risk (>5%).")

    lines.append("")
    if brief.layer_cascade_counts:
        lines.append("Cascade flowed primarily through these layers:")
        for layer, count in sorted(
            brief.layer_cascade_counts.items(), key=lambda x: -x[1]
        ):
            lines.append(f"  {layer:25s}  {count} cascade events")

    return "\n".join(lines)


# ── Entry point for testing ────────────────────────────────────────────────

if __name__ == "__main__":
    g = MultilayerGraph.from_json_files(
        species_path="data/processed/sabangau/species.json",
        interactions_path="data/processed/sabangau/interactions.json",
        layers_path="data/processed/sabangau/layers.json",
        ecosystem_name="Sabangau Peat-Swamp Forest",
    )

    # Find species IDs
    orangutan = next(sid for sid, sp in g.species.items()
                     if sp.scientific_name == "Pongo pygmaeus wurmbii")
    control = next(sid for sid, sp in g.species.items()
                   if sp.scientific_name == "Macaca fascicularis")

    brief_orangutan = run_probabilistic_cascade(g, [orangutan], n_trials=200)
    print(format_brief_for_human(brief_orangutan))

    brief_control = run_probabilistic_cascade(g, [control], n_trials=200)
    print(format_brief_for_human(brief_control))

"""
narrator.py
===========
Bridges the cascade engine and Gemma. Takes a CascadeBrief, constructs
a structured prompt with full ecological context, calls Gemma, returns
narrative suitable for the demo.

The prompt design is RAG-style: Gemma narrates the structured cascade
data rather than relying on its parametric knowledge of Bornean peat-swamp
ecology (which is thin and prone to species-level errors).
"""

from __future__ import annotations
from dataclasses import dataclass

from simulator.cascade.probabilistic import CascadeBrief
from simulator.llm.gemma_client import generate


SYSTEM_INSTRUCTION = (
    "You are an ecologist explaining cascade dynamics in the Sabangau "
    "peat-swamp forest of Central Kalimantan, Borneo. Your audience is "
    "policy makers and conservation practitioners. You speak plainly but "
    "scientifically. You name specific species and specific ecological "
    "mechanisms. You do not invent species or facts not present in the "
    "cascade brief. When you cannot infer a mechanism from the brief, "
    "you say so."
)


def build_prompt(brief: CascadeBrief) -> str:
    """Construct a Gemma prompt from a cascade brief."""

    removed_str = ", ".join(brief.removed_scientific_names)

    risk_lines = []
    for s in brief.species_at_risk:
        keystone = " (keystone candidate)" if s.keystone_candidate else ""
        risk_lines.append(
            f"  - {s.scientific_name} ({s.common_name}): "
            f"{s.extinction_probability:.0%} probability of extinction, "
            f"IUCN status {s.iucn_status}{keystone}, "
            f"primary cascade pathway via the {s.primary_loss_layer} layer"
        )
    risk_block = "\n".join(risk_lines) if risk_lines else "  None"

    layer_lines = []
    for layer, count in sorted(
        brief.layer_cascade_counts.items(), key=lambda x: -x[1]
    ):
        layer_lines.append(f"  - {layer}: {count} cascade events across trials")
    layer_block = "\n".join(layer_lines) if layer_lines else "  No cascade flow detected"

    prompt = f"""I am running a multilayer ecological cascade simulator for the Sabangau peat-swamp forest in Central Kalimantan, Borneo. The simulator models 31 species across four interaction layers: trophic (predation/herbivory), mutualism_dispersal (animal-mediated seed dispersal), mutualism_pollination (pollinator-plant), and facilitation (mycorrhizal seedling establishment, nest tree provision, hornbill cavity nesting).

I just ran a Monte Carlo cascade simulation ({brief.n_trials} trials) with the following scenario.

INITIAL DISTURBANCE
The species removed from the network: {removed_str}

CASCADE OUTCOMES
Mean secondary extinctions per trial: {brief.mean_cascade_size:.2f}
Maximum cascade size observed: {brief.max_cascade_size} species
Network integrity: {brief.integrity_baseline:.0f} → {brief.integrity_mean_after:.0f} (drop of {brief.integrity_delta_mean:.1f} points)
Estimated ecosystem services cost: ${brief.estimated_cost_usd_mean:,.0f}

SPECIES AT ELEVATED EXTINCTION RISK (>5% probability across trials):
{risk_block}

CASCADE PATHWAYS
The cascade flowed primarily through these interaction layers:
{layer_block}

YOUR TASK
Please write a focused, plain-language brief of 150-200 words explaining what this cascade tells us about the role of the removed species in the Sabangau forest. Specifically:

1. What ecological function does the removed species perform in this network?
2. Why do these specific other species end up at risk? Name them and explain the mechanism.
3. What is the conservation implication? What would happen on the ground at Sabangau over the next 10-20 years if this species were lost?

Do not invent species, kernels, or studies that are not represented in the cascade brief. Where the brief says a cascade pathway is "unknown", explain that the cascade was indirect (via secondary extinctions) rather than fabricating a direct mechanism.
"""

    return prompt


# max_tokens default tuned for e2b on local hardware (constrained RAM,
# slow generation). On HF Spaces with 26b on H200 we can lift this.
def narrate(brief: CascadeBrief, max_tokens: int = 700) -> str:
    """Generate a Gemma narrative for the cascade brief."""
    prompt = build_prompt(brief)
    return generate(
        prompt,
        system=SYSTEM_INSTRUCTION,
        temperature=0.6,  # slightly lower than default for factual narration
        max_tokens=max_tokens,
    )


# ── Entry point for testing ────────────────────────────────────────────────

if __name__ == "__main__":
    from simulator.graph import MultilayerGraph
    from simulator.cascade.probabilistic import (
        run_probabilistic_cascade,
        format_brief_for_human,
    )

    g = MultilayerGraph.from_json_files(
        species_path="data/processed/sabangau/species.json",
        interactions_path="data/processed/sabangau/interactions.json",
        layers_path="data/processed/sabangau/layers.json",
        ecosystem_name="Sabangau Peat-Swamp Forest",
    )

    orangutan = next(sid for sid, sp in g.species.items()
                     if sp.scientific_name == "Pongo pygmaeus wurmbii")

    print("Running cascade simulation (200 trials)...")
    brief = run_probabilistic_cascade(g, [orangutan], n_trials=200)
    print(format_brief_for_human(brief))

    print("\n" + "=" * 70)
    print("GEMMA NARRATIVE")
    print("=" * 70)
    print()
    narrative = narrate(brief)
    print(narrative)

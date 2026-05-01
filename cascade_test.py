"""
Moment-of-truth cascade test: does Pongo pygmaeus wurmbii removal
produce a meaningfully different cascade than removing a non-keystone species?

If yes → the keystone story is real, demo argument lands.
If no  → engine needs tuning before we can use it for the demo.
"""

from simulator.graph import (
    MultilayerGraph,
    CascadeSimulator,
    MetricsEngine,
    IntegrityIndex,
)

# Load Sabangau
g = MultilayerGraph.from_json_files(
    species_path="data/processed/sabangau/species.json",
    interactions_path="data/processed/sabangau/interactions.json",
    layers_path="data/processed/sabangau/layers.json",
    ecosystem_name="Sabangau Peat-Swamp Forest",
)
print(f"Loaded: {g.species_count()} species, {g.interaction_count()} interactions")
print()

# Quick: which species IDs are in the roster? Pick the orangutan and a control.
species_ids = list(g.species.keys())
orangutan_id = next(
    (sid for sid, sp in g.species.items()
     if sp.scientific_name == "Pongo pygmaeus wurmbii"),
    None,
)
control_id = next(
    (sid for sid, sp in g.species.items()
     if sp.scientific_name == "Macaca fascicularis"),
    None,
)

assert orangutan_id, "Pongo pygmaeus wurmbii not found in roster"
assert control_id, "Macaca fascicularis not found in roster"

print(f"Keystone test species: {orangutan_id} (Pongo pygmaeus wurmbii)")
print(f"Control test species:  {control_id} (Macaca fascicularis)")
print()

# Baseline (nothing removed)
baseline_metrics = MetricsEngine.compute(g, removed=set(), extinct=set())
baseline_integrity = IntegrityIndex.compute(baseline_metrics)
print(f"BASELINE")
print(f"  integrity:     {baseline_integrity:.1f}")
print(f"  active species: {baseline_metrics.get('active_species_count', '?')}")
print()

sim = CascadeSimulator(g)

# --- Orangutan removal ---
print("=" * 60)
print("SCENARIO 1: Remove Pongo pygmaeus wurmbii (keystone)")
print("=" * 60)
result_orangutan = sim.simulate(removed={orangutan_id})
print(f"Cascade result type: {type(result_orangutan).__name__}")
print(f"Cascade result attributes:")
for attr in dir(result_orangutan):
    if not attr.startswith("_"):
        val = getattr(result_orangutan, attr)
        if not callable(val):
            print(f"  {attr}: {val}")
print()

# --- Control removal ---
print("=" * 60)
print("SCENARIO 2: Remove Macaca fascicularis (non-keystone control)")
print("=" * 60)
result_control = sim.simulate(removed={control_id})
print(f"Cascade result attributes:")
for attr in dir(result_control):
    if not attr.startswith("_"):
        val = getattr(result_control, attr)
        if not callable(val):
            print(f"  {attr}: {val}")

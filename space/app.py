"""
Sabangau Cascade — Hugging Face Space
======================================
Multilayer ecological cascade simulator for the Sabangau peat-swamp forest,
narrated by Gemma 4. Built for the Gemma 4 for Good hackathon.

Hero species: Bornean orangutan (Pongo pygmaeus wurmbii) —
specifically Felix, sponsored via The Orangutan Project Borneo.

Architecture:
- Cascade engine (graph.py): multilayer Monte Carlo simulator
- Cascade brief (probabilistic.py): structured, RAG-ready output
- Narrator: Gemma 4 (e4b on HF Spaces, e2b for local dev)
- UI: Gradio with retro-futuristic LiDAR-instrument aesthetic
"""

import os
import json
import re
from pathlib import Path

import gradio as gr
import spaces
import torch
from transformers import AutoProcessor, AutoModelForCausalLM

from simulator.graph import (
    MultilayerGraph,
    CascadeSimulator,
    MetricsEngine,
    IntegrityIndex,
    CostCalculator,
)
from simulator.cascade.probabilistic import (
    run_probabilistic_cascade,
    format_brief_for_human,
    CascadeBrief,
)
from simulator.cascade.narrator import build_prompt, SYSTEM_INSTRUCTION


# ─────────────────────────────────────────────────────────────────────────────
# Gemma model loading (deferred to first GPU call via @spaces.GPU)
# ─────────────────────────────────────────────────────────────────────────────

MODEL_ID = "google/gemma-4-E4B-it"  # E4B instruction-tuned; runs on H200 ZeroGPU
_processor = None
_model = None


def _load_model():
    """Load Gemma 4 lazily (called on first GPU invocation)."""
    global _processor, _model
    if _model is None:
        _processor = AutoProcessor.from_pretrained(MODEL_ID)
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
    return _processor, _model


@spaces.GPU(duration=120)
def gemma_generate(prompt: str, max_new_tokens: int = 600) -> str:
    """Run a Gemma generation call. Holds GPU only during inference."""
    processor, model = _load_model()

    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": prompt},
    ]
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        enable_thinking=False,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)
    input_len = inputs["input_ids"].shape[-1]
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=1.0,
            top_p=0.95,
            top_k=64,
            pad_token_id=processor.tokenizer.eos_token_id,
        )
    new_tokens = outputs[0][input_len:]
    return processor.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()




@spaces.GPU(duration=60)
def gemma_transcribe(audio_path: str) -> str:
    """
    Transcribe an audio file via Gemma 4 E4B. Native audio support is one
    of E4B's distinguishing features (only E2B and E4B have it among the
    Gemma 4 family). Returns the raw transcript as a plain string.
    """
    processor, model = _load_model()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "audio", "audio": audio_path},
                {"type": "text", "text": "Transcribe the speech in this audio. Return only the transcribed words, no preamble."},
            ],
        },
    ]

    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        enable_thinking=False,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)
    input_len = inputs["input_ids"].shape[-1]

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=200,
            do_sample=False,  # deterministic for transcription
            pad_token_id=processor.tokenizer.eos_token_id,
        )

    new_tokens = outputs[0][input_len:]
    return processor.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def linkify_species(text: str, species_dict: dict) -> str:
    """
    Wrap any species name in `text` with a markdown link to its
    curated Wikipedia URL (set in species.json).

    Functional groups (e.g. Mycorrhizal community, Ceratosolen spp.)
    have wikipedia_url=None and are left unlinked. Subspecies link to
    the species article. Species link to their own article.
    """
    # Sort by length DESC so 'Pongo pygmaeus wurmbii' is matched before
    # 'Pongo pygmaeus' to avoid partial overwrite.
    species_list = sorted(
        species_dict.values(),
        key=lambda sp: len(sp.scientific_name),
        reverse=True,
    )

    for sp in species_list:
        name = sp.scientific_name
        url = sp.attributes.get("wikipedia_url") if hasattr(sp, "attributes") else None
        if not url:
            continue  # functional group: no link

        # Full binomial/trinomial match, skip already-linked instances
        pattern = re.compile(
            r"(?<!\[)\b" + re.escape(name) + r"\b(?!\])",
            flags=re.IGNORECASE,
        )
        text = pattern.sub(f"[{name}]({url})", text)

        # Also match abbreviated 'P. pygmaeus wurmbii' form
        parts = name.split()
        if len(parts) >= 2:
            abbreviated = f"{parts[0][0]}. {' '.join(parts[1:])}"
            abbrev_pattern = re.compile(
                r"(?<!\[)\b" + re.escape(abbreviated) + r"\b(?!\])",
                flags=re.IGNORECASE,
            )
            text = abbrev_pattern.sub(f"[{abbreviated}]({url})", text)

    return text


# ─────────────────────────────────────────────────────────────────────────────
# Load Sabangau data once at startup
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data" / "processed" / "sabangau"

GRAPH = MultilayerGraph.from_json_files(
    species_path=str(DATA_DIR / "species.json"),
    interactions_path=str(DATA_DIR / "interactions.json"),
    layers_path=str(DATA_DIR / "layers.json"),
    ecosystem_name="Sabangau Peat-Swamp Forest",
)

# Pre-built dropdown options
SPECIES_OPTIONS = sorted([
    f"{sp.scientific_name} ({sp.common_name})"
    for sp in GRAPH.species.values()
])

NAME_TO_ID = {
    f"{sp.scientific_name} ({sp.common_name})": sid
    for sid, sp in GRAPH.species.items()
}


# ─────────────────────────────────────────────────────────────────────────────
# Main interaction handler
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario(species_label, n_trials, generate_narrative):
    """Entry point: run cascade for selected species, optionally narrate."""
    if not species_label:
        return "Select a species to remove from the network.", "", ""

    species_id = NAME_TO_ID[species_label]
    species = GRAPH.species[species_id]

    # Run the cascade
    brief = run_probabilistic_cascade(
        GRAPH,
        [species_id],
        n_trials=int(n_trials),
    )

    # Build the cascade summary table
    summary_lines = [
        f"### Cascade Brief: {GRAPH.ecosystem_name}",
        f"**Removed:** *{species.scientific_name}* ({species.common_name})",
        f"**IUCN Status:** {species.iucn_status}",
        f"**Monte Carlo trials:** {brief.n_trials}",
        "",
        f"**Mean cascade size:** {brief.mean_cascade_size:.2f} secondary extinctions",
        f"**Maximum observed:** {brief.max_cascade_size} species",
        f"**Network integrity:** {brief.integrity_baseline:.0f} → "
        f"{brief.integrity_mean_after:.0f} (Δ {brief.integrity_delta_mean:.1f} points)",
        f"**Estimated ecosystem-services cost:** ${brief.estimated_cost_usd_mean:,.0f}",
        "",
    ]

    if brief.species_at_risk:
        summary_lines.append("### Species at elevated extinction risk (≥5%)")
        summary_lines.append("")
        summary_lines.append("| Probability | Species | Common name | IUCN | Cascade pathway |")
        summary_lines.append("|---|---|---|---|---|")
        for s in brief.species_at_risk:
            keystone_mark = " ★" if s.keystone_candidate else ""
            summary_lines.append(
                f"| {s.extinction_probability:.0%} | "
                f"*{s.scientific_name}* | "
                f"{s.common_name} | "
                f"{s.iucn_status}{keystone_mark} | "
                f"{s.primary_loss_layer} |"
            )
    else:
        summary_lines.append("### No species at elevated extinction risk")
        summary_lines.append("")
        summary_lines.append(
            "The network is robust to losing this species. Other species "
            "with overlapping ecological roles can compensate."
        )

    summary_lines.append("")
    if brief.layer_cascade_counts:
        summary_lines.append("### Cascade pathways")
        summary_lines.append("")
        for layer, count in sorted(
            brief.layer_cascade_counts.items(), key=lambda x: -x[1]
        ):
            summary_lines.append(f"- **{layer}**: {count} cascade events")

    summary_md = "\n".join(summary_lines)

    # Optionally generate narrative
    narrative = ""
    if generate_narrative:
        prompt = build_prompt(brief)
        narrative = gemma_generate(prompt)
        narrative = linkify_species(narrative, GRAPH.species)

    # Compact stats for header
    stats = (
        f"Mean cascade: **{brief.mean_cascade_size:.2f}** | "
        f"Integrity Δ: **{brief.integrity_delta_mean:.1f}** | "
        f"Cost: **${brief.estimated_cost_usd_mean:,.0f}**"
    )

    return summary_md, narrative, stats


# ─────────────────────────────────────────────────────────────────────────────
# Gradio UI — retro-futuristic LiDAR instrument aesthetic
# (preserves the visual sensibility of the original Bud project)
# ─────────────────────────────────────────────────────────────────────────────

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&display=swap');

:root {
    --bg: #F8F4ED;
    --bg-card: #FFFFFF;
    --text: #1A1A1A;
    --text-muted: #5A5A5A;
    --rule: #E8DFD0;
    --accent-magenta: #F5276C;
    --accent-orange: #F54927;
    --accent-amber: #F5B027;
    --keystone: #B8395E;
}

.gradio-container {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Inter', -apple-system, sans-serif !important;
    max-width: 1200px !important;
    margin: 0 auto !important;
    padding: 32px 24px !important;
}

h1 {
    font-family: 'Fraunces', Georgia, serif !important;
    font-weight: 600 !important;
    color: var(--text) !important;
    font-size: 2.4rem !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 0.4em !important;
}

h2, h3 {
    font-family: 'Inter', sans-serif !important;
    color: var(--text) !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
}

.prose, .markdown-text {
    color: var(--text) !important;
    font-size: 1rem !important;
    line-height: 1.6 !important;
}

.prose strong {
    color: var(--text) !important;
    font-weight: 600 !important;
}

.prose em {
    color: var(--accent-orange) !important;
    font-style: italic;
    font-weight: 500 !important;
}

.prose a {
    color: var(--accent-magenta) !important;
    text-decoration: underline;
    text-decoration-thickness: 1px;
    text-underline-offset: 2px;
}

.prose a:hover {
    color: var(--accent-orange) !important;
}

.prose blockquote {
    border-left: 3px solid var(--accent-amber) !important;
    background: rgba(245, 176, 39, 0.08) !important;
    color: var(--text) !important;
    padding: 12px 18px !important;
    margin: 16px 0 !important;
    font-style: italic;
}

.prose table {
    border-collapse: collapse;
    border: 1px solid var(--rule);
    background: var(--bg-card);
    font-size: 0.9rem;
    margin: 16px 0;
}

.prose th {
    background: rgba(245, 73, 39, 0.06);
    color: var(--text) !important;
    border-bottom: 2px solid var(--accent-orange);
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    font-size: 0.85rem;
    letter-spacing: 0.02em;
    text-transform: uppercase;
}

.prose td {
    border-bottom: 1px solid var(--rule);
    padding: 10px 14px;
    color: var(--text);
}

.prose td em {
    color: var(--keystone) !important;
    font-style: italic;
}

button.primary, button.lg, .gr-button-primary {
    background: var(--accent-orange) !important;
    border: 1px solid var(--accent-orange) !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    border-radius: 4px !important;
    padding: 12px 24px !important;
    transition: background 0.15s ease !important;
}

button.primary:hover, button.lg:hover {
    background: var(--accent-magenta) !important;
    border-color: var(--accent-magenta) !important;
    box-shadow: none !important;
}

input[type="text"], input[type="number"], select, .form-control, textarea {
    background: var(--bg-card) !important;
    border: 1px solid var(--rule) !important;
    color: var(--text) !important;
    font-family: 'Inter', sans-serif !important;
    border-radius: 4px !important;
}

/* Checkboxes: keep native rendering but tint to accent */
input[type="checkbox"] {
    accent-color: var(--accent-orange) !important;
    width: 18px !important;
    height: 18px !important;
    cursor: pointer !important;
}

label {
    color: var(--text-muted) !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}

/* Monospace for numerical/data display */
.mono, code, pre {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.9rem !important;
}

footer {
    display: none !important;
}

/* Soften gradio's default container backgrounds */
.gr-block, .gr-form, .gr-box {
    background: var(--bg-card) !important;
    border: 1px solid var(--rule) !important;
    border-radius: 6px !important;
}

/* Subtle horizontal rules */
hr {
    border: none !important;
    border-top: 1px solid var(--rule) !important;
    margin: 32px 0 !important;
}
"""

INTRO_MD = """
# Sabangau Cascade

### Multilayer Ecological Cascade Simulator · Sabangau Peat-Swamp Forest

A computational model of how ecological collapse propagates through Borneo's
largest contiguous peat-swamp forest, narrated by **Gemma 4**.

The simulator models **31 species** across **4 interaction layers**: trophic,
seed dispersal, pollination, and habitat facilitation. Run a Monte Carlo
cascade by removing any species and observe the propagating extinction risk
across the network.

> **Hero species:** *Pongo pygmaeus wurmbii* — the Bornean orangutan.
> Felix, sponsored via The Orangutan Project Borneo, is one such individual.
"""


with gr.Blocks(css=CUSTOM_CSS, title="Sabangau Cascade") as demo:
    gr.Markdown(INTRO_MD)

    with gr.Row():
        with gr.Column(scale=2):
            species_dropdown = gr.Dropdown(
                choices=SPECIES_OPTIONS,
                label="Species to remove",
                value="Pongo pygmaeus wurmbii (Bornean orangutan)",
                interactive=True,
            )
        with gr.Column(scale=1):
            n_trials_slider = gr.Slider(
                minimum=50,
                maximum=500,
                value=200,
                step=50,
                label="Monte Carlo trials",
            )
        with gr.Column(scale=1):
            narrate_checkbox = gr.Checkbox(
                value=True,
                label="Generate Gemma 4 narrative",
            )

    run_btn = gr.Button("RUN CASCADE", variant="primary", size="lg")

    stats_md = gr.Markdown("")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("## Cascade Brief")
            cascade_md = gr.Markdown("")
        with gr.Column(scale=1):
            gr.Markdown("## Narrative · Gemma 4")
            narrative_md = gr.Markdown(
                "*Click RUN CASCADE to generate a narrative.*"
            )

    gr.Markdown("""
    ---
    ### About

    Built for the Gemma 4 for Good hackathon by [Jacinta May](https://www.linkedin.com/in/jacinta-may-quantum/)
    (Research Associate, University of Oxford · CTO, [Percene](https://www.percene.com/)).

    With thanks to [Travis Raheb-Mol](https://www.linkedin.com/in/travisraheb-mol/).

    The cascade engine combines GloBI species-interaction data with curated
    primary-literature edges (Tarszisz 2018 dispersal kernels, Kinnaird & O'Brien
    2007 hornbill dispersal, Brearley 2007 mycorrhizal facilitation, Bronstein
    1989 fig-wasp obligate mutualism, Morrogh-Bernard 2009 nest-tree facilitation).

    [Repository](https://github.com/topological-lemon/bean-ecosystem-map) ·
    Branch: `sabangau-pivot`
    """)

    run_btn.click(
        fn=run_scenario,
        inputs=[species_dropdown, n_trials_slider, narrate_checkbox],
        outputs=[cascade_md, narrative_md, stats_md],
    )

    # ─────────────────────────────────────────────────────────────────────
    # Voice input test panel (Step 2 verification — not yet wired to cascade)
    # ─────────────────────────────────────────────────────────────────────
    with gr.Accordion("Test voice transcription (development)", open=False):
        gr.Markdown(
            "Record a short clip (e.g. the name of a species). "
            "Gemma 4 E4B will transcribe it using its native audio support. "
            "Once this works reliably, we'll wire it into species selection."
        )
        with gr.Row():
            audio_input = gr.Audio(
                sources=["microphone"],
                type="filepath",
                label="Record audio",
            )
        transcribe_btn = gr.Button("Transcribe", variant="primary")
        transcript_out = gr.Textbox(
            label="Transcript",
            placeholder="Transcribed text will appear here...",
            lines=2,
            interactive=False,
        )

        def _do_transcribe(audio_path):
            if not audio_path:
                return "No audio recorded yet."
            try:
                return gemma_transcribe(audio_path)
            except Exception as e:
                return f"Transcription failed: {type(e).__name__}: {e}"

        transcribe_btn.click(
            fn=_do_transcribe,
            inputs=[audio_input],
            outputs=[transcript_out],
        )


if __name__ == "__main__":
    demo.launch()

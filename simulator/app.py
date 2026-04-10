"""
Bud Ecosystem Quantum Map — Interactive Dash App
=================================================
Phase 1 prototype. Loads the Amazon species + interactions data,
renders the multilayer network, and lets users remove a species
to watch the cascade unfold in real time.

Run:
    python simulator/app.py

Then open http://localhost:8050
"""

import json
from pathlib import Path

import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import networkx as nx
import numpy as np

from graph import (
    MultilayerGraph, Species, Interaction,
    CascadeSimulator, MetricsEngine, IntegrityIndex, CostCalculator
)

# ─────────────────────────────────────────────────────────────────────────────
# Load or build demo graph
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"

LAYER_COLOURS = {
    "trophic":     "#E24B4A",
    "mutualistic": "#1D9E75",
    "parasitic":   "#7F77DD",
    "habitat":     "#EF9F27",
    "dispersal":   "#378ADD",
    "competitive": "#D4537E",
}

TAXA_COLOURS = {
    "mammal":       "#E24B4A",
    "bird":         "#378ADD",
    "plant":        "#1D9E75",
    "invertebrate": "#EF9F27",
    "reptile":      "#7F77DD",
    "amphibian":    "#5DCAA5",
    "fish":         "#D4537E",
    "other":        "#888780",
}


def build_demo_graph() -> MultilayerGraph:
    """
    Build a richer demo graph from species.json if available,
    otherwise fall back to the hardcoded Amazon demo network.
    """
    species_path = DATA_DIR / "species.json"
    interactions_path = DATA_DIR / "interactions.json"

    if species_path.exists() and interactions_path.exists():
        layers_path = DATA_DIR / "layers.json"
        if not layers_path.exists():
            _write_default_layers(layers_path)
        return MultilayerGraph.from_json_files(
            species_path, interactions_path, layers_path, "Amazon Tropical Forest"
        )

    # ── Hardcoded demo (Phase 1 fallback) ────────────────────────────────────
    g = MultilayerGraph("Amazon Tropical Forest")

    species_list = [
        ("sp_001", "Panthera onca",          "Jaguar",              "mammal",       4.2, 0.60, 0.10, True),
        ("sp_002", "Harpia harpyja",          "Harpy eagle",         "bird",         4.0, 0.62, 0.12, True),
        ("sp_003", "Tapirus terrestris",      "Tapir",               "mammal",       2.5, 0.75, 0.20, True),
        ("sp_004", "Tayassu pecari",          "White-lipped peccary","mammal",       2.3, 0.78, 0.30, False),
        ("sp_005", "Ateles paniscus",         "Black spider monkey", "mammal",       2.5, 0.70, 0.25, True),
        ("sp_006", "Mazama americana",        "Red brocket deer",    "mammal",       3.0, 0.80, 0.35, False),
        ("sp_007", "Dasyprocta leporina",     "Agouti",              "mammal",       2.2, 0.82, 0.50, False),
        ("sp_008", "Ramphastos tucanus",      "Toucan",              "bird",         2.5, 0.75, 0.40, False),
        ("sp_009", "Ara macao",               "Scarlet macaw",       "bird",         2.3, 0.73, 0.35, False),
        ("sp_010", "Ficus insipida",          "Fig tree",            "plant",        1.0, 0.90, 0.55, True),
        ("sp_011", "Cecropia peltata",        "Cecropia",            "plant",        1.0, 0.88, 0.60, False),
        ("sp_012", "Heliconia latispatha",    "Heliconia",           "plant",        1.0, 0.87, 0.65, False),
        ("sp_013", "Swietenia macrophylla",   "Mahogany",            "plant",        1.0, 0.85, 0.45, False),
        ("sp_014", "Mauritia flexuosa",       "Buriti palm",         "plant",        1.0, 0.89, 0.58, False),
        ("sp_015", "Eulaema meriana",         "Orchid bee",          "invertebrate", 2.0, 0.65, 0.45, True),
        ("sp_016", "Atta cephalotes",         "Leafcutter ant",      "invertebrate", 2.0, 0.88, 0.60, True),
        ("sp_017", "Hydrochoerus hydrochaeris","Capybara",           "mammal",       2.2, 0.82, 0.45, False),
        ("sp_018", "Pteronura brasiliensis",  "Giant river otter",   "mammal",       3.8, 0.58, 0.12, True),
        ("sp_019", "Nasua nasua",             "Coati",               "mammal",       2.8, 0.80, 0.48, False),
        ("sp_020", "Lagothrix lagothricha",   "Woolly monkey",       "mammal",       2.2, 0.72, 0.30, False),
    ]
    for row in species_list:
        sp_id, sci, common, taxa, tl, ps, rf, kc = row
        g.add_species(Species(sp_id, sci, common, taxa, tl, ps, rf, keystone_candidate=kc))

    for layer_id, meta in [
        ("trophic",     {"cascade_weight": 0.90}),
        ("mutualistic", {"cascade_weight": 0.75}),
        ("habitat",     {"cascade_weight": 0.60}),
        ("dispersal",   {"cascade_weight": 0.65}),
    ]:
        g.add_layer(layer_id, meta)

    interactions = [
        # Trophic
        ("i01", "sp_001", "sp_003", "predation",         "trophic",     0.80, True),
        ("i02", "sp_001", "sp_004", "predation",         "trophic",     0.75, False),
        ("i03", "sp_001", "sp_006", "predation",         "trophic",     0.70, False),
        ("i04", "sp_002", "sp_005", "predation",         "trophic",     0.85, True),
        ("i05", "sp_002", "sp_009", "predation",         "trophic",     0.60, False),
        ("i06", "sp_018", "sp_017", "predation",         "trophic",     0.80, True),
        ("i07", "sp_003", "sp_010", "herbivory",         "trophic",     0.65, False),
        ("i08", "sp_004", "sp_011", "herbivory",         "trophic",     0.60, False),
        ("i09", "sp_006", "sp_013", "herbivory",         "trophic",     0.55, False),
        ("i10", "sp_016", "sp_011", "herbivory",         "trophic",     0.70, False),
        # Mutualistic
        ("i11", "sp_010", "sp_005", "seed_dispersal",    "mutualistic", 0.90, True),
        ("i12", "sp_010", "sp_008", "seed_dispersal",    "mutualistic", 0.85, True),
        ("i13", "sp_014", "sp_003", "seed_dispersal",    "mutualistic", 0.80, False),
        ("i14", "sp_012", "sp_015", "pollination",       "mutualistic", 0.95, True),
        ("i15", "sp_011", "sp_015", "pollination",       "mutualistic", 0.88, True),
        ("i16", "sp_013", "sp_009", "seed_dispersal",    "mutualistic", 0.75, False),
        # Habitat
        ("i17", "sp_010", "sp_016", "habitat_facilitation","habitat",   0.70, False),
        ("i18", "sp_011", "sp_019", "habitat_facilitation","habitat",   0.65, False),
        ("i19", "sp_014", "sp_017", "habitat_facilitation","habitat",   0.72, True),
        # Dispersal
        ("i20", "sp_008", "sp_013", "seed_dispersal",    "dispersal",   0.80, False),
        ("i21", "sp_020", "sp_010", "seed_dispersal",    "dispersal",   0.85, True),
        ("i22", "sp_005", "sp_014", "seed_dispersal",    "dispersal",   0.78, False),
    ]
    for row in interactions:
        i_id, src, tgt, itype, layer, strength, obligate = row
        g.add_interaction(Interaction(i_id, src, tgt, itype, layer, strength, obligate))

    return g


def _write_default_layers(path: Path):
    layers = [
        {"id": "trophic",     "name": "Trophic",              "interaction_types": ["predation","herbivory"],             "cascade_weight": 0.90, "colour_hex": "#E24B4A"},
        {"id": "mutualistic", "name": "Mutualistic",          "interaction_types": ["pollination","seed_dispersal"],      "cascade_weight": 0.75, "colour_hex": "#1D9E75"},
        {"id": "parasitic",   "name": "Parasitic",            "interaction_types": ["parasitism","pathogen_host"],        "cascade_weight": 0.70, "colour_hex": "#7F77DD"},
        {"id": "habitat",     "name": "Habitat facilitation", "interaction_types": ["habitat_facilitation","nurse_plant"],"cascade_weight": 0.60, "colour_hex": "#EF9F27"},
        {"id": "dispersal",   "name": "Dispersal",            "interaction_types": ["seed_dispersal"],                    "cascade_weight": 0.65, "colour_hex": "#378ADD"},
    ]
    path.write_text(json.dumps(layers, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# Layout helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_network_figure(
    graph: MultilayerGraph,
    highlight_extinct: set[str] | None = None,
    highlight_removed: set[str] | None = None,
    active_layers: list[str] | None = None,
) -> go.Figure:
    highlight_extinct = highlight_extinct or set()
    highlight_removed = highlight_removed or set()
    active_layers = active_layers or list(graph.layers.keys())

    # Spring layout on the full graph for stable positions
    combined = nx.Graph()
    for sp_id in graph.species:
        combined.add_node(sp_id)
    for layer_id, g in graph.layers.items():
        if layer_id in active_layers:
            combined.add_edges_from(g.edges())

    pos = nx.spring_layout(combined, seed=42, k=2.5)

    traces = []

    # ── Edges ────────────────────────────────────────────────────────────────
    for layer_id in active_layers:
        if layer_id not in graph.layers:
            continue
        layer_g = graph.layers[layer_id]
        colour = LAYER_COLOURS.get(layer_id, "#888780")
        edge_x, edge_y = [], []
        for u, v in layer_g.edges():
            if u not in pos or v not in pos:
                continue
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]
        if edge_x:
            traces.append(go.Scatter(
                x=edge_x, y=edge_y, mode="lines",
                line=dict(width=1.2, color=colour),
                opacity=0.55,
                hoverinfo="none",
                name=layer_id.capitalize(),
                legendgroup=layer_id,
            ))

    # ── Nodes ─────────────────────────────────────────────────────────────────
    for sp_id, species in graph.species.items():
        if sp_id not in pos:
            continue
        x, y = pos[sp_id]
        is_removed = sp_id in highlight_removed
        is_extinct = sp_id in highlight_extinct
        is_keystone = species.keystone_candidate

        if is_removed:
            colour = "#E24B4A"
            symbol = "x"
            size = 22
            opacity = 1.0
        elif is_extinct:
            colour = "#EF9F27"
            symbol = "circle-open"
            size = 18
            opacity = 0.6
        else:
            colour = TAXA_COLOURS.get(species.taxa_group, "#888780")
            symbol = "diamond" if is_keystone else "circle"
            size = 18 if is_keystone else 14
            opacity = 1.0

        traces.append(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(size=size, color=colour, symbol=symbol,
                        line=dict(width=1.5, color="white")),
            text=[species.common_name],
            textposition="top center",
            textfont=dict(size=10, color="#444441"),
            opacity=opacity,
            hovertemplate=(
                f"<b>{species.common_name}</b><br>"
                f"{species.scientific_name}<br>"
                f"Taxa: {species.taxa_group}<br>"
                f"Trophic level: {species.trophic_level}<br>"
                f"Persistence: {species.persistence_score}<br>"
                f"{'⚠ KEYSTONE' if is_keystone else ''}"
                f"{'<br>❌ REMOVED' if is_removed else ''}"
                f"{'<br>💀 SECONDARY EXTINCTION' if is_extinct else ''}"
                "<extra></extra>"
            ),
            name=species.common_name,
            showlegend=False,
        ))

    fig = go.Figure(traces)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01,
            xanchor="left", x=0, font=dict(size=11),
        ),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hovermode="closest",
        height=520,
    )
    return fig


def make_metrics_cards(metrics: dict, integrity: float, cost: float, delta: float) -> list:
    def card(label, value, colour="#378ADD"):
        return html.Div([
            html.Div(label, style={"fontSize": "11px", "color": "#888780", "marginBottom": "4px"}),
            html.Div(value, style={"fontSize": "22px", "fontWeight": "500", "color": colour}),
        ], style={
            "background": "#f8f8f6",
            "borderRadius": "8px",
            "padding": "12px 14px",
            "flex": "1",
            "minWidth": "120px",
        })

    integrity_colour = "#1D9E75" if integrity >= 70 else "#EF9F27" if integrity >= 40 else "#E24B4A"
    cost_str = f"${cost/1e9:.1f}B" if cost >= 1e9 else f"${cost/1e6:.0f}M"

    return [
        card("Integrity score", f"{integrity:.1f}/100", integrity_colour),
        card("Integrity lost", f"−{delta:.1f} pts", "#E24B4A" if delta > 0 else "#1D9E75"),
        card("Extinctions", str(metrics.get("extinction_count", 0)), "#E24B4A"),
        card("Cascade depth", str(metrics.get("cascade_depth", 0)), "#7F77DD"),
        card("Connectivity lost", f"{metrics.get('connectivity_loss', 0)*100:.0f}%", "#EF9F27"),
        card("Est. cost/yr", cost_str, "#E24B4A"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Build app
# ─────────────────────────────────────────────────────────────────────────────

GRAPH = build_demo_graph()
SIM = CascadeSimulator(GRAPH)
BASELINE_METRICS = MetricsEngine.compute(GRAPH, set(), set())
BASELINE_INTEGRITY = IntegrityIndex.compute(BASELINE_METRICS)

SPECIES_OPTIONS = [
    {"label": f"{sp.common_name} ({sp.scientific_name})", "value": sp_id}
    for sp_id, sp in sorted(GRAPH.species.items(), key=lambda x: x[1].common_name)
]

LAYER_OPTIONS = [
    {"label": layer_id.capitalize(), "value": layer_id}
    for layer_id in GRAPH.layers
]

app = dash.Dash(__name__, title="Bud Ecosystem Quantum Map")

app.layout = html.Div([

    # ── Header ────────────────────────────────────────────────────────────────
    html.Div([
        html.Div([
            html.H1("Bud Ecosystem Quantum Map",
                    style={"fontSize": "20px", "fontWeight": "500", "margin": "0 0 2px"}),
            html.P("Amazon tropical forest — multilayer cascade simulator",
                   style={"fontSize": "13px", "color": "#888780", "margin": 0}),
        ]),
        html.Div([
            html.Span("Phase 1", style={
                "background": "#E1F5EE", "color": "#0F6E56",
                "padding": "3px 10px", "borderRadius": "12px", "fontSize": "12px",
            }),
        ]),
    ], style={
        "display": "flex", "justifyContent": "space-between", "alignItems": "center",
        "padding": "16px 24px 12px", "borderBottom": "0.5px solid #e0ded6",
    }),

    # ── Main layout ───────────────────────────────────────────────────────────
    html.Div([

        # Left panel — controls
        html.Div([
            html.Div("Disturbance", style={"fontSize": "12px", "fontWeight": "500",
                                           "color": "#888780", "marginBottom": "8px",
                                           "textTransform": "uppercase", "letterSpacing": ".05em"}),

            dcc.Dropdown(
                id="species-select",
                options=SPECIES_OPTIONS,
                placeholder="Select species to remove...",
                multi=True,
                style={"fontSize": "13px", "marginBottom": "12px"},
            ),

            html.Div("Simulation mode", style={"fontSize": "12px", "fontWeight": "500",
                                                "color": "#888780", "margin": "12px 0 8px",
                                                "textTransform": "uppercase"}),
            dcc.RadioItems(
                id="mode-select",
                options=[
                    {"label": " Multilayer", "value": "multilayer"},
                    {"label": " Monolayer (baseline)", "value": "monolayer"},
                ],
                value="multilayer",
                labelStyle={"display": "block", "fontSize": "13px", "marginBottom": "6px"},
            ),

            html.Div("Visible layers", style={"fontSize": "12px", "fontWeight": "500",
                                               "color": "#888780", "margin": "16px 0 8px",
                                               "textTransform": "uppercase"}),
            dcc.Checklist(
                id="layer-select",
                options=LAYER_OPTIONS,
                value=[o["value"] for o in LAYER_OPTIONS],
                labelStyle={"display": "block", "fontSize": "13px", "marginBottom": "6px"},
            ),

            html.Hr(style={"margin": "16px 0", "borderColor": "#e0ded6"}),

            html.Button("Run cascade", id="run-btn", n_clicks=0, style={
                "width": "100%", "padding": "10px", "background": "#1D9E75",
                "color": "white", "border": "none", "borderRadius": "8px",
                "fontSize": "14px", "fontWeight": "500", "cursor": "pointer",
            }),

            html.Button("Reset", id="reset-btn", n_clicks=0, style={
                "width": "100%", "padding": "8px", "background": "transparent",
                "color": "#888780", "border": "0.5px solid #d3d1c7",
                "borderRadius": "8px", "fontSize": "13px",
                "cursor": "pointer", "marginTop": "8px",
            }),

            html.Div(id="comparison-panel", style={"marginTop": "20px"}),

        ], style={
            "width": "220px", "flexShrink": "0", "padding": "20px 16px",
            "borderRight": "0.5px solid #e0ded6",
        }),

        # Right panel — network + metrics
        html.Div([

            # Metrics row
            html.Div(id="metrics-row", children=[
                html.Div(make_metrics_cards(
                    BASELINE_METRICS, BASELINE_INTEGRITY, 0.0, 0.0
                ), style={"display": "flex", "gap": "10px", "flexWrap": "wrap",
                          "marginBottom": "16px"}),
            ]),

            # Network graph
            dcc.Graph(
                id="network-graph",
                figure=make_network_figure(GRAPH),
                config={"displayModeBar": False},
                style={"borderRadius": "12px", "border": "0.5px solid #e0ded6"},
            ),

            # Legend
            html.Div([
                html.Span("● Removed", style={"color": "#E24B4A", "fontSize": "12px", "marginRight": "14px"}),
                html.Span("○ Secondary extinction", style={"color": "#EF9F27", "fontSize": "12px", "marginRight": "14px"}),
                html.Span("◆ Keystone species", style={"color": "#444441", "fontSize": "12px", "marginRight": "14px"}),
            ], style={"marginTop": "8px", "paddingLeft": "4px"}),

            # Cascade log
            html.Div(id="cascade-log", style={"marginTop": "16px"}),

        ], style={"flex": "1", "padding": "20px 24px", "overflowY": "auto"}),

    ], style={"display": "flex", "height": "calc(100vh - 60px)", "fontFamily": "sans-serif"}),

], style={"fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          "background": "white", "minHeight": "100vh"})


# ─────────────────────────────────────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output("network-graph", "figure"),
    Output("metrics-row", "children"),
    Output("cascade-log", "children"),
    Output("comparison-panel", "children"),
    Input("run-btn", "n_clicks"),
    Input("reset-btn", "n_clicks"),
    Input("layer-select", "value"),
    State("species-select", "value"),
    State("mode-select", "value"),
    prevent_initial_call=False,
)
def update(run_clicks, reset_clicks, active_layers, selected_species, mode):
    ctx = dash.callback_context
    trigger = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

    if "reset-btn" in trigger or not selected_species:
        fig = make_network_figure(GRAPH, active_layers=active_layers)
        cards = html.Div(make_metrics_cards(
            BASELINE_METRICS, BASELINE_INTEGRITY, 0.0, 0.0
        ), style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})
        return fig, cards, html.Div(), html.Div()

    if "run-btn" not in trigger and "layer-select" not in trigger:
        raise dash.exceptions.PreventUpdate

    multilayer = (mode == "multilayer")
    result = SIM.simulate(selected_species, multilayer=multilayer, n_trials=50)

    # Comparison (always run both)
    comparison = SIM.compare_multilayer_vs_monolayer(selected_species, n_trials=50)

    fig = make_network_figure(
        GRAPH,
        highlight_extinct=set(result.extinct_species),
        highlight_removed=set(result.removed_species),
        active_layers=active_layers,
    )

    cards = html.Div(make_metrics_cards(
        result.metrics,
        result.integrity_score,
        result.estimated_cost_usd,
        result.integrity_delta,
    ), style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})

    # Cascade log
    log_items = []
    for step in result.cascade_steps:
        names = [GRAPH.species[sp].common_name for sp in step["newly_extinct"] if sp in GRAPH.species]
        if names:
            log_items.append(html.Div([
                html.Span(f"Wave {step['step']}  ", style={"color": "#888780", "fontSize": "12px"}),
                html.Span(", ".join(names), style={"color": "#E24B4A", "fontSize": "13px"}),
            ], style={"padding": "4px 0", "borderBottom": "0.5px solid #f0ede6"}))

    log = html.Div([
        html.Div("Cascade waves", style={"fontSize": "12px", "fontWeight": "500",
                                          "color": "#888780", "marginBottom": "8px",
                                          "textTransform": "uppercase"}),
        html.Div(log_items if log_items else
                 html.Div("No secondary extinctions detected.", style={"fontSize": "13px", "color": "#888780"})),
    ], style={"background": "#f8f8f6", "borderRadius": "8px", "padding": "12px 14px"}) if result.cascade_steps else html.Div()

    # Comparison panel
    hidden = comparison["hidden_cascade_events"]
    hidden_colour = "#E24B4A" if hidden > 0 else "#1D9E75"
    comp_panel = html.Div([
        html.Div("Multilayer vs monolayer", style={
            "fontSize": "11px", "fontWeight": "500", "color": "#888780",
            "textTransform": "uppercase", "marginBottom": "8px",
        }),
        html.Div([
            html.Span("Hidden cascades: ", style={"fontSize": "12px", "color": "#444441"}),
            html.Span(str(hidden), style={"fontSize": "14px", "fontWeight": "500", "color": hidden_colour}),
        ]),
        html.Div([
            html.Span("Multi extinctions: ", style={"fontSize": "12px", "color": "#444441"}),
            html.Span(str(comparison["multilayer_extinctions"]), style={"fontSize": "13px", "color": "#E24B4A"}),
        ], style={"marginTop": "4px"}),
        html.Div([
            html.Span("Mono extinctions: ", style={"fontSize": "12px", "color": "#444441"}),
            html.Span(str(comparison["monolayer_extinctions"]), style={"fontSize": "13px", "color": "#EF9F27"}),
        ], style={"marginTop": "4px"}),
        html.Div([
            html.Span("Hidden species: ", style={"fontSize": "12px", "color": "#444441"}),
            html.Span(
                ", ".join(GRAPH.species[sp].common_name for sp in comparison["hidden_species"] if sp in GRAPH.species)
                or "none",
                style={"fontSize": "12px", "color": hidden_colour},
            ),
        ], style={"marginTop": "4px"}),
    ], style={
        "background": "#f8f8f6", "borderRadius": "8px",
        "padding": "12px", "fontSize": "13px",
    })

    return fig, cards, log, comp_panel


if __name__ == "__main__":
    print("\n  Bud Ecosystem Quantum Map")
    print(f"  Loaded: {GRAPH.ecosystem_name}")
    print(f"  Species: {GRAPH.species_count()}")
    print(f"  Baseline integrity: {BASELINE_INTEGRITY}/100\n")
    print("  → Open http://localhost:8050\n")
    app.run(debug=True, port=8050)

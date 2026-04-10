"""
Bud Ecosystem Quantum Map — Interactive Dash App
=================================================
Aesthetic: retro-futuristic scientific instrument.
LiDAR point cloud meets 1980s NASA display terminal.
Black void, cyan wireframes, teal point clouds, orange data streams.

Run:
    python simulator/app.py
    → http://localhost:8050
"""

import json
from pathlib import Path

import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import networkx as nx

from graph import (
    MultilayerGraph, Species, Interaction,
    CascadeSimulator, MetricsEngine, IntegrityIndex,
)

# ─────────────────────────────────────────────────────────────────────────────
# Palette — LiDAR instrument terminal
# ─────────────────────────────────────────────────────────────────────────────

P = {
    "void":      "#000000",
    "void2":     "#020a04",
    "surface":   "#040f06",
    "panel":     "#061209",
    "border":    "#0a2e10",
    "border2":   "#0f4018",
    "cyan":      "#00ffe0",
    "cyan2":     "#00c9b1",
    "cyan_dim":  "#003d35",
    "green":     "#00ff88",
    "green2":    "#00c86e",
    "green_dim": "#003320",
    "orange":    "#ff6b1a",
    "orange2":   "#e05500",
    "orange_dim":"#3d1800",
    "amber":     "#ffb800",
    "amber_dim": "#3d2c00",
    "red":       "#ff3b3b",
    "red_dim":   "#3d0000",
    "purple":    "#b060ff",
    "blue":      "#3b8fff",
    "text":      "#a8d4b0",
    "text2":     "#4a8a56",
    "text3":     "#1e4424",
    "scan":      "rgba(0,255,180,0.03)",
}

# LiDAR-style trophic colour ramp (blue=ground → teal → green → amber → red=apex)
TROPHIC_RAMP = {
    1.0: "#3b8fff",   # producer — deep blue
    2.0: "#00ffe0",   # primary consumer — cyan
    2.5: "#00ff88",   # frugivore — green
    3.0: "#7fff00",   # secondary consumer — lime
    3.5: "#ffb800",   # mesopredator — amber
    4.0: "#ff6b1a",   # apex — orange
    4.5: "#ff3b3b",   # apex+ — red
}

LAYER_COLOURS = {
    "trophic":     P["orange"],
    "mutualistic": P["green"],
    "parasitic":   P["purple"],
    "habitat":     P["amber"],
    "dispersal":   P["cyan"],
    "competitive": P["red"],
}

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"


def trophic_colour(level: float) -> str:
    keys = sorted(TROPHIC_RAMP.keys())
    for i, k in enumerate(keys):
        if level <= k:
            return TROPHIC_RAMP[k]
    return TROPHIC_RAMP[keys[-1]]


# ─────────────────────────────────────────────────────────────────────────────
# Graph
# ─────────────────────────────────────────────────────────────────────────────

def build_demo_graph() -> MultilayerGraph:
    species_path = DATA_DIR / "species.json"
    interactions_path = DATA_DIR / "interactions.json"
    if species_path.exists() and interactions_path.exists():
        layers_path = DATA_DIR / "layers.json"
        if not layers_path.exists():
            _write_default_layers(layers_path)
        return MultilayerGraph.from_json_files(
            species_path, interactions_path, layers_path, "Amazon Tropical Forest"
        )

    g = MultilayerGraph("Amazon Tropical Forest")
    species_list = [
        ("sp_001","Panthera onca",            "Jaguar",               "mammal",       4.2, 0.60, 0.10, True),
        ("sp_002","Harpia harpyja",            "Harpy eagle",          "bird",         4.0, 0.62, 0.12, True),
        ("sp_003","Tapirus terrestris",        "Tapir",                "mammal",       2.5, 0.75, 0.20, True),
        ("sp_004","Tayassu pecari",            "White-lipped peccary", "mammal",       2.3, 0.78, 0.30, False),
        ("sp_005","Ateles paniscus",           "Black spider monkey",  "mammal",       2.5, 0.70, 0.25, True),
        ("sp_006","Mazama americana",          "Red brocket deer",     "mammal",       3.0, 0.80, 0.35, False),
        ("sp_007","Dasyprocta leporina",       "Agouti",               "mammal",       2.2, 0.82, 0.50, False),
        ("sp_008","Ramphastos tucanus",        "Toucan",               "bird",         2.5, 0.75, 0.40, False),
        ("sp_009","Ara macao",                 "Scarlet macaw",        "bird",         2.3, 0.73, 0.35, False),
        ("sp_010","Ficus insipida",            "Fig tree",             "plant",        1.0, 0.90, 0.55, True),
        ("sp_011","Cecropia peltata",          "Cecropia",             "plant",        1.0, 0.88, 0.60, False),
        ("sp_012","Heliconia latispatha",      "Heliconia",            "plant",        1.0, 0.87, 0.65, False),
        ("sp_013","Swietenia macrophylla",     "Mahogany",             "plant",        1.0, 0.85, 0.45, False),
        ("sp_014","Mauritia flexuosa",         "Buriti palm",          "plant",        1.0, 0.89, 0.58, False),
        ("sp_015","Eulaema meriana",           "Orchid bee",           "invertebrate", 2.0, 0.65, 0.45, True),
        ("sp_016","Atta cephalotes",           "Leafcutter ant",       "invertebrate", 2.0, 0.88, 0.60, True),
        ("sp_017","Hydrochoerus hydrochaeris", "Capybara",             "mammal",       2.2, 0.82, 0.45, False),
        ("sp_018","Pteronura brasiliensis",    "Giant river otter",    "mammal",       3.8, 0.58, 0.12, True),
        ("sp_019","Nasua nasua",               "Coati",                "mammal",       2.8, 0.80, 0.48, False),
        ("sp_020","Lagothrix lagothricha",     "Woolly monkey",        "mammal",       2.2, 0.72, 0.30, False),
    ]
    for row in species_list:
        sp_id,sci,common,taxa,tl,ps,rf,kc = row
        g.add_species(Species(sp_id,sci,common,taxa,tl,ps,rf,keystone_candidate=kc))
    for lid,meta in [
        ("trophic",     {"cascade_weight":0.90}),
        ("mutualistic", {"cascade_weight":0.75}),
        ("habitat",     {"cascade_weight":0.60}),
        ("dispersal",   {"cascade_weight":0.65}),
    ]:
        g.add_layer(lid, meta)
    interactions = [
        ("i01","sp_001","sp_003","predation",            "trophic",     0.80,True),
        ("i02","sp_001","sp_004","predation",            "trophic",     0.75,False),
        ("i03","sp_001","sp_006","predation",            "trophic",     0.70,False),
        ("i04","sp_002","sp_005","predation",            "trophic",     0.85,True),
        ("i05","sp_002","sp_009","predation",            "trophic",     0.60,False),
        ("i06","sp_018","sp_017","predation",            "trophic",     0.80,True),
        ("i07","sp_003","sp_010","herbivory",            "trophic",     0.65,False),
        ("i08","sp_004","sp_011","herbivory",            "trophic",     0.60,False),
        ("i09","sp_006","sp_013","herbivory",            "trophic",     0.55,False),
        ("i10","sp_016","sp_011","herbivory",            "trophic",     0.70,False),
        ("i11","sp_010","sp_005","seed_dispersal",       "mutualistic", 0.90,True),
        ("i12","sp_010","sp_008","seed_dispersal",       "mutualistic", 0.85,True),
        ("i13","sp_014","sp_003","seed_dispersal",       "mutualistic", 0.80,False),
        ("i14","sp_012","sp_015","pollination",          "mutualistic", 0.95,True),
        ("i15","sp_011","sp_015","pollination",          "mutualistic", 0.88,True),
        ("i16","sp_013","sp_009","seed_dispersal",       "mutualistic", 0.75,False),
        ("i17","sp_010","sp_016","habitat_facilitation", "habitat",     0.70,False),
        ("i18","sp_011","sp_019","habitat_facilitation", "habitat",     0.65,False),
        ("i19","sp_014","sp_017","habitat_facilitation", "habitat",     0.72,True),
        ("i20","sp_008","sp_013","seed_dispersal",       "dispersal",   0.80,False),
        ("i21","sp_020","sp_010","seed_dispersal",       "dispersal",   0.85,True),
        ("i22","sp_005","sp_014","seed_dispersal",       "dispersal",   0.78,False),
    ]
    for row in interactions:
        i_id,src,tgt,itype,layer,strength,obligate = row
        g.add_interaction(Interaction(i_id,src,tgt,itype,layer,strength,obligate))
    return g


def _write_default_layers(path):
    layers = [
        {"id":"trophic",    "name":"Trophic",             "interaction_types":["predation","herbivory"],            "cascade_weight":0.90},
        {"id":"mutualistic","name":"Mutualistic",         "interaction_types":["pollination","seed_dispersal"],     "cascade_weight":0.75},
        {"id":"parasitic",  "name":"Parasitic",           "interaction_types":["parasitism","pathogen_host"],       "cascade_weight":0.70},
        {"id":"habitat",    "name":"Habitat facilitation","interaction_types":["habitat_facilitation","nurse_plant"],"cascade_weight":0.60},
        {"id":"dispersal",  "name":"Dispersal",           "interaction_types":["seed_dispersal"],                   "cascade_weight":0.65},
    ]
    path.write_text(json.dumps(layers, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# Network figure — LiDAR point cloud style
# ─────────────────────────────────────────────────────────────────────────────

def make_network_figure(
    graph, highlight_extinct=None, highlight_removed=None, active_layers=None
):
    highlight_extinct  = highlight_extinct  or set()
    highlight_removed  = highlight_removed  or set()
    active_layers      = active_layers or list(graph.layers.keys())

    combined = nx.Graph()
    for sp_id in graph.species:
        combined.add_node(sp_id)
    for lid, g in graph.layers.items():
        if lid in active_layers:
            combined.add_edges_from(g.edges())
    pos = nx.spring_layout(combined, seed=42, k=2.8)

    traces = []

    # Edges — thin coloured wires
    for lid in active_layers:
        if lid not in graph.layers:
            continue
        layer_g = graph.layers[lid]
        colour = LAYER_COLOURS.get(lid, P["text3"])
        ex, ey = [], []
        for u, v in layer_g.edges():
            if u not in pos or v not in pos:
                continue
            x0,y0 = pos[u]; x1,y1 = pos[v]
            ex += [x0,x1,None]; ey += [y0,y1,None]
        if ex:
            traces.append(go.Scatter(
                x=ex, y=ey, mode="lines",
                line=dict(width=0.8, color=colour),
                opacity=0.25, hoverinfo="none",
                name=lid.capitalize(), legendgroup=lid,
            ))

    # Nodes — LiDAR points coloured by trophic level
    for sp_id, sp in graph.species.items():
        if sp_id not in pos:
            continue
        x, y = pos[sp_id]
        is_removed = sp_id in highlight_removed
        is_extinct = sp_id in highlight_extinct

        if is_removed:
            colour      = P["orange"]
            symbol      = "x"
            size        = 28
            opacity     = 1.0
            line_c      = P["orange"]
            line_w      = 2.5
        elif is_extinct:
            colour      = P["red"]
            symbol      = "circle-open"
            size        = 22
            opacity     = 0.55
            line_c      = P["red"]
            line_w      = 2.0
        else:
            colour      = trophic_colour(sp.trophic_level)
            symbol      = "diamond" if sp.keystone_candidate else "circle"
            size        = 20 if sp.keystone_candidate else 12
            opacity     = 1.0
            line_c      = P["void"]
            line_w      = 1.0

        traces.append(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(size=size, color=colour, symbol=symbol,
                        opacity=opacity, line=dict(width=line_w, color=line_c)),
            text=[sp.common_name],
            textposition="top center",
            textfont=dict(size=8, color=P["text2"], family="Share Tech Mono, monospace"),
            hovertemplate=(
                f"<b>{sp.common_name}</b><br>"
                f"<span style='color:#4a8a56'>{sp.scientific_name}</span><br>"
                f"──────────────────<br>"
                f"Trophic level  {sp.trophic_level}<br>"
                f"Taxa           {sp.taxa_group}<br>"
                f"Persistence    {sp.persistence_score}<br>"
                f"Redundancy     {sp.redundancy_factor}<br>"
                + ("◆ KEYSTONE<br>" if sp.keystone_candidate else "")
                + ("▲ REMOVED<br>"  if is_removed else "")
                + ("✕ SECONDARY EXTINCTION<br>" if is_extinct else "")
                + "<extra></extra>"
            ),
            name=sp.common_name, showlegend=False,
        ))

    fig = go.Figure(traces)
    fig.update_layout(
        paper_bgcolor=P["void"],
        plot_bgcolor=P["void"],
        margin=dict(l=10,r=10,t=36,b=10),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
            font=dict(size=10, color=P["text2"], family="Share Tech Mono, monospace"),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hovermode="closest",
        height=520,
        hoverlabel=dict(
            bgcolor=P["panel"],
            bordercolor=P["border2"],
            font=dict(color=P["text"], family="Share Tech Mono, monospace", size=12),
        ),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# UI components — terminal readout style
# ─────────────────────────────────────────────────────────────────────────────

def readout(label, value, colour, sub=""):
    return html.Div([
        html.Div(label, style={
            "fontSize":"9px", "color":P["text3"], "letterSpacing":".15em",
            "textTransform":"uppercase", "fontFamily":"Share Tech Mono, monospace",
            "marginBottom":"5px",
        }),
        html.Div(value, style={
            "fontSize":"22px", "color":colour,
            "fontFamily":"Share Tech Mono, monospace",
            "lineHeight":"1", "letterSpacing":".02em",
        }),
        html.Div(sub, style={
            "fontSize":"9px", "color":P["text3"],
            "fontFamily":"Share Tech Mono, monospace", "marginTop":"3px",
        }),
    ], style={
        "background": P["surface"],
        "border": f"1px solid {P['border']}",
        "borderTop": f"2px solid {colour}",
        "borderRadius":"2px",
        "padding":"10px 12px",
        "flex":"1", "minWidth":"110px",
        "position":"relative",
    })


def make_metrics_row(metrics, integrity, cost, delta):
    cost_str    = f"${cost/1e9:.1f}B" if cost >= 1e9 else f"${cost/1e6:.0f}M" if cost >= 1e6 else f"${cost:,.0f}"
    int_colour  = P["green"]  if integrity >= 70 else P["amber"] if integrity >= 40 else P["red"]
    delt_colour = P["red"]    if delta > 5       else P["amber"] if delta > 0       else P["green"]
    return html.Div([
        readout("INTEGRITY",        f"{integrity:.1f}",                              int_colour,  "/ 100"),
        readout("DELTA",            f"−{delta:.1f}",                                 delt_colour, "pts lost"),
        readout("EXTINCTIONS",      str(metrics.get("extinction_count", 0)),          P["red"],    "species"),
        readout("CASCADE DEPTH",    str(metrics.get("cascade_depth", 0)),             P["purple"], "waves"),
        readout("CONNECTIVITY ▼",   f"{metrics.get('connectivity_loss',0)*100:.0f}%", P["amber"],  "lost"),
        readout("COST / YR",        cost_str,                                         P["red"],    "est. USD"),
    ], style={"display":"flex","gap":"6px","flexWrap":"wrap","marginBottom":"14px"})


def section_head(text, colour=None):
    c = colour or P["text3"]
    return html.Div([
        html.Span("▶ ", style={"color": P["cyan"], "fontSize":"10px"}),
        html.Span(text, style={"color":c, "letterSpacing":".15em"}),
    ], style={
        "fontSize":"9px", "fontFamily":"Share Tech Mono, monospace",
        "textTransform":"uppercase", "marginBottom":"8px", "marginTop":"18px",
    })


def wire_box(children, accent=None):
    ac = accent or P["border"]
    return html.Div(children, style={
        "background": P["surface"],
        "border": f"1px solid {P['border']}",
        "borderLeft": f"2px solid {ac}",
        "borderRadius":"2px",
        "padding":"12px 14px",
    })


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

GRAPH          = build_demo_graph()
SIM            = CascadeSimulator(GRAPH)
BASE_METRICS   = MetricsEngine.compute(GRAPH, set(), set())
BASE_INTEGRITY = IntegrityIndex.compute(BASE_METRICS)

SPECIES_OPTIONS = [
    {"label": sp.common_name, "value": sp_id}
    for sp_id, sp in sorted(GRAPH.species.items(), key=lambda x: x[1].common_name)
]
LAYER_OPTIONS = [{"label": lid.capitalize(), "value": lid} for lid in GRAPH.layers]

FONTS = (
    "https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap"
)

app = dash.Dash(__name__, title="BUD // QUANTUM MAP", external_stylesheets=[FONTS])

GLOBAL_CSS = """
* { box-sizing: border-box; }
body { background: #000000 !important; margin: 0; overflow: hidden; }

/* Scanline overlay on the whole page */
body::after {
    content: '';
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: repeating-linear-gradient(
        0deg,
        rgba(0,255,180,0.015) 0px,
        rgba(0,255,180,0.015) 1px,
        transparent 1px,
        transparent 3px
    );
    pointer-events: none; z-index: 9999;
}

/* Dropdown — terminal dark */
.Select-control {
    background: #040f06 !important;
    border: 1px solid #0a2e10 !important;
    border-radius: 2px !important;
    color: #a8d4b0 !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 12px !important;
}
.Select-menu-outer {
    background: #020a04 !important;
    border: 1px solid #0a2e10 !important;
    border-radius: 2px !important;
    z-index: 9999 !important;
}
.Select-option {
    background: #020a04 !important;
    color: #a8d4b0 !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 12px !important;
}
.Select-option:hover, .Select-option.is-focused {
    background: #061209 !important; color: #00ffe0 !important;
}
.Select-value-label {
    color: #00ffe0 !important;
    font-family: 'Share Tech Mono', monospace !important;
}
.Select-placeholder {
    color: #1e4424 !important;
    font-family: 'Share Tech Mono', monospace !important;
}
.Select--multi .Select-value {
    background: #003d35 !important;
    border: 1px solid #00c9b1 !important;
    color: #00ffe0 !important;
    border-radius: 2px !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 11px !important;
}
.Select--multi .Select-value-icon:hover { background: #004d43 !important; }
.Select-arrow { border-top-color: #4a8a56 !important; }
.Select-clear { color: #4a8a56 !important; }
.Select-control:hover { border-color: #0f4018 !important; }
.is-focused .Select-control { border-color: #00ffe0 !important; box-shadow: 0 0 0 1px #003d35 !important; }

input[type=radio]    { accent-color: #00ffe0; }
input[type=checkbox] { accent-color: #00ffe0; }

.run-btn:hover   { background: #00c9b1 !important; color: #000 !important; }
.reset-btn:hover { background: #061209 !important; color: #00ffe0 !important; }

::-webkit-scrollbar { width: 3px; }
::-webkit-scrollbar-track { background: #000; }
::-webkit-scrollbar-thumb { background: #0a2e10; border-radius: 1px; }

/* Blinking cursor on header */
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
.cursor { animation: blink 1s step-end infinite; }
"""

app.index_string = app.index_string.replace(
    "</style>",
    GLOBAL_CSS + "</style>",
    1
)

app.layout = html.Div([

    # ── Header bar ────────────────────────────────────────────────────────────
    html.Div([
        # Left — title block
        html.Div([
            html.Span("BUD//", style={
                "color": P["cyan"], "fontSize":"16px",
                "fontFamily":"Share Tech Mono, monospace",
                "letterSpacing":".2em",
            }),
            html.Span("ECOSYSTEM QUANTUM MAP", style={
                "color": P["text"], "fontSize":"16px",
                "fontFamily":"Share Tech Mono, monospace",
                "letterSpacing":".15em",
            }),
            html.Span("█", className="cursor", style={
                "color":P["cyan"], "marginLeft":"4px", "fontSize":"16px",
            }),
        ]),
        # Centre — status strip
        html.Div([
            html.Span("● AMAZON BASIN", style={"color":P["green"], "fontSize":"10px", "marginRight":"20px"}),
            html.Span("20 SPECIES", style={"color":P["text2"], "fontSize":"10px", "marginRight":"20px"}),
            html.Span("4 LAYERS", style={"color":P["text2"], "fontSize":"10px", "marginRight":"20px"}),
            html.Span("PHASE_01", style={
                "color":P["cyan"], "background":P["cyan_dim"],
                "padding":"2px 8px", "borderRadius":"2px",
                "fontSize":"10px", "letterSpacing":".1em",
            }),
        ], style={"fontFamily":"Share Tech Mono, monospace"}),
        # Right — integrity live readout
        html.Div([
            html.Span("SYS.INTEGRITY  ", style={"color":P["text3"],"fontSize":"10px","fontFamily":"Share Tech Mono, monospace"}),
            html.Span(f"{BASE_INTEGRITY:.1f}", id="header-integrity", style={
                "color":P["green"],"fontSize":"20px",
                "fontFamily":"Share Tech Mono, monospace","letterSpacing":".05em",
            }),
            html.Span("/100", style={"color":P["text3"],"fontSize":"10px","fontFamily":"Share Tech Mono, monospace"}),
        ]),
    ], style={
        "display":"flex","justifyContent":"space-between","alignItems":"center",
        "padding":"10px 20px",
        "borderBottom": f"1px solid {P['border']}",
        "background": P["void"],
        "height":"46px",
    }),

    # ── Main layout ───────────────────────────────────────────────────────────
    html.Div([

        # ── Sidebar ───────────────────────────────────────────────────────────
        html.Div([

            section_head("disturbance input"),
            dcc.Dropdown(
                id="species-select", options=SPECIES_OPTIONS,
                placeholder="> select target species...",
                multi=True, style={"marginBottom":"4px"},
            ),
            html.Div("— select one or more species to remove", style={
                "fontSize":"9px","color":P["text3"],
                "fontFamily":"Share Tech Mono, monospace","marginTop":"3px",
            }),

            section_head("simulation mode"),
            dcc.RadioItems(
                id="mode-select",
                options=[
                    {"label":"  MULTILAYER", "value":"multilayer"},
                    {"label":"  MONOLAYER [baseline]", "value":"monolayer"},
                ],
                value="multilayer",
                labelStyle={
                    "display":"block","fontSize":"12px",
                    "color":P["text2"],"fontFamily":"Share Tech Mono, monospace",
                    "marginBottom":"8px","cursor":"pointer","letterSpacing":".05em",
                },
            ),

            section_head("interaction layers"),
            dcc.Checklist(
                id="layer-select",
                options=[
                    {"label": html.Span([
                        html.Span("━ ", style={"color": LAYER_COLOURS.get(o["value"], P["text3"]),"fontSize":"14px"}),
                        html.Span(o["label"].upper(), style={"color":P["text2"],"letterSpacing":".05em"}),
                    ]), "value": o["value"]}
                    for o in LAYER_OPTIONS
                ],
                value=[o["value"] for o in LAYER_OPTIONS],
                labelStyle={
                    "display":"block","fontSize":"11px",
                    "fontFamily":"Share Tech Mono, monospace",
                    "marginBottom":"8px","cursor":"pointer",
                },
            ),

            # Divider
            html.Div(style={
                "borderTop": f"1px solid {P['border']}",
                "margin":"18px 0 14px",
            }),

            # Run button
            html.Button("▶  EXECUTE CASCADE", id="run-btn", n_clicks=0,
                className="run-btn",
                style={
                    "width":"100%","padding":"10px 0",
                    "background": P["cyan2"],
                    "color": P["void"],
                    "border":"none","borderRadius":"2px",
                    "fontSize":"11px","fontFamily":"Share Tech Mono, monospace",
                    "letterSpacing":".18em","cursor":"pointer",
                    "transition":"background .15s",
                }),

            html.Button("↺  RESET", id="reset-btn", n_clicks=0,
                className="reset-btn",
                style={
                    "width":"100%","padding":"8px 0",
                    "background":"transparent",
                    "color":P["text3"],
                    "border":f"1px solid {P['border2']}","borderRadius":"2px",
                    "fontSize":"11px","fontFamily":"Share Tech Mono, monospace",
                    "letterSpacing":".18em","cursor":"pointer",
                    "marginTop":"6px","transition":"all .15s",
                }),

            # Comparison readout
            html.Div(id="comparison-panel", style={"marginTop":"16px"}),

            # Trophic colour key
            html.Div([
                section_head("trophic ramp"),
                *[html.Div([
                    html.Span("■ ", style={"color":col,"fontSize":"13px"}),
                    html.Span(label, style={
                        "fontSize":"10px","color":P["text2"],
                        "fontFamily":"Share Tech Mono, monospace",
                    }),
                ], style={"marginBottom":"4px"})
                for label, col in [
                    ("PRODUCER   TL 1.0", P["blue"]),
                    ("HERBIVORE  TL 2.0", P["cyan"]),
                    ("FRUGIVORE  TL 2.5", P["green"]),
                    ("MESOPRED   TL 3.5", P["amber"]),
                    ("APEX       TL 4.0+", P["orange"]),
                ]],
                html.Div("◆  KEYSTONE SPECIES", style={
                    "fontSize":"10px","color":P["cyan"],
                    "fontFamily":"Share Tech Mono, monospace","marginTop":"8px",
                }),
            ]),

        ], style={
            "width":"210px","flexShrink":"0",
            "padding":"14px 16px",
            "borderRight": f"1px solid {P['border']}",
            "overflowY":"auto",
            "background": P["void"],
            "height":"calc(100vh - 46px)",
        }),

        # ── Main panel ────────────────────────────────────────────────────────
        html.Div([

            html.Div(id="metrics-row", children=[
                make_metrics_row(BASE_METRICS, BASE_INTEGRITY, 0.0, 0.0)
            ]),

            # Network graph
            html.Div([
                dcc.Graph(
                    id="network-graph",
                    figure=make_network_figure(GRAPH),
                    config={"displayModeBar":False},
                    style={"borderRadius":"2px"},
                ),
            ], style={
                "border": f"1px solid {P['border']}",
                "borderTop": f"2px solid {P['cyan_dim']}",
                "borderRadius":"2px",
                "background": P["void"],
                "overflow":"hidden",
            }),

            html.Div(id="cascade-log", style={"marginTop":"12px"}),

        ], style={
            "flex":"1","padding":"16px 20px",
            "overflowY":"auto",
            "background": P["void2"],
            "height":"calc(100vh - 46px)",
        }),

    ], style={"display":"flex","height":"calc(100vh - 46px)","overflow":"hidden"}),

], style={"background": P["void"], "minHeight":"100vh", "fontFamily":"Share Tech Mono, monospace"})


# ─────────────────────────────────────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output("network-graph",    "figure"),
    Output("metrics-row",      "children"),
    Output("cascade-log",      "children"),
    Output("comparison-panel", "children"),
    Output("header-integrity", "children"),
    Output("header-integrity", "style"),
    Input("run-btn",    "n_clicks"),
    Input("reset-btn",  "n_clicks"),
    Input("layer-select","value"),
    State("species-select","value"),
    State("mode-select",  "value"),
    prevent_initial_call=False,
)
def update(run_clicks, reset_clicks, active_layers, selected_species, mode):
    ctx = dash.callback_context
    trigger = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

    base_int_style = {"color":P["green"],"fontSize":"20px","fontFamily":"Share Tech Mono, monospace","letterSpacing":".05em"}

    if "reset-btn" in trigger or not selected_species:
        return (
            make_network_figure(GRAPH, active_layers=active_layers),
            make_metrics_row(BASE_METRICS, BASE_INTEGRITY, 0.0, 0.0),
            html.Div(), html.Div(),
            f"{BASE_INTEGRITY:.1f}", base_int_style,
        )

    if "run-btn" not in trigger and "layer-select" not in trigger:
        raise dash.exceptions.PreventUpdate

    multilayer = (mode == "multilayer")
    result     = SIM.simulate(selected_species, multilayer=multilayer, n_trials=50)
    comparison = SIM.compare_multilayer_vs_monolayer(selected_species, n_trials=50)

    fig = make_network_figure(
        GRAPH,
        highlight_extinct=set(result.extinct_species),
        highlight_removed=set(result.removed_species),
        active_layers=active_layers,
    )

    metrics_row = make_metrics_row(
        result.metrics, result.integrity_score,
        result.estimated_cost_usd, result.integrity_delta,
    )

    # Header integrity colour
    int_colour = P["green"] if result.integrity_score >= 70 else P["amber"] if result.integrity_score >= 40 else P["red"]
    int_style  = {**base_int_style, "color": int_colour}

    # Cascade log
    log_rows = []
    for step in result.cascade_steps:
        names = [GRAPH.species[sp].common_name for sp in step["newly_extinct"] if sp in GRAPH.species]
        if names:
            log_rows.append(html.Div([
                html.Span(f"WAVE_{step['step']:02d}  ", style={
                    "color":P["orange"],"fontSize":"10px",
                    "fontFamily":"Share Tech Mono, monospace","letterSpacing":".1em",
                }),
                html.Span("▶  ", style={"color":P["border2"]}),
                html.Span(", ".join(names), style={
                    "color":P["red"],"fontSize":"11px",
                    "fontFamily":"Share Tech Mono, monospace",
                }),
            ], style={"padding":"5px 0","borderBottom":f"1px solid {P['border']}"}))

    cascade_log = wire_box([
        html.Div("CASCADE_LOG.OUTPUT", style={
            "fontSize":"9px","color":P["text3"],
            "fontFamily":"Share Tech Mono, monospace",
            "letterSpacing":".15em","marginBottom":"8px",
        }),
        html.Div(log_rows if log_rows else
            html.Span("— NO SECONDARY EXTINCTIONS DETECTED —", style={
                "fontSize":"11px","color":P["text3"],
                "fontFamily":"Share Tech Mono, monospace",
            })
        ),
    ], accent=P["orange"]) if result.cascade_steps else html.Div()

    # Comparison panel
    hidden        = comparison["hidden_cascade_events"]
    hidden_colour = P["red"] if hidden > 0 else P["green"]
    hidden_names  = [GRAPH.species[sp].common_name for sp in comparison["hidden_species"] if sp in GRAPH.species]

    comp_panel = wire_box([
        html.Div("LAYER_COMPARISON", style={
            "fontSize":"9px","color":P["text3"],
            "fontFamily":"Share Tech Mono, monospace",
            "letterSpacing":".15em","marginBottom":"10px",
        }),
        *[html.Div([
            html.Span(f"{lbl}  ", style={"fontSize":"9px","color":P["text3"],"fontFamily":"Share Tech Mono, monospace","letterSpacing":".1em"}),
            html.Span(str(val), style={"fontSize":"16px","color":col,"fontFamily":"Share Tech Mono, monospace"}),
        ], style={"marginBottom":"5px"})
        for lbl, val, col in [
            ("HIDDEN ", hidden, hidden_colour),
            ("MULTI  ", comparison["multilayer_extinctions"], P["red"]),
            ("MONO   ", comparison["monolayer_extinctions"],  P["amber"]),
        ]],
        html.Div(
            ", ".join(hidden_names) if hidden_names else "—",
            style={
                "fontSize":"10px","color":hidden_colour,
                "fontFamily":"Share Tech Mono, monospace",
                "marginTop":"6px","lineHeight":"1.6",
            }
        ),
    ], accent=P["cyan"])

    return fig, metrics_row, cascade_log, comp_panel, f"{result.integrity_score:.1f}", int_style


if __name__ == "__main__":
    print(f"\n  BUD // ECOSYSTEM QUANTUM MAP")
    print(f"  {GRAPH.ecosystem_name}")
    print(f"  {GRAPH.species_count()} species  ·  {len(GRAPH.layers)} layers")
    print(f"  Baseline integrity: {BASE_INTEGRITY}/100")
    print("\n  → http://localhost:8050\n")
    app.run(debug=True, port=8050)

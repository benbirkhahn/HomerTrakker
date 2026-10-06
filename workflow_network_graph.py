#!/usr/bin/env python3
"""
HomerTrakker Network Graph

Force-directed view of the core HomerTrakker automation, data stores,
external services, and monitoring surfaces.

Run: python3 workflow_network_graph.py
Visit: http://localhost:8051
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import dash
from dash import Input, Output, State, callback, dcc, html
import networkx as nx
import plotly.graph_objects as go


BASE_DIR = Path(__file__).resolve().parent


NODE_DEFS = {
    "cron": {
        "label": "cron",
        "group": "scheduler",
        "title": "System cron",
        "description": "Triggers the minute poller every minute.",
        "meta": {"cadence": "1 minute", "kind": "scheduler"},
    },
    "poller": {
        "label": "homer_minute_poller.py",
        "group": "pipeline",
        "title": "Minute poller",
        "description": "Checks MLB schedule and live games, then starts the HR pipeline when needed.",
        "meta": {"role": "entrypoint"},
    },
    "mlb_api": {
        "label": "MLB Stats API",
        "group": "external",
        "title": "MLB schedule/live feed",
        "description": "Source of schedules, game states, and live play data.",
        "meta": {"kind": "external service"},
    },
    "state_cache": {
        "label": "~/.homer/state.json",
        "group": "data",
        "title": "Seen HR state",
        "description": "Small local cache that prevents duplicate work.",
        "meta": {"kind": "state file"},
    },
    "post_dir": {
        "label": "MLB_HomeRun_Posts/",
        "group": "data",
        "title": "HR post files",
        "description": "Per-day post folders and homer text/json artifacts.",
        "meta": {"kind": "working directory"},
    },
    "audit_logger": {
        "label": "workflow_audit_logger.py",
        "group": "observability",
        "title": "Workflow audit logger",
        "description": "Records pipeline stages and outcomes for the dashboard.",
        "meta": {"kind": "logger"},
    },
    "dashboard": {
        "label": "workflow_dashboard.py",
        "group": "observability",
        "title": "Workflow dashboard",
        "description": "Interactive status view for detections, failures, and execution details.",
        "meta": {"kind": "dashboard"},
    },
    "enricher": {
        "label": "statcast_enricher.py",
        "group": "pipeline",
        "title": "Statcast enricher",
        "description": "Adds exit velocity, launch angle, and distance to each homer.",
        "meta": {"stage": "enrichment"},
    },
    "stats_json": {
        "label": "stats/homer_X.json",
        "group": "data",
        "title": "Statcast output",
        "description": "Per-homer enriched JSON written alongside the post files.",
        "meta": {"kind": "artifact"},
    },
    "downloader": {
        "label": "download_homer_videos.py",
        "group": "pipeline",
        "title": "Video downloader",
        "description": "Fetches broadcast and animated replay clips.",
        "meta": {"stage": "download"},
    },
    "videos_dir": {
        "label": "videos/",
        "group": "data",
        "title": "Source clips",
        "description": "Downloaded source video assets for each homer.",
        "meta": {"kind": "artifact directory"},
    },
    "compiler": {
        "label": "shorts_video_compiler.py",
        "group": "pipeline",
        "title": "Shorts compiler",
        "description": "Builds the vertical YouTube Short and blurred background composite.",
        "meta": {"stage": "compilation"},
    },
    "shorts_ready": {
        "label": "Shorts_Ready/",
        "group": "data",
        "title": "Compiled shorts",
        "description": "Rendered MP4 output waiting to be uploaded.",
        "meta": {"kind": "artifact directory"},
    },
    "thumbnails_ready": {
        "label": "Thumbnails_Ready/",
        "group": "data",
        "title": "Thumbnail assets",
        "description": "Generated thumbnail frames with overlayed stats.",
        "meta": {"kind": "artifact directory"},
    },
    "uploader": {
        "label": "youtube_homer_bot.py",
        "group": "pipeline",
        "title": "YouTube uploader",
        "description": "Uploads the final Short and removes local video after success.",
        "meta": {"stage": "upload"},
    },
    "youtube_api": {
        "label": "YouTube Data API",
        "group": "external",
        "title": "YouTube upload endpoint",
        "description": "Receives the final video, title, description, tags, and thumbnail.",
        "meta": {"kind": "external service"},
    },
    "youtube_token": {
        "label": "youtube_token.json",
        "group": "data",
        "title": "OAuth token",
        "description": "Persisted auth token used for YouTube uploads.",
        "meta": {"kind": "credential cache"},
    },
    "uploads_ledger": {
        "label": "~/.homer/uploads.json",
        "group": "data",
        "title": "Upload ledger",
        "description": "Prevents duplicate uploads for the same homer.",
        "meta": {"kind": "state file"},
    },
    "publish_queue": {
        "label": "~/.homer/youtube_queue.json",
        "group": "data",
        "title": "YouTube publish queue",
        "description": "Persists reserved publish slots and ranks future uploads by score.",
        "meta": {"kind": "queue file"},
    },
    "n8n_logger": {
        "label": "n8n_audit_logger.py",
        "group": "observability",
        "title": "N8N audit logger",
        "description": "Captures execution details for the N8N-specific dashboard.",
        "meta": {"kind": "logger"},
    },
    "n8n_dashboard": {
        "label": "n8n_workflow_dashboard.py",
        "group": "observability",
        "title": "N8N dashboard",
        "description": "Real-time execution view for the N8N workflow path.",
        "meta": {"kind": "dashboard"},
    },
}


EDGE_DEFS = [
    ("cron", "poller", "triggers", 3),
    ("poller", "mlb_api", "reads schedule + live feed", 3),
    ("poller", "state_cache", "deduplicates", 2),
    ("poller", "post_dir", "creates HR post files", 3),
    ("poller", "audit_logger", "records run status", 2),
    ("post_dir", "enricher", "inputs homer record", 2),
    ("enricher", "stats_json", "writes statcast JSON", 3),
    ("post_dir", "downloader", "feeds download work", 2),
    ("downloader", "videos_dir", "saves clips", 3),
    ("downloader", "compiler", "passes broadcast + animated clips", 3),
    ("compiler", "shorts_ready", "renders MP4", 3),
    ("compiler", "thumbnails_ready", "creates thumbnail source", 2),
    ("shorts_ready", "uploader", "upload candidate", 2),
    ("uploader", "youtube_api", "uploads Short", 3),
    ("uploader", "youtube_token", "uses auth token", 2),
    ("uploader", "uploads_ledger", "guards duplicates", 2),
    ("uploader", "publish_queue", "reserves future slots", 2),
    ("publish_queue", "uploader", "stores schedule policy", 2),
    ("uploader", "videos_dir", "cleans source clips", 1),
    ("audit_logger", "dashboard", "feeds dashboard", 2),
    ("n8n_logger", "n8n_dashboard", "feeds dashboard", 2),
]


GROUP_STYLES = {
    "scheduler": {"label": "Scheduler", "color": "#334155"},
    "pipeline": {"label": "Pipeline", "color": "#0f766e"},
    "data": {"label": "Data / State", "color": "#b45309"},
    "external": {"label": "External", "color": "#1d4ed8"},
    "observability": {"label": "Observability", "color": "#7c3aed"},
}


class HomerTrakkerNetworkGraph:
    def __init__(self) -> None:
        self.graph = self._build_graph()
        self.base_positions = nx.spring_layout(self.graph, seed=42, weight="weight", k=0.9, iterations=200)
        self.app = dash.Dash(__name__)
        self.setup_layout()

    def _build_graph(self) -> nx.Graph:
        graph = nx.Graph()
        for node_id, payload in NODE_DEFS.items():
            graph.add_node(node_id, **payload)
        for source, target, label, weight in EDGE_DEFS:
            graph.add_edge(source, target, label=label, weight=weight)
        return graph

    def _match_node(self, term: str) -> str | None:
        if not term:
            return None
        needle = term.strip().lower()
        if not needle:
            return None
        for node_id, data in NODE_DEFS.items():
            haystack = " ".join(
                [
                    node_id,
                    data.get("label", ""),
                    data.get("title", ""),
                    data.get("description", ""),
                ]
            ).lower()
            if needle in haystack:
                return node_id
        return None

    def _visible_nodes(self, selected_node: str | None, allowed_groups: list[str]) -> set[str]:
        visible = {
            node_id
            for node_id, payload in NODE_DEFS.items()
            if payload["group"] in allowed_groups
        }
        if selected_node:
            visible.add(selected_node)
            visible.update(self.graph.neighbors(selected_node))
        return visible

    def _layout_positions(self, nodes: set[str], freeze_layout: bool) -> dict[str, tuple[float, float]]:
        subgraph = self.graph.subgraph(nodes).copy()
        if freeze_layout:
            return {node_id: self.base_positions[node_id] for node_id in subgraph.nodes}
        seed = int(datetime.now().timestamp()) % 10_000
        return nx.spring_layout(subgraph, seed=seed, weight="weight", k=0.95, iterations=200)

    def _graph_figure(
        self,
        selected_node: str | None,
        allowed_groups: list[str],
        freeze_layout: bool,
        fit_version: int,
    ) -> go.Figure:
        visible_nodes = self._visible_nodes(selected_node, allowed_groups)
        positions = self._layout_positions(visible_nodes, freeze_layout)
        highlighted = {selected_node} if selected_node else set()
        if selected_node:
            highlighted.update(self.graph.neighbors(selected_node))
        visible_edges = [
            edge
            for edge in self.graph.edges(data=True)
            if edge[0] in visible_nodes and edge[1] in visible_nodes
        ]

        fig = go.Figure()

        for source, target, edge_data in visible_edges:
            x0, y0 = positions[source]
            x1, y1 = positions[target]
            edge_weight = edge_data.get("weight", 1)
            is_related = not highlighted or source in highlighted or target in highlighted
            fig.add_trace(
                go.Scatter(
                    x=[x0, x1, None],
                    y=[y0, y1, None],
                    mode="lines",
                    line=dict(
                        width=1.5 + edge_weight * 0.8,
                        color="rgba(71, 85, 105, 0.75)" if is_related else "rgba(148, 163, 184, 0.16)",
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

        node_x = []
        node_y = []
        node_color = []
        node_size = []
        node_text = []
        node_custom = []
        node_hover = []

        for node_id in visible_nodes:
            data = NODE_DEFS[node_id]
            degree = self.graph.degree(node_id)
            related = not highlighted or node_id in highlighted
            group = data["group"]
            color = GROUP_STYLES[group]["color"]
            node_x.append(positions[node_id][0])
            node_y.append(positions[node_id][1])
            node_color.append(color if related else "rgba(148, 163, 184, 0.22)")
            node_size.append(18 + degree * 2.2 if related else 13 + degree * 1.3)
            node_text.append(data["label"])
            node_custom.append(node_id)
            node_hover.append(
                f"<b>{data['label']}</b><br>{data['title']}<br>{data['description']}<br>"
                f"Group: {GROUP_STYLES[group]['label']}<br>Connections: {degree}"
            )

        fig.add_trace(
            go.Scatter(
                x=node_x,
                y=node_y,
                mode="markers+text",
                text=node_text,
                textposition="top center",
                customdata=node_custom,
                hovertext=node_hover,
                hovertemplate="%{hovertext}<extra></extra>",
                marker=dict(
                    size=node_size,
                    color=node_color,
                    line=dict(color="white", width=1.6),
                    opacity=0.98,
                ),
                textfont=dict(size=12, color="#0f172a"),
                showlegend=False,
            )
        )

        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="#f8fafc",
            plot_bgcolor="#f8fafc",
            hovermode="closest",
            clickmode="event+select",
            dragmode="pan",
            showlegend=False,
            uirevision=f"graph-{fit_version}",
            xaxis=dict(showgrid=False, zeroline=False, visible=False),
            yaxis=dict(showgrid=False, zeroline=False, visible=False),
            font=dict(family="Aptos, Segoe UI, sans-serif", color="#0f172a"),
        )
        fig.update_xaxes(autorange=True)
        fig.update_yaxes(autorange=True, scaleanchor="x", scaleratio=1)
        return fig

    def _summary_cards(self, visible_nodes: set[str], selected_node: str | None) -> list[html.Div]:
        visible_edges = [
            edge
            for edge in self.graph.edges(data=True)
            if edge[0] in visible_nodes and edge[1] in visible_nodes
        ]
        groups = {NODE_DEFS[node_id]["group"] for node_id in visible_nodes}
        selected_degree = self.graph.degree(selected_node) if selected_node else 0

        return [
            self._card("Visible nodes", len(visible_nodes), "#0f766e"),
            self._card("Visible edges", len(visible_edges), "#1d4ed8"),
            self._card("Groups", len(groups), "#b45309"),
            self._card("Selected node degree", selected_degree, "#7c3aed"),
        ]

    def _card(self, label: str, value: int, color: str) -> html.Div:
        return html.Div(
            [
                html.Div(str(value), style={"fontSize": "30px", "fontWeight": 700, "color": color, "lineHeight": "1"}),
                html.Div(label, style={"marginTop": "6px", "fontSize": "12px", "color": "#475569"}),
            ],
            style={
                "background": "white",
                "border": "1px solid rgba(148, 163, 184, 0.22)",
                "borderLeft": f"4px solid {color}",
                "borderRadius": "14px",
                "padding": "14px 16px",
                "boxShadow": "0 8px 24px rgba(15, 23, 42, 0.05)",
            },
        )

    def _node_details(self, selected_node: str | None, allowed_groups: list[str]) -> html.Div:
        if not selected_node:
            return html.Div(
                [
                    html.H3("Select a node", style={"marginTop": 0, "marginBottom": "8px"}),
                    html.P(
                        "Click a node or use search to inspect its dependencies, category, and role in the pipeline.",
                        style={"color": "#475569", "lineHeight": 1.5},
                    ),
                ],
                style={
                    "background": "white",
                    "border": "1px solid rgba(148, 163, 184, 0.22)",
                    "borderRadius": "18px",
                    "padding": "18px",
                    "boxShadow": "0 8px 24px rgba(15, 23, 42, 0.05)",
                },
            )

        data = NODE_DEFS[selected_node]
        neighbors = list(self.graph.neighbors(selected_node))
        visible_neighbors = [n for n in neighbors if NODE_DEFS[n]["group"] in allowed_groups or n == selected_node]

        related_items = []
        for neighbor in visible_neighbors:
            edge = self.graph.get_edge_data(selected_node, neighbor, default={})
            related_items.append(
                html.Li(
                    f"{NODE_DEFS[neighbor]['label']} - {edge.get('label', 'connected')}",
                    style={"marginBottom": "6px"},
                )
            )

        return html.Div(
            [
                html.Div(
                    [
                        html.H3(data["label"], style={"margin": 0}),
                        html.Div(
                            GROUP_STYLES[data["group"]]["label"],
                            style={
                                "display": "inline-block",
                                "marginTop": "8px",
                                "padding": "4px 10px",
                                "borderRadius": "999px",
                                "background": GROUP_STYLES[data["group"]]["color"],
                                "color": "white",
                                "fontSize": "12px",
                                "fontWeight": 700,
                            },
                        ),
                    ],
                    style={"marginBottom": "14px"},
                ),
                html.P(data["title"], style={"fontSize": "15px", "fontWeight": 600, "marginBottom": "8px"}),
                html.P(data["description"], style={"color": "#475569", "lineHeight": 1.5, "marginTop": 0}),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div("Connections", style={"fontSize": "12px", "color": "#64748b"}),
                                html.Div(str(self.graph.degree(selected_node)), style={"fontSize": "22px", "fontWeight": 700}),
                            ],
                            style={
                                "background": "#f8fafc",
                                "borderRadius": "12px",
                                "padding": "12px 14px",
                                "border": "1px solid rgba(148, 163, 184, 0.2)",
                            },
                        ),
                        html.Div(
                            [
                                html.Div("Category", style={"fontSize": "12px", "color": "#64748b"}),
                                html.Div(GROUP_STYLES[data["group"]]["label"], style={"fontSize": "22px", "fontWeight": 700}),
                            ],
                            style={
                                "background": "#f8fafc",
                                "borderRadius": "12px",
                                "padding": "12px 14px",
                                "border": "1px solid rgba(148, 163, 184, 0.2)",
                            },
                        ),
                    ],
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                        "gap": "10px",
                        "margin": "14px 0",
                    },
                ),
                html.H4("Related nodes", style={"marginBottom": "8px"}),
                html.Ul(related_items or [html.Li("No related nodes in the current filter.")], style={"paddingLeft": "18px"}),
                html.H4("Metadata", style={"marginBottom": "8px"}),
                html.Pre(
                    "\n".join(f"{key}: {value}" for key, value in data.get("meta", {}).items()) or "No metadata",
                    style={
                        "background": "#0f172a",
                        "color": "#e2e8f0",
                        "padding": "14px",
                        "borderRadius": "12px",
                        "overflowX": "auto",
                        "whiteSpace": "pre-wrap",
                        "marginBottom": 0,
                    },
                ),
            ],
            style={
                "background": "white",
                "border": "1px solid rgba(148, 163, 184, 0.22)",
                "borderRadius": "18px",
                "padding": "18px",
                "boxShadow": "0 8px 24px rgba(15, 23, 42, 0.05)",
            },
        )

    def setup_layout(self) -> None:
        categories = list(GROUP_STYLES.keys())
        self.app.layout = html.Div(
            [
                dcc.Store(id="selected-node", data=None),
                dcc.Store(id="fit-version", data=0),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div("HomerTrakker Network Graph", style={"fontSize": "34px", "fontWeight": 800}),
                                html.Div(
                                    "Force-directed map of the pipeline, state, outputs, and monitoring surfaces.",
                                    style={"marginTop": "6px", "color": "#475569", "fontSize": "15px"},
                                ),
                            ]
                        ),
                        html.Div(
                            [
                                html.Div("Live topology", style={"fontWeight": 700}),
                                html.Div("Filter, search, fit, and inspect nodes", style={"fontSize": "12px", "color": "#475569"}),
                            ],
                            style={
                                "background": "rgba(255,255,255,0.7)",
                                "padding": "12px 14px",
                                "borderRadius": "16px",
                                "border": "1px solid rgba(148, 163, 184, 0.2)",
                                "minWidth": "220px",
                            },
                        ),
                    ],
                    style={
                        "display": "flex",
                        "justifyContent": "space-between",
                        "gap": "16px",
                        "alignItems": "flex-start",
                        "padding": "22px 24px",
                        "marginBottom": "16px",
                        "background": "linear-gradient(135deg, #e2e8f0 0%, #eef6f4 100%)",
                        "borderRadius": "22px",
                        "border": "1px solid rgba(148, 163, 184, 0.2)",
                        "boxShadow": "0 14px 36px rgba(15, 23, 42, 0.06)",
                    },
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div("Search", style={"fontSize": "12px", "fontWeight": 700, "marginBottom": "6px"}),
                                dcc.Input(
                                    id="search",
                                    type="text",
                                    placeholder="Search a node, file, or service",
                                    debounce=True,
                                    style={
                                        "width": "100%",
                                        "padding": "10px 12px",
                                        "borderRadius": "12px",
                                        "border": "1px solid rgba(148, 163, 184, 0.3)",
                                        "fontSize": "14px",
                                    },
                                ),
                            ],
                            style={"minWidth": "260px", "flex": "1"},
                        ),
                        html.Div(
                            [
                                html.Div("Categories", style={"fontSize": "12px", "fontWeight": 700, "marginBottom": "6px"}),
                                dcc.Dropdown(
                                    id="category-filter",
                                    options=[
                                        {"label": GROUP_STYLES[group]["label"], "value": group}
                                        for group in categories
                                    ],
                                    value=categories,
                                    multi=True,
                                    clearable=False,
                                    style={"minWidth": "280px"},
                                ),
                            ],
                            style={"minWidth": "280px", "flex": "1"},
                        ),
                        html.Div(
                            [
                                html.Div("Controls", style={"fontSize": "12px", "fontWeight": 700, "marginBottom": "6px"}),
                                html.Div(
                                    [
                                        html.Button(
                                            "Fit",
                                            id="fit-button",
                                            n_clicks=0,
                                            style=self._button_style("#0f766e"),
                                        ),
                                        html.Button(
                                            "Reset",
                                            id="reset-button",
                                            n_clicks=0,
                                            style=self._button_style("#475569"),
                                        ),
                                    ],
                                    style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
                                ),
                            ],
                            style={"minWidth": "180px"},
                        ),
                        html.Div(
                            [
                                html.Div("Layout", style={"fontSize": "12px", "fontWeight": 700, "marginBottom": "6px"}),
                                dcc.Checklist(
                                    id="freeze-layout",
                                    options=[{"label": "Freeze layout", "value": "freeze"}],
                                    value=["freeze"],
                                    style={
                                        "background": "white",
                                        "border": "1px solid rgba(148, 163, 184, 0.3)",
                                        "borderRadius": "12px",
                                        "padding": "9px 12px",
                                        "fontSize": "14px",
                                    },
                                ),
                            ],
                            style={"minWidth": "180px"},
                        ),
                    ],
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(4, minmax(0, 1fr))",
                        "gap": "12px",
                        "marginBottom": "16px",
                    },
                ),
                html.Div(
                    id="summary-cards",
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(4, minmax(0, 1fr))",
                        "gap": "12px",
                        "marginBottom": "16px",
                    },
                ),
                html.Div(
                    [
                        html.Div(
                            dcc.Graph(
                                id="graph",
                                config={
                                    "displaylogo": False,
                                    "scrollZoom": True,
                                    "responsive": True,
                                    "modeBarButtonsToAdd": ["pan2d", "select2d", "lasso2d"],
                                },
                                style={"height": "82vh"},
                            ),
                            style={
                                "flex": "1.85",
                                "minWidth": "0",
                                "background": "white",
                                "borderRadius": "18px",
                                "border": "1px solid rgba(148, 163, 184, 0.22)",
                                "padding": "8px",
                                "boxShadow": "0 8px 24px rgba(15, 23, 42, 0.05)",
                            },
                        ),
                        html.Div(
                            [
                                html.Div("Legend", style={"fontSize": "16px", "fontWeight": 700, "marginBottom": "10px"}),
                                self._legend(),
                                html.Div(id="node-details", style={"marginTop": "16px"}),
                            ],
                            style={
                                "flex": "0.95",
                                "minWidth": "340px",
                                "display": "flex",
                                "flexDirection": "column",
                                "gap": "12px",
                            },
                        ),
                    ],
                    style={"display": "flex", "gap": "14px", "alignItems": "stretch"},
                ),
            ],
            style={
                "minHeight": "100vh",
                "padding": "16px",
                "background": "linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%)",
                "fontFamily": "Aptos, Segoe UI, sans-serif",
            },
        )

        @callback(
            Output("selected-node", "data"),
            Input("search", "value"),
            Input("graph", "clickData"),
            Input("reset-button", "n_clicks"),
            State("selected-node", "data"),
            prevent_initial_call=False,
        )
        def update_selection(search_value, click_data, reset_clicks, current_selected):
            triggered = dash.ctx.triggered_id
            if triggered == "reset-button":
                return None
            if triggered == "graph" and click_data:
                point = click_data.get("points", [{}])[0]
                return point.get("customdata") or current_selected
            if triggered == "search":
                return self._match_node(search_value) or current_selected
            return current_selected

        @callback(
            Output("graph", "figure"),
            Output("node-details", "children"),
            Output("summary-cards", "children"),
            Input("selected-node", "data"),
            Input("category-filter", "value"),
            Input("freeze-layout", "value"),
            Input("fit-button", "n_clicks"),
        )
        def update_graph(selected_node, category_filter, freeze_layout_value, fit_clicks):
            allowed_groups = category_filter or categories
            freeze_layout = "freeze" in (freeze_layout_value or [])
            visible_nodes = self._visible_nodes(selected_node, allowed_groups)
            figure = self._graph_figure(selected_node, allowed_groups, freeze_layout, fit_clicks or 0)
            details = self._node_details(selected_node, allowed_groups)
            summary_cards = self._summary_cards(visible_nodes, selected_node)
            return figure, details, summary_cards

    def _button_style(self, background_color: str) -> dict:
        return {
            "background": background_color,
            "color": "white",
            "border": "none",
            "borderRadius": "12px",
            "padding": "10px 14px",
            "fontSize": "14px",
            "fontWeight": 700,
            "cursor": "pointer",
        }

    def _legend(self) -> html.Div:
        items = []
        for group_name, payload in GROUP_STYLES.items():
            items.append(
                html.Div(
                    [
                        html.Span(
                            "",
                            style={
                                "display": "inline-block",
                                "width": "12px",
                                "height": "12px",
                                "borderRadius": "999px",
                                "background": payload["color"],
                                "marginRight": "8px",
                            },
                        ),
                        html.Span(payload["label"]),
                    ],
                    style={"display": "flex", "alignItems": "center", "marginBottom": "8px"},
                )
            )

        return html.Div(
            items,
            style={
                "background": "white",
                "border": "1px solid rgba(148, 163, 184, 0.22)",
                "borderRadius": "18px",
                "padding": "16px",
                "boxShadow": "0 8px 24px rgba(15, 23, 42, 0.05)",
            },
        )

    def run(self, debug: bool = True) -> None:
        self.app.run(debug=debug, host="0.0.0.0", port=8051)


if __name__ == "__main__":
    HomerTrakkerNetworkGraph().run()

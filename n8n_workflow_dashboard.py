#!/usr/bin/env python3
"""
N8N Workflow Execution Dashboard
Real-time visualization matching your N8N pipeline flow.

Shows:
- Live node execution timeline
- HR progression through pipeline stages  
- Failure analysis with drill-down
- Execution metrics

Run: python3 n8n_workflow_dashboard.py
Visit: http://localhost:8050
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
import dash
from dash import html, dcc, callback, Input, Output
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from n8n_audit_logger import n8n_logger

BASE_DIR = Path(__file__).resolve().parent


class N8NWorkflowDashboard:
    def __init__(self):
        self.app = dash.Dash(__name__)
        self.setup_layout()
    
    def get_current_execution(self):
        """Get the most recent execution."""
        runs = n8n_logger.get_today_runs()
        return runs[-1] if runs else None
    
    def setup_layout(self):
        """Build Dash layout."""
        self.app.layout = html.Div([
            dcc.Interval(id='refresh', interval=3000, n_intervals=0),  # Refresh every 3s
            
            # Header
            html.Div([
                html.Div([
                    html.H1("🚀 N8N HR Pipeline Execution", style={"marginBottom": "5px"}),
                    html.P("Real-time HomerTrakker workflow dashboard", style={"color": "#7f8c8d", "fontSize": "14px"})
                ], style={"flex": 1}),
                html.Div(id='status-indicator', style={
                    "fontSize": "12px",
                    "padding": "10px 15px",
                    "borderRadius": "5px",
                    "backgroundColor": "#ecf0f1"
                })
            ], style={
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
                "backgroundColor": "#2c3e50",
                "color": "white",
                "padding": "20px",
                "marginBottom": "20px",
                "borderRadius": "5px"
            }),
            
            # Execution summary cards
            html.Div(id='summary-cards', style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fit, minmax(140px, 1fr))",
                "gap": "15px",
                "marginBottom": "20px"
            }),
            
            # N8N Node Timeline
            html.Div([
                html.H3("📊 Node Execution Timeline", style={"marginBottom": "15px"}),
                dcc.Graph(id='node-timeline', style={"height": "300px"})
            ], style={
                "backgroundColor": "white",
                "padding": "20px",
                "borderRadius": "8px",
                "marginBottom": "20px",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.1)"
            }),
            
            # HR Pipeline Sankey
            html.Div([
                html.H3("🏏 HR Flow Through Pipeline", style={"marginBottom": "15px"}),
                dcc.Graph(id='hr-sankey', style={"height": "400px"})
            ], style={
                "backgroundColor": "white",
                "padding": "20px",
                "borderRadius": "8px",
                "marginBottom": "20px",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.1)"
            }),
            
            # HR Cards (live progress)
            html.Div([
                html.H3("🎯 Home Run Cards", style={"marginBottom": "15px"}),
                html.Div(id='homer-cards', style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fill, minmax(280px, 1fr))",
                    "gap": "15px"
                })
            ], style={
                "backgroundColor": "white",
                "padding": "20px",
                "borderRadius": "8px",
                "marginBottom": "20px",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.1)"
            }),
            
            # Failed HRs
            html.Div([
                html.H3("⚠️  Issues & Failures", style={"marginBottom": "15px", "color": "#e74c3c"}),
                html.Div(id='failures-section')
            ], style={
                "backgroundColor": "#fff5f5",
                "padding": "20px",
                "borderRadius": "8px",
                "marginBottom": "20px",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.1)"
            })
        ], style={
            "fontFamily": "Segoe UI, Tahoma, sans-serif",
            "padding": "0",
            "backgroundColor": "#f8f9fa",
            "minHeight": "100vh"
        }, className="main-container")
        
        # Callbacks
        @callback(
            [Output('status-indicator', 'children'),
             Output('summary-cards', 'children'),
             Output('node-timeline', 'figure'),
             Output('hr-sankey', 'figure'),
             Output('homer-cards', 'children'),
             Output('failures-section', 'children')],
            Input('refresh', 'n_intervals')
        )
        def update_all(n):
            execution = self.get_current_execution()
            
            if not execution:
                return (
                    html.Span("⚫ No execution yet", style={"color": "#95a5a6"}),
                    [],
                    go.Figure().add_annotation(text="Awaiting first execution..."),
                    go.Figure().add_annotation(text="Awaiting first execution..."),
                    [html.P("Waiting for pipeline to run...", style={"color": "#95a5a6"})],
                    [html.P("No issues yet!", style={"color": "#2ecc71"})]
                )
            
            # Status indicator
            status = execution.get("status", "running")
            status_color = "#2ecc71" if status == "completed" else "#f39c12"
            status_text = "✓ Completed" if status == "completed" else "⏳ Running"
            status_elem = html.Span(status_text, style={"color": status_color})
            
            # Summary cards
            summary = n8n_logger.get_summary(execution["execution_id"])
            cards = [
                self.make_card("Detected", summary.get("total_homers", 0), "#3498db"),
                self.make_card("Uploaded", summary.get("uploaded", 0), "#2ecc71"),
                self.make_card("Failed", summary.get("failed", 0), "#e74c3c"),
                self.make_card("Pending", summary.get("pending", 0), "#f39c12"),
                self.make_card("Nodes OK", f"{summary.get('nodes_success', 0)}/{summary.get('nodes_total', 0)}", "#9b59b6")
            ]
            
            # Node timeline
            node_fig = self.create_node_timeline(execution)
            
            # HR Sankey flow
            sankey_fig = self.create_hr_sankey(execution)
            
            # HR cards
            homer_cards = self.create_homer_cards(execution)
            
            # Failures
            failures = self.create_failures_section(execution)
            
            return status_elem, cards, node_fig, sankey_fig, homer_cards, failures
    
    def make_card(self, label: str, value: any, color: str) -> html.Div:
        """Create a summary metric card."""
        return html.Div([
            html.Div(str(value), style={
                "fontSize": "28px",
                "fontWeight": "bold",
                "color": color
            }),
            html.Div(label, style={
                "fontSize": "12px",
                "color": "#7f8c8d",
                "marginTop": "5px"
            })
        ], style={
            "textAlign": "center",
            "padding": "15px",
            "backgroundColor": "#ecf0f1",
            "borderRadius": "8px",
            "borderLeft": f"4px solid {color}"
        })
    
    def create_node_timeline(self, execution: dict) -> go.Figure:
        """Create node execution timeline (Gantt-like)."""
        nodes = execution.get("nodes", {})
        
        if not nodes:
            return go.Figure().add_annotation(text="No nodes executed yet")
        
        data = []
        for node_name, node_data in nodes.items():
            start = node_data.get("started_at", "")
            end = node_data.get("completed_at", start)
            status = node_data.get("status", "unknown")
            
            # Color by status
            color = "#2ecc71" if status == "success" else "#e74c3c" if status == "failed" else "#f39c12"
            
            data.append({
                "Task": node_name[:30],  # Truncate long names
                "Start": start,
                "End": end or start,
                "Status": status,
                "Color": color
            })
        
        if not data:
            return go.Figure().add_annotation(text="Processing...")
        
        df = pd.DataFrame(data)
        
        fig = go.Figure()
        for idx, row in df.iterrows():
            fig.add_trace(go.Bar(
                y=[row["Task"]],
                x=[(pd.to_datetime(row["End"]) - pd.to_datetime(row["Start"])).total_seconds()],
                name=row["Status"],
                marker=dict(color=row["Color"]),
                orientation='h',
                hovertemplate=f"<b>{row['Task']}</b><br>Status: {row['Status']}<extra></extra>"
            ))
        
        fig.update_layout(
            title="Node Execution Timeline",
            barmode='stack',
            xaxis_title="Duration (seconds)",
            height=250,
            margin=dict(l=200, r=20, t=30, b=20),
            showlegend=False,
            hovermode='y'
        )
        
        return fig
    
    def create_hr_sankey(self, execution: dict) -> go.Figure:
        """Create Sankey diagram of HRs flowing through stages."""
        homers = execution.get("homers", [])
        
        if not homers:
            return go.Figure().add_annotation(text="No HRs detected yet")
        
        # Count HRs at each stage
        stages = ["detection", "content", "download_diamond", "download_animated", "compile", "upload"]
        stage_counts = {s: 0 for s in stages}
        
        for homer in homers:
            for stage in stages:
                stage_status = homer["stages"].get(stage, {}).get("status")
                if stage_status == "✓":
                    stage_counts[stage] += 1
        
        # Build Sankey
        labels = ["Start"] + stages + ["End"]
        source = [0]
        target = [1]
        value = [len(homers)]
        
        for i in range(len(stages) - 1):
            source.append(i + 1)
            target.append(i + 2)
            value.append(stage_counts.get(stages[i], 0))
        
        # Last to end
        source.append(len(stages))
        target.append(len(stages) + 1)
        value.append(stage_counts.get(stages[-1], 0))
        
        colors = ["#3498db", "#2ecc71", "#3498db", "#3498db", "#f39c12", "#e74c3c", "#2ecc71"]
        
        fig = go.Figure(data=[go.Sankey(
            node=dict(label=labels, color=colors),
            link=dict(source=source, target=target, value=value)
        )])
        
        fig.update_layout(
            title="HR Flow Through Pipeline",
            height=350,
            margin=dict(l=0, r=0, t=30, b=0)
        )
        
        return fig
    
    def create_homer_cards(self, execution: dict) -> list:
        """Create cards for each HR showing pipeline progress."""
        homers = execution.get("homers", [])
        
        if not homers:
            return [html.P("No HRs detected yet", style={"color": "#95a5a6"})]
        
        cards = []
        for homer in homers:
            batter = homer.get("batter", "Unknown")
            game = homer.get("game", "Unknown")
            inning = homer.get("inning", "?")
            stages = homer.get("stages", {})
            
            # Progress bar
            completed = sum(1 for s in stages.values() if s.get("status") == "✓")
            total = len(stages)
            progress_pct = (completed / total * 100) if total > 0 else 0
            
            # Stage badges
            stage_elements = []
            stage_order = ["detection", "content", "download_diamond", "download_animated", "compile", "upload"]
            stage_labels = ["Detect", "Content", "DL Diamond", "DL Anim", "Compile", "Upload"]
            
            for stage_name, label in zip(stage_order, stage_labels):
                stage_data = stages.get(stage_name, {})
                status = stage_data.get("status", "—")
                
                # Color mapping
                if status == "✓":
                    color = "#2ecc71"
                    bg = "#c8e6c9"
                elif status == "✗":
                    color = "#e74c3c"
                    bg = "#ffcdd2"
                else:
                    color = "#95a5a6"
                    bg = "#eceff1"
                
                stage_elements.append(html.Span(
                    f"{label}",
                    title=f"{label}: {status}",
                    style={
                        "display": "inline-block",
                        "fontSize": "10px",
                        "padding": "3px 6px",
                        "borderRadius": "3px",
                        "backgroundColor": bg,
                        "color": color,
                        "fontWeight": "bold",
                        "marginRight": "4px",
                        "marginBottom": "4px"
                    }
                ))
            
            card = html.Div([
                html.Div([
                    html.Span(f"🏏 {batter}", style={"fontWeight": "bold", "fontSize": "14px"}),
                    html.Span(f"{progress_pct:.0f}%", style={
                        "float": "right",
                        "fontSize": "12px",
                        "color": "#7f8c8d"
                    })
                ], style={"marginBottom": "8px"}),
                
                html.Div([
                    html.Span(f"🎮 {game}", style={"fontSize": "11px", "color": "#7f8c8d"}),
                    html.Br(),
                    html.Span(f"📍 Inning: {inning}", style={"fontSize": "11px", "color": "#7f8c8d"})
                ], style={"marginBottom": "10px"}),
                
                # Progress bar
                html.Div([
                    html.Div(
                        "",
                        style={
                            "height": "6px",
                            "backgroundColor": "#ecf0f1",
                            "borderRadius": "3px",
                            "overflow": "hidden"
                        }
                    ),
                    html.Div(
                        "",
                        style={
                            "height": "6px",
                            "width": f"{progress_pct}%",
                            "backgroundColor": "#2ecc71" if progress_pct == 100 else "#3498db",
                            "borderRadius": "3px"
                        }
                    )
                ], style={"position": "relative", "marginBottom": "10px"}),
                
                # Stage badges
                html.Div(stage_elements, style={"display": "flex", "flexWrap": "wrap", "gap": "4px"})
            ], style={
                "border": "1px solid #ecf0f1",
                "borderRadius": "8px",
                "padding": "12px",
                "backgroundColor": "#f8f9fa"
            })
            
            cards.append(card)
        
        return cards
    
    def create_failures_section(self, execution: dict) -> list:
        """Create failures and issues summary."""
        homers = execution.get("homers", [])
        
        failures = []
        for homer in homers:
            for stage_name, stage_data in homer.get("stages", {}).items():
                if stage_data.get("status") == "✗":
                    error = stage_data.get("error", "Unknown error")
                    failures.append({
                        "batter": homer.get("batter"),
                        "stage": stage_name,
                        "error": error
                    })
        
        if not failures:
            return [html.P("✅ No failures detected!", style={"color": "#2ecc71", "fontSize": "14px"})]
        
        failure_elements = []
        for failure in failures:
            failure_elements.append(html.Div([
                html.Div([
                    html.Span(f"🏏 {failure['batter']}", style={"fontWeight": "bold"}),
                    html.Span(f" — Failed at: {failure['stage']}", style={"color": "#e74c3c", "marginLeft": "10px"})
                ], style={"marginBottom": "5px"}),
                html.Div(f"❌ {failure['error']}", style={
                    "fontSize": "12px",
                    "color": "#c0392b",
                    "padding": "8px",
                    "backgroundColor": "#fadbd8",
                    "borderRadius": "3px",
                    "borderLeft": "3px solid #e74c3c"
                })
            ], style={"marginBottom": "12px"}))
        
        return failure_elements
    
    def run(self, debug=True):
        """Run the dashboard."""
        self.app.run(debug=debug, host='0.0.0.0', port=8050)


if __name__ == '__main__':
    dashboard = N8NWorkflowDashboard()
    dashboard.run()

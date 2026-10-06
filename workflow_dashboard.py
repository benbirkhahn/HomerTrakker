#!/usr/bin/env python3
"""
Enhanced Homer Workflow Dashboard
Real-time visualization of the entire HR pipeline: detection → enrichment → download → compilation → upload

Shows user:
- Live HR detections (in real-time from poller)
- Each HR's status through the pipeline
- Failed HRs with error details
- Failure breakdown by stage
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import dash
from dash import html, dcc, callback, Input, Output, State
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from workflow_audit_logger import workflow_logger


BASE_DIR = Path(__file__).resolve().parent


class WorkflowDashboard:
    def __init__(self):
        self.app = dash.Dash(__name__)
        self.setup_layout()
    
    def load_audit_data(self):
        """Load today's audit log."""
        return workflow_logger.get_today_summary()
    
    def load_failed_homers(self):
        """Load list of failed HRs."""
        return workflow_logger.get_failed_homers(limit=50)
    
    def load_all_homers_today(self):
        """Load all HRs from today with full details."""
        runs = workflow_logger._load_today_audit()
        all_homers = []
        for run in runs:
            for homer in run.get("homers", []):
                homer["run_id"] = run.get("run_id")
                all_homers.append(homer)
        return all_homers
    
    def get_stage_status_badge(self, homer: dict, stage: str) -> tuple:
        """
        Get status and style for a pipeline stage.
        Returns: (status_text, color, icon)
        """
        if stage not in homer.get("stages", {}):
            return ("—", "#cccccc", "⚪")
        
        stage_data = homer["stages"][stage]
        status = stage_data.get("status", "unknown")
        
        if status == "success":
            return ("✓", "#2ecc71", "🟢")
        elif status == "failed":
            return ("✗", "#e74c3c", "🔴")
        else:
            return ("...", "#f39c12", "🟡")
    
    def create_homer_card(self, homer: dict) -> html.Div:
        """Create an individual HR status card."""
        batter = homer.get("batter", "Unknown")
        game = homer.get("game", "Unknown")
        inning = homer.get("inning", "?")
        detected_time = homer.get("detected_at", "")[:16]  # YYYY-MM-DD HH:MM
        skipped = homer.get("skipped", False)
        skip_reason = homer.get("skip_reason", "")
        
        # Stage labels and keys
        stages = [
            ("Detection", "detection"),
            ("Enrichment", "enrichment"),
            ("Broadcast", "broadcast_clip"),
            ("Animated", "animated_clip"),
            ("Compile", "compilation"),
            ("Upload", "upload")
        ]
        
        # Build stage indicators
        stage_elements = []
        for label, key in stages:
            status_text, color, icon = self.get_stage_status_badge(homer, key)
            error_msg = homer.get("stages", {}).get(key, {}).get("error", "")
            
            tooltip = f"{label}: {status_text}"
            if error_msg:
                tooltip += f"\nError: {error_msg}"
            
            stage_elements.append(
                html.Span(
                    icon,
                    title=tooltip,
                    style={
                        "color": color,
                        "fontSize": "20px",
                        "marginRight": "8px",
                        "cursor": "help"
                    }
                )
            )
        
        # Determine overall status color
        if skipped:
            card_border = "2px solid #95a5a6"
            status_badge = html.Span("SKIPPED", style={
                "backgroundColor": "#95a5a6",
                "color": "white",
                "padding": "2px 8px",
                "borderRadius": "3px",
                "fontSize": "11px",
                "marginLeft": "10px"
            })
            status_msg = f"Skipped: {skip_reason}"
        else:
            upload_status = homer.get("stages", {}).get("upload", {}).get("status")
            if upload_status == "success":
                card_border = "2px solid #2ecc71"
                status_badge = html.Span("UPLOADED", style={
                    "backgroundColor": "#2ecc71",
                    "color": "white",
                    "padding": "2px 8px",
                    "borderRadius": "3px",
                    "fontSize": "11px",
                    "marginLeft": "10px"
                })
                status_msg = "✅ Successfully uploaded"
            elif upload_status == "failed":
                card_border = "2px solid #e74c3c"
                status_badge = html.Span("FAILED", style={
                    "backgroundColor": "#e74c3c",
                    "color": "white",
                    "padding": "2px 8px",
                    "borderRadius": "3px",
                    "fontSize": "11px",
                    "marginLeft": "10px"
                })
                error = homer.get("stages", {}).get("upload", {}).get("error", "Unknown error")
                status_msg = f"❌ Upload failed: {error}"
            else:
                card_border = "2px solid #f39c12"
                status_badge = html.Span("PENDING", style={
                    "backgroundColor": "#f39c12",
                    "color": "white",
                    "padding": "2px 8px",
                    "borderRadius": "3px",
                    "fontSize": "11px",
                    "marginLeft": "10px"
                })
                status_msg = "⏳ Pending/In Progress"
        
        return html.Div([
            html.Div([
                html.H4(f"🏏 {batter}", style={"marginBottom": "5px"}),
                html.Span(status_badge)
            ], style={"marginBottom": "10px"}),
            
            html.Div([
                html.Span(f"🎮 {game} • Inning: {inning}", style={"fontSize": "13px", "color": "#7f8c8d"}),
                html.Br(),
                html.Span(f"🕐 {detected_time}", style={"fontSize": "12px", "color": "#95a5a6"})
            ], style={"marginBottom": "10px", "fontSize": "13px"}),
            
            html.Div([
                html.Div(stage_elements, style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"}),
            ], style={"marginBottom": "10px"}),
            
            html.Div(status_msg, style={"fontSize": "12px", "color": "#34495e", "fontStyle": "italic"})
        ], style={
            "border": card_border,
            "borderRadius": "8px",
            "padding": "12px",
            "marginBottom": "12px",
            "backgroundColor": "#ecf0f1" if skipped else "#ffffff"
        })
    
    def create_failure_breakdown(self) -> go.Figure:
        """Create pie chart of failures by stage."""
        failed_homers = self.load_failed_homers()
        
        if not failed_homers:
            return go.Figure().add_annotation(text="No failures today! 🎉")
        
        stage_counts = {}
        for homer in failed_homers:
            stage = homer.get("failed_stage", "Unknown")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        
        fig = go.Figure(data=[go.Pie(
            labels=list(stage_counts.keys()),
            values=list(stage_counts.values()),
            marker=dict(colors=["#e74c3c", "#e67e22", "#f39c12", "#f1c40f"])
        )])
        
        fig.update_layout(
            title="Failure Breakdown by Stage",
            height=300,
            margin=dict(l=0, r=0, t=30, b=0)
        )
        
        return fig
    
    def create_hourly_detection_chart(self) -> go.Figure:
        """Create bar chart of detections by hour."""
        all_homers = self.load_all_homers_today()
        
        if not all_homers:
            return go.Figure().add_annotation(text="No detections yet today")
        
        # Extract hour from detected_at
        hourly = {}
        for homer in all_homers:
            detected_at = homer.get("detected_at", "")
            if detected_at:
                hour = detected_at[11:13]  # Extract hour from ISO format
                hourly[hour] = hourly.get(hour, 0) + 1
        
        if not hourly:
            return go.Figure().add_annotation(text="No detections yet today")
        
        fig = go.Figure(data=[go.Bar(
            x=sorted(hourly.keys()),
            y=[hourly[h] for h in sorted(hourly.keys())],
            marker_color="#3498db"
        )])
        
        fig.update_layout(
            title="HR Detections by Hour",
            xaxis_title="Hour",
            yaxis_title="Count",
            height=300,
            margin=dict(l=40, r=0, t=40, b=40)
        )
        
        return fig
    
    def setup_layout(self):
        """Build the Dash layout."""
        self.app.layout = html.Div([
            dcc.Interval(
                id='refresh-interval',
                interval=10000,  # Refresh every 10 seconds
                n_intervals=0
            ),
            
            # Header
            html.Div([
                html.H1("🏏 HomerTrakker Workflow Dashboard", style={"color": "#2c3e50"}),
                html.P("Real-time visibility into the HR pipeline: Detection → Enrichment → Download → Compilation → Upload",
                       style={"color": "#7f8c8d", "fontSize": "14px"})
            ], style={
                "backgroundColor": "#ecf0f1",
                "padding": "20px",
                "marginBottom": "20px",
                "borderRadius": "5px"
            }),
            
            # Summary cards
            html.Div(id='summary-cards', style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
                "gap": "15px",
                "marginBottom": "20px"
            }),
            
            # Charts row
            html.Div([
                html.Div(dcc.Graph(id='hourly-detections'), style={
                    "flexGrow": 1,
                    "minWidth": "300px"
                }),
                html.Div(dcc.Graph(id='failure-breakdown'), style={
                    "flexGrow": 1,
                    "minWidth": "300px"
                })
            ], style={
                "display": "flex",
                "gap": "20px",
                "marginBottom": "20px",
                "flexWrap": "wrap"
            }),
            
            # Tabs for different views
            dcc.Tabs(id='tabs', value='all-homers', children=[
                dcc.Tab(label='All HRs Today', value='all-homers', children=[
                    html.Div([
                        html.Div(id='all-homers-list', style={"maxHeight": "600px", "overflowY": "auto"})
                    ], style={"padding": "20px"})
                ]),
                
                dcc.Tab(label='Failed HRs', value='failed-homers', children=[
                    html.Div([
                        html.Div(id='failed-homers-list', style={"maxHeight": "600px", "overflowY": "auto"})
                    ], style={"padding": "20px"})
                ]),
                
                dcc.Tab(label='Details (JSON)', value='json-view', children=[
                    html.Div([
                        html.Pre(id='json-view', style={
                            "backgroundColor": "#2c3e50",
                            "color": "#ecf0f1",
                            "padding": "15px",
                            "borderRadius": "5px",
                            "overflowX": "auto",
                            "maxHeight": "600px"
                        })
                    ], style={"padding": "20px"})
                ])
            ], style={"marginTop": "20px"})
        ], style={
            "fontFamily": "Segoe UI, Tahoma, sans-serif",
            "padding": "20px",
            "maxWidth": "1200px",
            "margin": "0 auto"
        })
        
        # Callbacks
        @callback(
            [Output('summary-cards', 'children'),
             Output('all-homers-list', 'children'),
             Output('failed-homers-list', 'children'),
             Output('hourly-detections', 'figure'),
             Output('failure-breakdown', 'figure'),
             Output('json-view', 'children')],
            Input('refresh-interval', 'n_intervals')
        )
        def update_dashboard(n):
            audit_data = self.load_audit_data()
            all_homers = self.load_all_homers_today()
            failed_homers = self.load_failed_homers()
            
            # Summary cards
            summary_cards = [
                self.create_summary_card("Detected", audit_data["total_homers_detected"], "#3498db"),
                self.create_summary_card("Uploaded", audit_data["total_uploaded"], "#2ecc71"),
                self.create_summary_card("Failed", audit_data["total_failed"], "#e74c3c"),
                self.create_summary_card("Skipped", audit_data["total_skipped"], "#95a5a6")
            ]
            
            # All HRs cards
            all_homers_cards = [self.create_homer_card(h) for h in all_homers]
            if not all_homers_cards:
                all_homers_cards = [html.P("No HRs detected yet today.", style={"color": "#95a5a6"})]
            
            # Failed HRs list
            failed_cards = [self.create_failed_homer_row(h) for h in failed_homers]
            if not failed_cards:
                failed_cards = [html.P("No failures today! 🎉", style={"color": "#2ecc71", "fontSize": "16px"})]
            
            # Charts
            hourly_fig = self.create_hourly_detection_chart()
            failure_fig = self.create_failure_breakdown()
            
            # JSON view
            json_text = json.dumps({
                "timestamp": datetime.now().isoformat(),
                "summary": audit_data,
                "all_homers": all_homers
            }, indent=2)
            
            return summary_cards, all_homers_cards, failed_cards, hourly_fig, failure_fig, json_text
    
    def create_summary_card(self, label: str, value: int, color: str) -> html.Div:
        """Create a summary metric card."""
        return html.Div([
            html.Div(str(value), style={
                "fontSize": "32px",
                "fontWeight": "bold",
                "color": color
            }),
            html.Div(label, style={
                "fontSize": "12px",
                "color": "#7f8c8d"
            })
        ], style={
            "textAlign": "center",
            "padding": "15px",
            "backgroundColor": "#ecf0f1",
            "borderRadius": "8px"
        })
    
    def create_failed_homer_row(self, homer: dict) -> html.Div:
        """Create a row for a failed HR."""
        return html.Div([
            html.Div([
                html.Span(f"🏏 {homer.get('batter', 'Unknown')}", style={"fontWeight": "bold"}),
                html.Span(f" • {homer.get('game', 'Unknown')}", style={"marginLeft": "10px", "color": "#7f8c8d"})
            ], style={"marginBottom": "5px"}),
            
            html.Div([
                html.Span(f"Failed at: ", style={"fontWeight": "bold"}),
                html.Span(f"{homer.get('failed_stage', 'Unknown')}", style={"color": "#e74c3c"})
            ], style={"marginBottom": "5px", "fontSize": "13px"}),
            
            html.Div(f"Error: {homer.get('error', 'No details')}", style={
                "fontSize": "12px",
                "color": "#7f8c8d",
                "backgroundColor": "#fff5f5",
                "padding": "8px",
                "borderRadius": "3px",
                "borderLeft": "3px solid #e74c3c"
            })
        ], style={
            "borderLeft": "4px solid #e74c3c",
            "paddingLeft": "12px",
            "marginBottom": "12px",
            "padding": "12px",
            "backgroundColor": "#fafafa"
        })
    
    def run(self, debug=True):
        """Run the dashboard server."""
        self.app.run_server(debug=debug, host='0.0.0.0', port=8050)


if __name__ == '__main__':
    dashboard = WorkflowDashboard()
    dashboard.run()

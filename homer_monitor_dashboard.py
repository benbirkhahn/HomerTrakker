#!/usr/bin/env python3
"""
Homer Monitor Dashboard
Web-based monitoring dashboard for HomerTrakker clip timing analysis
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import dash
from dash import html, dcc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from homer_timing_logger import timing_logger

class HomerMonitorDashboard:
    def __init__(self):
        self.app = dash.Dash(__name__)
        self.setup_layout()
        
    def load_timing_data(self, days=7):
        """Load and process timing data from the logs"""
        log_dir = timing_logger.log_dir
        data = []
        
        # Get data from last N days
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            log_file = log_dir / f"clip_timing_{date}.json"
            if log_file.exists():
                try:
                    day_data = json.loads(log_file.read_text())
                    data.extend(day_data)
                except Exception as e:
                    print(f"Error loading {log_file}: {e}")
        
        return data
    
    def process_timing_stats(self, data):
        """Process raw timing data into statistics"""
        stats = {
            'total_events': len(data),
            'both_clips': 0,
            'broadcast_only': 0,
            'delays': [],
            'hourly_distribution': {},
        }
        
        for event in data:
            event_time = datetime.fromisoformat(event['event_time'])
            hour = event_time.hour
            
            if hour not in stats['hourly_distribution']:
                stats['hourly_distribution'][hour] = {'total': 0, 'both': 0, 'broadcast': 0}
            stats['hourly_distribution'][hour]['total'] += 1
            
            if event.get('broadcast_clip_time') and event.get('animated_clip_time'):
                stats['both_clips'] += 1
                stats['hourly_distribution'][hour]['both'] += 1
                # Calculate delays
                b_delay = (datetime.fromisoformat(event['broadcast_clip_time']) - event_time).total_seconds()
                a_delay = (datetime.fromisoformat(event['animated_clip_time']) - event_time).total_seconds()
                stats['delays'].append({
                    'event_id': event['event_id'],
                    'broadcast_delay': b_delay,
                    'animated_delay': a_delay,
                    'total_delay': max(b_delay, a_delay)
                })
            elif event.get('broadcast_clip_time'):
                stats['broadcast_only'] += 1
                stats['hourly_distribution'][hour]['broadcast'] += 1
        
        return stats
    
    def create_delay_histogram(self, delays):
        """Create histogram of clip arrival delays"""
        if not delays:
            return go.Figure()
            
        df = pd.DataFrame(delays)
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=df['broadcast_delay'],
            name='Broadcast Clip',
            opacity=0.75,
            nbinsx=20
        ))
        fig.add_trace(go.Histogram(
            x=df['animated_delay'],
            name='Animated Clip',
            opacity=0.75,
            nbinsx=20
        ))
        fig.update_layout(
            title='Clip Arrival Delay Distribution',
            xaxis_title='Delay (seconds)',
            yaxis_title='Count',
            barmode='overlay'
        )
        return fig
    
    def create_hourly_distribution(self, hourly_data):
        """Create hourly distribution chart"""
        hours = sorted(hourly_data.keys())
        data = {
            'hour': hours,
            'both': [hourly_data[h]['both'] for h in hours],
            'broadcast': [hourly_data[h]['broadcast'] for h in hours],
            'total': [hourly_data[h]['total'] for h in hours]
        }
        df = pd.DataFrame(data)
        
        fig = px.bar(df, x='hour', y=['both', 'broadcast'],
                    title='Hourly Distribution of Clip Arrivals',
                    labels={'hour': 'Hour of Day', 'value': 'Count'},
                    barmode='group')
        return fig
    
    def setup_layout(self):
        """Setup the dashboard layout"""
        self.app.layout = html.Div([
            html.H1('HomerTrakker Monitoring Dashboard'),
            
            html.Div([
                html.H2('Time Range'),
                dcc.Dropdown(
                    id='time-range',
                    options=[
                        {'label': 'Last 24 Hours', 'value': '1'},
                        {'label': 'Last 7 Days', 'value': '7'},
                        {'label': 'Last 30 Days', 'value': '30'}
                    ],
                    value='7'
                )
            ]),
            
            html.Div([
                html.H2('Summary Statistics'),
                html.Div(id='stats-container')
            ]),
            
            html.Div([
                html.H2('Delay Analysis'),
                dcc.Graph(id='delay-histogram')
            ]),
            
            html.Div([
                html.H2('Hourly Distribution'),
                dcc.Graph(id='hourly-distribution')
            ]),
            
            dcc.Interval(
                id='interval-component',
                interval=5*60*1000,  # update every 5 minutes
                n_intervals=0
            )
        ])
        
        @self.app.callback(
            [dash.Output('stats-container', 'children'),
             dash.Output('delay-histogram', 'figure'),
             dash.Output('hourly-distribution', 'figure')],
            [dash.Input('interval-component', 'n_intervals'),
             dash.Input('time-range', 'value')]
        )
        def update_metrics(n, days):
            days = int(days)
            data = self.load_timing_data(days)
            stats = self.process_timing_stats(data)
            
            # Create stats display
            stats_div = html.Div([
                html.P(f"Total Events: {stats['total_events']}"),
                html.P(f"Events with Both Clips: {stats['both_clips']}"),
                html.P(f"Broadcast-Only Events: {stats['broadcast_only']}"),
                html.P(f"Success Rate: {(stats['both_clips']/stats['total_events']*100):.1f}%" 
                      if stats['total_events'] else "N/A")
            ])
            
            # Create visualizations
            delay_hist = self.create_delay_histogram(stats['delays'])
            hourly_dist = self.create_hourly_distribution(stats['hourly_distribution'])
            
            return stats_div, delay_hist, hourly_dist
    
    def run(self, debug=False):
        """Run the dashboard server"""
        self.app.run_server(debug=debug)

def main():
    dashboard = HomerMonitorDashboard()
    dashboard.run(debug=True)

if __name__ == '__main__':
    main()
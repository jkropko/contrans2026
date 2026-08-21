"""
Dash app. Render runs this with gunicorn, which needs `server` at module level.

Replace everything below with your own dashboard. Only two things must survive:
the `server = app.server` line, and reading the port from the environment.
"""

import os

import pandas as pd
from dash import Dash, dcc, html

app = Dash(__name__)
server = app.server          # gunicorn entry point -- Render needs this

df = pd.read_csv("data/sample/members_sample.csv")

app.layout = html.Div(
    [
        html.H1("Replace me"),
        html.P("If you can read this on a Render URL, deployment works."),
        dcc.Dropdown(
            id="entity",
            options=[{"label": n, "value": i} for i, n in zip(df["id"], df["name"])],
            value=df["id"].iloc[0],
        ),
        html.Div(id="detail"),
    ]
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8050)), debug=True)

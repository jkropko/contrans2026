import numpy as np
import pandas as pd
import requests
import plotly.express as px
from dash import Dash, html, dcc

url = 'https://api.congress.gov/v3/member'
params = {'api_key': 'DEMO_KEY'}
r =requests.get(url, params = params)

memberdata = pd.json_normalize(r.json(), record_path=['members'])

member_parties = memberdata.groupby('partyName').size().reset_index()
member_parties = member_parties.rename({0:'count'}, axis=1)

fig = px.bar(member_parties, x='partyName', y='count')

app = Dash(__name__)

app.layout = html.Div([

    html.H1('Congress Transparency Dashboard'),
    dcc.Markdown('This is a very very bad website'),
    dcc.Graph(figure=fig)
])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port='8050')

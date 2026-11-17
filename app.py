import numpy as np
import pandas as pd
import os
import dotenv
import psycopg
from sqlalchemy import create_engine

import plotly.express as px
import plotly.figure_factory as ff

import dash
from dash import dcc, html, Dash
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc

# Connect to our deployed Neon DB
dotenv.load_dotenv()
NEON_DATABASE_URL_UNPOOLED = os.getenv('NEON_DATABASE_URL_UNPOOLED')
NEON_DATABASE_URL_UNPOOLED = NEON_DATABASE_URL_UNPOOLED.replace('postgresql://', 'postgresql+psycopg://')
engine = create_engine(NEON_DATABASE_URL_UNPOOLED, pool_pre_ping=True)

# Create features we will need (using SQL) that won't change depending on what the user does
myquery = '''
SELECT 
    bioguide_id,
    full_name,
    state,
    district,
    party
FROM members
'''
dropdown_df = pd.read_sql_query(myquery, con=engine)
display_names = [n + ' (' + p + ', ' + s + '-' + str(d) + ')' for n, s, d, p in 
                    zip(dropdown_df['full_name'],
                        dropdown_df['state'],
                        dropdown_df['district'],
                        dropdown_df['party'])]
display_names = [x.replace('.0', '').replace('-nan','') for x in display_names]
dropdown_options = [{'label': y, 'value': x} for x, y in 
                     zip(dropdown_df['bioguide_id'], display_names)]



# Add a custom style sheet to control how the dashboard looks
external_stylesheets = [dbc.themes.BOOTSTRAP]

# Define the Dash app as a Python variable
app = Dash(__name__)

# Populate the Dashboard's layout
app.layout = html.Div(
    [
        html.H1('Know Your Representatives in Congress!'),
        dcc.Dropdown(id = 'dropdown', options=dropdown_options, value='M001239'),
        dcc.Tabs(
            [
                dcc.Tab(label = 'Contact and Bio Info', children = [
                    html.Img(id = 'bioimage')
                    ]),
                dcc.Tab(label = 'How They Vote', children = []),
                dcc.Tab(label = 'Who Spends Money On Them?', children = []),
                dcc.Tab(label = 'What Bills Do They Sponsor?', children = [])
                ]
            )
        ]
    )

# Define the callbacks: functions that map a user's action to a result on the dashboard

@app.callback([Output(component_id = 'bioimage', component_property = 'src')], 
              [Input(component_id = 'dropdown', component_property = 'value')])

def get_image(b):
    myquery = f'''
        SELECT image
        FROM members
        WHERE bioguide_id = '{b}'
    '''
    image_url = pd.read_sql_query(myquery, con=engine)['image'][0]
    return [image_url]


# Run the dashboard
if __name__=='__main__':
    app.run(debug=True, host='0.0.0.0', port='8050')
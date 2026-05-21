import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.cloud import bigquery
from openai import OpenAI
import os
import re

# ------------------------- PAGE CONFIG -------------------------
st.set_page_config(
    page_title="Fuel Analytics Dashboard",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ------------------------- CUSTOM CSS -------------------------
st.markdown("""
<style>
    /* Global Background */
    .stApp { background-color: #f0f8ff; }

    /* --- TOP SECTION STYLES (Blue Theme) --- */
    .metric-container {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        text-align: center;
        border-top: 3px solid #3b82f6;
    }
    .metric-value { font-size: 24px; font-weight: bold; color: #1e3a8a; }
    .metric-label { font-size: 12px; color: #64748b; text-transform: uppercase; }

    /* Forecast Card */
    .forecast-card {
        background-color: white;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }

    /* --- CITY AVERAGE CARDS (New Feature) --- */
    .city-card {
        background-color: white;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #e5e7eb;
        text-align: center;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        transition: transform 0.2s;
    }
    .city-card:hover { transform: translateY(-2px); }
    .city-badge { 
        display: inline-block; padding: 4px 10px; border-radius: 12px; 
        font-size: 11px; font-weight: bold; color: white; margin-bottom: 8px;
    }
    .city-price { font-size: 24px; font-weight: 800; color: #1f2937; }
    .city-label { font-size: 13px; color: #6b7280; }

    /* --- RESULTS STYLES (Tankerkoenig Theme) --- */
    .station-card {
        background-color: white;
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        margin: 5px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }
    .station-card:hover { transform: scale(1.01); }
    .price-low { color: green; font-weight: bold; font-size: 1.2em; }
    .price-high { color: red; font-weight: bold; font-size: 1.2em; }
</style>
""", unsafe_allow_html=True)

# ------------------------- CONFIG -------------------------
PROJECT_ID = "your_gcp_project-id"
DATASET_TABLE = "your_gcp_table_name"

client = OpenAI(
    base_url="https://openrouter.ai/api/v1", 
    api_key="your_openrouter_api_key"
)

# SCHEMA (Name/House Number Removed)
SCHEMA = """
station_id: string, price_timestamp: timestamp, 
diesel: float, e5: float, e10: float, 
brand: string, street: string, post_code: string, city: string,
latitude: float, longitude: float
"""

# ------------------------- BACKEND FUNCTIONS -------------------------

@st.cache_data(ttl=600)
def get_forecast_data(fuel_type):
    """Fetches 7-day prediction."""
    bq_client = bigquery.Client(project=PROJECT_ID)
    table_map = {"e5": "e5_results", "diesel": "diesel_results", "e10": "e10_results"}
    table_name = table_map.get(fuel_type, "e5_results")
    
    query = f"""
    SELECT date, predicted_lowest_price, prediction_interval_lower_bound, prediction_interval_upper_bound
    FROM `{PROJECT_ID}.fuel_analytics.{table_name}`
    ORDER BY date ASC
    """
    try:
        return bq_client.query(query).to_dataframe()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_manual_stats(fuel_type, sort_descending=True):
    """Fetches stats for Manual Analytics."""
    bq_client = bigquery.Client(project=PROJECT_ID)
    
    query_brand = f"""
    SELECT brand, AVG({fuel_type}) as avg_price 
    FROM `{PROJECT_ID}.{DATASET_TABLE}`
    WHERE {fuel_type} IS NOT NULL 
    GROUP BY brand 
    ORDER BY COUNT(*) DESC LIMIT 10
    """
    
    sort_order = "DESC" if sort_descending else "ASC"
    query_cities = f"""
    SELECT city, AVG({fuel_type}) as avg_price
    FROM `{PROJECT_ID}.{DATASET_TABLE}`
    WHERE {fuel_type} IS NOT NULL
    GROUP BY city
    HAVING COUNT(*) > 5
    ORDER BY avg_price {sort_order}
    LIMIT 5
    """
    return bq_client.query(query_brand).to_dataframe(), bq_client.query(query_cities).to_dataframe()

def generate_sql_for_city(user_query):
    """
    Robust SQL Generator (Restored Working Logic + New Restrictions).
    """
    prompt = f"""
    You are an expert SQL generator for fuel price analytics.
    Table: `{PROJECT_ID}.{DATASET_TABLE}`
    Schema: {SCHEMA}

    User Input: "{user_query}"

    MANDATORY INSTRUCTIONS:
    1. **Target:** Identify the CITY from the input (e.g., 'Berlin', 'Munich').
    2. **Filtering:** Use `REGEXP_CONTAINS(city, r'(?i)CityName')` for robust matching.
    3. **Columns:** Select `brand`, `street`, `city`, `latitude`, `longitude`, `diesel`, `e5`, `e10`, `price_timestamp`.
       (Do NOT select 'name' or 'house_number').
    4. **Sorting:** Order by `e5 ASC` (Cheapest first).
    5. **Limit:** STRICTLY `LIMIT 20`.
    6. **Ignore:** Ignore requests for specific dates. Always fetch the latest available data (`ORDER BY price_timestamp DESC` logic is implied by sorting cheap prices).
    
    Output ONLY the standard SQL query.
    """
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-3.2-3b-instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300, temperature=0.1
        )
        sql = response.choices[0].message.content.strip()
        return re.sub(r'```sql|```', '', sql).strip()
    except Exception:
        return None

@st.cache_data(ttl=300)
def execute_query(sql):
    try:
        bq_client = bigquery.Client(project=PROJECT_ID)
        return bq_client.query(sql).to_dataframe()
    except Exception:
        return pd.DataFrame()

def get_city_averages(city_name):
    """
    Calculates the average price for Diesel, E5, E10 in the found city.
    Using 'LIKE' to ensure we match what the main query found.
    """
    bq_client = bigquery.Client(project=PROJECT_ID)
    # Simple sanitization
    city_clean = city_name.replace("'", "")
    
    query = f"""
    SELECT 
        AVG(diesel) as avg_diesel,
        AVG(e5) as avg_e5,
        AVG(e10) as avg_e10
    FROM `{PROJECT_ID}.{DATASET_TABLE}`
    WHERE REGEXP_CONTAINS(city, r'(?i){city_clean}')
    """
    try:
        return bq_client.query(query).to_dataframe()
    except Exception:
        return pd.DataFrame()

# ------------------------- VISUALIZATION FUNCTIONS -------------------------

def plot_forecast(df, fuel_type):
    if df.empty:
        st.warning("No forecast data available.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pd.concat([df['date'], df['date'][::-1]]),
        y=pd.concat([df['prediction_interval_upper_bound'], df['prediction_interval_lower_bound'][::-1]]),
        fill='toself', fillcolor='rgba(59, 130, 246, 0.2)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip", showlegend=True, name='Confidence Range'
    ))
    fig.add_trace(go.Scatter(
        x=df['date'], y=df['predicted_lowest_price'],
        mode='lines+markers', line=dict(color='#1e3a8a', width=3),
        marker=dict(size=8), name=f'Predicted {fuel_type.upper()}'
    ))
    
    min_y = df['prediction_interval_lower_bound'].min() * 0.99
    max_y = df['prediction_interval_upper_bound'].max() * 1.01
    
    fig.update_layout(
        title=f"7-Day Price Forecast ({fuel_type.upper()})",
        yaxis_title="Price (€)", xaxis_title="Date",
        yaxis_range=[min_y, max_y], template='plotly_white',
        hovermode="x unified", margin=dict(l=20, r=20, t=40, b=20)
    )
    st.plotly_chart(fig, use_container_width=True)

def display_station_list(df):
    """Displays Top 20 Cheapest Stations."""
    if df.empty: return
    
    # Identify which fuel to show as primary (E5 default, else Diesel)
    # If the user queried specifically for diesel, the SQL sort order might hint, 
    # but generally E5 is the benchmark.
    fuel_col = 'e5' if 'e5' in df.columns else 'diesel'
    
    q25 = df[fuel_col].quantile(0.25)
    
    st.subheader(f"📍 Top {len(df)} Cheapest Stations")

    with st.container(height=600):
        for _, row in df.iterrows():
            price_class = "price-low" if row[fuel_col] <= q25 else "price-high"
            
            st.markdown(f"""
            <div class="station-card">
                <div style="float: right;">
                    <span class="{price_class}">€{row[fuel_col]:.2f}</span>
                </div>
                <strong>{row['brand']}</strong><br>
                <span style="color: #666; font-size: 0.9em;">{row['street']}, {row['city']}</span>
            </div>
            """, unsafe_allow_html=True)

def create_map_visualization(df):
    if df.empty: return
    st.subheader("🗺️ Station Map")
    fig = px.scatter_mapbox(
        df, lat='latitude', lon='longitude', color='brand',
        hover_name='brand', hover_data=['street', 'e5', 'diesel'],
        zoom=10, height=600
    )
    fig.update_layout(mapbox_style="open-street-map", template='plotly_white', margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

def create_ai_charts(df_results):
    st.subheader("📈 Detailed Analysis")
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        # Simple Brand Comparison from search results
        if 'brand' in df_results.columns:
            brand_counts = df_results['brand'].value_counts().reset_index()
            brand_counts.columns = ['brand', 'count']
            fig = px.pie(brand_counts, names='brand', values='count', title='Station Brands Found')
            st.plotly_chart(fig, use_container_width=True)
    with col_a2:
        # Price Distribution
        if 'e5' in df_results.columns:
            fig_vol = px.box(df_results, y='e5', title='E5 Price Range in Search Area')
            st.plotly_chart(fig_vol, use_container_width=True)

# ------------------------- MAIN APP LAYOUT -------------------------

st.title("⛽ Intelligent Fuel Analytics Dashboard")

# --- SECTION 1: KPIS ---
c1, c2, c3, c4 = st.columns(4)
c1.markdown('<div class="metric-container"><div class="metric-value">€1.72</div><div class="metric-label">Avg E5 Today</div></div>', unsafe_allow_html=True)
c2.markdown('<div class="metric-container"><div class="metric-value">€1.65</div><div class="metric-label">Avg Diesel Today</div></div>', unsafe_allow_html=True)
c3.markdown('<div class="metric-container"><div class="metric-value">14,203</div><div class="metric-label">Stations Online</div></div>', unsafe_allow_html=True)
c4.markdown('<div class="metric-container"><div class="metric-value">-2%</div><div class="metric-label">Price Trend (24h)</div></div>', unsafe_allow_html=True)

st.divider()

# --- SECTION 2: 🔮 AI FORECAST ---
st.markdown("### 🔮 7-Day Price Prediction")
st.markdown('<div class="forecast-card">', unsafe_allow_html=True)
f_col1, f_col2 = st.columns([1, 4])
with f_col1:
    st.markdown("**Configuration**")
    forecast_fuel = st.selectbox("Predict for:", ["e5", "diesel", "e10"], key="forecast_select")
    st.caption("Shaded area shows confidence.")
with f_col2:
    df_forecast = get_forecast_data(forecast_fuel)
    plot_forecast(df_forecast, forecast_fuel)
st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# --- SECTION 3: MANUAL ANALYTICS ---
st.subheader("📊 Historical Market Trends")

c_ctrl1, c_ctrl2 = st.columns(2)
with c_ctrl1:
    fuel_select = st.selectbox("Select Fuel Type:", ["e5", "diesel", "e10"], index=0, key="manual_select")
with c_ctrl2:
    col_t1, col_t2 = st.columns([2, 1]) 
    with col_t1: st.write("") 
    with col_t2: 
        show_expensive = st.toggle("Highest Prices?", value=True)

df_brand, df_cities = get_manual_stats(fuel_select, sort_descending=show_expensive)
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.markdown(f"**Average Price by Brand**")
    if not df_brand.empty:
        fig_brand = px.bar(
            df_brand.sort_values('avg_price'), 
            x='avg_price', y='brand', 
            orientation='h', text_auto='.2f',
            color='avg_price', color_continuous_scale='Blues'
        )
        min_b, max_b = df_brand['avg_price'].min(), df_brand['avg_price'].max()
        fig_brand.update_xaxes(range=[min_b*0.95, max_b*1.01])
        fig_brand.update_layout(yaxis_title=None, showlegend=False, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_brand, use_container_width=True)

with col_chart2:
    sort_label = "Highest" if show_expensive else "Lowest"
    st.markdown(f"**Top 5 Cities ({sort_label})**")
    if not df_cities.empty:
        fig_cities = px.bar(
            df_cities, x='city', y='avg_price', text_auto='.3f',
            color='avg_price', color_continuous_scale='Reds' if show_expensive else 'Greens'
        )
        min_c, max_c = df_cities['avg_price'].min(), df_cities['avg_price'].max()
        fig_cities.update_yaxes(range=[min_c*0.99, max_c*1.01])
        fig_cities.update_layout(xaxis_title=None, yaxis_title="Avg Price (€)", margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_cities, use_container_width=True)

# --- SECTION 4: AI SEARCH ---
st.divider() 
st.subheader("🔎 City Smart Search")

# Simple layout, no white box wrapper
c_search, c_btn = st.columns([4, 1])
with c_search:
    user_query = st.text_input("", placeholder="Enter a City Name (e.g. 'Berlin', 'Stuttgart')", label_visibility="collapsed")
with c_btn:
    search_triggered = st.button("Search City", type="primary", use_container_width=True)

# --- SECTION 5: RESULTS ---
if search_triggered and user_query:
    with st.spinner("Analyzing City Prices..."):
        # 1. Generate SQL for Top 20 Cheapest
        sql = generate_sql_for_city(user_query)
        
        # 2. Execute
        if sql:
            df_results = execute_query(sql)
            
            if not df_results.empty:
                # 3. GET CITY AVERAGES
                # We extract the first valid city name found in the results to match correctly
                found_city_name = df_results['city'].iloc[0]
                df_avgs = get_city_averages(found_city_name)
                
                # --- NEW FEATURE: CITY AVERAGE CARDS ---
                st.markdown(f"### 🏙️ Market Overview: {found_city_name}")
                if not df_avgs.empty:
                    ac1, ac2, ac3 = st.columns(3)
                    with ac1:
                        st.markdown(f"""
                        <div class="city-card" style="border-top: 4px solid #16a34a;">
                            <span class="city-badge" style="background-color: #16a34a;">DIESEL</span><br>
                            <div class="city-price">€{df_avgs['avg_diesel'][0]:.2f}</div>
                            <div class="city-label">City Average</div>
                        </div>""", unsafe_allow_html=True)
                    with ac2:
                        st.markdown(f"""
                        <div class="city-card" style="border-top: 4px solid #2563eb;">
                            <span class="city-badge" style="background-color: #2563eb;">SUPER E5</span><br>
                            <div class="city-price">€{df_avgs['avg_e5'][0]:.2f}</div>
                            <div class="city-label">City Average</div>
                        </div>""", unsafe_allow_html=True)
                    with ac3:
                        st.markdown(f"""
                        <div class="city-card" style="border-top: 4px solid #9333ea;">
                            <span class="city-badge" style="background-color: #9333ea;">SUPER E10</span><br>
                            <div class="city-price">€{df_avgs['avg_e10'][0]:.2f}</div>
                            <div class="city-label">City Average</div>
                        </div>""", unsafe_allow_html=True)
                
                st.write("") # Spacer

                # 4. Display List and Map
                col_list, col_map = st.columns([1, 2])
                with col_list: display_station_list(df_results)
                with col_map: create_map_visualization(df_results)
                
                st.divider()
                create_ai_charts(df_results)
                
                with st.expander("Debug SQL"):
                    st.code(sql, language='sql')
            else:
                st.warning("No stations found. Please check the city spelling.")
        else:
            st.error("AI Error: Could not interpret city.")
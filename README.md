# Fuel Analytics & Forecasting Dashboard

## Overview

This project is an end-to-end fuel analytics platform built using:

* Google Cloud Platform (GCP)
* BigQuery
* BigQuery ML
* Python
* Streamlit
* Altair
* PyDeck

The system ingests fuel station data, performs preprocessing and feature engineering in BigQuery, trains machine learning models for forecasting and classification, and visualizes insights through an interactive Streamlit dashboard.

The dashboard allows users to:

* Explore fuel prices interactively
* Filter stations by city, brand, and fuel type
* View fuel price trends over time
* Analyze geographic fuel price distribution
* Forecast future lowest fuel prices using BigQuery ML
* Support future AI/NLP-based filtering and query interaction

---

# Project Architecture

## Data Flow

```text
Raw Fuel Data
      ↓
BigQuery Tables
      ↓
Feature Engineering
      ↓
BigQuery ML Models
      ↓
Forecast Results
      ↓
Python + Streamlit Dashboard
```

---

# Tech Stack

| Component        | Technology             |
| ---------------- | ---------------------- |
| Cloud Platform   | Google Cloud Platform  |
| Data Warehouse   | BigQuery               |
| Machine Learning | BigQuery ML            |
| Dashboard        | Streamlit              |
| Visualization    | Altair, PyDeck         |
| Language         | Python                 |
| Authentication   | Google Cloud SDK + ADC |

---

# Dataset Schema

The dashboard uses fuel station data with the following schema:

| Column          | Type      |
| --------------- | --------- |
| station_id      | STRING    |
| diesel          | FLOAT     |
| e5              | FLOAT     |
| e10             | FLOAT     |
| is_open         | BOOLEAN   |
| price_timestamp | TIMESTAMP |
| brand           | STRING    |
| city            | STRING    |
| house_number    | STRING    |
| latitude        | FLOAT     |
| longitude       | FLOAT     |
| name            | STRING    |
| post_code       | STRING    |
| street          | STRING    |

---

# BigQuery ML Pipeline

## 1. Feature Engineering

A normalized ML table is created from the cleaned fuel dataset.

### ML Base Table

```sql
CREATE OR REPLACE TABLE `fuel_analytics.ml_base` AS
SELECT
  brand,
  city,
  latitude,
  longitude,
  is_open,
  DATE(price_timestamp) AS price_date,
  EXTRACT(DAYOFWEEK FROM price_timestamp) AS day_of_week,
  EXTRACT(WEEK FROM price_timestamp) AS week_of_year,
  'e5' AS fuel_type,
  e5 AS fuel_price
FROM `fuel_analytics.cleaned_base`
WHERE e5 IS NOT NULL;
```

---

## 2. Daily Lowest Price Aggregation

```sql
CREATE OR REPLACE TABLE `fuel_analytics.ml_daily_lowest` AS
SELECT
  fuel_type,
  price_date,
  MIN(fuel_price) AS lowest_price
FROM `fuel_analytics.ml_base`
GROUP BY fuel_type, price_date;
```

---

## 3. Forecasting Model

BigQuery ML ARIMA_PLUS is used to forecast future fuel prices.

```sql
CREATE OR REPLACE MODEL `fuel_analytics.forecast_e5`
OPTIONS (
  MODEL_TYPE = 'ARIMA_PLUS',
  TIME_SERIES_TIMESTAMP_COL = 'price_date',
  TIME_SERIES_DATA_COL = 'lowest_price',
  AUTO_ARIMA = TRUE
) AS
SELECT
  price_date,
  lowest_price
FROM `fuel_analytics.ml_daily_lowest`
WHERE fuel_type = 'e5';
```

---

## 4. Forecast Query

```sql
SELECT *
FROM ML.FORECAST(
  MODEL `fuel_analytics.forecast_e5`,
  STRUCT(7 AS horizon)
);
```

### Forecast Output

| Column                          | Description                 |
| ------------------------------- | --------------------------- |
| forecast_timestamp              | Future prediction date      |
| forecast_value                  | Predicted lowest fuel price |
| prediction_interval_lower_bound | Lower confidence bound      |
| prediction_interval_upper_bound | Upper confidence bound      |

---

# Dashboard Features

## Interactive Filters

Users can filter visualizations dynamically by:

* Fuel Type (Diesel, E5, E10)
* Fuel Brand
* City
* Open Stations Only

---

## KPI Metrics

The dashboard displays:

* Average Fuel Price
* Total Stations
* Total Brands

---

## Visualizations

### 1. Fuel Price Distribution

Interactive Altair boxplots visualize fuel price spread and outliers.

### 2. Fuel Price Trend Over Time

Line charts show average fuel price changes across dates.

### 3. Brand-wise Fuel Analysis

Bar charts compare average fuel prices across brands.

### 4. City-wise Fuel Analysis

City comparison charts identify cheaper and expensive regions.

### 5. Geographic Fuel Map

PyDeck interactive maps display station locations and fuel prices.

### 6. Raw Data Viewer

Expandable data table for exploration and debugging.

---

# Streamlit Dashboard Code Structure

```text
project/
│
├── viz.py                 # Main dashboard
├── requirements.txt       # Python dependencies
├── README.md              # Project documentation
│
└── sql/
    ├── feature_engineering.sql
    ├── forecasting_model.sql
    └── forecast_queries.sql
```

---

# Running the Dashboard

## 1. Install Dependencies

```bash
pip install \
streamlit \
pandas \
altair \
pydeck \
google-cloud-bigquery \
google-cloud-bigquery-storage \
pyarrow \
db-dtypes
```

---

## 2. Authenticate with GCP

```bash
gcloud auth application-default login
```

---

## 3. Run the Streamlit App

```bash
streamlit run viz.py
```

The dashboard will launch locally at:

```text
http://localhost:8501
```

---

# BigQuery Authentication

The project uses Google Application Default Credentials (ADC).

Python BigQuery connection:

```python
from google.cloud import bigquery

client = bigquery.Client(project="data-engineering-480816")
```

---

# Future Enhancements

## Planned ML Features

* Multi-fuel forecasting
* Cheapest refueling recommendation engine
* Station clustering
* Regional anomaly detection
* Dynamic ML model comparison

---

## Planned AI Features

Natural language querying can be integrated so users can type:

```text
Show cheapest diesel stations in Berlin
```

Instead of manually applying filters.

Potential integration options:

* Gemini API
* LangChain
* OpenAI API
* Vertex AI

The AI layer would translate user prompts into dashboard filter states.

---

# Scalability Considerations

The project is designed to scale by:

* Querying data directly from BigQuery
* Using Streamlit caching
* Separating ML pipelines from visualization logic
* Keeping forecasting modular per fuel type
* Supporting future deployment to Cloud Run or GKE

---

# Key Learnings

This project demonstrates:

* Cloud-native analytics architecture
* Time-series forecasting using BigQuery ML
* Interactive dashboard engineering
* Geospatial visualization
* Data engineering workflow integration
* Real-time cloud data connectivity

---

# Author

Fuel Analytics Dashboard Project
Built using GCP, BigQuery ML, and Streamlit.

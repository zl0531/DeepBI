#!/usr/bin/env python
# -*- coding: utf-8 -*-

EXCEL_ECHART_TIPS_MESS = """Here are some examples of generating Excel queries and Python code to create charts using PyEcharts based on user questions."""

MYSQL_ECHART_TIPS_MESS = """Here are some examples of generating MySQL queries and Python code to create charts using PyEcharts based on user questions."""

POSTGRESQL_ECHART_TIPS_MESS = """Here are some examples of generating PostgreSQL queries and Python code to create charts using PyEcharts based on user questions.

You are a helpful assistant that can generate PostgreSQL queries and Python code to create charts using PyEcharts based on user questions.

You will be given a question about data analysis, and your task is to generate PostgreSQL queries and Python code to answer the question and visualize the results using PyEcharts.

The user will provide you with a description of the database schema, including table names, column names, and column descriptions. You should use this information to generate appropriate PostgreSQL queries.

IMPORTANT: Always carefully examine the field descriptions in the schema to understand the actual values stored in the database. When a field description mentions both full names and abbreviations (like "电池电动汽车（BEV）" or "插电式混合动力电动车（PHEV）"), you MUST use the full names in SQL WHERE clauses, not the abbreviations.

For example, if the schema shows:
- field: 'electric_vehicle_type', comment: '车辆的分类，标识为电池电动汽车（BEV）或插电式混合动力电动车（PHEV）。'

Then your SQL query should use the full names in the WHERE clause:
```sql
WHERE electric_vehicle_type IN ('Battery Electric Vehicle (BEV)', 'Plug-in Hybrid Electric Vehicle (PHEV)')
```

And use CASE statements to convert to abbreviations for display:
```sql
CASE 
    WHEN electric_vehicle_type = 'Battery Electric Vehicle (BEV)' THEN 'BEV'
    WHEN electric_vehicle_type = 'Plug-in Hybrid Electric Vehicle (PHEV)' THEN 'PHEV'
    ELSE electric_vehicle_type
END as display_name
```

You should follow these steps:
1. Understand the user's question and the database schema.
2. Generate PostgreSQL queries to retrieve the relevant data, using the full names in WHERE clauses.
3. Generate Python code to process the data and create charts using PyEcharts.
4. Return the complete code that can be executed to generate the charts.

Your code should include:
- Importing necessary libraries (psycopg2, pandas, pyecharts, etc.)
- Connecting to the PostgreSQL database
- Executing the SQL queries
- Processing the data if needed
- Creating charts using PyEcharts
- Returning the chart options as JSON

The output should be formatted as a JSON instance that conforms to the JSON schema below, the JSON is a list of dict,
[
{"echart_name": "Sales over Years", "echart_code": ret_json}
{},
{},
].

Please make sure your code is correct and can be executed without errors.

EXAMPLE FOR ELECTRIC VEHICLES:
When asked to compare BEV and PHEV sales trends, your code should look like this:

```python
import psycopg2
import pandas as pd
from pyecharts.charts import Line
from pyecharts import options as opts
import json

# Database connection parameters
connection = psycopg2.connect(
    dbname="your_dbname",
    user="your_username",
    password="your_password",
    host="your_host",
    port="your_port"
)

# Query to get the number of BEV and PHEV vehicles by model year
query = "SELECT model_year, COUNT(CASE WHEN electric_vehicle_type = 'Battery Electric Vehicle (BEV)' THEN 1 END) AS bev_count, COUNT(CASE WHEN electric_vehicle_type = 'Plug-in Hybrid Electric Vehicle (PHEV)' THEN 1 END) AS phev_count FROM electric_vehicles GROUP BY model_year ORDER BY model_year"

df = pd.read_sql(query, con=connection)
connection.close()

# Data processing
model_years = df["model_year"].astype(str).tolist()
bev_sales = df["bev_count"].tolist()
phev_sales = df["phev_count"].tolist()

# Create chart
line = Line()
line.add_xaxis(model_years)
line.add_yaxis("BEV", bev_sales, stack="")
line.add_yaxis("PHEV", phev_sales, stack="")

line.set_global_opts(
    xaxis_opts=opts.AxisOpts(
        type_="category",
        name="Model Year",
        boundary_gap=False
    ),
    yaxis_opts=opts.AxisOpts(
        type_="value",
        name="Sales Count",
        axistick_opts=opts.AxisTickOpts(is_show=True),
        splitline_opts=opts.SplitLineOpts(is_show=True),
    ),
    title_opts=opts.TitleOpts(is_show=False),
    datazoom_opts=[
        opts.DataZoomOpts(
            is_show=True, type_="slider", xaxis_index=[0],
            range_start=0, range_end=100, orient="horizontal",
            pos_bottom="0px", pos_left="1%", pos_right="1%"
        ),
        opts.DataZoomOpts(
            is_show=True, type_="slider", yaxis_index=[0],
            range_start=0, range_end=100, orient="vertical",
            pos_top="0px", pos_right="1%", pos_bottom="3%"
        ),
    ],
    legend_opts=opts.LegendOpts(
        type_="scroll", pos_top="1%", orient="horizontal"
    ),
    toolbox_opts=opts.ToolboxOpts(
        is_show=True,
        feature={
            "dataZoom": opts.ToolBoxFeatureDataZoomOpts(),
            "dataView": opts.ToolBoxFeatureDataViewOpts(),
            "magicType": opts.ToolBoxFeatureMagicTypeOpts(type_=['line', 'bar', 'stack']),
            "restore": opts.ToolBoxFeatureRestoreOpts(),
            "saveAsImage": opts.ToolBoxFeatureSaveAsImageOpts(),
        },
    ),
)

# Output chart options
ret_json = line.dump_options()
echart_code = json.loads(ret_json)

output = [{"echart_name": "BEV and PHEV Sales Trends", "echart_code": echart_code}]
print(output)
```
"""

MONGODB_ECHART_TIPS_MESS = """Here are some examples of generating MongoDB queries and Python code to create charts using PyEcharts based on user questions."""

CSV_ECHART_TIPS_MESS = """Here are some examples of generating CSV queries and Python code to create charts using PyEcharts based on user questions."""
